/* Shared helpers: theme, formatting, data loading and the analyzer picker. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } },
};

const Theme = {
  current() {
    return document.documentElement.dataset.theme ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  },
  init() {
    const saved = store.get("theme");
    if (saved) document.documentElement.dataset.theme = saved;
    const btn = $("#theme-btn");
    if (btn) btn.addEventListener("click", () => {
      const next = Theme.current() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      store.set("theme", next);
      window.dispatchEvent(new Event("themechange"));
    });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change",
      () => window.dispatchEvent(new Event("themechange")));
  },
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function money(v, cur) {
  if (v == null) return "–";
  const sym = cur === "EUR" ? "€" : "$";
  for (const [d, s] of [[1e9, "bn"], [1e6, "m"], [1e3, "k"]]) {
    if (Math.abs(v) >= d) return `${sym}${(v / d).toLocaleString("en", { maximumFractionDigits: v / d >= 100 ? 0 : 2 })}${s}`;
  }
  return `${sym}${Math.round(v)}`;
}
const pct = (v, digits = 1) => (v == null ? "–" : `${Number(v).toFixed(digits)}%`);
const signedPct = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${Number(v).toFixed(1)}%`);
const verdictClass = (v) => ({ "ENTER": "ok", "ENTER WITH CAUTION": "warn" }[v] || "bad");
const verdictText = (v) => ({ "ENTER": "Enter", "ENTER WITH CAUTION": "Enter with caution", "DO NOT ENTER NOW": "Do not enter now" }[v] || v);
const reportUrl = (s) => `report.html?p=${s.p}&t=${s.t}&h=${s.h}&s=${s.s}`;

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

function toast(msg) {
  let t = $(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 1800);
}

/* Make sure a selection is valid for the catalogue. */
function normalise(cat, s) {
  const out = { ...s };
  if (!cat.targets[out.t]) out.t = "EU";
  if (!cat.products.some((p) => p.hs === out.p && cat.available.includes(`${p.hs}-${out.t}`))) {
    out.p = (cat.products.find((p) => cat.available.includes(`${p.hs}-${out.t}`)) || cat.products[0]).hs;
  }
  const homes = cat.targets[out.t].homes.map((h) => h.code);
  if (!homes.includes(out.h)) out.h = homes[0];
  if (!cat.sizes[out.s]) out.s = "medium";
  return out;
}

/*
 * Analyzer picker. variant "card" (stacked, home page) or "bar" (one row, report page).
 * Calls onSubmit(selection) when the user asks for a report.
 */
function buildPicker(form, cat, initial, { variant = "card", onSubmit }) {
  let st = normalise(cat, initial);
  const targetSeg = Object.entries(cat.targets).map(([k, v]) =>
    `<label><input type="radio" name="t" value="${k}"><span>${k === "EU" ? "🇪🇺" : "🇨🇳"} ${esc(v.label)}</span></label>`).join("");
  const sizeSeg = Object.keys(cat.sizes).map((k) =>
    `<label><input type="radio" name="s" value="${k}"><span>${k[0].toUpperCase() + k.slice(1)}</span></label>`).join("");
  form.innerHTML = `
    <label class="field product"><span>Product</span><select name="p" aria-label="Product"></select></label>
    <div class="field"><span>Target market</span><div class="seg" role="radiogroup" aria-label="Target market">${targetSeg}</div></div>
    <label class="field"><span>Company home country</span><select name="h" aria-label="Home country"></select></label>
    <div class="field"><span>Company size</span><div class="seg" role="radiogroup" aria-label="Company size">${sizeSeg}</div></div>
    ${variant === "slot" ? "" : `<div class="actions">${variant === "card"
      ? '<button class="btn block" type="submit">Generate report <span aria-hidden="true">→</span></button>'
      : '<button class="btn sm" type="submit">Update report</button>'}</div>`}`;

  const fill = () => {
    form.p.innerHTML = cat.products.map((p) => {
      const ok = cat.available.includes(`${p.hs}-${st.t}`);
      return `<option value="${p.hs}" ${ok ? "" : "disabled"}>${p.icon} ${esc(p.label)}${variant !== "bar" ? ` · HS ${p.hs}` : ""}${ok ? "" : " (no data)"}</option>`;
    }).join("");
    form.h.innerHTML = cat.targets[st.t].homes.map((h) => `<option value="${h.code}">${esc(h.name)}</option>`).join("");
    form.p.value = st.p; form.h.value = st.h;
    $$('input[name="t"]', form).forEach((i) => { i.checked = i.value === st.t; });
    $$('input[name="s"]', form).forEach((i) => { i.checked = i.value === st.s; });
  };
  fill();

  form.addEventListener("change", (e) => {
    st = normalise(cat, { p: form.p.value, t: $('input[name="t"]:checked', form).value,
      h: form.h.value, s: $('input[name="s"]:checked', form).value });
    if (e.target.name === "t") fill();
  });
  form.addEventListener("submit", (e) => { e.preventDefault(); if (onSubmit) onSubmit(st); });
  return () => st;
}
