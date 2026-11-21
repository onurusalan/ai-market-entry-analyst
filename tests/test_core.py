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
