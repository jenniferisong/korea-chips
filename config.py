"""What the tracker measures: product codes, partners, and policy events.

Edit this file to track different goods or countries; fetch.py and build.py
read everything from here.
"""

START_PERIOD = "201901"  # first month to download (YYYYMM)

# How many recent months to re-download on every run. Customs agencies revise
# recent months, so the cache is refreshed for this window.
REFRESH_MONTHS = 15

# UN Comtrade numeric country codes.
KOREA = 410
CHINA = 156
WORLD = 0

DESTINATIONS = {
    156: "China",
    344: "Hong Kong",
    704: "Vietnam",
    702: "Singapore",
    458: "Malaysia",
    490: "Taiwan",  # Comtrade lists Taiwan as "Other Asia, nes"
    842: "United States",
    0: "World",
}

# Destinations grouped for the charts.
DEST_GROUPS = {
    "China": [156],
    "Hong Kong": [344],
    "Southeast Asia": [704, 702, 458],
    "Taiwan": [490],
    "United States": [842],
}

# HS 6-digit products. "controlled" = covered by US export controls on China
# since 2022; "baseline" = ordinary goods used as a comparison group.
PRODUCTS = {
    "848620": ("Chipmaking equipment", "controlled"),
    "848690": ("Chipmaking equipment parts", "controlled"),
    "854231": ("Processors & logic chips", "controlled"),
    "854232": ("Memory chips", "controlled"),
    "854239": ("Other integrated circuits", "controlled"),
    "330499": ("Cosmetics", "baseline"),
    "870899": ("Auto parts", "baseline"),
}

# Two download jobs: what Korea says it shipped, and what China says it got.
# China first: it is the smaller download, so a run cut short by the API's daily
# quota still fills in both sides over successive runs.
QUERIES = [
    {"reporter": CHINA, "flow": "M", "partners": [KOREA]},
    {"reporter": KOREA, "flow": "X", "partners": list(DESTINATIONS)},
]

# US policy events drawn as markers on every chart.
EVENTS = [
    ("2022-10", "US chip export controls"),
    ("2023-10", "Controls tightened"),
    ("2024-12", "HBM & tool controls"),
    ("2025-08", "Waivers for Korean fabs in China revoked"),
]
