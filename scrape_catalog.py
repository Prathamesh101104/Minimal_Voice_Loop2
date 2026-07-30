import json
import os

def main():
    catalog_path = r"c:\Users\Prathamesh\OneDrive\Desktop\Minimal_Voice_Loop_2\nimbus-voice-agent-starter\data\catalog.json"
    output_path = r"c:\Users\Prathamesh\OneDrive\Desktop\Minimal_Voice_Loop_2\nimbus-voice-agent-starter\data\context.md"

    if not os.path.exists(catalog_path):
        print(f"Error: Catalog file not found at {catalog_path}")
        return

    with open(catalog_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    markdown_content = []

    # 1. Company Profile
    company = data.get("company", {})
    markdown_content.append("# Nimbus Company Profile")
    markdown_content.append(f"- **Name**: {company.get('name', 'Nimbus')}")
    markdown_content.append(f"- **Legal Name**: {company.get('legalName', '')}")
    markdown_content.append(f"- **Tagline**: {company.get('tagline', '')}")
    markdown_content.append(f"- **Founded**: {company.get('founded', '')}")
    markdown_content.append(f"- **Headquarters**: {company.get('hq', '')}")
    markdown_content.append(f"- **About**: {company.get('about', '')}")
    markdown_content.append(f"- **Mission**: {company.get('mission', '')}")
    
    markdown_content.append("\n## Company Stats")
    stats = company.get("stats", {})
    for key, value in stats.items():
        markdown_content.append(f"- **{key}**: {value}")

    markdown_content.append("\n## Contact Information")
    contact = company.get("contact", {})
    for key, value in contact.items():
        markdown_content.append(f"- **{key.capitalize()}**: {value}")
    
    markdown_content.append("\n" + "="*40 + "\n")

    # 2. Company Policies
    policies = data.get("policies", {})
    markdown_content.append("# Company Policies")
    for key, policy_text in policies.items():
        # format key beautifully, e.g. freeTrial -> Free Trial
        title = "".join([f" {c}" if c.isupper() else c for c in key]).strip().title()
        markdown_content.append(f"## {title} Policy")
        markdown_content.append(policy_text)
        markdown_content.append("")

    markdown_content.append("\n" + "="*40 + "\n")

    # 3. Product Catalog
    markdown_content.append("# Product Catalog")
    
    # Map category ID/Name for easy retrieval if needed
    categories = {cat["id"]: cat["name"] for cat in data.get("categories", [])}
    
    products = data.get("products", [])
    for prod in products:
        prod_id = prod.get("id")
        name = prod.get("name")
        tagline = prod.get("tagline")
        summary = prod.get("summary")
        description = prod.get("description")
        category = prod.get("category", "")
        
        markdown_content.append(f"## Product: {name}")
        markdown_content.append(f"- **Product ID**: {prod_id}")
        markdown_content.append(f"- **Category**: {category}")
        markdown_content.append(f"- **Tagline**: {tagline}")
        markdown_content.append(f"- **Summary**: {summary}")
        markdown_content.append(f"- **Description**: {description}")
        
        markdown_content.append("\n### Key Features")
        for feat in prod.get("keyFeatures", []):
            markdown_content.append(f"- {feat}")
            
        markdown_content.append("\n### Specifications")
        specs = prod.get("specs", {})
        for spec_key, spec_val in specs.items():
            markdown_content.append(f"- **{spec_key}**: {spec_val}")
            
        markdown_content.append("\n### Integrations")
        for integration in prod.get("integrations", []):
            markdown_content.append(f"- {integration}")

        markdown_content.append("\n### Pricing Tiers")
        tiers = prod.get("tiers", [])
        for tier in tiers:
            tier_name = tier.get("name")
            monthly = tier.get("priceMonthly")
            annual = tier.get("priceAnnualMonthly")
            unit = tier.get("unit", "")
            
            price_str = ""
            if monthly is None or tier.get("custom"):
                price_str = "Custom / Enterprise Pricing (Contact Sales)"
            else:
                price_str = f"${monthly} {unit} (Billed Monthly) or ${annual} {unit} (Billed Annually)"
            
            markdown_content.append(f"#### Tier: {tier_name}")
            markdown_content.append(f"- **Pricing**: {price_str}")
            
            limits = tier.get("limits", {})
            if limits:
                markdown_content.append("- **Limits**:")
                for lim_k, lim_v in limits.items():
                    markdown_content.append(f"  - {lim_k}: {lim_v}")
                    
            highlights = tier.get("highlights", [])
            if highlights:
                markdown_content.append("- **Highlights**:")
                for hl in highlights:
                    markdown_content.append(f"  - {hl}")
            markdown_content.append("")

        add_ons = prod.get("addOns", [])
        if add_ons:
            markdown_content.append("### Add-ons")
            for addon in add_ons:
                markdown_content.append(f"- **{addon.get('name')}**: {addon.get('price')} - {addon.get('desc')}")
            markdown_content.append("")

        faqs = prod.get("faqs", [])
        if faqs:
            markdown_content.append("### Product FAQs")
            for faq in faqs:
                markdown_content.append(f"- **Q**: {faq.get('q')}")
                markdown_content.append(f"  - **A**: {faq.get('a')}")
            markdown_content.append("")

        markdown_content.append("-" * 20 + "\n")

    # Write out
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(markdown_content))

    print(f"Successfully generated context.md at {output_path} (size: {len(markdown_content)} lines)")

if __name__ == "__main__":
    main()
