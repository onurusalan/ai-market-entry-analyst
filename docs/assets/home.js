/* Home page: analyzer card, stats and featured case studies. */
(async function () {
  Theme.init();
  let cat;
  try { cat = await getJSON("data/catalog.json"); } catch (e) {
    $("#analyzer").innerHTML = '<p class="muted">Could not load the data catalogue. Please refresh.</p>';
    return;
  }

  const form = $("#analyzer");
  const first = cat.featured[0] || {};
  const head = '<div><h2>Generate an entry report</h2><p class="sub">Choose a case. The report opens instantly.</p></div>';
  buildPicker(form, cat, { p: first.hs, t: first.target, h: first.home, s: first.size }, {
    variant: "card", onSubmit: (s) => { location.href = reportUrl(s); },
  });
  form.insertAdjacentHTML("afterbegin", head);
  form.insertAdjacentHTML("beforeend",
    `<p class="foot">${cat.report_count} pre-computed reports · refreshed monthly from live data</p>`);

  $("#st-products").textContent = cat.products.length;
  $("#st-reports").textContent = cat.report_count.toLocaleString("en");
  $("#st-years").textContent = `${cat.years[0]}–${cat.years[1]}`;
  $("#updated").textContent = cat.updated;

  $("#case-grid").innerHTML = cat.featured.map((c) => `
    <a class="card case" href="${reportUrl({ p: c.hs, t: c.target, h: c.home, s: c.size })}">
      <div class="row"><span class="ico">${c.icon}</span><span class="badge ${verdictClass(c.verdict)}">${verdictText(c.verdict)}</span></div>
      <div><div class="route">${esc(c.home_name)} → ${esc(c.target_name)}</div><h3>${esc(c.label)}</h3></div>
      <p>${esc(c.headline)}</p>
      <div><div class="row" style="font-size:13px;margin-bottom:6px"><span class="muted">Attractiveness</span><b>${Number(c.score).toFixed(1)}/10</b></div>
        <div class="scorebar"><i style="width:${c.score * 10}%"></i></div></div>
      <div class="metrics"><span>Market ${c.year}<br><b>${money(c.market, c.currency)}</b></span>
        <span style="text-align:right">Growth (trend)<br><b>${signedPct(c.cagr)}</b></span></div>
    </a>`).join("");

  try {
    const bt = await getJSON("data/backtest.json");
    if (bt.length) {
      $("#bt-t0").textContent = bt[0].ranked_with[1];
      const fmt = (x) => (x == null ? "–" : x.toFixed(2));
      $("#bt-table tbody").innerHTML = bt.map((b) => `<tr><td>${b.icon} ${esc(b.label)}</td><td class="num"><b>${fmt(b.spearman_vs_gain)}</b></td>
        <td class="num">${fmt(b.spearman_vs_growth)}</td><td class="num">${b.top5_hits}/5</td></tr>`).join("");
      const avg = (k) => bt.reduce((a, b) => a + (b[k] || 0), 0) / bt.length;
      const hits = bt.reduce((a, b) => a + b.top5_hits, 0);
      $("#bt-summary").innerHTML = `Ranked with ${bt[0].ranked_with[0]}–${bt[0].ranked_with[1]} data, evaluated on ${bt[0].evaluated[0]}–${bt[0].evaluated[1]}.
        Average rank correlation with <b>new demand (absolute import gain): ${avg("spearman_vs_gain").toFixed(2)}</b>; ${hits} of ${bt.length * 5} predicted top-5 markets were among the actual top-5.
        Correlation with the <b>growth rate is negative (${avg("spearman_vs_growth").toFixed(2)})</b>: small, fast-growing markets tend to cool down, so the ranking is a guide to where demand volume will be, not to the fastest growth.
        Caveat: country fundamentals use current values.`;
    }
  } catch (e) { $("#validation").hidden = true; }
})();
