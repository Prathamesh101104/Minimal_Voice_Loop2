import time
import json
import os

CATALOG_PATH = r"c:\Users\Prathamesh\OneDrive\Desktop\Minimal_Voice_Loop_2\nimbus-voice-agent-starter\data\catalog.json"

def load_catalog_data():
    if not os.path.exists(CATALOG_PATH):
        return {}
    with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

# The cart state is passed back and forth between frontend and backend to keep them synchronized.
# We will define standard Python tool functions that take the current cart list as an argument,
# modify it, and return the updated cart along with a status message and latency.

def execute_tool_with_latency(tool_name, func, *args, **kwargs):
    start_time = time.perf_counter()
    result = func(*args, **kwargs)
    latency_ms = (time.perf_counter() - start_time) * 1000
    return {
        "tool": tool_name,
        "result": result,
        "latency_ms": latency_ms
    }

def add_to_cart_impl(cart, product_id_or_name, tier_name=None, seats=1):
    catalog = load_catalog_data()
    products = catalog.get("products", [])
    
    # Try to find product by id or name
    product = None
    for p in products:
        if p.get("id").lower() == product_id_or_name.lower() or p.get("name").lower() == product_id_or_name.lower():
            product = p
            break
            
    if not product:
        return {"success": False, "message": f"Product '{product_id_or_name}' not found in catalog.", "cart": cart}
        
    tiers = product.get("tiers", [])
    # Find matching tier, or default to the first tier that has a monthly price > 0, or just the first tier
    tier = None
    if tier_name:
        for t in tiers:
            if t.get("name").lower() == tier_name.lower():
                tier = t
                break
    else:
        # Default to standard/paid tier
        for t in tiers:
            if (t.get("priceMonthly") or 0) > 0:
                tier = t
                break
        if not tier and tiers:
            tier = tiers[0]
            
    if not tier:
        return {"success": False, "message": f"No pricing tiers found for product '{product.get('name')}'.", "cart": cart}
        
    tier_label = tier.get("name")
    monthly_price = tier.get("priceMonthly") or 0
    annual_monthly_price = tier.get("priceAnnualMonthly") or monthly_price
    
    # Use monthly price or annual monthly price depending on cart structure (default monthly price)
    price = annual_monthly_price if tier.get("priceAnnualMonthly") is not None else monthly_price
    
    # Check if item is already in cart
    found = False
    for item in cart:
        if item.get("product_id") == product.get("id") and item.get("tier").lower() == tier_label.lower():
            item["seats"] = int(item.get("seats", 1)) + seats
            found = True
            break
            
    if not found:
        cart.append({
            "product_id": product.get("id"),
            "product_name": product.get("name"),
            "tier": tier_label,
            "seats": seats,
            "price": price
        })
        
    return {
        "success": True,
        "message": f"Added {seats} seat(s) of {product.get('name')} ({tier_label} tier) to cart.",
        "cart": cart
    }

def remove_from_cart_impl(cart, product_id_or_name, tier_name=None):
    # If tier_name is not provided, remove all matches for product_id_or_name
    new_cart = []
    removed_count = 0
    product_name_removed = ""
    
    for item in cart:
        match_id_or_name = (
            item.get("product_id").lower() == product_id_or_name.lower() or 
            item.get("product_name").lower() == product_id_or_name.lower()
        )
        match_tier = True
        if tier_name:
            match_tier = item.get("tier").lower() == tier_name.lower()
            
        if match_id_or_name and match_tier:
            removed_count += 1
            product_name_removed = item.get("product_name")
        else:
            new_cart.append(item)
            
    if removed_count > 0:
        tier_str = f" ({tier_name})" if tier_name else ""
        return {
            "success": True,
            "message": f"Removed '{product_name_removed}'{tier_str} from cart.",
            "cart": new_cart
        }
    else:
        return {
            "success": False,
            "message": f"Item '{product_id_or_name}' not found in cart.",
            "cart": cart
        }

def clear_cart_impl(cart):
    return {
        "success": True,
        "message": "Cart cleared successfully.",
        "cart": []
    }

def view_cart_impl(cart):
    if not cart:
        return {
            "success": True,
            "message": "Your shopping cart is empty.",
            "cart": cart,
            "formatted_list": "Your cart is empty."
        }
    items_desc = []
    for it in cart:
        name = it.get("product_name") or it.get("product_id") or "Unknown Product"
        tier = it.get("tier") or "Standard"
        seats = it.get("seats", 1)
        price = it.get("price", 0)
        items_desc.append(f"{name} ({tier} tier, {seats} seat(s)) at ${price}/mo each")
    return {
        "success": True,
        "message": "Cart retrieved.",
        "cart": cart,
        "formatted_list": ", ".join(items_desc)
    }

def get_cart_total_impl(cart):
    total = sum((float(item.get("price", 0)) * int(item.get("seats", 1))) for item in cart)
    return {
        "success": True,
        "total": total,
        "message": f"Total monthly price of cart is ${total:.2f}."
    }

def checkout_cart_impl(cart):
    if not cart:
        return {
            "success": False,
            "message": "Cannot checkout. Cart is empty.",
            "cart": cart
        }
    total = sum((float(item.get("price", 0)) * int(item.get("seats", 1))) for item in cart)
    # Generate random order id
    import random
    order_id = "NB-" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6))
    return {
        "success": True,
        "order_id": order_id,
        "total": total,
        "message": f"Order {order_id} confirmed! Checked out {len(cart)} items for a monthly total of ${total:.2f}.",
        "cart": [] # Clear cart on success
    }

def checkout_single_item_impl(cart, product_id_or_name, tier_name=None):
    # Find the item
    item_to_checkout = None
    remaining_cart = []
    
    for item in cart:
        match_id_or_name = (
            item.get("product_id").lower() == product_id_or_name.lower() or 
            item.get("product_name").lower() == product_id_or_name.lower()
        )
        match_tier = True
        if tier_name:
            match_tier = item.get("tier").lower() == tier_name.lower()
            
        if match_id_or_name and match_tier and not item_to_checkout:
            item_to_checkout = item
        else:
            remaining_cart.append(item)
            
    if not item_to_checkout:
        return {
            "success": False,
            "message": f"Item '{product_id_or_name}' not found in cart to checkout.",
            "cart": cart
        }
        
    total = float(item_to_checkout.get("price", 0)) * int(item_to_checkout.get("seats", 1))
    import random
    order_id = "NB-" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6))
    return {
        "success": True,
        "order_id": order_id,
        "total": total,
        "message": f"Single item checkout successful! Order {order_id} confirmed for {item_to_checkout.get('product_name')} ({item_to_checkout.get('tier')}) at a total of ${total:.2f}.",
        "cart": remaining_cart
    }

def calculate_annual_pricing_impl(monthly_price):
    # 20% discount for annual pricing as per company policy
    discounted_monthly = monthly_price * 0.8
    annual_total = discounted_monthly * 12
    return {
        "success": True,
        "monthly_price": monthly_price,
        "discounted_monthly_rate": discounted_monthly,
        "annual_total": annual_total,
        "message": f"A monthly price of ${monthly_price:.2f} becomes ${discounted_monthly:.2f}/month when billed annually upfront (Total: ${annual_total:.2f}/year, saving 20%)."
    }

def calculate_annual_savings_impl(monthly_price, annual_monthly_price=None):
    # If annual_monthly_price is not provided, we calculate it using the 20% standard discount
    if annual_monthly_price is None:
        annual_monthly_price = monthly_price * 0.8
        
    monthly_cost_annual_rate = annual_monthly_price * 12
    monthly_cost_monthly_rate = monthly_price * 12
    
    savings = monthly_cost_monthly_rate - monthly_cost_annual_rate
    pct_savings = ((monthly_cost_monthly_rate - monthly_cost_annual_rate) / monthly_cost_monthly_rate) * 100 if monthly_cost_monthly_rate > 0 else 0
    
    return {
        "success": True,
        "monthly_rate": monthly_price,
        "annual_monthly_rate": annual_monthly_price,
        "savings_amount": savings,
        "savings_percentage": pct_savings,
        "message": f"Paying monthly costs ${monthly_cost_monthly_rate:.2f}/year. Paying annually upfront (at ${annual_monthly_price:.2f}/month) costs ${monthly_cost_annual_rate:.2f}/year. You save ${savings:.2f}/year ({pct_savings:.1f}% savings)."
    }

def sort_products_impl(order="asc"):
    catalog = load_catalog_data()
    products = catalog.get("products", [])
    
    # We sort products by their lowest non-free tier price, or standard starter price
    product_prices = []
    for p in products:
        # Find minimum non-free price
        prices = []
        for t in p.get("tiers", []):
            p_monthly = t.get("priceMonthly")
            if p_monthly is not None and p_monthly > 0:
                prices.append(p_monthly)
        min_price = min(prices) if prices else 0
        product_prices.append((p, min_price))
        
    reverse = (order.lower() == "desc")
    product_prices.sort(key=lambda x: x[1], reverse=reverse)
    
    sorted_prods = []
    message_lines = [f"Sorted products in {order}ending order of starter price:"]
    for idx, (p, price) in enumerate(product_prices):
        sorted_prods.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "category": p.get("category"),
            "starter_price": price
        })
        message_lines.append(f"{idx+1}. {p.get('name')} - Starter Price: ${price}/mo (Category: {p.get('category')})")
        
    return {
        "success": True,
        "products": sorted_prods,
        "message": "\n".join(message_lines)
    }

def get_top_k_expensive_products_impl(k):
    # Sort in descending order first
    sorted_res = sort_products_impl(order="desc")
    top_k = sorted_res.get("products", [])[:k]
    
    message_lines = [f"Top {k} most expensive products:"]
    for idx, p in enumerate(top_k):
        message_lines.append(f"{idx+1}. {p.get('name')} - Starter Price: ${p.get('starter_price')}/mo ({p.get('category')})")
        
    return {
        "success": True,
        "products": top_k,
        "message": "\n".join(message_lines)
    }

def product_info_impl(product_name):
    catalog = load_catalog_data()
    products = catalog.get("products", [])
    
    def _norm(s):
        return "".join(c for c in (s or "").lower() if c.isalnum())
        
    q = _norm(product_name)
    if not q:
        return {"success": False, "message": "Product name is required."}
        
    matched = None
    for p in products:
        if _norm(p.get("id", "")) == q or _norm(p.get("name", "")) == q:
            matched = p
            break
            
    if not matched:
        qq = q[6:] if q.startswith("nimbus") else q
        for p in products:
            name = _norm(p.get("name", ""))
            if name == "nimbus" + qq or name.replace("nimbus", "") == qq:
                matched = p
                break
                
    if not matched:
        for p in products:
            name = _norm(p.get("name", ""))
            if qq and (qq in name or name.replace("nimbus", "") in qq):
                matched = p
                break
                
    if not matched:
        return {"success": False, "message": f"No product matches '{product_name}'."}
        
    tiers = []
    for t in matched.get("tiers", []):
        tiers.append({
            "name": t.get("name"),
            "monthly": float(t.get("priceMonthly") or 0),
            "annual_monthly": float(t.get("priceAnnualMonthly") or t.get("priceMonthly") or 0),
            "unit": t.get("unit")
        })
        
    return {
        "success": True,
        "id": matched.get("id"),
        "name": matched.get("name"),
        "category": matched.get("category"),
        "tiers": tiers,
        "message": f"Product Info for {matched.get('name')}: Category: {matched.get('category')}. Tiers: " + 
                   ", ".join([f"{t['name']} (${t['monthly']}/mo)" for t in tiers])
    }

