"""
Curated knowledge base used by the rule-based report engine.

It encodes stable, well-documented facts about the EU and Chinese markets
(institutions, regulation, trade agreements, geography, language) so reports
can be generated without any paid AI service. Product-specific measures change
over time, so every regulatory note links to an official place to verify it.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Countries: capital coordinates, language family, trade-bloc membership
# --------------------------------------------------------------------------- #
COUNTRIES: dict[str, dict] = {
    # EU-27
    "AT": {"name": "Austria", "lat": 48.21, "lon": 16.37, "lang": "Germanic", "bloc": "EU"},
    "BE": {"name": "Belgium", "lat": 50.85, "lon": 4.35, "lang": "Germanic/Romance", "bloc": "EU"},
    "BG": {"name": "Bulgaria", "lat": 42.70, "lon": 23.32, "lang": "Slavic", "bloc": "EU"},
    "CY": {"name": "Cyprus", "lat": 35.17, "lon": 33.36, "lang": "Greek", "bloc": "EU"},
    "CZ": {"name": "Czechia", "lat": 50.08, "lon": 14.44, "lang": "Slavic", "bloc": "EU"},
    "DE": {"name": "Germany", "lat": 52.52, "lon": 13.40, "lang": "Germanic", "bloc": "EU"},
    "DK": {"name": "Denmark", "lat": 55.68, "lon": 12.57, "lang": "Germanic", "bloc": "EU"},
    "EE": {"name": "Estonia", "lat": 59.44, "lon": 24.75, "lang": "Finnic", "bloc": "EU"},
    "ES": {"name": "Spain", "lat": 40.42, "lon": -3.70, "lang": "Romance", "bloc": "EU"},
    "FI": {"name": "Finland", "lat": 60.17, "lon": 24.94, "lang": "Finnic", "bloc": "EU"},
    "FR": {"name": "France", "lat": 48.86, "lon": 2.35, "lang": "Romance", "bloc": "EU"},
    "GR": {"name": "Greece", "lat": 37.98, "lon": 23.73, "lang": "Greek", "bloc": "EU"},
    "HR": {"name": "Croatia", "lat": 45.81, "lon": 15.98, "lang": "Slavic", "bloc": "EU"},
    "HU": {"name": "Hungary", "lat": 47.50, "lon": 19.04, "lang": "Finnic", "bloc": "EU"},
    "IE": {"name": "Ireland", "lat": 53.35, "lon": -6.26, "lang": "English", "bloc": "EU"},
    "IT": {"name": "Italy", "lat": 41.90, "lon": 12.50, "lang": "Romance", "bloc": "EU"},
    "LT": {"name": "Lithuania", "lat": 54.69, "lon": 25.28, "lang": "Baltic", "bloc": "EU"},
    "LU": {"name": "Luxembourg", "lat": 49.61, "lon": 6.13, "lang": "Germanic/Romance", "bloc": "EU"},
    "LV": {"name": "Latvia", "lat": 56.95, "lon": 24.11, "lang": "Baltic", "bloc": "EU"},
    "MT": {"name": "Malta", "lat": 35.90, "lon": 14.51, "lang": "English", "bloc": "EU"},
    "NL": {"name": "Netherlands", "lat": 52.37, "lon": 4.90, "lang": "Germanic", "bloc": "EU"},
    "PL": {"name": "Poland", "lat": 52.23, "lon": 21.01, "lang": "Slavic", "bloc": "EU"},
    "PT": {"name": "Portugal", "lat": 38.72, "lon": -9.14, "lang": "Romance", "bloc": "EU"},
    "RO": {"name": "Romania", "lat": 44.43, "lon": 26.10, "lang": "Romance", "bloc": "EU"},
    "SE": {"name": "Sweden", "lat": 59.33, "lon": 18.07, "lang": "Germanic", "bloc": "EU"},
    "SI": {"name": "Slovenia", "lat": 46.06, "lon": 14.51, "lang": "Slavic", "bloc": "EU"},
    "SK": {"name": "Slovakia", "lat": 48.15, "lon": 17.11, "lang": "Slavic", "bloc": "EU"},
    # Aggregate / other
    "EU": {"name": "European Union", "lat": 50.85, "lon": 4.35, "lang": "Mixed", "bloc": "EU"},
    "CN": {"name": "China", "lat": 39.90, "lon": 116.40, "lang": "Sinitic", "bloc": "RCEP"},
    "US": {"name": "United States", "lat": 38.91, "lon": -77.04, "lang": "English", "bloc": "USMCA"},
    "GB": {"name": "United Kingdom", "lat": 51.51, "lon": -0.13, "lang": "English", "bloc": None},
    "CH": {"name": "Switzerland", "lat": 46.95, "lon": 7.45, "lang": "Germanic/Romance", "bloc": "EFTA"},
    "NO": {"name": "Norway", "lat": 59.91, "lon": 10.75, "lang": "Germanic", "bloc": "EFTA"},
    "JP": {"name": "Japan", "lat": 35.68, "lon": 139.69, "lang": "Japonic", "bloc": "RCEP"},
    "KR": {"name": "South Korea", "lat": 37.57, "lon": 126.98, "lang": "Koreanic", "bloc": "RCEP"},
    "TW": {"name": "Taiwan", "lat": 25.03, "lon": 121.57, "lang": "Sinitic", "bloc": None},
    "VN": {"name": "Vietnam", "lat": 21.03, "lon": 105.85, "lang": "Vietic", "bloc": "RCEP"},
    "IN": {"name": "India", "lat": 28.61, "lon": 77.21, "lang": "Indo-Aryan", "bloc": None},
    "TR": {"name": "Türkiye", "lat": 39.93, "lon": 32.86, "lang": "Turkic", "bloc": "EU Customs Union"},
    "SG": {"name": "Singapore", "lat": 1.35, "lon": 103.82, "lang": "English/Sinitic", "bloc": "RCEP"},
    "CA": {"name": "Canada", "lat": 45.42, "lon": -75.70, "lang": "English", "bloc": "USMCA"},
    "AU": {"name": "Australia", "lat": -35.28, "lon": 149.13, "lang": "English", "bloc": "RCEP"},
    "BR": {"name": "Brazil", "lat": -15.79, "lon": -47.88, "lang": "Romance", "bloc": "Mercosur"},
    "MX": {"name": "Mexico", "lat": 19.43, "lon": -99.13, "lang": "Romance", "bloc": "USMCA"},
}

EU27 = [c for c, v in COUNTRIES.items() if v["bloc"] == "EU" and c != "EU"]

# Trade agreements in force that cut tariffs between a home country and the target.
# (Kept to well-established agreements; verify details on the sources listed below.)
EU_FTA_PARTNERS = {
    "CH": "EU-Switzerland agreements", "NO": "European Economic Area",
    "GB": "EU-UK Trade and Cooperation Agreement", "JP": "EU-Japan EPA",
    "KR": "EU-Korea FTA", "VN": "EU-Vietnam FTA", "SG": "EU-Singapore FTA",
    "CA": "CETA (EU-Canada)", "MX": "EU-Mexico Global Agreement",
    "TR": "EU-Türkiye Customs Union (industrial goods)",
}
CN_FTA_PARTNERS = {
    "JP": "RCEP", "KR": "China-Korea FTA and RCEP", "VN": "China-ASEAN FTA and RCEP",
    "SG": "China-Singapore FTA and RCEP", "AU": "China-Australia FTA and RCEP",
    "CH": "China-Switzerland FTA", "NZ": "China-New Zealand FTA and RCEP",
}

# --------------------------------------------------------------------------- #
# Product sectors (by HS chapter) and sector-specific regulation
# --------------------------------------------------------------------------- #
SECTORS = [
    # (first chapter, last chapter, sector key)
    (1, 24, "agrifood"),
    (25, 27, "minerals_energy"),
    (28, 29, "chemicals"),
    (30, 30, "pharma"),
    (31, 32, "chemicals"),
    (33, 33, "cosmetics"),
    (34, 40, "chemicals"),
    (41, 43, "consumer"),
    (44, 49, "materials"),
    (50, 67, "textiles"),
    (68, 71, "materials"),
    (72, 83, "metals"),
    (84, 84, "machinery"),
    (85, 85, "electronics"),
    (86, 89, "vehicles"),
    (90, 92, "medtech"),
    (93, 93, "restricted"),
    (94, 96, "consumer"),
    (97, 99, "other"),
]

SECTOR_LABELS = {
    "agrifood": "Agri-food & beverages", "minerals_energy": "Minerals & energy",
    "chemicals": "Chemicals & plastics", "pharma": "Pharmaceuticals",
    "cosmetics": "Cosmetics & personal care", "consumer": "Consumer goods",
    "materials": "Materials (wood, paper, glass, ceramics)", "textiles": "Textiles & apparel",
    "metals": "Base metals", "machinery": "Machinery & equipment",
    "electronics": "Electrical & electronic equipment", "vehicles": "Vehicles & transport equipment",
    "medtech": "Medical & precision instruments", "restricted": "Arms (restricted)",
    "other": "Other",
}


def sector_for(hs_code: str) -> str:
    chapter = int(hs_code[:2])
    for lo, hi, key in SECTORS:
        if lo <= chapter <= hi:
            return key
    return "other"


EU_REGULATION = {
    "_all": [
        "General Product Safety Regulation (EU) 2023/988 (GPSR), applies to consumer products since Dec 2024",
        "Union Customs Code: an EU-established importer/representative and EORI number are required",
        "Forced Labour Regulation (EU) 2024/3015: ban on products made with forced labour, applies from Dec 2027",
    ],
    "agrifood": [
        "Food hygiene and official controls (Reg. 852/2004, 2017/625); border checks for animal and plant products",
        "Food Information to Consumers Reg. 1169/2011 (labelling in the local language)",
        "EU Deforestation Regulation (EUDR) for cocoa, coffee, soy, palm oil, cattle, wood and rubber",
    ],
    "chemicals": ["REACH registration (Reg. 1907/2006) and CLP classification and labelling (Reg. 1272/2008)"],
    "pharma": [
        "Marketing authorisation via EMA (centralised) or national agencies; GMP certification",
        "Falsified Medicines Directive: serialisation and safety features",
    ],
    "cosmetics": [
        "Cosmetics Regulation (EC) 1223/2009: Responsible Person in the EU, CPNP notification, safety report",
        "Animal testing ban on cosmetics and ingredients",
    ],
    "textiles": [
        "Textile Labelling Regulation 1007/2011; REACH restrictions on substances",
        "Ecodesign for Sustainable Products Regulation (ESPR) and the coming Digital Product Passport; ban on destroying unsold apparel",
    ],
    "metals": [
        "Carbon Border Adjustment Mechanism (CBAM): iron & steel and aluminium imports need an authorised declarant and CBAM certificates (definitive phase from 2026)",
        "EU steel safeguard measures and many anti-dumping duties on Chinese steel products",
    ],
    "minerals_energy": ["CBAM covers cement, fertilisers, electricity and hydrogen"],
    "machinery": [
        "CE marking: Machinery Regulation (EU) 2023/1230 (replaces the Machinery Directive from Jan 2027)",
        "EMC and Low Voltage Directives where electrical; Ecodesign energy-efficiency rules",
    ],
    "electronics": [
        "CE marking: Low Voltage, EMC and Radio Equipment Directives",
        "RoHS (hazardous substances) and WEEE (take-back and recycling, producer registration per member state)",
        "EU Battery Regulation (EU) 2023/1542 for products with batteries: carbon footprint, due diligence, battery passport phased in",
    ],
    "vehicles": [
        "EU type-approval (Reg. 2018/858 for cars; Reg. 168/2013 for L-category vehicles such as speed e-bikes)",
        "EN 15194 standard and CE marking (Machinery) for pedal-assist e-bikes",
        "EU Battery Regulation (EU) 2023/1542 for traction and light-means-of-transport batteries",
    ],
    "medtech": ["Medical Device Regulation (EU) 2017/745 (MDR): notified-body conformity assessment, EUDAMED registration"],
    "consumer": ["Toy Safety rules where relevant; REACH restrictions; GPSR"],
    "materials": ["Construction Products Regulation for building materials; EUTR/EUDR for wood"],
    "restricted": ["Dual-use and arms export/import licensing"],
    "other": [],
}

CN_REGULATION = {
    "_all": [
        "Customs registration of the consignee; Chinese-language labelling for retail goods",
        "Foreign Investment Law (2020) and the Negative List: most sectors open to wholly foreign-owned enterprises (WFOE)",
        "Data Security Law and Personal Information Protection Law (PIPL) for any customer data collected",
        "Cross-border e-commerce (e.g. Tmall Global, JD Worldwide) allows testing demand under a lighter regime for many consumer goods",
    ],
    "agrifood": [
        "GACC registration of overseas food manufacturers (Decree 248) and Chinese labelling (Decree 249)",
        "Market-access protocols needed for many meat, dairy and fresh products",
    ],
    "chemicals": ["New chemical substance registration (MEE Order 12) and hazardous-chemicals rules"],
    "pharma": [
        "NMPA drug registration with local clinical data requirements; a Marketing Authorisation Holder or agent in China",
        "Volume-based procurement (VBP) puts strong price pressure on off-patent drugs",
    ],
    "cosmetics": [
        "NMPA registration (special-use) or filing (general cosmetics) under the CSAR rules (2021)",
        "Animal testing waived for general cosmetics with a GMP certificate since 2021",
    ],
    "textiles": ["GB 18401 mandatory safety standard and Chinese labelling (GB 5296.4)"],
    "metals": ["Export-control and anti-dumping exposure; strong domestic overcapacity in steel and aluminium"],
    "minerals_energy": ["State-dominated sector; import licensing for some energy products"],
    "machinery": ["CCC certification for listed products; GB standards; special-equipment licences"],
    "electronics": [
        "China Compulsory Certification (CCC) for listed electrical products; SRRC approval for radio devices",
        "China RoHS labelling rules",
    ],
    "vehicles": [
        "CCC certification and MIIT product catalogue listing for vehicles; CCC for electric bicycles (GB 17761 standard)",
        "Domestic producers dominate EVs and e-bikes; intense price competition",
    ],
    "medtech": ["NMPA registration of Class II/III devices, usually with local testing"],
    "consumer": ["CCC for listed products (e.g. toys); GB standards"],
    "materials": ["GB standards and CCC where listed"],
    "restricted": ["Prohibited or licensed"],
    "other": [],
}

# Product-specific trade-defence notes for the EU-China corridor (high-salience cases)
TRADE_DEFENCE_NOTES = {
    "871160": "EU anti-dumping and anti-subsidy duties on e-bikes from China have applied since 2019 (check the current rate and any expiry review).",
    "870380": "EU countervailing duties on battery-electric cars from China since Oct 2024 (company-specific rates, on top of the 10% EU car tariff).",
    "854143": "No EU duties on Chinese solar modules today (measures expired in 2018), but EU NZIA resilience criteria and forced-labour rules matter.",
    "850760": "Chinese firms dominate the battery value chain; China's export controls on graphite (2023) and battery technology affect supply chains.",
    "220830": "China imposed anti-dumping measures on EU brandy (2024-2025), with price undertakings for many producers.",
    "220421": "EU wine faces strong competition from Australia in China since China lifted its duties on Australian wine in 2024.",
}

VERIFY_SOURCES = {
    "EU": [
        ("Access2Markets (EU tariffs, rules of origin, requirements)", "https://trade.ec.europa.eu/access-to-markets/"),
        ("EU TARIC tariff database", "https://ec.europa.eu/taxation_customs/dds2/taric/"),
        ("EU trade defence cases", "https://tron.trade.ec.europa.eu/investigations/ongoing"),
    ],
    "CN": [
        ("China Customs tariff and regulations (GACC)", "http://english.customs.gov.cn/"),
        ("MOFCOM trade remedy notices", "http://english.mofcom.gov.cn/"),
        ("EU Access2Markets: China export requirements", "https://trade.ec.europa.eu/access-to-markets/"),
        ("EU SME Centre (China market guides)", "https://www.eusmecentre.org.cn/"),
    ],
}

# --------------------------------------------------------------------------- #
# Market-level PESTEL baselines (stable structural facts)
# --------------------------------------------------------------------------- #
PESTEL_BASE = {
    "EU": {
        "Political": "Stable democracies with a single trade policy run by the European Commission. EU-China relations follow a 'de-risking' agenda: more trade-defence cases, the Foreign Subsidies Regulation and screening of Chinese investment.",
        "Economic": "Single market of ~450 million consumers and one of the world's largest import markets; high purchasing power, though growth is modest and varies strongly between member states.",
        "Social": "Diverse languages and consumer cultures across 27 countries; strong demand for sustainability, quality and data privacy; ageing population.",
        "Technological": "Advanced digital infrastructure and e-commerce; strict standards (CE, EN norms) make quality and certification a competitive factor.",
        "Environmental": "European Green Deal: CBAM, Ecodesign/ESPR, Battery Regulation, deforestation and packaging rules raise compliance costs but reward low-carbon products.",
        "Legal": "Harmonised product law across the EU (one CE mark for 27 markets), GDPR for customer data, strong IP protection and contract enforcement.",
    },
    "CN": {
        "Political": "One-party state with active industrial policy (Made in China 2025, dual circulation). Geopolitical tension with the EU and US; retaliation risk in trade disputes (e.g. EU brandy, pork, dairy probes).",
        "Economic": "World's second-largest economy and a huge consumer market, but slower growth, weak consumer confidence and strong price competition from domestic champions.",
        "Social": "Digitally native consumers; 'guochao' preference for domestic brands among younger buyers; foreign brands win on safety, heritage and premium positioning.",
        "Technological": "World-leading e-commerce and super-apps (Tmall, JD, Douyin, WeChat); fast product cycles; strong domestic manufacturing capability.",
        "Environmental": "Dual-carbon goals (peak 2030, neutrality 2060) drive demand for clean-tech; growing ESG disclosure requirements.",
        "Legal": "Foreign Investment Law (2020) improved access; still complex licensing, local standards (GB/CCC), data-localisation rules and uneven IP enforcement.",
    },
}

PESTEL_SECTOR_HINTS = {
    "vehicles": {"Environmental": "Electrification targets support EV and e-mobility demand.",
                 "Political": "Vehicles are a flashpoint in EU-China trade policy."},
    "electronics": {"Technological": "Fast innovation cycles; certification and cybersecurity rules tighten."},
    "pharma": {"Legal": "Long, data-heavy approval processes; pricing set or negotiated by public payers."},
    "cosmetics": {"Social": "Brand image, influencers and channel strategy drive sales."},
    "agrifood": {"Legal": "Sanitary and phytosanitary rules can block market access entirely."},
    "metals": {"Environmental": "CBAM puts a carbon price on embedded emissions."},
}
