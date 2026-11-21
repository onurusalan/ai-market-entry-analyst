/* Insights page: cross-product data stories built from data/insights.json. */
(async function () {
  Theme.init();
  let cat, ins;
  try { [cat, ins] = await Promise.all([getJSON("data/catalog.json"), getJSON("data/insights.json")]); } catch (e) {
    $("#main").insertAdjacentHTML("beforeend", '<p class="muted">Could not load the data.</p>'); return;
  }
  $("#updated").textContent = cat.updated;
  const eu = ins.eu_dependency, cn = ins.eu_in_china;
  const pp = (a, b) => `${b - a >= 0 ? "+" : ""}${(b - a).toFixed(1)} pp`;
  const link = (r, t) => `report.html?p=${r.hs}&t=${t}&h=${t === "EU" ? "CN" : "DE"}&s=medium`;

  const over50 = eu.filter((r) => r.china_share >= 50);
  $("#s1-lead").textContent = `In ${over50.length} of ${eu.length} products tracked, China supplies more than half of what the EU imports from outside the bloc: ${over50.map((r) => `${r.label} (${r.china_share.toFixed(0)}%)`).join(", ")}. That concentration is why the EU is "de-risking", and why non-Chinese suppliers find buyers looking for alternatives.`;
  const lead = cn.filter((r) => r.eu_share >= 40), weak = cn.filter((r) => r.eu_share < 10);
  $("#s2-lead").textContent = `EU-27 suppliers hold at least 40% of China's imports in ${lead.map((r) => r.label).join(", ") || "no product"}, but under 10% in ${weak.map((r) => r.label).join(", ") || "none"}, where China's own industry or Asian suppliers dominate.`;

  $("#t-dep tbody").innerHTML = eu.map((r) => `<tr><td><a href="${link(r, "EU")}">${r.icon} ${esc(r.label)}</a></td><td class="num">${money(r.market, "EUR")}</td>
    <td class="num"><b>${pct(r.china_share)}</b></td><td class="num">${pp(r.china_share_first, r.china_share)}</td><td class="num">${Math.round(r.hhi).toLocaleString("en")}</td>
    <td><span class="conf conf-${r.confidence}">${r.confidence}</span></td></tr>`).join("");
  $("#t-cn tbody").innerHTML = cn.map((r) => `<tr><td><a href="${link(r, "CN")}">${r.icon} ${esc(r.label)}</a></td><td class="num">${money(r.market, "USD")}</td>
    <td class="num"><b>${pct(r.eu_share)}</b></td><td class="num">${pp(r.eu_share_first, r.eu_share)}</td><td>${esc(r.top_supplier || "–")} (${pct(r.top_share)})</td></tr>`).join("");

  const tp = cat.trade_policy || [];
  $("#t-watch tbody").innerHTML = tp.map((x) => `<tr><td>${x.in_catalogue ? `<a href="report.html?p=${x.hs}&t=EU&h=CN&s=medium">${esc(x.label)}</a>` : esc(x.label)}<br><small class="muted">HS ${x.hs}</small></td>
    <td>${esc(x.note)}</td><td style="white-space:nowrap">${esc(x.checked)}</td><td>${x.source ? `<a href="${x.source}" rel="noopener">Official source</a>` : "–"}</td></tr>`).join("");
  if (cat.kb) $("#watch-status").textContent = `Knowledge base compiled ${cat.kb.as_of}${cat.kb.stale ? ": due for review" : ""}. Not legal advice.`;

  const rising = eu.slice().sort((a, b) => (b.china_share - b.china_share_first) - (a.china_share - a.china_share_first))[0];
  const falling = cn.slice().sort((a, b) => (a.eu_share - a.eu_share_first) - (b.eu_share - b.eu_share_first))[0];
  const imp = [
    ["Non-Chinese suppliers selling to the EU", `Where China's share is high and concentration (HHI) is above 1,800, EU buyers actively seek second sources. Position on reliability, compliance (Battery Regulation, forced-labour rules) and lead time, not just price.`],
    ["Chinese firms selling to the EU", `The fastest rise in China's share is in ${rising ? rising.label : "–"} (${rising ? pp(rising.china_share_first, rising.china_share) : ""}). Rapid share gains attract trade-defence cases: build duty scenarios into pricing and consider EU assembly.`],
    ["EU firms selling to China", `EU suppliers are strongest in premium, regulated or brand-driven categories. The weakest trend is in ${falling ? falling.label : "–"} (${falling ? pp(falling.eu_share_first, falling.eu_share) : ""}), a sign of local substitution: compete on brand and certification, or partner locally.`],
  ];
  $("#implications").innerHTML = imp.map(([h, p]) => `<div class="card feat"><h3>${h}</h3><p>${p}</p></div>`).join("");

  const draw = () => {
    if (!window.Plotly) return;
    const css = getComputedStyle(document.documentElement), v = (n) => css.getPropertyValue(n).trim();
    const lay = (rows) => ({
      margin: { t: 10, r: 20, b: 40, l: 170 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Inter, sans-serif", size: 12, color: v("--muted") }, showlegend: true,
      legend: { orientation: "h", y: -0.12, x: 0 },
      xaxis: { range: [0, 100], ticksuffix: "%", gridcolor: v("--line"), zeroline: false, fixedrange: true },
      yaxis: { gridcolor: "rgba(0,0,0,0)", fixedrange: true, automargin: true },
      shapes: rows.map((r, i) => ({ type: "line", y0: i, y1: i, x0: r[0], x1: r[1], line: { color: v("--line"), width: 4 } })),
    });
    const dumbbell = (id, rows, labels, firstName, lastName, alt) => {
      const r = rows.slice().reverse(), lab = labels.slice().reverse();
      Plotly.react(id, [
        { type: "scatter", mode: "markers", name: firstName, y: lab, x: r.map((x) => x[0]), marker: { size: 11, color: v("--faint") }, hovertemplate: "%{y}: %{x:.1f}%<extra></extra>" },
        { type: "scatter", mode: "markers", name: lastName, y: lab, x: r.map((x) => x[1]), marker: { size: 13, color: v("--accent") }, hovertemplate: "%{y}: %{x:.1f}%<extra></extra>" },
      ], lay(r), { displayModeBar: false, responsive: true });
      const el = document.getElementById(id); el.setAttribute("role", "img"); el.setAttribute("aria-label", alt);
    };
    dumbbell("c-dep", eu.map((r) => [r.china_share_first, r.china_share]), eu.map((r) => `${r.icon} ${r.label}`),
      "Earliest year with data", `Latest (${cat.years[1]})`, `China's share of EU imports by product; highest: ${eu[0]?.label} at ${eu[0]?.china_share}%.`);
    dumbbell("c-cn", cn.map((r) => [r.eu_share_first, r.eu_share]), cn.map((r) => `${r.icon} ${r.label}`),
      "Earliest year with data", `Latest (${cat.years[1]})`, `EU-27 share of China's imports by product; highest: ${cn[0]?.label} at ${cn[0]?.eu_share}%.`);
  };
  if (window.Plotly) draw(); else window.addEventListener("load", draw);
  window.addEventListener("themechange", draw);
})();
