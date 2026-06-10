@echo off
echo =======================================
echo     STARTING SMART SCHOOL SYSTEM...
echo =======================================

echo 1. Starting Main Server...
start "SmartSchool Server" cmd /k "python server.py"

:: Даємо серверу 2 секунди на запуск перед стартом інших модулів
timeout /t 2 /nobreak > NUL

echo 2. Starting Telegram Bot...
start "SmartSchool Admin Bot" cmd /k "python bot.py"

echo 3. Starting Parent Bot...
start "SmartSchool Parent Bot" cmd /k "python parent.py"

echo 4. Starting Backup System...
start "SmartSchool Auto Backup" cmd /k "python backup.py"

echo =======================================
echo       ALL SYSTEMS ARE RUNNING!
echo =======================================
pause