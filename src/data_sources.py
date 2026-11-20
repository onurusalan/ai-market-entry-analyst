"""
Data layer: fetches real trade and macro data from free public APIs.

Sources
-------
- Eurostat Comext (DS-045409): EU imports by product (HS6) and partner country, in EUR
- UN Comtrade (public preview API): China's imports by product and partner country, in USD
- World Bank Indicators API: macro, logistics and governance indicators

Every response is cached on disk (data/cache) so repeated runs are fast
and the public APIs are not hit more than necessary.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_SECONDS = 7 * 24 * 3600  # one week

EUROSTAT_URL = (
    "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"
)
COMTRADE_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_FULL_URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
COMTRADE_PARTNERS_URL = "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"

EU27 = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
}
CHINA_M49 = 156


# --------------------------------------------------------------------------- #
# HTTP + cache helpers
# --------------------------------------------------------------------------- #
def _cache_path(url: str, params) -> Path:
    key_src = url + json.dumps(params, sort_keys=True, default=str)
    return CACHE_DIR / f"{hashlib.sha256(key_src.encode()).hexdigest()[:24]}.json"


def _is_cached(url: str, params) -> bool:
    path = _cache_path(url, params)
    return path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL_SECONDS


def _cached_get_json(url: str, params: dict | list | None = None, timeout: int = 90,
                     headers: dict | None = None):
    """GET a URL and return parsed JSON, using a simple on-disk cache."""
    path = _cache_path(url, params)
    if _is_cached(url, params):
        return json.loads(path.read_text())

    last_error = None
    for attempt in range(5):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429:  # rate limited (Comtrade preview: ~1 call / 2 s)
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            path.write_text(json.dumps(data))
            return data
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Request failed for {url}: {last_error}")


# --------------------------------------------------------------------------- #
# Eurostat Comext: EU imports
# --------------------------------------------------------------------------- #
def _parse_jsonstat(data: dict) -> pd.DataFrame:
    """Turn a Eurostat JSON-stat 2.0 response into a flat DataFrame."""
    dims = data["id"]
    sizes = data["size"]
    categories = {}
    for dim in dims:
        cat = data["dimension"][dim]["category"]
        ordered = sorted(cat["index"].items(), key=lambda kv: kv[1])
        categories[dim] = [code for code, _ in ordered]
    labels = {dim: data["dimension"][dim]["category"].get("label", {}) for dim in dims}

    rows = []
    for flat_index, value in data.get("value", {}).items():
        flat_index = int(flat_index)
        coords = {}
        for dim, size in zip(reversed(dims), reversed(sizes)):
            coords[dim] = categories[dim][flat_index % size]
            flat_index //= size
        coords["value"] = value
        rows.append(coords)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["partner_name"] = df["partner"].map(labels.get("partner", {}))
    df["product_name"] = df["product"].map(labels.get("product", {}))
    return df


def eu_imports_by_partner(
    hs_code: str, start_year: int, end_year: int, reporter: str = "EU"
) -> pd.DataFrame:
    """
    Annual imports of one HS product into the EU (or one EU member state),
    broken down by partner country.

    Returns columns: year, partner, partner_name, value_eur, product_name,
    plus is_aggregate / is_eu_member flags.
    """
    params = [
        ("format", "JSON"), ("lang", "en"), ("freq", "A"), ("reporter", reporter),
        ("product", hs_code), ("flow", "1"), ("indicators", "VALUE_IN_EUROS"),
    ]
    params += [("time", str(y)) for y in range(start_year, end_year + 1)]
    data = _cached_get_json(EUROSTAT_URL, params)
    df = _parse_jsonstat(data)
    if df.empty:
        return df

    df = df.rename(columns={"time": "year", "value": "value_eur"})
    df["year"] = df["year"].astype(int)
    df["is_aggregate"] = df["partner"].str.len() != 2
    df["is_eu_member"] = df["partner"].isin(EU27)
    # Partner "GB" was intra-EU before 2020; Eurostat already handles this in aggregates.
    return df[
        ["year", "partner", "partner_name", "value_eur", "product_name",
         "is_aggregate", "is_eu_member"]
    ].sort_values(["year", "value_eur"], ascending=[True, False]).reset_index(drop=True)


def eu_extra_imports(hs_code: str, start_year: int, end_year: int, reporter: str = "EU"):
    """
    Convenience view: imports from outside the EU only (countries, no aggregates),
    plus the official extra-EU total per year.
    """
    df = eu_imports_by_partner(hs_code, start_year, end_year, reporter)
    if df.empty:
        return df, pd.Series(dtype=float)
    totals = (
        df[df["partner"] == "EXT_EU27_2020"].set_index("year")["value_eur"]
        if (df["partner"] == "EXT_EU27_2020").any()
        else df[~df["is_aggregate"] & ~df["is_eu_member"]].groupby("year")["value_eur"].sum()
    )
    countries = df[~df["is_aggregate"] & ~df["is_eu_member"]].copy()
    return countries, totals


def eu_member_imports_from(
    hs_code: str, year: int, partner: str = "CN"
) -> pd.DataFrame:
    """Imports of a product from one partner (default China) into each EU member state."""
    params = [
        ("format", "JSON"), ("lang", "en"), ("freq", "A"), ("partner", partner),
        ("product", hs_code), ("flow", "1"), ("indicators", "VALUE_IN_EUROS"),
        ("time", str(year)),
    ]
    params += [("reporter", r) for r in sorted(EU27)]
    data = _cached_get_json(EUROSTAT_URL, params)
    df = _parse_jsonstat(data)
    if df.empty:
        return df
    return (
        df.rename(columns={"value": "value_eur"})[["reporter", "value_eur"]]
        .sort_values("value_eur", ascending=False)
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------- #
# UN Comtrade: China's imports (for EU firms targeting China)
# --------------------------------------------------------------------------- #
def _comtrade_partner_lookup() -> dict[int, dict]:
    data = _cached_get_json(COMTRADE_PARTNERS_URL)
    return {
        r["PartnerCode"]: {
            "name": r["PartnerDesc"],
            "iso2": r.get("PartnerCodeIsoAlpha2"),
            "is_group": r.get("isGroup", False),
        }
        for r in data["results"]
    }


def _comtrade_rows(params: dict, years: list[int]) -> list[dict]:
    """
    Fetch Comtrade rows for several years.
    - With COMTRADE_API_KEY set (free at comtradeplus.un.org): one call to the full API.
    - Without a key: the public preview API, one year per call, spaced to respect its rate limit.
    """
    api_key = os.getenv("COMTRADE_API_KEY")
    if api_key:
        data = _cached_get_json(
            COMTRADE_FULL_URL, {**params, "period": ",".join(map(str, years))},
            headers={"Ocp-Apim-Subscription-Key": api_key},
        )
        return data.get("data") or []

    rows = []
    for i, year in enumerate(years):
        query = {**params, "period": year}
        if i and not _is_cached(COMTRADE_URL, query):
            time.sleep(2.2)  # preview API allows roughly one call every 2 seconds
        rows += _cached_get_json(COMTRADE_URL, query).get("data") or []
    return rows


def china_imports_by_partner(hs_code: str, years: list[int]) -> pd.DataFrame:
    """
    China's annual imports of one HS6 product by partner country (USD),
    from UN Comtrade (public preview API, or the full API if COMTRADE_API_KEY is set).
    """
    lookup = _comtrade_partner_lookup()
    frames = []
    for r in _comtrade_rows(
        {"reporterCode": CHINA_M49, "cmdCode": hs_code, "flowCode": "M"}, years
    ):
        # Keep only the plain "all customs procedures / all transport modes" rows
        if r.get("customsCode") not in (None, "C00") or r.get("motCode") not in (None, 0):
            continue
        if r.get("partner2Code") not in (None, 0):
            continue
        info = lookup.get(r["partnerCode"], {})
        frames.append({
            "year": int(r["refYear"]),
            "partner_code": r["partnerCode"],
            "partner": info.get("iso2") or str(r["partnerCode"]),
            "partner_name": "World" if r["partnerCode"] == 0 else info.get("name", "Unknown"),
            "value_usd": float(r.get("primaryValue") or 0),
            "is_world": r["partnerCode"] == 0,
            "is_group": bool(info.get("is_group")),
            "is_eu_member": (info.get("iso2") in EU27),
        })
    df = pd.DataFrame(frames)
    if df.empty:
        return df
    return df.sort_values(["year", "value_usd"], ascending=[True, False]).reset_index(drop=True)


def world_exporters(hs_code: str, year: int, reporters: list[str]) -> pd.DataFrame:
    """
    Total exports to the world of one HS6 product for a list of ISO2 countries
    (used to find alternative suppliers). Value in USD.
    """
    lookup = _comtrade_partner_lookup()
    iso_to_code = {v["iso2"]: k for k, v in lookup.items() if v.get("iso2") and not v["is_group"]}
    # Comtrade reporter codes differ from partner codes for a few countries
    overrides = {"FR": 251, "IT": 381, "US": 842, "IN": 699, "CH": 757, "NO": 579}
    codes = [overrides.get(c, iso_to_code.get(c)) for c in reporters]
    codes = [c for c in codes if c]
    params = {
        "reporterCode": ",".join(str(c) for c in codes), "period": year,
        "cmdCode": hs_code, "flowCode": "X", "partnerCode": 0,
    }
    if os.getenv("COMTRADE_API_KEY"):
        data = _cached_get_json(COMTRADE_FULL_URL, params,
                                headers={"Ocp-Apim-Subscription-Key": os.environ["COMTRADE_API_KEY"]})
    else:
        data = _cached_get_json(COMTRADE_URL, params)
    code_to_iso = {v: k for k, v in iso_to_code.items()}
    code_to_iso.update({v: k for k, v in overrides.items()})
    rows = []
    for r in data.get("data") or []:
        if r.get("customsCode") not in (None, "C00") or r.get("motCode") not in (None, 0):
            continue
        iso = code_to_iso.get(r["reporterCode"], str(r["reporterCode"]))
        rows.append({"country": iso, "exports_usd": float(r.get("primaryValue") or 0)})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.groupby("country", as_index=False)["exports_usd"].sum().sort_values(
        "exports_usd", ascending=False
    ).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# World Bank: country fundamentals
# --------------------------------------------------------------------------- #
WB_INDICATORS = {
    "NY.GDP.MKTP.CD": ("gdp_usd", 2),
    "NY.GDP.PCAP.CD": ("gdp_per_capita_usd", 2),
    "NY.GDP.MKTP.KD.ZG": ("gdp_growth_pct", 2),
    "SP.POP.TOTL": ("population", 2),
    "FP.CPI.TOTL.ZG": ("inflation_pct", 2),
    "LP.LPI.OVRL.XQ": ("logistics_performance_1_5", 2),
    "GOV_WGI_RL.EST": ("rule_of_law_-2.5_2.5", 3),
    "GOV_WGI_RQ.EST": ("regulatory_quality_-2.5_2.5", 3),
    "GOV_WGI_PV.EST": ("political_stability_-2.5_2.5", 3),
    "GOV_WGI_CC.EST": ("control_of_corruption_-2.5_2.5", 3),
}


def country_fundamentals(iso2_codes: list[str]) -> pd.DataFrame:
    """
    Latest available value of key macro, logistics and governance indicators
    for each country. One row per country.
    """
    countries = ";".join(iso2_codes)
    records: dict[str, dict] = {c: {"country": c} for c in iso2_codes}
    for indicator, (name, source) in WB_INDICATORS.items():
        url = WORLD_BANK_URL.format(countries=countries, indicator=indicator)
        params = {"format": "json", "mrnev": 1, "per_page": 500, "source": source}
        try:
            data = _cached_get_json(url, params)
        except RuntimeError:
            continue
        if not isinstance(data, list) or len(data) < 2 or not data[1]:
            continue
        for row in data[1]:
            iso2 = row["country"]["id"]
            if iso2 in records and row.get("value") is not None:
                records[iso2][name] = row["value"]
                records[iso2][f"{name}_year"] = row.get("date")
    return pd.DataFrame(records.values())
