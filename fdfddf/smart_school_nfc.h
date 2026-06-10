#pragma once

#include <MFRC522.h>

inline String smartSchoolFormatHwUid(MFRC522 &mfrc522) {
  String uidStr = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(mfrc522.uid.uidByte[i], HEX);
  }
  uidStr.toUpperCase();
  return uidStr;
}

inline bool smartSchoolIsHexChar(char c) {
  return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f');
}

inline bool smartSchoolExtractIdFromBytes(const byte *data, byte len, String &outId) {
  String raw = "";
  for (byte i = 0; i < len; i++) {
    char c = (char)data[i];
    if (smartSchoolIsHexChar(c)) raw += (char)toupper(c);
    else if (raw.length() >= 8) break;
    else raw = "";
  }
  if (raw.length() >= 8) {
    outId = raw.substring(0, 8);
    return true;
  }

  String text = "";
  for (byte i = 0; i < len; i++) {
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

inline bool smartSchoolIsoTransceive(MFRC522 &mfrc522, byte *apdu, byte apduLen, byte *back, byte *backLen) {
  byte frame[64];
  if (apduLen + 1 > sizeof(frame)) return false;
  frame[0] = 0x02;
  memcpy(frame + 1, apdu, apduLen);
  MFRC522::StatusCode status = mfrc522.PCD_TransceiveData(frame, apduLen + 1, back, backLen);
  return status == MFRC522::STATUS_OK && *backLen > 0;
}

inline bool smartSchoolActivateIso(MFRC522 &mfrc522) {
  byte rats[] = {0xE0, 0x50};
  byte buf[32];
  byte len = sizeof(buf);
  return mfrc522.PCD_TransceiveData(rats, 2, buf, &len) == MFRC522::STATUS_OK;
}

inline bool smartSchoolApduOk(MFRC522 &mfrc522, byte *apdu, byte apduLen) {
  byte resp[32];
  byte respLen = sizeof(resp);
  if (!smartSchoolIsoTransceive(mfrc522, apdu, apduLen, resp, &respLen)) return false;
  return respLen >= 2 && resp[respLen - 2] == 0x90 && resp[respLen - 1] == 0x00;
}

inline bool smartSchoolTryApdu(MFRC522 &mfrc522, byte *apdu, byte apduLen, String &outId) {
  byte resp[96];
  byte respLen = sizeof(resp);
  if (!smartSchoolIsoTransceive(mfrc522, apdu, apduLen, resp, &respLen)) return false;

  if (respLen >= 2 && resp[respLen - 2] == 0x90 && resp[respLen - 1] == 0x00) {
    if (smartSchoolExtractIdFromBytes(resp, respLen - 2, outId)) return true;
  }
  return smartSchoolExtractIdFromBytes(resp, respLen, outId);
}

inline bool smartSchoolReadVirtualIdFromPhone(MFRC522 &mfrc522, String &outId) {
  MFRC522::PICC_Type type = mfrc522.PICC_GetType(mfrc522.uid.sak);
  if (type != MFRC522::PICC_TYPE_ISO_14443_4) return false;

  smartSchoolActivateIso(mfrc522);

  byte selectSs[] = {0x00, 0xA4, 0x04, 0x00, 0x07, 0xF0, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06};
  byte getCmd[] = {0x80, 0xCB, 0x00, 0x00, 0x08};
  if (smartSchoolApduOk(mfrc522, selectSs, sizeof(selectSs))) {
    if (smartSchoolTryApdu(mfrc522, getCmd, sizeof(getCmd), outId)) return true;
  }

  byte selectNdef[] = {0x00, 0xA4, 0x04, 0x00, 0x07, 0xD2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01};
  byte readBin[] = {0x00, 0xB0, 0x00, 0x00, 0x30};
  if (smartSchoolApduOk(mfrc522, selectNdef, sizeof(selectNdef))) {
    if (smartSchoolTryApdu(mfrc522, readBin, sizeof(readBin), outId)) return true;
  }

  return false;
}

inline String smartSchoolResolveCardId(MFRC522 &mfrc522) {
  String virtualId;
  if (smartSchoolReadVirtualIdFromPhone(mfrc522, virtualId)) {
    Serial.println("SmartSchool virtual ID: " + virtualId);
    return virtualId;
  }
  String hw = smartSchoolFormatHwUid(mfrc522);
  Serial.println("Hardware UID: " + hw);
  return hw;
}
