"""Builds docs/OceanEye_YCL2026_Problem_Statement.docx (needs python-docx). Run from the project folder."""
from docx import Document
from docx.shared import Pt, Cm, RGBColor

d = Document()
for s in d.sections:
    s.left_margin = s.right_margin = Cm(2.3)
    s.top_margin = s.bottom_margin = Cm(2)
d.styles["Normal"].font.name = "Calibri"
d.styles["Normal"].font.size = Pt(11)
for name, size in (("Heading 1", 15), ("Title", 24)):
    d.styles[name].font.name = "Calibri"
    d.styles[name].font.size = Pt(size)
    d.styles[name].font.color.rgb = RGBColor(0x0B, 0x1F, 0x4D)


def h(t):
    d.add_heading(t, 1)


def p(t):
    d.add_paragraph(t)


def b(t):
    d.add_paragraph(t, style="List Bullet")


d.add_heading("OceanEye: spotting oil spills at sea with free radar satellite images", 0)
p("Young Creators League 2026, Problem Statement Document\n"
  "Team OceanEye, The Galaxy School, Wadi, Rajkot (Application YCL/D2026/0537)\n"
  "Team: Rian Palan (team leader), Nivaan Alex (presenter), Vivan Sojitra (researcher)\n"
  "Mentor: Toral Dwivedi\n"
  "Website: https://vivan-cpu.github.io/oceaneye/   App: https://oceaneye-ycl.streamlit.app")

h("1. Selected theme")
p("Water Security. Clean coastal and ocean water is part of water security. Oil in the sea poisons the water that "
  "fish, coral, mangroves and coastal communities depend on.")

h("2. Problem identified")
p("Oil spills at sea are hard to find quickly. Finding a spill early decides how much damage it does, but the usual "
  "tools have gaps. Ordinary satellite photos need daylight and a clear sky. Aircraft and ships can only search a small "
  "area and are expensive to send. So a spill can spread for a long time before anyone knows where it is.")
p("Our question: can a student team find oil spills using only free satellite data, free software and a laptop?")

h("3. Background and research")
b("A real case from India. On 25 May 2025 the container ship MSC ELSA 3 sank about 14 nautical miles off Alappuzha, "
  "Kerala, with around 84 tonnes of diesel and 367 tonnes of fuel oil on board. It was monsoon season, so normal "
  "satellite photos were mostly cloud and the Coast Guard had to send aircraft to look for the slick.")
b("Not only accidents. A lot of oil at sea comes from ships illegally washing out their tanks, often at night and far "
  "from shore, where nobody sees it.")
b("Close to us. We live in Gujarat, which has India's longest coastline. The Gulf of Kutch, about 100 km from Rajkot, "
  "has some of the country's biggest oil terminals and tanker routes, right next to the Marine National Park with "
  "coral reefs and mangroves.")
b("How a radar satellite sees oil. Sentinel-1 is a radar satellite run by the European Space Agency, and its images are "
  "free through the Copernicus programme. It sends microwaves down at a slant and measures the echo. It makes its own "
  "signal, so it works at night and through clouds.")
b("Wind makes small ripples on the sea, a few centimetres long. They scatter the radar back to the satellite, so normal "
  "sea looks grey. Oil forms a thin film that flattens those ripples. Smooth water acts like a mirror and bounces the "
  "beam away, so almost no echo returns and the oil looks dark, usually a few decibels darker than the sea around it.")
b("An old observation. Benjamin Franklin noticed the same effect in 1773, when a spoonful of oil calmed the ripples "
  "over a large part of a windy pond in London.")
b("Look-alikes. Calm water, rain cells, shadows from land and algae can also look dark. A detector has to say how sure "
  "it is and warn when the sea is too calm to trust. Existing systems such as EMSA CleanSeaNet in Europe and INCOIS in "
  "India show that satellite oil detection works, but they are run by large agencies.")
b("What we built to learn about it. We wrote a Python program that downloads a Sentinel-1 image for any area and date, "
  "hides land, compares each patch of sea with the water around it, and scores how likely each dark patch is to be "
  "oil. We tested it on a real image of the Oil Rocks oil field in the Caspian Sea (17 October 2026) and on a "
  "simulated scene where we know the right answer.")

h("4. People affected")
b("Coastal fishing families. Oil can shut fishing for weeks. They lose income first and have the least to fall back on.")
b("People who live and work on the coast, such as fish sellers, boat owners and tourism workers.")
b("Marine life: fish, birds, coral and mangroves, which are slow to recover.")
b("Port officials, Coast Guard teams, NGOs and local authorities, who need to know where a spill is before they can respond.")
b("Everyone downstream, since seafood and clean beaches are shared resources.")

h("5. Why it matters")
p("The sooner a spill is located, the smaller the area that needs cleaning and the less oil reaches the shore. Illegal "
  "dumping is also much easier to stop when it can be seen and recorded. At the moment, only large agencies have "
  "regular satellite watching. A free tool that a fishing co-operative, a school or a small port office can use puts "
  "that capability in the hands of the people living next to the sea. It fits Water Security directly, because clean "
  "water and healthy seas are what coastal livelihoods depend on.")

h("6. Proposed solution")
p("OceanEye is a free website and app. You pick an area of sea and a date. It downloads that day's Sentinel-1 radar "
  "image, hides land, finds dark patches that could be oil, gives each one a score for how likely it is to be oil, and "
  "shows them on a map with their size in km2. The results can be exported for Google Earth or QGIS.")
b("It works through clouds and at night because it uses radar, not normal photos.")
b("Every result says why it was flagged (how dark, how long and thin, how sharp the edges are), so a person can judge "
  "it. A person always checks a result before anything is reported.")
b("It warns when the sea is too calm to trust, because calm water also looks dark.")
b("A second tool checks water from the ground. Using a phone camera, a photo or a phone's light sensor, a small AI "
  "model looks for oil sheen, and the result can be compared with what the satellite saw at the same place. Honest "
  "limits: it was trained on openly licensed photos (70 patches of oil), found about half of the oil on photos it had "
  "not seen, and has not been tested on real spills at sea.")
b("Everything runs on free services, so the cost to a user is zero.")

h("7. Technology and prototype")
p("Software prototype (working now): a Python program using Sentinel-1 data from Copernicus. It removes radar speckle "
  "with a Lee filter, hides land, compares each pixel with the sea around it (about 3 km), marks patches at least 3 dB "
  "darker, and scores each patch by contrast, shape and edge sharpness. It runs as a demo in the browser on our website "
  "and as a full Streamlit app.")
p("Functional prototype (working now): the website and app are the prototype. You can open them, pick an area and a date, "
  "and get real results from real Sentinel-1 images. A second part checks water from the ground. It uses the camera of a "
  "phone or laptop, an uploaded photo, or the light sensor of a phone through the free Phyphox app, and compares the spot "
  "with what the satellite saw within 5 km.")
b("Software: Python, free Sentinel-1 data from Copernicus, free hosting on GitHub Pages and Streamlit Cloud.")
b("Camera check: simple rules find dark and rainbow-coloured patches, and a small trained model scores each one. It runs in "
  "the browser, so photos are never uploaded.")
b("Phone light sensor: a phone sensor read through Phyphox can show a sudden change in reflected light, a sign of oil on "
  "the surface.")
p("We have not built a physical model, and we say so. Everything above runs today and can be tried by anyone with a link.")

d.save("docs/OceanEye_YCL2026_Problem_Statement.docx")
print("saved")
