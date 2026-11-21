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

    rep = report_engine.generate_report("330499", "CN", "FR", "Test SA", "small", 2019, 2024, "Skincare")
    for section in ["Executive Summary", "PESTEL", "CAGE", "Risk Matrix", "Entry Mode", "90-Day"]:
        assert section in rep.markdown
    assert rep.data["verdict"] in {"ENTER", "ENTER WITH CAUTION", "DO NOT ENTER NOW"}
    assert "e-commerce" in rep.data["entry_mode"]["mode"].lower()
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
