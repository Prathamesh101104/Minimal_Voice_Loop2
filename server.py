import os
import time
import json
import random
import asyncio
import re
import logging
from typing import List, Dict, Any, Optional

LOG_FILE = os.path.join(os.path.dirname(__file__), "phone_call_logs.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("voice_loop")

# Load .env file automatically
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import our engines
from tools import (
    execute_tool_with_latency,
    add_to_cart_impl,
    remove_from_cart_impl,
    clear_cart_impl,
    view_cart_impl,
    get_cart_total_impl,
    checkout_cart_impl,
    checkout_single_item_impl,
    calculate_annual_pricing_impl,
    calculate_annual_savings_impl,
    sort_products_impl,
    get_top_k_expensive_products_impl,
    product_info_impl
)
from rag_engine import get_rag_engine

app = FastAPI(title="Nimbus Voice Agent API Server")

# Load product slugs dynamically from catalog.json
catalog_slugs = []
try:
    catalog_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nimbus-voice-agent-starter", "data", "catalog.json")
    if os.path.exists(catalog_path):
        with open(catalog_path, 'r', encoding='utf-8') as f:
            catalog_data = json.load(f)
            catalog_slugs = [p["id"].replace("nimbus-", "") for p in catalog_data.get("products", [])]
except Exception as e:
    logger.exception("Error loading catalog slugs: %s", e)

if not catalog_slugs:
    catalog_slugs = [
        "crm", "leads", "quote", "campaigns", "social", "sites", "books", 
        "invoice", "expense", "people", "recruit", "payroll", "desk", 
        "chat", "knowledge", "projects", "docs", "boards", "analytics", 
        "dashboards", "datapipe", "vault", "sso", "endpoint"
    ]

def clean_text_for_tts(text: str) -> str:
    if not text:
        return ""
    import re
    
    # 1. Strip markdown elements
    text = re.sub(r'#+\s*(.*?)\n', r'\1. ', text)
    text = text.replace('**', '').replace('*', '').replace('__', '').replace('_', '')
    text = text.replace('`', '')
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # 2. Handle parenthetical annotations (e.g., "(Starter · 1 seat)" or "(Category: HR)")
    text = re.sub(r'\(([^)]*?)·([^)]*?)\)', r' \1 with \2 ', text)
    text = re.sub(r'\(([^)]*?):([^)]*?)\)', r' \1 \2 ', text)
    text = text.replace('(', ', ').replace(')', ', ')

    # 3. Clean up list structures and bullet points
    def list_replacer(match):
        num = int(match.group(1))
        mapping = {1: "First, ", 2: "Second, ", 3: "Third, ", 4: "Fourth, ", 5: "Fifth, "}
        return mapping.get(num, f"Number {num}, ")
    text = re.sub(r'(?:^|\n)\s*(\d+)\.\s+', list_replacer, text)
    text = re.sub(r'(?:^|\n)\s*[•\-\*]\s+', ', ', text)
    
    # 4. Clean up colons, dashes, and mid-sentence spacers
    text = text.replace(' - ', ', ').replace(' – ', ', ')
    text = text.replace('·', ', ')
    
    # 5. Price translations
    text = re.sub(r'\$(\d+(?:\.\d+)?)/mo\b', r'\1 dollars per month', text)
    text = re.sub(r'\$(\d+(?:\.\d+)?)/yr\b', r'\1 dollars per year', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*\$?\s*/\s*mo\b', r'\1 dollars per month', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*\$?\s*/\s*yr\b', r'\1 dollars per year', text)
    text = re.sub(r'/mo\b', ' per month', text)
    text = re.sub(r'/yr\b', ' per year', text)
    text = re.sub(r'/user/mo\b', ' per user per month', text)
    text = text.replace('$', ' dollars ')
    
    # 6. SaaS Abbreviations and shortcuts
    abbrevs = {
        r'\bapprox\b': 'approximately',
        r'\bapprox\.\b': 'approximately',
        r'\bvs\b': 'versus',
        r'\be\.g\.\b': 'for example',
        r'\bi\.e\.\b': 'that is',
        r'\bw/o\b': 'without',
        r'\bw/\b': 'with',
        r'\bincl\.\b': 'including',
        r'\bmin\.\b': 'minimum',
        r'\bmax\.\b': 'maximum',
        r'\bqty\b': 'quantity',
        r'\bno\.\b': 'number',
        r'\bmo\.\b': 'month',
        r'\byr\.\b': 'year',
        r'\bCRM\b': 'C R M',
        r'\bHR\b': 'H R',
        r'\bIT\b': 'I T',
        r'\bBI\b': 'B I'
    }
    for pattern, replacement in abbrevs.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
    # 7. Clean up spacing
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r',\s*,', ',', text)
    return text.strip()

def is_valid_key(prov: str, key: Optional[str]) -> bool:
    if not key:
        return False
    k = key.strip()
    return len(k) > 10

def count_tokens(text: str) -> int:
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model("gpt-4o-mini")
        return len(encoding.encode(text))
    except Exception:
        return len(text.split()) * 4 // 3

def pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    import struct
    import io
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(pcm)))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(pcm)))
    buf.write(pcm)
    return buf.getvalue()

def resample_pcm(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Linearly resample mono 16-bit PCM to match the Vobiz stream rate."""
    if from_rate == to_rate or not pcm:
        return pcm
    import array
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return b""
    ratio = to_rate / from_rate
    out = array.array("h")
    for i in range(max(1, int(len(samples) * ratio))):
        src_pos = i / ratio
        idx = int(src_pos)
        frac = src_pos - idx
        if idx + 1 < len(samples):
            value = samples[idx] * (1 - frac) + samples[idx + 1] * frac
        elif idx < len(samples):
            value = samples[idx]
        else:
            value = samples[-1]
        out.append(max(-32768, min(32767, int(value))))
    return out.tobytes()

PHONE_GREETING = (
    "Welcome to Nimbus Automated Support! How can I help you with our products, pricing, or features today?"
)
# Use 8 kHz for the PSTN stream to match telephony media and reduce packet loss.
VOBIZ_STREAM_SAMPLE_RATE = 8000
VOBIZ_FRAME_MS = 20

def generate_mock_voice_response(query: str, cart: list, enabled_tools: list, history: list = None) -> tuple[str, list, list]:
    q = query.lower().strip()
    updated_cart = list(cart)
    tool_calls = []
    
    def is_enabled(t):
        return t in enabled_tools
        
    from tools import (
        add_to_cart_impl, remove_from_cart_impl, clear_cart_impl,
        get_cart_total_impl, checkout_cart_impl, sort_products_impl,
        get_top_k_expensive_products_impl, product_info_impl
    )
    
    if any(w in q for w in ["stop", "cancel", "shut up", "quiet"]):
        return "Okay, stopping.", updated_cart, tool_calls
        
    # 2. GREETINGS
    if any(q.startswith(w) for w in ["hello", "hi", "hey", "good morning", "good afternoon"]):
        return "Hello! I am Nimbus. I can help you search the product catalog, check prices, manage your cart, and checkout.", updated_cart, tool_calls

    # 3. HELP
    if any(w in q for w in ["help", "what can you do", "options"]):
        return "I can help you add items to your cart, list products, sort them by price, calculate annual savings, and complete your purchase. What would you like to do?", updated_cart, tool_calls

    # 4. COMPANY POLICIES
    if any(w in q for w in ["refund", "return", "money-back", "money back", "satisfied"]):
        return "Nimbus offers a comprehensive 30-day money-back guarantee for all new subscriptions. You can request a full refund within the first 30 days of purchase through your billing console.", updated_cart, tool_calls
        
    if any(w in q for w in ["trial", "free trial", "test", "evaluation"]):
        return "All Nimbus products include a 14-day free trial with full access to premium features, and no credit card is required to sign up.", updated_cart, tool_calls
        
    if any(w in q for w in ["cancellation", "cancel my subscription", "delete account", "downgrade"]):
        return "You can cancel or downgrade your plan anytime from the billing portal. Your account stays active until the end of the billing cycle, and we retain data for 60 days.", updated_cart, tool_calls
        
    if any(w in q for w in ["support", "contact", "email", "help desk", "phone number"]):
        return "You can contact Nimbus Support at support@nimbus.example, phone sales at +1 (800) 555-0142, or visit our Help Center.", updated_cart, tool_calls

    if any(w in q for w in ["sla", "uptime", "outage", "credit"]):
        return "We guarantee a 99.9% uptime SLA for standard plans and 99.99% for enterprise. Service credits are issued if we fail to meet this.", updated_cart, tool_calls

    if any(w in q for w in ["security", "gdpr", "ccpa", "encrypt"]):
        return "Nimbus is fully SOC 2 Type II and ISO 27001 compliant. Data residency choices include regional data centers in the US, EU, India, and Australia.", updated_cart, tool_calls

    # 5. CART OPERATIONS: ADD TO CART
    if ("add" in q or "buy" in q or "purchase" in q or "get" in q) and ("cart" in q or "in my cart" in q):
        # A. Cheapest products addition to cart
        if "cheapest" in q or "cheap" in q or "lowest" in q:
            if is_enabled("sort_products") and is_enabled("add_to_cart"):
                import re
                k_match = re.search(r'\b(\d+)\b', q)
                k = int(k_match.group(1)) if k_match else 3
                res = sort_products_impl("asc")
                cheapest_k = res["products"][:k]
                added_names = []
                for p in cheapest_k:
                    add_res = add_to_cart_impl(updated_cart, p["name"], "Starter")
                    updated_cart = add_res["cart"]
                    added_names.append(p["name"])
                tool_calls.append({"name": "sort_products", "args": {"order": "asc"}, "result": res})
                return f"I have added the top {k} cheapest products ({', '.join(added_names)}) to your cart.", updated_cart, tool_calls
                
        # B. Expensive products addition to cart
        if "expensive" in q or "costliest" in q:
            if is_enabled("get_top_k_expensive_products") and is_enabled("add_to_cart"):
                import re
                k_match = re.search(r'\b(\d+)\b', q)
                k = int(k_match.group(1)) if k_match else 3
                res = get_top_k_expensive_products_impl(k)
                added_names = []
                for p in res["products"]:
                    add_res = add_to_cart_impl(updated_cart, p["name"], "Starter")
                    updated_cart = add_res["cart"]
                    added_names.append(p["name"])
                tool_calls.append({"name": "get_top_k_expensive_products", "args": {"k": k}, "result": res})
                return f"I have added the top {k} most expensive products ({', '.join(added_names)}) to your cart.", updated_cart, tool_calls

        # C. Single product addition
        matched_prod = None
        for p in catalog_slugs:
            if p in q:
                matched_prod = p
                break
        prod_name = f"Nimbus {matched_prod.capitalize()}" if matched_prod else "Nimbus CRM"
        
        tier = "Starter"
        for t in ["free", "starter", "professional", "pro", "enterprise"]:
            if t in q:
                tier = t.capitalize()
                if tier == "Pro":
                    tier = "Professional"
                break
                
        import re
        seats_match = re.search(r'\b(\d+)\b\s*(?:seat|user|license)', q)
        seats = int(seats_match.group(1)) if seats_match else 1
        
        if is_enabled("add_to_cart"):
            res = add_to_cart_impl(updated_cart, prod_name, tier, seats)
            updated_cart = res["cart"]
            tool_calls.append({"name": "add_to_cart", "args": {"product_id_or_name": prod_name, "tier_name": tier, "seats": seats}, "result": res})
            return f"I have added {seats} seat{'s' if seats > 1 else ''} of {prod_name} ({tier} tier) to your cart.", updated_cart, tool_calls

    # 6. CART OPERATIONS: REMOVE FROM CART
    if ("remove" in q or "delete" in q or "take off" in q) and "cart" in q:
        matched_prod = None
        for p in catalog_slugs:
            if p in q:
                matched_prod = p
                break
        prod_name = f"Nimbus {matched_prod.capitalize()}" if matched_prod else "Nimbus CRM"
        
        if is_enabled("remove_from_cart"):
            res = remove_from_cart_impl(updated_cart, prod_name)
            updated_cart = res["cart"]
            tool_calls.append({"name": "remove_from_cart", "args": {"product_id_or_name": prod_name}, "result": res})
            return f"I have removed {prod_name} from your cart.", updated_cart, tool_calls

    # 7. CART OPERATIONS: CLEAR / CHECKOUT
    if "clear" in q and "cart" in q:
        if is_enabled("clear_cart"):
            res = clear_cart_impl(updated_cart)
            updated_cart = res["cart"]
            tool_calls.append({"name": "clear_cart", "args": {}, "result": res})
            return "Your cart has been cleared.", updated_cart, tool_calls

    if ("view" in q or "show" in q or "list" in q or "see" in q or "check" in q or "what" in q) and ("cart" in q or "my items" in q or "card" in q or "items" in q):
        if is_enabled("view_cart"):
            res = view_cart_impl(updated_cart)
            tool_calls.append({"name": "view_cart", "args": {}, "result": res})
            return f"Here are the items in your cart: {res['formatted_list']}", updated_cart, tool_calls

    if "checkout" in q or "pay" in q or "complete purchase" in q:
        if is_enabled("checkout_cart"):
            res = checkout_cart_impl(updated_cart)
            updated_cart = res["cart"]
            tool_calls.append({"name": "checkout_cart", "args": {}, "result": res})
            return f"Checkout completed successfully! Order total was ${res.get('total', 0.0):.2f}.", updated_cart, tool_calls

    # 8. MATHEMATICAL SUMS & TOTALS
    last_user_query = ""
    if history:
        for msg in reversed(history):
            if msg.get("role") == "user":
                last_user_query = msg.get("content", "").lower()
                break

    # 7.5 ANNUAL PRICING AND SAVINGS
    if "annual" in q or "yearly" in q or "year" in q:
        is_savings = "saving" in q or "save" in q
        matched = []
        
        # Check if query is about the products in the shopping cart
        if "cart" in q or "my items" in q or "present in my" in q:
            if not cart:
                return "Your shopping cart is currently empty. Please add some products to your cart first!", updated_cart, tool_calls
            for item in cart:
                name = item.get("name", "").lower()
                for slug in catalog_slugs:
                    if slug in name and slug not in matched:
                        matched.append(slug)
                        
        if not matched:
            for slug in catalog_slugs:
                aliases = [slug]
                if slug == "docs":
                    aliases.append("dogs")
                if slug == "leads":
                    aliases.append("needs")
                if any(alias in q for alias in aliases):
                    matched.append(slug)
                
        if not matched and history:
            for msg in reversed(history):
                if msg.get("role") == "user":
                    hist_q = msg.get("content", "").lower()
                    for slug in catalog_slugs:
                        aliases = [slug]
                        if slug == "docs":
                            aliases.append("dogs")
                        if slug == "leads":
                            aliases.append("needs")
                        if any(alias in hist_q for alias in aliases):
                            matched.append(slug)
                    if matched:
                        break
                        
        if matched:
            results = []
            total_monthly = 0.0
            total_annual = 0.0
            for slug in matched:
                p_res = sort_products_impl("asc")
                prod_detail = next((p for p in p_res["products"] if slug in p["name"].lower()), None)
                if prod_detail:
                    price = float(prod_detail["starter_price"])
                    # Use actual cart item price if available
                    cart_item = next((item for item in cart if slug in item.get("name", "").lower()), None)
                    if cart_item:
                        price = float(cart_item.get("price", price))
                    ann_res = calculate_annual_pricing_impl(price)
                    total_monthly += price
                    total_annual += ann_res["annual_total"]
                    results.append(f"Nimbus {slug.capitalize()} (${price}/mo monthly, or ${ann_res['discounted_monthly_rate']:.2f}/mo annually)")
            
            names_str = ", ".join(results)
            if is_savings:
                monthly_annualized = total_monthly * 12
                savings = monthly_annualized - total_annual
                if is_enabled("calculate_annual_savings"):
                    tool_calls.append({"name": "calculate_annual_savings", "args": {"monthly_price": total_monthly}, "result": {"success": True, "savings": savings}})
                return f"By billing annually, the upfront cost for {', '.join([s.capitalize() for s in matched])} is ${total_annual:.2f}/yr compared to ${monthly_annualized:.2f}/yr monthly, saving you ${savings:.2f}/year.", updated_cart, tool_calls
            else:
                if is_enabled("calculate_annual_pricing"):
                    tool_calls.append({"name": "calculate_annual_pricing", "args": {"monthly_price": total_monthly}, "result": {"success": True, "annual_total": total_annual}})
                return f"The annual rate for {names_str} is ${total_annual:.2f} per year total.", updated_cart, tool_calls
        else:
            return "Nimbus offers a 20% discount on all products when billed annually. For example, Nimbus CRM is $12/mo billed annually ($144/yr) instead of $15/mo.", updated_cart, tool_calls

    is_math_query = (
        "sum" in q or "total" in q or "calculate" in q or "add up" in q or "plus" in q or "final price" in q or
        ("add" in q and ("price" in q or "cost" in q or "number" in q or "together" in q or "math" in q))
    )
    
    if is_math_query:
        if "cart" in q or "my items" in q or "in cart" in q:
            if is_enabled("get_cart_total"):
                res = get_cart_total_impl(updated_cart)
                tool_calls.append({"name": "get_cart_total", "args": {}, "result": res})
                return f"The total price of the items in your cart is ${res['total']:.2f} per month.", updated_cart, tool_calls
                
        # Cheapest products sum context
        if "cheapest" in q or "lowest" in q or "cheapest" in last_user_query or "lowest" in last_user_query:
            import re
            k_match = re.search(r'\b(\d+)\b', q)
            k = int(k_match.group(1)) if k_match else 3
            res = sort_products_impl("asc")
            if is_enabled("sort_products"):
                tool_calls.append({"name": "sort_products", "args": {"order": "asc"}, "result": res})
            cheapest_k = res["products"][:k]
            total = sum(float(p.get("starter_price", 0)) for p in cheapest_k)
            names = ", ".join([p["name"] for p in cheapest_k])
            return f"The sum of the starter prices for the {k} cheapest products ({names}) is ${total:.2f} per month.", updated_cart, tool_calls
                
        # Expensive products sum context
        import re
        k_match = re.search(r'\b(\d+)\b', q)
        k = int(k_match.group(1)) if k_match else 3
        res = get_top_k_expensive_products_impl(k)
        if is_enabled("get_top_k_expensive_products"):
            tool_calls.append({"name": "get_top_k_expensive_products", "args": {"k": k}, "result": res})
        total = sum(float(p.get("starter_price", 0)) for p in res["products"])
        names = ", ".join([p["name"] for p in res["products"]])
        return f"The sum of the starter prices for the {k} most expensive products ({names}) is ${total:.2f} per month.", updated_cart, tool_calls

    # 9. CHEAPEST / EXPENSIVE FILTERING
    if "expensive" in q or "costliest" in q:
        import re
        k_match = re.search(r'\b(\d+)\b', q)
        k = int(k_match.group(1)) if k_match else 3
        res = get_top_k_expensive_products_impl(k)
        if is_enabled("get_top_k_expensive_products"):
            tool_calls.append({"name": "get_top_k_expensive_products", "args": {"k": k}, "result": res})
        items = [f"{p['name']} at ${p['starter_price']}/mo" for p in res["products"]]
        return f"The top {k} most expensive products are: " + ", ".join(items) + ".", updated_cart, tool_calls

    if "cheapest" in q or "cheap" in q or "lowest" in q:
        import re
        k_match = re.search(r'\b(\d+)\b', q)
        k = int(k_match.group(1)) if k_match else 3
        res = sort_products_impl("asc")
        if is_enabled("sort_products"):
            tool_calls.append({"name": "sort_products", "args": {"order": "asc"}, "result": res})
        cheapest_k = res["products"][:k]
        items = [f"{p['name']} at ${p['starter_price']}/mo" for p in cheapest_k]
        return f"The top {k} cheapest products are: " + ", ".join(items) + ".", updated_cart, tool_calls

    # 10. GENERAL LIST / SHOW ALL
    if "list" in q or "show" in q or "all products" in q or "listen" in q or "products" in q:
        res = sort_products_impl("asc")
        if is_enabled("sort_products"):
            tool_calls.append({"name": "sort_products", "args": {"order": "asc"}, "result": res})
        top_few = [p["name"] for p in res["products"][:5]]
        return f"Nimbus has {len(res['products'])} products. The lowest priced ones include " + ", ".join(top_few) + ". Would you like to hear about a specific one?", updated_cart, tool_calls

    # 11. DETAILED PRODUCT INFO / COST LOOKUP
    matched_prod = None
    all_prods = sort_products_impl("asc").get("products", [])
    matched_obj = None
    
    for p in all_prods:
        p_name_lower = p["name"].lower()
        clean_p_name = p_name_lower.replace("nimbus ", "")
        if p_name_lower in q or clean_p_name in q:
            matched_obj = p
            break
            
    if not matched_obj:
        for prod in catalog_slugs:
            if prod in q:
                matched_obj = next((p for p in all_prods if prod in p["name"].lower()), None)
                if matched_obj:
                    break

    if matched_obj:
        prod_name = matched_obj["name"]
        res = product_info_impl(prod_name)
        if res.get("success"):
            if is_enabled("product_info"):
                tool_calls.append({"name": "product_info", "args": {"product_name": prod_name}, "result": res})
            
            tier_strs = []
            for t in res.get("tiers", []):
                m_price = int(t['monthly']) if t['monthly'] == int(t['monthly']) else t['monthly']
                a_price = int(t['annual_monthly']) if t['annual_monthly'] == int(t['annual_monthly']) else t['annual_monthly']
                if t['name'] == 'Free' or m_price == 0:
                    tier_strs.append("Free tier at $0")
                elif a_price < m_price:
                    tier_strs.append(f"{t['name']} tier at ${a_price} per month billed annually (${m_price} monthly)")
                else:
                    tier_strs.append(f"{t['name']} tier at ${m_price} per month")
            
            pricing_formatted = ", ".join(tier_strs)
            starter_annual = res['tiers'][1]['annual_monthly'] if len(res.get('tiers', [])) > 1 else res['tiers'][0]['annual_monthly']
            starter_annual_int = int(starter_annual) if starter_annual == int(starter_annual) else starter_annual
            return f"{res['name']} is a {res['category']} solution. {res['name']} starts from ${starter_annual_int} per month. Pricing tiers are: {pricing_formatted}.", updated_cart, tool_calls
        return f"{matched_obj['name']} starts at ${matched_obj['starter_price']} per month.", updated_cart, tool_calls

    # 12. DEFAULT FALLBACK
    return "I am listening. Please ask your question about any Nimbus product or pricing.", updated_cart, tool_calls


def get_gemini_tools_and_runner(cart_state, enabled_tools):
    current_cart = list(cart_state)
    tools_list = []
    
    if "add_to_cart" in enabled_tools:
        def add_to_cart(product_id_or_name: str, tier_name: str = None, seats: int = 1) -> str:
            """Add a specific product and its tier (Free, Starter, Professional) to the shopping cart.
            
            Args:
                product_id_or_name: Name or ID of product (e.g. Nimbus CRM, nimbus-leads).
                tier_name: Tier name (e.g. Starter, Professional). Defaults to first paid tier if blank.
                seats: Number of seats/users to purchase. Defaults to 1.
            """
            nonlocal current_cart
            res = add_to_cart_impl(current_cart, product_id_or_name, tier_name, seats)
            current_cart = res["cart"]
            return json.dumps(res)
        tools_list.append(add_to_cart)
        
    if "remove_from_cart" in enabled_tools:
        def remove_from_cart(product_id_or_name: str, tier_name: str = None) -> str:
            """Remove an item or tier of a product from the shopping cart.
            
            Args:
                product_id_or_name: Name or ID of product.
                tier_name: Specific tier name.
            """
            nonlocal current_cart
            res = remove_from_cart_impl(current_cart, product_id_or_name, tier_name)
            current_cart = res["cart"]
            return json.dumps(res)
        tools_list.append(remove_from_cart)
        
    if "clear_cart" in enabled_tools:
        def clear_cart() -> str:
            """Remove all items from the shopping cart, clearing it completely."""
            nonlocal current_cart
            res = clear_cart_impl(current_cart)
            current_cart = res["cart"]
            return json.dumps(res)
        tools_list.append(clear_cart)
        
    if "view_cart" in enabled_tools:
        def view_cart() -> str:
            """Retrieve and view list of all items currently in the shopping cart."""
            res = view_cart_impl(current_cart)
            return json.dumps(res)
        tools_list.append(view_cart)
        
    if "get_cart_total" in enabled_tools:
        def get_cart_total() -> str:
            """Get the current total monthly price of all items in the shopping cart."""
            res = get_cart_total_impl(current_cart)
            return json.dumps(res)
        tools_list.append(get_cart_total)
        
    if "checkout_cart" in enabled_tools:
        def checkout_cart() -> str:
            """Perform checkout on the entire cart, finalizing purchase and clearing the cart."""
            nonlocal current_cart
            res = checkout_cart_impl(current_cart)
            current_cart = res["cart"]
            return json.dumps(res)
        tools_list.append(checkout_cart)
        
    if "checkout_single_item" in enabled_tools:
        def checkout_single_item(product_id_or_name: str, tier_name: str = None) -> str:
            """Checkout just one individual item from the cart, leaving other items behind.
            
            Args:
                product_id_or_name: Name or ID of product.
                tier_name: Specific tier name.
            """
            nonlocal current_cart
            res = checkout_single_item_impl(current_cart, product_id_or_name, tier_name)
            current_cart = res["cart"]
            return json.dumps(res)
        tools_list.append(checkout_single_item)
        
    if "calculate_annual_pricing" in enabled_tools:
        def calculate_annual_pricing(monthly_price: float) -> str:
            """Calculate the annual pricing of a product tier given its monthly rate (applies 20% discount).
            
            Args:
                monthly_price: Monthly subscription price.
            """
            res = calculate_annual_pricing_impl(monthly_price)
            return json.dumps(res)
        tools_list.append(calculate_annual_pricing)
        
    if "calculate_annual_savings" in enabled_tools:
        def calculate_annual_savings(monthly_price: float, annual_monthly_price: float = None) -> str:
            """Calculate annual savings of billing annually upfront versus billing monthly.
            
            Args:
                monthly_price: Standard monthly subscription price.
                annual_monthly_price: Annual contract monthly price. Defaults to 20% off if blank.
            """
            res = calculate_annual_savings_impl(monthly_price, annual_monthly_price)
            return json.dumps(res)
        tools_list.append(calculate_annual_savings)
        
    if "sort_products" in enabled_tools:
        def sort_products(order: str = "asc") -> str:
            """Sort and list products from the catalog in increasing or decreasing order of pricing.
            
            Args:
                order: Sort order: 'asc' (increasing) or 'desc' (decreasing).
            """
            res = sort_products_impl(order)
            return json.dumps(res)
        tools_list.append(sort_products)
        
    if "get_top_k_expensive_products" in enabled_tools:
        def get_top_k_expensive_products(k: int) -> str:
            """Get the top k most expensive products from the catalog.
            
            Args:
                k: Number of expensive products to retrieve.
            """
            res = get_top_k_expensive_products_impl(k)
            return json.dumps(res)
        tools_list.append(get_top_k_expensive_products)
        
    if "product_info" in enabled_tools:
        def product_info(product_name: str) -> str:
            """Look up a product's categories, tiers, prices, and features to ground answers.
            
            Args:
                product_name: The product name to query, e.g. Nimbus CRM, Leads, Campaigns.
            """
            res = product_info_impl(product_name)
            return json.dumps(res)
        tools_list.append(product_info)
        
    return tools_list, lambda: current_cart

# Allow CORS for client development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Configuration State (Default configurations)
config_state = {
    "openai_key": "",
    "gemini_key": "",
    "anthropic_key": "",
    "elevenlabs_key": "",
    "asr_provider": "browser",  # browser, openai, gemini, elevenlabs
    "llm_provider": "openai",   # openai, gemini, anthropic
    "tts_provider": "browser",  # browser, openai, gemini, elevenlabs
    "rag_mode": True,           # True: RAG, False: RAGless (full context.md)
    "streaming_mode": True,     # True: Streaming, False: Batch
    "system_prompt": (
        "You are Nimbus, a helpful voice agent for Nimbus Software Inc. "
        "Use tools whenever the user wants to manage their cart, see what is in their cart, list cart items, sort products, calculate pricing, or checkout. "
        "If a user asks about general company policies, answer directly based on context. "
        "Keep responses extremely short and conversational (1-2 sentences) since this is a voice interface."
    ),
    "response_length": "medium",  # low (short), medium, high (detailed)
    "top_k": 3,
    "verbatim_count": 3,
    "endpoint_duration": 800,     # ms silence detection threshold
    "selected_tools": [
        "add_to_cart", "remove_from_cart", "clear_cart", "view_cart", "get_cart_total", 
        "checkout_cart", "checkout_single_item", "calculate_annual_pricing", 
        "calculate_annual_savings", "sort_products", "get_top_k_expensive_products",
        "product_info"
    ]
}

# In-memory session stores for phone call simulation
phone_sessions = {}

# Utility: get active tools list for LLM binding
def get_available_tools_definitions():
    return [
        {
            "name": "add_to_cart",
            "description": "Add a specific product and its tier (Free, Starter, Professional) to the shopping cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id_or_name": {"type": "string", "description": "Name or ID of product (e.g. Nimbus CRM, nimbus-leads)"},
                    "tier_name": {"type": "string", "description": "Tier name (e.g. Starter, Professional). Defaults to first paid tier if blank."},
                    "seats": {"type": "integer", "description": "Number of seats/users to purchase. Defaults to 1."}
                },
                "required": ["product_id_or_name"]
            }
        },
        {
            "name": "remove_from_cart",
            "description": "Remove an item or tier of a product from the shopping cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id_or_name": {"type": "string", "description": "Product ID or Name to remove"},
                    "tier_name": {"type": "string", "description": "Specific tier (Starter, Professional). If blank, removes all matching products."}
                },
                "required": ["product_id_or_name"]
            }
        },
        {
            "name": "clear_cart",
            "description": "Remove all items from the shopping cart, clearing it completely.",
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "view_cart",
            "description": "Retrieve and view list of all items currently in the shopping cart.",
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "get_cart_total",
            "description": "Get the current total monthly price of all items in the shopping cart.",
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "checkout_cart",
            "description": "Perform checkout on the entire cart, finalizing purchase and clearing the cart.",
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "checkout_single_item",
            "description": "Checkout just one individual item from the cart, leaving other items behind.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id_or_name": {"type": "string", "description": "Name or ID of product"},
                    "tier_name": {"type": "string", "description": "Specific tier name"}
                },
                "required": ["product_id_or_name"]
            }
        },
        {
            "name": "calculate_annual_pricing",
            "description": "Calculate the annual pricing of a product tier given its monthly rate (applies 20% discount).",
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_price": {"type": "number", "description": "Monthly subscription price"}
                },
                "required": ["monthly_price"]
            }
        },
        {
            "name": "calculate_annual_savings",
            "description": "Calculate annual savings of billing annually upfront versus billing monthly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_price": {"type": "number", "description": "Standard monthly subscription price"},
                    "annual_monthly_price": {"type": "number", "description": "Annual contract monthly price. Defaults to 20% off if blank."}
                },
                "required": ["monthly_price"]
            }
        },
        {
            "name": "sort_products",
            "description": "Sort and list products from the catalog in increasing or decreasing order of pricing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order": {"type": "string", "enum": ["asc", "desc"], "description": "Sort order: asc (increasing) or desc (decreasing)"}
                }
            }
        },
        {
            "name": "get_top_k_expensive_products",
            "description": "Get the top k most expensive products from the catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "k": {"type": "integer", "description": "Number of expensive products to retrieve"}
                },
                "required": ["k"]
            }
        },
        {
            "name": "product_info",
            "description": "Look up a product's categories, tiers, prices, and features to ground answers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "The product name to query, e.g. Nimbus CRM, Leads, Campaigns"}
                },
                "required": ["product_name"]
            }
        }
    ]

# Models
class ConfigUpdate(BaseModel):
    openai_key: Optional[str] = None
    gemini_key: Optional[str] = None
    anthropic_key: Optional[str] = None
    elevenlabs_key: Optional[str] = None
    asr_provider: Optional[str] = None
    llm_provider: Optional[str] = None
    tts_provider: Optional[str] = None
    rag_mode: Optional[bool] = None
    streaming_mode: Optional[bool] = None
    system_prompt: Optional[str] = None
    response_length: Optional[str] = None
    top_k: Optional[int] = None
    verbatim_count: Optional[int] = None
    endpoint_duration: Optional[int] = None
    selected_tools: Optional[List[str]] = None

class ReasonRequest(BaseModel):
    query: str
    history: List[Dict[str, Any]]
    cart: List[Dict[str, Any]]

# Endpoints
@app.get("/api/config")
def get_config():
    # Return config with hidden keys for security, but exposing if they are set
    exposed = config_state.copy()
    for k in ["openai_key", "gemini_key", "anthropic_key", "elevenlabs_key"]:
        exposed[k] = "PRESENT" if config_state[k] else ""
    return exposed

@app.post("/api/config")
def update_config(update: ConfigUpdate):
    for k, v in update.dict(exclude_unset=True).items():
        config_state[k] = v
    
    # Reload RAG Engine to capture key changes if any
    try:
        get_rag_engine(
            openai_key=config_state["openai_key"],
            gemini_key=config_state["gemini_key"],
            force_reload=True
        )
    except Exception as e:
        print(f"RAG reload error: {e}")
        
    return {"status": "success", "message": "Configuration updated successfully."}

@app.get("/api/rag/nodes")
def get_rag_nodes(
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    openai_key = x_openai_key or config_state["openai_key"]
    gemini_key = x_gemini_key or config_state["gemini_key"]
    try:
        engine = get_rag_engine(openai_key, gemini_key)
        return {
            "success": True,
            "nodes": engine.get_all_coordinates()
        }
    except Exception as e:
        return {"success": False, "error": str(e), "nodes": []}

@app.get("/api/rag/query")
def query_rag(
    q: str, 
    k: int = 3,
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    openai_key = x_openai_key or config_state["openai_key"]
    gemini_key = x_gemini_key or config_state["gemini_key"]
    try:
        engine = get_rag_engine(openai_key, gemini_key)
        chunks, query_coord = engine.query(q, k=k)
        return {
            "success": True,
            "chunks": chunks,
            "query_coord": query_coord
        }
    except Exception as e:
        return {"success": False, "error": str(e), "chunks": [], "query_coord": [0.0, 0.0]}

# ASR REST endpoint (Whisper, Gemini, ElevenLabs)
@app.post("/api/asr")
async def process_asr(
    file: UploadFile = File(...), 
    provider: str = Form("browser"),
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_elevenlabs_key: Optional[str] = Header(None, alias="X-ElevenLabs-Key")
):
    start_time = time.perf_counter()
    content = await file.read()
    openai_key = x_openai_key or config_state["openai_key"]
    gemini_key = x_gemini_key or config_state["gemini_key"]
    elevenlabs_key = x_elevenlabs_key or config_state["elevenlabs_key"]
    
    key_avail = (
        (provider == "browser") or
        (provider == "openai" and openai_key) or
        (provider == "gemini" and gemini_key) or
        (provider == "elevenlabs" and elevenlabs_key)
    )
    
    # Provider fallback to browser or mock
    if provider == "browser" or not key_avail:
        # If no key, mock ASR output by parsing filename or return static text
        latency = (time.perf_counter() - start_time) * 1000
        return {
            "text": "How much does Nimbus CRM cost?",
            "latency_ms": latency,
            "provider": "mock"
        }
        
    if provider == "openai" and openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            # Save audio briefly with its original extension (e.g. webm)
            ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'webm'
            temp_name = f"temp_{int(time.time())}.{ext}"
            with open(temp_name, "wb") as f:
                f.write(content)
            
            with open(temp_name, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file
                )
            
            os.remove(temp_name)
            latency = (time.perf_counter() - start_time) * 1000
            return {
                "text": transcription.text,
                "latency_ms": latency,
                "provider": "openai"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    if provider == "gemini" and gemini_key:
        try:
            import base64
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            body = {
                "contents": [{"role": "user", "parts": [
                    {"text": "Transcribe this audio verbatim. Return only the transcript text."},
                    {"inline_data": {"mime_type": "audio/webm", "data": base64.b64encode(content).decode()}}
                ]}]
            }
            async with httpx.AsyncClient() as client:
                r = await client.post(url, json=body, timeout=60.0)
            if r.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Gemini ASR error: {r.text}")
            cand = (r.json().get("candidates") or [{}])[0]
            parts = cand.get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            latency = (time.perf_counter() - start_time) * 1000
            return {"text": text, "latency_ms": latency, "provider": "gemini"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    if provider == "elevenlabs" and elevenlabs_key:
        try:
            import httpx
            url = "https://api.elevenlabs.io/v1/speech-to-text"
            headers = {"xi-api-key": elevenlabs_key}
            files = {"file": (file.filename or "audio.webm", content, file.content_type or "audio/webm")}
            data = {"model_id": "scribe_v1"}
            async with httpx.AsyncClient() as client:
                r = await client.post(url, headers=headers, files=files, data=data, timeout=60.0)
            if r.status_code != 200:
                raise HTTPException(status_code=500, detail=f"ElevenLabs ASR error: {r.text}")
            text = r.json().get("text", "").strip()
            latency = (time.perf_counter() - start_time) * 1000
            return {"text": text, "latency_ms": latency, "provider": "elevenlabs"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    # Default fallback
    latency = (time.perf_counter() - start_time) * 1000
    return {
        "text": "[Mock ASR Response] Unable to transcribe.",
        "latency_ms": latency,
        "provider": "mock"
    }

# LLM Reasoning REST endpoint
@app.post("/api/reason")
async def process_reasoning(
    req: ReasonRequest,
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key")
):
    start_time = time.perf_counter()
    openai_key = x_openai_key or config_state["openai_key"]
    gemini_key = x_gemini_key or config_state["gemini_key"]
    anthropic_key = x_anthropic_key or config_state["anthropic_key"]
    
    # 1. Memory Summarization & History Setup
    verbatim_n = config_state["verbatim_count"]
    history = req.history
    
    formatted_history = []
    verbatim_history = history[-verbatim_n:] if len(history) > 0 else []
    summary_history = history[:-verbatim_n] if len(history) > verbatim_n else []
    
    # Construct summary of older messages
    if summary_history:
        summary_text = "[Summary of older conversations: "
        summary_points = []
        for msg in summary_history:
            role = "User" if msg["role"] == "user" else "Agent"
            txt = msg["content"]
            if len(txt) > 30:
                txt = txt[:30] + "..."
            summary_points.append(f"{role}: {txt}")
        summary_text += " | ".join(summary_points) + "]"
        formatted_history.append({"role": "system", "content": summary_text})
        
    for msg in verbatim_history:
        formatted_history.append({"role": msg["role"], "content": msg["content"]})

    # 2. Context Retrieval (RAG vs RAGless)
    rag_latency = 0
    context_str = ""
    retrieved_chunks = []
    query_coord = [0.0, 0.0]
    
    if config_state["rag_mode"]:
        rag_start = time.perf_counter()
        try:
            engine = get_rag_engine(openai_key, gemini_key)
            retrieved_chunks, query_coord = engine.query(req.query, k=config_state["top_k"])
            context_str = "\n\n".join([f"--- Chunk: {c['title']} ---\n{c['content']}" for c in retrieved_chunks])
        except Exception as e:
            print(f"RAG search error: {e}")
            context_str = "Error retrieving RAG context."
        rag_latency = (time.perf_counter() - rag_start) * 1000
    else:
        # RAGless: Load the entire context.md
        context_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nimbus-voice-agent-starter", "data", "context.md")
        if os.path.exists(context_path):
            with open(context_path, 'r', encoding='utf-8') as f:
                context_str = f.read()
        else:
            context_str = "Context file context.md not found."

    context_tokens = count_tokens(context_str)

    # Adjust system prompt with length constraints
    len_instruction = ""
    if config_state["response_length"] == "low":
        len_instruction = " Keep your response under 10 words."
    elif config_state["response_length"] == "medium":
        len_instruction = " Keep your response brief, under 25 words."
    elif config_state["response_length"] == "high":
        len_instruction = " You may explain in detail (under 80 words)."

    full_system_prompt = config_state["system_prompt"] + len_instruction + f"\n\n[CONTEXT TOKEN COUNT: {context_tokens}]\nCONTEXT INFORMATION:\n" + context_str

    # 3. LLM Call (OpenAI, Gemini, or Anthropic)
    llm_start = time.perf_counter()
    provider = config_state["llm_provider"]
    response_text = ""
    tool_calls_executed = []
    cart_state = req.cart
    tool_latency_total = 0
    
    # Determine enabled tools
    enabled_tools = config_state["selected_tools"]
    all_tools_defs = get_available_tools_definitions()
    active_tools_defs = [t for t in all_tools_defs if t["name"] in enabled_tools]

    # Handle Mock reasoning if no API keys
    key_avail = (
        (provider == "openai" and is_valid_key("openai", openai_key)) or
        (provider == "gemini" and is_valid_key("gemini", gemini_key)) or
        (provider == "anthropic" and is_valid_key("anthropic", anthropic_key))
    )
    
    if not key_avail:
        tool_start = time.perf_counter()
        response_text, cart_state, tool_calls_executed = generate_mock_voice_response(req.query, cart_state, enabled_tools, req.history)
        tool_latency_total = (time.perf_counter() - tool_start) * 1000
            
    else:
        # Key is available, make actual API call with Tool binding
        if provider == "openai" and openai_key:
            try:
                import openai
                client = openai.OpenAI(api_key=openai_key)
                
                # Format tools for OpenAI API
                openai_tools = []
                for t in active_tools_defs:
                    openai_tools.append({
                        "type": "function",
                        "function": t
                    })
                
                api_messages = [{"role": "system", "content": full_system_prompt}]
                api_messages.extend(formatted_history)
                api_messages.append({"role": "user", "content": req.query})
                
                # First call
                args = {
                    "model": "gpt-4o-mini",
                    "messages": api_messages,
                }
                if openai_tools:
                    args["tools"] = openai_tools
                    args["tool_choice"] = "auto"
                    
                response = client.chat.completions.create(**args)
                msg = response.choices[0].message
                
                if msg.tool_calls:
                    # Execute tool call
                    api_messages.append(msg)
                    for tool_call in msg.tool_calls:
                        func_name = tool_call.function.name
                        func_args = json.loads(tool_call.function.arguments)
                        
                        tool_start = time.perf_counter()
                        tool_res = None
                        
                        # Route tool execution
                        if func_name == "add_to_cart":
                            tool_res = add_to_cart_impl(cart_state, **func_args)
                            cart_state = tool_res["cart"]
                        elif func_name == "remove_from_cart":
                            tool_res = remove_from_cart_impl(cart_state, **func_args)
                            cart_state = tool_res["cart"]
                        elif func_name == "clear_cart":
                            tool_res = clear_cart_impl(cart_state)
                            cart_state = tool_res["cart"]
                        elif func_name == "view_cart":
                            tool_res = view_cart_impl(cart_state)
                        elif func_name == "get_cart_total":
                            tool_res = get_cart_total_impl(cart_state)
                        elif func_name == "checkout_cart":
                            tool_res = checkout_cart_impl(cart_state)
                            cart_state = tool_res["cart"]
                        elif func_name == "checkout_single_item":
                            tool_res = checkout_single_item_impl(cart_state, **func_args)
                            cart_state = tool_res["cart"]
                        elif func_name == "calculate_annual_pricing":
                            tool_res = calculate_annual_pricing_impl(**func_args)
                        elif func_name == "calculate_annual_savings":
                            tool_res = calculate_annual_savings_impl(**func_args)
                        elif func_name == "sort_products":
                            tool_res = sort_products_impl(**func_args)
                        elif func_name == "get_top_k_expensive_products":
                            tool_res = get_top_k_expensive_products_impl(**func_args)
                        elif func_name == "product_info":
                            tool_res = product_info_impl(**func_args)
                            
                        tool_lat = (time.perf_counter() - tool_start) * 1000
                        tool_latency_total += tool_lat
                        tool_calls_executed.append({
                            "name": func_name,
                            "args": func_args,
                            "result": tool_res,
                            "latency_ms": tool_lat
                        })
                        
                        # Add tool response back to thread
                        api_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": json.dumps(tool_res)
                        })
                        
                    # Call LLM again with tool results
                    second_response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=api_messages
                    )
                    response_text = second_response.choices[0].message.content
                else:
                    response_text = msg.content
                    
            except Exception as e:
                response_text = f"Error in OpenAI Reasoning: {str(e)}"
                
        elif provider == "gemini" and gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                
                # Build Gemini native tools list
                gemini_tools, get_updated_cart = get_gemini_tools_and_runner(cart_state, enabled_tools)
                
                model = genai.GenerativeModel(
                    model_name='gemini-2.5-flash',
                    tools=gemini_tools if gemini_tools else None,
                    system_instruction=full_system_prompt
                )
                
                # Format history for Gemini chat
                gemini_history = []
                for msg in formatted_history:
                    role = "user" if msg["role"] == "user" else "model"
                    gemini_history.append({"role": role, "parts": [msg["content"]]})
                
                # Start chat with automatic function calling enabled
                chat = model.start_chat(history=gemini_history, enable_automatic_function_calling=True)
                response = chat.send_message(req.query, request_options={"timeout": 10.0})
                response_text = response.text
                cart_state = get_updated_cart()
                
                # Extract any executed tools from the chat history
                for message in chat.history:
                    for part in message.parts:
                        if part.function_call:
                            func_name = part.function_call.name
                            func_args = dict(part.function_call.args)
                            tool_calls_executed.append({
                                "name": func_name,
                                "args": func_args,
                                "result": {"success": True, "message": f"Executed tool: {func_name}"}
                            })
            except Exception as e:
                print(f"Gemini API error: {e}. Falling back to mock matcher.")
                response_text, cart_state, tool_calls_executed = generate_mock_voice_response(req.query, cart_state, enabled_tools, req.history)
                
        elif provider == "anthropic" and anthropic_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_key)
                
                anth_messages = []
                for msg in formatted_history:
                    # Anthropic does not support 'system' role in message list
                    if msg["role"] == "system":
                        continue
                    anth_messages.append({"role": msg["role"], "content": msg["content"]})
                anth_messages.append({"role": "user", "content": req.query})
                
                message = client.messages.create(
                    model="claude-3-5-haiku-latest",
                    max_tokens=300,
                    system=full_system_prompt,
                    messages=anth_messages
                )
                response_text = message.content[0].text
            except Exception as e:
                response_text = f"Error in Anthropic Reasoning: {str(e)}"

    llm_latency = (time.perf_counter() - llm_start) * 1000
    total_latency = (time.perf_counter() - start_time) * 1000
    
    return {
        "text": response_text,
        "cart": cart_state,
        "tool_calls": tool_calls_executed,
        "latency": {
            "rag_ms": rag_latency,
            "llm_ms": llm_latency,
            "tool_ms": tool_latency_total,
            "total_ms": total_latency
        },
        "chunks": retrieved_chunks,
        "query_coord": query_coord,
        "context_tokens": context_tokens,
        "rag_mode": config_state["rag_mode"],
        "context_str": context_str
    }

# TTS REST Endpoint
@app.post("/api/tts")
async def process_tts(
    text: str = Form(...), 
    provider: str = Form("browser"),
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_elevenlabs_key: Optional[str] = Header(None, alias="X-ElevenLabs-Key")
):
    start_time = time.perf_counter()
    text = clean_text_for_tts(text)
    openai_key = x_openai_key or config_state["openai_key"]
    gemini_key = x_gemini_key or config_state["gemini_key"]
    elevenlabs_key = x_elevenlabs_key or config_state["elevenlabs_key"]
    
    key_avail = (
        (provider == "browser") or
        (provider == "openai" and openai_key) or
        (provider == "gemini" and gemini_key) or
        (provider == "elevenlabs" and elevenlabs_key)
    )
    
    # If using browser TTS, do not generate audio on server
    if provider == "browser" or not key_avail:
        # Simulate network buffer/processing latency
        await asyncio.sleep(0.1)
        latency = (time.perf_counter() - start_time) * 1000
        return {
            "use_browser_speech": True,
            "text": text,
            "latency_ms": latency,
            "buffer_latency_ms": 50.0
        }
        
    if provider == "openai" and openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text
            )
            # Read all audio
            audio_data = response.content
            latency = (time.perf_counter() - start_time) * 1000
            
            # Simple simulation of buffer latency (representing audio player network buffering time)
            buffer_lat = 120.0 # ms
            
            # We can encode it to base64 to send it as JSON
            import base64
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")
            
            return {
                "use_browser_speech": False,
                "audio": audio_b64,
                "latency_ms": latency,
                "buffer_latency_ms": buffer_lat
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    if provider == "gemini" and gemini_key:
        try:
            import base64
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            body = {
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Zephyr"}}},
                },
            }
            async with httpx.AsyncClient() as client:
                r = await client.post(url, json=body, timeout=60.0)
            if r.status_code != 200:
                raise RuntimeError(f"Gemini TTS error: {r.text}")
            part = r.json()["candidates"][0]["content"]["parts"][0]
            pcm_data = base64.b64decode(part["inlineData"]["data"])
            audio_data = pcm_to_wav(pcm_data, sample_rate=24000)
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")
            latency = (time.perf_counter() - start_time) * 1000
            return {
                "use_browser_speech": False,
                "audio": audio_b64,
                "latency_ms": latency,
                "buffer_latency_ms": 100.0
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    if provider == "elevenlabs" and elevenlabs_key:
        try:
            import base64
            import httpx
            url = "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL"
            headers = {"xi-api-key": elevenlabs_key, "Content-Type": "application/json", "accept": "audio/mpeg"}
            body = {"text": text, "model_id": "eleven_turbo_v2_5"}
            async with httpx.AsyncClient() as client:
                r = await client.post(url, headers=headers, json=body, timeout=60.0)
            if r.status_code != 200:
                raise RuntimeError(f"ElevenLabs TTS error: {r.text}")
            audio_data = r.content
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")
            latency = (time.perf_counter() - start_time) * 1000
            return {
                "use_browser_speech": False,
                "audio": audio_b64,
                "latency_ms": latency,
                "buffer_latency_ms": 150.0
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    # Default fallback
    latency = (time.perf_counter() - start_time) * 1000
    return {
        "use_browser_speech": True,
        "text": text,
        "latency_ms": latency,
        "buffer_latency_ms": 50.0
    }

# WebSockets Endpoint for full interactive real-time loop
@app.websocket("/api/voice-loop")
async def websocket_endpoint(
    websocket: WebSocket,
    openai_key: Optional[str] = None,
    gemini_key: Optional[str] = None,
    elevenlabs_key: Optional[str] = None
):
    await websocket.accept()
    logger.info("WebSocket voice loop connection accepted.")
    
    ws_openai_key = openai_key or config_state["openai_key"]
    ws_gemini_key = gemini_key or config_state["gemini_key"]
    ws_elevenlabs_key = elevenlabs_key or config_state["elevenlabs_key"]
    
    # Active TTS stream reference to handle barge-in interruptions
    tts_playing_task = None
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            action = message.get("action")
            
            if action == "interrupt":
                print("Barge-in: Interrupt received. Stopping playback.")
                if tts_playing_task and not tts_playing_task.done():
                    tts_playing_task.cancel()
                await websocket.send_json({"event": "interrupted", "message": "cancelled by the user"})
                continue
                
            if action == "query":
                query_text = message.get("text", "")
                history = message.get("history", [])
                cart = message.get("cart", [])
                
                print(f"Voice loop query received: {query_text}")
                
                # Execute reasoning flow
                reason_start = time.perf_counter()
                
                # Fetch RAG context if enabled
                rag_latency = 0
                context_str = ""
                retrieved_chunks = []
                query_coord = [0.0, 0.0]
                
                if config_state["rag_mode"]:
                    rag_start = time.perf_counter()
                    try:
                        engine = get_rag_engine(ws_openai_key, ws_gemini_key)
                        retrieved_chunks, query_coord = engine.query(query_text, k=config_state["top_k"])
                        context_str = "\n\n".join([f"--- Chunk: {c['title']} ---\n{c['content']}" for c in retrieved_chunks])
                    except Exception as e:
                        print(f"RAG error: {e}")
                    rag_latency = (time.perf_counter() - rag_start) * 1000
                else:
                    context_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nimbus-voice-agent-starter", "data", "context.md")
                    if os.path.exists(context_path):
                        with open(context_path, 'r', encoding='utf-8') as f:
                            context_str = f.read()
                            
                context_tokens = count_tokens(context_str)

                len_instruction = ""
                if config_state["response_length"] == "low":
                    len_instruction = " Keep response under 10 words."
                elif config_state["response_length"] == "medium":
                    len_instruction = " Keep response under 25 words."
                elif config_state["response_length"] == "high":
                    len_instruction = " Keep response under 80 words."
                    
                full_system = config_state["system_prompt"] + len_instruction + f"\n\n[CONTEXT TOKEN COUNT: {context_tokens}]\nCONTEXT:\n" + context_str
                
                # Execute reasoning & tools
                llm_start = time.perf_counter()
                response_text = ""
                cart_state = cart
                tool_calls_executed = []
                tool_latency_total = 0
                
                # Check for mock
                provider = config_state["llm_provider"]
                key_avail = (
                    (provider == "openai" and is_valid_key("openai", ws_openai_key)) or
                    (provider == "gemini" and is_valid_key("gemini", ws_gemini_key)) or
                    (provider == "anthropic" and is_valid_key("anthropic", config_state["anthropic_key"]))
                )
                
                if not key_avail:
                    tool_start = time.perf_counter()
                    response_text, cart_state, tool_calls_executed = generate_mock_voice_response(query_text, cart_state, config_state["selected_tools"], history)
                    tool_latency_total = (time.perf_counter() - tool_start) * 1000
                else:
                    # Actual API calls
                    if provider == "openai" and ws_openai_key:
                        try:
                            import openai
                            client = openai.OpenAI(api_key=ws_openai_key)
                            
                            openai_tools = []
                            for t_name in config_state["selected_tools"]:
                                for t_def in get_available_tools_definitions():
                                    if t_def["name"] == t_name:
                                        openai_tools.append({"type": "function", "function": t_def})
                                        
                            api_messages = [{"role": "system", "content": full_system}]
                            # Truncate history based on verbatim
                            verb_count = config_state["verbatim_count"]
                            verb_hist = history[-verb_count:] if history else []
                            for h in verb_hist:
                                api_messages.append({"role": h["role"], "content": h["content"]})
                            api_messages.append({"role": "user", "content": query_text})
                            
                            args = {"model": "gpt-4o-mini", "messages": api_messages}
                            if openai_tools:
                                args["tools"] = openai_tools
                                
                            res = client.chat.completions.create(**args)
                            msg = res.choices[0].message
                            
                            if msg.tool_calls:
                                api_messages.append(msg)
                                for tc in msg.tool_calls:
                                    f_name = tc.function.name
                                    f_args = json.loads(tc.function.arguments)
                                    
                                    t_start = time.perf_counter()
                                    t_res = None
                                    if f_name == "add_to_cart":
                                        t_res = add_to_cart_impl(cart_state, **f_args)
                                        cart_state = t_res["cart"]
                                    elif f_name == "remove_from_cart":
                                        t_res = remove_from_cart_impl(cart_state, **f_args)
                                        cart_state = t_res["cart"]
                                    elif f_name == "clear_cart":
                                        t_res = clear_cart_impl(cart_state)
                                        cart_state = t_res["cart"]
                                    elif f_name == "view_cart":
                                        t_res = view_cart_impl(cart_state)
                                    elif f_name == "get_cart_total":
                                        t_res = get_cart_total_impl(cart_state)
                                    elif f_name == "checkout_cart":
                                        t_res = checkout_cart_impl(cart_state)
                                        cart_state = t_res["cart"]
                                    elif f_name == "checkout_single_item":
                                        t_res = checkout_single_item_impl(cart_state, **f_args)
                                        cart_state = t_res["cart"]
                                    elif f_name == "calculate_annual_pricing":
                                        t_res = calculate_annual_pricing_impl(**f_args)
                                    elif f_name == "calculate_annual_savings":
                                        t_res = calculate_annual_savings_impl(**f_args)
                                    elif f_name == "sort_products":
                                        t_res = sort_products_impl(**f_args)
                                    elif f_name == "get_top_k_expensive_products":
                                        t_res = get_top_k_expensive_products_impl(**f_args)
                                    elif f_name == "product_info":
                                        t_res = product_info_impl(**f_args)
                                        
                                    t_lat = (time.perf_counter() - t_start) * 1000
                                    tool_latency_total += t_lat
                                    tool_calls_executed.append({"name": f_name, "args": f_args, "result": t_res, "latency_ms": t_lat})
                                    
                                    api_messages.append({
                                        "role": "tool",
                                        "tool_call_id": tc.id,
                                        "name": f_name,
                                        "content": json.dumps(t_res)
                                    })
                                    
                                second_res = client.chat.completions.create(model="gpt-4o-mini", messages=api_messages)
                                response_text = second_res.choices[0].message.content
                            else:
                                response_text = msg.content
                        except Exception as e:
                            response_text = f"Error: {e}"
                            
                    elif provider == "gemini" and ws_gemini_key:
                        try:
                            import google.generativeai as genai
                            genai.configure(api_key=ws_gemini_key)
                            
                            gemini_tools, get_updated_cart = get_gemini_tools_and_runner(cart_state, config_state["selected_tools"])
                            
                            model = genai.GenerativeModel(
                                model_name='gemini-2.5-flash',
                                tools=gemini_tools if gemini_tools else None,
                                system_instruction=full_system
                            )
                            
                            gemini_history = []
                            verb_count = config_state["verbatim_count"]
                            verb_hist = history[-verb_count:] if history else []
                            for h in verb_hist:
                                role = "user" if h["role"] == "user" else "model"
                                gemini_history.append({"role": role, "parts": [h["content"]]})
                                
                            chat = model.start_chat(history=gemini_history, enable_automatic_function_calling=True)
                            response = chat.send_message(query_text, request_options={"timeout": 10.0})
                            response_text = response.text
                            cart_state = get_updated_cart()
                            
                            for message in chat.history:
                                for part in message.parts:
                                    if part.function_call:
                                        func_name = part.function_call.name
                                        func_args = dict(part.function_call.args)
                                        tool_calls_executed.append({
                                            "name": func_name,
                                            "args": func_args,
                                            "result": {"success": True, "message": f"Executed tool: {func_name}"}
                                        })
                        except Exception as e:
                            print(f"Gemini WS API error: {e}. Falling back to mock matcher.")
                            response_text, cart_state, tool_calls_executed = generate_mock_voice_response(query_text, cart_state, config_state["selected_tools"], history)
                            
                    elif provider == "anthropic" and config_state["anthropic_key"]:
                        try:
                            import anthropic
                            client = anthropic.Anthropic(api_key=config_state["anthropic_key"])
                            
                            anth_messages = []
                            verb_count = config_state["verbatim_count"]
                            verb_hist = history[-verb_count:] if history else []
                            for h in verb_hist:
                                if h["role"] == "system":
                                    continue
                                anth_messages.append({"role": h["role"], "content": h["content"]})
                            anth_messages.append({"role": "user", "content": query_text})
                            
                            message = client.messages.create(
                                model="claude-3-5-haiku-latest",
                                max_tokens=300,
                                system=full_system,
                                messages=anth_messages
                            )
                            response_text = message.content[0].text
                        except Exception as e:
                            response_text = f"Error: {e}"
                            
                llm_latency = (time.perf_counter() - llm_start) * 1000
                total_reasoning_latency = (time.perf_counter() - reason_start) * 1000
                
                # Return reasoning event back
                await websocket.send_json({
                    "event": "reason_done",
                    "text": response_text,
                    "cart": cart_state,
                    "tool_calls": tool_calls_executed,
                    "chunks": retrieved_chunks,
                    "query_coord": query_coord,
                    "context_tokens": context_tokens,
                    "rag_mode": config_state["rag_mode"],
                    "context_str": context_str,
                    "latency": {
                        "rag_ms": rag_latency,
                        "llm_ms": llm_latency,
                        "tool_ms": tool_latency_total,
                        "total_ms": total_reasoning_latency
                    }
                })
                
                # Now generate and send TTS
                tts_start = time.perf_counter()
                tts_text = clean_text_for_tts(response_text)
                tts_provider = config_state["tts_provider"]
                
                ws_key_avail = (
                    (tts_provider == "browser") or
                    (tts_provider == "openai" and ws_openai_key) or
                    (tts_provider == "gemini" and ws_gemini_key) or
                    (tts_provider == "elevenlabs" and ws_elevenlabs_key)
                )
                
                if tts_provider == "browser" or not ws_key_avail:
                    # Browser-based speech synthesis, tell client to speak
                    await websocket.send_json({
                        "event": "tts_done",
                        "use_browser_speech": True,
                        "text": tts_text,
                        "latency_ms": (time.perf_counter() - tts_start) * 1000,
                        "buffer_latency_ms": 40.0
                    })
                elif tts_provider == "openai" and ws_openai_key:
                    # Stream voice chunks (or send full base64 file)
                    try:
                        import openai
                        client = openai.OpenAI(api_key=ws_openai_key)
                        response = client.audio.speech.create(
                            model="tts-1",
                            voice="alloy",
                            input=tts_text
                        )
                        audio_data = response.content
                        import base64
                        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                        
                        await websocket.send_json({
                            "event": "tts_done",
                            "use_browser_speech": False,
                            "audio": audio_b64,
                            "latency_ms": (time.perf_counter() - tts_start) * 1000,
                            "buffer_latency_ms": 110.0
                        })
                    except Exception as e:
                        print(f"TTS error: {e}")
                        await websocket.send_json({
                            "event": "tts_done",
                            "use_browser_speech": True,
                            "text": tts_text,
                            "latency_ms": 0,
                            "buffer_latency_ms": 0
                        })
                elif tts_provider == "gemini" and ws_gemini_key:
                    try:
                        import base64
                        import httpx
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={ws_gemini_key}"
                        body = {
                            "contents": [{"parts": [{"text": tts_text}]}],
                            "generationConfig": {
                                "responseModalities": ["AUDIO"],
                                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Zephyr"}}},
                            },
                        }
                        async with httpx.AsyncClient() as client:
                            r = await client.post(url, json=body, timeout=60.0)
                        if r.status_code != 200:
                            raise RuntimeError(f"Gemini TTS error: {r.text}")
                        part = r.json()["candidates"][0]["content"]["parts"][0]
                        pcm_data = base64.b64decode(part["inlineData"]["data"])
                        audio_data = pcm_to_wav(pcm_data, sample_rate=24000)
                        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                        
                        await websocket.send_json({
                            "event": "tts_done",
                            "use_browser_speech": False,
                            "audio": audio_b64,
                            "latency_ms": (time.perf_counter() - tts_start) * 1000,
                            "buffer_latency_ms": 100.0
                        })
                    except Exception as e:
                        print(f"Gemini TTS error: {e}")
                        await websocket.send_json({
                            "event": "tts_done",
                            "use_browser_speech": True,
                            "text": tts_text,
                            "latency_ms": 0,
                            "buffer_latency_ms": 0
                        })
                elif tts_provider == "elevenlabs" and ws_elevenlabs_key:
                    try:
                        import base64
                        import httpx
                        url = "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL"
                        headers = {"xi-api-key": ws_elevenlabs_key, "Content-Type": "application/json", "accept": "audio/mpeg"}
                        body = {"text": tts_text, "model_id": "eleven_turbo_v2_5"}
                        async with httpx.AsyncClient() as client:
                            r = await client.post(url, headers=headers, json=body, timeout=60.0)
                        if r.status_code != 200:
                            raise RuntimeError(f"ElevenLabs TTS error: {r.text}")
                        audio_data = r.content
                        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                        
                        await websocket.send_json({
                            "event": "tts_done",
                            "use_browser_speech": False,
                            "audio": audio_b64,
                            "latency_ms": (time.perf_counter() - tts_start) * 1000,
                            "buffer_latency_ms": 150.0
                        })
                    except Exception as e:
                        print(f"ElevenLabs TTS error: {e}")
                        await websocket.send_json({
                            "event": "tts_done",
                            "use_browser_speech": True,
                            "text": tts_text,
                            "latency_ms": 0,
                            "buffer_latency_ms": 0
                        })

    except WebSocketDisconnect:
        logger.info("WebSocket voice loop disconnected.")
    except Exception as e:
        logger.exception("WebSocket error: %s", e)

def _phone_public_host(request: Request) -> str:
    env_host = os.environ.get("PUBLIC_HOST") or os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if env_host:
        return env_host.replace("https://", "").replace("http://", "").strip("/")

    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "minimal-voice-loop2-2.onrender.com"
    if "localhost" in host or "127.0.0.1" in host:
        host = "minimal-voice-loop2-2.onrender.com"
    return host


def _vobiz_stream_twiml(host: str) -> str:
    stream_url = f"wss://{host}/api/phone/vobiz-stream"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true" audioTrack="inbound"
            contentType="audio/x-mulaw;rate=8000" streamTimeout="3600">
        {stream_url}
    </Stream>
</Response>
"""

@app.get("/api/phone/test-tts")
async def test_tts_endpoint():
    """Diagnostic endpoint to test if TTS works on this deployment."""
    import base64
    results = {}

    # Check which keys are available
    gemini_key = config_state.get("gemini_key") or os.environ.get("Gemini_API_Key") or os.environ.get("GEMINI_API_KEY")
    openai_key = config_state.get("openai_key") or os.environ.get("OpenAI_API_Key") or os.environ.get("OPENAI_API_KEY")
    results["gemini_key_present"] = bool(gemini_key)
    results["gemini_key_prefix"] = gemini_key[:12] + "..." if gemini_key else None
    results["openai_key_present"] = bool(openai_key)
    results["env_vars"] = {k: v[:8] + "..." for k, v in os.environ.items() if "KEY" in k.upper() or "API" in k.upper() or "GEMINI" in k.upper()}

    # Try TTS
    try:
        audio = await _phone_tts_pcm("Hello, this is a test.", VOBIZ_STREAM_SAMPLE_RATE)
        results["tts_success"] = bool(audio and len(audio) > 100)
        results["tts_audio_bytes"] = len(audio) if audio else 0
    except Exception as e:
        results["tts_success"] = False
        results["tts_error"] = str(e)

    return results

@app.api_route("/api/phone/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    from fastapi import Response

    host = _phone_public_host(request)
    logger.info("Vobiz incoming call -> bidirectional stream at wss://%s/api/phone/vobiz-stream", host)
    body = _vobiz_stream_twiml(host)
    logger.info("Returning Vobiz TwiML for host=%s", host)
    logger.info("TwiML body: %s", body)
    return Response(
        content=body,
        media_type="application/xml",
        headers={"ngrok-skip-browser-warning": "true"},
    )

def _select_phone_transcription_backend() -> str | None:
    gemini_key = config_state.get("gemini_key") or os.environ.get("Gemini_API_Key") or os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return "gemini"
    openai_key = config_state.get("openai_key") or os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return "openai"
    return None


async def _gemini_transcribe_phone_audio(audio: bytes, sample_rate: int) -> str:
    import base64
    import httpx
    from io import BytesIO
    from openai import OpenAI

    if not audio:
        return ""

    if sample_rate != 16000:
        audio_resampled = resample_pcm(audio, sample_rate, 16000)
        wav_audio = pcm_to_wav(audio_resampled, sample_rate=16000)
    else:
        wav_audio = pcm_to_wav(audio, sample_rate=sample_rate)

    backend = _select_phone_transcription_backend()

    if backend == "gemini":
        key = config_state.get("gemini_key") or os.environ.get("Gemini_API_Key") or os.environ.get("GEMINI_API_KEY")
        if key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
            body = {
                "contents": [{"parts": [
                    {"text": "Transcribe the spoken speech from this phone call audio accurately into text. Output only the transcript text."},
                    {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav_audio).decode()}}
                ]}]
            }

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=body, timeout=30.0)
                if response.status_code == 200:
                    candidates = response.json().get("candidates") or [{}]
                    parts = candidates[0].get("content", {}).get("parts", [])
                    transcript = "".join(part.get("text", "") for part in parts).strip()
                    if transcript:
                        return transcript
                else:
                    logger.error("Vobiz stream Gemini ASR error: %s %s", response.status_code, response.text[:200])
            except Exception as exc:
                logger.exception("Vobiz stream Gemini ASR exception: %s", exc)

    # Fallback to OpenAI Whisper if Gemini fails or is not selected
    openai_key = config_state.get("openai_key") or os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            with BytesIO(wav_audio) as audio_file:
                result = await asyncio.to_thread(
                    client.audio.transcriptions.create,
                    model="whisper-1",
                    file=("phone-call.wav", audio_file, "audio/wav"),
                )
            transcript = getattr(result, "text", "") or ""
            if transcript.strip():
                return transcript.strip()
        except Exception as exc:
            logger.exception("Vobiz stream OpenAI ASR fallback error: %s", exc)

    return ""

async def _phone_tts_pcm(text: str, target_sample_rate: int = VOBIZ_STREAM_SAMPLE_RATE) -> bytes:
    """Generate phone-compatible PCM audio using available TTS service."""
    cleaned = clean_text_for_tts(text)
    if not cleaned:
        return b""

    # 1. Try Gemini native TTS first (configured with Gemini_API_Key)
    gemini_key = config_state.get("gemini_key") or os.environ.get("Gemini_API_Key") or os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            import base64
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={gemini_key}"
            body = {
                "contents": [{"parts": [{"text": f"Read the following text aloud exactly: {cleaned}"}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Zephyr"}}},
                },
            }
            async with httpx.AsyncClient() as client:
                r = await client.post(url, json=body, timeout=30.0)
            if r.status_code == 200:
                part = r.json()["candidates"][0]["content"]["parts"][0]
                inline_obj = part.get("inlineData") or part.get("inline_data") or {}
                raw_b64 = inline_obj.get("data", "")
                if raw_b64:
                    pcm_data = base64.b64decode(raw_b64)
                    logger.info("Gemini TTS generated %d bytes of PCM audio", len(pcm_data))
                    return resample_pcm(pcm_data, 24000, target_sample_rate)
            else:
                logger.warning("Gemini TTS failed (%s): %s", r.status_code, r.text[:300])
        except Exception as e:
            logger.warning("Gemini TTS failed: %s", e)

    # 2. Try OpenAI TTS next
    openai_key = config_state.get("openai_key") or os.environ.get("OpenAI_API_Key") or os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            def _call_openai_tts():
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                response = client.audio.speech.create(
                    model="tts-1",
                    voice="alloy",
                    input=cleaned,
                    response_format="pcm"
                )
                return response.content

            audio_bytes = await asyncio.to_thread(_call_openai_tts)
            if audio_bytes:
                logger.info("OpenAI TTS generated %d bytes of PCM audio", len(audio_bytes))
                return resample_pcm(audio_bytes, 24000, target_sample_rate)
        except Exception as e:
            logger.warning("OpenAI TTS failed: %s", e)

    # 3. Try ElevenLabs TTS as fallback
    elevenlabs_key = config_state.get("elevenlabs_key") or os.environ.get("ElevenLabs_API_Key") or os.environ.get("ELEVENLABS_API_KEY")
    if elevenlabs_key:
        try:
            import httpx
            url = "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL"
            headers = {"xi-api-key": elevenlabs_key, "Content-Type": "application/json", "accept": "audio/mp3"}
            body = {"text": cleaned, "model_id": "eleven_monolingual_v1"}
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=body, headers=headers, timeout=10.0)
            if response.status_code == 200:
                logger.info("ElevenLabs TTS generated %d bytes (MP3)", len(response.content))
                return response.content
            else:
                logger.warning("ElevenLabs TTS error: %s", response.text[:200])
        except Exception as e:
            logger.warning("ElevenLabs TTS failed: %s", e)

    # 4. Fallback: Generate an audible audio notification tone so caller hears audio response
    logger.warning("No external TTS service available, generating audible notification tone")
    import struct
    import math
    duration_sec = 1.0
    num_samples = int(target_sample_rate * duration_sec)
    samples = []
    freq1, freq2 = 440.0, 880.0
    for i in range(num_samples):
        t = i / target_sample_rate
        freq = freq1 if t < 0.5 else freq2
        val = int(10000 * math.sin(2 * math.pi * freq * t))
        samples.append(val)
    return struct.pack("<" + "h" * num_samples, *samples)

def pcm16_to_mulaw(audio: bytes) -> bytes:
    """Convert 16-bit PCM Little-Endian audio to 8-bit G.711 mu-law for PSTN mobile phone calls."""
    try:
        import audioop
        return audioop.lin2ulaw(audio, 2)
    except Exception:
        import struct
        MULAW_BIAS = 0x84
        MULAW_CLIP = 32635
        out = bytearray()
        usable = audio[: len(audio) - len(audio) % 2]
        for i in range(0, len(usable), 2):
            sample = struct.unpack("<h", usable[i:i + 2])[0]
            sign = 0x80 if sample < 0 else 0x00
            if sample < 0:
                sample = -sample
            if sample > MULAW_CLIP:
                sample = MULAW_CLIP
            sample += MULAW_BIAS
            exponent = 7
            for exp in (7, 6, 5, 4, 3, 2, 1, 0):
                if sample & (1 << (exp + 7)):
                    exponent = exp
                    break
            mantissa = (sample >> (exponent + 3)) & 0x0F
            ulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
            out.append(ulaw_byte)
        return bytes(out)

def pcm16_to_alaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit PCM Little-Endian audio to 8-bit G.711 a-law (PCMA) for Indian PSTN mobile calls."""
    try:
        import audioop
        return audioop.lin2alaw(pcm_bytes, 2)
    except Exception:
        import struct
        out = bytearray()
        usable = pcm_bytes[: len(pcm_bytes) - len(pcm_bytes) % 2]
        for i in range(0, len(usable), 2):
            pcm_val = struct.unpack("<h", usable[i:i + 2])[0]
            sign = 0x80 if pcm_val < 0 else 0x00
            if pcm_val < 0:
                pcm_val = -pcm_val
            if pcm_val > 32767:
                pcm_val = 32767
            if pcm_val >= 256:
                exponent = 7
                for exp in range(7, 0, -1):
                    if pcm_val & (1 << (exp + 7)):
                        exponent = exp
                        break
                mantissa = (pcm_val >> (exponent + 3)) & 0x0F
                alaw_byte = (sign | (exponent << 4) | mantissa) ^ 0x55
            else:
                mantissa = (pcm_val >> 4) & 0x0F
                alaw_byte = (sign | mantissa) ^ 0x55
            out.append(alaw_byte)
        return bytes(out)

async def _send_vobiz_audio(websocket: WebSocket, stream_id: str, audio: bytes, sample_rate: int):
    import base64
    import struct

    if not audio:
        return
    if not stream_id:
        stream_id = "vobiz-stream"

    # 1. Convert Little-Endian PCM16 to G.711 A-law (PCMA) for Indian mobile phone carriers
    alaw_pcm = pcm16_to_alaw(audio)

    # 2. Convert Little-Endian PCM16 to G.711 mu-law (PCMU)
    mulaw_pcm = pcm16_to_mulaw(audio)

    chunk_duration_ms = 500
    chunk_size = sample_rate * 1 * chunk_duration_ms // 1000  # 1 byte per sample for 8kHz A-law / mu-law
    total_chunks = 0

    for offset in range(0, max(len(alaw_pcm), len(mulaw_pcm)), chunk_size):
        # Send G.711 A-law (PCMA) chunk (Primary codec for Indian mobile carriers)
        alaw_chunk = alaw_pcm[offset:offset + chunk_size]
        if alaw_chunk:
            payload_alaw_b64 = base64.b64encode(bytes(alaw_chunk)).decode("utf-8")
            await websocket.send_json({
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-alaw",
                    "sampleRate": sample_rate,
                    "payload": payload_alaw_b64
                }
            })

        # Send G.711 mu-law (PCMU) chunk
        mulaw_chunk = mulaw_pcm[offset:offset + chunk_size]
        if mulaw_chunk:
            payload_mulaw_b64 = base64.b64encode(bytes(mulaw_chunk)).decode("utf-8")
            await websocket.send_json({
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-mulaw",
                    "sampleRate": sample_rate,
                    "payload": payload_mulaw_b64
                }
            })

        total_chunks += 1
        await asyncio.sleep(0.05)

    logger.info("Sent %d playAudio chunks (A-law %d bytes, mu-law %d bytes) to stream %s", total_chunks, len(alaw_pcm), len(mulaw_pcm), stream_id)

    await websocket.send_json({
        "event": "checkpoint",
        "streamId": stream_id,
        "name": f"response-{int(time.time() * 1000)}"
    })

def _extract_vobiz_media_payload(message: Any, encoding: str) -> tuple[bytes, str]:
    """Extract audio bytes from either JSON Vobiz events or raw binary frames."""
    import base64

    if isinstance(message, (bytes, bytearray)):
        return bytes(message), "inbound"

    if isinstance(message, str):
        try:
            payload = json.loads(message)
        except Exception:
            return b"", "inbound"
        message = payload

    if isinstance(message, dict):
        media = message.get("media") or {}
        if isinstance(media, dict):
            payload = media.get("payload") or media.get("data") or ""
            track = media.get("track") or "inbound"
            if isinstance(payload, str):
                try:
                    return base64.b64decode(payload), track
                except Exception:
                    return payload.encode("utf-8"), track
            if isinstance(payload, (bytes, bytearray)):
                return bytes(payload), track
        event = message.get("event")
        if event == "media":
            payload = message.get("data") or message.get("payload") or ""
            track = message.get("track") or "inbound"
            if isinstance(payload, str):
                try:
                    return base64.b64decode(payload), track
                except Exception:
                    return payload.encode("utf-8"), track
            if isinstance(payload, (bytes, bytearray)):
                return bytes(payload), track
    return b"", "inbound"


def _normalize_vobiz_audio(frame: bytes, encoding: str) -> bytes:
    """Convert Vobiz telephony frames to little-endian PCM16 for ASR."""
    import struct

    encoding = (encoding or "").lower()
    if "mulaw" in encoding or "pcmu" in encoding:
        decoded = bytearray()
        for value in frame:
            value = ~value & 0xFF
            sign = value & 0x80
            exponent = (value >> 4) & 0x07
            mantissa = value & 0x0F
            sample = ((mantissa << 3) + 132) << exponent
            sample -= 132
            decoded.extend(struct.pack("<h", -sample if sign else sample))
        return bytes(decoded)


    if "pcma" in encoding or "alaw" in encoding:
        decoded = bytearray()
        for value in frame:
            value ^= 0x55
            sign = value & 0x80
            exponent = (value >> 4) & 0x07
            mantissa = value & 0x0F
            sample = (mantissa << 4) + 8
            if exponent:
                sample = (sample + 256) << (exponent - 1)
            decoded.extend(struct.pack("<h", -sample if sign else sample))
        return bytes(decoded)

    if "l16" in encoding or "pcm" in encoding:
        usable = frame[: len(frame) - len(frame) % 2]
        if not usable:
            return b""
        # Telephony RFC 3551 L16 / audio/x-l16 is Network Byte Order (Big-Endian).
        # We convert it to Little-Endian 16-bit PCM for standard ASR engines.
        converted = bytearray()
        for i in range(0, len(usable), 2):
            val = struct.unpack(">h", usable[i:i + 2])[0]
            converted.extend(struct.pack("<h", val))
        return bytes(converted)

    return frame

@app.websocket("/api/phone/vobiz-stream")
async def vobiz_stream(websocket: WebSocket):
    """Process Vobiz bidirectional media streams for real phone conversations."""
    import base64
    import math
    import json
    import collections

    await websocket.accept()
    logger.info("Vobiz websocket accepted")
    stream_id = None
    call_id = None
    sample_rate = VOBIZ_STREAM_SAMPLE_RATE
    audio_buffer = bytearray()
    pre_roll_buffer = collections.deque(maxlen=25)

    speech_started = False
    silence_ms = 0
    utterance_ms = 0
    processing_task = None
    greeting_task = None
    agent_speaking = False
    session = None
    media_encoding = "audio/x-l16"
    media_frames = 0

    def _generate_connection_tone(rate: int, duration_ms: int = 500) -> bytes:
        """Generate a short pleasant connection tone (immediate feedback for caller)."""
        import struct as _struct
        import math as _math
        num_samples = rate * duration_ms // 1000
        # Two-tone chime: 523Hz (C5) then 659Hz (E5) — pleasant "connected" sound
        samples = []
        half = num_samples // 2
        for i in range(num_samples):
            t = i / rate
            freq = 523.0 if i < half else 659.0
            # Fade in/out to avoid clicks
            env = min(i / (rate * 0.01), 1.0) * min((num_samples - i) / (rate * 0.01), 1.0)
            val = int(6000 * env * _math.sin(2 * _math.pi * freq * t))
            samples.append(max(-32768, min(32767, val)))
        return _struct.pack("<" + "h" * num_samples, *samples)

    async def speak_to_caller(text: str, send_connection_tone: bool = False):
        nonlocal agent_speaking, stream_id
        current_stream_id = stream_id or "vobiz-stream"
        if not text:
            logger.warning("speak_to_caller: no text provided, skipping")
            return
        agent_speaking = True
        logger.info("speak_to_caller: generating TTS for %d char text (stream_id=%s)", len(text), current_stream_id)
        try:
            # Send an immediate connection tone so caller hears audio instantly
            # while the Gemini TTS generates in the background (~4-6 seconds)
            if send_connection_tone:
                tone = _generate_connection_tone(sample_rate, 400)
                logger.info("speak_to_caller: sending connection tone: %d bytes", len(tone))
                await _send_vobiz_audio(websocket, current_stream_id, tone, sample_rate)

            response_audio = await _phone_tts_pcm(text, sample_rate)
            if response_audio:
                logger.info("speak_to_caller: sending audio response: %d bytes", len(response_audio))
                await _send_vobiz_audio(websocket, current_stream_id, response_audio, sample_rate)
            else:
                logger.warning("speak_to_caller: TTS returned no audio")
        except Exception as e:
            logger.error("speak_to_caller error: %s", e, exc_info=True)
        finally:
            agent_speaking = False

    async def process_utterance(audio: bytes):
        nonlocal session
        logger.info("Processing utterance: %d bytes", len(audio))
        transcript = await _gemini_transcribe_phone_audio(audio, sample_rate)
        if not transcript or len(transcript.strip()) < 2:
            logger.warning("Vobiz stream received no usable transcript, sending gentle prompt.")
            # Speak back to the caller instead of staying silent!
            await speak_to_caller("I didn't quite catch that. How can I help you with Nimbus products, pricing, or features today?")
            return
        logger.info("Vobiz stream transcript: %s", transcript)

        if session is None:
            session = {"history": [], "cart": [], "authenticated": True, "is_real_call": True}
        session["history"].append({"role": "user", "content": transcript})
        req = ReasonRequest(query=transcript, history=session["history"][:-1], cart=session["cart"])
        try:
            result = await process_reasoning(
                req,
                x_openai_key=config_state.get("openai_key") or os.environ.get("OPENAI_API_KEY"),
                x_gemini_key=config_state.get("gemini_key") or os.environ.get("Gemini_API_Key") or os.environ.get("GEMINI_API_KEY"),
                x_anthropic_key=config_state.get("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY")
            )
            response_text = result.get("text") or "I am sorry, I could not process that."
            session["cart"] = result.get("cart", session["cart"])
        except Exception as exc:
            print(f"Vobiz stream reasoning error: {exc}")
            response_text, session["cart"], _ = generate_mock_voice_response(
                transcript, session["cart"], config_state["selected_tools"], session["history"]
            )
        session["history"].append({"role": "assistant", "content": response_text})
        await speak_to_caller(response_text)

    async def process_audio_payload(payload_bytes: bytes, track: str):
        nonlocal media_frames, speech_started, silence_ms, utterance_ms, agent_speaking, processing_task, greeting_task
        if not payload_bytes:
            return
        if track and track.lower() not in ("inbound", "inbound_track", "caller", "user"):
            return

        frame = _normalize_vobiz_audio(payload_bytes, media_encoding)
        if not frame:
            return

        media_frames += 1
        if media_frames == 1:
            logger.info("First Vobiz media frame received: %d bytes, encoding=%s", len(frame), media_encoding)

        import struct
        samples = struct.unpack("<" + "h" * (len(frame) // 2), frame[: len(frame) - len(frame) % 2])
        if not samples:
            return
        rms = math.sqrt(sum(sample * sample for sample in samples) / max(len(samples), 1))
        peak = max(abs(sample) for sample in samples)
        # Mobile phone mic audio sensitivity threshold for speech buffering
        is_voice = rms > 35 or peak > 120
        # Intentional loud caller speech threshold required to interrupt/cancel an active agent response
        is_barge_in = (rms > 150 or peak > 450) and media_frames > 50
        endpoint_ms = int(config_state.get("endpoint_duration") or 600)

        if not speech_started:
            pre_roll_buffer.append(frame)

        if is_voice and not speech_started:
            speech_started = True
            silence_ms = 0
            logger.info("Speech detected at frame %d (RMS=%.1f peak=%d), buffering with pre-roll...", media_frames, rms, peak)
            audio_buffer.clear()
            for pf in pre_roll_buffer:
                audio_buffer.extend(pf)
            pre_roll_buffer.clear()

        if is_barge_in and agent_speaking:
            logger.info("Caller barge-in detected at frame %d (RMS=%.1f peak=%d), interrupting agent...", media_frames, rms, peak)
            agent_speaking = False
            if stream_id:
                try:
                    await websocket.send_json({"event": "clearAudio", "streamId": stream_id})
                except Exception:
                    pass
            if greeting_task and not greeting_task.done():
                greeting_task.cancel()


        if speech_started:
            audio_buffer.extend(frame)
            utterance_ms += VOBIZ_FRAME_MS

            if is_voice:
                silence_ms = 0
            else:
                silence_ms += VOBIZ_FRAME_MS
            if (silence_ms >= endpoint_ms or utterance_ms >= 10000) and len(audio_buffer) >= sample_rate * 2 // 2:

                utterance = bytes(audio_buffer)
                logger.info("Utterance complete: silence_ms=%d utterance_ms=%d buffer=%d bytes, processing...", silence_ms, utterance_ms, len(utterance))
                audio_buffer.clear()
                pre_roll_buffer.clear()
                speech_started = False
                silence_ms = 0
                utterance_ms = 0
                if processing_task and not processing_task.done():
                    processing_task.cancel()
                processing_task = asyncio.create_task(process_utterance(utterance))

    try:
        while True:
            try:
                raw_message = await websocket.receive()
            except RuntimeError:
                break

            message = None

            if isinstance(raw_message, dict):
                msg_type = raw_message.get("type")
                if msg_type == "websocket.disconnect":
                    logger.info("Vobiz websocket disconnected for call=%s", call_id)
                    break
                elif msg_type == "websocket.receive":
                    if raw_message.get("bytes"):
                        message = raw_message["bytes"]
                    elif raw_message.get("text"):
                        text_msg = raw_message["text"]
                        try:
                            message = json.loads(text_msg)
                        except Exception as e:
                            logger.warning("Failed to parse JSON: %s", e)
                            message = text_msg
            else:
                if hasattr(raw_message, 'type') and raw_message.type == WebSocketDisconnect:
                    logger.info("Vobiz websocket disconnected for call=%s", call_id)
                    break
                if hasattr(raw_message, 'bytes') and raw_message.bytes:
                    message = raw_message.bytes
                elif hasattr(raw_message, 'text') and raw_message.text:
                    try:
                        message = json.loads(raw_message.text)
                    except Exception:
                        message = raw_message.text

            if isinstance(message, (bytes, bytearray)):
                payload, track = _extract_vobiz_media_payload(message, media_encoding)
                await process_audio_payload(payload, track)
                continue

            event = message.get("event") if isinstance(message, dict) else None
            if event:
                logger.info("Vobiz event received: %s", event)
            if event == "start":
                start = message.get("start", {})
                stream_id = start.get("streamId")
                call_id = start.get("callId") or start.get("callUUID") or start.get("callSid")
                media_format = start.get("mediaFormat", {})
                sample_rate = int(media_format.get("sampleRate") or VOBIZ_STREAM_SAMPLE_RATE)
                media_encoding = media_format.get("encoding", "audio/x-l16")
                session = phone_sessions.setdefault(call_id or stream_id, {
                    "phone_number": start.get("from", "Unknown"),
                    "history": [],
                    "cart": [],
                    "is_real_call": True,
                    "authenticated": True
                })
                logger.info("Vobiz stream started: call=%s, stream=%s, encoding=%s, rate=%s", call_id, stream_id, media_encoding, sample_rate)
                logger.info("Creating greeting task for: %s (stream_id=%s)", PHONE_GREETING[:50], stream_id)
                greeting_task = asyncio.create_task(speak_to_caller(PHONE_GREETING, send_connection_tone=True))
                logger.info("Greeting task created: %s", greeting_task)
            elif event == "media":
                payload, track = _extract_vobiz_media_payload(message, media_encoding)
                await process_audio_payload(payload, track)
            elif event == "playedStream":
                logger.info("Vobiz stream audio played: %s", message.get('name'))
            elif event == "stop":
                logger.info("Vobiz stream stop: call=%s", call_id)
                break
    except WebSocketDisconnect:
        logger.info("Vobiz stream disconnected: call=%s", call_id)
    except Exception as exc:
        logger.exception("Vobiz stream error: %s", exc)
    finally:
        for task in (processing_task, greeting_task):
            if task and not task.done():
                task.cancel()
        if call_id:
            phone_sessions.pop(call_id, None)

@app.api_route("/api/phone/hangup", methods=["GET", "POST"])
async def phone_hangup(request: Request):
    """Handle Vobiz hangup callbacks without restarting the call flow."""
    from fastapi import Response
    form_data = {}
    try:
        form_data = dict(await request.form())
    except Exception:
        pass

    params = {**dict(request.query_params), **form_data}
    session_id = params.get("CallUUID") or params.get("CallSid")
    if session_id:
        phone_sessions.pop(session_id, None)

    logger.info("Phone call ended: session=%s, params=%s", session_id or 'unknown', params)
    return Response(content="", status_code=200)

@app.api_route("/api/phone/twiml-respond", methods=["GET", "POST"])
async def twiml_respond(request: Request):
    """Legacy webhook: redirect any Gather/Record callbacks to bidirectional streaming."""
    from fastapi import Response

    form_data = {}
    try:
        form_data = dict(await request.form())
    except Exception:
        pass
    params = {**dict(request.query_params), **form_data}
    print("Legacy twiml-respond hit; returning bidirectional stream XML:", params)

    host = _phone_public_host(request)
    return Response(
        content=_vobiz_stream_twiml(host),
        media_type="application/xml",
        headers={"ngrok-skip-browser-warning": "true"},
    )

# Phone Call Simulation endpoints
@app.post("/api/phone/call")
def initiate_call(phone_number: str = Form(...)):
    # Simple validation
    clean_number = phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # Check if number matches Nimbus Support
    is_nimbus = ("+18005550142" in clean_number or "18005550142" in clean_number or "5550142" in clean_number)
    
    session_id = f"call_{random.randint(1000, 9999)}"
    phone_sessions[session_id] = {
        "phone_number": phone_number,
        "is_nimbus": is_nimbus,
        "status": "connected",
        "authenticated": False,
        "otp": str(random.randint(1000, 9999)),
        "history": [],
        "cart": [] # Call session has its own temporary cart
    }
    
    greeting = (
        "Welcome to Nimbus Automated Support! I can help you query products, check prices, "
        "and modify your cart. First, let's verify your identity. I have sent a 4-digit code to your mobile. "
        "Please enter it using your keypad or speak it."
    ) if is_nimbus else "Connection established, but this is not the Nimbus Support number."
    
    return {
        "session_id": session_id,
        "status": "connected",
        "is_nimbus": is_nimbus,
        "greeting": greeting,
        "otp_required": is_nimbus
    }

@app.post("/api/phone/dtmf")
def send_dtmf(session_id: str = Form(...), key: str = Form(...)):
    session = phone_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
        
    response_text = ""
    auth_success = False
    
    if not session["authenticated"]:
        # User is trying to enter OTP
        current_digits = session.get("otp_digits", "") + key
        session["otp_digits"] = current_digits
        
        if len(current_digits) >= 4:
            if current_digits == session["otp"]:
                session["authenticated"] = True
                auth_success = True
                response_text = "Authentication successful! Your phone number is verified. You can now ask questions about products, add items to your cart, or check out."
            else:
                session["otp_digits"] = ""
                response_text = f"Invalid code '{current_digits}'. Please enter the 4-digit code again."
        else:
            response_text = f"Entered {key}. Waiting for remaining digits."
    else:
        # User is authenticated, standard keypad options could go here
        response_text = f"Received key '{key}'. You can speak any question or request to the operator."

    return {
        "session_id": session_id,
        "authenticated": session["authenticated"],
        "auth_success": auth_success,
        "response": response_text
    }

@app.post("/api/phone/speak")
async def speak_to_phone(
    request: Request,
    session_id: Optional[str] = Form(None),
    speech: Optional[str] = Form(None),
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key")
):
    form_data = {}
    try:
        form_data = dict(await request.form())
    except Exception:
        pass

    session_id = session_id or form_data.get("session_id")
    speech = speech or form_data.get("speech") or form_data.get("SpeechResult") or ""
    speech_clean = speech.strip()

    session = phone_sessions.get(session_id)
    if not session:
        return {
            "session_id": session_id or "unknown",
            "authenticated": False,
            "response": "Session expired or not found. Please redial.",
            "cart": []
        }
        
    if not speech_clean:
        return {
            "session_id": session_id,
            "authenticated": session.get("authenticated", False),
            "response": "I didn't hear any speech. Please ask your question or state your request.",
            "cart": session.get("cart", [])
        }

    speech_lower = speech_clean.lower()
    
    # 1. OTP Verification attempt if not authenticated
    word_to_digit = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
    }
    extracted_text = speech_lower
    for w, d in word_to_digit.items():
        extracted_text = re.sub(r'\b' + w + r'\b', d, extracted_text)
    digits = "".join(re.findall(r'\d', extracted_text))

    if not session["authenticated"]:
        if len(digits) == 4:
            if digits == session["otp"]:
                session["authenticated"] = True
                response_text = "Authentication successful! Your phone line is verified. How can I help you with Nimbus products today?"
                session.setdefault("history", []).append({"role": "user", "content": speech_clean})
                session.setdefault("history", []).append({"role": "assistant", "content": response_text})
                return {
                    "session_id": session_id,
                    "authenticated": True,
                    "response": response_text,
                    "cart": session.get("cart", [])
                }
            else:
                response_text = f"Verification code '{digits}' is incorrect. Please check the code and repeat the 4 digits."
                return {
                    "session_id": session_id,
                    "authenticated": False,
                    "response": response_text,
                    "cart": session.get("cart", [])
                }
        
        # Check if the user is asking to modify cart or checkout without OTP
        if any(action in speech_lower for action in ["add", "buy", "cart", "checkout", "purchase", "remove", "clear"]):
            return {
                "session_id": session_id,
                "authenticated": False,
                "response": f"To manage your cart or check out, please verify your identity by entering or speaking your 4-digit code (Code: {session['otp']}).",
                "cart": session.get("cart", [])
            }

    # 2. General query / Product query / Authenticated cart actions
    session.setdefault("history", []).append({"role": "user", "content": speech_clean})
    
    reason_req = ReasonRequest(
        query=speech_clean,
        history=session["history"][:-1],
        cart=session.get("cart", [])
    )

    try:
        result = await process_reasoning(
            reason_req,
            x_openai_key=x_openai_key,
            x_gemini_key=x_gemini_key,
            x_anthropic_key=x_anthropic_key
        )
        response_text = result.get("text")
        if not response_text or "error" in response_text.lower():
            resp, updated_cart, _ = generate_mock_voice_response(
                speech_clean, session.get("cart", []), config_state["selected_tools"], session.get("history", [])
            )
            response_text = resp
            session["cart"] = updated_cart
        else:
            session["cart"] = result.get("cart", session.get("cart", []))
            
        session["history"].append({"role": "assistant", "content": response_text})
    except Exception as e:
        print(f"Error in speak_to_phone reasoning: {e}")
        resp, updated_cart, _ = generate_mock_voice_response(
            speech_clean, session.get("cart", []), config_state["selected_tools"], session.get("history", [])
        )
        response_text = resp
        session["cart"] = updated_cart
        session["history"].append({"role": "assistant", "content": response_text})

    return {
        "session_id": session_id,
        "authenticated": session["authenticated"],
        "response": response_text,
        "cart": session.get("cart", [])
    }


# Mount static frontend files
static_dir = os.path.join(os.path.dirname(__file__), "nimbus-voice-agent-starter")
index_file = os.path.join(static_dir, "index.html")
if os.path.exists(index_file):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    @app.get("/")
    def root_status():
        return {
            "status": "online",
            "message": "Nimbus Voice Agent API Server is running.",
            "endpoints": {
                "incoming_call": "/api/phone/incoming-call",
                "vobiz_stream": "/api/phone/vobiz-stream"
            }
        }

if __name__ == "__main__":
    import uvicorn
    # Run uvicorn on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)

