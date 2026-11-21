"""
AI layer (experimental, optional): a Claude agent that researches a market-entry question with real data
and writes a structured International Business report.

The agent decides which tools to call (EU trade data, China trade data,
country fundamentals, scoring, web search for current regulation/news),
then applies IB frameworks (PESTEL, CAGE, Porter, entry modes) to the results.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic
from anthropic import beta_tool

from . import analysis

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are a senior International Business strategy analyst specialising in \
EU-China trade. You help companies decide whether and how to enter the EU or Chinese market.

How you work:
1. Identify the product's HS6 code (use your knowledge of the Harmonized System; state the code \
and its description in the report). If several codes fit, pick the most specific one and say so.
2. Gather evidence with the tools. Always call the trade-data tool for the target market and \
country_profiles for the relevant countries before drawing conclusions. Use web_search for \
current tariffs, trade-defence measures (anti-dumping / anti-subsidy duties), regulations \
(e.g. CE marking, CCC certification, CBAM, EU Battery Regulation, China export controls) and \
recent EU-China news that affects the product.
3. Analyse with IB frameworks and write the report.

Rules on evidence:
- Every number you report must come from a tool result or a cited web source. Never invent figures.
- Name the source next to key numbers (e.g. "Eurostat Comext, 2024"). Keep currencies explicit: \
Eurostat data is in EUR, UN Comtrade data is in USD.
- Trade data measures imports, which is a proxy for the addressable market, not total consumption. \
Say so once.
- If data is missing or a tool fails, say what is missing instead of guessing.

Report format (Markdown, in the language the user writes in; keep framework names in English):
# Market Entry Report: <product> -> <target market>
## 1. Executive Summary  (verdict: Enter / Enter with caution / Do not enter now; the attractiveness \
score from the scoring tool; 3-5 key reasons)
## 2. Market Size & Growth  (import market size, CAGR, trend; a small Markdown table)
## 3. Competitive Landscape  (top suppliers with shares, HHI and what it means, China's / EU's share trend)
## 4. PESTEL Analysis  (one short bullet per factor, specific to this product and market)
## 5. CAGE Distance  (Cultural, Administrative, Geographic, Economic distance between the \
company's home country and the target market; rate each Low/Medium/High)
## 6. Tariffs, Trade Defence & Regulation  (duties, anti-dumping/anti-subsidy measures, \
certifications, upcoming rules; cite sources)
## 7. Risk Matrix  (Markdown table: risk, likelihood, impact, mitigation)
## 8. Recommended Entry Mode  (exporting / distributor / licensing / JV / WFOE or subsidiary / \
acquisition, with reasoning tied to the evidence; mention the first 2-3 target countries or \
regions where relevant)
## 9. 90-Day Action Plan  (concrete next steps)
## Sources
Be concise and analytical, like a top-tier consulting deliverable. No filler."""


# --------------------------------------------------------------------------- #
# Tools the agent can call
# --------------------------------------------------------------------------- #
def _to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


@beta_tool
def eu_market_data(hs_code: str, start_year: int = 2015, end_year: int = 2024,
                   reporter: str = "EU") -> str:
    """Get EU import data for one product from Eurostat Comext: import market size by year (EUR),
    growth (CAGR), top non-EU supplier countries with market shares, HHI supplier concentration,
    China's share over time, and which EU member states import most from China.
    Use this when the target market is the EU or an EU member state.

    Args:
        hs_code: 6-digit Harmonized System product code, e.g. "871160" for e-bikes.
        start_year: First year of the series (data usually available from 2002; latest is ~1 year ago).
        end_year: Last year of the series.
        reporter: "EU" for EU-27 total, or an ISO2 member-state code such as "DE", "FR", "IT".
    """
    try:
        return _to_json(analysis.analyze_eu_market(hs_code, start_year, end_year, reporter))
    except Exception as exc:  # return errors to the model instead of crashing the loop
        return _to_json({"error": str(exc)})


@beta_tool
def china_market_data(hs_code: str, start_year: int = 2019, end_year: int = 2024) -> str:
    """Get China's import data for one product from UN Comtrade: import market size by year (USD),
    growth (CAGR), top supplier countries with shares, HHI concentration, and the EU-27's share
    over time. Use this when the target market is China.

    Args:
        hs_code: 6-digit Harmonized System product code.
        start_year: First year of the series.
        end_year: Last year of the series (latest available is usually last year).
    """
    try:
        return _to_json(analysis.analyze_china_market(hs_code, start_year, end_year))
    except Exception as exc:
        return _to_json({"error": str(exc)})


@beta_tool
def country_profiles(iso2_codes: list[str]) -> str:
    """Get World Bank fundamentals for countries: GDP, GDP per capita, GDP growth, population,
    inflation, Logistics Performance Index (1-5) and the four Worldwide Governance Indicators
    (rule of law, regulatory quality, political stability, control of corruption; -2.5 to 2.5).
    Use "EU" for the European Union aggregate.

    Args:
        iso2_codes: ISO 3166 alpha-2 country codes, e.g. ["CN", "DE", "FR"].
    """
    try:
        return _to_json(analysis.country_profiles(iso2_codes))
    except Exception as exc:
        return _to_json({"error": str(exc)})


@beta_tool
def market_attractiveness_score(target_market: str, hs_code: str, start_year: int = 2019,
                                end_year: int = 2024, profile_country: str = "") -> str:
    """Compute the platform's transparent 0-10 market attractiveness score (market size, growth,
    competitive openness, institutional quality, logistics) for a product in a target market.
    Always call this once and report the score and sub-scores in the executive summary.

    Args:
        target_market: "EU", an EU member ISO2 code (e.g. "DE"), or "CN" for China.
        hs_code: 6-digit Harmonized System product code.
        start_year: First year used for growth.
        end_year: Last year used for growth and size.
        profile_country: ISO2 code whose institutions/logistics to score (defaults to the target market).
    """
    try:
        if target_market.upper() in ("CN", "CHINA"):
            market = analysis.analyze_china_market(hs_code, start_year, end_year)
            country = profile_country or "CN"
        else:
            market = analysis.analyze_eu_market(hs_code, start_year, end_year, target_market.upper())
            country = profile_country or target_market.upper()
        if "error" in market:
            return _to_json(market)
        profiles = analysis.country_profiles([country])
        return _to_json(analysis.attractiveness_score(market, profiles[0] if profiles else None))
    except Exception as exc:
        return _to_json({"error": str(exc)})


@beta_tool
def rule_based_entry_report(hs_code: str, target_market: str, home_country: str,
                            company_size: str = "medium") -> str:
    """Run the platform's own rule-based entry engine and return its verdict, score, tariff,
    landed cost, competitive position and entry mode. Use it as the quantitative baseline.

    Args:
        hs_code: 6-digit HS product code.
        target_market: "EU" or "CN".
        home_country: ISO2 code of the company's home country.
        company_size: "small", "medium" or "large".
    """
    from .report_engine import generate_report
    try:
        d = generate_report(hs_code, target_market, home_country, company_size=company_size).data
        return _to_json({k: d[k] for k in ("verdict", "score", "entry_mode", "tariff", "landed_cost",
                                           "position", "sensitivity", "data_quality", "cage")})
    except Exception as exc:  # report the error to the model instead of crashing the loop
        return _to_json({"error": str(exc)})


TOOLS: list[Any] = [
    rule_based_entry_report,
    eu_market_data,
    china_market_data,
    country_profiles,
    market_attractiveness_score,
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 6},
]

TOOL_LABELS = {
    "rule_based_entry_report": "Running the rule-based entry engine",
    "eu_market_data": "Eurostat: pulling EU import data",
    "china_market_data": "UN Comtrade: pulling China import data",
    "country_profiles": "World Bank: pulling country indicators",
    "market_attractiveness_score": "Computing the attractiveness score",
    "web_search": "Web: checking current tariffs, regulation and news",
}


# --------------------------------------------------------------------------- #
# Running the agent
# --------------------------------------------------------------------------- #
@dataclass
class AgentResult:
    report_markdown: str
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None


def build_prompt(company: str, product: str, home_country: str, target_market: str,
                 extra: str = "") -> str:
    prompt = (
        f"Company: {company or 'not specified'}\n"
        f"Product: {product}\n"
        f"Company home country: {home_country}\n"
        f"Target market: {target_market}\n"
    )
    if extra:
        prompt += f"Additional context: {extra}\n"
    prompt += "\nPrepare the full market entry report."
    return prompt


def run_agent(user_prompt: str, on_event: Callable[[str, dict], None] | None = None,
              client: anthropic.Anthropic | None = None) -> AgentResult:
    """
    Run the research agent to completion.

    on_event(kind, payload) is called as the agent works, so a UI can show progress:
      kind = "tool"     payload = {"name": ..., "input": {...}}
      kind = "thinking" payload = {}
    """
    client = client or anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        # If a request is declined by a safety classifier, let the API retry on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        max_iterations=20,
        messages=[{"role": "user", "content": user_prompt}],
    )

    result = AgentResult(report_markdown="")
    final_message = None
    for message in runner:
        final_message = message
        if message.usage:
            result.input_tokens += message.usage.input_tokens or 0
            result.output_tokens += message.usage.output_tokens or 0
        for block in message.content:
            if block.type in ("tool_use", "server_tool_use"):
                call = {"name": block.name, "input": block.input}
                result.tool_calls.append(call)
                if on_event:
                    on_event("tool", call)

    if final_message is None:
        raise RuntimeError("The agent returned no response.")

    result.stop_reason = final_message.stop_reason
    if final_message.stop_reason == "refusal":
        result.report_markdown = "The model declined this request. Try rephrasing the product or market."
        return result

    result.report_markdown = "".join(
        block.text for block in final_message.content if block.type == "text"
    ).strip()
    if final_message.stop_reason == "max_tokens":
        result.report_markdown += "\n\n_(Report was cut off by the output limit.)_"
    return result
