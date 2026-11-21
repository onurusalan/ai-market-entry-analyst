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
    vals = [float(profile[k]) for k in analysis.GOV_KEYS if profile.get(k) is not None]
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
                cage: dict, hs_code: str, tariff: dict | None = None) -> list[dict]:
    risks = []
    rate = (tariff or {}).get("applicable_pct")
    if rate is not None and rate >= 10:
        risks.append({"risk": f"High import tariff ({rate:g}% applicable)", "likelihood": "High", "impact": "Medium",
                      "mitigation": "Price the duty into the landed cost; consider local assembly, a bonded warehouse or sourcing from an FTA partner."})
    top = (market.get("top_suppliers_latest_year") or [{}])[0]
    if market.get("hhi", 0) > 1800 and top:
        risks.append({"risk": f"Dominant incumbent supplier ({top.get('partner_name')}, {top.get('share_pct')}% share)",
                      "likelihood": "High", "impact": "High",
                      "mitigation": "Differentiate on quality, service, sustainability and EU/China-specific certification rather than price."})
    growth = market.get("growth_trend_pct", market.get("cagr_pct"))
    if (growth or 0) < 0:
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
    if (market.get("data_quality") or {}).get("confidence") == "Low":
        risks.append({"risk": "Thin or volatile trade data: market size and growth are uncertain", "likelihood": "Medium",
                      "impact": "Medium", "mitigation": "Validate demand with distributor interviews and a small pilot before committing budget."})
    risks.append({"risk": "Currency volatility (EUR/CNY/USD)", "likelihood": "Medium", "impact": "Medium",
                  "mitigation": "Price in home currency where possible; hedge large contracts with forwards."})
    return risks


def entry_mode(target: str, sector: str, company_size: str, score: dict, cage: dict,
               market: dict, position: dict | None = None) -> dict:
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

    if position and position.get("present") and (position.get("share_pct") or 0) >= 5:
        reasons.append(f"Your home country already supplies {position['share_pct']}% of this market (rank {position['rank']}): "
                       "existing importers and logistics routes lower the cost of entry, so partner with established importers first.")
    elif position is not None and not (position.get("present") and (position.get("share_pct") or 0) >= 1):
        reasons.append("Your home country is not yet an established supplier here: buyers will need proof of quality, so plan for samples, certification and references.")
    if position and position.get("price_position") == "Premium":
        reasons.append("Home-country exports are priced above the market average: position on quality and brand, with selective distribution.")
    elif position and position.get("price_position") == "Value":
        reasons.append("Home-country exports are priced below the market average: compete on value through volume channels and B2B buyers.")
    if target == "EU":
        reasons.append("Within the EU one CE-compliant product and one importer of record give access to all 27 markets: start with 2-3 priority countries.")
    reasons.append(f"Inputs: attractiveness {s}/10, CAGE distance {cage['overall_label'].lower()}, "
                   f"institutional quality {inst}/10, company size {COMPANY_SIZES[company_size].lower()}.")
    return {"mode": mode, "reasons": reasons}


def tariff_position(target: str, home: str, hs_code: str, mfn: dict | None, pref: dict | None = None) -> dict:
    """
    MFN rate from WITS plus the rate this home country is likely to pay. Priority: a partner-specific
    preferential rate published by WITS, then an FTA assumption (0%), then MFN.
    """
    fta = (kb.CN_FTA_PARTNERS.get(home) if target == "CN" else kb.EU_FTA_PARTNERS.get(home))
    if target != "CN" and home in kb.EU27:
        return {"mfn": mfn, "applicable_pct": 0.0, "basis": "Intra-EU trade: no customs duty", "fta": None}
    mfn_rate = mfn["rate_pct"] if mfn else None
    extra = kb.TRADE_DEFENCE_NOTES.get(hs_code) if (target != "CN" and home == "CN") or target == "CN" else None
    if pref and pref.get("type") == "PREF" and pref.get("rate_pct") is not None:
        label = fta or kb.EU_GSP_BENEFICIARIES.get(home) if target != "CN" else fta
        label = label or "a preferential scheme"
        return {"mfn": mfn, "applicable_pct": pref["rate_pct"], "fta": fta, "trade_defence": extra, "pref": pref,
                "basis": f"Preferential rate under {label}, published by WITS for {pref['year']} "
                         f"(rules of origin apply; MFN {mfn_rate if mfn_rate is not None else 'n/a'}% otherwise)"}
    rate: float | None
    if fta and mfn_rate is not None:
        rate, basis = kb.FTA_DEFAULT_PREF_RATE, f"Preferential rate under {fta} (if rules of origin are met; MFN {mfn_rate}% otherwise)"
    else:
        rate, basis = mfn_rate, "MFN rate (no free-trade agreement)" if mfn_rate is not None else "Tariff data unavailable"
    return {"mfn": mfn, "applicable_pct": rate, "basis": basis, "fta": fta, "trade_defence": extra}


def needs_partner_lookup(target: str, home: str) -> bool:
    """Partner-specific rates exist only for FTA partners and GSP beneficiaries."""
    if target == "CN":
        return home in kb.CN_FTA_PARTNERS
    return home not in kb.EU27 and (home in kb.EU_FTA_PARTNERS or home in kb.EU_GSP_BENEFICIARIES)


FREIGHT_PCT = {"Low": 3.0, "Medium": 6.0, "High": 10.0}  # freight + insurance as % of goods value


def landed_cost(goods_value: float, freight_pct: float, duty_pct: float, vat_pct: float,
                other_pct: float = 1.5) -> dict:
    """
    Landed cost of an import, in the same currency as goods_value.
    Customs value = goods + freight/insurance (CIF basis, as in EU and Chinese customs);
    duty on the customs value; import VAT on customs value + duty; other = clearance, broker, port fees.
    """
    freight = goods_value * freight_pct / 100
    customs_value = goods_value + freight
    duty = customs_value * duty_pct / 100
    other = goods_value * other_pct / 100
    vat = (customs_value + duty) * vat_pct / 100
    total = customs_value + duty + other + vat
    return {"goods": round(goods_value, 2), "freight_insurance": round(freight, 2), "duty": round(duty, 2),
            "clearance_other": round(other, 2), "import_vat": round(vat, 2), "landed_total": round(total, 2),
            "landed_ex_vat": round(total - vat, 2), "uplift_ex_vat_pct": round((total - vat) / goods_value * 100 - 100, 1),
            "assumptions": {"freight_pct": freight_pct, "duty_pct": duty_pct, "vat_pct": vat_pct, "other_pct": other_pct}}


def competitive_position(home: str, market: dict) -> dict:
    """Where the home country already stands in the target market, and at what price level."""
    pos = (market.get("supplier_positions") or {}).get(home)
    sup = {s["partner"]: s for s in market.get("top_suppliers_latest_year", [])}
    avg_uv = market.get("unit_value_per_kg")
    out = {"present": bool(pos), "rank": None, "share_pct": None, "share_change_pp": None,
           "unit_value_per_kg": None, "market_unit_value_per_kg": avg_uv, "price_position": None}
    if pos:
        shares = pos["share_by_year"]
        ly, fy = max(shares), min(shares)
        out.update(rank=pos["rank"], suppliers=pos["suppliers"], share_pct=shares[ly],
                   share_change_pp=round(shares[ly] - shares[fy], 2), first_year=fy)
    uv = sup.get(home, {}).get("unit_value_per_kg")
    if uv and avg_uv:
        ratio = uv / avg_uv
        out["unit_value_per_kg"] = uv
        out["price_position"] = ("Premium" if ratio >= 1.25 else "Value" if ratio <= 0.8 else "Mid-market")
        out["price_ratio"] = round(ratio, 2)
    return out


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


@dataclass
class Case:
    """Every input and computed result for one entry question; rendered by report_markdown."""
    hs_code: str
    target: str
    home: str
    company: str
    company_size: str
    market: dict
    sector: str
    target_profile: dict | None
    score: dict
    sensitivity: dict
    cage: dict
    tariff: dict
    position: dict
    risks: list[dict]
    mode: dict
    verdict: str
    verdict_reason: str
    data_quality: dict
    kb_info: dict
    ranking: list[dict]
    vat_country: str
    cost: dict
    growth: float | None
    product: str

    @property
    def currency(self) -> str:
        return self.market["currency"]

    @property
    def latest_year(self) -> int:
        return self.market["latest_year"]

    @property
    def target_name(self) -> str:
        return "EU-27" if self.target == "EU" else _name(self.target)

    @property
    def title(self) -> str:
        return f"Market Entry Report: {self.product} → {self.target_name}"

    @property
    def priority(self) -> list[str]:
        return [_name(r["member"]) for r in self.ranking[:3]]

    def data(self) -> dict:
        """The machine-readable part of the report (used by the web app and the AI agent)."""
        return {
            "market": self.market, "score": self.score,
            "cage": {k: v for k, v in self.cage.items() if k != "dimensions"},
            "cage_dimensions": {k: v[0] for k, v in self.cage["dimensions"].items()},
            "risks": self.risks, "entry_mode": self.mode, "verdict": self.verdict, "ranking": self.ranking,
            "sector": self.sector, "tariff": self.tariff, "landed_cost": self.cost, "vat_country": self.vat_country,
            "position": self.position, "sensitivity": self.sensitivity, "data_quality": self.data_quality,
            "kb": self.kb_info, "growth_pct": self.growth,
        }


def _load_market(hs_code: str, target: str, start_year: int, end_year: int) -> dict:
    if target == "CN":
        market = analysis.analyze_china_market(hs_code, start_year, end_year)
    else:
        market = analysis.analyze_eu_market(hs_code, start_year, end_year, target)
    if "error" in market:
        raise ValueError(market["error"])
    return market


def _vat_country(target: str, ranking: list[dict]) -> str:
    if target == "CN":
        return "CN"
    if target in kb.VAT_RATES:
        return target
    return ranking[0]["member"] if ranking else "DE"


def analyse_case(hs_code: str, target: str, home: str, company: str = "",
                 company_size: str = "medium", start_year: int | None = None,
                 end_year: int | None = None, product_label: str = "") -> Case:
    """
    Run every analysis step for one entry question and return the results.

    target: "EU", an EU member ISO2 code, or "CN".  home: ISO2 of the company's home country.
    """
    if company_size not in COMPANY_SIZES:
        raise ValueError(f"company_size must be one of {sorted(COMPANY_SIZES)}")
    end_year = end_year or date.today().year - 2
    start_year = start_year or end_year - 5
    target, home = target.upper(), home.upper()

    market = _load_market(hs_code, target, start_year, end_year)
    ly = market["latest_year"]
    sector = kb.sector_for(hs_code)
    target_p = analysis.profile_for(target)
    home_p = analysis.profile_for(home)
    score = analysis.attractiveness_score(market, target_p)
    cage = cage_analysis(home, target, home_p, target_p)
    pref = analysis.partner_tariff_for(target, hs_code, home, ly) if needs_partner_lookup(target, home) else None
    tariff = tariff_position(target, home, hs_code, analysis.tariff_for(target, hs_code, ly), pref)
    position = competitive_position(home, market)
    risks = risk_matrix(target, home, sector, market, score, cage, hs_code, tariff)
    mode = entry_mode(target, sector, company_size, score, cage, market, position)
    v, v_reason = verdict(score, risks)
    ranking = analysis.rank_eu_members(hs_code, start_year, end_year) if target == "EU" else []
    vat_country = _vat_country(target, ranking)
    duty = tariff["applicable_pct"] if tariff["applicable_pct"] is not None else 0.0
    cost = landed_cost(100.0, FREIGHT_PCT[cage["dimensions"]["Geographic"][0]], duty, kb.VAT_RATES.get(vat_country, 20))
    growth = market.get("growth_trend_pct")
    if growth is None:
        growth = market.get("cagr_pct")

    return Case(
        hs_code=hs_code, target=target, home=home, company=company, company_size=company_size,
        market=market, sector=sector, target_profile=target_p, score=score,
        sensitivity=analysis.score_sensitivity(score), cage=cage, tariff=tariff, position=position,
        risks=risks, mode=mode, verdict=v, verdict_reason=v_reason,
        data_quality=market.get("data_quality") or {"confidence": "High", "flags": []},
        kb_info=kb.kb_status(), ranking=ranking, vat_country=vat_country, cost=cost, growth=growth,
        product=product_label or market.get("product_name") or f"HS {hs_code}",
    )


def generate_report(hs_code: str, target: str, home: str, company: str = "",
                    company_size: str = "medium", start_year: int | None = None,
                    end_year: int | None = None, product_label: str = "") -> Report:
    """Analyse one entry question and render the full Markdown report."""
    from .report_markdown import render

    case = analyse_case(hs_code, target, home, company, company_size, start_year, end_year, product_label)
    return Report(title=case.title, markdown=render(case), data=case.data())
