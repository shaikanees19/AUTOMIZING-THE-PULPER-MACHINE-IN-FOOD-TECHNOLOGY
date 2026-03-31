#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

const char* ssid = "realme";
const char* password = "password";

WebServer server(80);
LiquidCrystal_I2C lcd(0x27, 16, 2);

String cls = "";
String rpm = "";

// Non-blocking LCD clear timer
unsigned long lcdClearTime = 0;
bool lcdActive = false;

void handleData() {
  Serial.println(">>> Request received!");  // Debug: confirms Flask reached ESP32

  if (server.hasArg("class") && server.hasArg("rpm")) {

    cls = server.arg("class");
    rpm = server.arg("rpm");

    Serial.print("Class: "); Serial.println(cls);
    Serial.print("RPM: ");   Serial.println(rpm);

    // Update LCD immediately
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(cls);
    lcd.setCursor(0, 1);
    lcd.print("RPM: ");
    lcd.print(rpm);

    // Schedule LCD clear after 6 seconds (non-blocking)
    lcdClearTime = millis() + 6000;
    lcdActive = true;

    // Respond to Flask RIGHT AWAY (don't make it wait)
    server.send(200, "text/plain", "OK");

  } else {
    Serial.println("Missing args!");
    server.send(400, "text/plain", "Missing class or rpm");
  }
}

void handleRoot() {
  server.send(200, "text/plain", "ESP32 is online");
}

void setup() {
  Serial.begin(115200);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Connecting WiFi");

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
  Serial.println(WiFi.localIP());

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("WiFi Connected");
  lcd.setCursor(0, 1);
  lcd.print(WiFi.localIP());

  server.on("/data", handleData);
  server.on("/", handleRoot);   // test route: visit http://IP/ in browser
  server.begin();

  Serial.println("Server started");
}

void loop() {
  server.handleClient();

  // Non-blocking LCD clear after 6 seconds
  if (lcdActive && millis() >= lcdClearTime) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Waiting...");
    lcdActive = false;
  }
}