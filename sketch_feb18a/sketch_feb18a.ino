// SmartSchool RFID Scanner — ESP32 + PN532 (I2C)
// Замінює стару версію з MFRC522 (SPI)
//
// ЗМІНИ GPIO ПОРІВНЯНО ЗІ СТАРОЮ ВЕРСІЄЮ:
//   LED_GREEN: GPIO21 → GPIO25  (GPIO21 тепер I2C SDA)
//   RST_PIN:   GPIO22 → не потрібен (GPIO22 тепер I2C SCL)
//   PN532 SDA: GPIO21  (фіксований)
//   PN532 SCL: GPIO22  (фіксований)
//   PN532 IRQ: GPIO15  (опціонально, рекомендовано)

#include <Wire.h>
#include <Adafruit_PN532.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include <HTTPClient.h>
#include <ESPmDNS.h>
#include <vector>
#include "smart_school_nfc.h"

// ================= НАЛАШТУВАННЯ =================
const char* ssid_1 = "nn2";
const char* pass_1 = "abcdefghijkl";
const char* ssid_2 = "Red";
const char* pass_2 = "12345678";
WiFiMulti wifiMulti;

const char* serverUrl = "http://141.147.21.34:5000/api/scan";
const char* token     = "TOKEN_EXIT";
const char* hmacSecret = "SmartSchool_Secret_Key_2026";

// PN532 — I2C (SW1=ON, SW2=OFF на модулі)
// SDA → GPIO21, SCL → GPIO22 (стандарт ESP32 Wire)
#define PN532_IRQ_PIN  15   // -1 якщо не підключено
#define PN532_RST_PIN  -1   // не потрібен

// Індикатори (LED_GREEN переміщено з GPIO21 → GPIO25!)
#define BUZZER_PIN     27
#define LED_GREEN_PIN  25   // ← УВАГА: переключіть дріт з GPIO21 на GPIO25
#define LED_RED_PIN    17
// =================================================

Adafruit_PN532 nfc(PN532_IRQ_PIN, PN532_RST_PIN);

struct OfflineRecord {
  String uid;
  unsigned long scanTime;
};
std::vector<OfflineRecord> offlineBuffer;

unsigned long lastScanTime = 0;
const unsigned long COOLDOWN = 10000;
String lastUID = "";

// ---- Сигнали ----
void signalProcessing() {
  digitalWrite(BUZZER_PIN, HIGH); delay(50); digitalWrite(BUZZER_PIN, LOW);
}
void signalSuccess() {
  digitalWrite(LED_GREEN_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH); delay(100); digitalWrite(BUZZER_PIN, LOW);
  delay(800);
  digitalWrite(LED_GREEN_PIN, LOW);
}
void signalError() {
  digitalWrite(LED_RED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH); delay(1000);
  digitalWrite(LED_RED_PIN, LOW); digitalWrite(BUZZER_PIN, LOW);
}
void signalOfflineSave() {
  digitalWrite(LED_GREEN_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH); delay(50); digitalWrite(BUZZER_PIN, LOW); delay(50);
  digitalWrite(BUZZER_PIN, HIGH); delay(50); digitalWrite(BUZZER_PIN, LOW);
  delay(850);
  digitalWrite(LED_GREEN_PIN, LOW);
}

// ---- HMAC-SHA256 підпис ----
String generateSignature(String uid, String currentToken) {
  String payload = uid + ":" + currentToken;
  byte hmacResult[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)hmacSecret, strlen(hmacSecret));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)payload.c_str(), payload.length());
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);
  String hashStr = "";
  for (int i = 0; i < 32; i++) {
    if (hmacResult[i] < 0x10) hashStr += "0";
    hashStr += String(hmacResult[i], HEX);
  }
  return hashStr;
}

void setup() {
  Serial.begin(115200);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_RED_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_GREEN_PIN, LOW);
  digitalWrite(LED_RED_PIN, LOW);

  // Ініціалізація PN532 по I2C
  Wire.begin(21, 22);
  nfc.begin();

  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("PN532 не знайдено! Перевірте підключення та DIP-перемикачі (SW1=ON, SW2=OFF).");
    // Мигаємо червоним поки не знайдено
    while (true) {
      digitalWrite(LED_RED_PIN, HIGH); delay(200);
      digitalWrite(LED_RED_PIN, LOW);  delay(200);
    }
  }
  Serial.print("PN532 знайдено! Chip: PN5");
  Serial.println((versiondata >> 24) & 0xFF, HEX);
  Serial.print("Firmware ver. ");
  Serial.print((versiondata >> 16) & 0xFF, DEC);
  Serial.print('.');
  Serial.println((versiondata >> 8) & 0xFF, DEC);

  nfc.SAMConfig();  // Дозволити зчитувати пасивні картки

  // Wi-Fi (підключається у фоні)
  wifiMulti.addAP(ssid_1, pass_1);
  wifiMulti.addAP(ssid_2, pass_2);

  if (!MDNS.begin("esp32-scanner")) {
    Serial.println("Помилка mDNS");
  }

  Serial.println("Система готова! Прикладіть картку або телефон.");
}

void loop() {
  bool isConnected = (wifiMulti.run() == WL_CONNECTED);

  // 1. Вивантаження офлайн-буфера якщо є Wi-Fi
  if (isConnected && !offlineBuffer.empty()) {
    OfflineRecord record = offlineBuffer.front();
    unsigned long offset_sec = (millis() - record.scanTime) / 1000;
    HTTPClient http;
    String sig = generateSignature(record.uid, String(token));
    String requestUrl = String(serverUrl)
      + "?token=" + token
      + "&uid=" + record.uid
      + "&offset=" + String(offset_sec)
      + "&signature=" + sig;
    http.begin(requestUrl);
    int httpCode = http.GET();
    http.end();
    if (httpCode > 0) {
      Serial.printf("Sync OK: %s (offset %lus)\n", record.uid.c_str(), offset_sec);
      offlineBuffer.erase(offlineBuffer.begin());
    }
  }

  // 2. Читання картки / телефону
  uint8_t uid[7];
  uint8_t uidLength;
  if (!nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 1000)) {
    return; // Картки немає — продовжуємо цикл
  }

  signalProcessing();

  // Завжди пробуємо APDU (HCE) спочатку, потім hardware UID як fallback
  String uidStr = smartSchoolResolveCardId(nfc, uid, uidLength);

  // 3. Debounce — ігноруємо повторне сканування тієї ж картки
  if (uidStr == lastUID && (millis() - lastScanTime < COOLDOWN)) {
    Serial.println("Debounce: ігноруємо дублікат");
    return;
  }
  lastUID = uidStr;
  lastScanTime = millis();

  Serial.println("Card UID: " + uidStr);

  // 4. Відправка на сервер або збереження в буфер
  if (isConnected) {
    HTTPClient http;
    String sig = generateSignature(uidStr, String(token));
    String requestUrl = String(serverUrl)
      + "?token=" + token
      + "&uid=" + uidStr
      + "&signature=" + sig;
    http.begin(requestUrl);
    int httpResponseCode = http.GET();
    if (httpResponseCode > 0) {
      Serial.println("HTTP: " + String(httpResponseCode));
      if (httpResponseCode == 200) {
        signalSuccess();
      } else {
        signalError();
      }
    } else {
      Serial.println("Сервер недоступний, зберігаємо офлайн...");
      if (offlineBuffer.size() < 100) {
        offlineBuffer.push_back({uidStr, millis()});
      }
      signalOfflineSave();
    }
    http.end();
  } else {
    Serial.println("Немає Wi-Fi, зберігаємо офлайн...");
    if (offlineBuffer.size() < 100) {
      offlineBuffer.push_back({uidStr, millis()});
      signalOfflineSave();
    } else {
      signalError();
    }
  }
}