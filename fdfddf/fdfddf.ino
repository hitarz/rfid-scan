#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include <HTTPClient.h>
#include <ESPmDNS.h>
#include <vector>
#include "smart_school_nfc.h"

// ================= НАСТРОЙКИ =================
// 1. Основний Wi-Fi (Шкільний)
const char* ssid_1 = "nn2";
const char* pass_1 = "abcdefghijkl";

// 2. Резервний Wi-Fi (Наприклад, роздача з телефону)
const char* ssid_2 = "Red";
const char* pass_2 = "12345678";

// Створюємо об'єкт для мульти-підключення
WiFiMulti wifiMulti; 
// =============================================
const char* serverUrl = "http://141.147.21.34:5000/api/scan";
const char* token = "TOKEN_ENTRY";
const char* hmacSecret = "SmartSchool_Secret_Key_2026";

#define RST_PIN 22
#define SS_PIN  5
#define BUZZER_PIN 27
#define LED_GREEN_PIN 21
#define LED_RED_PIN 17
// =============================================

MFRC522 mfrc522(SS_PIN, RST_PIN);

// Створюємо структуру, яка зберігає і картку, і час її сканування
struct OfflineRecord {
  String uid;
  unsigned long scanTime; // Тут будемо зберігати millis() на момент сканування
};

// Змінюємо тип нашого вектора
std::vector<OfflineRecord> offlineBuffer;

unsigned long lastScanTime = 0;      // Час останнього успішного сканування
const unsigned long COOLDOWN = 10000; // Затримка 10 секунд (10000 мілісекунд)
String lastUID = "";                 // UID останньої відсканованої картки

// ---- ФУНКЦИИ ИНДИКАЦИИ (ПАСИВНИЙ ЗУМЕР) ----

// Короткий писк при зчитуванні карти (Середній тон)
void signalProcessing() {
  tone(BUZZER_PIN, 2000); 
  delay(50);
  noTone(BUZZER_PIN);
}

// Успішний вхід (Зелений + Приємний високий тон)
void signalSuccess() {
  digitalWrite(LED_GREEN_PIN, HIGH);
  tone(BUZZER_PIN, 3000);
  delay(100);
  noTone(BUZZER_PIN);
  delay(900);
  digitalWrite(LED_GREEN_PIN, LOW);
}

// Помилка / Відмова (Червоний + Низький тривожний звук)
void signalError() {
  digitalWrite(LED_RED_PIN, HIGH);
  tone(BUZZER_PIN, 500); 
  delay(1000);
  noTone(BUZZER_PIN);
  digitalWrite(LED_RED_PIN, LOW);
}

// Збережено в офлайн (Зелений + Два коротких швидких писка)
void signalOfflineSave() {
  digitalWrite(LED_GREEN_PIN, HIGH);
  tone(BUZZER_PIN, 2500); delay(50); noTone(BUZZER_PIN); delay(50);
  tone(BUZZER_PIN, 2500); delay(50); noTone(BUZZER_PIN);
  delay(850);
  digitalWrite(LED_GREEN_PIN, LOW);
}

// ---------------------------
// Функція для створення HMAC-SHA256 підпису
String generateSignature(String uid, String currentToken) {
  String payload = uid + ":" + currentToken; // Формат: "UID:TOKEN"
  byte hmacResult[32];

  mbedtls_md_context_t ctx;
  mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;

  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char *)hmacSecret, strlen(hmacSecret));
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)payload.c_str(), payload.length());
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
  while (!Serial);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_RED_PIN, OUTPUT);
  
  noTone(BUZZER_PIN); // Завжди вимикаємо звук при старті
  digitalWrite(LED_GREEN_PIN, LOW);
  digitalWrite(LED_RED_PIN, LOW);

  SPI.begin();
  mfrc522.PCD_Init();
  
  Serial.print("Налаштування Wi-Fi...");
  wifiMulti.addAP(ssid_1, pass_1);
  wifiMulti.addAP(ssid_2, pass_2);
  
  if (!MDNS.begin("esp32-scanner")) { 
    Serial.println("Помилка запуску mDNS");
  } else {
    Serial.println("mDNS запущено успішно!");
  }

  Serial.println("\nСистема готова! Wi-Fi підключиться у фоні.");
}

void loop() {
  // Ця функція тримає зв'язок. Якщо мережа 1 впала, вона сама підключиться до мережі 2.
  bool isConnected = (wifiMulti.run() == WL_CONNECTED);

  // 1. ФОНОВАЯ ВЫГРУЗКА БУФЕРА (если есть интернет и в буфере есть данные)
  if (isConnected && !offlineBuffer.empty()) { 
    
    // Беремо ПЕРШИЙ запис із черги
    OfflineRecord record = offlineBuffer.front();
    
    // ВИРАХОВУЄМО ЗМІЩЕННЯ ЧАСУ (скільки секунд тому було сканування)
    unsigned long offset_sec = (millis() - record.scanTime) / 1000;
    
    HTTPClient http;
    
    // ДОДАЄМО параметр &offset=... до нашого GET-запиту
    String sig = generateSignature(record.uid, String(token));
    String requestUrl = String(serverUrl) + "?token=" + token + "&uid=" + record.uid + "&offset=" + String(offset_sec) + "&signature=" + sig;
    
    http.begin(requestUrl);
    int httpCode = http.GET();
    http.end();

    // Видаляємо з буфера, якщо сервер дав БУДЬ-ЯКУ відповідь (навіть помилку)
    if (httpCode > 0) {
      Serial.print("Sync OK: ");
      Serial.print(record.uid);
      Serial.print(" (Спізнилося на ");
      Serial.print(offset_sec);
      Serial.println(" секунд)");
      
      offlineBuffer.erase(offlineBuffer.begin());
    }
  }

  // 2. ПОИСК НОВОЙ КАРТЫ
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  // Карта найдена!
  signalProcessing();

  // 3. Стабільний ID з телефону (HCE) або hardware UID (RFID-картка)
  String uidStr = smartSchoolResolveCardId(mfrc522);
  
  // === ЗАХИСТ ВІД ПАНІЧНОГО СКАНУВАННЯ (DEBOUNCING) ===
  if (uidStr == lastUID && (millis() - lastScanTime < COOLDOWN)) {
    Serial.println("Захист від спаму: ігноруємо дублікат");
    mfrc522.PICC_HaltA(); // Зупиняємо читання цієї карти
    return; // Виходимо, щоб не слати запит
  }

  // Оновлюємо дані для наступної перевірки
  lastUID = uidStr;
  lastScanTime = millis();
  // ============================================================

  Serial.println("Card UID: " + uidStr);

  // 4. ОТПРАВКА НА СЕРВЕР ИЛИ СОХРАНЕНИЕ В БУФЕР
  if (isConnected) { 
    HTTPClient http;
    String sig = generateSignature(uidStr, String(token));
    String requestUrl = String(serverUrl) + "?token=" + token + "&uid=" + uidStr + "&signature=" + sig;
    
    http.begin(requestUrl);
    int httpResponseCode = http.GET();
    
    if (httpResponseCode > 0) {
      Serial.println("HTTP Code: " + String(httpResponseCode));
      
      if (httpResponseCode == 200) {
        signalSuccess(); // Сервер пустил
      } else {
        signalError();   // Сервер отказал в доступе (напр. 403)
      }
    } else {
      // Интернет есть, но сервер не отвечает (упал локальный сервер на Python)
      Serial.println("Server unreachable, saving offline...");
      if (offlineBuffer.size() < 100) {
        offlineBuffer.push_back({uidStr, millis()});
      }
      signalOfflineSave(); 
    }
    http.end();
    
  } else {
    // Wi-Fi отключился (Нет сети)
    Serial.println("No WiFi, saving offline...");
    if (offlineBuffer.size() < 100) {
      offlineBuffer.push_back({uidStr, millis()});
      signalOfflineSave(); // Пропускаем ученика, запишем потом
    } else {
      signalError(); // Буфер переполнен
    }
  }
  
  // 5. ОЖИДАНИЕ ПЕРЕД СЛЕДУЮЩИМ СКАНИРОВАНИЕМ
  mfrc522.PICC_HaltA();
  delay(1000); 
}
