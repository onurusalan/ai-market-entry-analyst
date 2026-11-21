"""
Build the static web app (docs/) published on GitHub Pages.

The front end lives in site/ (HTML, CSS, JS). This script runs the real
report engine on live public data for every product x target x home country
x company size in the catalogue and writes the results as JSON, so the
published site works as an interactive analyzer without any server.

Run:  python scripts/build_site.py
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

import markdown as md
from plotly.offline import get_plotlyjs_version

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import analysis, catalog  # noqa: E402
from src import knowledge as kb  # noqa: E402
from src.report_engine import COMPANY_SIZES, generate_report  # noqa: E402

SITE = ROOT / "site"
DOCS = ROOT / "docs"
DATA = DOCS / "data.new"   # built here first, swapped into docs/data only if complete
MIN_MARKETS = 16           # of 20 product-market pairs; protects the live site from a flaky API run
REPO_URL = "https://github.com/onurusalan/ai-market-entry-analyst"

END = date.today().year - 2
START = END - 5

PRODUCTS = catalog.PRODUCTS
PRODUCT_LABELS = catalog.PRODUCT_LABELS
TARGETS = catalog.TARGET_HOMES
CASES = catalog.CASES
CASE_COMPANY = {(c[0], c[1], c[2], c[3]): c[4] for c in CASES}
EU_ISO3 = catalog.EU_ISO3

# Old static report URLs (kept working as redirects).
LEGACY = {
    "ebikes-taiwan-to-eu": ("871160", "EU", "TW", "medium"),
    "evs-china-to-eu": ("870380", "EU", "CN", "large"),
    "skincare-france-to-china": ("330499", "CN", "FR", "small"),
    "wine-italy-to-china": ("220421", "CN", "IT", "medium"),
    "medicines-germany-to-china": ("300490", "CN", "DE", "large"),
    "batteries-korea-to-eu": ("850760", "EU", "KR", "large"),
    "heatpumps-japan-to-eu": ("841861", "EU", "JP", "large"),
    "furniture-vietnam-to-eu": ("940360", "EU", "VN", "small"),
}


def memoize(fn):
    """Cache analysis results for the build (each report reuses the same market data)."""
    store: dict = {}

    def wrapper(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key not in store:
            store[key] = fn(*args, **kwargs)
        return copy.deepcopy(store[key])
    return wrapper


for _fn in ("analyze_eu_market", "analyze_china_market", "profile_for", "rank_eu_members", "tariff_for",
            "partner_tariff_for"):
    setattr(analysis, _fn, memoize(getattr(analysis, _fn)))


def name(iso2: str) -> str:
    return kb.COUNTRIES.get(iso2, {}).get("name", iso2)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def market_payload(hs: str, target: str, data: dict) -> dict:
    m = data["market"]
    share_key = "china_share_pct_by_year" if target != "CN" else "eu27_share_pct_by_year"
    return {
        "hs": hs, "target": target, "currency": m["currency"], "source": m["source"],
        "product_name": m.get("product_name"), "sector": kb.SECTOR_LABELS.get(data["sector"], data["sector"]),
        "years": [int(y) for y in m["import_market_size_by_year"]],
        "sizes": list(m["import_market_size_by_year"].values()),
        "latest_year": m["latest_year"], "latest_size": m["latest_market_size"], "cagr": m["cagr_pct"],
        "growth": data["growth_pct"], "quality": data["data_quality"],
        "hhi": m["hhi"], "hhi_label": m["hhi_label"], "unit_value": m.get("unit_value_per_kg"),
        "suppliers": [{"name": s["partner_name"], "code": s["partner"], "value": s["value"], "share": s["share_pct"],
                       "uv": s.get("unit_value_per_kg")} for s in m["top_suppliers_latest_year"]],
        "share_label": "China's share of extra-EU imports" if target != "CN" else "EU-27 share of China's imports",
        "share": {str(k): v for k, v in (m.get(share_key) or {}).items()},
        "score": data["score"], "sensitivity": data["sensitivity"],
        "ranking": [{"rank": r["rank"], "code": r["member"], "name": name(r["member"]), "iso3": EU_ISO3[r["member"]],
                     "score": r["score_0_10"], "imports": r["imports_eur"], "share": r["share_of_eu_pct"],
                     "cagr": r["cagr_pct"]} for r in data["ranking"]],
    }


def report_payload(rep, home: str, size: str) -> dict:
    d = rep.data
    body = rep.markdown.split("\n", 1)[1] if rep.markdown.startswith("# ") else rep.markdown
    return {
        "title": rep.title, "home": home, "home_name": name(home), "size": size,
        "verdict": d["verdict"], "score": d["score"]["score_0_10"], "mode": d["entry_mode"]["mode"],
        "cage": d["cage"]["overall_label"], "cage_dims": d["cage_dimensions"],
        "distance_km": round(d["cage"].get("distance_km") or 0),
        "risks": [{"risk": r["risk"], "likelihood": r["likelihood"], "impact": r["impact"]} for r in d["risks"]],
        "tariff": {"mfn": (d["tariff"].get("mfn") or {}).get("rate_pct"), "mfn_year": (d["tariff"].get("mfn") or {}).get("year"),
                   "applicable": d["tariff"]["applicable_pct"], "basis": d["tariff"]["basis"],
                   "pref_year": (d["tariff"].get("pref") or {}).get("year"), "fta": d["tariff"].get("fta"),
                   "trade_defence": bool(d["tariff"].get("trade_defence"))},
        "cost": d["landed_cost"]["assumptions"] | {"vat_country": name(d["vat_country"])},
        "position": d["position"],
        "html": md.markdown(body, extensions=["tables"]),
    }


def insights_payload(markets: dict[str, dict]) -> dict:
    """Cross-product view: how dependent is the EU on China, and how present is the EU in China?"""
    eu, cn = [], []
    for hs, label, icon in PRODUCTS:
        m = markets.get(f"{hs}-EU")
        if m and m["share"]:
            years = sorted(m["share"])
            eu.append({"hs": hs, "label": label, "icon": icon, "market": m["latest_size"], "hhi": m["hhi"],
                       "china_share": m["share"][years[-1]], "china_share_first": m["share"][years[0]],
                       "first_year": int(years[0]), "growth": m["growth"], "confidence": m["quality"]["confidence"]})
        c = markets.get(f"{hs}-CN")
        if c and c["share"]:
            years = sorted(c["share"])
            top = c["suppliers"][0] if c["suppliers"] else {}
            cn.append({"hs": hs, "label": label, "icon": icon, "market": c["latest_size"], "eu_share": c["share"][years[-1]],
                       "eu_share_first": c["share"][years[0]], "first_year": int(years[0]), "top_supplier": top.get("name"),
                       "top_share": top.get("share"), "growth": c["growth"], "confidence": c["quality"]["confidence"]})
    eu.sort(key=lambda r: r["china_share"], reverse=True)
    cn.sort(key=lambda r: r["eu_share"], reverse=True)
    return {"eu_dependency": eu, "eu_in_china": cn}



def prefetch_tariffs() -> None:
    """Warm the on-disk cache for WITS in parallel (it is slow and needs many small calls)."""
    from concurrent.futures import ThreadPoolExecutor

    from src import data_sources as ds
    from src.report_engine import needs_partner_lookup
    jobs = [("mfn", t, hs, None) for hs, _, _ in PRODUCTS for t in TARGETS]
    jobs += [("partner", t, hs, h) for hs, _, _ in PRODUCTS for t, v in TARGETS.items() for h in v["homes"]
             if needs_partner_lookup(t, h)]

    def run(job):
        kind, t, hs, h = job
        try:
            return ds.mfn_tariff(t, hs, END) if kind == "mfn" else ds.partner_tariff(t, hs, h, END)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = sum(1 for r in pool.map(run, jobs) if r)
    print(f"Tariffs: {found} of {len(jobs)} WITS lookups returned data")


def build_data() -> dict:
    prefetch_tariffs()
    available, featured, markets = [], [], {}
    for hs, label, _icon in PRODUCTS:
        for target, tinfo in TARGETS.items():
            print(f"→ {hs} {label} → {tinfo['label']}")
            ok = False
            for home in tinfo["homes"]:
                for size in COMPANY_SIZES:
                    company = CASE_COMPANY.get((hs, target, home, size), f"{label} producer")
                    try:
                        rep = generate_report(hs, target, home, company, size, START, END, label)
                    except Exception as exc:  # skip unavailable product/market combinations
                        print(f"   skipped: {exc}")
                        break
                    if not ok:
                        markets[f"{hs}-{target}"] = market_payload(hs, target, rep.data)
                        write_json(DATA / "m" / f"{hs}-{target}.json", markets[f"{hs}-{target}"])
                        ok = True
                    write_json(DATA / "r" / f"{hs}-{target}-{home}-{size}.json", report_payload(rep, home, size))
                if not ok:
                    break
            if ok:
                available.append(f"{hs}-{target}")

    for hs, target, home, size, company, headline in CASES:
        path = DATA / "r" / f"{hs}-{target}-{home}-{size}.json"
        if not path.exists():
            continue
        r = json.loads(path.read_text())
        m = json.loads((DATA / "m" / f"{hs}-{target}.json").read_text())
        label, icon = next((p[1], p[2]) for p in PRODUCTS if p[0] == hs)
        featured.append({"hs": hs, "target": target, "home": home, "size": size, "label": label, "icon": icon,
                         "company": company, "headline": headline, "home_name": name(home),
                         "target_name": TARGETS[target]["label"], "verdict": r["verdict"], "score": r["score"],
                         "mode": r["mode"], "market": m["latest_size"], "currency": m["currency"],
                         "year": m["latest_year"], "cagr": m["growth"]})

    write_json(DATA / "insights.json", insights_payload(markets))
    backtest = []
    for hs, label, icon in PRODUCTS:
        try:
            bt = analysis.backtest_eu_ranking(hs, END)
        except Exception as exc:  # validation is optional; never block the build
            print(f"   backtest skipped for {hs}: {exc}")
            bt = None
        if bt:
            backtest.append({**bt, "label": label, "icon": icon})
    write_json(DATA / "backtest.json", backtest)

    catalog = {
        "updated": date.today().isoformat(), "years": [START, END], "repo": REPO_URL,
        "kb": kb.kb_status(),
        "vat": {code: {"name": name(code), "rate": rate} for code, rate in sorted(kb.VAT_RATES.items(), key=lambda x: name(x[0]))},
        "trade_policy": [{"hs": hs, "label": PRODUCT_LABELS.get(hs, f"HS {hs}"), "note": note,
                          "checked": kb.TRADE_DEFENCE_META.get(hs, (kb.KB_AS_OF, None))[0],
                          "source": kb.TRADE_DEFENCE_META.get(hs, (None, None))[1],
                          "in_catalogue": hs in PRODUCT_LABELS}
                         for hs, note in kb.TRADE_DEFENCE_NOTES.items()],
        "plotly": get_plotlyjs_version(),
        "products": [{"hs": hs, "label": label, "icon": icon} for hs, label, icon in PRODUCTS],
        "targets": {t: {"label": v["label"], "homes": [{"code": h, "name": name(h)} for h in v["homes"]]}
                    for t, v in TARGETS.items()},
        "sizes": COMPANY_SIZES, "available": available, "featured": featured,
        "report_count": len(list((DATA / "r").glob("*.json"))),
    }
    write_json(DATA / "catalog.json", catalog)
    return catalog


def analytics_tag() -> str:
    """
    Privacy-friendly, cookie-free visitor counting with GoatCounter (free for non-commercial use).
    Off unless the GOATCOUNTER_CODE environment variable (a GitHub Actions repository variable) is set.
    """
    code = os.getenv("GOATCOUNTER_CODE", "").strip()
    if not code or not code.replace("-", "").isalnum():
        return ""
    return (f'<script data-goatcounter="https://{code}.goatcounter.com/count" '
            'async src="https://gc.zgo.at/count.js"></script>')


def copy_front_end(plotly_version: str) -> None:
    for src in SITE.rglob("*"):
        if src.is_dir() or src.name == "og.html":  # og.html is only the template for the share image
            continue
        dst = DOCS / src.relative_to(SITE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".html":
            dst.write_text(src.read_text().replace("{{PLOTLY_VERSION}}", plotly_version)
                           .replace("{{ANALYTICS}}", analytics_tag()))
        else:
            shutil.copy2(src, dst)
    for slug, (hs, target, home, size) in LEGACY.items():
        url = f"../report.html?p={hs}&t={target}&h={home}&s={size}"
        (DOCS / "reports").mkdir(exist_ok=True)
        (DOCS / "reports" / f"{slug}.html").write_text(
            f'<!doctype html><meta charset="utf-8"><title>Redirecting…</title>'
            f'<meta http-equiv="refresh" content="0; url={url}"><link rel="canonical" href="{url}">'
            f'<a href="{url}">Open the report</a>')
    (DOCS / ".nojekyll").write_text("")


def main() -> None:
    shutil.rmtree(DATA, ignore_errors=True)
    catalog = build_data()
    if len(catalog["available"]) < MIN_MARKETS:
        shutil.rmtree(DATA, ignore_errors=True)
        sys.exit(f"Only {len(catalog['available'])} markets built (minimum {MIN_MARKETS}); keeping the current site.")
    shutil.rmtree(DOCS / "data", ignore_errors=True)
    shutil.rmtree(DOCS / "assets", ignore_errors=True)
    (DOCS / "cases.json").unlink(missing_ok=True)
    DATA.rename(DOCS / "data")
    copy_front_end(catalog["plotly"])
    print(f"Built {catalog['report_count']} reports for {len(catalog['available'])} markets into {DOCS}")


if __name__ == "__main__":
    main()
