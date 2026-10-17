# Korea Chip Trade Tracker

**Live site: https://jenniferisong.github.io/korea-chips/**

A self-updating website that tracks where South Korea's chips and chipmaking
equipment go after US export controls on China, and whether China's customs
records agree with Korea's.

Every Monday a GitHub Action downloads the newest monthly data from the
[UN Comtrade](https://comtradeplus.un.org/) public API, recomputes the
measures, and republishes the site.

## What it measures

- **Destination mix**: Korea's exports of each product to China, Hong Kong,
  Southeast Asia (Vietnam, Singapore, Malaysia), Taiwan and the US.
- **Mirror ratio**: imports China records as made in Korea, divided by what
  Korea records as shipped straight to China. Korea logs exports by first
  destination and China logs imports by origin, so routing through a third
  country pushes the ratio above the normal ~1.05.
- **Controlled vs ordinary goods**: the China + Hong Kong share for chips and
  chipmaking tools, against cosmetics and auto parts as a comparison group.

All values are 12-month rolling sums.

## Files

| File | What it does |
|---|---|
| `config.py` | Products, countries and policy dates. Edit this to track something else. |
| `fetch.py` | Downloads data into `data/comtrade.csv`, only re-fetching recent months. |
| `build.py` | Computes the measures and writes the site to `_site/`. |
| `site/index.html` | The web page; draws the charts from `data.json`. |
| `tests/` | Checks the math on a small hand-made dataset. |

## Run it yourself

```
pip install pandas pytest
python fetch.py     # a few dozen calls; the free API has a daily limit
python build.py
python -m http.server -d _site 8000   # open http://localhost:8000
```
