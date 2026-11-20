# 🌍 Market Entry Analyst: EU ⇄ China

[![CI](https://github.com/onurusalan/ai-market-entry-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/onurusalan/ai-market-entry-analyst/actions/workflows/ci.yml)
**Live demo:** https://onurusalan.github.io/ai-market-entry-analyst/

**A data platform that turns official trade statistics into consulting-style market entry reports for the EU and Chinese markets.**

Pick a product (HS code), a target market (EU-27, one member state or China) and the company's home country. The platform pulls live data from **Eurostat, UN Comtrade and the World Bank**, applies International Business frameworks in code (**PESTEL, CAGE distance, HHI, OLI entry-mode logic**) and produces a report with a clear verdict, an EU-27 country ranking, a risk matrix and a 90-day action plan.

Everything runs on **free public data**. No paid service is needed. An optional Claude AI agent can add live web research if you bring your own API key.

---

## ✨ What it does

| | Feature | Details |
|---|---|---|
| 📄 | **Market entry report** | Verdict (Enter / Enter with caution / Do not enter now), market sizing, competition, PESTEL, CAGE, regulation checklist, risk matrix, entry mode, 90-day plan |
| 📊 | **Market dashboard** | Import market size and CAGR, top suppliers, China's (or the EU's) share over time, EU map of imports from China |
| 🇪🇺 | **EU-27 ranking** | Ranks all member states on demand, growth, purchasing power, logistics and institutions |
| 📈 | **Supply concentration (HHI)** | Herfindahl-Hirschman Index with DOJ/FTC 2023 bands to quantify supplier dependency |
| 🎯 | **Transparent scoring** | 0-10 attractiveness score with published weights and formulas |
| 🌐 | **Static showcase site** | 8 case studies rebuilt monthly from live data by GitHub Actions and published on GitHub Pages |
| 🤖 | **Optional AI agent** | Claude tool-use agent with web search (bring your own key) |

### Case studies on the live site

| Case | Verdict | Recommended entry mode |
|---|---|---|
| 🚲 E-bikes: Taiwan → EU-27 | Enter with caution | Exclusive distributor + small sales office |
| 🚗 Battery-electric cars: China → EU-27 | Enter with caution | Wholly owned sales subsidiary |
| 🧴 Skincare: France → China | Enter | Cross-border e-commerce first, then a distributor |
| 🍷 Bottled wine: Italy → China | Enter with caution | Exclusive Chinese importer-distributor |
| 💊 Medicaments: Germany → China | Enter | Joint venture or licensing |
| 🔋 Lithium-ion batteries: Korea → EU-27 | Enter with caution | Wholly owned sales subsidiary |
| 🌡️ Heat pumps: Japan → EU-27 | Enter | Wholly owned sales subsidiary |
| 🪑 Wooden furniture: Vietnam → EU-27 | Enter with caution | Exporting via importers and distributors |

*(Verdicts are regenerated from the latest data each month.)*

## 🧪 Example insight (real data)

**E-bikes (HS 871160) → EU-27, 2024:** extra-EU imports were **€1.57 bn**. **China supplied 53.5%**, Taiwan 22.5% and Vietnam 8.1%. **HHI is 3,476 (highly concentrated)**, a supplier-dependency risk for EU buyers and an opening for non-Chinese suppliers. The top-ranked entry markets are Austria, Germany and the Netherlands. *(Source: Eurostat Comext DS-045409.)*

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Data layer: src/data_sources.py                                  │
│  Eurostat Comext (JSON-stat) · UN Comtrade · World Bank WDI/WGI  │
│  retries · rate-limit handling · on-disk cache                   │
└──────────────────────────────┬───────────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────────┐
│ Analysis layer: src/analysis.py                                  │
│  market size · CAGR · supplier shares · HHI · score · EU ranking │
└──────────────────────────────┬───────────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────────┐
│ Decision layer: src/report_engine.py + src/knowledge.py          │
│  PESTEL · CAGE · risk matrix · entry-mode rules · 90-day plan    │
│  curated regulation knowledge base (EU and China)                │
│  (optional) src/agent.py: Claude tool-use agent + web search     │
└──────────────────────────────┬───────────────────────────────────┘
                               ↓
┌───────────────────────────────┐   ┌──────────────────────────────┐
│ app.py: Streamlit web app     │   │ scripts/build_site.py:       │
│ report · dashboard · ranking  │   │ static site → GitHub Pages   │
└───────────────────────────────┘   └──────────────────────────────┘
```

## 🚀 Quick start

```bash
git clone https://github.com/onurusalan/ai-market-entry-analyst.git
cd ai-market-entry-analyst
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Other commands:

```bash
pytest -q                       # offline unit tests
python scripts/build_site.py    # rebuild the static showcase site into docs/
```

Optional environment variables (see `.env.example`): `COMTRADE_API_KEY` (free, faster China data) and `ANTHROPIC_API_KEY` (AI narrative).

## ☁️ Deploy the interactive app (free)

The static showcase site is already live on GitHub Pages. To host the interactive Streamlit app as well:

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with GitHub.
2. **Create app** → repository `onurusalan/ai-market-entry-analyst`, branch `main`, file `app.py` → **Deploy**.

No secrets are required: the app runs fully on public data.

## 📐 Methodology

**Market size.** Imports into the target market proxy addressable demand: extra-EU imports (Eurostat `EXT_EU27_2020`) for the EU and China-reported imports (UN Comtrade, excluding re-imports of Chinese goods) for China.

**HHI.** Sum of squared supplier shares (%): below 1,000 is unconcentrated, 1,000 to 1,800 is moderately concentrated, above 1,800 is highly concentrated.

**Attractiveness score (0-10).**

| Component | Weight | Formula |
|---|---|---|
| Market size | 25% | 2 × (log10(value) − 6) |
| Growth | 25% | 5 + CAGR / 3 |
| Competitive openness | 20% | 10 − HHI / 1000 |
| Institutional quality | 15% | mean of 4 World Bank WGI scores, rescaled |
| Logistics | 15% | (LPI − 1) × 2.5 |

**CAGE distance** (Ghemawat, 2001). Cultural distance from language-family overlap. Administrative distance from single market, FTA or none, plus the governance gap. Geographic distance between capitals: below 1,500 km is low, below 5,000 km is medium. Economic distance from the GDP per capita ratio: below 1.5× is low, below 3× is medium.

**Entry mode.** Rules follow transaction-cost and OLI logic. High distance, low attractiveness or small firms lead to low-commitment modes (exporting, distributors, cross-border e-commerce). Attractive markets with strong institutions and large firms lead to subsidiaries or a WFOE. Regulated sectors in China (pharma, medtech) lead to a JV or licensing.

**EU-27 ranking.** Demand 40% (total imports, log scale), growth 25%, GDP per capita 15%, logistics 10%, institutions 10%.

**Limitations.** Imports are a demand proxy, not total consumption. Hub countries (Netherlands, Belgium) re-export. Regulatory notes are curated and must be verified on the official sources linked in each report.

## 🗺️ Roadmap

- [ ] Tariff lookup from EU TARIC and China's tariff schedule
- [ ] Trade-defence tracker (EU anti-dumping and anti-subsidy cases)
- [ ] Landed-cost calculator (duties, freight, VAT, FX)
- [ ] PDF export with charts

## 🛠️ Tech stack

Python · pandas · REST APIs (Eurostat SDMX/JSON-stat, UN Comtrade, World Bank) · Streamlit · Plotly · pytest · GitHub Actions · GitHub Pages · optional Anthropic Claude API

---

*Built by Onur Usalan (MSc International Business, BSc Management Information Systems).*
