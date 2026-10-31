// ripple_tank.ino
// Tabletop model of how Sentinel-1 sees oil.
//
// fan = wind, makes ripples on the water
// laser = the satellite's radar, shines at an angle onto the water
// LDR next to the laser = the satellite's antenna, measures what bounces BACK
//
// rippled water scatters some light back -> LDR reading flickers a lot
// add a drop of oil -> ripples get flattened -> light reflects away like a mirror -> reading goes flat
// fan off (no wind) -> also flat, so we say "no wind, can't tell" (same problem the real satellite has!)
//
// board: ESP32 dev module. libraries: Adafruit SSD1306 + Adafruit GFX (install from library manager)

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define LDR_PIN     34   // LDR + 10k divider, must be an ADC1 pin
#define FAN_PIN     25   // to transistor base (via 1k), transistor switches the fan
#define LASER_PIN   33
#define BUZZER_PIN  26
#define RED_LED     27
#define GREEN_LED   14
#define BTN_FAN     13   // button to GND: toggles the "wind"
#define BTN_CAL     0    // the BOOT button on the board: calibrate on clean water

Adafruit_SSD1306 oled(128, 64, &Wire, -1);

const int N = 400;          // samples per window
const int SAMPLE_US = 2500; // 400 Hz -> 1 second window
float cleanRough = 0;       // roughness of clean rippled water (from calibration)
float OIL_RATIO = 0.45;     // if roughness drops below 45% of clean -> oil. tune this!
bool fanOn = true;
unsigned long lastBtn = 0;

// read one second of data, return mean and roughness (std dev of the flicker)
void readWindow(float &mean, float &rough) {
  static int buf[N];
  long sum = 0;
  for (int i = 0; i < N; i++) {
    buf[i] = analogRead(LDR_PIN);
    sum += buf[i];
    delayMicroseconds(SAMPLE_US);
  }
  mean = (float)sum / N;
  float v = 0;
  for (int i = 0; i < N; i++) v += (buf[i] - mean) * (buf[i] - mean);
  rough = sqrt(v / N);
}

void showScreen(const char *status, float mean, float rough) {
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print("OilWatch tank  fan:");
  oled.print(fanOn ? "ON" : "OFF");
  oled.setCursor(0, 12);
  oled.print("light "); oled.print((int)mean);
  oled.print("  rough "); oled.print(rough, 1);

  // roughness bar, full bar = clean water
  int w = cleanRough > 0 ? constrain((int)(120 * rough / cleanRough), 0, 120) : 0;
  oled.drawRect(0, 24, 122, 10, SSD1306_WHITE);
  oled.fillRect(1, 25, w, 8, SSD1306_WHITE);

  oled.setTextSize(2);
  oled.setCursor(0, 42);
  oled.print(status);
  oled.display();
}

void calibrate() {
  oled.clearDisplay(); oled.setTextSize(1); oled.setCursor(0, 20);
  oled.print("Calibrating...\nclean water, fan on");
  oled.display();
  digitalWrite(FAN_PIN, HIGH); fanOn = true;
  delay(3000);  // let ripples build up
  float m, r, total = 0;
  for (int i = 0; i < 5; i++) { readWindow(m, r); total += r; }
  cleanRough = total / 5;
  Serial.print("calibrated, clean roughness = "); Serial.println(cleanRough);
}

void setup() {
  Serial.begin(115200);
  pinMode(FAN_PIN, OUTPUT); pinMode(LASER_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT); pinMode(RED_LED, OUTPUT); pinMode(GREEN_LED, OUTPUT);
  pinMode(BTN_FAN, INPUT_PULLUP); pinMode(BTN_CAL, INPUT_PULLUP);
  analogReadResolution(12);

  Wire.begin(21, 22);
  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) Serial.println("OLED not found, carrying on without it");

  digitalWrite(LASER_PIN, HIGH);
  calibrate();
}

void loop() {
  // buttons
  if (millis() - lastBtn > 400) {
    if (digitalRead(BTN_FAN) == LOW) { fanOn = !fanOn; digitalWrite(FAN_PIN, fanOn); lastBtn = millis(); }
    if (digitalRead(BTN_CAL) == LOW) { calibrate(); lastBtn = millis(); }
  }

  float mean, rough;
  readWindow(mean, rough);
  float ratio = cleanRough > 0 ? rough / cleanRough : 1;

  const char *status;
  bool alarm = false;
  if (!fanOn) {
    status = "NO WIND";        // calm water looks just like oil -> don't guess
  } else if (ratio < OIL_RATIO) {
    status = "OIL!";
    alarm = true;
  } else {
    status = "CLEAN";
  }

  digitalWrite(RED_LED, alarm);
  digitalWrite(GREEN_LED, fanOn && !alarm);
  if (alarm) tone(BUZZER_PIN, 2000, 150); else noTone(BUZZER_PIN);
  showScreen(status, mean, rough);

  // open Tools > Serial Plotter to see the graph live (good for the video)
  Serial.print("roughness:"); Serial.print(rough);
  Serial.print(",clean:"); Serial.print(cleanRough);
  Serial.print(",oil_line:"); Serial.println(cleanRough * OIL_RATIO);
}
