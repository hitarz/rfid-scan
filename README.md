# SmartSchool: NFC & HCE Attendance System

SmartSchool is a comprehensive, offline-first attendance tracking system designed for educational institutions. It seamlessly bridges physical hardware scanners, a secure Android mobile wallet application, real-time web administration, and Telegram bot notifications to provide an end-to-end access control and monitoring solution.

## Architecture Overview

The project consists of several interconnected components:

1. **Backend Server (`server.py`)**
   - Built on Python and Flask, acting as the central hub for data and APIs.
   - Uses SQLite for lightweight, reliable database storage.
   - Provides a real-time responsive web dashboard using TailwindCSS and WebSockets (Socket.IO).
   
2. **Hardware Scanners (ESP32 + PN532)**
   - Physical RFID/NFC readers installed at entry/exit points.
   - Communicate securely with the backend via REST API (`/api/scan`).
   - Use HMAC-SHA256 signatures to prevent payload spoofing.

3. **Android Mobile Application (Kotlin)**
   - Operates as a Host Card Emulation (HCE) digital wallet, allowing students to use their smartphones instead of physical NFC cards.
   - Implements an **Offline-First** architecture. It generates cryptographic tokens that are valid even when the phone has no internet connection, and the scanners queue the scans if the backend goes down.
   - Secures communication through short-lived session tokens and Google OAuth.

4. **Telegram Integrations**
   - **Admin Bot (`bot.py`)**: Generates structured reports for administrators and teachers regarding student attendance, lateness, and absence by class or date.
   - **Parent Bot (`parent.py`)**: Allows parents to subscribe to their child's events and receive real-time push notifications when the child enters or exits the school.

---

## How It Works: The Data Flow

### 1. Identity & Binding
Students are registered in the system via the Web Admin Panel (manually or via Excel upload). A student can use a standard physical NFC card, or bind their Android app to their account. When using the app, the app retrieves an authorization token from the backend, linking the Google Account to the student's profile.

### 2. The Scanning Process (HCE)
When a student taps their smartphone to the physical PN532 reader:
1. The Android app transmits a secure, dynamically generated token alongside the User ID via NFC (Host Card Emulation).
2. The payload is cryptographically signed using HMAC to ensure it wasn't intercepted or forged.
3. The hardware scanner reads this data and forwards it to the backend via an HTTP GET request to `/api/scan`.

### 3. Server Validation & Logging
When the backend receives the scan request:
1. It validates the hardware token (verifying the request actually came from a legitimate entry/exit scanner).
2. It verifies the HMAC signature using a shared secret.
3. It resolves the identity of the student (matching hardware UIDs or alias UIDs to the database).
4. It calculates the time of entry based on predefined school schedules (e.g., categorizing as "On Time", "Late", "Break time", or "Anomaly").
5. The log is inserted into the SQLite database.

### 4. Real-time Updates & Notifications
As soon as the log is saved:
1. The server emits a WebSocket `refresh_logs` event. The Web Dashboard instantly updates without a page reload, showing the student's name, class, and status.
2. The backend places a notification message into the Telegram Queue.
3. A background worker picks up the message and uses the Telegram HTTP API to send an instant notification to subscribed parents (handled by `parent.py` subscriptions).

---

## Key Features

- **Offline-First Resilience**: Physical scanners can cache scans if the network drops. Mobile apps generate offline-valid dynamic NFC passes.
- **Role-Based Access Control (RBAC)**: Distinct permissions for `admin` (global view, user management) and `teacher` (restricted to view and manage only their assigned classes).
- **Automated Scheduling Analysis**: Automatically calculates lateness based on a dynamic bell schedule configured in the dashboard.
- **Multilingual Support**: The web interface supports English and Ukrainian seamlessly via a built-in localization dictionary.
- **Bulk Import**: Administrators can upload `.xlsx` (Excel) files to map hundreds of students to classes instantly.
- **Excuses & Manual Overrides**: Teachers can mark students as "Sick" or "Released early" directly from the dashboard.

## Installation & Setup

1. **Clone the repository.**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment Variables:**
   Create a `.env` file based on `.env.example`:
   ```env
   FLASK_SECRET_KEY=your_secure_flask_key
   HMAC_SECRET=your_hardware_hmac_secret
   PARENT_BOT_TOKEN=telegram_parent_bot_token
   TOKEN=telegram_admin_bot_token
   GOOGLE_CLIENT_ID=your_google_oauth_client_id
   ADMIN_LOGIN=admin
   ADMIN_PASS=admin
   ```
4. **Run the Application:**
   ```bash
   python3 server.py
   # For the telegram bots:
   python3 bot.py
   python3 parent.py
   ```
