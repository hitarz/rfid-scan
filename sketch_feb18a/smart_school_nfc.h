#pragma once

#include <Adafruit_PN532.h>

// =====================================================================
// SmartSchool NFC Helper — для PN532 (I2C/SPI/HSU)
// Читає virtual card_uid з телефону (HCE) або hardware UID з картки
// =====================================================================

inline String smartSchoolFormatHwUid(uint8_t *uid, uint8_t uidLength) {
  String s = "";
  for (uint8_t i = 0; i < uidLength; i++) {
    if (uid[i] < 0x10) s += "0";
    s += String(uid[i], HEX);
  }
  s.toUpperCase();
  return s;
}

// Витягує 8-символьний HEX ID або "SSCARD:XXXXXXXX" із сирих байт відповіді
inline bool smartSchoolExtractIdFromBytes(const uint8_t *data, uint8_t len, String &outId) {
  // Спроба 1: 8 послідовних hex-символів ASCII
  String raw = "";
  for (uint8_t i = 0; i < len; i++) {
    char c = (char)data[i];
    bool isHex = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f');
    if (isHex) {
      raw += (char)toupper(c);
    } else if (raw.length() >= 8) {
      break;
    } else {
      raw = "";
    }
  }
  if (raw.length() >= 8) {
    outId = raw.substring(0, 8);
    return true;
  }

  // Спроба 2: маркер "SSCARD:XXXXXXXX" у тексті
  String text = "";
  for (uint8_t i = 0; i < len; i++) {
    char c = (char)data[i];
    if (c >= 32 && c <= 126) text += c;
  }
  int marker = text.indexOf("SSCARD:");
  if (marker >= 0 && marker + 15 <= (int)text.length()) {
    outId = text.substring(marker + 7, marker + 15);
    outId.toUpperCase();
    return outId.length() == 8;
  }
  return false;
}

// Намагається прочитати virtual ID з телефону через APDU (HCE)
// Підтримує обидві версії додатка:
// Нова: повертає card_uid прямо у відповіді на SELECT AID
// Стара: повертає 90 00 на SELECT AID, і потребує команди GET CARD UID
inline bool smartSchoolReadVirtualIdFromPhone(Adafruit_PN532 &nfc, String &outId) {
  uint8_t response[64];
  uint8_t responseLength;

  // 1. SELECT SmartSchool AID (F0010203040506)
  uint8_t selectSs[] = {0x00, 0xA4, 0x04, 0x00, 0x07,
                         0xF0, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06};

  // Робимо до 3 спроб, оскільки Android HCE іноді потребує часу на запуск сервісу
  // і може скидати перші APDU з помилкою 0xB (RF Protocol Error)
  for (int retry = 0; retry < 3; retry++) {
    if (retry > 0) {
      Serial.println("APDU retry... re-listing target");
      delay(50); // Даємо телефону трохи часу
      if (!nfc.inListPassiveTarget()) {
        continue; // Якщо телефон вже прибрали, пропускаємо
      }
    }

    responseLength = sizeof(response);
    Serial.println("APDU: SELECT SmartSchool AID...");
    if (nfc.inDataExchange(selectSs, sizeof(selectSs), response, &responseLength)) {
      Serial.print("Response len="); Serial.print(responseLength);
      Serial.print(" data: ");
      for (uint8_t i = 0; i < responseLength; i++) {
        Serial.print(response[i], HEX); Serial.print(' ');
      }
      Serial.println();
      
      // Перевіряємо SW 90 00
      if (responseLength >= 2 &&
          response[responseLength - 2] == 0x90 &&
          response[responseLength - 1] == 0x00) {
        
        // Якщо нова версія додатка повернула дані разом з 90 00
        if (responseLength >= 4) {
          if (smartSchoolExtractIdFromBytes(response, responseLength - 2, outId)) {
            return true;
          }
        } 
        // Якщо стара версія повернула тільки 90 00, надсилаємо GET CARD UID
        else if (responseLength == 2) {
          uint8_t getCmd[] = {0x80, 0xCB, 0x00, 0x00, 0x08};
          responseLength = sizeof(response);
          Serial.println("APDU: GET CARD UID...");
          if (nfc.inDataExchange(getCmd, sizeof(getCmd), response, &responseLength)) {
            Serial.print("GET UID response len="); Serial.print(responseLength);
            Serial.print(" data: ");
            for (uint8_t i = 0; i < responseLength; i++) {
              Serial.print((char)response[i]);
            }
            Serial.println();
            if (smartSchoolExtractIdFromBytes(response, responseLength, outId)) return true;
          } else {
            Serial.println("APDU: GET UID failed");
          }
        }
      }
    } else {
      Serial.println("APDU: SELECT SmartSchool AID failed");
    }
  }

  return false;
}

// Головна функція: повертає card_uid (virtual з телефону АБО hardware)
// Завжди спочатку пробує APDU (HCE), якщо не вдалось — повертає hardware UID
inline String smartSchoolResolveCardId(Adafruit_PN532 &nfc, uint8_t *uid, uint8_t uidLength) {
  // Пробуємо прочитати virtual ID через APDU
  // Для звичайних карток це просто швидко поверне false
  String virtualId;
  if (smartSchoolReadVirtualIdFromPhone(nfc, virtualId)) {
    Serial.println("SmartSchool virtual ID: " + virtualId);
    return virtualId;
  }

  // Якщо HCE не спрацював, АЛЕ це телефон (випадкові UID в Android ЗАВЖДИ починаються з 0x08)
  // Ми не повинні повертати цей Hardware UID, бо він випадковий і щоразу змінюється.
  // Це викликало хибні помилки 403, коли телефон залишався на зчитувачі.
  if (uidLength == 4 && uid[0] == 0x08) {
    Serial.println("Phone detected but HCE failed. Ignoring random UID.");
    return ""; // Порожній рядок означає "ігнорувати"
  }

  // Якщо APDU не спрацював і це звичайна картка — повертаємо апаратний UID
  String hw = smartSchoolFormatHwUid(uid, uidLength);
  Serial.println("Hardware UID: " + hw);
  return hw;
}
