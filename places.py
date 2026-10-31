# places we tested / want to show. bbox = (west, south, east, north) in degrees
# dates are where real spills were reported in news / papers (links in docs/how_it_works.md)

PLACES = {
    "Kerch Strait, Black Sea - tanker spill (Dec 2024)": {
        "bbox": (36.3, 44.75, 37.3, 45.35),
        "from": "2024-12-17", "to": "2024-12-31",
        "note": "Two tankers (Volgoneft-212/239) broke apart on 15 Dec 2024, ~4000 t of fuel oil. "
                "Slicks were seen on Sentinel-1 on 18, 19, 29, 30, 31 Dec.",
    },
    "Off Alappuzha, Kerala - MSC ELSA 3 sinking (May-Jun 2025)": {
        "bbox": (75.8, 8.95, 76.5, 9.6),
        "from": "2025-05-25", "to": "2025-06-12",
        "note": "Container ship sank 25 May 2025 with diesel + fuel oil on board. "
                "A ~9 km slick was seen on satellite on 1 June. Monsoon winds make it hard.",
    },
    "Mauritius - MV Wakashio (Aug 2020)": {
        "bbox": (57.6, -20.55, 57.9, -20.3),
        "from": "2020-08-05", "to": "2020-08-20",
        "note": "Bulk carrier ran aground on the reef, started leaking ~6 Aug 2020.",
    },
    "Oil Rocks, Caspian Sea - old oil platforms": {
        "bbox": (50.5, 40.0, 51.2, 40.45),
        "from": "2026-09-01", "to": "2026-10-30",
        "note": "Very old offshore oil field, small leaks show up on radar very often. Good for testing.",
    },
    "Mumbai High offshore field (India)": {
        "bbox": (71.0, 19.15, 71.8, 19.75),
        "from": "2026-10-01", "to": "2026-10-30",
        "note": "India's biggest offshore oil field. Use this for routine checking.",
    },
    "Gulf of Kutch - oil terminals (India)": {
        "bbox": (69.4, 22.45, 70.3, 22.9),
        "from": "2026-10-01", "to": "2026-10-30",
        "note": "Lots of tankers and offshore mooring buoys. Careful: tidal mudflats can look dark too.",
    },
    "Custom area": {
        "bbox": (72.0, 18.5, 72.6, 19.0),
        "from": "2026-10-01", "to": "2026-10-30",
        "note": "Draw your own box on the map.",
    },
}
