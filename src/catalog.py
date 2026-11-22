"""
Single source of truth for the product catalogue and country lists.

Used by both front ends (the Streamlit app and the static web app built by
scripts/build_site.py) so they always offer the same products and markets.
"""

from __future__ import annotations

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
PRODUCT_LABELS = {hs: label for hs, label, _ in PRODUCTS}

# Home countries offered for each target market in the web app.
TARGET_HOMES = {
    "EU": {"label": "EU-27", "homes": ["CN", "US", "JP", "KR", "TW", "VN", "IN", "GB"]},
    "CN": {"label": "China", "homes": ["DE", "FR", "IT", "ES", "NL", "US", "JP", "KR"]},
}

EU_ISO3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK",
    "EE": "EST", "ES": "ESP", "FI": "FIN", "FR": "FRA", "GR": "GRC", "HR": "HRV", "HU": "HUN",
    "IE": "IRL", "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT", "NL": "NLD",
    "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE", "SI": "SVN", "SK": "SVK",
}

# Featured case studies: hs, target, home, size, company, headline
CASES = [
    ("870380", "EU", "CN", "large", "Chinese EV maker", "Can a Chinese EV maker scale in Europe despite countervailing duties?"),
    ("871160", "EU", "TW", "medium", "Taiwanese e-bike manufacturer", "A premium niche in a China-dominated supply base."),
    ("330499", "CN", "FR", "small", "French premium skincare brand", "Cross-border e-commerce as a low-risk door into China."),
    ("300490", "CN", "DE", "large", "German pharmaceutical company", "Regulated market: why a partner beats going alone."),
    ("850760", "EU", "KR", "large", "Korean battery-cell producer", "Duty-free under the EU-Korea FTA, against Chinese incumbents."),
    ("841861", "EU", "JP", "large", "Japanese HVAC manufacturer", "Heat pumps and the EU's decarbonisation push."),
    ("220421", "CN", "IT", "medium", "Italian wine cooperative", "A 14% tariff and Australia's comeback in Chinese wine."),
    ("940360", "EU", "VN", "small", "Vietnamese furniture exporter", "Low-cost entry for a small exporter with FTA access."),
]


# EU-27 tile-grid map: (row, column) per member state, roughly geographic.
# Drawn as squares, so maps need no external geometry files and work offline.
EU_TILES = {
    "SE": (0, 4), "FI": (0, 5),
    "IE": (1, 0), "DK": (1, 3), "EE": (1, 5),
    "NL": (2, 2), "DE": (2, 3), "PL": (2, 4), "LV": (2, 5),
    "BE": (3, 1), "LU": (3, 2), "CZ": (3, 3), "SK": (3, 4), "LT": (3, 5),
    "FR": (4, 1), "AT": (4, 3), "HU": (4, 4), "RO": (4, 5),
    "PT": (5, 0), "ES": (5, 1), "IT": (5, 2), "SI": (5, 3), "HR": (5, 4), "BG": (5, 5),
    "MT": (6, 2), "GR": (6, 5), "CY": (6, 6),
}
