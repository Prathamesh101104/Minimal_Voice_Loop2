// A simple client-side shopping cart for the static Nimbus site.
//
// State lives in localStorage (no backend needed, so it works on GitHub Pages).
// A nav button shows the count and opens a slide-in drawer; "Add to cart"
// buttons on the product and pricing pages call addToCart(). Checkout is a
// dummy that just confirms and clears the cart.
//
// When you later build the voice agent, point its add_to_cart tool at this same
// store (read/write the "nimbus_cart" key, or expose addToCart on window) so a
// click here and "add it to my cart" said to the agent stay in sync.

import { el, escapeHtml, icon, loadCatalog } from "./app.js";

const KEY = "nimbus_cart";

let drawer, badge, listEl, totalEl, statusEl;

// ---- storage ----
function load() {
  try {
    const items = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}
function persist(items) {
  localStorage.setItem(KEY, JSON.stringify(items));
  paint(items);
}
const lineTotal = (it) => (Number(it.price) || 0) * (Number(it.seats) || 1);
const cartTotal = (items) => items.reduce((sum, it) => sum + lineTotal(it), 0);
const cartCount = (items) => items.reduce((n, it) => n + (Number(it.seats) || 1), 0);

// ---- public API ----
export async function addToCart(productName, tierName = null, seats = 1) {
  let product, tier, price = 0;
  try {
    const catalog = await loadCatalog();
    product = (catalog.products || []).find((p) => p.name === productName);
    const tiers = (product && product.tiers) || [];
    tier = tierName ? tiers.find((t) => t.name === tierName) : (tiers.find((t) => (t.priceMonthly || 0) > 0) || tiers[0]);
    price = (tier && (tier.priceAnnualMonthly ?? tier.priceMonthly)) || 0;
  } catch {
    // catalog unavailable: still add a bare line so the cart works
  }
  const id = (product && product.id) || productName;
  const tierLabel = (tier && tier.name) || tierName || "Standard";

  const items = load();
  const existing = items.find((i) => i.product_id === id && i.tier === tierLabel);
  if (existing) existing.seats = (Number(existing.seats) || 1) + seats;
  else items.push({ product_id: id, product_name: productName, tier: tierLabel, seats, price });
  persist(items);
  openCart();
  toast(`Added ${productName} (${tierLabel})`);
}

export function mountCart() {
  if (document.querySelector(".cart-btn")) return;

  const btn = el("button", {
    class: "cart-btn",
    "aria-label": "Open cart",
    html: `${icon("card")}<span class="cart-count" hidden>0</span>`,
    onclick: openCart,
  });
  const cta = document.querySelector(".nav-cta");
  if (cta) cta.insertBefore(btn, cta.firstChild);
  badge = btn.querySelector(".cart-count");

  drawer = el("div", {
    class: "cart-drawer",
    html: `<div class="cart-scrim"></div>
      <aside class="cart-panel" role="dialog" aria-label="Your cart">
        <header class="cart-head"><h3>Your cart</h3><button class="cart-x" aria-label="Close">${icon("arrow")}</button></header>
        <div class="cart-status"></div>
        <div class="cart-items"></div>
        <footer class="cart-foot">
          <div class="cart-total"><span>Monthly total</span><strong>$0</strong></div>
          <button class="btn btn-primary btn-block cart-checkout">Checkout (dummy)</button>
          <p class="cart-note">No real payment is taken. This is a teaching demo.</p>
        </footer>
      </aside>`,
  });
  document.body.append(drawer);
  listEl = drawer.querySelector(".cart-items");
  totalEl = drawer.querySelector(".cart-total strong");
  statusEl = drawer.querySelector(".cart-status");
  drawer.querySelector(".cart-scrim").addEventListener("click", closeCart);
  drawer.querySelector(".cart-x").addEventListener("click", closeCart);
  drawer.querySelector(".cart-checkout").addEventListener("click", checkout);

  paint(load());
}

// ---- drawer ----
export function openCart() {
  if (!drawer) return;
  drawer.classList.add("open");
  document.body.style.overflow = "hidden";
  paint(load());
}
function closeCart() {
  drawer.classList.remove("open");
  document.body.style.overflow = "";
}

function checkout() {
  const items = load();
  if (!items.length) {
    statusEl.innerHTML = `<div class="cart-empty">Your cart is empty.</div>`;
    return;
  }
  const orderId = "NB-" + Math.abs(hash(JSON.stringify(items) + items.length)).toString(36).toUpperCase().slice(0, 6);
  const total = cartTotal(items);
  localStorage.removeItem(KEY);
  listEl.innerHTML = "";
  statusEl.innerHTML = `<div class="cart-done">${icon("shield")}<div><strong>Order ${escapeHtml(orderId)} confirmed</strong><span>${items.length} app(s), $${total}/mo. Dummy checkout, no card charged.</span></div></div>`;
  totalEl.textContent = "$0";
  setBadge(0);
}

function paint(items) {
  if (!listEl) return;
  totalEl.textContent = `$${cartTotal(items)}`;
  setBadge(cartCount(items));
  if (!items.length) {
    listEl.innerHTML = `<div class="cart-empty">Your cart is empty. Add an app from any product or pricing page.</div>`;
    return;
  }
  if (statusEl) statusEl.innerHTML = "";
  listEl.innerHTML = "";
  items.forEach((it, idx) =>
    listEl.append(
      el("div", {
        class: "cart-item",
        html: `<div><strong>${escapeHtml(it.product_name)}</strong><span>${escapeHtml(it.tier)} &middot; ${
          it.seats
        } seat(s)</span></div>
          <div class="cart-item-right"><span>$${lineTotal(it)}/mo</span>
          <button class="cart-remove" data-idx="${idx}" aria-label="Remove">${icon("arrow")}</button></div>`,
      })
    )
  );
  listEl.querySelectorAll(".cart-remove").forEach((b) =>
    b.addEventListener("click", () => {
      const items2 = load();
      items2.splice(Number(b.dataset.idx), 1);
      persist(items2);
    })
  );
}

function setBadge(n) {
  if (!badge) return;
  badge.textContent = String(n);
  badge.hidden = !n;
}

function hash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return h;
}

let toastEl;
function toast(msg) {
  toastEl?.remove();
  toastEl = el("div", { class: "toast", html: escapeHtml(msg) });
  document.body.append(toastEl);
  setTimeout(() => toastEl?.classList.add("show"), 10);
  setTimeout(() => {
    toastEl?.classList.remove("show");
    setTimeout(() => toastEl?.remove(), 300);
  }, 2400);
}
