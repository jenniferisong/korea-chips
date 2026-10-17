"""Turn data/comtrade.csv into the published site (_site/).

Every figure is a 12-month rolling sum, which smooths out shipping lumpiness
and China's habit of reporting January and February together.

Two measures:
  * Destination mix: where Korea says its exports went.
  * Mirror ratio: what China says it imported *from Korea*, divided by what
    Korea says it exported *to China*. China counts goods by country of
    origin, Korea by first destination, so Korean goods that reach China
    through Hong Kong, Singapore or another hub push the ratio above ~1.05
    (the usual freight-and-insurance markup).
"""

import datetime as dt
import json
import shutil
from pathlib import Path

import pandas as pd

import config

ROOT = Path(__file__).parent
CACHE = ROOT / "data" / "comtrade.csv"
OUT = ROOT / "_site"
BASELINE_END = "2022-09"  # last month before the first US controls

# Products shown in the site's picker: combined groups first, then single codes.
VIEWS = {
    "chips": ("All chips", ["854231", "854232", "854239"]),
    "tools": ("All chipmaking equipment", ["848620", "848690"]),
    **{"hs" + code: (label, [code]) for code, (label, _) in config.PRODUCTS.items()},
}


def load():
    df = pd.read_csv(CACHE, dtype={"cmd": str, "period": str})
    df["month"] = pd.PeriodIndex(df["period"].str[:4] + "-" + df["period"].str[4:], freq="M")
    return df


def monthly(df, reporter, flow, partners, cmds):
    """Monthly totals for one reporter/flow over a set of partners and products.

    A month the reporter filed but with no row for this pair is a real zero.
    A month the reporter never filed is missing, except January, which China
    folds into February.
    """
    mine = df[(df.reporter == reporter) & (df.flow == flow)]
    if mine.empty:
        return pd.Series(dtype=float)
    filed = set(mine["month"])
    span = pd.period_range(min(filed), max(filed), freq="M")
    sel = mine[mine.partner.isin(partners) & mine.cmd.isin(cmds)]
    s = sel.groupby("month")["value_usd"].sum().reindex(span, fill_value=0.0)
    for m in span:
        if m not in filed and m.month != 1:
            s[m] = float("nan")
    return s


def rolling12(s):
    return s.rolling(12, min_periods=12).sum()


def at(s, month):
    month = pd.Period(month, freq="M")
    v = s.get(month)
    return None if v is None or pd.isna(v) else float(v)


def pct(new, old):
    if new is None or not old:
        return None
    return (new / old - 1) * 100


def build_view(df, cmds):
    kr = {
        name: rolling12(monthly(df, config.KOREA, "X", codes, cmds))
        for name, codes in config.DEST_GROUPS.items()
    }
    world = rolling12(monthly(df, config.KOREA, "X", [config.WORLD], cmds))
    cn_seen = rolling12(monthly(df, config.CHINA, "M", [config.KOREA], cmds))

    index = world.index
    frame = pd.DataFrame({**kr, "World": world}, index=index)
    frame["China reports"] = cn_seen.reindex(index)
    frame = frame.dropna(subset=["World"])
    mirror = frame["China reports"] / frame["China"].where(frame["China"] > 0)
    share = (frame["China"] + frame["Hong Kong"]) / frame["World"].where(frame["World"] > 0)

    def clean(s):
        return [None if pd.isna(v) else round(float(v), 4) for v in s]

    return {
        "dates": [str(m) for m in frame.index],
        "destinations": {k: clean(frame[k]) for k in config.DEST_GROUPS},
        "world": clean(frame["World"]),
        "mirror": clean(mirror),
        "china_hk_share": clean(share * 100),
    }, frame, mirror, share


def findings(label, frame, mirror, share):
    """Plain-English sentences comparing the latest 12 months with the period before controls."""
    if frame.empty:
        return []
    latest = frame.index[-1]
    year_ago = latest - 12
    out = []

    china_now, china_then = at(frame["China"], latest), at(frame["China"], year_ago)
    change = pct(china_now, china_then)
    if change is not None:
        goods = label.lower().removeprefix("all ")
        out.append(
            f"Korea shipped ${china_now / 1e9:.1f}B of {goods} straight to China in the "
            f"12 months to {latest.strftime("%b %Y")}, {abs(change):.0f}% {'more' if change >= 0 else 'less'} "
            f"than the year before."
        )

    share_now, share_base = at(share, latest), at(share, BASELINE_END)
    if share_now is not None and share_base is not None:
        out.append(
            f"China and Hong Kong took {share_now * 100:.0f}% of these exports, versus "
            f"{share_base * 100:.0f}% in the 12 months before the October 2022 controls."
        )

    sea_now, sea_base = at(frame["Southeast Asia"], latest), at(frame["Southeast Asia"], BASELINE_END)
    change = pct(sea_now, sea_base)
    if change is not None and sea_now > 1e8:
        out.append(
            f"Shipments to Vietnam, Singapore and Malaysia are {abs(change):.0f}% "
            f"{'higher' if change >= 0 else 'lower'} than before the controls "
            f"(${sea_now / 1e9:.1f}B a year)."
        )

    m_valid = mirror.dropna()
    if not m_valid.empty:
        m_month = m_valid.index[-1]
        m_now, m_base = float(m_valid.iloc[-1]), at(mirror, BASELINE_END)
        line = (
            f"China records ${m_now:.2f} of Korean-made imports for every $1 Korea says it "
            f"shipped to China directly (12 months to {m_month.strftime("%b %Y")})"
        )
        line += f", against ${m_base:.2f} before the controls." if m_base else "."
        out.append(line)
    return out


def main():
    df = load()
    views = {}
    for key, (label, cmds) in VIEWS.items():
        data, frame, mirror, share = build_view(df, cmds)
        group = "controlled" if key in ("chips", "tools") else config.PRODUCTS[key[2:]][1]
        views[key] = {"label": label, "group": group, "codes": cmds, **data,
                      "findings": findings(label, frame, mirror, share)}

    kr_last = df[df.reporter == config.KOREA]["month"].max()
    cn_last = df[df.reporter == config.CHINA]["month"].max()
    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "korea_data_through": str(kr_last),
        "china_data_through": str(cn_last),
        "baseline_end": BASELINE_END,
        "events": [{"month": m, "label": t} for m, t in config.EVENTS],
        "views": views,
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    shutil.copy(CACHE, OUT / "comtrade.csv")
    (OUT / "data.json").write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Built {OUT} — Korea data through {kr_last}, China through {cn_last}")


if __name__ == "__main__":
    main()
