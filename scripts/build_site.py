"""
Build the static showcase website (docs/) published on GitHub Pages.

It runs the real report engine on a curated set of EU-China market entry
cases with live public data, and writes one HTML page per case plus a
landing page. Run:  python scripts/build_site.py
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path

import markdown as md
import plotly.express as px
from plotly.offline import get_plotlyjs_version

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import knowledge as kb  # noqa: E402
from src.report_engine import generate_report  # noqa: E402

DOCS = ROOT / "docs"
REPORTS = DOCS / "reports"
REPO_URL = "https://github.com/onurusalan/ai-market-entry-analyst"

END = date.today().year - 2
START = END - 5

CASES = [
    # slug, hs, target, home, company, size, label, emoji
    ("ebikes-taiwan-to-eu", "871160", "EU", "TW", "Taiwanese e-bike manufacturer", "medium", "E-bikes", "🚲"),
    ("evs-china-to-eu", "870380", "EU", "CN", "Chinese EV maker", "large", "Battery-electric cars", "🚗"),
    ("skincare-france-to-china", "330499", "CN", "FR", "French premium skincare brand", "small", "Skincare", "🧴"),
    ("wine-italy-to-china", "220421", "CN", "IT", "Italian wine cooperative", "medium", "Bottled wine", "🍷"),
    ("medicines-germany-to-china", "300490", "CN", "DE", "German pharmaceutical company", "large", "Medicaments", "💊"),
    ("batteries-korea-to-eu", "850760", "EU", "KR", "Korean battery-cell producer", "large", "Lithium-ion batteries", "🔋"),
    ("heatpumps-japan-to-eu", "841861", "EU", "JP", "Japanese HVAC manufacturer", "large", "Heat pumps", "🌡️"),
    ("furniture-vietnam-to-eu", "940360", "EU", "VN", "Vietnamese furniture exporter", "small", "Wooden furniture", "🪑"),
]

CSS = """
:root{--bg:#f7f8fb;--card:#fff;--text:#14161a;--muted:#5b6270;--line:#e3e6ec;--accent:#0b5fff;--accent-soft:#e8efff;
--ok:#0f9d58;--warn:#d98e04;--bad:#d93025}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--text:#eef0f4;--muted:#a3aab8;--line:#2a2f3a;
--accent:#6c9bff;--accent-soft:#1c2740}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font-family:Inter,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.6}
a{color:var(--accent)}.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
header.top{border-bottom:1px solid var(--line);background:var(--card)}
header.top .wrap{display:flex;justify-content:space-between;align-items:center;height:60px}
.brand{font-weight:700;text-decoration:none;color:var(--text)}.nav a{margin-left:18px;text-decoration:none;color:var(--muted)}
.hero{padding:64px 0 40px}.hero h1{font-size:clamp(28px,5vw,48px);line-height:1.15;margin:0 0 16px}
.hero p{font-size:18px;color:var(--muted);max-width:720px}.pill{display:inline-block;background:var(--accent-soft);
color:var(--accent);padding:4px 12px;border-radius:999px;font-size:13px;font-weight:600;margin-bottom:16px}
.btn{display:inline-block;background:var(--accent);color:#fff;padding:12px 20px;border-radius:10px;text-decoration:none;
font-weight:600;margin:8px 8px 0 0}.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}
.card h3{margin:0 0 6px;font-size:17px}.card p{margin:0;color:var(--muted);font-size:14px}
a.card{text-decoration:none;color:inherit;transition:transform .15s,border-color .15s}a.card:hover{transform:translateY(-2px);border-color:var(--accent)}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:2px 8px;border-radius:6px;margin-top:10px}
.tag.ENTER{background:#e6f4ea;color:var(--ok)}.tag.CAUTION{background:#fef3e0;color:var(--warn)}.tag.DONOT{background:#fde8e7;color:var(--bad)}
section{padding:32px 0}h2.sec{font-size:26px;margin:0 0 18px}
.steps{counter-reset:s}.steps .card h3:before{counter-increment:s;content:counter(s) ". ";color:var(--accent)}
footer{border-top:1px solid var(--line);padding:24px 0;color:var(--muted);font-size:14px;margin-top:40px}
.report{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:clamp(16px,4vw,40px);margin:24px 0}
.report table{border-collapse:collapse;width:100%;display:block;overflow-x:auto;font-size:14px}
.report td,.report th{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
.report th{background:var(--accent-soft)}.report h1{font-size:clamp(22px,4vw,32px);line-height:1.2}
.report h2{border-bottom:2px solid var(--accent);padding-bottom:4px;margin-top:36px}
.report blockquote{background:#fff7e6;color:#5a3d00;border-left:4px solid var(--warn);margin:0;padding:10px 14px;border-radius:6px}
.kpis{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));margin:16px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.kpi b{display:block;font-size:22px}.kpi span{color:var(--muted);font-size:13px}
.charts{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
@media (max-width:560px){.nav a:nth-child(2){display:none}.nav a{margin-left:12px;font-size:14px}.brand{font-size:15px}}
.chart{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:8px;min-width:0}
"""


def page(title: str, body: str, depth: int = 0, charts: bool = False) -> str:
    up = "../" * depth
    plotly_tag = (f'<script src="https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js" charset="utf-8"></script>'
                  if charts else "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="Data-driven market entry analysis for the EU and Chinese markets.">
<style>{CSS}</style>{plotly_tag}</head><body>
<header class="top"><div class="wrap"><a class="brand" href="{up}index.html">🌍 Market Entry Analyst</a>
<nav class="nav"><a href="{up}index.html#cases">Case studies</a><a href="{up}index.html#how">How it works</a>
<a href="{REPO_URL}">GitHub</a></nav></div></header>
{body}
<footer><div class="wrap">Built by Onur Usalan · MSc International Business · BSc Management Information Systems ·
Data: Eurostat, UN Comtrade, World Bank · Updated {date.today().isoformat()} ·
<a href="{REPO_URL}">Source code</a></div></footer></body></html>"""


def chart_html(fig) -> str:
    fig.update_layout(margin=dict(t=48, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#7d8696"))
    fig.update_layout(autosize=True, height=None)
    return '<div class="chart">' + fig.to_html(full_html=False, include_plotlyjs=False,
                                                default_width="100%", default_height="340px",
                                                config={"displayModeBar": False, "responsive": True}) + "</div>"


def verdict_class(v: str) -> str:
    return {"ENTER": "ENTER", "ENTER WITH CAUTION": "CAUTION"}.get(v, "DONOT")


def build_case(case) -> dict | None:
    slug, hs, target, home, company, size, label, emoji = case
    print(f"→ {slug}")
    try:
        rep = generate_report(hs, target, home, company, size, START, END, label)
    except Exception as exc:  # keep building the other cases
        print(f"   skipped: {exc}")
        return None
    m, d = rep.data["market"], rep.data
    cur = m["currency"]
    sym = "€" if cur == "EUR" else "$"

    charts = []
    years = list(m["import_market_size_by_year"].keys())
    vals = [v / 1e6 for v in m["import_market_size_by_year"].values()]
    charts.append(chart_html(px.bar(x=years, y=vals, labels={"x": "", "y": f"{sym} m"},
                                    title=f"Import market size ({cur} m)", color_discrete_sequence=["#0b5fff"])))
    sup = m["top_suppliers_latest_year"][:8][::-1]
    charts.append(chart_html(px.bar(x=[s["share_pct"] for s in sup], y=[s["partner_name"] for s in sup],
                                    orientation="h", labels={"x": "share %", "y": ""},
                                    title=f"Top suppliers {m['latest_year']} (share %)",
                                    color_discrete_sequence=["#0b5fff"])))
    if d["ranking"]:
        iso3 = {"AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK",
                "EE": "EST", "ES": "ESP", "FI": "FIN", "FR": "FRA", "GR": "GRC", "HR": "HRV", "HU": "HUN",
                "IE": "IRL", "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT", "NL": "NLD",
                "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE", "SI": "SVN", "SK": "SVK"}
        fig = px.choropleth(locations=[iso3[r["member"]] for r in d["ranking"]],
                            color=[r["score_0_10"] for r in d["ranking"]],
                            hover_name=[kb.COUNTRIES[r["member"]]["name"] for r in d["ranking"]],
                            color_continuous_scale="Blues", title="EU-27 entry attractiveness (0-10)",
                            labels={"color": "score"})
        fig.update_geos(fitbounds="locations", visible=False, showcountries=True, bgcolor="rgba(0,0,0,0)")
        charts.append(chart_html(fig))

    share = m.get("china_share_pct_by_year") or m.get("eu27_share_pct_by_year") or {}
    share_label = "China's share of EU imports" if "china_share_pct_by_year" in m else "EU-27 share of China's imports"
    kpis = [
        (d["verdict"].title(), "Verdict"),
        (f"{d['score']['score_0_10']}/10", "Attractiveness"),
        (f"{sym}{m['latest_market_size'] / 1e6:,.0f} m", f"Import market {m['latest_year']}"),
        (f"{share.get(m['latest_year'], '–')}%", share_label),
        (d["cage"]["overall_label"], "CAGE distance"),
    ]
    kpi_html = "".join(f'<div class="kpi"><b>{html.escape(str(a))}</b><span>{html.escape(b)}</span></div>' for a, b in kpis)
    body = f"""<main class="wrap">
<p style="margin-top:24px"><a href="../index.html#cases">← All case studies</a></p>
<div class="kpis">{kpi_html}</div>
<div class="charts">{''.join(charts)}</div>
<article class="report">{md.markdown(rep.markdown, extensions=['tables'])}</article>
</main>
<script>window.addEventListener("load",function(){{document.querySelectorAll(".js-plotly-plot")
.forEach(function(el){{Plotly.Plots.resize(el);}});}});</script>"""
    (REPORTS / f"{slug}.html").write_text(page(rep.title, body, depth=1, charts=True))
    return {"slug": slug, "emoji": emoji, "label": label, "home": kb.COUNTRIES[home]["name"],
            "target": "EU-27" if target == "EU" else kb.COUNTRIES[target]["name"],
            "verdict": d["verdict"], "score": d["score"]["score_0_10"], "mode": d["entry_mode"]["mode"]}


def build_index(cards: list[dict]) -> None:
    case_cards = "".join(
        f'<a class="card" href="reports/{c["slug"]}.html"><h3>{c["emoji"]} {html.escape(c["label"])}</h3>'
        f'<p>{html.escape(c["home"])} → {html.escape(c["target"])}</p>'
        f'<p style="margin-top:8px">{html.escape(c["mode"])}</p>'
        f'<span class="tag {verdict_class(c["verdict"])}">{c["verdict"]} · {c["score"]}/10</span></a>'
        for c in cards)
    features = [
        ("📊 Live official data", "Eurostat Comext, UN Comtrade and World Bank APIs; no estimates or invented numbers."),
        ("📈 Supply concentration", "Herfindahl-Hirschman Index shows dependency on dominant suppliers such as China."),
        ("🎯 Transparent scoring", "A 0-10 attractiveness score from size, growth, openness, institutions and logistics."),
        ("🧭 IB frameworks", "PESTEL, CAGE distance, risk matrix and OLI-based entry-mode logic, built into code."),
        ("🇪🇺 EU-27 ranking", "Ranks all member states to pick the best first markets."),
        ("🤖 Optional AI agent", "A Claude tool-use agent can add live web research on tariffs and regulation."),
    ]
    feat = "".join(f'<div class="card"><h3>{a}</h3><p>{b}</p></div>' for a, b in features)
    steps = [
        ("Describe the case", "Product (HS6 code), target market (EU, a member state or China), home country and company size."),
        ("Pull live data", "Trade flows, supplier shares, macro, logistics and governance indicators."),
        ("Analyse", "Market size and growth, HHI, attractiveness score, CAGE distance, EU-27 ranking."),
        ("Decide", "Verdict, PESTEL, regulation checklist, risk matrix, entry mode and a 90-day plan."),
    ]
    step_html = "".join(f'<div class="card"><h3>{a}</h3><p>{b}</p></div>' for a, b in steps)
    body = f"""<main class="wrap">
<section class="hero"><span class="pill">EU ⇄ China · International Business × Data</span>
<h1>Market entry decisions, backed by official trade data.</h1>
<p>An analytics platform that turns Eurostat, UN Comtrade and World Bank data into consulting-style market entry
reports for the EU and Chinese markets: verdict, PESTEL, CAGE distance, risk matrix and entry-mode recommendation.</p>
<a class="btn" href="#cases">See case studies</a><a class="btn ghost" href="{REPO_URL}">View source on GitHub</a></section>
<section id="cases"><h2 class="sec">Case studies (generated from live data)</h2><div class="grid">{case_cards}</div></section>
<section><h2 class="sec">What it does</h2><div class="grid">{feat}</div></section>
<section id="how"><h2 class="sec">How it works</h2><div class="grid steps">{step_html}</div>
<p style="color:var(--muted);margin-top:16px">Run the interactive app (dashboard, custom reports, EU-27 ranking) locally
with <code>streamlit run app.py</code>; see the <a href="{REPO_URL}#-quick-start">quick start</a>.</p></section>
</main>"""
    (DOCS / "index.html").write_text(page("Market Entry Analyst: EU ⇄ China", body))


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    cards = [c for c in (build_case(case) for case in CASES) if c]
    build_index(cards)
    (DOCS / ".nojekyll").write_text("")
    (DOCS / "cases.json").write_text(json.dumps(cards, indent=2, ensure_ascii=False))
    print(f"Built {len(cards)} case pages into {DOCS}")


if __name__ == "__main__":
    main()
