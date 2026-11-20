import os, uuid
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, current_app
from .auth import login_required
from .db import get_db, audit
bp = Blueprint('resident', __name__, url_prefix='/resident')
TYPES = ('general', 'recyclable', 'bulky', 'hazardous')
@bp.route('/')
@login_required('resident')
def dashboard():
    db = get_db(); uid = g.user['id']
    reqs = db.execute('SELECT p.*, z.name zone FROM pickup_requests p JOIN zones z ON z.id=p.zone_id WHERE resident_id=? ORDER BY p.id DESC', (uid,)).fetchall()
    reps = db.execute('SELECT d.*, z.name zone FROM dumping_reports d JOIN zones z ON z.id=d.zone_id WHERE reporter_id=? ORDER BY d.id DESC', (uid,)).fetchall()
    zone = db.execute('SELECT * FROM zones WHERE id=?', (g.user['zone_id'],)).fetchone()
    return render_template('resident.html', reqs=reqs, reps=reps, zone=zone, types=TYPES, zones=db.execute('SELECT * FROM zones ORDER BY name').fetchall())
@bp.route('/request', methods=['POST'])
@login_required('resident')
def new_request():
    db = get_db(); wt = request.form.get('waste_type'); addr = request.form.get('address', '').strip()
    pref = request.form.get('preferred_date', '')
    if wt not in TYPES or len(addr) < 5: flash('Choose a waste type and enter a full address.', 'error')
    elif pref and (pref < date.today().isoformat()): flash('Preferred date cannot be in the past.', 'error')
    else:
        open_n = db.execute("SELECT COUNT(*) FROM pickup_requests WHERE resident_id=? AND status IN('pending','scheduled')", (g.user['id'],)).fetchone()[0]
        if open_n >= 5: flash('You already have 5 open requests.', 'error')
        else:
            cur = db.execute('INSERT INTO pickup_requests(resident_id,zone_id,address,waste_type,preferred_date) VALUES(?,?,?,?,?)', (g.user['id'], g.user['zone_id'], addr, wt, pref or None))
            audit(g.user['id'], 'request_created', str(cur.lastrowid)); db.commit(); flash('Pickup request submitted.', 'ok')
    return redirect(url_for('resident.dashboard'))
@bp.route('/request/<int:rid>/cancel', methods=['POST'])
@login_required('resident')
def cancel(rid):
    db = get_db()
    r = db.execute('SELECT * FROM pickup_requests WHERE id=?', (rid,)).fetchone()
    if not r or r['resident_id'] != g.user['id']: abort(404)
    n = db.execute("UPDATE pickup_requests SET status='cancelled', version=version+1 WHERE id=? AND status='pending'", (rid,)).rowcount
    if n: audit(g.user['id'], 'request_cancelled', str(rid)); flash('Request cancelled.', 'ok')
    else: flash('Only pending requests can be cancelled.', 'error')
    db.commit(); return redirect(url_for('resident.dashboard'))
@bp.route('/report', methods=['POST'])
@login_required('resident')
def report():
    db = get_db(); loc, desc = request.form.get('location', '').strip(), request.form.get('description', '').strip()
    zone = request.form.get('zone_id', '')
    if len(loc) < 3 or len(desc) < 10 or not zone.isdigit() or not db.execute('SELECT 1 FROM zones WHERE id=?', (zone,)).fetchone():
        flash('Give the zone, the location and a description of at least 10 characters.', 'error')
    else:
        photo = None; f = request.files.get('photo')
        if f and f.filename:
            head = f.stream.read(8); f.stream.seek(0)
            ext = 'png' if head.startswith(b'\x89PNG') else 'jpg' if head[:3] == b'\xff\xd8\xff' else None
            if not ext: flash('Photo must be a real PNG or JPEG image.', 'error'); return redirect(url_for('resident.dashboard'))
            photo = uuid.uuid4().hex + '.' + ext
            os.makedirs(os.path.join(current_app.instance_path, 'uploads'), exist_ok=True)
            f.save(os.path.join(current_app.instance_path, 'uploads', photo))
        cur = db.execute('INSERT INTO dumping_reports(reporter_id,zone_id,location,description,photo) VALUES(?,?,?,?,?)', (g.user['id'], int(zone), loc, desc, photo))
        audit(g.user['id'], 'dumping_reported', str(cur.lastrowid)); db.commit(); flash('Report received. Thank you.', 'ok')
    return redirect(url_for('resident.dashboard'))
