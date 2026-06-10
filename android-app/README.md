# Smart School Card — Android

Мобільний додаток для входу через Google та створення цифрової NFC-картки для системи Smart School RFID.

## Як це працює

1. Користувач входить через **Google**.
2. Натискає **«Створити картку»** — сервер видає **постійний** віртуальний ID (наприклад `A1B2C3D4`).
3. Телефон через **HCE** передає цей ID зчитувачу (не змінний hardware UID чипа NFC).
4. **ESP32 з оновленою прошивкою** читає ID через APDU і надсилає на сервер (`/api/scan`).
5. Прикладайте телефон до зчитувача — той самий ID кожного разу.

> Android змінює hardware NFC UID при кожному скануванні. Тому стара логіка «привʼязати NFC» видалена.
> Потрібна прошивка ESP32 з файлом `smart_school_nfc.h`.

## Налаштування Google Sign-In

1. Відкрийте [Google Cloud Console](https://console.cloud.google.com/).
2. Створіть проєкт → **APIs & Services** → **Credentials**.
3. Створіть **OAuth 2.0 Client ID** типу **Web application** — скопіюйте Client ID.
4. Створіть **OAuth 2.0 Client ID** типу **Android**:
   - Package name: `com.smartschool.card`
   - SHA-1: отримайте командою  
     `keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android`
5. У `app/build.gradle.kts` вкажіть:
   - `GOOGLE_WEB_CLIENT_ID` — Web Client ID з кроку 3
   - `SERVER_URL` — адреса Flask-сервера (наприклад `http://192.168.1.100:5000`)
6. У `.env` на сервері додайте той самий Web Client ID:
   ```
   GOOGLE_CLIENT_ID=ваш-web-client-id.apps.googleusercontent.com
   ```

## Збірка

Відкрийте папку `android-app` в **Android Studio** (Ladybug або новіше) і натисніть **Run**.

Або з командного рядка (потрібен Android SDK):

```bash
cd android-app
./gradlew assembleDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`

## Емулятор

- `SERVER_URL` для емулятора: `http://10.0.2.2:5000` (localhost хост-машини).
- NFC на емуляторі не працює — тестуйте на реальному пристрої.

## NFC

- Увімкніть NFC на телефоні.
- Додаток використовує **Host Card Emulation (HCE)** — телефон виступає як NFC-картка.
- Зчитувач MFRC522 на ESP32 зчитує **апаратний UID** чипа NFC телефону (не віртуальний UID з додатку).
- Тому обовʼязковий крок **привʼязки NFC** після створення картки.
