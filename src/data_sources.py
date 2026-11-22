"""
Data layer: fetches real trade and macro data from free public APIs.

Sources
-------
- Eurostat Comext (DS-045409): EU imports by product (HS6) and partner country, in EUR
- UN Comtrade (public preview API): China's imports by product and partner country, in USD
- World Bank Indicators API: macro, logistics and governance indicators
- World Bank WITS (UNCTAD TRAINS): MFN import tariffs by HS6 product

Every response is cached on disk (data/cache) so repeated runs are fast
and the public APIs are not hit more than necessary.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

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
WITS_URL = ("https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN/reporter/{reporter}"
            "/partner/000/product/{hs}/year/{year}/datatype/reported")
WITS_REPORTERS = {"EU": "918", "CN": "156"}  # EU member states apply the common EU tariff
WITS_PARTNER_URL = ("https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN/reporter/{reporter}"
                    "/partner/{partner}/product/{hs}/year/{year}/datatype/reported")
# ISO 3166 numeric codes used by WITS for partner countries
ISO_NUMERIC = {
    "CN": "156", "US": "840", "JP": "392", "KR": "410", "TW": "158", "VN": "704", "IN": "356", "GB": "826",
    "CH": "756", "NO": "578", "SG": "702", "CA": "124", "AU": "036", "MX": "484", "BR": "076", "TR": "792",
    "DE": "276", "FR": "250", "IT": "380", "ES": "724", "NL": "528", "BE": "056", "AT": "040", "PL": "616",
    "SE": "752", "DK": "208", "FI": "246", "IE": "372", "PT": "620", "CZ": "203", "HU": "348", "RO": "642",
    "GR": "300", "BG": "100", "HR": "191", "SK": "703", "SI": "705", "LT": "440", "LV": "428", "EE": "233",
    "LU": "442", "MT": "470", "CY": "196",
}

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


_session: requests.Session | None = None


def _http() -> requests.Session:
    """One pooled HTTP session for all sources (keeps connections alive across the many small calls)."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
        _session.headers["User-Agent"] = "market-entry-analyst/1.0 (open-source research tool)"
    return _session


def offline() -> bool:
    """True when MEA_OFFLINE is set: work from the local cache only (e.g. a presentation without internet)."""
    return os.getenv("MEA_OFFLINE", "").strip().lower() in ("1", "true", "yes")


class NotFound(RuntimeError):
    """The source answered but has no data for this query (HTTP 404)."""


def _cached_get_json(url: str, params: dict | list | None = None, timeout: int = 90,
                     headers: dict | None = None):
    """
    GET a URL and return parsed JSON, using a simple on-disk cache.

    Offline use: with MEA_OFFLINE=1 the network is never touched and cached answers are used
    whatever their age. Without it, a failed request falls back to an expired cached answer.
    """
    path = _cache_path(url, params)

    def from_cache():
        cached = json.loads(path.read_text())
        if isinstance(cached, dict) and cached.get("__not_found__"):
            raise NotFound(f"No data at {url} (cached)")
        return cached

    if _is_cached(url, params) or (offline() and path.exists()):
        return from_cache()
    if offline():
        raise RuntimeError(f"Offline mode and no cached data for {url}. Run once with internet to fill data/cache.")

    last_error = None
    for attempt in range(5):
        try:
            log.info("GET %s", url)
            resp = _http().get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429:  # rate limited (Comtrade preview: ~1 call / 2 s)
                log.warning("rate limited by %s, retrying (attempt %d)", url, attempt + 1)
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code == 404:
                path.write_text(json.dumps({"__not_found__": True}))  # remember empty answers too
                raise NotFound(f"No data at {url}")
            resp.raise_for_status()
            if not getattr(resp, "content", b"x").strip():  # some APIs answer 200 with an empty body for "no data"
                path.write_text(json.dumps({"__not_found__": True}))
                raise NotFound(f"Empty answer from {url}")
            data = resp.json()
            path.write_text(json.dumps(data))
            return data
        except NotFound:
            raise
        except (requests.RequestException, ValueError) as exc:
            log.warning("request to %s failed (attempt %d): %s", url, attempt + 1, exc)
            last_error = exc
            if path.exists():  # no network or a failing API: an older answer beats no answer
                log.warning("using cached data older than a week for %s", url)
                return from_cache()
            if isinstance(exc, requests.ConnectionError) and attempt >= 1:
                break  # no connection at all: don't keep the user waiting
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
        for dim, size in zip(reversed(dims), reversed(sizes), strict=True):
            coords[dim] = categories[dim][flat_index % size]
            flat_index //= size
        coords["value"] = value
        rows.append(coords)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for dim in ("partner", "product"):
        if dim in df:
            df[f"{dim}_name"] = df[dim].map(labels.get(dim, {}))
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
        ("indicators", "QUANTITY_IN_100KG"),
    ]
    params += [("time", str(y)) for y in range(start_year, end_year + 1)]
    data = _cached_get_json(EUROSTAT_URL, params)
    df = _parse_jsonstat(data)
    if df.empty:
        return df
    if "indicators" in df:
        keys = [c for c in df.columns if c not in ("indicators", "value")]
        df = (df.pivot_table(index=keys, columns="indicators", values="value", aggfunc="sum", dropna=False)
                .reset_index().rename_axis(None, axis=1))
        df = df.rename(columns={"VALUE_IN_EUROS": "value", "QUANTITY_IN_100KG": "qty_100kg"})
        df = df[df["value"].notna()]
    if "qty_100kg" not in df:
        df["qty_100kg"] = float("nan")
    df["weight_kg"] = df["qty_100kg"] * 100

    df = df.rename(columns={"time": "year", "value": "value_eur"})
    df["year"] = df["year"].astype(int)
    df["is_aggregate"] = df["partner"].str.len() != 2
    df["is_eu_member"] = df["partner"].isin(EU27)
    # Partner "GB" was intra-EU before 2020; Eurostat already handles this in aggregates.
    return df[
        ["year", "partner", "partner_name", "value_eur", "weight_kg", "product_name",
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

    rows: list[dict] = []
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
            "weight_kg": float(r.get("netWgt") or 0) or None,
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


def eu_members_total_imports(hs_code: str, years: list[int], partner: str = "WORLD") -> pd.DataFrame:
    """
    Imports of one product into EACH EU member state from a partner
    (default WORLD = all origins, incl. intra-EU). One row per member and year.
    """
    params = [
        ("format", "JSON"), ("lang", "en"), ("freq", "A"), ("partner", partner),
        ("product", hs_code), ("flow", "1"), ("indicators", "VALUE_IN_EUROS"),
    ]
    params += [("reporter", r) for r in sorted(EU27)]
    params += [("time", str(y)) for y in years]
    data = _cached_get_json(EUROSTAT_URL, params)
    df = _parse_jsonstat(data)
    if df.empty:
        return df
    df = df.rename(columns={"time": "year", "value": "value_eur"})
    df["year"] = df["year"].astype(int)
    return df[["reporter", "year", "value_eur"]]


# --------------------------------------------------------------------------- #
# WITS (UNCTAD TRAINS): MFN import tariffs
# --------------------------------------------------------------------------- #
def _parse_wits(data: dict) -> dict | None:
    """Extract the simple-average MFN rate and its min/max from a WITS SDMX-JSON answer."""
    try:
        series = next(iter(data["dataSets"][0]["series"].values()))
        obs = next(iter(series["observations"].values()))
    except (KeyError, IndexError, StopIteration):
        return None
    attrs = data["structure"]["attributes"].get("observation", [])
    out = {"rate": obs[0]}
    for pos, attr in enumerate(attrs, start=1):
        if pos < len(obs) and obs[pos] is not None and attr.get("values"):
            vals = attr["values"]
            if obs[pos] < len(vals):
                out[attr["id"]] = vals[obs[pos]].get("id") or vals[obs[pos]].get("name")
    if out["rate"] is None:
        return None

    def num(key):
        try:
            return round(float(out[key]), 2)
        except (KeyError, TypeError, ValueError):
            return None
    return {"rate_pct": round(float(out["rate"]), 2), "min_pct": num("MIN_RATE"), "max_pct": num("MAX_RATE"),
            "tariff_lines": int(num("TOTALNOOFLINES") or 0) or None, "type": out.get("TARIFFTYPE", "MFN")}


def mfn_tariff(target: str, hs_code: str, latest_year: int, lookback: int = 4) -> dict | None:
    """
    Most-favoured-nation applied tariff (simple average over national tariff lines) that the
    target market charges on one HS6 product, from the latest year WITS has data for.
    target: "EU" (or any EU member state) or "CN".
    """
    reporter = WITS_REPORTERS["CN" if target == "CN" else "EU"]
    for year in range(latest_year, latest_year - lookback, -1):
        url = WITS_URL.format(reporter=reporter, hs=hs_code, year=year)
        try:
            data = _cached_get_json(url, {"format": "JSON"}, timeout=60)
        except RuntimeError:  # includes NotFound: no data for this year, try the previous one
            continue
        parsed = _parse_wits(data)
        if parsed:
            return {**parsed, "year": year, "source": "World Bank WITS / UNCTAD TRAINS (MFN applied, simple average)"}
    return None


def partner_tariff(target: str, hs_code: str, partner_iso2: str, latest_year: int, lookback: int = 6) -> dict | None:
    """
    Tariff the target market applies to one partner country, including preferential (FTA/GSP) rates,
    from WITS. WITS publishes partner-specific rates only where a preference exists and with a lag,
    so this walks back up to `lookback` years. Returns None when no partner-specific record exists
    (the partner then pays the MFN rate).
    """
    partner = ISO_NUMERIC.get(partner_iso2)
    if not partner:
        return None
    reporter = WITS_REPORTERS["CN" if target == "CN" else "EU"]
    for year in range(latest_year, latest_year - lookback, -1):
        url = WITS_PARTNER_URL.format(reporter=reporter, partner=partner, hs=hs_code, year=year)
        try:
            data = _cached_get_json(url, {"format": "JSON"}, timeout=30)
        except RuntimeError:
            continue
        parsed = _parse_wits(data)
        if parsed:
            return {**parsed, "year": year, "partner": partner_iso2,
                    "source": "World Bank WITS / UNCTAD TRAINS (partner-specific applied rate)"}
    return None


# --------------------------------------------------------------------------- #
# Eurostat Comext monthly: seasonality of extra-EU imports
# --------------------------------------------------------------------------- #
def eu_monthly_extra_imports(hs_code: str, years: list[int]) -> pd.Series:
    """Monthly extra-EU imports (EUR) of one product, indexed by 'YYYY-MM'."""
    params = [
        ("format", "JSON"), ("lang", "en"), ("freq", "M"), ("reporter", "EU27_2020"),
        ("partner", "EXT_EU27_2020"), ("product", hs_code), ("flow", "1"), ("indicators", "VALUE_IN_EUROS"),
    ]
    params += [("time", f"{y}-{m:02d}") for y in years for m in range(1, 13)]
    df = _parse_jsonstat(_cached_get_json(EUROSTAT_URL, params))
    if df.empty or "time" not in df:
        return pd.Series(dtype=float)
    return df.set_index("time")["value"].astype(float).sort_index()


# --------------------------------------------------------------------------- #
# ECB: monthly euro reference exchange rates
# --------------------------------------------------------------------------- #
ECB_EXR_URL = "https://data-api.ecb.europa.eu/service/data/EXR/M.{currencies}.EUR.SP00.A"


def ecb_monthly_rates(currencies: list[str], start: str) -> dict[str, dict[str, float]]:
    """
    Monthly average foreign-currency units per euro from the ECB, e.g. {"CNY": {"2024-01": 7.8, ...}}.
    Currencies the ECB does not publish are simply missing from the result.
    """
    out: dict[str, dict[str, float]] = {}
    for cur in sorted({c for c in currencies if c != "EUR"}):  # one call each: a missing currency can't break the others
        try:
            data = _cached_get_json(ECB_EXR_URL.format(currencies=cur),
                                    {"format": "jsondata", "startPeriod": start, "detail": "dataonly"}, timeout=60)
            periods = [v["id"] for v in data["structure"]["dimensions"]["observation"][0]["values"]]
            series = next(iter(data["dataSets"][0]["series"].values()))
        except (RuntimeError, KeyError, IndexError, TypeError, StopIteration):
            continue
        out[cur] = {periods[int(i)]: float(v[0]) for i, v in series["observations"].items() if v and v[0] is not None}
    return out
