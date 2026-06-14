from flask import Flask, request, render_template, redirect, url_for, jsonify, Response, g, session, flash
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

# Примусово встановлюємо часовий пояс Києва для всього скрипта
os.environ['TZ'] = 'Europe/Kyiv'
time.tzset()
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl

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

def get_current_user():
    username = session.get('web_user')
    if not username:
        return None
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM web_users WHERE username = ?', (username,)).fetchone()
    if not row:
        conn.close()
        return None
    classes = [r['class_group'] for r in conn.execute('SELECT class_group FROM teacher_classes WHERE username = ?', (username,)).fetchall()]
    conn.close()
    return {'username': row['username'], 'role': row['role'], 'display_name': row['display_name'], 'classes': classes}

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for('login_page'))
        g.web_user = user
        return f(*args, **kwargs)
    return decorated

def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for('login_page'))
        if user['role'] != 'admin':
            return "Forbidden: Admin only", 403
        g.web_user = user
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

    # === RBAC ===
    c.execute('''CREATE TABLE IF NOT EXISTS web_users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL, display_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS teacher_classes (username TEXT NOT NULL, class_group TEXT NOT NULL, PRIMARY KEY(username, class_group))''')
    
    # Create default admin if not exists
    admin_pw = generate_password_hash(ADMIN_PASS)
    c.execute("INSERT OR IGNORE INTO web_users (username, password_hash, role, display_name) VALUES (?, ?, 'admin', 'Адміністратор')", (ADMIN_LOGIN, admin_pw))
    # ============

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
           WHERE status = 'waiting' AND expires_at >= datetime('now', 'localtime')
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
           WHERE s.token = ? AND s.expires_at >= datetime('now', 'localtime')''',
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


LOGIN_HTML = """
<!DOCTYPE html>
<html lang="uk" class="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Вхід — Smart School</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
       .glass-panel { background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.3); }
    </style>
</head>
<body class="bg-slate-100 text-slate-800 font-sans antialiased min-h-screen flex items-center justify-center relative bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] px-4">
    <div class="glass-panel w-full max-w-md rounded-2xl shadow-xl p-6 md:p-8">
        <div class="flex justify-center mb-6">
            <div class="w-16 h-16 bg-white rounded-full flex items-center justify-center shadow-sm">
                <img src="/static/logo.png" alt="Logo" class="w-12 h-12 object-contain">
            </div>
        </div>
        <h2 class="text-2xl font-bold text-center text-slate-900 mb-6">Smart<span class="text-blue-600">School</span> Panel</h2>
        
        {% with messages = get_flashed_messages() %}
        {% if messages %}
        <div class="mb-4">
            {% for message in messages %}
            <div class="bg-rose-100 border border-rose-400 text-rose-700 px-4 py-3 rounded relative text-sm" role="alert">{{ message }}</div>
            {% endfor %}
        </div>
        {% endif %}
        {% endwith %}

        <form action="/login" method="POST" class="flex flex-col gap-4">
            <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">Логін</label>
                <input type="text" name="username" required class="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-xl px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">Пароль</label>
                <input type="password" name="password" required class="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-xl px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <button type="submit" class="w-full text-white bg-blue-600 hover:bg-blue-700 font-medium rounded-xl px-5 py-3 mt-2 shadow-md active:scale-95 transition-transform">Увійти</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM web_users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['web_user'] = username
            return redirect(url_for('index'))
        else:
            flash('Неправильний логін або пароль')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('web_user', None)
    return redirect(url_for('login_page'))


@app.route('/')
@requires_auth
def index():
    conn = get_db_connection()
    if g.web_user['role'] == 'admin':
        users_raw = conn.execute('SELECT * FROM users ORDER BY class_group, name').fetchall()
    else:
        classes = g.web_user['classes']
        if not classes:
            users_raw = []
        else:
            placeholders = ','.join('?' * len(classes))
            users_raw = conn.execute(f'SELECT * FROM users WHERE class_group IN ({placeholders}) ORDER BY class_group, name', classes).fetchall()
    
    # Отримуємо поточний розклад із бази. Якщо його ще немає - ставимо 08:30
    setting = conn.execute("SELECT setting_value FROM settings WHERE setting_name = 'lesson_start'").fetchone()
    lesson_start = setting['setting_value'] if setting else "08:30"
    
    conn.close()
    users_json = json.dumps([dict(u) for u in users_raw]) 
    
    class_options = ''.join(f'<option value="{c}">{c}</option>' for c in CLASSES)
    return render_template(
        'index.html',
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
    if g.web_user['role'] == 'admin':
        users = conn.execute('SELECT * FROM users ORDER BY class_group, name').fetchall()
    else:
        classes = g.web_user['classes']
        if not classes:
            users = []
        else:
            placeholders = ','.join('?' * len(classes))
            users = conn.execute(f'SELECT * FROM users WHERE class_group IN ({placeholders}) ORDER BY class_group, name', classes).fetchall()
    conn.close()
    
    grouped_users = {}
    for u in users:
        cg = u['class_group']
        if cg not in grouped_users:
            grouped_users[cg] = []
        grouped_users[cg].append(u)
        
    cu = CANONICAL['class_unassigned']
    sorted_groups = {k: grouped_users[k] for k in sorted(grouped_users.keys(), key=lambda x: (x != cu, x))}

    return render_template('classes.html', grouped_users=sorted_groups, t=t_dict(), canon=CANONICAL)

@app.route('/api/set_excuse', methods=['POST'])
@requires_auth
def set_excuse():
    uid = request.form.get('uid')
    excuse = request.form.get('excuse')
    if uid and excuse:
        conn = get_db_connection()
        if g.web_user['role'] == 'teacher':
            user = conn.execute("SELECT class_group FROM users WHERE uid = ?", (uid,)).fetchone()
            if not user or user['class_group'] not in g.web_user['classes']:
                conn.close()
                flash('Доступ заборонено', 'error')
                return redirect(url_for('classes_page'))
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

    if g.web_user['role'] == 'admin':
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
    else:
        classes = g.web_user['classes']
        if not classes:
            late_stats = []
            total_logs = on_time = late = excused = 0
        else:
            placeholders = ','.join('?' * len(classes))
            late_stats = conn.execute(f'''
                SELECT users.class_group, COUNT(logs.id) as late_count 
                FROM logs 
                JOIN users ON logs.uid = users.uid 
                WHERE logs.status LIKE ? AND logs.scan_time BETWEEN ? AND ? AND users.class_group IN ({placeholders})
                GROUP BY class_group 
                ORDER BY late_count DESC
            ''', (late_like, start_time, end_time, *classes)).fetchall()
            
            total_logs = conn.execute(f'SELECT COUNT(*) as c FROM logs JOIN users ON logs.uid = users.uid WHERE logs.scan_time BETWEEN ? AND ? AND users.class_group IN ({placeholders})', (start_time, end_time, *classes)).fetchone()['c']
            on_time = conn.execute(f"SELECT COUNT(*) as c FROM logs JOIN users ON logs.uid = users.uid WHERE logs.status LIKE ? AND logs.scan_time BETWEEN ? AND ? AND users.class_group IN ({placeholders})", (allowed_like, start_time, end_time, *classes)).fetchone()['c']
            late = conn.execute(f"SELECT COUNT(*) as c FROM logs JOIN users ON logs.uid = users.uid WHERE logs.status LIKE ? AND logs.scan_time BETWEEN ? AND ? AND users.class_group IN ({placeholders})", (late_like, start_time, end_time, *classes)).fetchone()['c']
            excused = conn.execute(f"SELECT COUNT(*) as c FROM logs JOIN users ON logs.uid = users.uid WHERE (logs.status = ? OR logs.status = ?) AND logs.scan_time BETWEEN ? AND ? AND users.class_group IN ({placeholders})", (sick, rel, start_time, end_time, *classes)).fetchone()['c']
    
    conn.close()

    punctuality = 0
    if (on_time + late) > 0:
        punctuality = round((on_time / (on_time + late)) * 100, 1)

    labels = [row['class_group'] for row in late_stats]
    data = [row['late_count'] for row in late_stats]

    return render_template(
        'stats.html', 
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
    # ESP32 не надсилає Accept-Language, тому за замовчуванням ставимо 'uk'
    header_lang = request.headers.get('Accept-Language')
    scan_lang = parse_accept_language(header_lang) if header_lang else 'uk'

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
    if g.web_user['role'] == 'admin':
        logs = conn.execute('''SELECT logs.id, datetime(logs.scan_time, 'localtime') as scan_time, logs.uid, logs.room, logs.status, users.name, users.class_group FROM logs LEFT JOIN users ON logs.uid = users.uid ORDER BY logs.scan_time DESC LIMIT 1000''').fetchall()
    else:
        classes = g.web_user['classes']
        if not classes:
            logs = []
        else:
            placeholders = ','.join('?' * len(classes))
            logs = conn.execute(f'''SELECT logs.id, datetime(logs.scan_time, 'localtime') as scan_time, logs.uid, logs.room, logs.status, users.name, users.class_group FROM logs JOIN users ON logs.uid = users.uid WHERE users.class_group IN ({placeholders}) ORDER BY logs.scan_time DESC LIMIT 1000''', classes).fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in logs])

@app.route('/api/export_csv', methods=['GET'])
@requires_auth
def export_csv():
    conn = get_db_connection()
    unk = gettext('csv_unknown_name')
    if g.web_user['role'] == 'admin':
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
    else:
        classes = g.web_user['classes']
        if not classes:
            logs = []
        else:
            placeholders = ','.join('?' * len(classes))
            logs = conn.execute(f'''
                SELECT datetime(logs.scan_time, 'localtime') as col_date,
                       logs.room as col_room,
                       logs.uid as col_uid,
                       users.name as col_name,
                       users.class_group as col_class,
                       logs.status as col_status
                FROM logs JOIN users ON logs.uid = users.uid WHERE users.class_group IN ({placeholders}) ORDER BY logs.scan_time DESC
                ''', classes).fetchall()
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
@requires_admin
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
@requires_admin
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
    
    web_users_list = []
    if g.web_user['role'] == 'admin':
        wu_raw = conn.execute('SELECT * FROM web_users').fetchall()
        for wu in wu_raw:
            classes = [r['class_group'] for r in conn.execute('SELECT class_group FROM teacher_classes WHERE username = ?', (wu['username'],)).fetchall()]
            web_users_list.append({
                'username': wu['username'],
                'display_name': wu['display_name'],
                'role': wu['role'],
                'classes': classes
            })
            
    conn.close()
    
    return render_template('settings.html', lesson_start=lesson_start, t=t_dict(), classes=CLASSES, web_users_list=web_users_list)
 
@app.route('/api/add_web_user', methods=['POST'])
@requires_admin
def add_web_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'teacher').strip()
    display_name = request.form.get('display_name', '').strip()
    classes = request.form.getlist('classes')
    
    if not username or not password:
        flash("Логін та пароль обов'язкові", 'error')
        return redirect(url_for('settings_page'))
        
    pw_hash = generate_password_hash(password)
    
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO web_users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)', 
                    (username, pw_hash, role, display_name))
        for c in classes:
            conn.execute('INSERT INTO teacher_classes (username, class_group) VALUES (?, ?)', (username, c))
        conn.commit()
        flash(f'Користувача {username} додано', 'success')
    except Exception as e:
        flash(f'Помилка створення користувача {username}', 'error')
    finally:
        conn.close()
        
    return redirect(url_for('settings_page'))

@app.route('/api/delete_web_user/<username>')
@requires_admin
def delete_web_user(username):
    if username == g.web_user['username']:
        flash('Не можна видалити самого себе', 'error')
        return redirect(url_for('settings_page'))
        
    conn = get_db_connection()
    conn.execute('DELETE FROM web_users WHERE username = ?', (username,))
    conn.execute('DELETE FROM teacher_classes WHERE username = ?', (username,))
    conn.commit()
    conn.close()
    flash(f'Користувача {username} видалено', 'success')
    return redirect(url_for('settings_page'))

@app.route('/api/upload_students', methods=['POST'])
@requires_auth
def upload_students():
    if 'file' not in request.files:
        flash('Немає файлу', 'error')
        return redirect(url_for('settings_page'))
    file = request.files['file']
    if file.filename == '':
        flash('Файл не вибрано', 'error')
        return redirect(url_for('settings_page'))
    
    if not file.filename.endswith('.xlsx'):
        flash('Тільки .xlsx файли підтримуються', 'error')
        return redirect(url_for('settings_page'))

    try:
        wb = openpyxl.load_workbook(file)
        sheet = wb.active
        
        headers = {}
        for col_idx, cell in enumerate(sheet[1]):
            val = str(cell.value).strip().lower() if cell.value else ""
            if "прізвище" in val or "фамилия" in val: headers['last'] = col_idx
            elif "ім'я" in val or "имя" in val: headers['first'] = col_idx
            elif "батькові" in val or "отчество" in val: headers['mid'] = col_idx
            elif "піб" in val or "фіо" in val or "п.і.б" in val or "ф.и.о" in val: headers['full'] = col_idx
            elif "клас" in val or "класс" in val: headers['class'] = col_idx

        if 'class' not in headers:
            flash('Колонка "Клас" не знайдена в першому рядку!', 'error')
            return redirect(url_for('settings_page'))
            
        if 'full' not in headers and 'first' not in headers:
            flash('Не знайдено колонки з ПІБ або Ім\'ям!', 'error')
            return redirect(url_for('settings_page'))

        conn = get_db_connection()
        db_users = conn.execute("SELECT uid, name FROM users").fetchall()
        
        def normalize(name):
            return " ".join(str(name).lower().split())
            
        name_to_uid = {normalize(u['name']): u['uid'] for u in db_users}
        
        updated = 0
        skipped = 0

        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not any(row): continue
            
            c_val = row[headers['class']]
            if not c_val: continue
            class_group = str(c_val).strip()
            
            full_name = ""
            if 'full' in headers and row[headers['full']]:
                full_name = str(row[headers['full']]).strip()
            elif 'last' in headers and 'first' in headers:
                last = str(row[headers['last']] or "").strip()
                first = str(row[headers['first']] or "").strip()
                mid = str(row[headers.get('mid')] or "").strip() if 'mid' in headers else ""
                full_name = f"{last} {first} {mid}".strip()
            
            if not full_name:
                continue
                
            norm_name = normalize(full_name)
            
            if g.web_user['role'] == 'teacher' and class_group not in g.web_user['classes']:
                skipped += 1
                continue
                
            if norm_name in name_to_uid:
                uid = name_to_uid[norm_name]
                conn.execute("UPDATE users SET class_group = ? WHERE uid = ?", (class_group, uid))
                updated += 1
            else:
                skipped += 1
                
        conn.commit()
        conn.close()
        flash(f'Успішно оновлено класів: {updated}. Пропущено/не знайдено в базі: {skipped}', 'success')
        
    except Exception as e:
        flash(f'Помилка обробки файлу: {str(e)}', 'error')

    return redirect(url_for('settings_page'))

@app.route('/api/add_user', methods=['POST'])
@requires_admin
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
@requires_admin
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