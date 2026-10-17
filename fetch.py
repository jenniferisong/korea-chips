"""Download monthly trade data from the UN Comtrade public API into data/comtrade.csv.

Uses the free preview endpoint (no API key). It takes one month per call and
allows a limited number of calls per day, so months already in the cache are
skipped unless they fall inside the REFRESH_MONTHS revision window: a weekly
run makes about 30 calls. If the daily quota runs out, progress is saved and
the next run continues where this one stopped.
"""

import csv
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config

API = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
CACHE = Path(__file__).parent / "data" / "comtrade.csv"
FIELDS = ["period", "reporter", "flow", "partner", "cmd", "value_usd", "net_kg"]
PAUSE_SECONDS = 1.5
MAX_ROWS = 500  # the public preview API returns at most this many rows per call


def months(start, end):
    """Every YYYYMM string from start to end inclusive."""
    y, m = int(start[:4]), int(start[4:])
    out = []
    while f"{y}{m:02d}" <= end:
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


class QuotaExceeded(Exception):
    """The free API's daily request allowance is used up."""


def request(query, period):
    """One API call: one reporter, one month, all partners and products."""
    params = {
        "reporterCode": query["reporter"],
        "period": period,
        "partnerCode": ",".join(map(str, query["partners"])),
        "cmdCode": ",".join(config.PRODUCTS),
        "flowCode": query["flow"],
        "partner2Code": 0,
        "customsCode": "C00",
        "motCode": 0,
        "includeDesc": "false",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                body = json.load(resp)
            if body.get("count", 0) >= MAX_ROWS:
                raise RuntimeError("hit the 500-row cap; track fewer partners or products")
            return body.get("data") or []
        except urllib.error.HTTPError as err:
            if err.code == 403:
                raise QuotaExceeded(err.reason) from err
            if err.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2 ** (attempt + 2))
    raise RuntimeError(f"gave up on {query['reporter']} {period}")


def to_rows(records, query):
    rows = []
    for r in records:
        value = r.get("primaryValue")
        if value is None:
            continue
        rows.append({
            "period": str(r["period"]),
            "reporter": query["reporter"],
            "flow": query["flow"],
            "partner": r["partnerCode"],
            "cmd": r["cmdCode"],
            "value_usd": value,
            "net_kg": r.get("netWgt") or "",
        })
    return rows


def load_cache():
    if not CACHE.exists():
        return []
    with CACHE.open() as f:
        return list(csv.DictReader(f))


def main():
    today = dt.date.today()
    last = today.replace(day=1) - dt.timedelta(days=1)
    all_months = months(config.START_PERIOD, last.strftime("%Y%m"))
    refresh = set(all_months[-config.REFRESH_MONTHS:])

    cached = load_cache()
    have = {(r["reporter"], r["period"]) for r in cached}
    fetched, failures, quota_hit = [], 0, False
    for q in config.QUERIES:
        todo = [p for p in all_months if p in refresh or (str(q["reporter"]), p) not in have]
        for period in todo:
            try:
                rows = to_rows(request(q, period), q)
            except QuotaExceeded:
                quota_hit = True
                break
            except Exception as err:  # keep going; the old cache still covers this month
                print(f"  failed {q['reporter']} {period}: {err}", file=sys.stderr)
                failures += 1
                continue
            fetched.extend(rows)
            print(f"  {q['reporter']} {period}: {len(rows)} rows")
            time.sleep(PAUSE_SECONDS)
        if quota_hit:
            break

    # A month that came back empty keeps whatever the cache had for it.
    replaced = {(str(r["reporter"]), r["period"]) for r in fetched}
    keep = [r for r in cached if (r["reporter"], r["period"]) not in replaced]
    keep.extend(fetched)
    keep.sort(key=lambda r: (str(r["reporter"]), r["period"], str(r["partner"]), r["cmd"]))

    if not keep:
        sys.exit("No data at all: the API may be down. Nothing written.")
    if quota_hit:
        # Progress so far is saved; the next run picks up the missing months.
        print("::warning::UN Comtrade daily quota reached; the rest will be fetched next run.")
    CACHE.parent.mkdir(exist_ok=True)
    with CACHE.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(keep)
    print(f"Wrote {len(keep)} rows to {CACHE} ({failures} failed calls)")


if __name__ == "__main__":
    main()
