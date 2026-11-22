"""
Command-line interface.

    market-entry report --hs 871160 --target EU --home TW --size medium -o ebikes.md
    market-entry report --hs 220421 --target CN --home IT --json
    market-entry rank --hs 870380
    market-entry tariff --hs 850760 --target EU --home KR

(or `python -m src.cli ...` without installing the package)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from . import analysis, catalog
from . import knowledge as kb
from .report_engine import COMPANY_SIZES, generate_report, needs_partner_lookup, tariff_position

DEFAULT_END = date.today().year - 2


def _hs(value: str) -> str:
    if not (value.isdigit() and len(value) == 6):
        raise argparse.ArgumentTypeError("HS code must have exactly 6 digits, e.g. 871160")
    return value


def _country(value: str) -> str:
    code = value.upper()
    if code != "EU" and code not in kb.COUNTRIES:
        raise argparse.ArgumentTypeError(f"unknown country code {value!r}; use ISO2 such as DE, CN, TW")
    return code


def _target(value: str) -> str:
    code = _country(value)
    if code != "CN" and code != "EU" and code not in kb.EU27:
        raise argparse.ArgumentTypeError("target must be EU, an EU member state (ISO2) or CN")
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="market-entry", description="EU ⇄ China market entry analysis from official trade data.")
    p.add_argument("-v", "--verbose", action="store_true", help="log data requests")
    p.add_argument("--offline", action="store_true", help="use cached data only, never the network (same as MEA_OFFLINE=1)")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("report", help="full market entry report")
    r.add_argument("--hs", type=_hs, required=True, help="6-digit HS product code")
    r.add_argument("--target", type=_target, required=True, help="EU, an EU member state or CN")
    r.add_argument("--home", type=_country, required=True, help="company home country (ISO2)")
    r.add_argument("--size", choices=sorted(COMPANY_SIZES), default="medium")
    r.add_argument("--company", default="")
    r.add_argument("--label", default="", help="product name to show in the title")
    r.add_argument("--start", type=int, help="first year (default: end - 5)")
    r.add_argument("--end", type=int, default=DEFAULT_END, help=f"last year (default: {DEFAULT_END})")
    r.add_argument("--json", action="store_true", help="print the machine-readable data instead of Markdown")
    r.add_argument("-o", "--output", type=Path, help="write to a file instead of stdout")

    k = sub.add_parser("rank", help="rank the 27 EU member states for a product")
    k.add_argument("--hs", type=_hs, required=True)
    k.add_argument("--start", type=int)
    k.add_argument("--end", type=int, default=DEFAULT_END)
    k.add_argument("--top", type=int, default=10)

    s = sub.add_parser("serve", help="open the web app on this computer (works without internet)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")

    t = sub.add_parser("tariff", help="import duty for a product and country pair")
    t.add_argument("--hs", type=_hs, required=True)
    t.add_argument("--target", type=_target, required=True)
    t.add_argument("--home", type=_country, required=True)
    t.add_argument("--year", type=int, default=DEFAULT_END)
    return p


def _emit(text: str, output: Path | None) -> None:
    if output:
        output.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {output}", file=sys.stderr)
    else:
        print(text)


def cmd_report(a: argparse.Namespace) -> int:
    if a.target == a.home or (a.target != "CN" and a.home in kb.EU27):
        print("Home and target are the same single market; choose another pair.", file=sys.stderr)
        return 2
    label = a.label or catalog.PRODUCT_LABELS.get(a.hs, "")
    rep = generate_report(a.hs, a.target, a.home, a.company, a.size, a.start, a.end, label)
    _emit(json.dumps(rep.data, indent=2, default=str) if a.json else rep.markdown, a.output)
    return 0


def cmd_rank(a: argparse.Namespace) -> int:
    end = a.end
    rows = analysis.rank_eu_members(a.hs, a.start or end - 5, end)
    if not rows:
        print("No Eurostat data for this product.", file=sys.stderr)
        return 1
    print(f"{'#':>2}  {'Country':<14}{'Imports (EUR)':>16}{'CAGR':>9}{'Score':>8}")
    for r in rows[: a.top]:
        cagr = f"{r['cagr_pct']:+.1f}%" if r["cagr_pct"] is not None else "n/a"
        print(f"{r['rank']:>2}  {kb.COUNTRIES[r['member']]['name']:<14}{r['imports_eur']:>16,.0f}{cagr:>9}{r['score_0_10']:>8.2f}")
    return 0


def cmd_tariff(a: argparse.Namespace) -> int:
    mfn = analysis.tariff_for(a.target, a.hs, a.year)
    pref = analysis.partner_tariff_for(a.target, a.hs, a.home, a.year) if needs_partner_lookup(a.target, a.home) else None
    t = tariff_position(a.target, a.home, a.hs, mfn, pref)
    print(f"MFN rate:        {mfn['rate_pct']:g}% ({mfn['year']})" if mfn else "MFN rate:        not available")
    applicable = f"{t['applicable_pct']:g}%" if t["applicable_pct"] is not None else "n/a"
    print(f"Applicable rate: {applicable}  ({t['basis']})")
    if t.get("trade_defence"):
        print(f"Trade policy:    {t['trade_defence']}")
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    import functools
    import http.server
    import webbrowser

    docs = Path(__file__).resolve().parent.parent / "docs"
    if not (docs / "index.html").exists():
        print("docs/ not built yet: run python scripts/build_site.py once (with internet).", file=sys.stderr)
        return 1
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(docs))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    url = f"http://localhost:{a.port}/index.html"
    print(f"Serving the web app offline at {url} (Ctrl+C to stop)")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.offline:
        import os
        os.environ["MEA_OFFLINE"] = "1"
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    handlers = {"report": cmd_report, "rank": cmd_rank, "tariff": cmd_tariff, "serve": cmd_serve}
    try:
        return handlers[args.command](args)
    except ValueError as exc:  # e.g. no data for this product
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
