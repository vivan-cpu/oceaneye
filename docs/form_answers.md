# YCL 2026 form - draft answers (Application YCL/D2026/0537)

Draft for the empty "Prototype & Project Information" part of the form.
Change the wording so it sounds like us before pasting. Anything in [brackets] we still have to fill in.

---

**Project Title**

OceanEye - spotting oil spills at sea with free radar satellite images

**Plaksha Research Theme**

Water Security

**What problem are you addressing?**

Oil spills in the sea kill fish, birds, coral and mangroves, and stop fishing for weeks. Coastal fishing
families are hit first. The problem is that spills are hard to find quickly. In May 2025 the ship
MSC ELSA 3 sank off Kerala during the monsoon with diesel and fuel oil on board. Normal satellite
photos were covered in cloud, so the Coast Guard had to send aircraft to search. Also, a lot of oil
at sea comes from ships illegally washing their tanks at night, far from the coast, where nobody sees it.

**Why did you choose this problem?**

We live in Gujarat, which has India's longest coastline. The Gulf of Kutch, about 100 km from Rajkot, has
some of the country's biggest oil terminals and tanker routes, right next to the Marine National Park
with coral reefs and mangroves. When we read about the Kerala ship sinking in 2025, we wondered
if a spill like that could be found even through monsoon clouds, using only free data and a laptop.
[add your own reason here - something one of us saw or read]

**Project Overview**

OceanEye is a website/app where you pick an area of sea and a date. It downloads that day's free
Sentinel-1 radar image from the European Space Agency (Copernicus), finds dark patches that could be
oil, gives each patch a score for how likely it is to really be oil, and shows them on a map with their
size in km². We also built a tabletop ripple tank model that shows the same science: a fan makes
waves, a laser acts as the radar, and a light sensor acts as the satellite's antenna.
Website: https://vivan-cpu.github.io/oceaneye/ [add the Streamlit app link once it is live]

**What solution are you proposing?**

A free, simple tool that NGOs, fishing co-operatives, port officials or schools can use to keep regular
watch on their own coast and to check reports of spills. It works through clouds and at night,
because it uses radar instead of normal photos. Every result says why it was flagged (how dark, how
long and thin, how sharp the edges are), and a person checks it before anything is reported.

**Describe the technology or scientific principles being deployed to solve it.**

Sentinel-1 is a radar satellite. It sends microwaves down at a slant and measures the echo. Wind makes
small ripples on the sea, a few cm long, about the same size as the radar wavelength, so they scatter the
signal back and the sea looks grey (Bragg scattering). Oil makes a thin film that flattens these ripples.
Smooth water reflects the beam away like a mirror, so oil looks dark, usually 3-10 dB darker than the sea
around it. Our Python program removes radar "speckle" with a Lee filter, hides land, compares each pixel
with the sea around it (about 3 km), marks patches at least 3 dB darker, and then scores each patch by
contrast, shape and edge sharpness. The ripple tank uses an ESP32, a fan, a laser and an LDR to show the
same effect.

**Innovation Factor - What makes your solution unique?**

Systems like this already exist (EMSA CleanSeaNet in Europe, INCOIS in India), but they are run by big
agencies. Ours uses only free satellite data and free hosting and runs in a browser, so anyone can check
their own coast. We used clear rules instead of a black-box AI, so we can explain every decision, and
it warns when the sea is too calm to trust (calm water also looks dark). The ripple tank lets people see
and touch the physics that the satellite uses.

---

## Other things still empty on the form

- Project & team pictures: [photos of the ripple tank, the app on a laptop, the team]
- Video submission link: [after we make the 3-minute video - see video_plan.md]
- School nomination: nominator name, designation, email, phone + nomination letter [ask school]
- School LinkedIn / Instagram links (optional)
- Check: the form says Grade 12 but passing year 2029 for all three of us - one of these is wrong.
