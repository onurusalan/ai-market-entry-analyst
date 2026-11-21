"""
Markdown rendering of a market entry report.

report_engine.analyse_case() does all the analysis and returns a Case; this module
only turns that Case into text, one function per report section, so each section
can be changed and tested on its own.
"""

from __future__ import annotations

from collections.abc import Callable

from . import knowledge as kb
from .report_engine import COMPANY_SIZES, Case, _name, action_plan, money, pestel

SCORE_NAMES = {"market_size": "Market size", "growth": "Growth", "competitive_openness": "Competitive openness",
               "institutional_quality": "Institutional quality", "logistics": "Logistics"}

Lines = list[str]


def _unit_value(case: Case, v: float | None) -> str:
    sym = "€" if case.currency == "EUR" else "$"
    return f"{sym}{v:,.2f}" if v else "n/a"


def header(c: Case) -> Lines:
    return [f"# {c.title}", "",
            f"*Company: {c.company or 'n/a'} · Home country: {_name(c.home)} · Size: {COMPANY_SIZES[c.company_size]} · "
            f"HS {c.hs_code} ({kb.SECTOR_LABELS[c.sector]}) · Trade data {c.market['years'][0]}-{c.latest_year}*", ""]


def executive_summary(c: Case) -> Lines:
    m, ly, top, pos, tariff = c.market, c.latest_year, c.market["top_suppliers_latest_year"], c.position, c.tariff
    lines = ["## 1. Executive Summary", "",
             f"**Verdict: {c.verdict}.** {c.verdict_reason}", "",
             f"**Market attractiveness: {c.score['score_0_10']}/10**  ",
             f"**Recommended entry mode:** {c.mode['mode']}", ""]
    points = [
        f"Import market of {money(m['latest_market_size'], c.currency)} in {ly}"
        + (f", trend growth {c.growth:+.1f}% a year (data confidence: {c.data_quality['confidence'].lower()})."
           if c.growth is not None else "."),
        f"Supply is {m['hhi_label'].split(' (')[0].lower()} (HHI {m['hhi']:,.0f}); "
        f"top supplier {top[0]['partner_name']} holds {top[0]['share_pct']}%." if top else "No supplier data.",
        f"CAGE distance from {_name(c.home)}: {c.cage['overall_label'].lower()}.",
        (f"Applicable import duty: {tariff['applicable_pct']:g}% ({tariff['basis']}); landed cost ≈ "
         f"{c.cost['uplift_ex_vat_pct']:+.0f}% over ex-works price before VAT." if tariff["applicable_pct"] is not None
         else "Import duty: check the official tariff database."),
        (f"{_name(c.home)} is supplier #{pos['rank']} with {pos['share_pct']}% of imports"
         + (f", priced {pos['price_position'].lower()} ({pos['price_ratio']}x market average per kg)."
            if pos.get("price_position") else ".")
         if pos["present"] else f"{_name(c.home)} is not yet a recorded supplier to this market."),
    ]
    if c.target == "EU" and "china_share_pct_by_year" in m:
        points.append(f"China supplies {m['china_share_pct_by_year'].get(ly)}% of extra-EU imports.")
    if c.target == "CN":
        points.append(f"EU-27 suppliers hold {m['eu27_share_pct_by_year'].get(ly)}% of China's imports.")
    if c.priority:
        points.append("Priority EU markets: " + ", ".join(c.priority) + ".")
    return lines + [f"- {p}" for p in points] + [""]


def market_size(c: Case) -> Lines:
    m, dq = c.market, c.data_quality
    lines = ["## 2. Market Size & Growth", "",
             f"Market size is measured as imports into {c.target_name} ({m['source']}). "
             "Imports show demand served from abroad, not total consumption.", "",
             f"| Year | Imports ({c.currency}) |", "|---|---|"]
    lines += [f"| {y} | {money(val, c.currency)} |" for y, val in m["import_market_size_by_year"].items()]
    gw = dq.get("growth_window") or m["years"]
    lines += ["", f"Growth {gw[0]}-{gw[1]}: trend **{c.growth:+.2f}%** a year (log-linear fit over all years)"
              + (f"; end-point CAGR {m['cagr_pct']:+.2f}%." if m.get("cagr_pct") is not None else ".")
              if c.growth is not None else "Growth: not enough data.", ""]
    lines += [f"**Data confidence: {dq['confidence']}.** " + ("No quality issues detected." if not dq["flags"] else
              "The growth signal in the score is shrunk towards neutral because:"), ""]
    lines += [f"- {f}" for f in dq["flags"]] + ([""] if dq["flags"] else [])
    return lines


def competition(c: Case) -> Lines:
    m, ly, top = c.market, c.latest_year, c.market["top_suppliers_latest_year"]
    lines = ["## 3. Competitive Landscape", "",
             f"| Rank | Supplier | Imports {ly} | Share | Unit value per kg |", "|---|---|---|---|---|"]
    lines += [f"| {i} | {'**' + s['partner_name'] + '**' if s['partner'] == c.home else s['partner_name']} | "
              f"{money(s['value'], c.currency)} | {s['share_pct']}% | {_unit_value(c, s.get('unit_value_per_kg'))} |"
              for i, s in enumerate(top, 1)]
    if m.get("unit_value_per_kg"):
        lines += ["", f"Market average unit value: **{_unit_value(c, m['unit_value_per_kg'])}/kg**. "
                      "Unit values show each supplier's price level (product mix also matters)."]
    lines += ["", f"**HHI {m['hhi']:,.0f}: {m['hhi_label']}.** "
              + ("A few suppliers dominate, so a newcomer must win share from incumbents or exploit buyers' wish to "
                 "diversify supply (EU 'de-risking')." if m["hhi"] > 1800 else
                 "Supply is reasonably spread, so there is room for a differentiated new entrant."), ""]
    share_key, who = (("china_share_pct_by_year", "China's share of extra-EU imports") if c.target == "EU"
                      else ("eu27_share_pct_by_year", "The EU-27's share of China's imports") if c.target == "CN"
                      else (None, None))
    trend = m.get(share_key) if share_key else None
    if trend:
        first_y = min(trend)
        lines += [f"{who} moved from {trend[first_y]}% ({first_y}) to {trend[ly]}% ({ly}).", ""]
    return lines


def competitor_momentum(c: Case) -> Lines:
    mom = c.market.get("momentum") or {}
    gainers, losers = mom.get("gainers") or [], mom.get("losers") or []
    if not gainers and not losers:
        return []
    lines = ["### Competitor momentum", "",
             "Change in market share over the period, among suppliers with at least 1% share.", "",
             "| Supplier | Share then | Share now | Change |", "|---|---|---|---|"]
    for r in gainers + losers:
        name = f"**{r['name']}**" if r["partner"] == c.home else r["name"]
        lines.append(f"| {name} | {r['share_first']}% ({r['first_year']}) | {r['share_last']}% | {r['change_pp']:+.2f} pp |")
    if gainers:
        top = gainers[0]
        lines += ["", f"Fastest-rising challenger: **{top['name']}** ({top['change_pp']:+.1f} pp). "
                      "Rising suppliers signal where price and capacity pressure will come from."]
    return lines + [""]


def starting_position(c: Case) -> Lines:
    pos, ly = c.position, c.latest_year
    lines = [f"### Your starting position: {_name(c.home)}", ""]
    if pos["present"]:
        lines += [f"- Supplier **#{pos['rank']} of {pos.get('suppliers')}** with **{pos['share_pct']}%** of imports in {ly} "
                  f"({pos['share_change_pp']:+.2f} pp since {pos.get('first_year')})."]
    else:
        lines += [f"- {_name(c.home)} does not appear among recorded suppliers in {ly}: a greenfield entry."]
    if pos.get("price_position"):
        lines += [f"- Price level: **{pos['price_position']}**, {_unit_value(c, pos['unit_value_per_kg'])}/kg vs a market "
                  f"average of {_unit_value(c, pos['market_unit_value_per_kg'])}/kg ({pos['price_ratio']}x)."]
    if c.tariff.get("fta"):
        lines += [f"- Trade agreement: **{c.tariff['fta']}** gives preferential access if rules of origin are met."]
    return lines + [""]


def priority_markets(c: Case) -> Lines:
    if not c.ranking:
        return []
    lines = ["### Priority EU member states", "",
             "Ranked on total imports (demand incl. intra-EU trade), growth, purchasing power, logistics and institutions.", "",
             "| Rank | Country | Imports | Share of EU | CAGR | Score |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['rank']} | {_name(r['member'])} | {money(r['imports_eur'], 'EUR')} | {r['share_of_eu_pct']}% | "
              f"{r['cagr_pct']}% | {r['score_0_10']} |" for r in c.ranking[:8]]
    return lines + ["", "*Note: the Netherlands and Belgium also import for re-export through Rotterdam and Antwerp.*", ""]


def untapped_section(c: Case) -> Lines:
    u = c.untapped
    if not u:
        return []
    lines = [f"### Untapped potential for {_name(c.home)} by member state", ""]
    if not u["markets"]:
        return lines + [f"{_name(c.home)} has no recorded extra-EU share in {u['year']}, so there is no benchmark yet: "
                        "use the priority markets above.", ""]
    lines += [f"{_name(c.home)} supplies {u['home_share_pct']}% of all extra-EU imports. Applying that share to each "
              "member state's extra-EU imports gives an expected value; the gap to actual imports from "
              f"{_name(c.home)} is untapped potential (simplified ITC Export Potential Map logic, {u['year']}).", "",
              "| Member state | Extra-EU imports | From your country | Expected | Untapped | Penetration |",
              "|---|---|---|---|---|---|"]
    lines += [f"| {_name(r['member'])} | {money(r['extra_eu_imports'], 'EUR')} | {money(r['actual'], 'EUR')} | "
              f"{money(r['expected'], 'EUR')} | **{money(r['untapped'], 'EUR')}** | "
              f"{'n/a' if r['penetration'] is None else f'{r['penetration'] * 100:.0f}%'} |" for r in u["markets"]]
    return lines + ["", f"Total untapped potential: **{money(u['total_untapped_eur'], 'EUR')}**. Low penetration in a large "
                        "market is the clearest expansion target; hubs (Netherlands, Belgium) partly re-export.", ""]


def seasonality_block(c: Case) -> Lines:
    s = c.seasonality
    if not s:
        return []
    idx = s["index"]
    return ["### Seasonality", "",
            f"Monthly extra-EU imports relative to the yearly average (100), {s['years'][0]}–{s['years'][-1]}:", "",
            "| " + " | ".join(idx) + " |", "|" + "---|" * len(idx), "| " + " | ".join(f"{v:.0f}" for v in idx.values()) + " |", "",
            f"**{s['strength']} seasonality** (peak-to-trough {s['amplitude']:.0f} points). Peak months: "
            f"{', '.join(s['peak_months'])}; quietest: {', '.join(s['low_months'])}. With 6-8 weeks of sea freight, "
            f"ship in **{' and '.join(s['ship_window'])}** to have stock in place for the peak.", ""]


def pestel_section(c: Case) -> Lines:
    factors = pestel(c.target, c.sector, c.market, c.target_profile)
    return ["## 4. PESTEL Analysis", ""] + [f"- **{k}:** {val}" for k, val in factors.items()] + [""]


def cage_section(c: Case) -> Lines:
    lines = ["## 5. CAGE Distance", "", "| Dimension | Distance | Evidence |", "|---|---|---|"]
    lines += [f"| {d} | {lvl} | {note} |" for d, (lvl, note) in c.cage["dimensions"].items()]
    return lines + ["", f"**Overall distance: {c.cage['overall_label']}.**", ""]


def tariffs_and_regulation(c: Case) -> Lines:
    tariff, cost, market_key = c.tariff, c.cost, "CN" if c.target == "CN" else "EU"
    lines = ["## 6. Tariffs, Trade Defence & Regulation", "", "### Import duty", ""]
    mfn = tariff.get("mfn")
    if mfn:
        rng = (f" (range {mfn['min_pct']:g}-{mfn['max_pct']:g}% across {mfn['tariff_lines']} national tariff lines)"
               if mfn.get("min_pct") is not None and mfn.get("max_pct") is not None and mfn["min_pct"] != mfn["max_pct"]
               else "")
        lines += [f"- **MFN applied tariff of {c.target_name}: {mfn['rate_pct']:g}%**{rng}, {mfn['year']} ({mfn['source']})."]
    else:
        lines += ["- MFN tariff: not available from WITS for this product; check the official tariff database."]
    if tariff["applicable_pct"] is not None:
        lines += [f"- **Likely rate for a company from {_name(c.home)}: {tariff['applicable_pct']:g}%** ({tariff['basis']})."]
    lines += [""]
    if c.hs_code in kb.TRADE_DEFENCE_NOTES:
        checked, link = kb.TRADE_DEFENCE_META.get(c.hs_code, (kb.KB_AS_OF, None))
        lines += [f"> ⚠️ **Trade policy note (checked {checked}):** {kb.TRADE_DEFENCE_NOTES[c.hs_code]}"
                  + (f" [Official source]({link})." if link else ""), ""]
    a, geo = cost["assumptions"], c.cage["dimensions"]["Geographic"][0].lower()
    lines += ["### Indicative landed cost (per 100 of ex-works value)", "",
              "| Item | Amount | Assumption |", "|---|---|---|",
              f"| Goods (ex-works) | {cost['goods']:.2f} | |",
              f"| Freight & insurance | {cost['freight_insurance']:.2f} | {a['freight_pct']:g}% for {geo} distance |",
              f"| Import duty | {cost['duty']:.2f} | {a['duty_pct']:g}% on CIF value |",
              f"| Clearance, broker, port | {cost['clearance_other']:.2f} | {a['other_pct']:g}% |",
              f"| Import VAT | {cost['import_vat']:.2f} | {a['vat_pct']:g}% ({_name(c.vat_country)}), "
              "usually recoverable for VAT-registered importers |",
              f"| **Landed cost** | **{cost['landed_total']:.2f}** | **{cost['landed_ex_vat']:.2f} before VAT "
              f"({cost['uplift_ex_vat_pct']:+.1f}%)** |", ""]
    if c.target == "CN" and c.sector in ("vehicles", "cosmetics"):
        lines += ["*China also levies consumption tax on cars and some cosmetics; add it to the model where relevant.*", ""]
    reg = kb.CN_REGULATION if c.target == "CN" else kb.EU_REGULATION
    lines += ["### Regulatory checklist", ""] + [f"- {r}" for r in reg.get(c.sector, []) + reg["_all"]]
    srcs = kb.REG_SOURCES[market_key]
    official = srcs.get(c.sector, []) + srcs.get("_all", [])
    if official:
        lines += ["", "**Official texts:** " + " · ".join(f"[{label}]({url})" for label, url in official)]
    lines += ["", f"*Regulatory notes compiled {c.kb_info['as_of']} from official sources"
              + (" and now **due for review**" if c.kb_info["stale"] else "") + "; not legal advice.*", "",
              "**Verify current duties and requirements:**"]
    return lines + [f"- [{label}]({url})" for label, url in kb.VERIFY_SOURCES[market_key]] + [""]


def risk_section(c: Case) -> Lines:
    lines = ["## 7. Risk Matrix", ""]
    if c.fx and c.fx.get("note"):
        lines += [f"**Exchange rate (ECB reference rates):** {c.fx['note']}"
                  + (f" Risk level: **{c.fx['level']}**." if c.fx.get("level") not in (None, "None") else ""), ""]
    lines += ["| Risk | Likelihood | Impact | Mitigation |", "|---|---|---|---|"]
    return lines + [f"| {r['risk']} | {r['likelihood']} | {r['impact']} | {r['mitigation']} |" for r in c.risks] + [""]


def entry_mode_section(c: Case) -> Lines:
    return ["## 8. Recommended Entry Mode", "", f"**{c.mode['mode']}**", ""] + [f"- {r}" for r in c.mode["reasons"]] + [""]


def score_section(c: Case) -> Lines:
    s, sens = c.score, c.sensitivity
    lines = ["## 9. Attractiveness Score Breakdown", "", "| Component | Weight | Score |", "|---|---|---|"]
    lines += [f"| {SCORE_NAMES[k]} | {int(s['weights'][k] * 100)}% | {val}/10 |" for k, val in s["sub_scores"].items()]
    lines += [f"| **Total** | | **{s['score_0_10']}/10** |", ""]
    lines += ["### Sensitivity to the weights", "",
              "The weights are a judgement call, so the same sub-scores are re-weighted under alternative schemes:", "",
              "| Weighting scheme | Score |", "|---|---|"]
    lines += [f"| {r['scenario']} | {r['score']} |" for r in sens["scenarios"]]
    return lines + ["", (f"**Robust:** the score stays between {sens['min']} and {sens['max']}, and the verdict band "
                         "does not change." if sens["robust"] else
                         f"**Weight-sensitive:** the score ranges from {sens['min']} to {sens['max']} and crosses a "
                         f"verdict threshold ({', '.join(b.lower() for b in sens['bands'])}), so treat the verdict "
                         "as borderline."), ""]


def action_plan_section(c: Case) -> Lines:
    steps = action_plan(c.target, c.sector, c.mode["mode"], c.priority)
    return ["## 10. 90-Day Action Plan", ""] + [f"{i}. {step}" for i, step in enumerate(steps, 1)] + [""]


def sources(c: Case) -> Lines:
    return ["## Sources", "",
            f"- {c.market['source']}, trade data {c.market['years'][0]}-{c.latest_year}",
            "- World Bank WITS / UNCTAD TRAINS (MFN tariffs); ECB euro reference exchange rates",
            "- World Bank World Development Indicators, Logistics Performance Index, Worldwide Governance Indicators",
            "- Regulatory notes: curated from official EU and Chinese sources; verify with the links in section 6",
            "- Frameworks: PESTEL; CAGE distance (Ghemawat, 2001); HHI bands (US DOJ/FTC 2023); entry-mode logic "
            "(Dunning's OLI, transaction-cost theory)", ""]


SECTIONS: list[Callable[[Case], Lines]] = [
    header, executive_summary, market_size, seasonality_block, competition, competitor_momentum, starting_position,
    priority_markets, untapped_section, pestel_section,
    cage_section, tariffs_and_regulation, risk_section, entry_mode_section, score_section, action_plan_section, sources,
]


def render(case: Case) -> str:
    """The full report as Markdown."""
    return "\n".join(line for section in SECTIONS for line in section(case))
