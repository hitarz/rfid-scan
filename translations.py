# -*- coding: utf-8 -*-
"""
UI strings: LANGUAGES['en'] / LANGUAGES['uk'].
Canonical values written to the database or matched in SQL must stay stable — see CANONICAL.
"""
from __future__ import annotations

from flask import g

# --- Stored in DB / used in SQL LIKE / form values (do not localize per request) ---
CANONICAL = {
    "class_unassigned": "Не задано",
    "excuse_sick": "На лікарняному",
    "excuse_released": "Звільнений",
    "room_system": "Система",
    "token_entry_room": "Головний вхід (Вулиця)",
    "token_exit_room": "Головний вихід (Приміщення)",
    # Log status strings (must match existing rows and hardware logic)
    "status_entry_allowed": "Вхід дозволено",
    "status_entry_break": "Вхід дозволено (Перерва)",
    "status_off_schedule": "Поза розкладом",
    "status_anomaly_reentry": "Аномалія: Повторний вхід",
    "status_anomaly_exit_no_entry": "Аномалія: Вихід без входу",
    "status_exit": "Вихід",
    "status_late_prefix": "Запізнення на",
    "status_late_suffix": "хв",
    "status_late_lesson_word": "урок",
    # Legacy substring checks in scan_card (inside last_status)
    "status_legacy_anomaly_reentry": "Аномалія: Повторний вхід",
    "substring_entry": "Вхід",
    "substring_late": "Запізнення",
    "substring_allowed": "дозволено",
    "substring_anomaly": "аномалія",
    "substring_sick": "лікарняному",
    "substring_released": "звільнений",
    "match_late": "запізнення",
    "match_anomaly": "аномалія",
    "match_allowed": "дозволено",
    "match_sick": "лікарняному",
    "match_released": "звільнений",
    "sql_like_late": "Запізнення",
    "sql_like_allowed": "дозволено",
}

HARDWARE_TOKENS = {
    "TOKEN_ENTRY": CANONICAL["token_entry_room"],
    "TOKEN_EXIT": CANONICAL["token_exit_room"],
}

CLASSES = [
    CANONICAL["class_unassigned"],
    "5-А",
    "6-А",
    "10-А",
    "10-Б",
    "10-В",
    "11-А",
    "11-Б",
    "11-В",
]

LANGUAGES: dict[str, dict[str, str]] = {
    "en": {
        "html_lang": "en",
        "nav_logo_alt": "Logo",
        "nav_link_classes": "Class lists",
        "nav_link_stats": "Analytics",
        "nav_link_settings": "Settings",
        "nav_mobile_journal": "Log",
        "nav_mobile_lists": "Lists",
        "nav_mobile_analytics": "Analytics",
        "nav_mobile_settings_short": "Settings",
        "page_title_index": "Smart School RFID — Event log",
        "page_title_classes": "Class lists — Smart School RFID",
        "page_title_stats": "Analytics — Smart School RFID",
        "page_title_settings": "Settings — Smart School",
        "stats_present_today": "Present (today)",
        "stats_ontime": "On time",
        "stats_late_short": "Late",
        "journal_title": "Event log",
        "csv_export": "CSV",
        "th_time": "Time",
        "th_room": "Room",
        "th_student": "Student",
        "th_status": "Status",
        "clear_hidden": "Clear",
        "new_card_title": "New card",
        "ph_uid": "UID (A1B2C3D4)",
        "ph_student_name": "Student full name",
        "btn_save": "Save",
        "modal_stats": "Statistics",
        "btn_hide_title": "Hide",
        "ph_name_quick": "Name",
        "btn_ok": "OK",
        "modal_present": "Attendance (today)",
        "modal_ontime": "On time (today)",
        "modal_late": "Late (today)",
        "modal_students_unit": "stu.",
        "modal_present_list": "Present:",
        "modal_absent_list": "Absent:",
        "modal_none": "None",
        "modal_no_data": "No data",
        "toast_unknown": "Unknown",
        "classes_heading": "Student lists",
        "search_placeholder": "Search by name…",
        "students_count": "stu.",
        "btn_sick_label": "Sick leave",
        "btn_released_label": "Excused absence",
        "stats_filter": "Filter",
        "stats_total_logs": "All records",
        "stats_punctuality": "Punctuality",
        "stats_late": "Late arrivals",
        "stats_excused_short": "Excused",
        "stats_chart_discipline": "Discipline",
        "stats_chart_late_by_class": "Late arrivals by class",
        "chart_late_count_label": "Late count",
        "chart_ratio_ontime": "On time",
        "chart_ratio_late": "Late",
        "settings_heading": "System settings",
        "settings_bell_title": "Bell schedule",
        "settings_first_lesson_label": "Start of first lesson:",
        "settings_save": "Save changes",
        "settings_promote_title": "Year-end class move",
        "settings_promote_desc": "Move all students from one class label to another (e.g. 10-A → 11-A). Past scan logs are not changed.",
        "settings_promote_from": "From class",
        "settings_promote_to": "To class",
        "settings_promote_submit": "Move all students",
        "settings_promote_confirm_label": "I confirm this bulk change",
        "promote_err_confirm": "Please tick the confirmation box.",
        "promote_err_invalid": "Invalid class selection.",
        "promote_err_same": "Source and target class must be different.",
        "promote_ok_zero": "No students had the selected source class. Nothing was updated.",
        "promote_ok": "{count} student(s) updated.",
        "csv_col_date": "Date",
        "csv_col_room": "Room",
        "csv_col_uid": "UID",
        "csv_col_name": "Name",
        "csv_col_class": "Class",
        "csv_col_status": "Status",
        "csv_unknown_name": "Unknown",
        "err_parent_token": "Error: PARENT_BOT_TOKEN not found in .env file!",
        "err_auth_required": "Authentication required.\n",
        "log_spoof_attempt": "SPOOF ATTEMPT! Invalid signature for UID {uid}",
        "telegram_line_title": "Access control notification",
        "telegram_line_student": "Student:",
        "telegram_line_location": "Location:",
        "telegram_line_time": "Time:",
        "telegram_line_status": "Status:",
        "status_badge_entry_in": "In",
        "status_badge_reentry": "Re-entry",
        "status_badge_late_short": "Late",
        "scan_denied_invalid_token": "Denied: invalid token",
        "scan_denied_missing_uid": "Denied: missing or empty UID",
        "scan_denied_missing_signature": "Denied: missing cryptographic signature",
        "scan_denied_invalid_signature": "Denied: invalid signature (spoofing)",
        "scan_denied_unknown_card": "Denied: unknown card (press Pass in app first)",
    },
    "uk": {
        "html_lang": "uk",
        "nav_logo_alt": "Логотип",
        "nav_link_classes": "Списки класів",
        "nav_link_stats": "Аналітика",
        "nav_link_settings": "Налаштування",
        "nav_mobile_journal": "Журнал",
        "nav_mobile_lists": "Списки",
        "nav_mobile_analytics": "Аналітика",
        "nav_mobile_settings_short": "Налашт.",
        "page_title_index": "Smart School RFID — Журнал подій",
        "page_title_classes": "Списки класів — Smart School RFID",
        "page_title_stats": "Аналітика — Smart School RFID",
        "page_title_settings": "Налаштування — Smart School",
        "stats_present_today": "Присутні (сьогодні)",
        "stats_ontime": "Вчасно",
        "stats_late_short": "Запізн.",
        "journal_title": "Журнал подій",
        "csv_export": "CSV",
        "th_time": "Час",
        "th_room": "Аудиторія",
        "th_student": "Учень",
        "th_status": "Статус",
        "clear_hidden": "Очистити",
        "new_card_title": "Нова картка",
        "ph_uid": "UID (A1B2C3D4)",
        "ph_student_name": "ПІБ учня",
        "btn_save": "Зберегти",
        "modal_stats": "Статистика",
        "btn_hide_title": "Сховати",
        "ph_name_quick": "Ім'я",
        "btn_ok": "ОК",
        "modal_present": "Присутність (сьогодні)",
        "modal_ontime": "Вчасно (сьогодні)",
        "modal_late": "Запізнення (сьогодні)",
        "modal_students_unit": "уч.",
        "modal_present_list": "Присутні:",
        "modal_absent_list": "Відсутні:",
        "modal_none": "Немає",
        "modal_no_data": "Немає даних",
        "toast_unknown": "Невідомо",
        "classes_heading": "Списки учнів",
        "search_placeholder": "Пошук за ім'ям…",
        "students_count": "уч.",
        "btn_sick_label": "Лікарняний",
        "btn_released_label": "Звільнений",
        "stats_filter": "Фільтр",
        "stats_total_logs": "Усі записи",
        "stats_punctuality": "Пунктуальність",
        "stats_late": "Запізнення",
        "stats_excused_short": "Поважні причини",
        "stats_chart_discipline": "Дисципліна",
        "stats_chart_late_by_class": "Запізнення за класами",
        "chart_late_count_label": "Кількість запізнень",
        "chart_ratio_ontime": "Вчасно",
        "chart_ratio_late": "Запізнення",
        "settings_heading": "Налаштування системи",
        "settings_bell_title": "Розклад дзвінків",
        "settings_first_lesson_label": "Початок першого уроку:",
        "settings_save": "Зберегти зміни",
        "settings_promote_title": "Переведення класу (на новий навчальний рік)",
        "settings_promote_desc": "Усім учням з обраного класу буде змінено поле «клас» на новий (наприклад 10-А → 11-А). Записи в журналі сканувань не змінюються.",
        "settings_promote_from": "З якого класу",
        "settings_promote_to": "У який клас",
        "settings_promote_submit": "Перевести всіх",
        "settings_promote_confirm_label": "Підтверджую масову зміну",
        "promote_err_confirm": "Поставте галочку підтвердження.",
        "promote_err_invalid": "Некоректний вибір класу.",
        "promote_err_same": "Початковий і цільовий клас не повинні збігатися.",
        "promote_ok_zero": "У вибраному класі не було жодного учня. Змін не внесено.",
        "promote_ok": "Оновлено записів: {count}.",
        "csv_col_date": "Дата",
        "csv_col_room": "Аудиторія",
        "csv_col_uid": "UID",
        "csv_col_name": "Ім'я",
        "csv_col_class": "Клас",
        "csv_col_status": "Статус",
        "csv_unknown_name": "Невідомо",
        "err_parent_token": "Помилка: PARENT_BOT_TOKEN не знайдено у файлі .env!",
        "err_auth_required": "Потрібна авторизація.\n",
        "log_spoof_attempt": "СПРОБА СПУФІНГУ! Некоректний підпис для UID {uid}",
        "telegram_line_title": "Сповіщення СКУД",
        "telegram_line_student": "Учень:",
        "telegram_line_location": "Локація:",
        "telegram_line_time": "Час:",
        "telegram_line_status": "Статус:",
        "status_badge_entry_in": "Вхід",
        "status_badge_reentry": "Повторний вхід",
        "status_badge_late_short": "Запізн.",
        "scan_denied_invalid_token": "Відмовлено: невірний токен",
        "scan_denied_missing_uid": "Відмовлено: відсутній або порожній UID",
        "scan_denied_missing_signature": "Відмовлено: відсутній криптографічний підпис",
        "scan_denied_invalid_signature": "Відмовлено: невірний підпис (спуфінг)",
        "scan_denied_unknown_card": "Відмовлено: невідома картка (спочатку натисніть «Пройти» в додатку)",
    },
}


def parse_accept_language(header: str | None) -> str:
    if not header:
        return "en"
    for part in header.split(","):
        lang = part.split(";")[0].strip().lower()
        if lang.startswith("uk") or lang == "ua":
            return "uk"
        if lang.startswith("en"):
            return "en"
    return "en"


def gettext(key: str, lang: str | None = None) -> str:
    if lang is None:
        try:
            lang = getattr(g, "lang", None) or "en"
        except RuntimeError:
            lang = "en"
    if lang not in LANGUAGES:
        lang = "en"
    return LANGUAGES[lang].get(key, LANGUAGES["en"].get(key, key))


def gettext_fmt(key: str, **kwargs) -> str:
    lang = kwargs.pop("lang", None)
    return gettext(key, lang=lang).format(**kwargs)


def t_dict(lang: str | None = None) -> dict[str, str]:
    if lang is None:
        try:
            lang = getattr(g, "lang", "en")
        except RuntimeError:
            lang = "en"
    if lang not in LANGUAGES:
        lang = "en"
    return LANGUAGES[lang]
