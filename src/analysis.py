"""
Analysis layer: turns raw trade data into market-entry metrics.

All functions return plain dicts / lists so the same results can be shown
in the web app AND handed to the AI agent as JSON.
"""

from __future__ import annotations

import math

import pandas as pd

from . import data_sources as ds


# --------------------------------------------------------------------------- #
# Core metrics
# --------------------------------------------------------------------------- #
def hhi(shares_pct: list[float]) -> float:
    """Herfindahl-Hirschman Index from market shares in percent (0-10,000)."""
    return round(sum(s ** 2 for s in shares_pct), 0)


def hhi_label(value: float) -> str:
    """Concentration bands used by the US DOJ/FTC 2023 Merger Guidelines."""
    if value < 1000:
        return "Unconcentrated (diversified supply)"
    if value <= 1800:
        return "Moderately concentrated"
    return "Highly concentrated"


def cagr(first: float, last: float, years: int) -> float | None:
    if not first or first <= 0 or years <= 0 or last is None or last <= 0:
        return None
    return round(((last / first) ** (1 / years) - 1) * 100, 2)


SMALL_MARKET = 50e6        # below this (EUR/USD) growth rates are noisy
SERIES_BREAK_RATIO = 0.05  # a year below 5% of the peak points to a classification change or gap


def trend_growth(series: dict[int, float]) -> float | None:
    """
    Average annual growth from a log-linear least-squares fit over all years.
    Less sensitive to an unusual first or last year than the end-point CAGR.
    """
    pts = [(int(y), math.log(v)) for y, v in series.items() if v and v > 0]
    if len(pts) < 3:
        return None
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    den = sum((x - mx) ** 2 for x, _ in pts)
    if not den:
        return None
    slope = sum((x - mx) * (y - my) for x, y in pts) / den
    return round((math.exp(slope) - 1) * 100, 2)


def data_quality(series: dict[int, float], latest_size: float, hs_code: str = "") -> dict:
    """
    Flags that tell the reader how far to trust the growth figures:
    small markets, series breaks (e.g. a new HS code in HS2022) and volatile base years.
    Returns the usable series window and a High / Medium / Low confidence label.
    """
    from . import knowledge as kb

    flags: list[str] = []
    years = sorted(series)
    peak = max(series.values()) if series else 0
    usable = [y for y in years if series[y] and series[y] >= SERIES_BREAK_RATIO * peak]
    first_usable = usable[0] if usable else (years[0] if years else None)
    if usable and first_usable != years[0]:
        flags.append(f"Series break: values before {first_usable} are near zero, likely a classification change "
                     f"or reporting gap, so growth is measured from {first_usable}.")
    if hs_code in kb.HS2022_NEW_CODES:
        flags.append(f"HS {hs_code} was created in HS2022 (previously part of HS {kb.HS2022_NEW_CODES[hs_code]}); "
                     "data before 2022 may be incomplete.")
    if latest_size and latest_size < SMALL_MARKET:
        flags.append("Small market (below 50 million): a few shipments can swing growth rates strongly.")
    window = {y: series[y] for y in years if first_usable is not None and y >= first_usable}
    if len(window) >= 3:
        vals = list(window.values())
        med = sorted(vals)[len(vals) // 2]
        if vals[0] < 0.5 * med:
            flags.append("Low base year: the first year is less than half the median, which inflates the end-point CAGR.")
    confidence = "High" if not flags else ("Medium" if len(flags) == 1 and "Small market" not in flags[0] else "Low")
    return {"confidence": confidence, "flags": flags, "growth_window": [first_usable, years[-1] if years else None]}


def _growth_block(series: dict[int, float], latest_size: float, hs_code: str) -> dict:
    dq = data_quality(series, latest_size, hs_code)
    lo, hi = dq["growth_window"]
    window = {y: v for y, v in series.items() if lo is not None and y >= lo}
    endpoint = cagr(window.get(lo), window.get(hi), (hi - lo) if lo is not None and hi is not None else 0)
    return {"cagr_pct": endpoint, "growth_trend_pct": trend_growth(window), "data_quality": dq}


def _unit_value(value: float, weight_kg: float | None) -> float | None:
    if not weight_kg or weight_kg <= 0 or not value:
        return None
    return round(value / weight_kg, 2)


def _supplier_table(df: pd.DataFrame, value_col: str, total: float, top_n: int | None) -> list[dict]:
    df = df.sort_values(value_col, ascending=False)
    rows = []
    for _, r in (df if top_n is None else df.head(top_n)).iterrows():
        w = r.get("weight_kg")
        w = float(w) if w is not None and not pd.isna(w) else None
        rows.append({
            "partner": r["partner"],
            "partner_name": str(r["partner_name"]).split(" (")[0],
            "value": round(float(r[value_col]), 0),
            "share_pct": round(float(r[value_col]) / total * 100, 2) if total else None,
            "unit_value_per_kg": _unit_value(float(r[value_col]), w),
        })
    return rows


def _positions(df: pd.DataFrame, value_col: str, totals: pd.Series, latest: int) -> dict:
    """Every supplier's rank and share in the latest year plus its share trend (for 'your position')."""
    out = {}
    last = df[df["year"] == latest].sort_values(value_col, ascending=False)
    for rank, (_, r) in enumerate(last.iterrows(), 1):
        code = r["partner"]
        hist = df[df["partner"] == code].set_index("year")[value_col]
        out[code] = {
            "rank": rank, "suppliers": len(last),
            "share_by_year": {int(y): round(float(hist.get(y, 0)) / float(totals.loc[y]) * 100, 2)
                              for y in totals.index if totals.loc[y]},
        }
    return out


# --------------------------------------------------------------------------- #
# EU as the target market
# --------------------------------------------------------------------------- #
def analyze_eu_market(
    hs_code: str, start_year: int = 2015, end_year: int = 2024, reporter: str = "EU",
    top_n: int = 10,
) -> dict:
    """
    Market analysis for selling an HS6 product INTO the EU (or one member state).
    Market size is proxied by extra-EU imports (what the EU buys from outside).
    """
    countries, totals = ds.eu_extra_imports(hs_code, start_year, end_year, reporter)
    if countries.empty or totals.empty:
        return {"error": f"No Eurostat data for HS {hs_code} / {reporter} in {start_year}-{end_year}."}

    last_year = int(totals.index.max())
    first_year = int(totals.index.min())
    total_last = float(totals.loc[last_year])
    latest = countries[countries["year"] == last_year]
    suppliers = _supplier_table(latest, "value_eur", total_last, top_n)
    all_shares = (latest["value_eur"] / total_last * 100).tolist()
    concentration = hhi(all_shares)
    w_last = latest["weight_kg"].sum(min_count=1) if "weight_kg" in latest else None
    w_last = float(w_last) if w_last is not None and not pd.isna(w_last) else None
    sizes = {int(k): round(float(v), 0) for k, v in totals.items()}

    china_by_year = countries[countries["partner"] == "CN"].set_index("year")["value_eur"]
    china_share_trend = {
        int(y): round(float(china_by_year.get(y, 0)) / float(totals.loc[y]) * 100, 2)
        for y in totals.index if totals.loc[y]
    }

    product_name = countries["product_name"].dropna().iloc[0] if not countries.empty else ""

    result = {
        "market": "EU-27" if reporter == "EU" else reporter,
        "hs_code": hs_code,
        "product_name": product_name,
        "currency": "EUR",
        "source": "Eurostat Comext DS-045409 (extra-EU imports)",
        "years": [first_year, last_year],
        "import_market_size_by_year": sizes,
        "latest_year": last_year,
        "latest_market_size": round(total_last, 0),
        **_growth_block(sizes, total_last, hs_code),
        "top_suppliers_latest_year": suppliers,
        "unit_value_per_kg": _unit_value(float(latest["value_eur"].sum()), w_last),
        "supplier_positions": _positions(countries, "value_eur", totals, last_year),
        "hhi": concentration,
        "hhi_label": hhi_label(concentration),
        "china_share_pct_by_year": china_share_trend,
    }

    if reporter == "EU":
        try:
            members = ds.eu_member_imports_from(hs_code, last_year, "CN")
            result["eu_members_importing_from_china_latest_year"] = [
                {"member": r["reporter"], "value_eur": round(float(r["value_eur"]), 0)}
                for _, r in members.iterrows()
            ]
        except RuntimeError:
            pass
    return result


# --------------------------------------------------------------------------- #
# China as the target market
# --------------------------------------------------------------------------- #
def analyze_china_market(
    hs_code: str, start_year: int = 2019, end_year: int = 2024, top_n: int = 10
) -> dict:
    """Market analysis for selling an HS6 product INTO China (China's imports)."""
    years = list(range(start_year, end_year + 1))
    df = ds.china_imports_by_partner(hs_code, years)
    if df.empty:
        return {"error": f"No UN Comtrade data for China imports of HS {hs_code}."}

    df = df.copy()
    # Comtrade reports Taiwan as "Other Asia, nes" (code 490)
    df.loc[df["partner_code"] == 490, ["partner", "partner_name"]] = ["TW", "Taiwan (Other Asia, nes)"]
    df["is_group"] = df["is_group"] & (df["partner_code"] != 490)
    # Exclude China's re-imports of its own goods: we want foreign suppliers only
    reimports = df[df["partner_code"] == ds.CHINA_M49].groupby("year")["value_usd"].sum()
    df = df[df["partner_code"] != ds.CHINA_M49]

    world = df[df["is_world"]].set_index("year")["value_usd"]
    world = world.sub(reimports, fill_value=0)
    countries = df[~df["is_world"] & ~df["is_group"]]
    if world.empty:
        world = countries.groupby("year")["value_usd"].sum()

    last_year = int(world.index.max())
    first_year = int(world.index.min())
    total_last = float(world.loc[last_year])
    latest = countries[countries["year"] == last_year]
    suppliers = _supplier_table(latest, "value_usd", total_last, top_n)
    concentration = hhi((latest["value_usd"] / total_last * 100).tolist())
    sizes = {int(k): round(float(v), 0) for k, v in world.items()}
    w_last = latest["weight_kg"].sum(min_count=1) if "weight_kg" in latest else None
    w_last = float(w_last) if w_last is not None and not pd.isna(w_last) else None

    eu_by_year = countries[countries["is_eu_member"]].groupby("year")["value_usd"].sum()
    eu_share_trend = {
        int(y): round(float(eu_by_year.get(y, 0)) / float(world.loc[y]) * 100, 2)
        for y in world.index if world.loc[y]
    }

    return {
        "market": "China",
        "hs_code": hs_code,
        "currency": "USD",
        "source": "UN Comtrade (China-reported imports, excluding re-imports of Chinese goods)",
        "years": [first_year, last_year],
        "import_market_size_by_year": sizes,
        "latest_year": last_year,
        "latest_market_size": round(total_last, 0),
        **_growth_block(sizes, total_last, hs_code),
        "top_suppliers_latest_year": suppliers,
        "unit_value_per_kg": _unit_value(float(latest["value_usd"].sum()), w_last),
        "supplier_positions": _positions(countries, "value_usd", world, last_year),
        "hhi": concentration,
        "hhi_label": hhi_label(concentration),
        "eu27_share_pct_by_year": eu_share_trend,
    }


# --------------------------------------------------------------------------- #
# Country fundamentals and attractiveness score
# --------------------------------------------------------------------------- #
def country_profiles(iso2_codes: list[str]) -> list[dict]:
    df = ds.country_fundamentals(iso2_codes)
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def _clip(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


def attractiveness_score(market: dict, profile: dict | None = None) -> dict:
    """
    Transparent 0-10 market attractiveness score built from five sub-scores.
    Weights are explicit so users (and interviewers) can see the logic.
    """
    weights = {"market_size": 0.25, "growth": 0.25, "competitive_openness": 0.20,
               "institutional_quality": 0.15, "logistics": 0.15}
    size = market.get("latest_market_size") or 0
    # log scale: ~10M -> 2, ~100M -> 4, ~1B -> 6, ~10B -> 8, ~100B -> 10
    size_score = _clip((math.log10(size) - 6) * 2) if size > 0 else 0
    g = market.get("growth_trend_pct")
    if g is None:
        g = market.get("cagr_pct")
    growth_score = _clip(5 + g / 3) if g is not None else 5
    # Shrink the growth signal towards neutral when the data are less reliable.
    confidence = (market.get("data_quality") or {}).get("confidence", "High")
    growth_score = 5 + (growth_score - 5) * {"High": 1.0, "Medium": 0.75, "Low": 0.5}.get(confidence, 1.0)
    openness_score = _clip(10 - (market.get("hhi") or 10000) / 1000)

    inst_score, log_score = 5.0, 5.0
    if profile:
        gov = [profile.get(k) for k in (
            "rule_of_law_-2.5_2.5", "regulatory_quality_-2.5_2.5",
            "political_stability_-2.5_2.5", "control_of_corruption_-2.5_2.5")]
        gov = [v for v in gov if v is not None]
        if gov:
            inst_score = _clip((sum(gov) / len(gov) + 2.5) * 2)
        lpi = profile.get("logistics_performance_1_5")
        if lpi:
            log_score = _clip((lpi - 1) * 2.5)

    subs = {
        "market_size": round(size_score, 1),
        "growth": round(growth_score, 1),
        "competitive_openness": round(openness_score, 1),
        "institutional_quality": round(inst_score, 1),
        "logistics": round(log_score, 1),
    }
    total = round(sum(subs[k] * w for k, w in weights.items()), 1)
    return {"score_0_10": total, "sub_scores": subs, "weights": weights,
            "growth_input_pct": g, "growth_confidence": confidence}


WEIGHT_SCENARIOS = {
    "Base case": {"market_size": 0.25, "growth": 0.25, "competitive_openness": 0.20,
                  "institutional_quality": 0.15, "logistics": 0.15},
    "Equal weights": {k: 0.20 for k in ("market_size", "growth", "competitive_openness",
                                        "institutional_quality", "logistics")},
    "Size-led (large incumbents)": {"market_size": 0.40, "growth": 0.20, "competitive_openness": 0.15,
                                    "institutional_quality": 0.15, "logistics": 0.10},
    "Growth-led (start-ups)": {"market_size": 0.15, "growth": 0.40, "competitive_openness": 0.20,
                               "institutional_quality": 0.15, "logistics": 0.10},
    "Risk-averse (institutions first)": {"market_size": 0.20, "growth": 0.15, "competitive_openness": 0.20,
                                         "institutional_quality": 0.30, "logistics": 0.15},
    "Niche entrant (openness first)": {"market_size": 0.15, "growth": 0.20, "competitive_openness": 0.40,
                                       "institutional_quality": 0.15, "logistics": 0.10},
}


def score_sensitivity(score: dict) -> dict:
    """
    Re-weight the same sub-scores under alternative, defensible weighting schemes.
    Shows whether the verdict depends on the (subjective) weights or holds across them.
    """
    subs = score["sub_scores"]
    rows = [{"scenario": name, "weights": w, "score": round(sum(subs[k] * v for k, v in w.items()), 1)}
            for name, w in WEIGHT_SCENARIOS.items()]
    vals = [r["score"] for r in rows]

    def band(x):
        return "ENTER" if x >= 6.5 else ("ENTER WITH CAUTION" if x >= 5 else "DO NOT ENTER NOW")
    bands = {band(v) for v in vals}
    return {"scenarios": rows, "min": min(vals), "max": max(vals),
            "robust": len(bands) == 1, "bands": sorted(bands)}


# --------------------------------------------------------------------------- #
# EU aggregate profile and member-state ranking
# --------------------------------------------------------------------------- #
GOV_KEYS = ("rule_of_law_-2.5_2.5", "regulatory_quality_-2.5_2.5",
            "political_stability_-2.5_2.5", "control_of_corruption_-2.5_2.5")


def profile_for(iso2: str) -> dict | None:
    """Country profile; for "EU" the missing governance scores are the EU-27 average."""
    rows = country_profiles([iso2])
    profile = rows[0] if rows else None
    if iso2 == "EU" and profile is not None:
        members = pd.DataFrame(country_profiles(sorted(ds.EU27)))
        for key in GOV_KEYS:
            if profile.get(key) is None and key in members:
                profile[key] = round(float(members[key].dropna().mean()), 3)
    return profile


def rank_eu_members(hs_code: str, start_year: int, end_year: int) -> list[dict]:
    """
    Rank the 27 EU member states as entry markets for one product.

    Demand = total imports from all origins (incl. intra-EU), growth = CAGR,
    plus purchasing power, logistics and institutional quality.
    """
    df = ds.eu_members_total_imports(hs_code, [start_year, end_year])
    if df.empty:
        return []
    wide = df.pivot(index="reporter", columns="year", values="value_eur").fillna(0)
    profiles = {p["country"]: p for p in country_profiles(sorted(ds.EU27))}
    total_eu = float(wide.get(end_year, pd.Series(dtype=float)).sum()) or 1.0

    rows = []
    for member, r in wide.iterrows():
        last = float(r.get(end_year, 0))
        first = float(r.get(start_year, 0))
        p = profiles.get(member, {})
        growth = cagr(first, last, end_year - start_year)
        gov = [p.get(k) for k in GOV_KEYS if p.get(k) is not None]
        size_s = _clip((math.log10(last) - 6) * 2.5) if last > 0 else 0
        growth_s = _clip(5 + (growth or 0) / 3) if growth is not None else 5
        ppp_s = _clip((p.get("gdp_per_capita_usd") or 0) / 8000)
        lpi_s = _clip(((p.get("logistics_performance_1_5") or 3) - 1) * 2.5)
        inst_s = _clip((sum(gov) / len(gov) + 2.5) * 2) if gov else 5
        score = round(0.40 * size_s + 0.25 * growth_s + 0.15 * ppp_s + 0.10 * lpi_s + 0.10 * inst_s, 2)
        rows.append({
            "member": member,
            "imports_eur": round(last, 0),
            "share_of_eu_pct": round(last / total_eu * 100, 2),
            "cagr_pct": growth,
            "gdp_per_capita_usd": round(p["gdp_per_capita_usd"], 0) if p.get("gdp_per_capita_usd") else None,
            "lpi": p.get("logistics_performance_1_5"),
            "score_0_10": score,
        })
    rows.sort(key=lambda x: x["score_0_10"], reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


# --------------------------------------------------------------------------- #
# Validation: does the EU-27 ranking predict where demand actually grew?
# --------------------------------------------------------------------------- #
def backtest_eu_ranking(hs_code: str, end_year: int, horizon: int = 4, lookback: int = 5) -> dict | None:
    """
    Out-of-sample check of the member-state ranking.

    Rank the 27 members using only data up to t0 = end_year - horizon, then compare
    that ranking with what happened next (t0 -> end_year): the absolute increase in
    imports (where new demand appeared) and the growth rate. Reports Spearman rank
    correlations and how many of the predicted top-5 were among the actual top-5.
    Caveat: country fundamentals are today's values (small look-ahead bias).
    """
    t0 = end_year - horizon
    past = rank_eu_members(hs_code, t0 - lookback, t0)
    if not past:
        return None
    df = ds.eu_members_total_imports(hs_code, [t0, end_year])
    if df.empty:
        return None
    wide = df.pivot(index="reporter", columns="year", values="value_eur").fillna(0)
    if t0 not in wide or end_year not in wide:
        return None
    pred = pd.Series({r["member"]: r["score_0_10"] for r in past})
    gain = (wide[end_year] - wide[t0]).reindex(pred.index)
    growth = pd.Series({m: cagr(wide.at[m, t0], wide.at[m, end_year], horizon) for m in pred.index}, dtype=float)
    top_pred = set(pred.sort_values(ascending=False).index[:5])
    top_gain = set(gain.sort_values(ascending=False).index[:5])

    def spearman(a: pd.Series, b: pd.Series) -> float | None:
        both = pd.concat([a, b], axis=1).dropna()
        if len(both) < 5:
            return None
        return round(float(both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())), 2)
    return {
        "hs_code": hs_code, "ranked_with": [t0 - lookback, t0], "evaluated": [t0, end_year],
        "spearman_vs_gain": spearman(pred, gain), "spearman_vs_growth": spearman(pred, growth),
        "top5_hits": len(top_pred & top_gain), "predicted_top5": sorted(top_pred), "actual_top5": sorted(top_gain),
    }


def tariff_for(target: str, hs_code: str, latest_year: int) -> dict | None:
    """MFN tariff applied by the target market (thin wrapper so callers can cache or mock it)."""
    try:
        return ds.mfn_tariff(target, hs_code, latest_year)
    except Exception:  # tariff data is a nice-to-have; never break a report over it
        return None
