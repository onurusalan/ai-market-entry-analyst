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
import shutil
import sys
from datetime import date
from pathlib import Path

import markdown as md
from plotly.offline import get_plotlyjs_version

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import analysis  # noqa: E402
from src import knowledge as kb  # noqa: E402
from src.report_engine import COMPANY_SIZES, generate_report  # noqa: E402

SITE = ROOT / "site"
DOCS = ROOT / "docs"
DATA = DOCS / "data.new"   # built here first, swapped into docs/data only if complete
MIN_MARKETS = 16           # of 20 product-market pairs; protects the live site from a flaky API run
REPO_URL = "https://github.com/onurusalan/ai-market-entry-analyst"

END = date.today().year - 2
START = END - 5

PRODUCTS = [
    # hs, label, icon
    ("871160", "E-bikes", "🚲"),
    ("870380", "Battery-electric cars", "🚗"),
    ("850760", "Lithium-ion batteries", "🔋"),
    ("854143", "Solar PV modules", "☀️"),
    ("841861", "Heat pumps", "🌡️"),
    ("300490", "Medicaments", "💊"),
    ("330499", "Skincare & cosmetics", "🧴"),
    ("220421", "Bottled wine", "🍷"),
    ("940360", "Wooden furniture", "🪑"),
    ("610910", "Cotton T-shirts", "👕"),
]

TARGETS = {
    "EU": {"label": "EU-27", "homes": ["CN", "US", "JP", "KR", "TW", "VN", "IN", "GB"]},
    "CN": {"label": "China", "homes": ["DE", "FR", "IT", "ES", "NL", "US", "JP", "KR"]},
}

# Featured case studies (all of them are also reachable through the analyzer).
CASES = [
    # hs, target, home, size, company, headline
    ("870380", "EU", "CN", "large", "Chinese EV maker", "Can a Chinese EV maker scale in Europe despite countervailing duties?"),
    ("871160", "EU", "TW", "medium", "Taiwanese e-bike manufacturer", "A diversification opening in a China-dominated supply base."),
    ("330499", "CN", "FR", "small", "French premium skincare brand", "Cross-border e-commerce as a low-risk door into China."),
    ("300490", "CN", "DE", "large", "German pharmaceutical company", "Regulated market: why a partner beats going alone."),
    ("850760", "EU", "KR", "large", "Korean battery-cell producer", "Riding Europe's battery boom against Chinese incumbents."),
    ("841861", "EU", "JP", "large", "Japanese HVAC manufacturer", "Heat pumps and the EU's decarbonisation push."),
    ("220421", "CN", "IT", "medium", "Italian wine cooperative", "Competing with Australia's comeback in Chinese wine."),
    ("940360", "EU", "VN", "small", "Vietnamese furniture exporter", "Low-cost entry for a small exporter."),
]
CASE_COMPANY = {(c[0], c[1], c[2], c[3]): c[4] for c in CASES}

EU_ISO3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK",
    "EE": "EST", "ES": "ESP", "FI": "FIN", "FR": "FRA", "GR": "GRC", "HR": "HRV", "HU": "HUN",
    "IE": "IRL", "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT", "NL": "NLD",
    "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE", "SI": "SVN", "SK": "SVK",
}

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


for _fn in ("analyze_eu_market", "analyze_china_market", "profile_for", "rank_eu_members"):
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
        "hhi": m["hhi"], "hhi_label": m["hhi_label"],
        "suppliers": [{"name": s["partner_name"], "code": s["partner"], "value": s["value"], "share": s["share_pct"]}
                      for s in m["top_suppliers_latest_year"]],
        "share_label": "China's share of extra-EU imports" if target != "CN" else "EU-27 share of China's imports",
        "share": {str(k): v for k, v in (m.get(share_key) or {}).items()},
        "score": data["score"],
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
        "html": md.markdown(body, extensions=["tables"]),
    }


def build_data() -> dict:
    available, featured = [], []
    for hs, label, icon in PRODUCTS:
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
                        write_json(DATA / "m" / f"{hs}-{target}.json", market_payload(hs, target, rep.data))
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
                         "year": m["latest_year"], "cagr": m["cagr"]})

    catalog = {
        "updated": date.today().isoformat(), "years": [START, END], "repo": REPO_URL,
        "plotly": get_plotlyjs_version(),
        "products": [{"hs": hs, "label": label, "icon": icon} for hs, label, icon in PRODUCTS],
        "targets": {t: {"label": v["label"], "homes": [{"code": h, "name": name(h)} for h in v["homes"]]}
                    for t, v in TARGETS.items()},
        "sizes": COMPANY_SIZES, "available": available, "featured": featured,
        "report_count": len(list((DATA / "r").glob("*.json"))),
    }
    write_json(DATA / "catalog.json", catalog)
    return catalog


def copy_front_end(plotly_version: str) -> None:
    for src in SITE.rglob("*"):
        if src.is_dir():
            continue
        dst = DOCS / src.relative_to(SITE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".html":
            dst.write_text(src.read_text().replace("{{PLOTLY_VERSION}}", plotly_version))
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
