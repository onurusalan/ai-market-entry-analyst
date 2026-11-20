"""
Rule-based market entry report engine (no paid AI service needed).

Combines live trade data, World Bank indicators and the curated knowledge base
with explicit decision rules to produce a full International Business report:
executive verdict, market sizing, competition, PESTEL, CAGE distance,
regulation, risk matrix, entry-mode recommendation and a 90-day plan.

Every rule is written out in code so the reasoning is auditable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from . import analysis
from . import knowledge as kb

COMPANY_SIZES = {"small": "Small (<50 staff)", "medium": "Mid-sized (50-250 staff)",
                 "large": "Large (250+ staff)"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def money(v: float | None, currency: str) -> str:
    if v is None:
        return "n/a"
    sym = "€" if currency == "EUR" else "$"
    for div, suf in ((1e9, " bn"), (1e6, " m"), (1e3, " k")):
        if abs(v) >= div:
            return f"{sym}{v / div:,.2f}{suf}"
    return f"{sym}{v:,.0f}"


def haversine_km(a: str, b: str) -> float | None:
    ca, cb = kb.COUNTRIES.get(a), kb.COUNTRIES.get(b)
    if not ca or not cb:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (ca["lat"], ca["lon"], cb["lat"], cb["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(h)), 0)


def _gov_avg(profile: dict | None) -> float | None:
    if not profile:
        return None
    vals = [profile.get(k) for k in analysis.GOV_KEYS if profile.get(k) is not None]
    return sum(vals) / len(vals) if vals else None


def _level(value: float, low: float, high: float) -> str:
    return "Low" if value < low else ("Medium" if value < high else "High")


def _name(iso2: str) -> str:
    return kb.COUNTRIES.get(iso2, {}).get("name", iso2)


# --------------------------------------------------------------------------- #
# Framework blocks
# --------------------------------------------------------------------------- #
def cage_analysis(home: str, target: str, home_p: dict | None, target_p: dict | None) -> dict:
    """CAGE distance (Ghemawat, 2001) with explicit, data-driven rules."""
    t_geo = "CN" if target == "CN" else ("EU" if target == "EU" else target)
    home_info, target_info = kb.COUNTRIES.get(home, {}), kb.COUNTRIES.get(t_geo, {})

    # Cultural: language family overlap
    hl, tl = home_info.get("lang", ""), target_info.get("lang", "")
    if target == "EU":
        cultural = "Medium"
        cultural_note = ("The EU spans 24 official languages; expect local-language marketing, "
                         "labels and service in each priority country.")
    elif hl and tl and (hl == tl or set(hl.split("/")) & set(tl.split("/"))):
        cultural, cultural_note = "Low", f"Shared language family ({tl})."
    else:
        cultural = "High" if "Sinitic" in (hl + tl) or "Japonic" in (hl + tl) else "Medium"
        cultural_note = f"Different language families ({hl or 'n/a'} vs {tl or 'n/a'}); localisation needed."

    # Administrative: trade bloc / FTA + governance gap
    in_eu = home in kb.EU27
    if target != "CN" and in_eu:
        admin, admin_note = "Low", "Same EU single market and customs union: no tariffs or customs formalities."
    elif target != "CN" and home in kb.EU_FTA_PARTNERS:
        admin, admin_note = "Medium", f"Preferential access via {kb.EU_FTA_PARTNERS[home]}; rules of origin apply."
    elif target == "CN" and home in kb.CN_FTA_PARTNERS:
        admin, admin_note = "Medium", f"Preferential access via {kb.CN_FTA_PARTNERS[home]}."
    else:
        admin = "High"
        admin_note = ("No free-trade agreement: MFN tariffs, separate standards and customs procedures."
                      if not (target == "CN" and in_eu) else
                      "No EU-China FTA: MFN tariffs, CCC/GB standards, distinct legal system and growing trade tension.")
    gh, gt = _gov_avg(home_p), _gov_avg(target_p)
    if gh is not None and gt is not None and abs(gh - gt) > 1.0:
        admin_note += f" Large governance gap (WGI {gh:+.2f} vs {gt:+.2f})."
        if admin == "Medium":
            admin = "High"

    # Geographic: great-circle distance between capitals
    km = haversine_km(home, t_geo)
    geo = _level(km, 1500, 5000) if km is not None else "Medium"
    geo_note = f"~{km:,.0f} km between capitals." if km is not None else "Distance unknown."
    if geo == "High":
        geo_note += " Long lead times (Asia-Europe sea freight ~30-45 days; China-Europe rail ~15-20 days)."

    # Economic: GDP per capita ratio
    ph = (home_p or {}).get("gdp_per_capita_usd")
    pt = (target_p or {}).get("gdp_per_capita_usd")
    if ph and pt:
        ratio = max(ph, pt) / min(ph, pt)
        econ = _level(ratio, 1.5, 3.0)
        econ_note = f"GDP per capita ${ph:,.0f} (home) vs ${pt:,.0f} (target), ratio {ratio:.1f}x."
    else:
        econ, econ_note = "Medium", "Income data incomplete."

    levels = {"Low": 1, "Medium": 2, "High": 3}
    dims = {"Cultural": (cultural, cultural_note), "Administrative": (admin, admin_note),
            "Geographic": (geo, geo_note), "Economic": (econ, econ_note)}
    overall = sum(levels[v[0]] for v in dims.values()) / 4
    return {"dimensions": dims, "overall": overall,
            "overall_label": _level(overall, 1.75, 2.5), "distance_km": km}


def pestel(target: str, sector: str, market: dict, target_p: dict | None) -> dict:
    base_key = "CN" if target == "CN" else "EU"
    out = dict(kb.PESTEL_BASE[base_key])
    for factor, hint in kb.PESTEL_SECTOR_HINTS.get(sector, {}).items():
        out[factor] = out[factor] + " " + hint
    if target_p:
        g = target_p.get("gdp_growth_pct")
        inf = target_p.get("inflation_pct")
        bits = []
        if g is not None:
            bits.append(f"GDP growth {g:.1f}% ({target_p.get('gdp_growth_pct_year')})")
        if inf is not None:
            bits.append(f"inflation {inf:.1f}%")
        if bits:
            out["Economic"] += " Latest: " + ", ".join(bits) + " (World Bank)."
    if target not in ("EU", "CN"):
        out["Economic"] = f"{_name(target)}: " + out["Economic"]
    return out


def risk_matrix(target: str, home: str, sector: str, market: dict, score: dict,
                cage: dict, hs_code: str) -> list[dict]:
    risks = []
    top = (market.get("top_suppliers_latest_year") or [{}])[0]
    if market.get("hhi", 0) > 1800 and top:
        risks.append({"risk": f"Dominant incumbent supplier ({top.get('partner_name')}, {top.get('share_pct')}% share)",
                      "likelihood": "High", "impact": "High",
                      "mitigation": "Differentiate on quality, service, sustainability and EU/China-specific certification rather than price."})
    if (market.get("cagr_pct") or 0) < 0:
        risks.append({"risk": "Shrinking import demand", "likelihood": "High", "impact": "Medium",
                      "mitigation": "Target growing niches or member states; validate demand before fixed investment."})
    if hs_code in kb.TRADE_DEFENCE_NOTES or (target != "CN" and home == "CN") or (target == "CN" and home in kb.EU27):
        risks.append({"risk": "Trade-defence or retaliation measures in the EU-China corridor",
                      "likelihood": "Medium" if hs_code not in kb.TRADE_DEFENCE_NOTES else "High",
                      "impact": "High",
                      "mitigation": "Monitor trade-defence notices; diversify sourcing and production locations; build tariff scenarios into pricing."})
    if sector in ("pharma", "medtech", "agrifood", "cosmetics"):
        risks.append({"risk": "Long regulatory approval / registration timeline", "likelihood": "High",
                      "impact": "High", "mitigation": "Start registration early with a local regulatory agent; budget 6-24 months."})
    if score["sub_scores"].get("institutional_quality", 10) < 5:
        risks.append({"risk": "Institutional and IP-protection risk", "likelihood": "Medium", "impact": "High",
                      "mitigation": "Register trademarks and patents locally before entry; use contracts with local arbitration (e.g. CIETAC/HKIAC)."})
    if cage["dimensions"]["Geographic"][0] == "High":
        risks.append({"risk": "Logistics disruption (Red Sea, port congestion, freight-rate swings)",
                      "likelihood": "Medium", "impact": "Medium",
                      "mitigation": "Use mixed sea/rail routing, safety stock in a regional hub, Incoterms that share freight risk."})
    if cage["dimensions"]["Cultural"][0] != "Low":
        risks.append({"risk": "Brand and message mis-fit with local consumers", "likelihood": "Medium",
                      "impact": "Medium", "mitigation": "Local consumer testing, native-language content, local marketplace and social channels."})
    risks.append({"risk": "Currency volatility (EUR/CNY/USD)", "likelihood": "Medium", "impact": "Medium",
                  "mitigation": "Price in home currency where possible; hedge large contracts with forwards."})
    return risks


def entry_mode(target: str, sector: str, company_size: str, score: dict, cage: dict,
               market: dict) -> dict:
    """
    Entry-mode choice following the transaction-cost / OLI logic:
    higher distance and risk -> lower commitment; larger, attractive markets
    and bigger firms -> more control.
    """
    s = score["score_0_10"]
    distance = cage["overall"]
    inst = score["sub_scores"]["institutional_quality"]
    size_rank = {"small": 0, "medium": 1, "large": 2}[company_size]
    reasons = []

    if target == "CN" and sector in ("pharma", "medtech"):
        mode = "Joint venture or licensing with an established Chinese partner"
        reasons += ["Regulated sector: registration, distribution and hospital access depend on local relationships.",
                    "A partner shares regulatory and market risk while you keep IP protected by contract."]
    elif target == "CN" and sector == "agrifood":
        mode = "Exclusive Chinese importer-distributor, supported by cross-border e-commerce"
        reasons += ["Food and beverage imports need a licensed Chinese importer for customs, GACC compliance and labelling.",
                    "Cross-border e-commerce builds brand awareness with consumers before scaling through general trade."]
    elif target == "CN" and sector in ("cosmetics", "consumer", "textiles") and size_rank < 2:
        mode = "Cross-border e-commerce first (e.g. Tmall Global), then a local distributor"
        reasons += ["Cross-border e-commerce lets consumer brands test demand with lighter registration and low fixed cost.",
                    "Move to general trade with a distributor once sales prove the concept."]
    elif s < 5 or (distance >= 2.5 and size_rank == 0):
        mode = "Indirect / direct exporting via importers and distributors"
        reasons += ["Moderate attractiveness or high distance favour a low-commitment, reversible entry.",
                    "Keeps capital at risk low while you learn the market."]
    elif s >= 6.5 and size_rank == 2 and inst >= 6 and (distance < 2.5 or s >= 7.5):
        mode = "Wholly owned sales subsidiary (later local assembly if volumes justify)"
        reasons += ["Attractive market and strong institutions justify full control for a large firm.",
                    "A subsidiary captures the full margin and builds direct customer relationships."]
        if distance >= 2.5:
            reasons.append("High distance is managed through the subsidiary itself: local management, "
                           "a regional warehouse and, at scale, local assembly to reduce tariff and logistics exposure.")
    elif target == "CN" and size_rank == 2 and s >= 6:
        mode = "WFOE (wholly foreign-owned enterprise) for sales and service"
        reasons += ["Most sectors allow full foreign ownership under the Foreign Investment Law.",
                    "Control over brand, pricing and IP outweighs higher set-up cost for a large firm."]
    else:
        mode = "Exclusive distributor or agent, with a small local sales office"
        reasons += ["Balances control and cost for a mid-attractiveness market.",
                    "A distributor brings market access; a sales office protects the brand and gathers market intelligence."]

    if target == "EU":
        reasons.append("Within the EU one CE-compliant product and one importer of record give access to all 27 markets: start with 2-3 priority countries.")
    reasons.append(f"Inputs: attractiveness {s}/10, CAGE distance {cage['overall_label'].lower()}, "
                   f"institutional quality {inst}/10, company size {COMPANY_SIZES[company_size].lower()}.")
    return {"mode": mode, "reasons": reasons}


def verdict(score: dict, risks: list[dict]) -> tuple[str, str]:
    s = score["score_0_10"]
    severe = sum(1 for r in risks if r["likelihood"] == "High" and r["impact"] == "High")
    if s >= 6.5 and severe <= 1:
        return "ENTER", "Attractive market with manageable risks."
    if s >= 5:
        return "ENTER WITH CAUTION", "Real opportunity, but specific risks need a mitigation plan before scaling."
    return "DO NOT ENTER NOW", "Limited attractiveness at present; monitor and revisit."


def action_plan(target: str, sector: str, mode: str, priority: list[str]) -> list[str]:
    where = ", ".join(priority) if priority else _name(target)
    plan = [
        "**Days 1-30, validate:** confirm the HS code and duty rate on official tariff tools, size the niche with customer interviews, shortlist 10 potential partners or channels in " + where + ".",
        "**Days 1-30, compliance:** map required certifications and labelling (see section 6), get quotes from a test lab or regulatory agent, register trademarks in the target market.",
        "**Days 31-60, commercial model:** build a landed-cost and pricing model (duties, freight, VAT, channel margins, FX), and draft the partner or channel agreement.",
        "**Days 31-60, go-to-market:** localise product pages, packaging and sales material; pick 1-2 launch channels consistent with the entry mode: " + mode.lower() + ".",
        "**Days 61-90, pilot:** ship a pilot order or open the online store, track sell-through, margin and customer feedback against go/no-go KPIs.",
    ]
    if sector in ("pharma", "medtech", "agrifood", "cosmetics"):
        plan.insert(2, "**Days 1-30, registration:** file the product registration / notification early: it is the critical path.")
    return plan


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
@dataclass
class Report:
    title: str
    markdown: str
    data: dict = field(default_factory=dict)


def generate_report(hs_code: str, target: str, home: str, company: str = "",
                    company_size: str = "medium", start_year: int | None = None,
                    end_year: int | None = None, product_label: str = "") -> Report:
    """
    Build the full report.

    target: "EU", an EU member ISO2 code, or "CN".  home: ISO2 of the company's home country.
    """
    end_year = end_year or date.today().year - 2
    start_year = start_year or end_year - 5
    target = target.upper()
    home = home.upper()

    if target == "CN":
        market = analysis.analyze_china_market(hs_code, start_year, end_year)
    else:
        market = analysis.analyze_eu_market(hs_code, start_year, end_year, target)
    if "error" in market:
        raise ValueError(market["error"])

    sector = kb.sector_for(hs_code)
    target_p = analysis.profile_for(target)
    home_p = analysis.profile_for(home)
    score = analysis.attractiveness_score(market, target_p)
    cage = cage_analysis(home, target, home_p, target_p)
    risks = risk_matrix(target, home, sector, market, score, cage, hs_code)
    mode = entry_mode(target, sector, company_size, score, cage, market)
    v, v_reason = verdict(score, risks)

    ranking = analysis.rank_eu_members(hs_code, start_year, end_year) if target == "EU" else []
    priority = [_name(r["member"]) for r in ranking[:3]]

    cur = market["currency"]
    product = product_label or market.get("product_name") or f"HS {hs_code}"
    target_name = "EU-27" if target == "EU" else _name(target)
    title = f"Market Entry Report: {product} → {target_name}"
    ly = market["latest_year"]
    top = market["top_suppliers_latest_year"]

    md: list[str] = [f"# {title}", ""]
    md.append(f"*Company: {company or 'n/a'} · Home country: {_name(home)} · Size: {COMPANY_SIZES[company_size]} · "
              f"HS {hs_code} ({kb.SECTOR_LABELS[sector]}) · Generated {date.today().isoformat()}*")
    md.append("")

    # 1. Executive summary
    md += ["## 1. Executive Summary", "",
           f"**Verdict: {v}.** {v_reason}", "",
           f"**Market attractiveness: {score['score_0_10']}/10**  ",
           f"**Recommended entry mode:** {mode['mode']}", ""]
    key_points = [
        f"Import market of {money(market['latest_market_size'], cur)} in {ly}"
        + (f", growing {market['cagr_pct']}% a year since {market['years'][0]}." if market['cagr_pct'] is not None else "."),
        f"Supply is {market['hhi_label'].split(' (')[0].lower()} (HHI {market['hhi']:,.0f}); "
        f"top supplier {top[0]['partner_name']} holds {top[0]['share_pct']}%." if top else "No supplier data.",
        f"CAGE distance from {_name(home)}: {cage['overall_label'].lower()}.",
    ]
    if target == "EU" and "china_share_pct_by_year" in market:
        key_points.append(f"China supplies {market['china_share_pct_by_year'].get(ly)}% of extra-EU imports.")
    if target == "CN":
        key_points.append(f"EU-27 suppliers hold {market['eu27_share_pct_by_year'].get(ly)}% of China's imports.")
    if priority:
        key_points.append("Priority EU markets: " + ", ".join(priority) + ".")
    md += [f"- {p}" for p in key_points] + [""]

    # 2. Market size
    md += ["## 2. Market Size & Growth", "",
           f"Market size is measured as imports into {target_name} ({market['source']}). Imports show demand served from abroad, not total consumption.", "",
           f"| Year | Imports ({cur}) |", "|---|---|"]
    md += [f"| {y} | {money(val, cur)} |" for y, val in market["import_market_size_by_year"].items()]
    md += ["", f"CAGR {market['years'][0]}-{ly}: **{market['cagr_pct']}%**." if market["cagr_pct"] is not None else "", ""]

    # 3. Competition
    md += ["## 3. Competitive Landscape", "",
           f"| Rank | Supplier | Imports {ly} | Share |", "|---|---|---|---|"]
    md += [f"| {i} | {s['partner_name']} | {money(s['value'], cur)} | {s['share_pct']}% |" for i, s in enumerate(top, 1)]
    md += ["", f"**HHI {market['hhi']:,.0f}: {market['hhi_label']}.** "
           + ("A few suppliers dominate, so a newcomer must win share from incumbents or exploit buyers' wish to diversify supply (EU 'de-risking')."
              if market["hhi"] > 1800 else
              "Supply is reasonably spread, so there is room for a differentiated new entrant."), ""]
    if target == "EU" and market.get("china_share_pct_by_year"):
        trend = market["china_share_pct_by_year"]
        first_y = min(trend)
        md += [f"China's share of extra-EU imports moved from {trend[first_y]}% ({first_y}) to {trend[ly]}% ({ly}).", ""]
    if target == "CN" and market.get("eu27_share_pct_by_year"):
        trend = market["eu27_share_pct_by_year"]
        first_y = min(trend)
        md += [f"The EU-27's share of China's imports moved from {trend[first_y]}% ({first_y}) to {trend[ly]}% ({ly}).", ""]

    # 3b. Priority markets
    if ranking:
        md += ["### Priority EU member states", "",
               "Ranked on total imports (demand incl. intra-EU trade), growth, purchasing power, logistics and institutions.", "",
               "| Rank | Country | Imports | Share of EU | CAGR | Score |", "|---|---|---|---|---|---|"]
        md += [f"| {r['rank']} | {_name(r['member'])} | {money(r['imports_eur'], 'EUR')} | {r['share_of_eu_pct']}% | "
               f"{r['cagr_pct']}% | {r['score_0_10']} |" for r in ranking[:8]]
        md += ["", "*Note: the Netherlands and Belgium also import for re-export through Rotterdam and Antwerp.*", ""]

    # 4. PESTEL
    md += ["## 4. PESTEL Analysis", ""]
    md += [f"- **{k}:** {val}" for k, val in pestel(target, sector, market, target_p).items()] + [""]

    # 5. CAGE
    md += ["## 5. CAGE Distance", "", "| Dimension | Distance | Evidence |", "|---|---|---|"]
    md += [f"| {d} | {lvl} | {note} |" for d, (lvl, note) in cage["dimensions"].items()]
    md += ["", f"**Overall distance: {cage['overall_label']}.**", ""]

    # 6. Regulation
    reg_src = kb.CN_REGULATION if target == "CN" else kb.EU_REGULATION
    md += ["## 6. Tariffs, Trade Defence & Regulation", ""]
    if hs_code in kb.TRADE_DEFENCE_NOTES:
        md += [f"> ⚠️ **Trade defence:** {kb.TRADE_DEFENCE_NOTES[hs_code]}", ""]
    md += [f"- {r}" for r in reg_src.get(sector, []) + reg_src["_all"]]
    md += ["", "**Verify current duties and requirements:**"]
    md += [f"- [{label}]({url})" for label, url in kb.VERIFY_SOURCES["CN" if target == "CN" else "EU"]] + [""]

    # 7. Risks
    md += ["## 7. Risk Matrix", "", "| Risk | Likelihood | Impact | Mitigation |", "|---|---|---|---|"]
    md += [f"| {r['risk']} | {r['likelihood']} | {r['impact']} | {r['mitigation']} |" for r in risks] + [""]

    # 8. Entry mode
    md += ["## 8. Recommended Entry Mode", "", f"**{mode['mode']}**", ""]
    md += [f"- {r}" for r in mode["reasons"]] + [""]

    # 9. Score breakdown
    names = {"market_size": "Market size", "growth": "Growth", "competitive_openness": "Competitive openness",
             "institutional_quality": "Institutional quality", "logistics": "Logistics"}
    md += ["## 9. Attractiveness Score Breakdown", "", "| Component | Weight | Score |", "|---|---|---|"]
    md += [f"| {names[k]} | {int(score['weights'][k] * 100)}% | {val}/10 |" for k, val in score["sub_scores"].items()]
    md += [f"| **Total** | | **{score['score_0_10']}/10** |", ""]

    # 10. Plan
    md += ["## 10. 90-Day Action Plan", ""]
    md += [f"{i}. {step}" for i, step in enumerate(action_plan(target, sector, mode["mode"], priority), 1)] + [""]

    md += ["## Sources", "",
           f"- {market['source']}, accessed {date.today().isoformat()}",
           "- World Bank World Development Indicators, Logistics Performance Index, Worldwide Governance Indicators",
           "- Regulatory notes: curated from official EU and Chinese sources; verify with the links in section 6",
           "- Frameworks: PESTEL; CAGE distance (Ghemawat, 2001); HHI bands (US DOJ/FTC 2023); entry-mode logic (Dunning's OLI, transaction-cost theory)", ""]

    return Report(title=title, markdown="\n".join(md), data={
        "market": market, "score": score, "cage": {k: v for k, v in cage.items() if k != "dimensions"},
        "cage_dimensions": {k: v[0] for k, v in cage["dimensions"].items()},
        "risks": risks, "entry_mode": mode, "verdict": v, "ranking": ranking, "sector": sector,
    })
