"""Checks the math in build.py on a tiny hand-made dataset."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build  # noqa: E402
import fetch  # noqa: E402


def frame(rows):
    df = pd.DataFrame(rows, columns=["period", "reporter", "flow", "partner", "cmd", "value_usd"])
    df["month"] = pd.PeriodIndex(df["period"].str[:4] + "-" + df["period"].str[4:], freq="M")
    return df


def korea_months(n, value, partner=156, cmd="854232"):
    out = []
    for p in fetch.months("202001", "203001")[:n]:
        out.append((p, 410, "X", partner, cmd, value))
        out.append((p, 410, "X", 0, cmd, value * 4))
    return out


def test_months_crosses_year_end():
    assert fetch.months("202211", "202302") == ["202211", "202212", "202301", "202302"]


def test_rolling_sum_needs_twelve_months():
    df = frame(korea_months(13, 10.0))
    data, *_ = build.build_view(df, ["854232"])
    # The first 11 months have no full year behind them, so the series starts at month 12.
    assert data["dates"] == ["2020-12", "2021-01"]
    assert data["destinations"]["China"] == [120.0, 120.0]
    assert data["china_hk_share"][0] == 25.0  # 10 of every 40 to China


def test_unfiled_month_is_missing_but_january_is_zero():
    rows = [r for r in korea_months(14, 10.0) if r[0] != "202006"]
    df = frame(rows)
    s = build.monthly(df, 410, "X", [156], ["854232"])
    assert pd.isna(s[pd.Period("2020-06", freq="M")])

    cn = frame([("202012", 156, "M", 410, "854232", 5.0), ("202102", 156, "M", 410, "854232", 9.0)])
    s = build.monthly(cn, 156, "M", [410], ["854232"])
    assert s[pd.Period("2021-01", freq="M")] == 0.0


def test_mirror_ratio():
    rows = korea_months(12, 10.0)
    rows += [(p, 156, "M", 410, "854232", 15.0) for p in fetch.months("202001", "202012")]
    data, *_ = build.build_view(frame(rows), ["854232"])
    assert data["mirror"][-1] == 1.5


def test_findings_mention_the_numbers():
    rows = korea_months(36, 1e9)
    df = frame(rows)
    _, f, mirror, share = build.build_view(df, ["854232"])
    text = " ".join(build.findings("Memory chips", f, mirror, share))
    assert "$12.0B of memory chips" in text and "0% more" in text


def test_fetch_stops_at_quota_and_saves_progress(tmp_path, monkeypatch):
    calls = []

    def fake_request(query, period):
        calls.append((query["reporter"], period))
        if len(calls) == 4:
            raise fetch.QuotaExceeded("Quota Exceeded")
        return [{"period": period, "partnerCode": query["partners"][0], "cmdCode": "854232",
                 "primaryValue": 1.0}]

    monkeypatch.setattr(fetch, "request", fake_request)
    monkeypatch.setattr(fetch, "CACHE", tmp_path / "comtrade.csv")
    monkeypatch.setattr(fetch, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(fetch.config, "START_PERIOD", "202001")
    fetch.main()

    assert calls[:3] == [(156, "202001"), (156, "202002"), (156, "202003")]  # China first
    assert len(calls) == 4  # stopped at the quota instead of hammering the API
    saved = (tmp_path / "comtrade.csv").read_text().splitlines()
    assert len(saved) == 1 + 3 and saved[1].startswith("202001,156,M,410,854232")
