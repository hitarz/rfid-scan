#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>
#include <WiFiMulti.h> // <=== ДОДАЛИ БІБЛІОТЕКУ
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
const char* token = "TOKEN_EXIT";
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
const unsigned long COOLDOWN = 10000; // Затримка 5 секунд (5000 мілісекунд)
String lastUID = "";                 // UID останньої відсканованої картки

// ---- ФУНКЦИИ ИНДИКАЦИИ ----

// Короткий писк при считывании карты
void signalProcessing() {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(50);
  digitalWrite(BUZZER_PIN, LOW);
}

// Успешный вход (Зеленый + Короткий писк)
void signalSuccess() {
  digitalWrite(LED_GREEN_PIN, HIGH);
  delay(100);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(100);
  digitalWrite(BUZZER_PIN, LOW);
  delay(800);
  digitalWrite(LED_GREEN_PIN, LOW);
}

// Ошибка / Отказ (Красный + Длинный писк)
void signalError() {
  digitalWrite(LED_RED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(1000);
  digitalWrite(LED_RED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
}

// Сохранено в офлайн (Зеленый + Два коротких писка)
void signalOfflineSave() {
  digitalWrite(LED_GREEN_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH); delay(50); digitalWrite(BUZZER_PIN, LOW); delay(50);
  digitalWrite(BUZZER_PIN, HIGH); delay(50); digitalWrite(BUZZER_PIN, LOW);
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
  
  digitalWrite(BUZZER_PIN, LOW);
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
  if (isConnected && !offlineBuffer.empty()) { // <=== ТУТ ТЕЖ ЗАМІНИЛИ НА isConnected
    
    // Беремо ПЕРШИЙ запис із черги
    OfflineRecord record = offlineBuffer.front();
    
    // ВИРАХОВУЄМО ЗМІЩЕННЯ ЧАСУ (скільки секунд тому було сканування)
    // Поточний час мінус час сканування, поділити на 1000 (бо millis це мілісекунди)
    unsigned long offset_sec = (millis() - record.scanTime) / 1000;
    
    HTTPClient http;
    
    // ДОДАЄМО параметр &offset=... до нашого GET-запиту
    String sig = generateSignature(record.uid, String(token));
    String requestUrl = String(serverUrl) + "?token=" + token + "&uid=" + record.uid + "&offset=" + String(offset_sec) + "&signature=" + sig;
    
    http.begin(requestUrl);
    int httpCode = http.GET();
    http.end();

    // ИСПРАВЛЕНИЕ БАГА: Удаляем из буфера, если сервер дал ЛЮБОЙ ответ (даже 403 Ошибка).
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
  
  // === ДОДАНО: ЗАХИСТ ВІД ПАНІЧНОГО СКАНУВАННЯ (DEBOUNCING) ===
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
  if (isConnected) { // <=== ОСЬ ЦЯ ЗМІНА
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
        // === ВИПРАВЛЕНО: передаємо структуру {uid, час} ===
        offlineBuffer.push_back({uidStr, millis()});
      }
      signalOfflineSave(); 
    }
    http.end();
    
  } else {
    // Wi-Fi отключился (Нет сети)
    Serial.println("No WiFi, saving offline...");
    if (offlineBuffer.size() < 100) {
      // === ВИПРАВЛЕНО: передаємо структуру {uid, час} ===
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