/* Compare page: up to three entry cases side by side. */
(async function () {
  Theme.init();
  let cat;
  try { cat = await getJSON("data/catalog.json"); } catch (e) {
    $("#result").innerHTML = '<p class="muted">Could not load the data catalogue.</p>'; return;
  }
  $("#updated").textContent = cat.updated;

  const DEFAULTS = [
    { p: "841861", t: "EU", h: "JP", s: "large" },
    { p: "841861", t: "CN", h: "JP", s: "large" },
    { p: "850760", t: "EU", h: "KR", s: "large" },
  ];
  const parse = (txt) => { const [p, t, h, s] = (txt || "").split("-"); return p ? { p, t, h, s } : null; };
  const fromUrl = (new URLSearchParams(location.search).get("c") || "").split(",").map(parse).filter(Boolean);
  const initial = [0, 1, 2].map((i) => fromUrl[i] || DEFAULTS[i]);
  const useThird = fromUrl.length !== 2;

  const getters = [];
  $("#slots").innerHTML = ["A", "B", "C"].map((n, i) => `
    <div class="card slot${i === 2 && !useThird ? " off" : ""}" id="slot-${i}">
      <div class="slot-h"><b>Case ${n}</b>${i === 2 ? `<label class="muted" style="font-size:13px"><input type="checkbox" id="use-c" ${useThird ? "checked" : ""}> include</label>` : ""}</div>
      <form aria-label="Case ${n}"></form>
    </div>`).join("");
  $$(".slot form").forEach((f, i) => getters.push(buildPicker(f, cat, initial[i], { variant: "slot" })));
  $("#use-c").addEventListener("change", (e) => $("#slot-2").classList.toggle("off", !e.target.checked));

  const cases = () => getters.filter((_, i) => i < 2 || $("#use-c").checked).map((g) => g());
  const key = (s) => `${s.p}-${s.t}-${s.h}-${s.s}`;
  $("#share").addEventListener("click", async () => {
    const url = `${location.origin}${location.pathname}?c=${cases().map(key).join(",")}`;
    history.replaceState(null, "", url);
    try { await navigator.clipboard.writeText(url); toast("Link copied"); } catch (e) { toast(url); }
  });
  $("#run").addEventListener("click", run);
  run();

  async function run() {
    const list = cases();
    history.replaceState(null, "", `?c=${list.map(key).join(",")}`);
    $("#result").innerHTML = '<div class="skeleton" style="height:420px;margin-top:28px"></div>';
    let data;
    try {
      data = await Promise.all(list.map(async (s) => {
        const [m, r] = await Promise.all([getJSON(`data/m/${s.p}-${s.t}.json`), getJSON(`data/r/${key(s)}.json`)]);
        return { s, m, r, product: cat.products.find((p) => p.hs === s.p) };
      }));
    } catch (e) {
      $("#result").innerHTML = '<div class="state"><h2>A case is not available</h2><p class="muted">Pick another product or market.</p></div>';
      return;
    }
    render(data);
  }

  function uplift(c) { // landed cost before VAT, % over ex-works (same formula as the report)
    const f = c.freight_pct, d = c.duty_pct, o = c.other_pct;
    return (100 + f) * (1 + d / 100) + o - 100;
  }

  function render(data) {
    const sameCur = new Set(data.map((d) => d.m.currency)).size === 1;
    const rows = [
      { label: "Verdict", fmt: (d) => `<span class="badge ${verdictClass(d.r.verdict)}">${verdictText(d.r.verdict)}</span>` },
      { label: "Attractiveness (0–10)", val: (d) => d.r.score, better: "high", fmt: (d) => `<b>${Number(d.r.score).toFixed(1)}</b>` },
      { label: "Recommended entry mode", fmt: (d) => esc(d.r.mode) },
      { label: `Import market ${data[0].m.latest_year}`, val: (d) => (sameCur ? d.m.latest_size : null), better: "high", fmt: (d) => money(d.m.latest_size, d.m.currency) },
      { label: "Growth (trend, per year)", val: (d) => d.m.growth, better: "high", fmt: (d) => `${signedPct(d.m.growth)} <small class="conf conf-${d.m.quality.confidence}">${d.m.quality.confidence}</small>` },
      { label: "Supplier concentration (HHI)", val: (d) => d.m.hhi, better: "low", fmt: (d) => Math.round(d.m.hhi).toLocaleString("en") },
      { label: "Applicable import duty", val: (d) => d.r.tariff.applicable, better: "low", fmt: (d) => (d.r.tariff.applicable != null ? `${d.r.tariff.applicable}%` : "n/a") },
      { label: "Landed cost before VAT", val: (d) => uplift(d.r.cost), better: "low", fmt: (d) => signedPct(uplift(d.r.cost)) + " on ex-works" },
      { label: "CAGE distance", val: (d) => ({ Low: 1, Medium: 2, High: 3 }[d.r.cage]), better: "low", fmt: (d) => `<span class="lvl-${esc(d.r.cage)}">${esc(d.r.cage)}</span>` },
      { label: "Your market share", val: (d) => (d.r.position.present ? d.r.position.share_pct : 0), better: "high", fmt: (d) => (d.r.position.present ? `${pct(d.r.position.share_pct)} (#${d.r.position.rank})` : "Not a supplier yet") },
      { label: "Price level vs market", fmt: (d) => (d.r.position.price_position ? `${d.r.position.price_position} (${d.r.position.price_ratio}×)` : "n/a") },
      { label: "High-severity risks", val: (d) => d.r.risks.filter((x) => x.likelihood === "High" && x.impact === "High").length, better: "low", fmt: (d) => String(d.r.risks.filter((x) => x.likelihood === "High" && x.impact === "High").length) },
      { label: "Verdict robust to weights?", fmt: (d) => (d.m.sensitivity.robust ? "Yes" : "Borderline") },
    ];
    const best = (row) => {
      if (!row.val) return new Set();
      const vals = data.map(row.val);
      if (vals.some((x) => x == null)) return new Set();
      const target = row.better === "high" ? Math.max(...vals) : Math.min(...vals);
      if (vals.every((x) => x === target)) return new Set();
      return new Set(vals.map((x, i) => (x === target ? i : -1)).filter((i) => i >= 0));
    };
    const head = data.map((d, i) => `<th class="case">Case ${"ABC"[i]}: ${d.product.icon} ${esc(d.product.label)}
      <small>${esc(d.r.home_name)} → ${esc(cat.targets[d.s.t].label)} · ${esc(d.s.s)}</small></th>`).join("");
    const body = rows.map((row) => {
      const b = best(row);
      return `<tr><td>${row.label}</td>${data.map((d, i) => `<td class="${b.has(i) ? "best" : ""}">${row.fmt(d)}</td>`).join("")}</tr>`;
    }).join("");

    const ranked = data.map((d, i) => ({ d, i, hr: d.r.risks.filter((x) => x.likelihood === "High" && x.impact === "High").length }))
      .sort((a, b) => b.d.r.score - a.d.r.score || a.hr - b.hr);
    const top = ranked[0], second = ranked[1];
    const gap = (top.d.r.score - second.d.r.score).toFixed(1);
    const close = Number(gap) < 0.5;
    const caseName = (x) => `Case ${"ABC"[x.i]} (${x.d.product.label}, ${x.d.r.home_name} → ${cat.targets[x.d.s.t].label})`;

    $("#result").innerHTML = `
      <div class="card reco"><h2>${close ? "Too close to call on the score alone" : `Start with ${esc(caseName(top))}`}</h2>
        <p>${esc(caseName(top))} scores ${Number(top.d.r.score).toFixed(1)} (${verdictText(top.d.r.verdict).toLowerCase()}), ${gap} points ahead of ${esc(caseName(second))}.
        ${close ? "With a gap under 0.5, compare duty, distance and your existing market share before choosing." : `Suggested mode: ${esc(top.d.r.mode.toLowerCase())}.`}
        ${top.d.m.sensitivity.robust ? "" : " Its verdict is weight-sensitive, so validate demand before committing."}</p></div>
      <div class="card pad cmp"><div class="table-wrap"><table><thead><tr><th>Metric</th>${head}</tr></thead><tbody>${body}</tbody></table></div>
        <p class="muted" style="font-size:13px;margin:0">Highlighted: best value in the row. Market sizes are only compared when the currency matches (EU data in EUR, China data in USD).
        ${data.map((d, i) => `<a href="${reportUrl(d.s)}">Full report ${"ABC"[i]}</a>`).join(" · ")}</p></div>`;
  }
})();
