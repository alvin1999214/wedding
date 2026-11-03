import io
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
import zipfile
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

import qrcode
from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

DATA = Path(os.environ.get('DATA_DIR', 'data'))
DATA.mkdir(parents=True, exist_ok=True)
DOMAIN = os.environ.get('DOMAIN', 'localhost')
if not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]+)?', DOMAIN):
    raise ValueError('DOMAIN 必須是網域名稱，不含協定或路徑')
LOCAL = DOMAIN.split(':')[0] in ('localhost', '127.0.0.1')
BASE = ('http://' if LOCAL else 'https://') + DOMAIN

def persisted_secret(name):
    path = DATA / name
    try:
        with path.open('x') as file:
            file.write(secrets.token_urlsafe(32))
        path.chmod(0o600)
    except FileExistsError:
        pass
    return path.read_text().strip()

app = Flask(__name__)
app.config.update(SECRET_KEY=persisted_secret('session.key'), SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SECURE=not LOCAL, SESSION_COOKIE_SAMESITE='Lax',
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=1024*1024)

DEFAULTS = {'couple': 'Jamie & Alex', 'date': '2027-05-22', 'venue': '我們的婚禮場地',
            'address': '請在後臺填寫婚禮地址', 'message': '最美的日子，因為有你。謝謝你來見證我們的故事。',
            'schedule': [{'time': '16:00', 'title': '迎賓 · 相聚的開始'}, {'time': '16:30', 'title': '證婚 · 說出我願意'},
                         {'time': '17:15', 'title': '合照 · 收藏這一刻'}, {'time': '18:30', 'title': '婚宴 · 為幸福乾杯'}],
            'mode': 'wedding', 'custom_path': '/games/lottery', 'lottery_message': '幸運即將降臨，請留意現場主持人的指示。'}
with sqlite3.connect(DATA / 'wedding.db') as conn:
    conn.executescript('''PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL, password TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS guests (id TEXT PRIMARY KEY, name TEXT NOT NULL, table_name TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY, name TEXT NOT NULL, time TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS memberships (guest_id TEXT REFERENCES guests(id) ON DELETE CASCADE, group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE, PRIMARY KEY(guest_id,group_id));
    CREATE TABLE IF NOT EXISTS attempts (ip TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
    ''')
    conn.execute('INSERT OR IGNORE INTO settings VALUES (1,?)', (json.dumps(DEFAULTS, ensure_ascii=False),))
    if not conn.execute('SELECT 1 FROM admins').fetchone():
        persisted_secret('setup.token')

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATA / 'wedding.db', timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(error):
    if 'db' in g:
        g.db.close()

def settings():
    return json.loads(db().execute('SELECT value FROM settings WHERE id=1').fetchone()[0])

def csrf():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']
app.jinja_env.globals.update(csrf=csrf)

@app.before_request
def protect():
    if request.method == 'POST' and not secrets.compare_digest(session.get('csrf', '').encode(), request.form.get('csrf', '').encode()):
        abort(400, '頁面已過期，請重新載入後再試。')
    if request.method == 'POST' and not session.get('csrf'):
        abort(400)

@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    return response

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped

def field(name, limit=200, required=False):
    value = request.form.get(name, '').strip()
    if len(value) > limit or (required and not value):
        abort(400, '欄位過長或缺少必填資料：' + name)
    return value

def throttle():
    # The origin is loopback-only. Cloudflare Tunnel supplies CF-Connecting-IP;
    # direct local requests fall back to the peer, never arbitrary X-Forwarded-For.
    ip = request.headers.get('CF-Connecting-IP') or request.remote_addr or 'unknown'
    now = time.time()
    db().execute('DELETE FROM attempts WHERE started < ?', (now-900,))
    db().execute('INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(ip) DO UPDATE SET count=count+1', (ip, now))
    db().commit()
    if db().execute('SELECT count FROM attempts WHERE ip=?', (ip,)).fetchone()[0] > 15:
        abort(429, '嘗試次數過多，請於 15 分鐘後重試。')

@app.route('/admin/setup', methods=['GET', 'POST'])
def setup():
    if db().execute('SELECT 1 FROM admins').fetchone():
        return redirect(url_for('login'))
    if request.method == 'POST':
        throttle()
        token = field('token', 100, True)
        password = field('password', 200, True)
        if not secrets.compare_digest(token.encode(), persisted_secret('setup.token').encode()):
            flash('設定碼不正確。', 'error')
        elif len(password) < 12:
            flash('密碼至少需要 12 個字元。', 'error')
        else:
            try:
                db().execute('INSERT INTO admins VALUES (1,?,?)', (field('username', 80, True), generate_password_hash(password)))
                db().commit()
            except sqlite3.IntegrityError:
                abort(409)
            (DATA / 'setup.token').unlink(missing_ok=True)
            flash('管理員已建立，請登入。')
            return redirect(url_for('login'))
    return render_template('auth.html', setup=True)

@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if not db().execute('SELECT 1 FROM admins').fetchone():
        return redirect(url_for('setup'))
    if request.method == 'POST':
        throttle()
        admin = db().execute('SELECT * FROM admins WHERE id=1').fetchone()
        if field('username', 80) == admin['username'] and check_password_hash(admin['password'], field('password', 200)):
            session.clear()
            session['admin'] = True
            session.permanent = True
            return redirect(url_for('admin'))
        flash('帳號或密碼不正確。', 'error')
    return render_template('auth.html', setup=False)

@app.post('/admin/logout')
@admin_required
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.get('/admin')
@admin_required
def admin():
    guests = db().execute('SELECT * FROM guests ORDER BY name').fetchall()
    groups = db().execute('SELECT * FROM groups ORDER BY position,id').fetchall()
    memberships = {(r['guest_id'], r['group_id']) for r in db().execute('SELECT * FROM memberships')}
    return render_template('admin.html', s=settings(), guests=guests, groups=groups, memberships=memberships, base=BASE)

@app.post('/admin/guests')
@admin_required
def save_guest():
    guest_id = field('id', 36) or str(uuid.uuid4())
    db().execute('INSERT INTO guests VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,table_name=excluded.table_name,note=excluded.note',
                 (guest_id, field('name', 80, True), field('table_name', 80), field('note', 500)))
    db().execute('DELETE FROM memberships WHERE guest_id=?', (guest_id,))
    for group_id in set(request.form.getlist('groups')):
        if not db().execute('SELECT 1 FROM groups WHERE id=?', (group_id,)).fetchone():
            abort(400, '拍照組別不存在。')
        db().execute('INSERT INTO memberships VALUES (?,?)', (guest_id, group_id))
    db().commit()
    flash('賓客及拍照組別已儲存。')
    return redirect(url_for('admin', _anchor='guests'))

@app.post('/admin/guests/<guest_id>/delete')
@admin_required
def delete_guest(guest_id):
    db().execute('DELETE FROM guests WHERE id=?', (guest_id,))
    db().commit()
    flash('賓客已刪除，原 QR code 將失效。')
    return redirect(url_for('admin', _anchor='guests'))

@app.post('/admin/groups')
@admin_required
def save_group():
    group_id = field('id', 20) or None
    position = field('position', 8) or '0'
    if not position.isdigit():
        abort(400, '排序必須是非負整數。')
    db().execute('INSERT INTO groups VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,time=excluded.time,location=excluded.location,position=excluded.position',
                 (group_id, field('name', 80, True), field('time', 20), field('location', 200), int(position)))
    db().commit()
    flash('拍照組別已儲存。')
    return redirect(url_for('admin', _anchor='groups'))

@app.post('/admin/groups/<int:group_id>/delete')
@admin_required
def delete_group(group_id):
    db().execute('DELETE FROM groups WHERE id=?', (group_id,))
    db().commit()
    return redirect(url_for('admin', _anchor='groups'))

@app.post('/admin/settings')
@admin_required
def save_settings():
    s = settings()
    for key in ('couple', 'date', 'venue', 'address', 'message', 'lottery_message'):
        s[key] = field(key, 1000, True)
    try:
        date.fromisoformat(s['date'])
    except ValueError:
        abort(400, '日期格式不正確。')
    schedule = []
    for line in field('schedule', 5000, True).splitlines():
        parts = line.strip().split('|', 1)
        if len(parts) != 2 or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', parts[0].strip()) or not parts[1].strip():
            abort(400, '行程每行格式為 HH:MM | 活動名稱。')
        schedule.append({'time': parts[0].strip(), 'title': parts[1].strip()})
    s['schedule'] = sorted(schedule, key=lambda row: row['time'])
    db().execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(s, ensure_ascii=False),))
    db().commit()
    flash('婚禮資訊已更新。')
    return redirect(url_for('admin', _anchor='settings'))

@app.post('/admin/mode')
@admin_required
def save_mode():
    s = settings()
    mode = field('mode', 20, True)
    path = field('custom_path', 200) or '/games/lottery'
    if mode not in ('wedding', 'lottery', 'custom') or not re.fullmatch(r'/games/[a-zA-Z0-9/_-]+', path):
        abort(400, '擴充遊戲路徑必須以 /games/ 開頭，且不含查詢參數。')
    s.update(mode=mode, custom_path=path)
    db().execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(s, ensure_ascii=False),))
    db().commit()
    flash('跳轉模式已更新；重新掃描原 QR code 即可生效。')
    return redirect(url_for('admin', _anchor='routing'))

def get_guest(guest_id):
    guest = db().execute('SELECT * FROM guests WHERE id=?', (guest_id,)).fetchone()
    if not guest:
        abort(404, '找不到這張邀請函，請向新人確認專屬連結。')
    return guest

def qr_bytes(guest_id):
    output = io.BytesIO()
    qrcode.make(BASE + '/' + guest_id).save(output, format='PNG')
    output.seek(0)
    return output

@app.get('/admin/qr/<guest_id>.png')
@admin_required
def qr(guest_id):
    get_guest(guest_id)
    return send_file(qr_bytes(guest_id), mimetype='image/png', as_attachment=True, download_name=guest_id+'.png')

@app.get('/admin/qrcodes.zip')
@admin_required
def qr_zip():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for guest in db().execute('SELECT * FROM guests'):
            archive.writestr(guest['id']+'.png', qr_bytes(guest['id']).getvalue())
        import csv
        manifest = io.StringIO()
        writer = csv.writer(manifest)
        writer.writerow(['UUID', '賓客', '桌號', '連結'])
        for guest in db().execute('SELECT * FROM guests'):
            safe = lambda value: "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
            writer.writerow([guest['id'], safe(guest['name']), safe(guest['table_name']), BASE+'/'+guest['id']])
        archive.writestr('guests.csv', '\ufeff'+manifest.getvalue())
    output.seek(0)
    return send_file(output, mimetype='application/zip', as_attachment=True, download_name='wedding-qrcodes.zip')

@app.get('/health')
def health():
    db().execute('SELECT 1')
    return {'status': 'ok'}

@app.get('/')
def index():
    return render_template('guest.html', s=settings(), guest=None, groups=[], map_url=None)

@app.get('/<uuid:guest_id>')
def resolve_guest(guest_id):
    guest_id = str(guest_id)
    get_guest(guest_id)
    s = settings()
    if s['mode'] == 'wedding':
        return redirect(url_for('invitation', guest_id=guest_id), 302)
    path = '/games/lottery' if s['mode'] == 'lottery' else s['custom_path']
    return redirect(path + '?' + urlencode({'guest': guest_id}), 302)

@app.get('/invitation/<uuid:guest_id>')
def invitation(guest_id):
    guest = get_guest(str(guest_id))
    groups = db().execute('SELECT groups.* FROM groups JOIN memberships ON groups.id=memberships.group_id WHERE guest_id=? ORDER BY position,groups.id', (str(guest_id),)).fetchall()
    s = settings()
    return render_template('guest.html', s=s, guest=guest, groups=groups, map_url='https://www.google.com/maps/search/?'+urlencode({'api': 1, 'query': s['address']}))

@app.get('/games/lottery')
def lottery():
    guest = get_guest(request.args.get('guest', ''))
    return render_template('lottery.html', s=settings(), guest=guest)

@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(413)
@app.errorhandler(429)
def error_page(error):
    return render_template('error.html', error=error), error.code
