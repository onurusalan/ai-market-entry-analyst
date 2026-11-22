"""
AI Market Entry Analyst: EU <-> China
Streamlit web app. Run with:  streamlit run app.py

Everything works for free with public data. Claude AI narrative is optional
(bring your own API key).
"""

from __future__ import annotations

import os
from datetime import date

import markdown as md
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from src import analysis, catalog
from src import knowledge as kb
from src.report_engine import COMPANY_SIZES, generate_report, landed_cost
from src.viz import eu_tile_map

load_dotenv()

st.set_page_config(page_title="Market Entry Analyst", page_icon="🌍", layout="wide")

ACCENT = "#2457f5"
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [ACCENT, "#0b2545", "#8a93a3", "#6c9bff", "#b8c4d9"]

st.markdown("""
<style>
html, body, [class*="css"], .stMarkdown, .stTextInput, .stSelectbox, button { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Arial, sans-serif !important; }
.block-container { padding-top: 1.6rem; max-width: 1240px; }
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; }
.app-hero { background: linear-gradient(135deg, #0b2545 0%, #1a3fb8 100%); color: #fff; border-radius: 16px;
  padding: 26px 30px; margin-bottom: 18px; }
.app-hero h1 { color: #fff; font-size: 28px; margin: 0 0 4px; letter-spacing: -.02em; padding: 0; }
.app-hero p { margin: 0; opacity: .82; font-size: 15px; }
.app-hero .tags { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.app-hero .tags span { background: rgba(255,255,255,.14); padding: 3px 10px; border-radius: 999px; font-size: 12.5px; font-weight: 600; }
[data-testid="stMetric"] { background: #fff; border: 1px solid #e3e7ed; border-radius: 12px; padding: 14px 16px;
  box-shadow: 0 1px 2px rgba(16,24,40,.04); }
[data-testid="stMetricLabel"] p { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: #5a6474; }
[data-testid="stMetricValue"] { font-size: clamp(18px, 1.8vw, 26px); font-weight: 700; letter-spacing: -.02em; }
[data-testid="stMetricValue"] > div { white-space: normal; overflow: visible; text-overflow: clip; }
[data-testid="stAppDeployButton"], .stDeployButton { display: none; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #e3e7ed; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: 10px 16px; }
[data-testid="stForm"] { background: #fff; border: 1px solid #e3e7ed; border-radius: 14px; padding: 18px 20px; }
[data-testid="stPlotlyChart"] { background: #fff; border-radius: 14px; box-shadow: 0 0 0 1px #e3e7ed; overflow: hidden; }
.stMarkdown table { border-collapse: collapse; font-size: 14px; }
.stMarkdown th { background: #f0f3f7; text-transform: uppercase; font-size: 12px; letter-spacing: .04em; color: #5a6474; }
.stMarkdown h2 { border-bottom: 2px solid #2457f5; padding-bottom: 4px; margin-top: 28px; }
section[data-testid="stSidebar"] { background: #0b2545; }
section[data-testid="stSidebar"] * { color: #e8ecf3 !important; }
section[data-testid="stSidebar"] input { color: #0e1726 !important; }
</style>
<div class="app-hero"><h1>Market Entry Analyst · EU ⇄ China</h1>
<p>Official trade data plus International Business frameworks, turned into a market entry decision.</p>
<div class="tags"><span>Eurostat Comext</span><span>UN Comtrade</span><span>World Bank</span><span>PESTEL · CAGE · HHI · OLI</span></div></div>
""", unsafe_allow_html=True)

PRESETS = {f"{label} ({hs})": hs for hs, label, _ in catalog.PRODUCTS}
PRESETS["Custom HS6 code…"] = ""

EU_ISO3 = catalog.EU_ISO3
HOME_COUNTRIES = {f"{v['name']} ({k})": k for k, v in sorted(kb.COUNTRIES.items(), key=lambda kv: kv[1]["name"])
                  if k != "EU"}
LAST_FULL_YEAR = date.today().year - 2  # annual trade data lags about one year


def fmt_money(v: float | None, cur: str) -> str:
    if v is None:
        return "–"
    sym = "€" if cur == "EUR" else "$"
    for div, suf in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if abs(v) >= div:
            return f"{sym}{v / div:,.2f}{suf}"
    return f"{sym}{v:,.0f}"


def name(iso2: str) -> str:
    return kb.COUNTRIES.get(iso2, {}).get("name", iso2)


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def load_market(target: str, hs: str, start: int, end: int) -> dict:
    if target == "CN":
        return analysis.analyze_china_market(hs, start, end)
    return analysis.analyze_eu_market(hs, start, end, target)


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def load_profile(iso2: str) -> dict | None:
    return analysis.profile_for(iso2)


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def load_ranking(hs: str, start: int, end: int) -> list[dict]:
    return analysis.rank_eu_members(hs, start, end)


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def load_report(hs, target, home, company, size, start, end, label):
    r = generate_report(hs, target, home, company, size, start, end, label)
    return r.title, r.markdown, r.data


def product_picker(key: str, default: str = "E-bikes (871160)") -> tuple[str, str]:
    preset = st.selectbox("Product", list(PRESETS.keys()), index=list(PRESETS).index(default), key=f"p_{key}")
    hs = PRESETS[preset]
    if not hs:
        hs = st.text_input("HS6 code", "940360", max_chars=6, key=f"hs_{key}")
    label = preset.split(" (")[0] if PRESETS[preset] else f"HS {hs}"
    return hs, label


def report_html(title: str, body_md: str) -> str:
    return (
        f"<html><head><meta charset='utf-8'><title>{title}</title>"
        "<style>body{font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:900px;margin:40px auto;"
        "padding:0 16px;line-height:1.55;color:#1d1d1f}table{border-collapse:collapse;width:100%;margin:8px 0}"
        "td,th{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}th{background:#f3f4f6}"
        "h1{color:#0b3d91}h2{border-bottom:2px solid #0b3d91;padding-bottom:4px;margin-top:32px}"
        "blockquote{background:#fff7e6;border-left:4px solid #f59e0b;margin:0;padding:8px 12px}</style></head><body>"
        + md.markdown(body_md, extensions=["tables"])
        + "<hr><small>Generated by AI Market Entry Analyst · Data: Eurostat, UN Comtrade, World Bank</small>"
        "</body></html>"
    )


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### Market Entry Analyst")
    st.caption("Data-driven market entry decisions for the EU and China")
    st.divider()
    st.markdown("**Live data sources**")
    st.markdown(
        "- Eurostat Comext (EU trade, EUR)\n"
        "- UN Comtrade (China trade, USD)\n"
        "- World Bank (macro, logistics, governance)"
    )
    st.markdown("**Frameworks**: PESTEL · CAGE · HHI · OLI entry modes")
    st.markdown("[🌐 Live showcase site](https://onurusalan.github.io/ai-market-entry-analyst/)")
    st.divider()
    with st.expander("Optional: Claude AI narrative (experimental, needs internet)"):
        st.caption("The platform is fully free. If you have your own Anthropic API key, "
                   "an AI agent can also write a narrative report with live web research.")
        user_key = st.text_input("Anthropic API key", type="password",
                                 help="Used only in this session, never stored.")
    owner_key = os.getenv("ANTHROPIC_API_KEY", "")
    access_code = os.getenv("DEMO_ACCESS_CODE", "")
    api_key = user_key or (owner_key if owner_key and not access_code else "")

tab_report, tab_data, tab_rank, tab_method = st.tabs(
    ["📄 Entry Report", "📊 Market Dashboard", "🇪🇺 EU-27 Ranking", "📐 Methodology"])

# --------------------------------------------------------------------------- #
# Tab 1: Entry report (free rule-based engine)
# --------------------------------------------------------------------------- #
with tab_report:
    st.markdown("### Generate a market entry report")
    st.caption("Live trade data plus IB frameworks: verdict, PESTEL, CAGE, risk matrix, entry mode and 90-day plan.")
    with st.form("report_form"):
        r1, r2, r3 = st.columns([2, 1.3, 1.3])
        with r1:
            hs_r, label_r = product_picker("report")
        target_label = r2.selectbox("Target market", ["EU-27", "China"] + [name(c) for c in sorted(EU_ISO3)],
                                    index=1)
        home_label = r3.selectbox("Company home country", list(HOME_COUNTRIES),
                                  index=list(HOME_COUNTRIES.values()).index("DE"))
        r4, r5, r6, r7 = st.columns([2, 1.3, 0.8, 0.8])
        company = r4.text_input("Company (optional)", "Mid-sized premium e-bike manufacturer")
        size = r5.selectbox("Company size", list(COMPANY_SIZES), index=1, format_func=COMPANY_SIZES.get)
        start_r = r6.number_input("From", 2002, LAST_FULL_YEAR - 1, LAST_FULL_YEAR - 5)
        end_r = r7.number_input("To", 2003, LAST_FULL_YEAR + 1, LAST_FULL_YEAR)
        go_btn = st.form_submit_button("📄 Generate report", type="primary")

    if target_label == "EU-27":
        target_r = "EU"
    elif target_label == "China":
        target_r = "CN"
    else:
        target_r = next(c for c in EU_ISO3 if name(c) == target_label)
    home_r = HOME_COUNTRIES[home_label]

    if go_btn:
        if not (hs_r.isdigit() and len(hs_r) == 6):
            st.error("The HS code must have 6 digits.")
        elif target_r == home_r or (target_r == "EU" and home_r in kb.EU27):
            st.warning("Home and target market are the same single market. Pick a different target "
                       "(e.g. China for an EU company) or home country.")
        else:
            with st.spinner("Pulling live data and running the analysis… (first run can take ~30 s)"):
                try:
                    st.session_state["report"] = load_report(
                        hs_r, target_r, home_r, company, size, int(start_r), int(end_r), label_r)
                except Exception as exc:
                    st.error(f"Could not build the report: {exc}")

    if st.session_state.get("report"):
        title, body, data = st.session_state["report"]
        s = data["score"]["score_0_10"]
        v = data["verdict"]
        colour = {"ENTER": "🟢", "ENTER WITH CAUTION": "🟡", "DO NOT ENTER NOW": "🔴"}[v]
        banner = {"ENTER": st.success, "ENTER WITH CAUTION": st.warning, "DO NOT ENTER NOW": st.error}[v]
        banner(f"{colour} **Verdict: {v}** · Recommended entry mode: {data['entry_mode']['mode']}")
        k2, k3, k4 = st.columns(3)
        k2.metric("Attractiveness", f"{s}/10")
        k3.metric("CAGE distance", data["cage"]["overall_label"])
        k4.metric("Risks flagged", len(data["risks"]))
        if data.get("data_quality", {}).get("flags"):
            st.info("**Data note:** " + " ".join(data["data_quality"]["flags"]))

        with st.expander("💶 Landed-cost calculator", expanded=False):
            a = data["landed_cost"]["assumptions"]
            c1, c2, c3, c4, c5 = st.columns(5)
            price = c1.number_input("Ex-works price / unit", 0.0, value=100.0, step=10.0)
            freight = c2.number_input("Freight & insurance %", 0.0, value=float(a["freight_pct"]), step=0.5)
            duty = c3.number_input("Import duty %", 0.0, value=float(a["duty_pct"]), step=0.1,
                                   help=data["tariff"]["basis"])
            vat = c4.number_input("Import VAT %", 0.0, value=float(a["vat_pct"]), step=0.5)
            other = c5.number_input("Clearance & fees %", 0.0, value=float(a["other_pct"]), step=0.5)
            lc = landed_cost(price, freight, duty, vat, other)
            m1, m2, m3 = st.columns(3)
            m1.metric("Landed cost / unit", f"{lc['landed_total']:,.2f}")
            m2.metric("Before VAT", f"{lc['landed_ex_vat']:,.2f}", f"{lc['uplift_ex_vat_pct']:+.1f}% on ex-works", delta_color="off")
            m3.metric("Import duty / unit", f"{lc['duty']:,.2f}")
        st.divider()
        st.markdown(body)
        d1, d2 = st.columns(2)
        slug = title.split(":")[-1].strip().replace(" ", "_").replace("→", "to")[:60]
        d1.download_button("⬇️ Download Markdown", body, file_name=f"{slug}.md")
        d2.download_button("⬇️ Download HTML (print to PDF)", report_html(title, body),
                           file_name=f"{slug}.html", mime="text/html")

        if api_key:
            st.divider()
            if st.button("🤖 Add Claude AI narrative with live web research"):
                import anthropic

                from src.agent import TOOL_LABELS, build_prompt, run_agent
                with st.status("AI agent working…", expanded=True) as status:
                    def on_event(kind, payload):
                        if kind == "tool":
                            st.write("🔧 " + TOOL_LABELS.get(payload["name"], payload["name"]))
                    try:
                        res = run_agent(build_prompt(company, label_r, name(home_r), target_label),
                                        on_event=on_event, client=anthropic.Anthropic(api_key=api_key))
                        status.update(label="AI narrative ready", state="complete")
                        st.markdown(res.report_markdown)
                    except Exception as exc:
                        status.update(label="AI error", state="error")
                        st.error(f"{type(exc).__name__}: {exc}")

# --------------------------------------------------------------------------- #
# Tab 2: Market dashboard
# --------------------------------------------------------------------------- #
with tab_data:
    c1, c2, c3, c4 = st.columns([1.2, 2, 1, 1])
    target_label = c1.selectbox("Target market", ["EU-27", "China", "EU member state"], key="dash_target")
    with c2:
        hs, _ = product_picker("dash")
    start = c3.number_input("From", 2002, LAST_FULL_YEAR, 2017, key="dash_from")
    end = c4.number_input("To", 2003, LAST_FULL_YEAR + 1, LAST_FULL_YEAR, key="dash_to")

    if target_label == "EU-27":
        target = "EU"
    elif target_label == "China":
        target = "CN"
    else:
        target = st.selectbox("Member state", sorted(EU_ISO3), format_func=name,
                              index=sorted(EU_ISO3).index("DE"))

    if not (hs.isdigit() and len(hs) == 6):
        st.warning("The HS code must have 6 digits.")
    else:
        with st.spinner("Pulling live trade data…"):
            try:
                m = load_market(target, hs, int(start), int(end))
            except Exception as exc:
                m = {"error": str(exc)}

        if "error" in m:
            st.error(m["error"])
        else:
            cur = m["currency"]
            profile = load_profile(target)
            score = analysis.attractiveness_score(m, profile)

            if m.get("product_name"):
                st.subheader(m["product_name"][:120])
            st.caption(f"Source: {m['source']} · HS {hs} · {m['years'][0]}–{m['years'][1]}")

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric(f"Import market {m['latest_year']}", fmt_money(m["latest_market_size"], cur))
            k2.metric("CAGR", f"{m['cagr_pct']}%" if m["cagr_pct"] is not None else "–")
            k3.metric("HHI", f"{m['hhi']:,.0f}", m["hhi_label"].split(" (")[0], delta_color="off")
            if target == "CN":
                k4.metric("EU-27 share", f"{m['eu27_share_pct_by_year'].get(m['latest_year'])}%")
            else:
                k4.metric("China share", f"{m['china_share_pct_by_year'].get(m['latest_year'])}%")
            k5.metric("Attractiveness", f"{score['score_0_10']}/10")

            g1, g2 = st.columns(2)
            size_df = pd.DataFrame({"Year": list(m["import_market_size_by_year"].keys()),
                                    "Value": list(m["import_market_size_by_year"].values())})
            fig = px.bar(size_df, x="Year", y="Value", title=f"Import market size ({cur})")
            fig.update_layout(height=360, margin=dict(t=50, b=10))
            g1.plotly_chart(fig, width="stretch")

            share_key = "eu27_share_pct_by_year" if target == "CN" else "china_share_pct_by_year"
            share_title = "EU-27 share of China's imports (%)" if target == "CN" else "China's share of extra-EU imports (%)"
            sh = pd.DataFrame({"Year": list(m[share_key].keys()), "Share": list(m[share_key].values())})
            fig = px.line(sh, x="Year", y="Share", markers=True, title=share_title)
            fig.update_layout(height=360, margin=dict(t=50, b=10), yaxis_range=[0, 100])
            g2.plotly_chart(fig, width="stretch")

            g3, g4 = st.columns(2)
            sup = pd.DataFrame(m["top_suppliers_latest_year"])
            fig = px.bar(sup.iloc[::-1], x="share_pct", y="partner_name", orientation="h",
                         title=f"Top suppliers {m['latest_year']} (market share %)",
                         labels={"share_pct": "Share %", "partner_name": ""})
            fig.update_layout(height=400, margin=dict(t=50, b=10))
            g3.plotly_chart(fig, width="stretch")

            subs = score["sub_scores"]
            labels = {"market_size": "Market size", "growth": "Growth", "competitive_openness": "Openness",
                      "institutional_quality": "Institutions", "logistics": "Logistics"}
            vals = list(subs.values())
            fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=[labels[k] for k in subs] + [labels[list(subs)[0]]],
                                            fill="toself"))
            fig.update_layout(title=f"Attractiveness components (total {score['score_0_10']}/10)",
                              polar=dict(radialaxis=dict(range=[0, 10])), height=400, margin=dict(t=60, b=10))
            g4.plotly_chart(fig, width="stretch")

            members = m.get("eu_members_importing_from_china_latest_year")
            if members:
                fig = eu_tile_map({r["member"]: r["value_eur"] / 1e6 for r in members},
                                  f"Imports from China by EU member state ({m['latest_year']}, EUR m)", " m", "Reds")
                st.plotly_chart(fig, width="stretch")

            with st.expander("Raw data (JSON)"):
                st.json(m)

# --------------------------------------------------------------------------- #
# Tab 3: EU-27 ranking
# --------------------------------------------------------------------------- #
with tab_rank:
    st.markdown("### Which EU country should you enter first?")
    st.caption("All 27 member states ranked on demand, growth, purchasing power, logistics and institutions.")
    q1, q2, q3 = st.columns([2, 1, 1])
    with q1:
        hs_k, _ = product_picker("rank")
    start_k = q2.number_input("From", 2002, LAST_FULL_YEAR - 1, LAST_FULL_YEAR - 5, key="rank_from")
    end_k = q3.number_input("To", 2003, LAST_FULL_YEAR + 1, LAST_FULL_YEAR, key="rank_to")
    if hs_k.isdigit() and len(hs_k) == 6:
        with st.spinner("Ranking 27 markets…"):
            try:
                ranking = load_ranking(hs_k, int(start_k), int(end_k))
            except Exception as exc:
                ranking = []
                st.error(str(exc))
        if ranking:
            rdf = pd.DataFrame(ranking)
            rdf["country"] = rdf["member"].map(name)
            fig = eu_tile_map(dict(zip(rdf["member"], rdf["score_0_10"], strict=True)),
                              "Entry attractiveness by member state (0-10)", "", "Blues")
            st.plotly_chart(fig, width="stretch")
            show = rdf[["rank", "country", "imports_eur", "share_of_eu_pct", "cagr_pct", "gdp_per_capita_usd",
                        "lpi", "score_0_10"]].rename(columns={
                "rank": "Rank", "country": "Country", "imports_eur": "Imports (EUR)", "share_of_eu_pct": "Share of EU %",
                "cagr_pct": "CAGR %", "gdp_per_capita_usd": "GDP/capita (USD)", "lpi": "LPI", "score_0_10": "Score"})
            st.dataframe(show, hide_index=True, width="stretch")
            st.caption("Imports include intra-EU trade; hubs such as the Netherlands and Belgium also re-export.")

# --------------------------------------------------------------------------- #
# Tab 4: Methodology
# --------------------------------------------------------------------------- #
with tab_method:
    st.markdown("""
### Market size
Imports into the target market proxy addressable demand: extra-EU imports (Eurostat Comext, `EXT_EU27_2020`)
for the EU and China-reported imports (UN Comtrade, excluding re-imports of Chinese goods) for China.

### HHI (Herfindahl-Hirschman Index)
Sum of squared supplier shares (%), from 0 to 10,000.
| HHI | Meaning |
|---|---|
| < 1,000 | Unconcentrated (diversified supply) |
| 1,000 – 1,800 | Moderately concentrated |
| > 1,800 | Highly concentrated |
Bands follow the US DOJ/FTC 2023 Merger Guidelines.

### Market attractiveness score (0–10)
| Component | Weight | Formula |
|---|---|---|
| Market size | 25% | 2 × (log10(value) − 6) |
| Growth | 25% | 5 + CAGR / 3 |
| Competitive openness | 20% | 10 − HHI / 1000 |
| Institutional quality | 15% | mean of 4 World Bank WGI scores, rescaled |
| Logistics | 15% | (LPI − 1) × 2.5 |

### CAGE distance (Ghemawat, 2001)
- **Cultural:** language-family overlap
- **Administrative:** same single market, free-trade agreement or none; governance gap (WGI)
- **Geographic:** great-circle distance between capitals (<1,500 km low, <5,000 km medium)
- **Economic:** GDP per capita ratio (<1.5× low, <3× medium)

### Entry mode
Rules follow transaction-cost and OLI logic: high distance, low attractiveness or small firms lead to
low-commitment modes (exporting, distributors, cross-border e-commerce); attractive, low-risk markets and
large firms lead to subsidiaries or a WFOE; regulated sectors in China lead to joint ventures or licensing.

### EU-27 ranking
Demand 40% (total imports, log scale), growth 25%, GDP per capita 15%, logistics 10%, institutions 10%.
""")
