"""
AI Market Entry Analyst: EU <-> China
Streamlit web app. Run with:  streamlit run app.py
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

from src import analysis

load_dotenv()

st.set_page_config(page_title="AI Market Entry Analyst", page_icon="🌍", layout="wide")

PRESETS = {
    "E-bisiklet (871160)": "871160",
    "Lityum-iyon pil (850760)": "850760",
    "Güneş paneli / PV modül (854143)": "854143",
    "Elektrikli otomobil (870380)": "870380",
    "İlaç, dozlu (300490)": "300490",
    "Şarap, şişede (220421)": "220421",
    "Kozmetik / cilt bakımı (330499)": "330499",
    "Isı pompası (841861)": "841861",
    "Özel kod gir…": "",
}

EU_ISO3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK",
    "EE": "EST", "ES": "ESP", "FI": "FIN", "FR": "FRA", "GR": "GRC", "HR": "HRV", "HU": "HUN",
    "IE": "IRL", "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT", "NL": "NLD",
    "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE", "SI": "SVN", "SK": "SVK",
}

LAST_FULL_YEAR = date.today().year - 2  # trade data lags ~1 year; keep a safe default


def fmt_money(v: float | None, cur: str) -> str:
    if v is None:
        return "–"
    sym = "€" if cur == "EUR" else "$"
    for div, suf in ((1e9, " Mr"), (1e6, " Mn"), (1e3, " B")):
        if abs(v) >= div:
            return f"{sym}{v / div:,.2f}{suf}"
    return f"{sym}{v:,.0f}"


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def load_market(target: str, hs: str, start: int, end: int) -> dict:
    if target == "CN":
        return analysis.analyze_china_market(hs, start, end)
    return analysis.analyze_eu_market(hs, start, end, target)


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def load_profile(iso2: str) -> dict | None:
    rows = analysis.country_profiles([iso2])
    return rows[0] if rows else None


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("🌍 AI Market Entry Analyst")
    st.caption("AB ⇄ Çin pazarına giriş kararları için gerçek veri + yapay zekâ")
    st.divider()
    st.markdown("**Veri kaynakları**")
    st.markdown(
        "- Eurostat Comext (AB ticareti, EUR)\n"
        "- UN Comtrade (Çin ticareti, USD)\n"
        "- World Bank (makro, lojistik, yönetişim)\n"
        "- Web araması (güncel regülasyon, haber)"
    )
    st.divider()
    # --- AI access -------------------------------------------------------- #
    # On a public deployment the owner's key must not be usable by everyone:
    # visitors either enter the demo access code or bring their own API key.
    owner_key = os.getenv("ANTHROPIC_API_KEY", "")
    access_code = os.getenv("DEMO_ACCESS_CODE", "")
    st.markdown("**AI erişimi**")
    user_key = st.text_input("Kendi Anthropic API anahtarınız", type="password",
                             help="Sadece bu oturumda kullanılır, kaydedilmez.")
    code_ok = False
    if owner_key and access_code:
        entered = st.text_input("veya demo erişim kodu", type="password")
        code_ok = bool(entered) and entered == access_code
    elif owner_key:
        code_ok = True  # local use: no access code configured
    api_key = user_key or (owner_key if code_ok else "")
    st.markdown("**AI durumu:** " + ("🟢 Hazır" if api_key else "🔴 Kapalı"))
    if not api_key:
        st.caption("AI raporu için API anahtarı veya demo kodu gerekir. Veri paneli herkese açık.")

tab_data, tab_ai, tab_method = st.tabs(["📊 Veri Paneli", "🤖 AI Pazara Giriş Raporu", "📐 Metodoloji"])

# --------------------------------------------------------------------------- #
# Tab 1: Data dashboard (no AI needed)
# --------------------------------------------------------------------------- #
with tab_data:
    c1, c2, c3, c4 = st.columns([1.2, 2, 1, 1])
    target_label = c1.selectbox("Hedef pazar", ["AB-27", "Çin", "AB üye ülkesi"])
    preset = c2.selectbox("Ürün", list(PRESETS.keys()))
    hs = PRESETS[preset] or c2.text_input("HS6 kodu", "940360", max_chars=6)
    start = c3.number_input("Başlangıç", 2002, LAST_FULL_YEAR, 2017)
    end = c4.number_input("Bitiş", 2003, LAST_FULL_YEAR + 1, LAST_FULL_YEAR)

    if target_label == "AB-27":
        target = "EU"
    elif target_label == "Çin":
        target = "CN"
    else:
        target = st.selectbox("Üye ülke", sorted(EU_ISO3.keys()), index=sorted(EU_ISO3).index("DE"))

    if not (hs.isdigit() and len(hs) == 6):
        st.warning("HS kodu 6 haneli olmalı.")
        st.stop()

    with st.spinner("Gerçek ticaret verisi çekiliyor…"):
        try:
            m = load_market(target, hs, int(start), int(end))
        except Exception as exc:  # network / API errors
            m = {"error": str(exc)}

    if "error" in m:
        st.error(m["error"])
    else:
        cur = m["currency"]
        profile_iso = "CN" if target == "CN" else target
        profile = load_profile(profile_iso)
        score = analysis.attractiveness_score(m, profile)

        if m.get("product_name"):
            st.subheader(f"{m['product_name'][:110]}")
        st.caption(f"Kaynak: {m['source']} · HS {hs} · {m['years'][0]}–{m['years'][1]}")

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric(f"İthalat pazarı ({m['latest_year']})", fmt_money(m["latest_market_size"], cur))
        k2.metric("Yıllık büyüme (CAGR)", f"%{m['cagr_pct']}" if m["cagr_pct"] is not None else "–")
        hhi_tr = {"Unconcentrated": "Çeşitlendirilmiş", "Moderately concentrated": "Orta yoğunlaşma",
                  "Highly concentrated": "Yüksek yoğunlaşma"}
        k3.metric("Tedarik yoğunlaşması (HHI)", f"{m['hhi']:,.0f}",
                  hhi_tr.get(m["hhi_label"].split(" (")[0], m["hhi_label"]), delta_color="off")
        if target == "CN":
            eu_share = m["eu27_share_pct_by_year"].get(m["latest_year"])
            k4.metric("AB-27 payı", f"%{eu_share}")
        else:
            cn_share = m["china_share_pct_by_year"].get(m["latest_year"])
            k4.metric("Çin payı", f"%{cn_share}")
        k5.metric("Çekicilik skoru", f"{score['score_0_10']}/10")

        g1, g2 = st.columns(2)
        size_df = pd.DataFrame(
            {"Yıl": list(m["import_market_size_by_year"].keys()),
             "Değer": list(m["import_market_size_by_year"].values())}
        )
        fig = px.bar(size_df, x="Yıl", y="Değer", title=f"İthalat pazarı büyüklüğü ({cur})")
        fig.update_layout(height=360, margin=dict(t=50, b=10))
        g1.plotly_chart(fig, width="stretch")

        share_key = "eu27_share_pct_by_year" if target == "CN" else "china_share_pct_by_year"
        share_title = "AB-27'nin Çin ithalatındaki payı (%)" if target == "CN" else "Çin'in AB dışı ithalattaki payı (%)"
        sh = pd.DataFrame({"Yıl": list(m[share_key].keys()), "Pay": list(m[share_key].values())})
        fig = px.line(sh, x="Yıl", y="Pay", markers=True, title=share_title)
        fig.update_layout(height=360, margin=dict(t=50, b=10), yaxis_range=[0, 100])
        g2.plotly_chart(fig, width="stretch")

        g3, g4 = st.columns(2)
        sup = pd.DataFrame(m["top_suppliers_latest_year"])
        fig = px.bar(sup.iloc[::-1], x="share_pct", y="partner_name", orientation="h",
                     title=f"En büyük tedarikçiler ({m['latest_year']}, pazar payı %)",
                     labels={"share_pct": "Pay %", "partner_name": ""})
        fig.update_layout(height=400, margin=dict(t=50, b=10))
        g3.plotly_chart(fig, width="stretch")

        subs = score["sub_scores"]
        names = {"market_size": "Pazar büyüklüğü", "growth": "Büyüme",
                 "competitive_openness": "Rekabete açıklık",
                 "institutional_quality": "Kurumsal kalite", "logistics": "Lojistik"}
        fig = go.Figure(go.Scatterpolar(
            r=list(subs.values()) + [list(subs.values())[0]],
            theta=[names[k] for k in subs] + [names[list(subs)[0]]],
            fill="toself"))
        fig.update_layout(title=f"Çekicilik skoru alt bileşenleri (toplam {score['score_0_10']}/10)",
                          polar=dict(radialaxis=dict(range=[0, 10])), height=400,
                          margin=dict(t=60, b=10))
        g4.plotly_chart(fig, width="stretch")

        members = m.get("eu_members_importing_from_china_latest_year")
        if members:
            mdf = pd.DataFrame(members)
            mdf["iso3"] = mdf["member"].map(EU_ISO3)
            fig = px.choropleth(mdf, locations="iso3", color="value_eur", scope="europe",
                                color_continuous_scale="Reds",
                                title=f"Çin'den en çok ithalat yapan AB ülkeleri ({m['latest_year']}, EUR)",
                                labels={"value_eur": "EUR"})
            fig.update_geos(fitbounds="locations", visible=False, showcountries=True,
                            bgcolor="rgba(0,0,0,0)")
            fig.update_layout(height=520, margin=dict(t=50, b=0), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, width="stretch")

        with st.expander("Ham veri (JSON)"):
            st.json(m)

# --------------------------------------------------------------------------- #
# Tab 2: AI report
# --------------------------------------------------------------------------- #
with tab_ai:
    st.markdown(
        "Şirketinizi ve ürününüzü anlatın. AI ajanı **gerçek veriyi kendisi çeker**, "
        "PESTEL, CAGE ve giriş modu çerçeveleriyle analiz eder ve kaynaklı bir rapor yazar."
    )
    with st.form("ai_form"):
        a1, a2 = st.columns(2)
        company = a1.text_input("Şirket (opsiyonel)", "Orta ölçekli bir Alman e-bisiklet üreticisi")
        product = a2.text_input("Ürün", "Elektrikli bisiklet (e-bike)")
        a3, a4 = st.columns(2)
        home = a3.text_input("Şirketin ülkesi", "Almanya")
        target_ai = a4.selectbox("Hedef pazar", ["Çin", "AB-27 (Avrupa Birliği)", "Almanya",
                                               "Fransa", "İtalya", "Hollanda", "İspanya", "Polonya"])
        extra = st.text_area("Ek bağlam (opsiyonel)",
                             "Yıllık ciro ~50M €, premium segment, online satış kanalı güçlü.")
        submitted = st.form_submit_button("🚀 Raporu oluştur", type="primary", disabled=not api_key)

    if not api_key:
        st.info("AI raporu için soldaki menüden kendi API anahtarınızı veya demo erişim kodunu girin.")

    MAX_REPORTS_PER_SESSION = 3
    used = st.session_state.get("reports_used", 0)
    using_owner_key = api_key and not user_key
    if submitted and using_owner_key and used >= MAX_REPORTS_PER_SESSION:
        st.warning(f"Demo limiti: oturum başına {MAX_REPORTS_PER_SESSION} rapor. "
                   "Devam etmek için kendi API anahtarınızı kullanın.")
        submitted = False

    if submitted:
        import anthropic

        from src.agent import TOOL_LABELS, build_prompt, run_agent

        st.session_state["reports_used"] = used + 1

        prompt = build_prompt(company, product, home, target_ai, extra)
        with st.status("AI ajanı çalışıyor…", expanded=True) as status:
            def on_event(kind: str, payload: dict) -> None:
                if kind == "tool":
                    label = TOOL_LABELS.get(payload["name"], payload["name"])
                    detail = ", ".join(f"{k}={v}" for k, v in (payload.get("input") or {}).items())
                    st.write(f"🔧 {label}  \n`{detail[:120]}`")

            try:
                result = run_agent(prompt, on_event=on_event,
                                   client=anthropic.Anthropic(api_key=api_key))
                status.update(label=f"Rapor hazır · {len(result.tool_calls)} araç çağrısı", state="complete")
                st.session_state["report"] = result.report_markdown
            except Exception as exc:
                status.update(label="Hata oluştu", state="error")
                st.error(f"{type(exc).__name__}: {exc}")

    report = st.session_state.get("report")
    if report:
        st.divider()
        st.markdown(report)
        html = (
            "<html><head><meta charset='utf-8'><title>Market Entry Report</title>"
            "<style>body{font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:860px;"
            "margin:40px auto;line-height:1.55;color:#1d1d1f}table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ddd;padding:6px 8px}th{background:#f3f4f6}h1{color:#0b3d91}"
            "h2{border-bottom:2px solid #0b3d91;padding-bottom:4px;margin-top:32px}</style></head><body>"
            + md.markdown(report, extensions=["tables"])
            + "<hr><small>Generated by AI Market Entry Analyst · Data: Eurostat, UN Comtrade, World Bank</small>"
            "</body></html>"
        )
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Markdown indir", report, file_name="market_entry_report.md")
        d2.download_button("⬇️ HTML indir (tarayıcıdan PDF'e yazdırılabilir)", html,
                           file_name="market_entry_report.html", mime="text/html")

# --------------------------------------------------------------------------- #
# Tab 3: Methodology
# --------------------------------------------------------------------------- #
with tab_method:
    st.markdown("""
### Pazar büyüklüğü
Hedef pazarın **ithalatı** kullanılır: AB için AB dışından yapılan ithalat (Eurostat Comext,
`EXT_EU27_2020`), Çin için Çin'in bildirdiği ithalat (UN Comtrade). İthalat toplam tüketimin değil,
dışarıdan karşılanan talebin göstergesidir.

### HHI: Herfindahl-Hirschman Endeksi
Tedarikçi ülkelerin pazar paylarının (%) karelerinin toplamı (0–10.000).
| HHI | Yorum |
|---|---|
| < 1.000 | Çeşitlendirilmiş tedarik |
| 1.000 – 1.800 | Orta yoğunlaşma |
| > 1.800 | Yüksek yoğunlaşma |
Eşikler ABD Adalet Bakanlığı ve FTC'nin 2023 birleşme kılavuzundan alınmıştır.

### Çekicilik skoru (0–10)
| Bileşen | Ağırlık | Hesaplama |
|---|---|---|
| Pazar büyüklüğü | %25 | log10 ölçek: 10 Mn ≈ 2, 1 Mr ≈ 6, 100 Mr ≈ 10 |
| Büyüme | %25 | 5 + CAGR/3 |
| Rekabete açıklık | %20 | 10 − HHI/1000 |
| Kurumsal kalite | %15 | World Bank WGI ortalaması (−2,5…2,5) → 0–10 |
| Lojistik | %15 | World Bank LPI (1–5) → 0–10 |

### AI ajanı
Claude (Anthropic) bir **araç kullanan ajan** olarak çalışır: hangi veriyi çekeceğine kendisi karar verir,
sonuçları PESTEL, CAGE ve giriş modu çerçeveleriyle yorumlar. Tüm rakamlar araç sonuçlarından veya kaynak
gösterilen web sonuçlarından gelmek zorundadır.
""")
