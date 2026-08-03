# Nimbus: a fictitious SaaS website (voice-agent starter)

This is a static marketing/catalog website for **Nimbus**, a made-up all-in-one
business software suite (think a fictional Zoho / Salesforce). It is the
**starting point for the Voice Agents bootcamp build**: a real product surface
that you will point a voice agent at.

There is **no voice agent in this repo** on purpose. You add it. The site gives
you the company, the catalog, the pricing, and the policies that your agent will
answer questions about and act on.

## What's here

```
.
├── index.html        # home
├── products.html     # filterable catalog (?cat=<id>)
├── product.html      # product detail (?id=<slug>)
├── pricing.html      # plan model + per-product starting prices
├── support.html      # refund / SLA / billing / security policies + FAQs
├── about.html        # company profile
├── assets/
│   ├── styles.css    # design system
│   ├── app.js        # catalog loader, shared layout (nav/footer), helpers
│   ├── render.js     # per-page renderers
│   └── favicon.svg
└── data/
    └── catalog.json  # single source of truth: company + policies + products
```

Everything is driven by `data/catalog.json`. There is **no build step** and **no
backend**: plain HTML, CSS, and ES modules.

## Run locally

`fetch()` needs HTTP (not `file://`), so serve the folder:

```bash
python3 -m http.server 8093
# then open http://localhost:8093/
```

## Build a voice agent on top of it

This is where your work begins. A typical path:

1. Build a small backend (RAG over `data/catalog.json`, a few tools, an LLM).
2. Add a voice loop (speech-to-text -> LLM -> text-to-speech) with barge-in.
3. Drop a "talk to Nimbus" button on the site that calls your backend.

Keep your API keys private. Never commit keys to this public repo.

## Notes

- Nimbus is **not a real company**. Names, prices, and policies are invented for
  teaching.
- Pricing buttons are static links; there is no real cart or checkout (you can
  add one as a tool your agent drives).
