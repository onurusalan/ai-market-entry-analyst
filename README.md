# 🌍 AI Market Entry Analyst: EU ⇄ China

**An AI agent that turns official trade data into consulting-grade market entry reports for the EU and Chinese markets.**

A company describes its product and target market. The agent pulls live data from Eurostat, UN Comtrade and the World Bank, searches the web for current tariffs and regulation, applies International Business frameworks (PESTEL, CAGE, entry-mode theory) and writes a sourced report with a clear recommendation.

> *Why not just ask a chatbot?* General chatbots can invent numbers and rely on stale knowledge. This tool fetches **official, current data**, scores markets with a **transparent model**, and **cites a source for every figure**.

---

## ✨ Features

| | Feature | Details |
|---|---|---|
| 📊 | **Trade data dashboard** | EU-27 / member-state / China import market size, CAGR, top suppliers, China's (or the EU's) share over time, EU map of imports from China |
| 📈 | **Supply concentration (HHI)** | Herfindahl-Hirschman Index with DOJ/FTC 2023 bands, a measure of supplier dependency and competitive openness |
| 🎯 | **Market attractiveness score (0-10)** | Transparent weighted model: market size, growth, competitive openness, institutional quality (WGI), logistics (LPI) |
| 🤖 | **AI research agent** | Claude decides which data to fetch, runs web searches for tariffs, trade defence and regulation, and writes the report |
| 🧭 | **IB frameworks** | PESTEL, CAGE distance, risk matrix, entry-mode recommendation, 90-day action plan |
| ⬇️ | **Export** | Markdown and print-ready HTML (save as PDF from the browser) |

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Data layer (src/data_sources.py)                             │
│  Eurostat Comext API · UN Comtrade API · World Bank API      │
│  → JSON-stat parsing, retries, rate-limit handling, cache    │
└──────────────────────────┬───────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ Analysis layer (src/analysis.py)                             │
│  market size · CAGR · supplier shares · HHI · score model    │
└──────────────────────────┬───────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ AI layer (src/agent.py)                                      │
│  Claude tool-use agent: 4 data tools + web search            │
│  → IB-framework report with sources                          │
└──────────────────────────┬───────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ App layer (app.py): Streamlit dashboard + AI report UI       │
└──────────────────────────────────────────────────────────────┘
```

## 🚀 Quick start

```bash
git clone <your-repo-url> && cd ai-market-entry-analyst
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your ANTHROPIC_API_KEY
streamlit run app.py
```

- The **data dashboard works without any API key.**
- The **AI report** needs an Anthropic API key ([console.anthropic.com](https://console.anthropic.com)).
- Optional: a free **UN Comtrade** key (`COMTRADE_API_KEY`) makes China data faster. Without one, the public preview API is used.

## ☁️ Deploy (Streamlit Community Cloud, free)

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **Create app** → pick the repo, branch `main`, main file `app.py`.
3. In **Advanced settings → Secrets**, add:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   DEMO_ACCESS_CODE = "choose-a-code"
   ```
   The data dashboard is public. The AI report needs either the demo access code (uses your key, limited to 3 reports per session) or the visitor's own API key.

## 📐 Methodology

**Market size.** Imports into the target market are the proxy for addressable demand: extra-EU imports (Eurostat `EXT_EU27_2020`) for the EU, China-reported imports for China (excluding re-imports of Chinese goods). Imports measure demand met from abroad, not total consumption.

**HHI.** Sum of squared supplier shares (%), from 0 to 10,000: below 1,000 is unconcentrated, 1,000 to 1,800 is moderately concentrated, above 1,800 is highly concentrated.

**Attractiveness score.**

| Component | Weight | Formula |
|---|---|---|
| Market size | 25% | 2 × (log10(value) − 6), capped 0-10 |
| Growth | 25% | 5 + CAGR / 3 |
| Competitive openness | 20% | 10 − HHI / 1000 |
| Institutional quality | 15% | mean WGI (−2.5…2.5) rescaled to 0-10 |
| Logistics | 15% | (LPI − 1) × 2.5 |

## 🧪 Example insight (real data)

**E-bikes (HS 871160) → EU-27, 2024:** extra-EU imports were **€1.57 bn** (8-year CAGR ≈ 10%). **China supplied 53.5%**, Taiwan 22.5% and Vietnam 8.1%. **HHI is 3,476 (highly concentrated)**, a clear supplier-dependency risk and an opening for alternative suppliers. The Netherlands is by far the largest EU importer from China. *(Source: Eurostat Comext DS-045409.)*

## 🗺️ Roadmap

- [ ] Tariff lookup via EU TARIC and China's customs tariff schedule
- [ ] Trade-defence tracker (EU anti-dumping and anti-subsidy cases on Chinese goods)
- [ ] Multi-market comparison (rank all 27 EU member states for a product)
- [ ] User accounts, saved reports and Stripe billing (freemium SaaS)
- [ ] Deploy to Streamlit Community Cloud

## 🛠️ Tech stack

Python · pandas · REST APIs (Eurostat SDMX/JSON-stat, UN Comtrade, World Bank) · Anthropic Claude API (tool use, web search) · Streamlit · Plotly

---

*Built by Onur Usalan (MSc International Business, BSc Management Information Systems).*
