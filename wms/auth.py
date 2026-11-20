import re, secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g, abort
from werkzeug.security import generate_password_hash, check_password_hash
from .db import get_db, audit
bp = Blueprint('auth', __name__)
MAX_FAILS, LOCK_MIN = 5, 15
def login_required(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if not g.user: return redirect(url_for('auth.login'))
            if roles and g.user['role'] not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco
def home_for(role): return url_for({'resident': 'resident.dashboard', 'collector': 'staff.my_routes', 'admin': 'staff.dashboard'}[role])
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = get_db(); email = request.form.get('email', '').strip().lower()
        u = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        now = datetime.utcnow()
        if u and u['locked_until'] and datetime.fromisoformat(u['locked_until']) > now:
            flash('Account locked for 15 minutes after repeated failed sign-ins.', 'error')
        elif u and u['active'] and check_password_hash(u['password_hash'], request.form.get('password', '')):
            db.execute('UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?', (u['id'],))
            session.clear(); session['uid'] = u['id']; session['csrf'] = secrets.token_hex(16)
            audit(u['id'], 'login'); db.commit()
            return redirect(home_for(u['role']))
        else:
            if u:
                f = u['failed_logins'] + 1
                lock = (now + timedelta(minutes=LOCK_MIN)).isoformat() if f >= MAX_FAILS else None
                db.execute('UPDATE users SET failed_logins=?, locked_until=? WHERE id=?', (0 if lock else f, lock, u['id']))
                audit(u['id'], 'login_failed'); db.commit()
            flash('Invalid email or password.', 'error')
    return render_template('login.html')
@bp.route('/register', methods=['GET', 'POST'])
def register():
    db = get_db(); zones = db.execute('SELECT * FROM zones ORDER BY name').fetchall()
    if request.method == 'POST':
        name, email = request.form.get('name', '').strip(), request.form.get('email', '').strip().lower()
        pw, zone = request.form.get('password', ''), request.form.get('zone_id', '')
        err = None
        if not name or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email): err = 'Enter your name and a valid email.'
        elif len(pw) < 8 or not re.search(r'\d', pw) or not re.search(r'[A-Za-z]', pw): err = 'Password must be 8+ characters with letters and digits.'
        elif not zone.isdigit() or not db.execute('SELECT 1 FROM zones WHERE id=?', (zone,)).fetchone(): err = 'Choose your zone.'
        elif db.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone(): err = 'That email is already registered.'
        if err: flash(err, 'error')
        else:
            cur = db.execute('INSERT INTO users(name,email,phone,password_hash,role,zone_id) VALUES(?,?,?,?,?,?)',
                (name, email, request.form.get('phone', '').strip(), generate_password_hash(pw), 'resident', int(zone)))
            audit(cur.lastrowid, 'register'); db.commit()
            flash('Account created. Please sign in.', 'ok'); return redirect(url_for('auth.login'))
    return render_template('register.html', zones=zones)
@bp.route('/logout', methods=['POST'])
def logout():
    if g.user: audit(g.user['id'], 'logout'); get_db().commit()
    session.clear(); return redirect(url_for('public.index'))
