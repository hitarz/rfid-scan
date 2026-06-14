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
// PN532 автоматично обробляє ISO 14443-4, тому RATS не потрібен окремо
inline bool smartSchoolReadVirtualIdFromPhone(Adafruit_PN532 &nfc, String &outId) {
  uint8_t response[64];
  uint8_t responseLength;

  // --- Метод 1: SmartSchool AID (F0010203040506) ---
  uint8_t selectSs[] = {0x00, 0xA4, 0x04, 0x00, 0x07,
                         0xF0, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06};
  responseLength = sizeof(response);
  if (nfc.inDataExchange(selectSs, sizeof(selectSs), response, &responseLength)) {
    if (responseLength >= 2 &&
        response[responseLength - 2] == 0x90 &&
        response[responseLength - 1] == 0x00) {
      // GET CARD UID: 80 CB 00 00 08
      uint8_t getCmd[] = {0x80, 0xCB, 0x00, 0x00, 0x08};
      responseLength = sizeof(response);
      if (nfc.inDataExchange(getCmd, sizeof(getCmd), response, &responseLength)) {
        if (smartSchoolExtractIdFromBytes(response, responseLength, outId)) return true;
      }
    }
  }

  // --- Метод 2: NDEF AID (D2760000850101) → READ BINARY ---
  uint8_t selectNdef[] = {0x00, 0xA4, 0x04, 0x00, 0x07,
                           0xD2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01};
  responseLength = sizeof(response);
  if (nfc.inDataExchange(selectNdef, sizeof(selectNdef), response, &responseLength)) {
    if (responseLength >= 2 &&
        response[responseLength - 2] == 0x90 &&
        response[responseLength - 1] == 0x00) {
      uint8_t readBin[] = {0x00, 0xB0, 0x00, 0x00, 0x30};
      responseLength = sizeof(response);
      if (nfc.inDataExchange(readBin, sizeof(readBin), response, &responseLength)) {
        if (smartSchoolExtractIdFromBytes(response, responseLength, outId)) return true;
      }
    }
  }

  return false;
}

// Головна функція: повертає card_uid (virtual з телефону АБО hardware)
// Завжди спочатку пробує APDU (HCE), якщо не вдалось — повертає hardware UID
inline String smartSchoolResolveCardId(Adafruit_PN532 &nfc, uint8_t *uid, uint8_t uidLength) {
  // Спочатку завжди пробуємо прочитати virtual ID через APDU
  // Для звичайних карток це просто швидко поверне false
  String virtualId;
  if (smartSchoolReadVirtualIdFromPhone(nfc, virtualId)) {
    Serial.println("SmartSchool virtual ID: " + virtualId);
    return virtualId;
  }

  // Якщо APDU не спрацював — повертаємо апаратний UID
  String hw = smartSchoolFormatHwUid(uid, uidLength);
  Serial.println("Hardware UID: " + hw);
  return hw;
}
