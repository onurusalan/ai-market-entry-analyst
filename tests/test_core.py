"""Offline unit tests: no network calls (data access is monkeypatched)."""

import pandas as pd
import pytest

from src import analysis, report_engine
from src import data_sources as ds


# ---------------------------------------------------------------- metrics
def test_hhi_monopoly_and_even_split():
    assert analysis.hhi([100]) == 10000
    assert analysis.hhi([25, 25, 25, 25]) == 2500


@pytest.mark.parametrize("value,label", [(500, "Unconcentrated"), (1500, "Moderately"), (3000, "Highly")])
def test_hhi_bands(value, label):
    assert analysis.hhi_label(value).startswith(label)


def test_cagr():
    assert analysis.cagr(100, 200, 1) == 100.0
    assert analysis.cagr(100, 121, 2) == 10.0
    assert analysis.cagr(0, 100, 3) is None


def test_attractiveness_score_bounds():
    market = {"latest_market_size": 1e9, "cagr_pct": 10, "hhi": 2000}
    s = analysis.attractiveness_score(market, None)
    assert 0 <= s["score_0_10"] <= 10
    assert abs(sum(s["weights"].values()) - 1) < 1e-9
    assert s["sub_scores"]["market_size"] == 6.0


# ---------------------------------------------------------------- parsing
def test_parse_jsonstat():
    data = {
        "id": ["partner", "time"], "size": [2, 2],
        "dimension": {
            "partner": {"category": {"index": {"CN": 0, "TW": 1}, "label": {"CN": "China", "TW": "Taiwan"}}},
            "time": {"category": {"index": {"2023": 0, "2024": 1}}},
        },
        "value": {"0": 10, "1": 20, "3": 40},  # TW-2023 missing
    }
    df = ds._parse_jsonstat(data)
    assert len(df) == 3
    row = df[(df.partner == "TW") & (df.time == "2024")].iloc[0]
    assert row.value == 40 and row.partner_name == "Taiwan"


# ---------------------------------------------------------------- frameworks
def test_haversine_berlin_beijing():
    km = report_engine.haversine_km("DE", "CN")
    assert 7000 < km < 7700


def test_cage_same_single_market_is_low_admin():
    cage = report_engine.cage_analysis("FR", "DE", {"gdp_per_capita_usd": 49000}, {"gdp_per_capita_usd": 60000})
    assert cage["dimensions"]["Administrative"][0] == "Low"
    assert cage["dimensions"]["Geographic"][0] == "Low"


def test_cage_eu_to_china_is_high():
    cage = report_engine.cage_analysis("DE", "CN", {"gdp_per_capita_usd": 60000}, {"gdp_per_capita_usd": 13800})
    assert cage["overall_label"] == "High"


def _score(total, inst=7.0):
    return {"score_0_10": total, "sub_scores": {"institutional_quality": inst}}


def test_entry_mode_regulated_sector_in_china_is_jv():
    cage = {"overall": 3.0, "overall_label": "High"}
    mode = report_engine.entry_mode("CN", "pharma", "large", _score(7), cage, {})
    assert "Joint venture" in mode["mode"]


def test_entry_mode_low_score_is_exporting():
    cage = {"overall": 2.0, "overall_label": "Medium"}
    mode = report_engine.entry_mode("EU", "machinery", "medium", _score(4), cage, {})
    assert "exporting" in mode["mode"].lower()


def test_entry_mode_attractive_close_large_is_subsidiary():
    cage = {"overall": 1.5, "overall_label": "Low"}
    mode = report_engine.entry_mode("DE", "machinery", "large", _score(7.5, inst=8), cage, {})
    assert "subsidiary" in mode["mode"].lower()


# ---------------------------------------------------------------- end-to-end (mocked data)
def _mock_report(monkeypatch):
    market = {
        "market": "China", "hs_code": "330499", "currency": "USD", "source": "UN Comtrade (test)",
        "years": [2019, 2024], "import_market_size_by_year": {2019: 1e10, 2024: 1.2e10},
        "latest_year": 2024, "latest_market_size": 1.2e10, "cagr_pct": 3.7,
        "top_suppliers_latest_year": [{"partner": "FR", "partner_name": "France", "value": 3e9, "share_pct": 25.0}],
        "hhi": 1500, "hhi_label": "Moderately concentrated", "eu27_share_pct_by_year": {2019: 30.0, 2024: 35.0},
    }
    profiles = {"CN": {"country": "CN", "gdp_per_capita_usd": 13800, "logistics_performance_1_5": 3.7,
                       "rule_of_law_-2.5_2.5": -0.4},
                "FR": {"country": "FR", "gdp_per_capita_usd": 49000, "logistics_performance_1_5": 3.9,
                       "rule_of_law_-2.5_2.5": 1.2}}
    monkeypatch.setattr(analysis, "analyze_china_market", lambda *a, **k: market)
    monkeypatch.setattr(analysis, "profile_for", lambda iso: profiles.get(iso))
    monkeypatch.setattr(analysis, "partner_tariff_for", lambda *a, **k: None)
    monkeypatch.setattr(analysis, "fx_risk", lambda home, target: {"home_currency": "EUR", "target_currency": "CNY",
                                                                   "level": "Low", "volatility_pct": 4.9, "note": "test"})
    monkeypatch.setattr(analysis, "tariff_for", lambda *a, **k: {"rate_pct": 5.0, "min_pct": 5.0, "max_pct": 5.0,
                                                                  "tariff_lines": 1, "year": 2023, "source": "test"})

    rep = report_engine.generate_report("330499", "CN", "FR", "Test SA", "small", 2019, 2024, "Skincare")
    for section in ["Executive Summary", "PESTEL", "CAGE", "Risk Matrix", "Entry Mode", "90-Day"]:
        assert section in rep.markdown
    assert rep.data["verdict"] in {"ENTER", "ENTER WITH CAUTION", "DO NOT ENTER NOW"}
    assert "e-commerce" in rep.data["entry_mode"]["mode"].lower()
    assert rep.data["tariff"]["applicable_pct"] == 5.0          # France has no FTA with China
    assert rep.data["position"]["present"] is False             # no supplier_positions in the fixture
    assert "Sensitivity to the weights" in rep.markdown and "landed cost" in rep.markdown.lower()
    assert "Generated" not in rep.markdown                      # deterministic output
    return rep


def test_generate_report_end_to_end(monkeypatch):
    _mock_report(monkeypatch)


# ---------------------------------------------------------------- web app data (mocked data)
def test_site_payloads_are_json_ready(monkeypatch):
    import json

    from scripts import build_site

    rep = _mock_report(monkeypatch)
    m = build_site.market_payload("330499", "CN", rep.data)
    r = build_site.report_payload(rep, "FR", "small")
    json.dumps(m)
    json.dumps(r)
    assert m["years"] == [2019, 2024] and m["share"] == {"2019": 30.0, "2024": 35.0}
    assert m["suppliers"][0]["name"] == "France" and m["ranking"] == []
    assert r["verdict"] == rep.data["verdict"] and r["home_name"] == "France"
    assert r["html"].lstrip().startswith("<p>") and "<h1>" not in r["html"]
    assert set(r["cage_dims"]) == {"Cultural", "Administrative", "Geographic", "Economic"}


# ---------------------------------------------------------------- data reliability
def test_trend_growth_matches_constant_growth():
    series = {2019 + i: 100 * 1.10 ** i for i in range(6)}
    assert analysis.trend_growth(series) == pytest.approx(10.0, abs=0.01)


def test_data_quality_flags_series_break_and_small_market():
    series = {2019: 1_000, 2020: 2e6, 2021: 3e6, 2022: 2.5e6, 2023: 3e6, 2024: 3.3e6}
    dq = analysis.data_quality(series, 3.3e6, "871160")
    assert dq["growth_window"][0] == 2020
    assert dq["confidence"] == "Low"
    assert any("Series break" in f for f in dq["flags"]) and any("Small market" in f for f in dq["flags"])


def test_data_quality_hs2022_code_is_flagged():
    series = {2022: 9e9, 2023: 8e9, 2024: 7e9}
    dq = analysis.data_quality(series, 7e9, "854143")
    assert dq["confidence"] == "Medium" and "HS2022" in dq["flags"][0]


def test_low_confidence_shrinks_growth_score():
    base = {"latest_market_size": 1e9, "growth_trend_pct": 30.0, "hhi": 2000}
    high = analysis.attractiveness_score({**base, "data_quality": {"confidence": "High"}})
    low = analysis.attractiveness_score({**base, "data_quality": {"confidence": "Low"}})
    assert high["sub_scores"]["growth"] == 10.0 and low["sub_scores"]["growth"] == 7.5


def test_score_sensitivity_detects_borderline_verdicts():
    robust = analysis.score_sensitivity({"sub_scores": {k: 8.0 for k in analysis.WEIGHT_SCENARIOS["Base case"]}})
    assert robust["robust"] and robust["min"] == robust["max"] == 8.0
    mixed = analysis.score_sensitivity({"sub_scores": {"market_size": 10, "growth": 9, "competitive_openness": 1,
                                                       "institutional_quality": 6, "logistics": 6}})
    assert not mixed["robust"]


# ---------------------------------------------------------------- tariffs, landed cost, position
def test_landed_cost_arithmetic():
    c = report_engine.landed_cost(100, freight_pct=10, duty_pct=10, vat_pct=20, other_pct=0)
    assert c["duty"] == 11.0                     # duty on CIF value 110
    assert c["import_vat"] == pytest.approx(24.2)  # VAT on 110 + 11
    assert c["landed_ex_vat"] == 121.0 and c["uplift_ex_vat_pct"] == 21.0


def test_tariff_position_fta_vs_mfn():
    mfn = {"rate_pct": 2.7}
    kr = report_engine.tariff_position("EU", "KR", "850760", mfn)
    us = report_engine.tariff_position("EU", "US", "850760", mfn)
    de = report_engine.tariff_position("EU", "DE", "850760", mfn)
    assert kr["applicable_pct"] == 0.0 and "EU-Korea" in kr["basis"]
    assert us["applicable_pct"] == 2.7 and de["applicable_pct"] == 0.0
    pref = report_engine.tariff_position("EU", "KR", "850760", mfn, {"type": "PREF", "rate_pct": 1.2, "year": 2021})
    assert pref["applicable_pct"] == 1.2 and "2021" in pref["basis"]
    assert report_engine.needs_partner_lookup("EU", "IN") and not report_engine.needs_partner_lookup("EU", "US")
    assert not report_engine.needs_partner_lookup("EU", "DE") and report_engine.needs_partner_lookup("CN", "KR")


def test_competitive_position_price_level():
    market = {"unit_value_per_kg": 10.0,
              "top_suppliers_latest_year": [{"partner": "TW", "unit_value_per_kg": 30.0}],
              "supplier_positions": {"TW": {"rank": 2, "suppliers": 40, "share_by_year": {2019: 30.0, 2024: 22.0}}}}
    pos = report_engine.competitive_position("TW", market)
    assert pos["rank"] == 2 and pos["share_change_pp"] == -8.0 and pos["price_position"] == "Premium"
    assert report_engine.competitive_position("BR", market)["present"] is False


def test_kb_status_flags_stale_notes():
    from datetime import date

    from src import knowledge as kb
    assert kb.kb_status(date(2026, 12, 1), "2026-11-21")["stale"] is False
    assert kb.kb_status(date(2028, 1, 1), "2026-11-21")["stale"] is True


# ---------------------------------------------------------------- data layer with recorded API answers
FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def test_eurostat_parser_pivots_value_and_quantity(monkeypatch):
    import json
    fx = json.loads((FIXTURES / "eurostat_two_indicators.json").read_text())
    monkeypatch.setattr(ds, "_cached_get_json", lambda *a, **k: fx)
    df = ds.eu_imports_by_partner("871160", 2023, 2024)
    cn24 = df[(df["partner"] == "CN") & (df["year"] == 2024)].iloc[0]
    assert cn24["value_eur"] == 800 and cn24["weight_kg"] == 700
    m = analysis.analyze_eu_market("871160", 2023, 2024)
    assert m["latest_market_size"] == 1100 and m["top_suppliers_latest_year"][0]["unit_value_per_kg"] == pytest.approx(800 / 700, abs=0.01)
    assert m["supplier_positions"]["TW"]["rank"] == 2


def test_wits_parser_reads_mfn_rate(monkeypatch):
    import json
    fx = json.loads((FIXTURES / "wits_mfn.json").read_text())
    calls = []

    def fake(url, params=None, **k):
        calls.append(url)
        if "/year/2024/" in url:
            raise ds.NotFound("no 2024 data yet")
        return fx
    monkeypatch.setattr(ds, "_cached_get_json", fake)
    t = ds.mfn_tariff("EU", "871160", 2024)
    assert t["rate_pct"] == 6.0 and t["year"] == 2023 and t["tariff_lines"] == 2
    assert "/reporter/918/" in calls[0]


def test_backtest_reports_rank_correlations(monkeypatch):
    members = ["AT", "BE", "DE", "FR", "IT", "NL"]
    monkeypatch.setattr(analysis, "rank_eu_members", lambda hs, a, b: [
        {"member": m, "score_0_10": 10 - i} for i, m in enumerate(members)])
    rows = [{"reporter": m, "year": y, "value_eur": v} for i, m in enumerate(members)
            for y, v in ((2020, 100), (2024, 100 + (len(members) - i) * 10))]
    monkeypatch.setattr(ds, "eu_members_total_imports", lambda hs, years: pd.DataFrame(rows))
    bt = analysis.backtest_eu_ranking("871160", 2024)
    assert bt["spearman_vs_gain"] == 1.0 and bt["top5_hits"] == 5


# ---------------------------------------------------------------- optional AI agent (no network, fake client)
def test_agent_loop_with_fake_client():
    from types import SimpleNamespace as NS

    from src import agent

    msgs = [
        NS(usage=NS(input_tokens=100, output_tokens=20), stop_reason="tool_use",
           content=[NS(type="tool_use", name="rule_based_entry_report", input={"hs_code": "871160"})]),
        NS(usage=NS(input_tokens=300, output_tokens=900), stop_reason="end_turn",
           content=[NS(type="text", text="# Report\nVerdict: ENTER")]),
    ]
    seen = []
    fake = NS(beta=NS(messages=NS(tool_runner=lambda **kw: (seen.append(kw), iter(msgs))[1])))
    events = []
    res = agent.run_agent(agent.build_prompt("Co", "E-bikes", "Taiwan", "EU-27"),
                          on_event=lambda k, p: events.append(p["name"]), client=fake)
    assert res.report_markdown.startswith("# Report") and res.input_tokens == 400
    assert events == ["rule_based_entry_report"]
    assert seen[0]["thinking"] == {"type": "adaptive"} and any(getattr(t, "name", None) == "rule_based_entry_report"
                                                                for t in seen[0]["tools"])


def test_analytics_tag_is_opt_in(monkeypatch):
    from scripts import build_site
    monkeypatch.delenv("GOATCOUNTER_CODE", raising=False)
    assert build_site.analytics_tag() == ""
    monkeypatch.setenv("GOATCOUNTER_CODE", "market-entry")
    assert "market-entry.goatcounter.com" in build_site.analytics_tag()
    monkeypatch.setenv("GOATCOUNTER_CODE", "bad code\"><script>")
    assert build_site.analytics_tag() == ""


def test_site_build_smoke(monkeypatch, tmp_path):
    """Run the whole static-site build on mocked data into a temp folder (catches wiring bugs)."""
    from scripts import build_site

    rep = _mock_report(monkeypatch)
    monkeypatch.setattr(build_site, "generate_report", lambda *a, **k: rep)
    monkeypatch.setattr(build_site, "prefetch_tariffs", lambda: None)
    monkeypatch.setattr(build_site.analysis, "backtest_eu_ranking", lambda *a, **k: None)
    monkeypatch.setattr(build_site, "DOCS", tmp_path)
    monkeypatch.setattr(build_site, "DATA", tmp_path / "data.new")
    monkeypatch.setattr(build_site, "MIN_MARKETS", 1)
    build_site.main()
    import json
    cat = json.loads((tmp_path / "data" / "catalog.json").read_text())
    assert cat["report_count"] == 480 and cat["trade_policy"] and cat["vat"]["DE"]["rate"] == 19
    html = (tmp_path / "report.html").read_text()
    assert "{{" not in html and (tmp_path / "insights.html").exists() and (tmp_path / "compare.html").exists()


# ---------------------------------------------------------------- command-line interface
def test_cli_report_markdown_and_json(monkeypatch, capsys, tmp_path):
    from src import cli
    rep = _mock_report(monkeypatch)
    calls = []
    monkeypatch.setattr(cli, "generate_report", lambda *a, **k: (calls.append(a), rep)[1])
    assert cli.main(["report", "--hs", "330499", "--target", "cn", "--home", "fr", "--size", "small"]) == 0
    assert capsys.readouterr().out.startswith("# Market Entry Report")
    assert calls[0][:2] == ("330499", "CN") and calls[0][-1] == "Skincare & cosmetics"   # catalogue label
    out = tmp_path / "r.json"
    assert cli.main(["report", "--hs", "330499", "--target", "CN", "--home", "FR", "--json", "-o", str(out)]) == 0
    import json
    assert json.loads(out.read_text())["verdict"] == rep.data["verdict"]


def test_cli_rejects_bad_input(capsys):
    from src import cli
    with pytest.raises(SystemExit):
        cli.main(["report", "--hs", "12345", "--target", "EU", "--home", "TW"])
    with pytest.raises(SystemExit):
        cli.main(["report", "--hs", "871160", "--target", "US", "--home", "TW"])
    assert cli.main(["report", "--hs", "871160", "--target", "EU", "--home", "DE"]) == 2


def test_cli_tariff(monkeypatch, capsys):
    from src import cli
    monkeypatch.setattr(cli.analysis, "tariff_for", lambda *a: {"rate_pct": 10.0, "year": 2023})
    monkeypatch.setattr(cli.analysis, "partner_tariff_for", lambda *a: {"type": "PREF", "rate_pct": 9.6, "year": 2021})
    assert cli.main(["tariff", "--hs", "850760", "--target", "CN", "--home", "KR"]) == 0
    out = capsys.readouterr().out
    assert "10% (2023)" in out and "9.6%" in out


def test_analyse_case_rejects_unknown_size():
    with pytest.raises(ValueError):
        report_engine.analyse_case("871160", "EU", "TW", company_size="huge")


def test_markdown_sections_render_in_order(monkeypatch):
    from src import report_markdown
    md = _mock_report(monkeypatch).markdown
    heads = [line for line in md.splitlines() if line.startswith("## ")]
    assert heads[0] == "## 1. Executive Summary" and heads[-1] == "## Sources" and len(heads) == 11
    assert len(report_markdown.SECTIONS) == 17


# ---------------------------------------------------------------- HTTP cache, retries and parsers (fake network)
class _FakeResp:
    def __init__(self, status, payload=None):
        self.status_code, self._payload = status, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


def _fake_http(monkeypatch, tmp_path, responses):
    from types import SimpleNamespace
    calls = []

    def get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        return responses.pop(0)
    monkeypatch.setattr(ds, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ds, "_http", lambda: SimpleNamespace(get=get))
    monkeypatch.setattr(ds.time, "sleep", lambda s: None)
    return calls


def test_http_cache_hit_after_first_call(monkeypatch, tmp_path):
    calls = _fake_http(monkeypatch, tmp_path, [_FakeResp(200, {"ok": 1})])
    assert ds._cached_get_json("https://x.test/a", {"q": 1}) == {"ok": 1}
    assert ds._cached_get_json("https://x.test/a", {"q": 1}) == {"ok": 1}   # served from disk
    assert len(calls) == 1


def test_http_retries_on_rate_limit_then_succeeds(monkeypatch, tmp_path):
    calls = _fake_http(monkeypatch, tmp_path, [_FakeResp(429), _FakeResp(500), _FakeResp(200, [1, 2])])
    assert ds._cached_get_json("https://x.test/b") == [1, 2] and len(calls) == 3


def test_http_404_is_cached_as_not_found(monkeypatch, tmp_path):
    calls = _fake_http(monkeypatch, tmp_path, [_FakeResp(404)])
    for _ in range(2):
        with pytest.raises(ds.NotFound):
            ds._cached_get_json("https://x.test/missing")
    assert len(calls) == 1


def test_http_gives_up_after_five_failures(monkeypatch, tmp_path):
    _fake_http(monkeypatch, tmp_path, [_FakeResp(500) for _ in range(5)])
    with pytest.raises(RuntimeError):
        ds._cached_get_json("https://x.test/down")


def _comtrade_row(year, partner, value, kg=None):
    return {"refYear": year, "partnerCode": partner, "primaryValue": value, "netWgt": kg,
            "customsCode": "C00", "motCode": 0, "partner2Code": 0}


def test_china_market_from_comtrade_rows(monkeypatch):
    lookup = {0: {"name": "World", "iso2": None, "is_group": True}, 156: {"name": "China", "iso2": "CN", "is_group": False},
              251: {"name": "France", "iso2": "FR", "is_group": False}, 36: {"name": "Australia", "iso2": "AU", "is_group": False},
              490: {"name": "Other Asia, nes", "iso2": None, "is_group": True}}
    rows = [_comtrade_row(y, p, v, kg) for y, p, v, kg in [
        (2019, 0, 1000, 100), (2019, 251, 400, 20), (2019, 36, 300, 50), (2019, 156, 100, 10), (2019, 490, 200, 20),
        (2024, 0, 1600, 160), (2024, 251, 500, 25), (2024, 36, 800, 90), (2024, 156, 100, 10), (2024, 490, 200, 20)]]
    rows.append({**_comtrade_row(2024, 251, 999), "customsCode": "C01"})   # filtered out
    monkeypatch.setattr(ds, "_comtrade_partner_lookup", lambda: lookup)
    monkeypatch.setattr(ds, "_comtrade_rows", lambda params, years: rows)
    m = analysis.analyze_china_market("220421", 2019, 2024)
    assert m["latest_market_size"] == 1500                      # world minus China's re-imports
    assert m["top_suppliers_latest_year"][0]["partner"] == "AU"
    assert {s["partner"] for s in m["top_suppliers_latest_year"]} >= {"TW"}   # 490 relabelled as Taiwan
    assert m["eu27_share_pct_by_year"][2024] == round(500 / 1500 * 100, 2)
    assert m["unit_value_per_kg"] is not None


def test_country_fundamentals_parses_world_bank(monkeypatch):
    def fake(url, params=None, **k):
        if "NY.GDP.PCAP.CD" in url:
            return [{"page": 1}, [{"country": {"id": "DE"}, "value": 54000.0, "date": "2024"}]]
        if "LP.LPI" in url:
            raise RuntimeError("down")
        return [{"page": 1}, []]
    monkeypatch.setattr(ds, "_cached_get_json", fake)
    df = ds.country_fundamentals(["DE", "FR"])
    de = df.set_index("country").loc["DE"]
    assert de["gdp_per_capita_usd"] == 54000.0 and de["gdp_per_capita_usd_year"] == "2024"


def test_rank_eu_members_orders_by_score(monkeypatch):
    rows = [{"reporter": m, "year": y, "value_eur": v} for m, y, v in [
        ("DE", 2019, 1e9), ("DE", 2024, 2e9), ("MT", 2019, 1e6), ("MT", 2024, 1.1e6)]]
    monkeypatch.setattr(ds, "eu_members_total_imports", lambda hs, years: pd.DataFrame(rows))
    monkeypatch.setattr(analysis, "country_profiles", lambda codes: [
        {"country": "DE", "gdp_per_capita_usd": 54000, "logistics_performance_1_5": 4.1, "rule_of_law_-2.5_2.5": 1.5},
        {"country": "MT", "gdp_per_capita_usd": 38000, "logistics_performance_1_5": 3.0}])
    ranking = analysis.rank_eu_members("871160", 2019, 2024)
    assert [r["member"] for r in ranking] == ["DE", "MT"] and ranking[0]["rank"] == 1
    assert ranking[0]["share_of_eu_pct"] == pytest.approx(2e9 / 2.0011e9 * 100, abs=0.01)


def test_supplier_momentum_gainers_and_losers():
    positions = {
        "CN": {"name": "China", "share_by_year": {2019: 50.0, 2024: 60.0}},
        "TW": {"name": "Taiwan", "share_by_year": {2019: 30.0, 2024: 22.0}},
        "VN": {"name": "Viet Nam", "share_by_year": {2019: 2.0, 2024: 8.0}},
        "XX": {"name": "Tiny", "share_by_year": {2019: 0.1, 2024: 0.5}},
    }
    mom = analysis.supplier_momentum(positions)
    assert [r["partner"] for r in mom["gainers"]] == ["CN", "VN"]
    assert mom["losers"][0]["partner"] == "TW" and mom["losers"][0]["change_pp"] == -8.0
    assert all(r["partner"] != "XX" for r in mom["gainers"] + mom["losers"])   # below 1% share



# ---------------------------------------------------------------- untapped potential, seasonality, FX risk
def test_untapped_potential_benchmarks_member_states(monkeypatch):
    extra = pd.DataFrame({"reporter": ["DE", "FR", "PL"], "value_eur": [600.0, 300.0, 100.0]})
    home = pd.DataFrame({"reporter": ["DE", "FR"], "value_eur": [150.0, 50.0]})
    monkeypatch.setattr(ds, "eu_member_imports_from",
                        lambda hs, year, partner: extra if partner == "EXT_EU27_2020" else home)
    u = analysis.untapped_potential("871160", 2024, "TW")
    assert u["home_share_pct"] == 20.0                       # 200 of 1,000
    by = {r["member"]: r for r in u["markets"]}
    assert by["PL"]["untapped"] == 20 and by["PL"]["penetration"] == 0.0
    assert by["FR"]["untapped"] == 10 and "DE" not in by     # Germany already above its benchmark
    assert analysis.untapped_potential("871160", 2024, "DE") is None   # EU members are not extra-EU suppliers


def test_seasonality_finds_peaks_and_shipping_window(monkeypatch):
    vals = {}
    for y in (2022, 2023, 2024):
        for m in range(1, 13):
            vals[f"{y}-{m:02d}"] = 200.0 if m in (5, 6, 7) else 100.0
    monkeypatch.setattr(ds, "eu_monthly_extra_imports", lambda hs, years: pd.Series(vals))
    s = analysis.seasonality("871160", 2024)
    assert set(s["peak_months"]) == {"May", "Jun", "Jul"} and s["strength"] == "Strong"
    assert s["ship_window"] == ["Mar", "Apr"]


def test_fx_risk_levels(monkeypatch):
    stable = {f"2024-{m:02d}": 7.8 for m in range(1, 13)} | {f"2025-{m:02d}": 7.8 for m in range(1, 13)}
    swing = {p: (7.0 if i % 2 else 8.5) for i, p in enumerate(sorted(stable))}
    monkeypatch.setattr(ds, "ecb_monthly_rates", lambda cur, start: {"CNY": stable, "JPY": swing})
    assert analysis.fx_risk("CN", "EU")["level"] == "Low"
    assert analysis.fx_risk("JP", "EU")["level"] == "High"
    assert analysis.fx_risk("DE", "EU")["level"] == "None"          # same currency
    assert analysis.fx_risk("VN", "EU")["level"] is None             # not published by the ECB


def test_currency_risk_follows_fx_level():
    base = dict(target="EU", home="CN", sector="consumer", market={"hhi": 500}, score={"sub_scores": {}},
                cage={"dimensions": {"Geographic": ("Low", ""), "Cultural": ("Low", "")}}, hs_code="940360")
    same = report_engine.risk_matrix(**base, fx={"level": "None"})
    assert not any("Currency" in r["risk"] for r in same)
    high = report_engine.risk_matrix(**base, fx={"level": "High", "home_currency": "JPY", "target_currency": "EUR",
                                                 "volatility_pct": 12.0})
    cur = next(r for r in high if "Currency" in r["risk"])
    assert cur["likelihood"] == "High" and "12.0%" in cur["risk"]


def test_http_empty_body_is_not_found(monkeypatch, tmp_path):
    resp = _FakeResp(200, None)
    resp.content = b""
    _fake_http(monkeypatch, tmp_path, [resp])
    with pytest.raises(ds.NotFound):
        ds._cached_get_json("https://x.test/empty")


def test_seasonality_peak_block_starts_before_strongest_month(monkeypatch):
    level = {3: 150.0, 4: 200.0, 5: 160.0}                 # strongest in April, block Mar-May
    vals = {f"{y}-{m:02d}": level.get(m, 100.0) for y in (2022, 2023, 2024) for m in range(1, 13)}
    monkeypatch.setattr(ds, "eu_monthly_extra_imports", lambda hs, years: pd.Series(vals))
    s = analysis.seasonality("841861", 2024)
    assert s["peak_months"] == ["Mar", "Apr", "May"] and s["ship_window"] == ["Jan", "Feb"]
