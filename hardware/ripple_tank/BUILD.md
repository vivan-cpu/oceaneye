# Ripple tank - a tabletop "satellite"

This shows judges *why* oil shows up dark on a radar image, with real water and real oil.
Benjamin Franklin noticed this in 1773: he poured a spoon of oil on a windy pond in London
and the ripples over a huge area went flat. Sentinel-1 uses exactly that effect.

| Real satellite | Our model |
|---|---|
| wind makes ripples | small fan blowing across the water |
| radar beam at an angle (~30-45°) | laser pointer at ~35° |
| antenna listening for the echo | LDR (light sensor) right next to the laser |
| oil flattens ripples -> weak echo -> dark | drop of oil -> ripples flatten -> LDR reading goes flat |
| low wind also looks dark (look-alike) | fan off -> also flat -> we show "NO WIND" |

## Parts (approx prices, Robu.in / Amazon / local electronics shop)

| Part | Qty | ₹ approx |
|---|---|---|
| ESP32 DevKit V1 (30 pin) | 1 | 400 |
| 0.96" OLED SSD1306 I2C | 1 | 200 |
| Laser module KY-008 (5 mW, red) | 1 | 60 |
| LDR + 10k resistor | 2 sets | 20 |
| 5 V mini fan or 130 motor + propeller | 1 | 80 |
| 2N2222 / BC547 transistor + 1N4007 diode + 1k resistor (fan switch) | 1 set | 20 |
| Buzzer, red + green LED, 220Ω resistors | - | 40 |
| Push button | 1 | 10 |
| Breadboard + jumper wires | 1 | 150 |
| Glass baking dish or clear plastic tray (~30×20 cm) | 1 | 200 |
| Black chart paper / shoe box (to block room light) | - | 50 |
| Sunflower oil (few drops), dish soap to clean | - | - |
| Stand for laser + sensor (cardboard, ice-cream sticks, hot glue) | - | 50 |
| **Total** | | **~₹1,300** |

That leaves money for printing a poster (₹300-500) and spare parts.

**Laser safety:** never look into it, point it only at the water, angle it so the reflection hits the black box wall not anyone's eyes.

## Wiring

```
LDR ---- 3.3V
 |
 +------ GPIO34  (ESP32)
 |
10k ---- GND

OLED: VCC->3.3V  GND->GND  SDA->GPIO21  SCL->GPIO22
Laser: S->GPIO33  -->GND  (middle pin to 3.3V if your module has 3 pins)
Fan:   GPIO25 -> 1k -> transistor base. emitter->GND. collector->fan(-). fan(+)->5V (VIN pin)
       diode across fan, stripe side to +5V
Buzzer: GPIO26 -> buzzer + , buzzer - -> GND
Red LED GPIO27, green LED GPIO14 (each through 220Ω to GND)
Fan button: GPIO13 -> button -> GND
Calibrate: the BOOT button already on the ESP32
```

## Setting it up

1. Fill the dish ~2 cm with water. Put it inside the box so room light doesn't reach the LDR.
2. Fan at one end, low, blowing *across* the water surface (not down into it).
3. Laser and LDR side by side on the other side, both pointing at the same spot in the middle,
   tilted about 35° from straight down. Wrap the LDR in a small black paper tube so it only sees that spot.
4. Arduino IDE: add ESP32 boards (Boards Manager -> "esp32 by Espressif"), install
   "Adafruit SSD1306" and "Adafruit GFX" libraries, select "ESP32 Dev Module", upload `ripple_tank.ino`.
5. On power-up it calibrates on clean water for ~8 seconds. Press BOOT any time to redo it.

## The demo (this is ~30 s of the video)

1. Fan on, clean water -> screen says **CLEAN**, green LED, roughness bar full.
2. Put 2-3 drops of oil upwind of the laser spot. Watch the ripples die -> **OIL!**, red LED, beep.
3. Clean the water (wash dish with soap), fan **off** -> **NO WIND**. Explain: the real satellite has the same problem,
   which is why our software warns when the sea is too calm.
4. Open Tools -> Serial Plotter to show the roughness line dropping below the "oil_line".

## If it doesn't work first time
- Roughness tiny even with fan on: move LDR so it's closer to where the laser hits, or make the fan stronger.
- Says OIL with clean water: room light is getting in, close the box. Or change `OIL_RATIO` (0.45) to 0.35.
- Oil doesn't calm ripples: you added too little, or the dish has soap left in it. Rinse well with plain water.
- Write down the numbers you get (clean vs oil vs no wind, 5 tries each). That table is your "testing" evidence.
