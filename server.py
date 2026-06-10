from flask import Flask, request, render_template_string, redirect, url_for, jsonify, Response, g, session, flash
from flask_socketio import SocketIO
import sqlite3
from datetime import datetime, timedelta
import csv
import io
import json
import urllib.request
from functools import wraps
import threading
import queue  
import time   
import hmac
import hashlib
import os
import secrets
import uuid
from dotenv import load_dotenv

from translations import (
    CANONICAL,
    CLASSES,
    HARDWARE_TOKENS,
    LANGUAGES,
    gettext,
    gettext_fmt,
    parse_accept_language,
    t_dict,
)

MOBILE_CLASSES = [c for c in CLASSES if c != CANONICAL['class_unassigned']]

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default-unsafe-key')
socketio = SocketIO(app, cors_allowed_origins="*")

DB_NAME = 'rfid_database.db'

HMAC_SECRET = os.getenv('HMAC_SECRET', 'default-hmac-key')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
MOBILE_TOKEN_TTL_HOURS = int(os.getenv('MOBILE_TOKEN_TTL_HOURS', '720'))

ADMIN_LOGIN = os.getenv('ADMIN_LOGIN', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASS', 'admin')
PARENT_BOT_TOKEN = os.getenv('PARENT_BOT_TOKEN')

if not PARENT_BOT_TOKEN:
    raise ValueError(LANGUAGES['en']['err_parent_token'])


@app.before_request
def _set_request_language():
    if session.get('lang') == 'ru':
        session['lang'] = 'uk'
    lang = request.args.get('lang')
    if lang in ('en', 'uk'):
        session['lang'] = lang
    lang = session.get('lang') or parse_accept_language(request.headers.get('Accept-Language'))
    if lang not in ('en', 'uk'):
        lang = 'en'
    g.lang = lang

LESSONS = [
    {"num": 1, "start": "08:00", "end": "08:45"},
    {"num": 2, "start": "08:55", "end": "09:40"},
    {"num": 3, "start": "10:00", "end": "10:45"},
    {"num": 4, "start": "11:00", "end": "11:45"},
    {"num": 5, "start": "12:30", "end": "13:15"},
    {"num": 6, "start": "13:25", "end": "14:10"},
    {"num": 7, "start": "14:30", "end": "15:15"},
    {"num": 8, "start": "15:30", "end": "20:15"}
]

def check_auth(username, password):
    return username == ADMIN_LOGIN and password == ADMIN_PASS

def authenticate():
    return Response(gettext('err_auth_required'), 401, {'WWW-Authenticate': 'Basic realm="Admin Panel"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password): return authenticate()
        return f(*args, **kwargs)
    return decorated

# === ЧЕРГА TELEGRAM (Захист від лімітів API) ===
telegram_queue = queue.Queue()

def telegram_worker():
    while True:
        if not telegram_queue.empty():
            chat_ids, msg_text = telegram_queue.get()
            for chat_id in chat_ids:
                try:
                    url = f"https://api.telegram.org/bot{PARENT_BOT_TOKEN}/sendMessage"
                    data = json.dumps({"chat_id": chat_id, "text": msg_text, "parse_mode": "Markdown"}).encode('utf-8')
                    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req, timeout=3)
                except Exception as e:
                    print(f"Telegram Error: {e}")
                
                # СПАСІННЯ ВІД БАНУ: Затримка 0.05 сек між повідомленнями (макс 20 на секунду)
                time.sleep(0.05) 
            
            telegram_queue.task_done()
        else:
            time.sleep(0.5) # Якщо черга порожня - спимо півсекунди

# Запускаємо фонового робітника (працюватиме постійно)
threading.Thread(target=telegram_worker, daemon=True).start()


def build_index_i18n_obj():
    return {
        "class_unassigned": CANONICAL["class_unassigned"],
        "match_late": CANONICAL["match_late"],
        "match_anomaly": CANONICAL["match_anomaly"],
        "match_allowed": CANONICAL["match_allowed"],
        "match_sick": CANONICAL["match_sick"],
        "match_released": CANONICAL["match_released"],
        "status_entry_allowed": CANONICAL["status_entry_allowed"],
        "status_anomaly_reentry": CANONICAL["status_anomaly_reentry"],
        "status_late_prefix": CANONICAL["status_late_prefix"],
        "badge_in": gettext("status_badge_entry_in"),
        "badge_reentry": gettext("status_badge_reentry"),
        "badge_late": gettext("status_badge_late_short"),
        "modal_present": gettext("modal_present"),
        "modal_ontime": gettext("modal_ontime"),
        "modal_late": gettext("modal_late"),
        "modal_students_unit": gettext("modal_students_unit"),
        "modal_present_list": gettext("modal_present_list"),
        "modal_absent_list": gettext("modal_absent_list"),
        "modal_none": gettext("modal_none"),
        "modal_no_data": gettext("modal_no_data"),
        "toast_unknown": gettext("toast_unknown"),
        "ph_name_quick": gettext("ph_name_quick"),
        "btn_ok": gettext("btn_ok"),
        "btn_hide_title": gettext("btn_hide_title"),
    }


# === Shared navigation (Jinja: pass `t` as LANGUAGES[g.lang]) ===
NAV_HTML = """
<nav class="glass-panel fixed w-full z-30 top-0 shadow-sm transition-all duration-300">
    <div class="max-w-screen-2xl flex flex-wrap items-center justify-between mx-auto p-3 md:p-4">
        <a href="/" class="flex items-center space-x-2 md:space-x-3 group">
            <div class="w-8 h-8 md:w-10 md:h-10 flex items-center justify-center shrink-0 drop-shadow-sm group-hover:scale-105 transition-transform">
                <img src="/static/logo.png" alt="{{ t.nav_logo_alt }}" class="w-full h-full object-contain">
            </div>
            <span class="self-center text-xl md:text-2xl font-bold whitespace-nowrap dark:text-white tracking-tight">Smart<span class="text-blue-600 dark:text-blue-400">School</span></span>
        </a>
        <div class="flex items-center space-x-2 md:space-x-4">
            <div class="hidden md:flex items-center space-x-2">
                <a href="/classes" class="text-sm font-medium text-slate-700 hover:text-blue-600 dark:text-slate-200 dark:hover:text-blue-400 bg-slate-200/50 hover:bg-slate-300/50 dark:bg-slate-800 dark:hover:bg-slate-700 px-3 py-2 rounded-xl transition-colors shadow-sm">{{ t.nav_link_classes }}</a>
                <a href="/stats" class="text-sm font-medium text-slate-700 hover:text-blue-600 dark:text-slate-200 dark:hover:text-blue-400 bg-slate-200/50 hover:bg-slate-300/50 dark:bg-slate-800 dark:hover:bg-slate-700 px-3 py-2 rounded-xl transition-colors shadow-sm">📊 {{ t.nav_link_stats }}</a>
                <a href="/settings" class="text-sm font-medium text-slate-700 hover:text-blue-600 dark:text-slate-200 dark:hover:text-blue-400 bg-slate-200/50 hover:bg-slate-300/50 dark:bg-slate-800 dark:hover:bg-slate-700 px-3 py-2 rounded-xl transition-colors shadow-sm">⚙️ {{ t.nav_link_settings }}</a>
            </div>
            <div class="flex items-center gap-1 text-[10px] font-semibold uppercase text-slate-500 dark:text-slate-400">
                <a href="?lang=en" class="px-1.5 py-0.5 rounded hover:bg-slate-200 dark:hover:bg-slate-700">en</a>
                <span class="opacity-40">|</span>
                <a href="?lang=uk" class="px-1.5 py-0.5 rounded hover:bg-slate-200 dark:hover:bg-slate-700">UA</a>
            </div>
            <button id="theme-toggle" type="button" class="text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl p-2 md:p-2.5 transition-colors">
                <svg id="theme-toggle-dark-icon" class="hidden w-5 h-5 md:w-6 md:h-6" fill="currentColor" viewBox="0 0 20 20"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"></path></svg>
                <svg id="theme-toggle-light-icon" class="hidden w-5 h-5 md:w-6 md:h-6" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"></path></svg>
            </button>
        </div>
    </div>
</nav>
<div class="md:hidden fixed bottom-0 w-full z-40 glass-panel border-t border-slate-200 dark:border-slate-700 pb-2">
    <div class="flex justify-around items-center px-2 pt-2">
        <a href="/" class="flex flex-col items-center text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 p-2">
            <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>
            <span class="text-[10px] font-semibold">{{ t.nav_mobile_journal }}</span>
        </a>
        <a href="/classes" class="flex flex-col items-center text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 p-2">
            <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
            <span class="text-[10px] font-semibold">{{ t.nav_mobile_lists }}</span>
        </a>
        <a href="/stats" class="flex flex-col items-center text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 p-2">
            <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
            <span class="text-[10px] font-semibold">{{ t.nav_mobile_analytics }}</span>
        </a>
        <a href="/settings" class="flex flex-col items-center text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 p-2">
            <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
            <span class="text-[10px] font-semibold">{{ t.nav_mobile_settings_short }}</span>
        </a>
    </div>
</div>
<script>
    const themeBtn = document.getElementById('theme-toggle');
    const darkIcon = document.getElementById('theme-toggle-dark-icon');
    const lightIcon = document.getElementById('theme-toggle-light-icon');
    if (document.documentElement.classList.contains('dark')) lightIcon.classList.remove('hidden');
    else darkIcon.classList.remove('hidden');
    themeBtn.addEventListener('click', () => {
        darkIcon.classList.toggle('hidden');
        lightIcon.classList.toggle('hidden');
        if (document.documentElement.classList.contains('dark')) {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('color-theme', 'light');
            if(typeof updateChartTheme === 'function') updateChartTheme('light');
        } else {
            document.documentElement.classList.add('dark');
            localStorage.setItem('color-theme', 'dark');
            if(typeof updateChartTheme === 'function') updateChartTheme('dark');
        }
    });
</script>
"""

# === Main page ===
HTML_PAGE = (
"""
<!DOCTYPE html>
<html lang="{{ t.html_lang }}" class="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{{ t.page_title_index }}</title>
    {% raw %}
    <script>
        if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) { document.documentElement.classList.add('dark'); } else { document.documentElement.classList.remove('dark') }
    </script>
    {% endraw %}
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.1/socket.io.js"></script>
    {% raw %}
    <script>tailwind.config = { darkMode: 'class', theme: { extend: {} } }</script>
<style>
       .glass-panel { background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.3); }
       .dark .glass-panel { background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(255, 255, 255, 0.1); }
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @keyframes fadeOut { to { opacity: 0; } }
       .toast-enter { animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
       .toast-exit { animation: fadeOut 0.3s ease forwards; }
       details > summary { list-style: none; }
       details > summary::-webkit-details-marker { display: none; }
    </style>
    {% endraw %}
</head>
<body class="bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200 transition-colors duration-300 font-sans antialiased min-h-screen relative bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] pb-24 md:pb-12">
"""
+ NAV_HTML +
"""
    <div class="max-w-screen-2xl mx-auto pt-20 md:pt-24 px-3 md:px-4">
        
        <div class="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-6 mb-4 md:mb-6">
            <div class="glass-panel rounded-xl md:rounded-2xl p-4 md:p-6 shadow-md cursor-pointer hover:scale-[1.02] transition-transform col-span-2 md:col-span-1" onclick="openStatsModal('present')">
                <div class="flex items-center">
                    <div class="p-2 md:p-3 bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400 rounded-xl"><svg class="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg></div>
                    <div class="ml-3 md:ml-4">
                        <p class="text-xs md:text-sm font-medium text-slate-500 dark:text-slate-400">{{ t.stats_present_today }}</p>
                        <p class="text-2xl md:text-3xl font-bold text-slate-800 dark:text-white" id="stat-total">0</p>
                    </div>
                </div>
            </div>
            <div class="glass-panel rounded-xl md:rounded-2xl p-4 md:p-6 shadow-md cursor-pointer hover:scale-[1.02] transition-transform" onclick="openStatsModal('ontime')">
                <div class="flex items-center">
                    <div class="p-2 md:p-3 bg-emerald-100 text-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-400 rounded-xl"><svg class="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></div>
                    <div class="ml-3 md:ml-4">
                        <p class="text-xs md:text-sm font-medium text-slate-500 dark:text-slate-400">{{ t.stats_ontime }}</p>
                        <p class="text-2xl md:text-3xl font-bold text-slate-800 dark:text-white" id="stat-ontime">0</p>
                    </div>
                </div>
            </div>
            <div class="glass-panel rounded-xl md:rounded-2xl p-4 md:p-6 shadow-md cursor-pointer hover:scale-[1.02] transition-transform" onclick="openStatsModal('late')">
                <div class="flex items-center">
                    <div class="p-2 md:p-3 bg-amber-100 text-amber-600 dark:bg-amber-900/50 dark:text-amber-400 rounded-xl"><svg class="w-6 h-6 md:w-8 md:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></div>
                    <div class="ml-3 md:ml-4">
                        <p class="text-xs md:text-sm font-medium text-slate-500 dark:text-slate-400">{{ t.stats_late_short }}</p>
                        <p class="text-2xl md:text-3xl font-bold text-slate-800 dark:text-white" id="stat-late">0</p>
                    </div>
                </div>
            </div>
        </div>

        <div class="grid grid-cols-1 xl:grid-cols-4 gap-4 md:gap-6">
            <div class="xl:col-span-3">
                <div class="glass-panel rounded-xl md:rounded-2xl shadow-lg overflow-hidden h-full">
                    <div class="p-4 md:p-6 border-b border-slate-200 dark:border-slate-700 flex justify-between items-center">
                        <h3 class="text-lg md:text-xl font-bold flex items-center text-slate-900 dark:text-white">
                            <span class="w-2 h-2 md:w-3 md:h-3 bg-emerald-500 rounded-full mr-2 md:mr-3 animate-pulse"></span> {{ t.journal_title }}
                        </h3>
                        <div class="flex gap-2">
                            <a href="/api/export_csv" class="text-xs md:text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 px-3 md:px-4 py-1.5 md:py-2 rounded-lg shadow-sm">📥 {{ t.csv_export }}</a>
                            <button type="button" onclick="purgeUnknownLogs()" class="text-xs md:text-sm font-medium text-slate-700 dark:text-slate-200 bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 px-3 md:px-4 py-1.5 md:py-2 rounded-lg shadow-sm">🗑 Невідомі</button>
                        </div>
                    </div>
                    <div class="overflow-x-auto max-h-[60vh] md:max-h-[600px] overflow-y-auto">
                        <table class="w-full text-left text-slate-500 dark:text-slate-300">
                            <thead class="text-[10px] md:text-xs text-slate-600 uppercase bg-slate-100 dark:bg-slate-800 dark:text-slate-300 sticky top-0 z-10 backdrop-blur-md">
                                <tr>
                                    <th scope="col" class="px-3 py-3 md:px-6 md:py-4 font-semibold">{{ t.th_time }}</th>
                                    <th scope="col" class="hidden sm:table-cell px-3 py-3 md:px-6 md:py-4 font-semibold">{{ t.th_room }}</th>
                                    <th scope="col" class="px-3 py-3 md:px-6 md:py-4 font-semibold">{{ t.th_student }}</th>
                                    <th scope="col" class="px-3 py-3 md:px-6 md:py-4 font-semibold">{{ t.th_status }}</th>
                                    <th scope="col" class="px-2 py-3 md:px-6 md:py-4 text-center"><button onclick="clearHiddenLogs();" class="text-[10px] text-blue-500">{{ t.clear_hidden }}</button></th>
                                </tr>
                            </thead>
                            <tbody id="logs-body"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="xl:col-span-1">
                <div class="glass-panel rounded-xl md:rounded-2xl shadow-lg p-4 md:p-6">
                    <h3 class="text-md md:text-lg font-bold mb-4 text-slate-900 dark:text-white">➕ {{ t.new_card_title }}</h3>
                    <form action="/api/add_user" method="POST" class="flex flex-col gap-3 md:gap-4">
                        <input type="text" name="uid" placeholder="{{ t.ph_uid }}" required class="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-900 text-sm rounded-xl px-3 py-2 md:p-3 dark:text-white outline-none w-full">
                        <input type="text" name="name" placeholder="{{ t.ph_student_name }}" required class="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-900 text-sm rounded-xl px-3 py-2 md:p-3 dark:text-white outline-none w-full">
                        <select name="class_group" class="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-900 text-sm rounded-xl px-3 py-2 md:p-3 dark:text-white outline-none w-full">
                            {% for c in classes %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
                        </select>
                        <button type="submit" class="w-full text-white bg-emerald-600 hover:bg-emerald-700 font-medium rounded-xl text-sm px-5 py-3 mt-1 shadow-md active:scale-95 transition-transform">{{ t.btn_save }}</button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    </div>
</div>

   <div id="class-modal" class="hidden fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="glass-panel rounded-2xl w-full max-w-sm md:max-w-md p-5 md:p-6 relative shadow-2xl">
            <button onclick="closeStatsModal()" class="absolute top-3 right-3 md:top-4 md:right-4 text-slate-500 hover:text-slate-800 dark:hover:text-white p-2 text-xl transition-colors">✖</button>
            <h3 id="modal-title" class="text-lg md:text-xl font-bold mb-4 text-slate-900 dark:text-white">{{ t.modal_stats }}</h3>
            <div id="class-stats-list" class="flex flex-col max-h-[60vh] overflow-y-auto pr-1"></div>
        </div>
    </div>

    <div id="toast-container" class="fixed bottom-20 md:bottom-5 right-4 md:right-5 z-50 flex flex-col gap-2 w-[calc(100%-2rem)] md:w-auto md:max-w-xs pointer-events-none"></div>

    <script>
        const I18N = {{ i18n_obj | tojson }};
        const allUsers = {{ users_json | safe }};
        const classOptions = {{ class_options | tojson }};
    </script>
    <script>
{% raw %}
        window.classStats = {};

        function showToast(name, status, isLate) {
            const toast = document.createElement('div');
            const bgClass = isLate ? 'bg-rose-500' : 'bg-emerald-500';
            const icon = isLate ? '⚠️' : '✅';
            toast.className = `toast-enter pointer-events-auto glass-panel flex items-center w-full p-3 md:p-4 text-slate-900 dark:text-white rounded-xl md:rounded-2xl shadow-xl border-l-4 ${isLate ? 'border-amber-500' : 'border-emerald-500'}`;
            toast.innerHTML = `
                <div class="inline-flex items-center justify-center shrink-0 w-8 h-8 rounded-full ${bgClass} text-white shadow-inner text-sm">${icon}</div>
                <div class="ml-3 font-normal overflow-hidden">
                    <span class="mb-0.5 text-xs md:text-sm font-bold block truncate">${name}</span>
                    <div class="text-[10px] md:text-xs text-slate-500 dark:text-slate-400 truncate">${status}</div>
                </div>
            `;
            const container = document.getElementById('toast-container');
            container.appendChild(toast);
            setTimeout(() => {
                toast.classList.replace('toast-enter', 'toast-exit');
                setTimeout(() => toast.remove(), 300);
            }, 4000);
        }

        let isEditing = false;
        let hiddenLogs = JSON.parse(localStorage.getItem('hiddenLogs') || '[]');
        let lastKnownLogId = 0;

        document.getElementById('logs-body').addEventListener('focusin', (e) => { if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') isEditing = true; });
        document.getElementById('logs-body').addEventListener('focusout', (e) => { if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') isEditing = false; });

        function hideLog(logId) { hiddenLogs.push(logId); localStorage.setItem('hiddenLogs', JSON.stringify(hiddenLogs)); fetchLogs(); }
        function clearHiddenLogs() { hiddenLogs = []; localStorage.removeItem('hiddenLogs'); fetchLogs(); }

        function openStatsModal(type) {
            document.getElementById('class-modal').classList.remove('hidden');
            const listContainer = document.getElementById('class-stats-list');
            const titleElement = document.getElementById('modal-title');
            const cu = I18N.class_unassigned;
            let sortedClasses = Object.keys(window.classStats).sort((a,b) => a === cu ? 1 : b === cu ? -1 : a.localeCompare(b));

            if(type === 'present') titleElement.innerText = I18N.modal_present;
            else if(type === 'ontime') titleElement.innerText = I18N.modal_ontime;
            else if(type === 'late') titleElement.innerText = I18N.modal_late;

            let listHTML = '';

            sortedClasses.forEach(c => {
                let stats = window.classStats[c];
                if (stats.all.length === 0) return;

                let targetCount = 0;
                let summaryBadge = '';

                if (type === 'present') {
                    targetCount = stats.present.length;
                    summaryBadge = `<span class="bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300 text-[10px] font-bold px-2 py-0.5 rounded-full">${targetCount} / ${stats.all.length}</span>`;
                } else if (type === 'ontime') {
                    targetCount = stats.onTime.length;
                    if(targetCount === 0) return;
                    summaryBadge = `<span class="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300 text-[10px] font-bold px-2 py-0.5 rounded-full">${targetCount} ${I18N.modal_students_unit}</span>`;
                } else if (type === 'late') {
                    targetCount = stats.late.length;
                    if(targetCount === 0) return;
                    summaryBadge = `<span class="bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 text-[10px] font-bold px-2 py-0.5 rounded-full">${targetCount} ${I18N.modal_students_unit}</span>`;
                }

                let detailsHTML = '';
                if (type === 'present') {
                    detailsHTML += `<p class="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 mb-1">✅ ${I18N.modal_present_list}</p>`;
                    if(stats.present.length === 0) detailsHTML += `<p class="text-[10px] text-slate-500 ml-2 mb-2">${I18N.modal_none}</p>`;
                    stats.present.forEach(u => detailsHTML += `<p class="text-xs text-slate-700 dark:text-slate-300 ml-2 py-0.5">${u.name}</p>`);

                    detailsHTML += `<p class="text-[10px] font-bold text-rose-500 dark:text-rose-400 mt-3 mb-1">❌ ${I18N.modal_absent_list}</p>`;
                    if(stats.absent.length === 0) detailsHTML += `<p class="text-[10px] text-slate-500 ml-2">${I18N.modal_none}</p>`;
                    stats.absent.forEach(u => detailsHTML += `<p class="text-xs text-slate-700 dark:text-slate-300 ml-2 py-0.5">${u.name}</p>`);
                } else {
                    let colorClass = type === 'late' ? 'text-amber-500' : 'text-emerald-500';
                    let targetList = type === 'late' ? stats.late : stats.onTime;
                    targetList.forEach(u => detailsHTML += `<p class="text-xs text-slate-700 dark:text-slate-300 ml-2 py-0.5"><span class="${colorClass} mr-1.5">•</span>${u.name}</p>`);
                }

                listHTML += `
                <details class="group bg-slate-50 dark:bg-slate-800/80 rounded-xl border border-slate-200 dark:border-slate-700 mb-2 overflow-hidden">
                    <summary class="flex justify-between items-center p-3 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors">
                        <span class="font-semibold text-sm text-slate-800 dark:text-slate-200 flex items-center gap-2">
                            <svg class="w-4 h-4 text-slate-400 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                            ${c}
                        </span>
                        ${summaryBadge}
                    </summary>
                    <div class="px-4 pb-3 pt-1 border-t border-slate-200/50 dark:border-slate-700/50 bg-white dark:bg-slate-900/50">
                        ${detailsHTML}
                    </div>
                </details>`;
            });

            if (listHTML === '') listHTML = '<p class="text-slate-500 text-sm text-center py-4">' + I18N.modal_no_data + '</p>';
            listContainer.innerHTML = listHTML;
        }

        function closeStatsModal() { document.getElementById('class-modal').classList.add('hidden'); }

        function purgeUnknownLogs() {
            if (!confirm('Видалити записи без зареєстрованого учня?')) return;
            fetch('/api/purge_unknown_logs', { method: 'POST' })
                .then(r => r.json())
                .then(d => { alert('Видалено: ' + (d.deleted || 0)); fetchLogs(); })
                .catch(() => alert('Помилка очищення'));
        }

        function fetchLogs() {
            if (isEditing) return;
            fetch('/api/logs_json').then(res => {
                if (res.status === 401) { window.location.reload(); return null; }
                return res.json();
            }).then(data => {
                if (!data) return;

                if (data.length > 0) {
                    const currentMaxId = Math.max(...data.map(l => l.id));
                    if (lastKnownLogId > 0 && currentMaxId > lastKnownLogId) {
                        const newLogs = data.filter(l => l.id > lastKnownLogId);
                        newLogs.reverse().forEach(log => {
                            const st = log.status.toLowerCase();
                            const isLate = st.includes(I18N.match_late) || st.includes(I18N.match_anomaly);
                            const unk = I18N.toast_unknown + ' (' + log.uid + ')';
                            showToast(log.name || unk, log.status, isLate);
                        });
                    }
                    lastKnownLogId = currentMaxId;
                }

                let firstScanToday = {};
                const todayStr = new Date().toISOString().split('T')[0];

                data.forEach(log => {
                    if (log.scan_time.startsWith(todayStr)) {
                        firstScanToday[log.uid] = log.status;
                    }
                });

                let presentUIDs = new Set();
                let onTimeUIDs = new Set();
                let lateUIDs = new Set();

                Object.entries(firstScanToday).forEach(([uid, status]) => {
                    presentUIDs.add(uid);
                    const sl = status.toLowerCase();
                    if (sl.includes(I18N.match_late)) lateUIDs.add(uid);
                    else if (sl.includes(I18N.match_allowed)) onTimeUIDs.add(uid);
                });

                window.classStats = {};
                allUsers.forEach(u => {
                    let cg = u.class_group || I18N.class_unassigned;
                    if (!window.classStats[cg]) window.classStats[cg] = { all: [], present: [], absent: [], onTime: [], late: [] };

                    window.classStats[cg].all.push(u);
                    if (presentUIDs.has(u.uid)) window.classStats[cg].present.push(u);
                    else window.classStats[cg].absent.push(u);

                    if (onTimeUIDs.has(u.uid)) window.classStats[cg].onTime.push(u);
                    if (lateUIDs.has(u.uid)) window.classStats[cg].late.push(u);
                });

                document.getElementById('stat-total').innerText = presentUIDs.size;
                document.getElementById('stat-ontime').innerText = onTimeUIDs.size;
                document.getElementById('stat-late').innerText = lateUIDs.size;

                const tbody = document.getElementById('logs-body');
                tbody.innerHTML = '';

                let limit = 0;
                data.forEach(log => {
                    if (hiddenLogs.includes(log.id) || limit >= 100) return;
                    limit++;

                    let statusLower = log.status.toLowerCase();
                    let statusBadge = '';
                    const sea = I18N.status_entry_allowed;
                    const sar = I18N.status_anomaly_reentry;
                    const slp = I18N.status_late_prefix;
                    if (statusLower.includes(I18N.match_allowed)) {
                        statusBadge = `<span class="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-1 md:px-3 md:py-1.5 rounded-lg md:rounded-xl text-[10px] md:text-xs font-bold border border-emerald-500/20"><span class="mr-1 hidden md:inline">✅</span>${log.status.replace(sea, I18N.badge_in)}</span>`;
                    } else if (statusLower.includes(I18N.match_anomaly)) {
                        statusBadge = `<span class="bg-rose-500/10 text-rose-600 dark:text-rose-400 px-2 py-1 md:px-3 md:py-1.5 rounded-lg md:rounded-xl text-[10px] md:text-xs font-bold border border-rose-500/20"><span class="mr-1 hidden md:inline">🚫</span>${log.status.replace(sar, I18N.badge_reentry)}</span>`;
                    } else if (statusLower.includes(I18N.match_late)) {
                        statusBadge = `<span class="bg-rose-500/10 text-rose-600 dark:text-rose-400 px-2 py-1 md:px-3 md:py-1.5 rounded-lg md:rounded-xl text-[10px] md:text-xs font-bold border border-rose-500/20"><span class="mr-1 hidden md:inline">🔴</span>${log.status.replace(slp, I18N.badge_late)}</span>`;
                    } else if (statusLower.includes(I18N.match_sick) || statusLower.includes(I18N.match_released)) {
                        statusBadge = `<span class="bg-blue-500/10 text-blue-600 dark:text-blue-400 px-2 py-1 md:px-3 md:py-1.5 rounded-lg md:rounded-xl text-[10px] md:text-xs font-bold border border-blue-500/20"><span class="mr-1 hidden md:inline">ℹ️</span>${log.status}</span>`;
                    } else {
                        statusBadge = `<span class="bg-slate-500/10 text-slate-600 dark:text-slate-400 px-2 py-1 md:px-3 md:py-1.5 rounded-lg md:rounded-xl text-[10px] md:text-xs font-bold border border-slate-500/20"><span class="mr-1 hidden md:inline">🕒</span>${log.status}</span>`;
                    }

                    let classBadge = log.class_group && log.class_group !== I18N.class_unassigned ?
                        `<span class="bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded text-[10px] font-bold ml-2 shrink-0">${log.class_group}</span>` : '';

                    let nameHtml = log.name ?
                        `<div class="flex items-center w-28 md:w-auto"><div class="font-semibold text-slate-900 dark:text-white text-xs md:text-sm truncate">${log.name}</div>${classBadge}</div><div class="text-[9px] md:text-xs text-slate-500 font-mono mt-0.5">${log.uid}</div>` :
                        `<form action="/api/add_user" method="POST" class="flex flex-col md:flex-row md:items-center gap-1 md:gap-2">
                            <input type="hidden" name="uid" value="${log.uid}">
                            <input type="text" name="name" placeholder="${I18N.ph_name_quick}" required class="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-[10px] md:text-xs rounded px-2 py-1 outline-none w-full md:w-24">
                            <select name="class_group" class="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-[10px] md:text-xs rounded px-1 py-1 outline-none">${classOptions}</select>
                            <button type="submit" class="text-white bg-blue-600 rounded text-[10px] md:text-xs px-2 py-1">${I18N.btn_ok}</button>
                         </form>`;

                    let tr = `
                    <tr class="border-b border-slate-200/60 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors">
                        <td class="px-3 py-3 md:px-6 md:py-4 whitespace-nowrap font-medium text-slate-900 dark:text-slate-200 text-xs md:text-sm">${log.scan_time.split(' ')[1]} <span class="text-[9px] md:text-xs text-slate-400 font-normal ml-1 block md:inline">${log.scan_time.split(' ')[0]}</span></td>
                        <td class="hidden sm:table-cell px-3 py-3 md:px-6 md:py-4 text-slate-600 dark:text-slate-300 whitespace-nowrap text-xs md:text-sm">${log.room}</td>
                        <td class="px-3 py-3 md:px-6 md:py-4 text-xs md:text-sm max-w-[140px] md:max-w-xs">${nameHtml}</td>
                        <td class="px-3 py-3 md:px-6 md:py-4 whitespace-nowrap">${statusBadge}</td>
                        <td class="px-2 py-3 md:px-6 md:py-4 text-center">
                            <button onclick="hideLog(${log.id})" class="text-slate-400 hover:text-rose-500 p-2 text-lg leading-none" title="${I18N.btn_hide_title}">×</button>
                        </td>
                    </tr>`;
                    tbody.innerHTML += tr;
                });
            });
        }

        fetchLogs();

        const socket = io();
        socket.on('refresh_logs', function() {
            fetchLogs();
        });
{% endraw %}
    </script>
</body>
</html>
"""
)

# === Classes page ===
CLASSES_HTML = (
"""
<!DOCTYPE html>
<html lang="{{ t.html_lang }}" class="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{{ t.page_title_classes }}</title>
    {% raw %}
    <script>
        if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) { document.documentElement.classList.add('dark'); } else { document.documentElement.classList.remove('dark') }
    </script>
    {% endraw %}
    <script src="https://cdn.tailwindcss.com"></script>
    {% raw %}
    <script>tailwind.config = { darkMode: 'class', theme: { extend: {} } }</script>
    <style>
       .glass-panel { background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.3); }
       .dark .glass-panel { background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(255, 255, 255, 0.1); }
       details > summary { list-style: none; }
       details > summary::-webkit-details-marker { display: none; }
    </style>
    {% endraw %}
</head>
<body class="bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200 transition-colors duration-300 font-sans antialiased min-h-screen relative bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] pb-24 md:pb-12">
"""
+ NAV_HTML +
"""
    <div class="max-w-screen-md mx-auto pt-20 md:pt-24 px-3 md:px-4">
        <div class="flex flex-col md:flex-row md:justify-between md:items-center gap-4 mb-6">
            <h2 class="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">{{ t.classes_heading }}</h2>
            <div class="relative w-full md:w-64">
                <div class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                    <svg class="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                </div>
                <input type="text" id="searchInput" onkeyup="filterStudents()" placeholder="{{ t.search_placeholder }}" class="bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-sm rounded-xl pl-10 pr-4 py-2 outline-none w-full dark:text-white shadow-sm focus:ring-2 focus:ring-blue-500">
            </div>
        </div>

        <div class="flex flex-col gap-3">
            {% for class_name, students in grouped_users.items() %}
            <details class="glass-panel rounded-xl shadow-md group">
                <summary class="text-base md:text-lg font-bold p-4 text-slate-900 dark:text-white cursor-pointer flex justify-between items-center bg-slate-50/50 dark:bg-slate-800/30 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                    <div class="flex items-center gap-3">
                        {{ class_name }}
                        <span class="bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300 text-xs px-2 py-0.5 rounded-full font-semibold">{{ students|length }} {{ t.students_count }}</span>
                    </div>
                    <svg class="w-5 h-5 text-slate-400 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                </summary>
                <div class="flex flex-col px-2 md:px-4 pb-2 border-t border-slate-200/50 dark:border-slate-700/50">
                    {% for student in students %}
                    <div class="student-row flex flex-col md:flex-row md:items-center justify-between py-3 border-b border-slate-100 dark:border-slate-800 last:border-0" data-name="{{ student.name|lower }}">
                        <div class="mb-2 md:mb-0 flex items-baseline gap-2 px-2">
                            <span class="font-medium text-slate-800 dark:text-slate-200 text-sm">{{ student.name }}</span>
                            <span class="text-[10px] text-slate-400 font-mono">{{ student.uid }}</span>
                        </div>
                        <form action="/api/set_excuse" method="POST" class="flex gap-2 px-2 md:px-0">
                            <input type="hidden" name="uid" value="{{ student.uid }}">
                            <button type="submit" name="excuse" value="{{ canon.excuse_sick }}" class="flex-1 md:flex-none text-amber-700 bg-amber-100 active:scale-95 hover:bg-amber-200 dark:text-amber-400 dark:bg-amber-900/40 font-medium rounded-lg text-xs px-3 py-1.5 transition-colors border border-amber-200 dark:border-amber-800/50 shadow-sm flex justify-center items-center gap-1.5">
                                🏥 <span class="md:inline">{{ t.btn_sick_label }}</span>
                            </button>
                            <button type="submit" name="excuse" value="{{ canon.excuse_released }}" class="flex-1 md:flex-none text-blue-700 bg-blue-100 active:scale-95 hover:bg-blue-200 dark:text-blue-400 dark:bg-blue-900/40 font-medium rounded-lg text-xs px-3 py-1.5 transition-colors border border-blue-200 dark:border-blue-800/50 shadow-sm flex justify-center items-center gap-1.5">
                                ✈️ <span class="md:inline">{{ t.btn_released_label }}</span>
                            </button>
                        </form>
                    </div>
                    {% endfor %}
                </div>
            </details>
            {% endfor %}
        </div>
    </div>

    <script>
{% raw %}
        function filterStudents() {
            const term = document.getElementById('searchInput').value.toLowerCase();
            const detailsElements = document.querySelectorAll('details');
            document.querySelectorAll('.student-row').forEach(row => {
                const name = row.getAttribute('data-name');
                if(name.includes(term)) { row.style.display = ''; }
                else { row.style.display = 'none'; }
            });
            detailsElements.forEach(detail => {
                if (term.length > 0) { detail.setAttribute('open', ''); }
                else { detail.removeAttribute('open'); }
            });
        }
{% endraw %}
    </script>
</body>
</html>
"""
)

# === Stats page ===
STATS_HTML = (
"""
<!DOCTYPE html>
<html lang="{{ t.html_lang }}" class="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{{ t.page_title_stats }}</title>
    {% raw %}
    <script>
        if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) { document.documentElement.classList.add('dark'); } else { document.documentElement.classList.remove('dark') }
    </script>
    {% endraw %}
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    {% raw %}
    <script>tailwind.config = { darkMode: 'class', theme: { extend: {} } }</script>
    <style>
       .glass-panel { background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.3); }
       .dark .glass-panel { background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(255, 255, 255, 0.1); }
    </style>
    {% endraw %}
</head>
<body class="bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200 transition-colors duration-300 font-sans antialiased min-h-screen relative bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] pb-24 md:pb-12">
"""
+ NAV_HTML +
"""
    <div class="max-w-screen-xl mx-auto pt-20 md:pt-24 px-3 md:px-4">
        <div class="glass-panel rounded-xl md:rounded-2xl shadow-lg p-4 md:p-6 mb-4 md:mb-6">
            <form action="/stats" method="GET" class="flex flex-col md:flex-row md:items-center gap-3 md:gap-4">
                <div class="flex items-center gap-2 w-full md:w-auto">
                    <input type="date" name="start_date" value="{{ start_date }}" class="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white text-sm rounded-xl px-3 py-2 outline-none flex-1">
                    <span class="text-slate-500">—</span>
                    <input type="date" name="end_date" value="{{ end_date }}" class="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white text-sm rounded-xl px-3 py-2 outline-none flex-1">
                </div>
                <button type="submit" class="w-full md:w-auto text-white bg-blue-600 hover:bg-blue-700 font-medium rounded-xl text-sm px-6 py-2 shadow-md active:scale-95 transition-transform">{{ t.stats_filter }}</button>
            </form>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-6 mb-4 md:mb-6">
            <div class="glass-panel rounded-xl p-4 shadow-md text-center">
                <p class="text-[10px] md:text-sm font-medium text-slate-500">{{ t.stats_total_logs }}</p>
                <p class="text-xl md:text-3xl font-bold text-slate-800 dark:text-white">{{ total_logs }}</p>
            </div>
            <div class="glass-panel rounded-xl p-4 shadow-md text-center">
                <p class="text-[10px] md:text-sm font-medium text-slate-500">{{ t.stats_punctuality }}</p>
                <p class="text-xl md:text-3xl font-bold text-slate-800 dark:text-white">{{ punctuality }}%</p>
            </div>
            <div class="glass-panel rounded-xl p-4 shadow-md text-center">
                <p class="text-[10px] md:text-sm font-medium text-slate-500">{{ t.stats_late }}</p>
                <p class="text-xl md:text-3xl font-bold text-slate-800 dark:text-white">{{ late }}</p>
            </div>
            <div class="glass-panel rounded-xl p-4 shadow-md text-center">
                <p class="text-[10px] md:text-sm font-medium text-slate-500">{{ t.stats_excused_short }}</p>
                <p class="text-xl md:text-3xl font-bold text-slate-800 dark:text-white">{{ excused }}</p>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
            <div class="glass-panel rounded-xl md:rounded-2xl shadow-lg p-4 md:p-6 lg:col-span-1">
                <h2 class="text-base md:text-lg font-bold mb-2 md:mb-4 text-slate-900 dark:text-white text-center">{{ t.stats_chart_discipline }}</h2>
                <div class="relative h-48 md:h-64 w-full flex justify-center">
                    <canvas id="ratioChart"></canvas>
                </div>
            </div>
            <div class="glass-panel rounded-xl md:rounded-2xl shadow-lg p-4 md:p-6 lg:col-span-2">
                <h2 class="text-base md:text-lg font-bold mb-2 md:mb-4 text-slate-900 dark:text-white text-center">{{ t.stats_chart_late_by_class }}</h2>
                <div class="relative h-48 md:h-64 w-full flex justify-center">
                    <canvas id="lateClassChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <script>
        const chartLateLabel = {{ chart_late_label | safe }};
        const ratioLabels = {{ chart_labels_ratio | safe }};
        const labels = {{ labels | safe }};
        const dataArr = {{ data | safe }};
        const onTimeCount = {{ on_time }};
        const lateCount = {{ late }};
{% raw %}
        const isDark = document.documentElement.classList.contains('dark');
        const chartColors = {
            light: { text: '#475569', grid: '#e2e8f0' },
            dark: { text: '#cbd5e1', grid: '#334155' }
        };

        const ctxBar = document.getElementById('lateClassChart').getContext('2d');
        let lateChart = new Chart(ctxBar, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: chartLateLabel,
                    data: dataArr,
                    backgroundColor: 'rgba(245, 158, 11, 0.8)',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, ticks: { stepSize: 1, color: isDark ? chartColors.dark.text : chartColors.light.text }, grid: { color: isDark ? chartColors.dark.grid : chartColors.light.grid } },
                    x: { ticks: { color: isDark ? chartColors.dark.text : chartColors.light.text, font: {size: 10} }, grid: { display: false } }
                }
            }
        });

        const ctxDoughnut = document.getElementById('ratioChart').getContext('2d');
        let ratioChart = new Chart(ctxDoughnut, {
            type: 'doughnut',
            data: {
                labels: ratioLabels,
                datasets: [{
                    data: [onTimeCount, lateCount],
                    backgroundColor: ['#10b981', '#f59e0b'],
                    borderWidth: 0,
                    cutout: '70%'
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { color: isDark ? chartColors.dark.text : chartColors.light.text, font: {size: 10} } } }
            }
        });

        function updateChartTheme(theme) {
            lateChart.options.scales.x.ticks.color = chartColors[theme].text;
            lateChart.options.scales.y.ticks.color = chartColors[theme].text;
            lateChart.options.scales.y.grid.color = chartColors[theme].grid;
            lateChart.update();
            ratioChart.options.plugins.legend.labels.color = chartColors[theme].text;
            ratioChart.update();
        }
{% endraw %}
    </script>
</body>
</html>
"""
)
# === Settings page ===
SETTINGS_HTML = (
"""
<!DOCTYPE html>
<html lang="{{ t.html_lang }}" class="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{{ t.page_title_settings }}</title>
    {% raw %}
    <script>if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) { document.documentElement.classList.add('dark'); } else { document.documentElement.classList.remove('dark') }</script>
    {% endraw %}
    <script src="https://cdn.tailwindcss.com"></script>
    {% raw %}
    <script>tailwind.config = { darkMode: 'class', theme: { extend: {} } }</script>
    <style>
       .glass-panel { background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.3); }
       .dark .glass-panel { background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(255, 255, 255, 0.1); }
    </style>
    {% endraw %}
</head>
<body class="bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200 transition-colors duration-300 font-sans antialiased min-h-screen relative bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] pb-24 md:pb-12">
"""
+ NAV_HTML +
"""
    <div class="max-w-screen-md mx-auto pt-20 md:pt-24 px-3 md:px-4">
        <h2 class="text-xl md:text-2xl font-bold text-slate-900 dark:text-white mb-6 flex items-center gap-2">
            ⚙️ {{ t.settings_heading }}
        </h2>

        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        <div class="mb-6 space-y-2">
            {% for category, message in messages %}
            <div role="alert" class="rounded-xl px-4 py-3 text-sm font-medium border
                {% if category == 'error' %}border-rose-300 bg-rose-50 text-rose-900 dark:border-rose-700 dark:bg-rose-950/50 dark:text-rose-100
                {% elif category == 'success' %}border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-100
                {% else %}border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-100{% endif %}">{{ message }}</div>
            {% endfor %}
        </div>
        {% endif %}
        {% endwith %}

        <div class="glass-panel rounded-xl md:rounded-2xl shadow-lg p-6 mb-6">
            <h3 class="text-lg font-bold mb-4 text-slate-900 dark:text-white border-b border-slate-200 dark:border-slate-700 pb-2">⏰ {{ t.settings_bell_title }}</h3>
            <form action="/api/update_schedule" method="POST" class="flex flex-col gap-4">
                <div>
                    <label class="text-sm font-semibold text-slate-500 uppercase block mb-2">{{ t.settings_first_lesson_label }}</label>
                    <input type="time" name="lesson_start" value="{{ lesson_start }}" required class="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-900 text-lg rounded-xl px-4 py-3 dark:text-white outline-none w-full max-w-xs font-mono focus:ring-2 focus:ring-blue-500 transition-all">
                </div>
                <button type="submit" class="w-full max-w-xs text-white bg-blue-600 hover:bg-blue-700 font-medium rounded-xl text-sm px-5 py-3 shadow-md active:scale-95 transition-transform">
                    {{ t.settings_save }}
                </button>
            </form>
        </div>

        <div class="glass-panel rounded-xl md:rounded-2xl shadow-lg p-6 mb-6">
            <h3 class="text-lg font-bold mb-2 text-slate-900 dark:text-white border-b border-slate-200 dark:border-slate-700 pb-2">📚 {{ t.settings_promote_title }}</h3>
            <p class="text-sm text-slate-600 dark:text-slate-400 mb-4">{{ t.settings_promote_desc }}</p>
            <form action="/api/promote_class" method="POST" class="flex flex-col gap-4">
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label class="text-sm font-semibold text-slate-500 uppercase block mb-2">{{ t.settings_promote_from }}</label>
                        <select name="from_class" required class="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white text-sm rounded-xl px-3 py-2 outline-none w-full">
                            {% for c in classes %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label class="text-sm font-semibold text-slate-500 uppercase block mb-2">{{ t.settings_promote_to }}</label>
                        <select name="to_class" required class="bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white text-sm rounded-xl px-3 py-2 outline-none w-full">
                            {% for c in classes %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
                        </select>
                    </div>
                </div>
                <label class="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
                    <input type="checkbox" name="confirm" value="1" required class="mt-1 rounded border-slate-300 dark:border-slate-600">
                    <span>{{ t.settings_promote_confirm_label }}</span>
                </label>
                <button type="submit" class="w-full sm:w-auto text-white bg-amber-600 hover:bg-amber-700 font-medium rounded-xl text-sm px-5 py-3 shadow-md active:scale-95 transition-transform">
                    {{ t.settings_promote_submit }}
                </button>
            </form>
        </div>

    </div>
</body>
</html>
"""
)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f'''CREATE TABLE IF NOT EXISTS users (uid TEXT PRIMARY KEY, name TEXT, class_group TEXT DEFAULT '{CANONICAL["class_unassigned"]}')''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, room TEXT, status TEXT, scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (name TEXT, chat_id INTEGER, PRIMARY KEY(name, chat_id))''')
    
    # === НОВІ РЯДКИ ДЛЯ РОЗКЛАДУ ===
    c.execute('''CREATE TABLE IF NOT EXISTS settings (setting_name TEXT PRIMARY KEY, setting_value TEXT)''')
    c.execute('''INSERT OR IGNORE INTO settings (setting_name, setting_value) VALUES ('lesson_start', '08:30')''')
    # ==============================

    c.execute('''CREATE TABLE IF NOT EXISTS google_users (
        google_id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        display_name TEXT,
        card_uid TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS mobile_sessions (
        token TEXT PRIMARY KEY,
        google_id TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY (google_id) REFERENCES google_users(google_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS nfc_bind_sessions (
        id TEXT PRIMARY KEY,
        google_id TEXT NOT NULL,
        status TEXT DEFAULT 'waiting',
        bound_uid TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_nfc_scans (
        uid TEXT PRIMARY KEY,
        scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS nfc_uid_aliases (
        hw_uid TEXT PRIMARY KEY,
        card_uid TEXT NOT NULL,
        google_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS scan_prep_sessions (
        id TEXT PRIMARY KEY,
        google_id TEXT NOT NULL,
        card_uid TEXT NOT NULL,
        status TEXT DEFAULT 'waiting',
        matched_hw_uid TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL
    )''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def _cleanup_mobile_tables(conn):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('DELETE FROM mobile_sessions WHERE expires_at < ?', (now,))
    conn.execute('DELETE FROM nfc_bind_sessions WHERE expires_at < ?', (now,))
    conn.execute('DELETE FROM scan_prep_sessions WHERE expires_at < ?', (now,))
    conn.execute(
        "DELETE FROM pending_nfc_scans WHERE scanned_at < datetime('now', '-2 minutes')"
    )


def _record_pending_nfc_scan(conn, hw_uid):
    conn.execute(
        'INSERT OR REPLACE INTO pending_nfc_scans (uid, scanned_at) VALUES (?, datetime("now"))',
        (hw_uid.upper(),),
    )
    conn.commit()


def _resolve_scan_identity(conn, hw_uid):
    """hw_uid з ESP32 → стабільний card_uid для журналу."""
    hw_uid = hw_uid.upper()

    user = conn.execute(
        'SELECT name, class_group FROM users WHERE uid = ?', (hw_uid,)
    ).fetchone()
    if user:
        return hw_uid, user

    alias = conn.execute(
        'SELECT card_uid FROM nfc_uid_aliases WHERE hw_uid = ?', (hw_uid,)
    ).fetchone()
    if alias:
        card_uid = alias['card_uid'].upper()
        user = conn.execute(
            'SELECT name, class_group FROM users WHERE uid = ?', (card_uid,)
        ).fetchone()
        if user:
            return card_uid, user

    prep = conn.execute(
        '''SELECT id, card_uid, google_id FROM scan_prep_sessions
           WHERE status = 'waiting' AND expires_at >= datetime('now')
           ORDER BY created_at ASC LIMIT 1'''
    ).fetchone()
    if prep:
        card_uid = prep['card_uid'].upper()
        user = conn.execute(
            'SELECT name, class_group FROM users WHERE uid = ?', (card_uid,)
        ).fetchone()
        conn.execute(
            "UPDATE scan_prep_sessions SET status = 'used', matched_hw_uid = ? WHERE id = ?",
            (hw_uid, prep['id']),
        )
        conn.execute(
            '''INSERT OR REPLACE INTO nfc_uid_aliases (hw_uid, card_uid, google_id)
               VALUES (?, ?, ?)''',
            (hw_uid, card_uid, prep['google_id']),
        )
        conn.commit()
        return card_uid, user

    return hw_uid, None


def verify_google_id_token(id_token):
    if not GOOGLE_CLIENT_ID:
        raise ValueError('GOOGLE_CLIENT_ID is not configured on server')
    url = f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}'
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        try:
            err_json = json.loads(err_body)
            desc = err_json.get('error_description') or err_json.get('error', err_body)
        except json.JSONDecodeError:
            desc = err_body or str(e)
        raise ValueError(f'Google token invalid: {desc}') from e

    token_aud = data.get('aud', '')
    if token_aud != GOOGLE_CLIENT_ID:
        raise ValueError(
            f'Invalid Google token audience. Expected {GOOGLE_CLIENT_ID}, got {token_aud}. '
            'Use Web Client ID (not Android) in GOOGLE_CLIENT_ID and GOOGLE_WEB_CLIENT_ID.'
        )
    verified = data.get('email_verified')
    if str(verified).lower() not in ('true', '1'):
        raise ValueError('Google email is not verified')
    return data


def create_mobile_session(conn, google_id):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(hours=MOBILE_TOKEN_TTL_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        'INSERT INTO mobile_sessions (token, google_id, expires_at) VALUES (?, ?, ?)',
        (token, google_id, expires_at),
    )
    return token, expires_at


def get_google_user_from_token(conn, auth_header):
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None
    _cleanup_mobile_tables(conn)
    row = conn.execute(
        '''SELECT g.google_id, g.email, g.display_name, g.card_uid
           FROM mobile_sessions s
           JOIN google_users g ON g.google_id = s.google_id
           WHERE s.token = ? AND s.expires_at >= datetime('now')''',
        (token,),
    ).fetchone()
    return row


def requires_mobile_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        conn = get_db_connection()
        user = get_google_user_from_token(conn, request.headers.get('Authorization'))
        if not user:
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 401
        g.mobile_user = user
        g.mobile_conn = conn
        try:
            return f(*args, **kwargs)
        finally:
            conn.close()
    return decorated


@app.route('/')
@requires_auth
def index():
    conn = get_db_connection()
    users_raw = conn.execute('SELECT * FROM users ORDER BY class_group, name').fetchall()
    
    # Отримуємо поточний розклад із бази. Якщо його ще немає - ставимо 08:30
    setting = conn.execute("SELECT setting_value FROM settings WHERE setting_name = 'lesson_start'").fetchone()
    lesson_start = setting['setting_value'] if setting else "08:30"
    
    conn.close()
    users_json = json.dumps([dict(u) for u in users_raw]) 
    
    class_options = ''.join(f'<option value="{c}">{c}</option>' for c in CLASSES)
    return render_template_string(
        HTML_PAGE,
        users_json=users_json,
        classes=CLASSES,
        lesson_start=lesson_start,
        t=t_dict(),
        i18n_obj=build_index_i18n_obj(),
        class_options=class_options,
    )

@app.route('/classes')
@requires_auth
def classes_page():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users ORDER BY class_group, name').fetchall()
    conn.close()
    
    grouped_users = {}
    for u in users:
        cg = u['class_group']
        if cg not in grouped_users:
            grouped_users[cg] = []
        grouped_users[cg].append(u)
        
    cu = CANONICAL['class_unassigned']
    sorted_groups = {k: grouped_users[k] for k in sorted(grouped_users.keys(), key=lambda x: (x != cu, x))}

    return render_template_string(CLASSES_HTML, grouped_users=sorted_groups, t=t_dict(), canon=CANONICAL)

@app.route('/api/set_excuse', methods=['POST'])
@requires_auth
def set_excuse():
    uid = request.form.get('uid')
    excuse = request.form.get('excuse')
    if uid and excuse:
        conn = get_db_connection()
        conn.execute('INSERT INTO logs (uid, room, status) VALUES (?, ?, ?)', (uid, CANONICAL['room_system'], excuse))
        conn.commit()
        conn.close()
        socketio.emit('refresh_logs') # Оновлюємо таблиці в реальному часі
    return redirect(url_for('classes_page'))

@app.route('/stats')
@requires_auth
def stats():
    today_str = datetime.now().strftime('%Y-%m-%d')
    start_date = request.args.get('start_date', today_str)
    end_date = request.args.get('end_date', today_str)
    
    start_time = f"{start_date} 00:00:00"
    end_time = f"{end_date} 23:59:59"
    
    conn = get_db_connection()
    
    late_like = f"%{CANONICAL['sql_like_late']}%"
    allowed_like = f"%{CANONICAL['sql_like_allowed']}%"
    cu = CANONICAL['class_unassigned']
    sick = CANONICAL['excuse_sick']
    rel = CANONICAL['excuse_released']

    late_stats = conn.execute(f'''
        SELECT COALESCE(users.class_group, ?) as class_group, COUNT(logs.id) as late_count 
        FROM logs 
        LEFT JOIN users ON logs.uid = users.uid 
        WHERE logs.status LIKE ? AND logs.scan_time BETWEEN ? AND ?
        GROUP BY class_group 
        ORDER BY late_count DESC
    ''', (cu, late_like, start_time, end_time)).fetchall()
    
    total_logs = conn.execute('SELECT COUNT(*) as c FROM logs WHERE scan_time BETWEEN ? AND ?', (start_time, end_time)).fetchone()['c']
    on_time = conn.execute("SELECT COUNT(*) as c FROM logs WHERE status LIKE ? AND scan_time BETWEEN ? AND ?", (allowed_like, start_time, end_time)).fetchone()['c']
    late = conn.execute("SELECT COUNT(*) as c FROM logs WHERE status LIKE ? AND scan_time BETWEEN ? AND ?", (late_like, start_time, end_time)).fetchone()['c']
    excused = conn.execute("SELECT COUNT(*) as c FROM logs WHERE (status = ? OR status = ?) AND scan_time BETWEEN ? AND ?", (sick, rel, start_time, end_time)).fetchone()['c']
    
    conn.close()

    punctuality = 0
    if (on_time + late) > 0:
        punctuality = round((on_time / (on_time + late)) * 100, 1)

    labels = [row['class_group'] for row in late_stats]
    data = [row['late_count'] for row in late_stats]

    return render_template_string(
        STATS_HTML, 
        labels=json.dumps(labels), 
        data=json.dumps(data),
        start_date=start_date,
        end_date=end_date,
        total_logs=total_logs,
        on_time=on_time,
        late=late,
        excused=excused,
        punctuality=punctuality,
        t=t_dict(),
        chart_late_label=json.dumps(gettext('chart_late_count_label')),
        chart_labels_ratio=json.dumps([gettext('chart_ratio_ontime'), gettext('chart_ratio_late')]),
    )

@app.route('/api/scan', methods=['GET'])
def scan_card():
    scan_lang = parse_accept_language(request.headers.get('Accept-Language'))

    uid = request.args.get('uid')
    token = request.args.get('token')
    signature = request.args.get('signature')

    if not token or token not in HARDWARE_TOKENS:
        return gettext('scan_denied_invalid_token', scan_lang), 401
    if not uid:
        return gettext('scan_denied_missing_uid', scan_lang), 400

    if not signature:
        return gettext('scan_denied_missing_signature', scan_lang), 403

    message = f"{uid}:{token}".encode('utf-8')
    expected_signature = hmac.new(HMAC_SECRET.encode('utf-8'), message, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_signature.lower(), signature.lower()):
        print(gettext_fmt('log_spoof_attempt', lang=scan_lang, uid=uid))
        return gettext('scan_denied_invalid_signature', scan_lang), 403

    offset_sec = request.args.get('offset', type=int, default=0)

    room = HARDWARE_TOKENS[token]
    hw_uid = uid.upper()

    conn = get_db_connection()
    uid, user = _resolve_scan_identity(conn, hw_uid)
    if not user:
        _record_pending_nfc_scan(conn, hw_uid)
        conn.close()
        return gettext('scan_denied_unknown_card', scan_lang), 403

    now = datetime.now() - timedelta(seconds=offset_sec)

    today_str = now.strftime('%Y-%m-%d')

    last_log = conn.execute('''
        SELECT status FROM logs 
        WHERE uid = ? AND scan_time >= ? 
        ORDER BY scan_time DESC LIMIT 1
    ''', (uid, today_str)).fetchone()

    is_inside = False
    if last_log:
        last_status = last_log['status']
        if (
            CANONICAL['substring_entry'] in last_status
            or CANONICAL['substring_late'] in last_status
            or CANONICAL['status_anomaly_reentry'] in last_status
        ):
            is_inside = True

    current_mins = now.hour * 60 + now.minute
    status = ""

    if token == "TOKEN_ENTRY":
        if is_inside:
            status = CANONICAL['status_anomaly_reentry']
        else:
            status = CANONICAL['status_off_schedule']
            is_second_shift = user and user['class_group'] and user['class_group'].startswith(('6-', '10-'))

            if is_second_shift:
                shift_start_mins = 12 * 60 + 30
                relevant_lessons = LESSONS[4:]
            else:
                shift_start_mins = 8 * 60
                relevant_lessons = LESSONS

            shift_end_mins = max(int(l["end"].split(':')[0]) * 60 + int(l["end"].split(':')[1]) for l in relevant_lessons)

            if current_mins <= shift_start_mins:
                status = CANONICAL['status_entry_allowed']
            elif current_mins > shift_end_mins + 60:
                status = CANONICAL['status_off_schedule']
            else:
                is_break = True
                for lesson in relevant_lessons:
                    start_h, start_m = map(int, lesson["start"].split(':'))
                    end_h, end_m = map(int, lesson["end"].split(':'))
                    start_mins = start_h * 60 + start_m
                    end_mins = end_h * 60 + end_m

                    if start_mins < current_mins <= end_mins:
                        late = current_mins - start_mins
                        status = (
                            f"{CANONICAL['status_late_prefix']} {late} {CANONICAL['status_late_suffix']} "
                            f"({lesson['num']} {CANONICAL['status_late_lesson_word']})"
                        )
                        is_break = False
                        break
                    elif current_mins == start_mins:
                        status = CANONICAL['status_entry_allowed']
                        is_break = False
                        break

                if is_break:
                    status = CANONICAL['status_entry_break']

    elif token == "TOKEN_EXIT":
        if not is_inside:
            status = CANONICAL['status_anomaly_exit_no_entry']
        else:
            status = CANONICAL['status_exit']

    conn.execute('INSERT INTO logs (uid, room, status) VALUES (?,?,?)', (uid, room, status))
    conn.commit()

    if user:
        name = user['name']
        subs = conn.execute('SELECT chat_id FROM subscriptions WHERE name = ?', (name,)).fetchall()
        if subs:
            chat_ids = [sub['chat_id'] for sub in subs]
            if CANONICAL['status_exit'] in status:
                action_icon = "🔴"
            elif CANONICAL['substring_entry'] in status or 'Запізн' in status:
                action_icon = "🟢"
            else:
                action_icon = "⚠️"

            msg_text = (
                f"{action_icon} **{gettext('telegram_line_title', scan_lang)}**\n"
                f"👤 {gettext('telegram_line_student', scan_lang)} {name}\n"
                f"📍 {gettext('telegram_line_location', scan_lang)} {room}\n"
                f"🕒 {gettext('telegram_line_time', scan_lang)} {now.strftime('%H:%M:%S')}\n"
                f"📊 {gettext('telegram_line_status', scan_lang)} {status}"
            )

            telegram_queue.put((chat_ids, msg_text))

    conn.close()

    socketio.emit('refresh_logs')

    return f"OK: {uid}", 200

@app.route('/api/logs_json', methods=['GET'])
@requires_auth
def get_logs_json():
    conn = get_db_connection()
    # Изменили LIMIT 100 на LIMIT 1000 для корректной статистики за день
    logs = conn.execute('''SELECT logs.id, datetime(logs.scan_time, 'localtime') as scan_time, logs.uid, logs.room, logs.status, users.name, users.class_group FROM logs LEFT JOIN users ON logs.uid = users.uid ORDER BY logs.scan_time DESC LIMIT 1000''').fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in logs])

@app.route('/api/export_csv', methods=['GET'])
@requires_auth
def export_csv():
    conn = get_db_connection()
    unk = gettext('csv_unknown_name')
    logs = conn.execute(
        '''
        SELECT datetime(logs.scan_time, 'localtime') as col_date,
               logs.room as col_room,
               logs.uid as col_uid,
               COALESCE(users.name, ?) as col_name,
               COALESCE(users.class_group, '-') as col_class,
               logs.status as col_status
        FROM logs LEFT JOIN users ON logs.uid = users.uid ORDER BY logs.scan_time DESC
        ''',
        (unk,),
    ).fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si, dialect='excel', delimiter=';')
    cw.writerow([
        gettext('csv_col_date'),
        gettext('csv_col_room'),
        gettext('csv_col_uid'),
        gettext('csv_col_name'),
        gettext('csv_col_class'),
        gettext('csv_col_status'),
    ])
    for row in logs:
        cw.writerow([row['col_date'], row['col_room'], row['col_uid'], row['col_name'], row['col_class'], row['col_status']])
    output = Response(si.getvalue().encode('utf-8-sig'), mimetype='text/csv')
    output.headers['Content-Disposition'] = f"attachment; filename=log_{datetime.now().strftime('%Y%m%d')}.csv"
    return output

@app.route('/api/update_schedule', methods=['POST'])
@requires_auth
def update_schedule():
    new_time = request.form.get('lesson_start')
    if new_time:
        conn = get_db_connection()
        # Зберігаємо новий час у таблицю settings
        conn.execute("REPLACE INTO settings (setting_name, setting_value) VALUES ('lesson_start', ?)", (new_time,))
        conn.commit()
        conn.close()
    # Після збереження просто перезавантажуємо головну сторінку
    return redirect(url_for('settings_page'))


@app.route('/api/promote_class', methods=['POST'])
@requires_auth
def promote_class():
    if request.form.get('confirm') != '1':
        flash(gettext('promote_err_confirm'), 'error')
        return redirect(url_for('settings_page'))
    from_c = (request.form.get('from_class') or '').strip()
    to_c = (request.form.get('to_class') or '').strip()
    if from_c not in CLASSES or to_c not in CLASSES:
        flash(gettext('promote_err_invalid'), 'error')
        return redirect(url_for('settings_page'))
    if from_c == to_c:
        flash(gettext('promote_err_same'), 'error')
        return redirect(url_for('settings_page'))
    conn = get_db_connection()
    n = conn.execute('SELECT COUNT(*) AS c FROM users WHERE class_group = ?', (from_c,)).fetchone()['c']
    conn.execute('UPDATE users SET class_group = ? WHERE class_group = ?', (to_c, from_c))
    conn.commit()
    conn.close()
    socketio.emit('refresh_logs')
    if n == 0:
        flash(gettext('promote_ok_zero'), 'info')
    else:
        flash(gettext_fmt('promote_ok', count=n), 'success')
    return redirect(url_for('settings_page'))


@app.route('/settings')
@requires_auth
def settings_page():
    conn = get_db_connection()
    setting = conn.execute("SELECT setting_value FROM settings WHERE setting_name = 'lesson_start'").fetchone()
    lesson_start = setting['setting_value'] if setting else "08:30"
    conn.close()
    
    return render_template_string(SETTINGS_HTML, lesson_start=lesson_start, t=t_dict(), classes=CLASSES)
 
@app.route('/api/add_user', methods=['POST'])
@requires_auth
def add_user():
    uid = request.form.get('uid').strip().upper()
    name = request.form.get('name').strip()
    class_group = request.form.get('class_group', CANONICAL['class_unassigned']).strip()
    conn = get_db_connection()
    conn.execute('REPLACE INTO users (uid, name, class_group) VALUES (?,?,?)', (uid, name, class_group))
    conn.commit()
    conn.close()
    socketio.emit('refresh_logs')
    return redirect(url_for('index'))

@app.route('/api/delete_user/<uid>', methods=['GET'])
@requires_auth
def delete_user(uid):
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE uid = ?', (uid,))
    conn.commit()
    conn.close()
    socketio.emit('refresh_logs')
    return redirect(url_for('index'))


# === Mobile API (Android app) ===

@app.route('/api/mobile/auth/google', methods=['POST'])
def mobile_auth_google():
    data = request.get_json(silent=True) or {}
    id_token = data.get('id_token', '').strip()
    if not id_token:
        return jsonify({'error': 'id_token is required'}), 400
    try:
        google_data = verify_google_id_token(id_token)
    except Exception as e:
        return jsonify({'error': str(e)}), 401

    google_id = google_data['sub']
    email = google_data.get('email', '')
    display_name = google_data.get('name', email)

    conn = get_db_connection()
    _cleanup_mobile_tables(conn)
    conn.execute(
        '''INSERT INTO google_users (google_id, email, display_name)
           VALUES (?, ?, ?)
           ON CONFLICT(google_id) DO UPDATE SET
             email = excluded.email,
             display_name = excluded.display_name''',
        (google_id, email, display_name),
    )
    session_token, expires_at = create_mobile_session(conn, google_id)
    user = conn.execute(
        'SELECT card_uid FROM google_users WHERE google_id = ?', (google_id,)
    ).fetchone()
    card_uid = user['card_uid'] if user else None
    class_group = _user_class_group(conn, card_uid)
    conn.commit()
    conn.close()

    return jsonify({
        'token': session_token,
        'expires_at': expires_at,
        'email': email,
        'display_name': display_name,
        'has_card': bool(card_uid),
        'card_uid': card_uid,
        'class_group': class_group,
    })


def _user_class_group(conn, card_uid):
    if not card_uid:
        return CANONICAL['class_unassigned']
    row = conn.execute(
        'SELECT class_group FROM users WHERE uid = ?', (card_uid.upper(),)
    ).fetchone()
    return row['class_group'] if row else CANONICAL['class_unassigned']



@app.route('/api/mobile/me', methods=['GET'])
@requires_mobile_auth
def mobile_me():
    user = g.mobile_user
    conn = g.mobile_conn
    class_group = _user_class_group(conn, user['card_uid'])
    return jsonify({
        'email': user['email'],
        'display_name': user['display_name'],
        'has_card': bool(user['card_uid']),
        'card_uid': user['card_uid'],
        'class_group': class_group,
    })


@app.route('/api/mobile/card', methods=['POST'])
@requires_mobile_auth
def mobile_create_card():
    user = g.mobile_user
    conn = g.mobile_conn

    if user['card_uid']:
        return jsonify({'error': 'Card already exists', 'card_uid': user['card_uid']}), 409

    class_group = CANONICAL['class_unassigned']

    card_uid = secrets.token_hex(4).upper()
    display_name = user['display_name'] or user['email']

    conn.execute(
        'UPDATE google_users SET card_uid = ? WHERE google_id = ?',
        (card_uid, user['google_id']),
    )
    conn.execute(
        'INSERT INTO users (uid, name, class_group) VALUES (?, ?, ?) '
        'ON CONFLICT(uid) DO UPDATE SET name = excluded.name, class_group = excluded.class_group',
        (card_uid, display_name, class_group),
    )
    conn.commit()
    socketio.emit('refresh_logs')

    return jsonify({
        'card_uid': card_uid,
        'display_name': display_name,
        'class_group': class_group,
        'message': 'Virtual card created. Tap Pass button in app, then hold phone to reader.',
    }), 201



@app.route('/api/purge_unknown_logs', methods=['POST'])
@requires_auth
def purge_unknown_logs():
    conn = get_db_connection()
    deleted = conn.execute(
        'DELETE FROM logs WHERE uid NOT IN (SELECT uid FROM users)'
    ).rowcount
    conn.commit()
    conn.close()
    socketio.emit('refresh_logs')
    return jsonify({'deleted': deleted})


@app.route('/api/mobile/health', methods=['GET'])
def mobile_health():
    return jsonify({
        'ok': True,
        'api_version': 2,
        'features': ['scan_prep', 'nfc_bind', 'google_auth'],
    })


@app.route('/api/mobile/scan/prep', methods=['POST'])
@requires_mobile_auth
def mobile_scan_prep():
    user = g.mobile_user
    conn = g.mobile_conn

    if not user['card_uid']:
        return jsonify({'error': 'Create a card first'}), 400

    conn.execute(
        "DELETE FROM scan_prep_sessions WHERE google_id = ? AND status = 'waiting'",
        (user['google_id'],),
    )
    prep_id = str(uuid.uuid4())
    expires_at = (datetime.now() + timedelta(seconds=5)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        '''INSERT INTO scan_prep_sessions (id, google_id, card_uid, status, expires_at)
           VALUES (?, ?, ?, 'waiting', ?)''',
        (prep_id, user['google_id'], user['card_uid'].upper(), expires_at),
    )
    conn.commit()

    return jsonify({
        'prep_id': prep_id,
        'card_uid': user['card_uid'],
        'expires_at': expires_at,
        'instructions': 'Hold phone to ESP32 reader within 5 seconds.',
    })


@app.route('/api/mobile/scan/prep/status/<prep_id>', methods=['GET'])
@requires_mobile_auth
def mobile_scan_prep_status(prep_id):
    user = g.mobile_user
    conn = g.mobile_conn

    session = conn.execute(
        'SELECT * FROM scan_prep_sessions WHERE id = ? AND google_id = ?',
        (prep_id, user['google_id']),
    ).fetchone()
    if not session:
        return jsonify({'error': 'Prep session not found'}), 404

    if session['status'] == 'used':
        return jsonify({
            'status': 'used',
            'card_uid': session['card_uid'],
            'hw_uid': session['matched_hw_uid'],
        })

    if datetime.now() > datetime.strptime(session['expires_at'], '%Y-%m-%d %H:%M:%S'):
        conn.execute(
            "UPDATE scan_prep_sessions SET status = 'expired' WHERE id = ?", (prep_id,)
        )
        conn.commit()
        return jsonify({'status': 'expired'})

    return jsonify({'status': 'waiting', 'card_uid': session['card_uid']})


@app.route('/api/mobile/card/bind/start', methods=['POST'])
@requires_mobile_auth
def mobile_bind_start():
    user = g.mobile_user
    conn = g.mobile_conn

    if not user['card_uid']:
        return jsonify({'error': 'Create a card first'}), 400

    conn.execute(
        "DELETE FROM nfc_bind_sessions WHERE google_id = ? AND status = 'waiting'",
        (user['google_id'],),
    )
    bind_id = str(uuid.uuid4())
    expires_at = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        '''INSERT INTO nfc_bind_sessions (id, google_id, status, expires_at)
           VALUES (?, ?, 'waiting', ?)''',
        (bind_id, user['google_id'], expires_at),
    )
    conn.commit()

    return jsonify({
        'bind_id': bind_id,
        'card_uid': user['card_uid'],
        'expires_at': expires_at,
        'instructions': 'Hold phone to reader. NFC UID will be linked to your card (not replace it).',
    })


@app.route('/api/mobile/card/bind/status/<bind_id>', methods=['GET'])
@requires_mobile_auth
def mobile_bind_status(bind_id):
    user = g.mobile_user
    conn = g.mobile_conn

    session = conn.execute(
        'SELECT * FROM nfc_bind_sessions WHERE id = ? AND google_id = ?',
        (bind_id, user['google_id']),
    ).fetchone()
    if not session:
        return jsonify({'error': 'Bind session not found'}), 404

    if session['status'] == 'bound':
        return jsonify({
            'status': 'bound',
            'hw_uid': session['bound_uid'],
            'card_uid': user['card_uid'],
        })

    if datetime.now() > datetime.strptime(session['expires_at'], '%Y-%m-%d %H:%M:%S'):
        conn.execute(
            "UPDATE nfc_bind_sessions SET status = 'expired' WHERE id = ?", (bind_id,)
        )
        conn.commit()
        return jsonify({'status': 'expired'})

    pending = conn.execute(
        '''SELECT uid FROM pending_nfc_scans
           WHERE scanned_at >= datetime('now', '-2 minutes')
           ORDER BY scanned_at DESC LIMIT 1'''
    ).fetchone()

    if pending:
        hw_uid = pending['uid'].upper()
        card_uid = user['card_uid'].upper()

        conn.execute(
            '''INSERT OR REPLACE INTO nfc_uid_aliases (hw_uid, card_uid, google_id)
               VALUES (?, ?, ?)''',
            (hw_uid, card_uid, user['google_id']),
        )
        conn.execute(
            "UPDATE nfc_bind_sessions SET status = 'bound', bound_uid = ? WHERE id = ?",
            (hw_uid, bind_id),
        )
        conn.execute('DELETE FROM pending_nfc_scans WHERE uid = ?', (hw_uid,))
        conn.commit()

        return jsonify({
            'status': 'bound',
            'hw_uid': hw_uid,
            'card_uid': card_uid,
        })

    return jsonify({'status': 'waiting'})


@app.route('/api/mobile/card/reset', methods=['POST'])
@requires_mobile_auth
def mobile_reset_card():
    """Скинути картку, якщо раніше привʼязали випадковий NFC UID телефону."""
    user = g.mobile_user
    conn = g.mobile_conn

    old_uid = user['card_uid']
    card_uid = secrets.token_hex(4).upper()
    display_name = user['display_name'] or user['email']

    if old_uid:
        conn.execute('DELETE FROM users WHERE uid = ?', (old_uid,))
        conn.execute('DELETE FROM nfc_uid_aliases WHERE card_uid = ?', (old_uid,))

    conn.execute(
        'UPDATE google_users SET card_uid = ? WHERE google_id = ?',
        (card_uid, user['google_id']),
    )
    conn.execute(
        f'''INSERT INTO users (uid, name, class_group)
            VALUES (?, ?, '{CANONICAL["class_unassigned"]}')
            ON CONFLICT(uid) DO UPDATE SET name = excluded.name''',
        (card_uid, display_name),
    )
    conn.commit()
    socketio.emit('refresh_logs')

    return jsonify({
        'card_uid': card_uid,
        'display_name': display_name,
        'message': 'New virtual card issued.',
    })


@app.route('/api/mobile/logout', methods=['POST'])
@requires_mobile_auth
def mobile_logout():
    conn = g.mobile_conn
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:].strip() if auth_header.startswith('Bearer ') else ''
    if token:
        conn.execute('DELETE FROM mobile_sessions WHERE token = ?', (token,))
        conn.commit()
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()
    # Запуск сервера через socketio замість app.run
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)