# How OilWatch works (and what to say when the panel asks)

## The problem

- Oil at sea kills fish, birds, coral and mangroves, and ruins fishing for months. Fishing families
  lose income first.
- India: in May 2025 the container ship **MSC ELSA 3** sank ~14 nautical miles off Alappuzha, Kerala,
  carrying about 84 t of diesel and 367 t of fuel oil. The Coast Guard used aircraft to find the slick.
  A ~9 km slick was seen by satellite on 1 June.
- Black Sea, Dec 2024: two old tankers broke in a storm in the Kerch Strait, ~4,000 t of fuel oil.
  Bad weather made aircraft surveys hard; scientists tracked it with Sentinel-1 for months.
- Most pollution isn't big accidents: it's ships illegally cleaning tanks at night, far from shore,
  where nobody is watching.

**Who is affected:** coastal fishing communities, tourism, the Coast Guard (has to find spills fast),
port authorities, marine life.

**Why it fits Water Security:** clean seas = safe seafood, livelihoods, and coastal water quality.

## The science (simple version)

1. Sentinel-1 is a radar satellite (ESA, C-band, ~5.6 cm wavelength). It sends microwave pulses
   down at a slant and listens for the echo.
2. Wind makes small ripples (a few cm, same size as the radar wavelength). Ripples scatter energy
   back to the satellite = **grey sea** in the image. This is called *Bragg scattering*.
3. Oil forms a thin film that damps those small ripples. Smooth water acts like a mirror and reflects
   the beam away = **very little echo = dark patch**. Typically 3-10 dB darker than the sea around it.
4. Radar makes its own "light", so it works at night and through clouds.

We use the **VV** band (vertical send, vertical receive), which shows the sea contrast best, and
**sigma0** (the standard brightness unit for radar).

## Our method, step by step

| Step | What | Why |
|---|---|---|
| 1 | Download VV image for the area/date | free from Copernicus |
| 2 | Mask land (+1 km buffer) | coasts and mudflats cause false alarms |
| 3 | Lee speckle filter (7×7) | radar images are grainy; this smooths sea but keeps edges |
| 4 | Local background = average sea in a ~3 km window | wind changes across the image, so one fixed threshold doesn't work |
| 5 | Mark pixels ≥3 dB darker than background AND below -18 dB | "dark spot" detection |
| 6 | Clean up mask, drop blobs < 0.05 km² | remove noise |
| 7 | Measure each blob: contrast, elongation, edge sharpness, area | features |
| 8 | Points system → likely / possible / look-alike | explainable decision |

**Points rules**

- contrast ≥6 dB: +2, ≥4 dB: +1
- elongation (length ÷ width) ≥3: +2, ≥1.8: +1 (ship discharges are long trails)
- sharp edges: +1, fuzzy edges: -1 (low-wind areas fade out gradually)
- covers >25% of the sea in the image: -3 (that's weather, not a spill)
- whole sea darker than -22 dB (very low wind): -1 and a warning

Score ≥4 = likely oil, 2-3 = possible, below 2 = probably look-alike.

## How we tested it

1. **Simulated scene** (`make_test_scene.py`): fake radar image with realistic speckle, an oil trail
   behind a ship, a calm-wind patch and a rain cell. We know where the oil really is.
   Result: found the oil trail (87% overlap with the true shape, 95% of oil pixels found),
   ignored the calm patch, called the rain cell a look-alike.
2. **Real spills**: Kerch Strait (Dec 2024), MSC ELSA 3 (May-Jun 2025), Wakashio (Aug 2020).
   _(fill in: which dates you ran, what it found, screenshots)_
3. **Ripple tank**: clean vs oil vs no-wind, 5 tries each. _(fill in your table)_
4. **Talking to people**: _(fill in - see video plan for ideas)_

## Questions the panel might ask

**Why not just use normal satellite photos?** Clouds and night. Also thin oil is hard to see in normal
colour. We do show a Sentinel-2 photo as a second check when it's clear.

**What fools your system?** Calm wind areas, rain cells, natural algae/fish oil films, ship wakes,
shallow areas near coast. That's why we score shape and contrast and warn when wind is low.

**How often can you check?** Sentinel-1 revisits most places every ~6-12 days (now better with
Sentinel-1C launched in Dec 2024). Not real-time, but good for regular patrols and confirming reports.

**Why rules and not AI/ML?** We wanted to understand and explain every decision. With a labelled
dataset (e.g. the Krestenitis et al. 2019 Sentinel-1 oil spill dataset) a neural network could do better.
That's our next step.

**Does anyone already do this?** Yes - EMSA's CleanSeaNet in Europe, and INCOIS in India. Ours shows
that students can do a basic version with free data and a laptop, and it could help NGOs, fishing
co-operatives or schools keep watch on their own coast.

**How much did it cost?** Data and software are free. Ripple tank ~₹1,300.

**What's the minimum spill you can see?** At 40 m pixels and 0.05 km² minimum, roughly a patch
200 m × 250 m. At 20 m pixels you can go smaller but it uses more quota.

## Sources

- YCL 2026 guide: https://ycl.atplaksha.in/assets/docs/YCL-2026-Registration-and-School-Nomination-Guide.pdf
- MSC ELSA 3 incident sheet (Cedre): https://cedre.fr/en/resources/incident-information-sheets/msc-elsa-3
- 2025 Kerala oil spill: https://en.wikipedia.org/wiki/2025_Kerala_oil_spill
- Kerch Strait Sentinel-1 analysis: https://www.earthdoc.org/content/papers/10.3997/2214-4609.2025510062
- Kerch spill modelling + SAR: https://meetingorganizer.copernicus.org/EGU25/EGU25-6129.html
- Sentinel-1 on Copernicus: https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html
- Free quota (10,000 PU/month): https://dataspace.copernicus.eu/node/2602
- Benjamin Franklin's oil on water (1774, Phil. Trans. Royal Society) - search "Franklin Clapham pond oil"
- Brekke & Solberg (2005), "Oil spill detection by satellite remote sensing", Remote Sensing of Environment
- Krestenitis et al. (2019), "Oil Spill Identification from Satellite Images Using Deep Neural Networks", Remote Sensing
