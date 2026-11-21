/* Report page: loads one pre-computed report and renders KPIs, charts and the narrative. */
(async function () {
  Theme.init();
  const main = $("#main");
  let cat;
  try { cat = await getJSON("data/catalog.json"); } catch (e) { return fail("Could not load the data catalogue."); }
  $("#updated").textContent = cat.updated;

  const q = new URLSearchParams(location.search);
  const f = cat.featured[0] || {};
  const st = normalise(cat, { p: q.get("p") || f.hs, t: q.get("t") || f.target, h: q.get("h") || f.home, s: q.get("s") || f.size });
  buildPicker($("#picker"), cat, st, { variant: "bar", onSubmit: (s) => { location.href = reportUrl(s); } });

  let m, r;
  try {
    [m, r] = await Promise.all([getJSON(`data/m/${st.p}-${st.t}.json`), getJSON(`data/r/${st.p}-${st.t}-${st.h}-${st.s}.json`)]);
  } catch (e) { return fail("This combination is not available yet. Try another product or market."); }

  const product = cat.products.find((p) => p.hs === st.p);
  const tName = cat.targets[st.t].label;
  document.title = `${product.label} → ${tName} · Market Entry Analyst`;
  render(m, r, product, tName);
  if (location.search !== `?${new URLSearchParams(st)}`) history.replaceState(null, "", reportUrl(st));

  function fail(msg) {
    main.innerHTML = `<div class="state"><h2>Report unavailable</h2><p class="muted">${esc(msg)}</p>
      <p><a class="btn" href="index.html">Back to the analyzer</a></p></div>`;
  }

  function render(m, r, product, tName) {
    const cur = m.currency;
    const vc = verdictClass(r.verdict);
    const share = m.share[String(m.latest_year)];
    const highRisks = r.risks.filter((x) => x.likelihood === "High" && x.impact === "High").length;
    const ring = 2 * Math.PI * 44;
    const icon = { ok: '<path d="M20 6L9 17l-5-5"/>', warn: '<path d="M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/>',
      bad: '<path d="M18 6L6 18M6 6l12 12"/>' }[vc];

    main.innerHTML = `
    <div class="r-head">
      <div class="crumbs"><a href="index.html">Home</a> / <a href="index.html#cases">Reports</a> / ${esc(product.label)} → ${esc(tName)}</div>
      <div class="r-top">
        <div><h1>${product.icon} ${esc(product.label)} → ${esc(tName)}</h1>
          <div class="chips"><span class="chip">HS ${m.hs}</span><span class="chip">${esc(m.sector)}</span>
            <span class="chip">Home: ${esc(r.home_name)}</span><span class="chip">${esc(cat.sizes[r.size])}</span>
            <span class="chip">Data ${m.years[0]}–${m.years[m.years.length - 1]}</span></div></div>
        <div class="r-actions"><button class="btn ghost sm" id="copy">Copy link</button><a class="btn ghost sm" href="${compareUrl()}">Compare</a><button class="btn ghost sm" id="csv">Download data (CSV)</button><button class="btn ghost sm" id="print">Download PDF</button></div>
      </div>
    </div>

    <div class="verdict ${vc}">
      <div class="v-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${icon}</svg></div>
      <div><div class="label">Verdict</div><div class="v">${verdictText(r.verdict)}</div>
        <div class="mode">Recommended entry mode: <b>${esc(r.mode)}</b></div></div>
      <div class="gauge" title="Market attractiveness"><svg viewBox="0 0 104 104"><circle cx="52" cy="52" r="44" fill="none" stroke="var(--line)" stroke-width="9"/>
        <circle cx="52" cy="52" r="44" fill="none" stroke="currentColor" class="lvl" stroke-width="9" stroke-linecap="round"
          stroke-dasharray="${ring}" stroke-dashoffset="${ring * (1 - r.score / 10)}" style="color:var(--${vc})"/></svg>
        <div class="val"><div><b>${Number(r.score).toFixed(1)}</b><span>of 10</span></div></div></div>
    </div>

    <div class="kpis">
      <div class="card kpi"><span>Import market ${m.latest_year}</span><b>${money(m.latest_size, cur)}</b><small>${esc(m.source.split("(")[0])}</small></div>
      <div class="card kpi"><span>Growth (trend)</span><b>${signedPct(m.growth)}</b><small>per year · <span class="conf conf-${m.quality.confidence}">${m.quality.confidence} confidence</span></small></div>
      <div class="card kpi"><span>Concentration</span><b>${Math.round(m.hhi).toLocaleString("en")}</b><small>HHI · ${esc(m.hhi_label.split(" (")[0])}</small></div>
      <div class="card kpi"><span>${st.t === "CN" ? "EU-27 share" : "China's share"}</span><b>${pct(share)}</b><small>${esc(m.share_label)}</small></div>
      <div class="card kpi"><span>CAGE distance</span><b class="lvl-${esc(r.cage)}">${esc(r.cage)}</b><small>${highRisks} high-severity risk${highRisks === 1 ? "" : "s"}</small></div>
    </div>

    ${m.quality.flags.length ? `<div class="notice" role="note"><b>Data note (${m.quality.confidence.toLowerCase()} confidence):</b>
      <ul>${m.quality.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></div>` : ""}

    <div class="charts">
      <div class="card chart-card"><h3>Import market size</h3><p class="cap">${cur}, ${m.years[0]}–${m.latest_year}</p><div class="plot" id="c-size"></div></div>
      <div class="card chart-card"><h3>Who supplies the market</h3><p class="cap">Top suppliers' share of imports, ${m.latest_year}. ${esc(r.home_name)} highlighted.</p><div class="plot" id="c-sup"></div></div>
      <div class="card chart-card"><h3>${esc(m.share_label)}</h3><p class="cap">Share of total imports, %</p><div class="plot" id="c-share"></div></div>
      ${(m.momentum.gainers.length || m.momentum.losers.length) ? `<div class="card chart-card"><h3>Who is gaining share</h3><p class="cap">Change in market share since ${m.years[0]}, percentage points (suppliers with ≥1% share)</p><div class="plot" id="c-mom"></div></div>` : ""}
      <div class="card chart-card"><h3>Score breakdown</h3><p class="cap">Sub-scores out of 10, with weights</p><div class="plot" id="c-score"></div></div>
      <div class="card chart-card"><h3>Does the verdict depend on the weights?</h3><p class="cap">${m.sensitivity.robust
        ? `Robust: ${m.sensitivity.min}–${m.sensitivity.max} across six weighting schemes, same verdict band`
        : `Borderline: ${m.sensitivity.min}–${m.sensitivity.max} across six schemes, crossing a verdict threshold`}</p><div class="plot" id="c-sens"></div></div>
      <div class="card chart-card"><h3>Your starting position: ${esc(r.home_name)}</h3><p class="cap">Share, rank and price level in this market, ${m.latest_year}</p>
        <div class="pos">${positionHtml(r, m)}</div></div>
      ${m.ranking.length ? `<div class="card chart-card wide"><h3>Where to start in the EU</h3><p class="cap">Entry attractiveness by member state (0-10): demand, growth, purchasing power, logistics, institutions</p>
        <div class="map-split"><div class="plot" id="c-map"></div><div class="table-wrap"><table><thead><tr><th>#</th><th>Country</th><th class="num">Imports</th><th class="num">CAGR</th><th class="num">Score</th></tr></thead>
        <tbody>${m.ranking.slice(0, 8).map((x) => `<tr><td>${x.rank}</td><td>${esc(x.name)}</td><td class="num">${money(x.imports, "EUR")}</td><td class="num">${signedPct(x.cagr)}</td><td class="num"><b>${x.score}</b></td></tr>`).join("")}</tbody></table></div></div></div>` : ""}
      <div class="card chart-card wide" id="calc"><h3>Landed-cost calculator</h3>
        <p class="cap">Duty prefilled from WITS: ${r.tariff.mfn != null ? `MFN ${r.tariff.mfn}% (${r.tariff.mfn_year})` : "MFN n/a"} · ${esc(r.tariff.basis)}. Edit any input.</p>
        <div class="calc">
          <form class="calc-in" id="calc-form">
            <label class="field"><span>Ex-works price per unit (${cur})</span><input type="number" name="price" value="100" min="0" step="any"></label>
            <label class="field"><span>Units per shipment</span><input type="number" name="units" value="1000" min="1" step="1"></label>
            <label class="field"><span>Freight &amp; insurance (%)</span><input type="number" name="freight" value="${r.cost.freight_pct}" min="0" step="0.5"></label>
            <label class="field"><span>Import duty (%)</span><input type="number" name="duty" value="${r.cost.duty_pct}" min="0" step="0.1"></label>
            ${st.t === "EU" && cat.vat ? `<label class="field"><span>Destination member state</span><select name="dest" aria-label="Destination member state">${Object.entries(cat.vat).filter(([c]) => c !== "CN")
              .map(([c, x]) => `<option value="${c}" data-rate="${x.rate}" ${x.name === r.cost.vat_country ? "selected" : ""}>${esc(x.name)} · VAT ${x.rate}%</option>`).join("")}</select></label>` : ""}
            <label class="field"><span>Import VAT (%)${st.t === "EU" ? "" : ` · ${esc(r.cost.vat_country)}`}</span><input type="number" name="vat" value="${r.cost.vat_pct}" min="0" step="0.5"></label>
            <label class="field"><span>Clearance &amp; fees (%)</span><input type="number" name="other" value="${r.cost.other_pct}" min="0" step="0.5"></label>
            <label class="field" style="grid-column:1/-1"><span>Anti-dumping / countervailing duty (%)${r.tariff.trade_defence ? " · check the trade-policy note" : ""}</span><input type="number" name="td" value="0" min="0" step="0.1"></label>
          </form>
          <div class="calc-out" aria-live="polite" id="calc-out"></div>
        </div></div>
      <div class="card chart-card ${m.ranking.length ? "" : "wide"}"><h3>CAGE distance: ${esc(r.home_name)} → ${esc(tName)}</h3><p class="cap">Ghemawat's four dimensions · ${r.distance_km.toLocaleString("en")} km between capitals</p>
        <div class="cage">${Object.entries(r.cage_dims).map(([k, v]) => `<div><span>${esc(k)}</span><b class="lvl-${esc(v)}">${esc(v)}</b></div>`).join("")}</div></div>
      <div class="card chart-card ${m.ranking.length ? "" : "wide"}"><h3>Risk register</h3><p class="cap">${r.risks.length} risks flagged · full matrix and mitigations in the report</p>
        <div class="table-wrap"><table><thead><tr><th>Risk</th><th>Likelihood</th><th>Impact</th></tr></thead><tbody>
        ${r.risks.map((x) => `<tr><td>${esc(x.risk)}</td><td class="lvl-${x.likelihood}"><b>${x.likelihood}</b></td><td class="lvl-${x.impact}"><b>${x.impact}</b></td></tr>`).join("")}</tbody></table></div></div>
    </div>

    <div class="r-body">
      <nav class="toc" aria-label="Report sections"><b>Report contents</b><div id="toc"></div></nav>
      <article class="card article" id="article">${r.html}</article>
    </div>`;

    // Article: wrap tables, build table of contents.
    $$("#article table").forEach((t) => { const w = document.createElement("div"); w.className = "table-wrap"; t.replaceWith(w); w.appendChild(t); });
    const heads = $$("#article h2");
    heads.forEach((h, i) => { h.id = `sec-${i + 1}`; });
    $("#toc").innerHTML = heads.map((h) => `<a href="#${h.id}">${esc(h.textContent)}</a>`).join("");
    const links = $$("#toc a");
    const spy = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === `#${e.target.id}`));
      });
    }, { rootMargin: "-140px 0px -70% 0px" });
    heads.forEach((h) => spy.observe(h));

    $("#print").addEventListener("click", () => window.print());
    $("#csv").addEventListener("click", () => downloadCsv(m, r, product, tName));
    $("#copy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(location.href); toast("Link copied"); } catch (e) { toast(location.href); }
    });

    const form = $("#calc-form");
    const calc = () => {
      const v = Object.fromEntries([...new FormData(form)].filter(([k]) => k !== "dest").map(([k, x]) => [k, Math.max(0, parseFloat(x) || 0)]));
      const goods = v.price, freight = goods * v.freight / 100, cif = goods + freight, duty = cif * (v.duty + v.td) / 100;
      const other = goods * v.other / 100, vat = (cif + duty) * v.vat / 100, exVat = cif + duty + other, total = exVat + vat;
      const f = (x) => x.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const sym = cur === "EUR" ? "€" : "$";
      const rows = [["Goods (ex-works)", goods], ["Freight & insurance", freight], [v.td ? "Import duty incl. trade defence" : "Import duty", duty], ["Clearance & fees", other], ["Import VAT", vat]];
      $("#calc-out").innerHTML = `
        <div class="calc-big"><span>Landed cost per unit</span><b>${sym}${f(total)}</b><small>${sym}${f(exVat)} before VAT · ${signedPct(goods ? (exVat / goods - 1) * 100 : 0)} on ex-works</small></div>
        <div class="stack" role="img" aria-label="Cost build-up">${rows.map(([k, x], i) => `<i class="s${i}" style="width:${total ? (x / total) * 100 : 0}%" title="${k}"></i>`).join("")}</div>
        <table><tbody>${rows.map(([k, x], i) => `<tr><td><span class="dot s${i}"></span>${k}</td><td class="num">${sym}${f(x)}</td></tr>`).join("")}
          <tr><td><b>Per shipment (${v.units.toLocaleString("en")} units)</b></td><td class="num"><b>${money(total * v.units, cur)}</b></td></tr></tbody></table>
        <p class="muted" style="font-size:12.5px;margin:6px 0 0">Duty and VAT on the CIF value (EU and Chinese customs practice). Import VAT is usually recoverable for registered importers. Excise and consumption taxes are not included.</p>`;
    };
    if (form.dest) form.dest.addEventListener("change", () => { form.vat.value = form.dest.selectedOptions[0].dataset.rate; calc(); });
    form.addEventListener("input", calc);
    calc();

    const draw = () => drawCharts(m, r);
    if (window.Plotly) draw(); else window.addEventListener("load", draw);
    window.addEventListener("themechange", draw);
  }

  function compareUrl() { // this case vs the same product in the other market (same home if offered there)
    const other = st.t === "EU" ? "CN" : "EU";
    const homes = cat.targets[other].homes.map((h) => h.code);
    const h = homes.includes(st.h) ? st.h : homes[0];
    const k = (x) => `${x.p}-${x.t}-${x.h}-${x.s}`;
    return `compare.html?c=${k(st)},${k({ p: st.p, t: other, h, s: st.s })}`;
  }

  function downloadCsv(m, r, product, tName) {
    const q = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
    const rows = [["section", "item", "value", "detail"]];
    const add = (...cells) => rows.push(cells);
    add("case", "product", product.label, `HS ${m.hs}`); add("case", "target", tName, ""); add("case", "home", r.home_name, r.size);
    add("verdict", "verdict", r.verdict, r.mode); add("verdict", "score_0_10", r.score, "");
    Object.entries(m.score.sub_scores).forEach(([k, v]) => add("score", k, v, `weight ${m.score.weights[k]}`));
    m.years.forEach((y, i) => add("market_size", y, m.sizes[i], m.currency));
    add("market", "growth_trend_pct", m.growth, `confidence ${m.quality.confidence}`); add("market", "hhi", m.hhi, m.hhi_label);
    m.suppliers.forEach((s) => add("supplier", s.name, s.share, `value ${s.value}; unit value/kg ${s.uv ?? ""}`));
    [...m.momentum.gainers, ...m.momentum.losers].forEach((x) => add("momentum_pp", x.name, x.change_pp, `${x.share_first}% -> ${x.share_last}%`));
    add("tariff", "mfn_pct", r.tariff.mfn, r.tariff.mfn_year); add("tariff", "applicable_pct", r.tariff.applicable, r.tariff.basis);
    Object.entries(r.cost).forEach(([k, v]) => add("landed_cost_assumption", k, v, ""));
    r.risks.forEach((x) => add("risk", x.risk, x.likelihood, `impact ${x.impact}`));
    m.ranking.forEach((x) => add("eu_ranking", x.name, x.score, `rank ${x.rank}; imports ${x.imports}`));
    const blob = new Blob(["\ufeff" + rows.map((row) => row.map(q).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${product.label.replace(/[^A-Za-z0-9]+/g, "-")}-${st.t}-${st.h}-${st.s}.csv`.toLowerCase();
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast("CSV downloaded");
  }

  function positionHtml(r, m) {
    const p = r.position || {};
    const sym = m.currency === "EUR" ? "€" : "$";
    const uv = (x) => (x ? `${sym}${Number(x).toFixed(2)}/kg` : "n/a");
    const items = [
      ["Supplier rank", p.present ? `#${p.rank} of ${p.suppliers}` : "Not a supplier yet"],
      ["Market share", p.present ? `${pct(p.share_pct)} <small class="${p.share_change_pp >= 0 ? "lvl-Low" : "lvl-High"}">${p.share_change_pp >= 0 ? "▲" : "▼"} ${Math.abs(p.share_change_pp).toFixed(1)} pp since ${p.first_year}</small>` : "–"],
      ["Price level", p.price_position ? `${p.price_position} <small>(${p.price_ratio}× market)</small>` : "n/a"],
      ["Unit value", `${uv(p.unit_value_per_kg)} <small>vs ${uv(m.unit_value)} avg</small>`],
      ["Applicable duty", r.tariff.applicable != null ? `${r.tariff.applicable}%` : "n/a"],
      ["Trade agreement", r.tariff.fta ? esc(r.tariff.fta) : "None"],
    ];
    return items.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");
  }

  function drawCharts(m, r) {
    if (!window.Plotly) return;
    const css = getComputedStyle(document.documentElement);
    const v = (n) => css.getPropertyValue(n).trim();
    const C = { text: v("--muted"), line: v("--line"), accent: v("--accent"), faint: v("--surface-2"), base: v("--faint") };
    const sym = m.currency === "EUR" ? "€" : "$";
    const base = {
      margin: { t: 8, r: 12, b: 36, l: 48 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Inter, -apple-system, Segoe UI, sans-serif", size: 12, color: C.text },
      xaxis: { gridcolor: C.line, linecolor: C.line, zeroline: false, fixedrange: true },
      yaxis: { gridcolor: C.line, linecolor: C.line, zeroline: false, fixedrange: true },
      hoverlabel: { font: { family: "Inter, sans-serif" } }, showlegend: false, bargap: 0.35,
    };
    const cfg = { displayModeBar: false, responsive: true };
    const L = (extra) => Object.assign(JSON.parse(JSON.stringify(base)), extra);

    const big = Math.max(...m.sizes) >= 1e9;
    const div = big ? 1e9 : 1e6, unit = big ? "bn" : "m";
    Plotly.react("c-size", [{
      type: "bar", x: m.years, y: m.sizes.map((x) => x / div), marker: { color: C.accent },
      hovertemplate: `%{x}: ${sym}%{y:,.${big ? 2 : 0}f}${unit}<extra></extra>`,
    }], L({ xaxis: { ...base.xaxis, type: "category", gridcolor: "rgba(0,0,0,0)" },
      yaxis: { ...base.yaxis, tickprefix: sym, ticksuffix: unit, tickformat: ",.1~f", automargin: true } }), cfg);

    const sup = m.suppliers.slice(0, 8).reverse();
    const isHome = (s) => s.code === r.home || s.name === r.home_name || (r.home === "KR" && /korea/i.test(s.name)) ||
      (r.home === "VN" && /viet/i.test(s.name)) || (r.home === "US" && /united states/i.test(s.name));
    Plotly.react("c-sup", [{
      type: "bar", orientation: "h", y: sup.map((s) => s.name.replace("Korea, Republic of", "South Korea")),
      x: sup.map((s) => s.share), marker: { color: sup.map((s) => (isHome(s) ? C.accent : C.base)) },
      text: sup.map((s) => `${s.share.toFixed(1)}%`), textposition: "outside", cliponaxis: false,
      customdata: sup.map((s) => (s.uv ? `${sym}${s.uv.toFixed(2)}/kg` : "n/a")),
      hovertemplate: "%{y}: %{x:.1f}% · unit value %{customdata}<extra></extra>",
    }], L({ margin: { t: 8, r: 44, b: 30, l: 120 }, xaxis: { ...base.xaxis, ticksuffix: "%" }, yaxis: { ...base.yaxis, gridcolor: "rgba(0,0,0,0)", automargin: true } }), cfg);

    const yrs = Object.keys(m.share);
    Plotly.react("c-share", [{
      type: "scatter", mode: "lines+markers", x: yrs, y: yrs.map((y) => m.share[y]), line: { color: C.accent, width: 3 },
      marker: { size: 7 }, fill: "tozeroy", fillcolor: C.accent + "22", hovertemplate: "%{x}: %{y:.1f}%<extra></extra>",
    }], L({ xaxis: { ...base.xaxis, type: "category", gridcolor: "rgba(0,0,0,0)" }, yaxis: { ...base.yaxis, ticksuffix: "%", range: [0, Math.min(100, Math.max(...yrs.map((y) => m.share[y] || 0)) * 1.15 + 2)] } }), cfg);

    const names = { market_size: "Market size", growth: "Growth", competitive_openness: "Openness", institutional_quality: "Institutions", logistics: "Logistics" };
    const keys = Object.keys(m.score.sub_scores).reverse();
    Plotly.react("c-score", [
      { type: "bar", orientation: "h", y: keys.map((k) => `${names[k] || k} (${Math.round(m.score.weights[k] * 100)}%)`),
        x: keys.map(() => 10), marker: { color: C.faint }, hoverinfo: "skip" },
      { type: "bar", orientation: "h", y: keys.map((k) => `${names[k] || k} (${Math.round(m.score.weights[k] * 100)}%)`),
        x: keys.map((k) => m.score.sub_scores[k]), marker: { color: C.accent }, text: keys.map((k) => Number(m.score.sub_scores[k]).toFixed(1)),
        textposition: "outside", cliponaxis: false, hovertemplate: "%{y}: %{x:.1f}/10<extra></extra>" },
    ], L({ barmode: "overlay", margin: { t: 8, r: 36, b: 30, l: 140 }, xaxis: { ...base.xaxis, range: [0, 10.5] }, yaxis: { ...base.yaxis, gridcolor: "rgba(0,0,0,0)", automargin: true } }), cfg);

    if (document.getElementById("c-mom")) {
      const mv = [...m.momentum.gainers, ...m.momentum.losers].sort((a, b) => a.change_pp - b.change_pp);
      Plotly.react("c-mom", [{
        type: "bar", orientation: "h", y: mv.map((x) => x.name), x: mv.map((x) => x.change_pp),
        marker: { color: mv.map((x) => (x.partner === r.home ? C.accent : x.change_pp >= 0 ? v("--warn") : C.base)) },
        text: mv.map((x) => `${x.change_pp > 0 ? "+" : ""}${x.change_pp.toFixed(1)} pp`), textposition: "outside", cliponaxis: false,
        customdata: mv.map((x) => `${x.share_first}% → ${x.share_last}%`), hovertemplate: "%{y}: %{customdata}<extra></extra>",
      }], L({ margin: { t: 8, r: 60, b: 30, l: 120 }, xaxis: { ...base.xaxis, ticksuffix: " pp", zeroline: true, zerolinecolor: C.text },
        yaxis: { ...base.yaxis, gridcolor: "rgba(0,0,0,0)", automargin: true } }), cfg);
    }
    const sc = m.sensitivity.scenarios.slice().reverse();
    const band = (x) => (x >= 6.5 ? v("--ok") : x >= 5 ? v("--warn") : v("--bad"));
    Plotly.react("c-sens", [{
      type: "bar", orientation: "h", y: sc.map((x) => x.scenario), x: sc.map((x) => x.score), marker: { color: sc.map((x) => band(x.score)) },
      text: sc.map((x) => x.score.toFixed(1)), textposition: "outside", cliponaxis: false, hovertemplate: "%{y}: %{x:.1f}/10<extra></extra>",
    }], L({ margin: { t: 8, r: 36, b: 30, l: 190 }, xaxis: { ...base.xaxis, range: [0, 10.5] }, yaxis: { ...base.yaxis, gridcolor: "rgba(0,0,0,0)", automargin: true },
      shapes: [5, 6.5].map((x0) => ({ type: "line", x0, x1: x0, y0: -0.5, y1: sc.length - 0.5, line: { color: C.text, width: 1, dash: "dot" } })) }), cfg);

    // Text alternatives for screen readers.
    const alt = {
      "c-size": `Bar chart: imports grew from ${money(m.sizes[0], m.currency)} in ${m.years[0]} to ${money(m.latest_size, m.currency)} in ${m.latest_year}.`,
      "c-sup": `Bar chart of supplier shares: ${m.suppliers.slice(0, 3).map((s) => `${s.name} ${s.share}%`).join(", ")}.`,
      "c-share": `Line chart: ${m.share_label} by year.`,
      "c-score": `Score components: ${Object.entries(m.score.sub_scores).map(([k, x]) => `${k.replace(/_/g, " ")} ${x}`).join(", ")}.`,
      "c-mom": `Share change since ${m.years[0]}: ${[...m.momentum.gainers, ...m.momentum.losers].slice(0, 4).map((x) => `${x.name} ${x.change_pp > 0 ? "+" : ""}${x.change_pp} pp`).join(", ")}.`,
      "c-sens": `Scores under six weighting schemes range from ${m.sensitivity.min} to ${m.sensitivity.max}.`,
      "c-map": m.ranking.length ? `Map of EU member states by entry score; top three: ${m.ranking.slice(0, 3).map((x) => x.name).join(", ")}.` : "",
    };
    Object.entries(alt).forEach(([id, label]) => { const el = document.getElementById(id); if (el && label) { el.setAttribute("role", "img"); el.setAttribute("aria-label", label); } });

    if (m.ranking.length) {
      Plotly.react("c-map", [{
        type: "choropleth", locations: m.ranking.map((x) => x.iso3), z: m.ranking.map((x) => x.score), text: m.ranking.map((x) => x.name),
        colorscale: [[0, C.faint], [1, C.accent]], marker: { line: { color: v("--surface"), width: 0.6 } },
        colorbar: { thickness: 10, len: 0.7, outlinewidth: 0, tickfont: { color: C.text } },
        hovertemplate: "%{text}<br>Score %{z:.1f}/10<extra></extra>",
      }], L({ margin: { t: 0, r: 0, b: 0, l: 0 }, dragmode: false,
        geo: { scope: "europe", fitbounds: "locations", visible: false, showcountries: false, bgcolor: "rgba(0,0,0,0)", projection: { type: "mercator" } } }), cfg);
    }
  }
})();
