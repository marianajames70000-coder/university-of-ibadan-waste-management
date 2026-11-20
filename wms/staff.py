import csv, io, re
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, current_app, Response, send_from_directory
from werkzeug.security import generate_password_hash
from .auth import login_required
from .db import get_db, audit
from .routing import plan, DEPOT
bp = Blueprint('staff', __name__, url_prefix='/staff')
MATERIALS = ('plastic', 'paper', 'glass', 'metal', 'organic')
@bp.route('/')
@login_required('admin')
def dashboard():
    db = get_db(); th = current_app.config['FILL_THRESHOLD']
    q = lambda s, *a: db.execute(s, a).fetchone()[0]
    stats = dict(bins=q('SELECT COUNT(*) FROM bins'), full=q('SELECT COUNT(*) FROM bins WHERE fill_pct>=?', th),
        pending=q("SELECT COUNT(*) FROM pickup_requests WHERE status='pending'"),
        open_reports=q("SELECT COUNT(*) FROM dumping_reports WHERE status!='resolved'"),
        active_routes=q("SELECT COUNT(*) FROM routes WHERE status!='completed'"),
        collected_kg=q('SELECT COALESCE(SUM(weight_kg),0) FROM route_stops WHERE done=1'))
    alerts = db.execute('SELECT b.*, z.name zone FROM bins b JOIN zones z ON z.id=b.zone_id WHERE fill_pct>=? ORDER BY fill_pct DESC', (th,)).fetchall()
    return render_template('dashboard.html', stats=stats, alerts=alerts, th=th)
@bp.route('/bins')
@login_required('admin')
def bins():
    rows = get_db().execute('SELECT b.*, z.name zone FROM bins b JOIN zones z ON z.id=b.zone_id ORDER BY z.name, b.label').fetchall()
    return render_template('bins.html', bins=rows, th=current_app.config['FILL_THRESHOLD'])
@bp.route('/bins/<int:bid>/fill', methods=['POST'])
@login_required('admin')
def set_fill(bid):
    v = request.form.get('fill_pct', '')
    if not v.isdigit() or not 0 <= int(v) <= 100: flash('Fill level must be 0 to 100.', 'error')
    else:
        db = get_db(); db.execute('UPDATE bins SET fill_pct=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (int(v), bid))
        audit(g.user['id'], 'bin_fill', f'{bid}={v}'); db.commit()
    return redirect(url_for('staff.bins'))
@bp.route('/routes')
@login_required('admin')
def routes():
    db = get_db()
    rows = db.execute('SELECT r.*, z.name zone, u.name collector, (SELECT COUNT(*) FROM route_stops s WHERE s.route_id=r.id) stops FROM routes r JOIN zones z ON z.id=r.zone_id JOIN users u ON u.id=r.collector_id ORDER BY r.id DESC').fetchall()
    return render_template('routes.html', routes=rows, zones=db.execute('SELECT * FROM zones ORDER BY name').fetchall(),
        collectors=db.execute("SELECT * FROM users WHERE role='collector' AND active=1 ORDER BY name").fetchall(), today=date.today().isoformat())
@bp.route('/routes/plan', methods=['POST'])
@login_required('admin')
def plan_route():
    db = get_db(); f = request.form; th = current_app.config['FILL_THRESHOLD']
    zid, cid, vehicle, rdate = f.get('zone_id', ''), f.get('collector_id', ''), f.get('vehicle', '').strip(), f.get('route_date', '')
    col = db.execute("SELECT * FROM users WHERE id=? AND role='collector' AND active=1", (cid,)).fetchone() if cid.isdigit() else None
    if not zid.isdigit() or not col or not vehicle or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', rdate):
        flash('Choose a zone, a collector, a date and a vehicle.', 'error'); return redirect(url_for('staff.routes'))
    bins = db.execute('SELECT * FROM bins WHERE zone_id=? AND fill_pct>=?', (zid, th)).fetchall()
    reqs = db.execute("SELECT p.*, z.name FROM pickup_requests p JOIN zones z ON z.id=p.zone_id WHERE zone_id=? AND status='pending'", (zid,)).fetchall()
    pts = [(b['lat'], b['lon'], ('bin', b['id'])) for b in bins]
    # a pickup request is served at the zone's request point (zone centroid of its bins, else depot)
    zb = db.execute('SELECT AVG(lat) la, AVG(lon) lo FROM bins WHERE zone_id=?', (zid,)).fetchone()
    base = (zb['la'] or DEPOT[0], zb['lo'] or DEPOT[1])
    for i, r in enumerate(reqs): pts.append((base[0] + 0.0007*((i % 5) - 2), base[1] + 0.0007*((i // 5) - 1), ('req', r['id'])))
    if not pts: flash('Nothing to collect in that zone: no full bins and no pending requests.', 'error'); return redirect(url_for('staff.routes'))
    order, km, naive = plan(pts)
    cur = db.execute('INSERT INTO routes(zone_id,route_date,vehicle,collector_id,distance_km,naive_km) VALUES(?,?,?,?,?,?)', (zid, rdate, vehicle, col['id'], round(km, 2), round(naive, 2)))
    rid = cur.lastrowid
    for i, (_, _, (kind, ref)) in enumerate(order, 1):
        db.execute('INSERT INTO route_stops(route_id,seq,bin_id,request_id) VALUES(?,?,?,?)', (rid, i, ref if kind == 'bin' else None, ref if kind == 'req' else None))
        if kind == 'req': db.execute("UPDATE pickup_requests SET status='scheduled', route_id=?, version=version+1 WHERE id=? AND status='pending'", (rid, ref))
    audit(g.user['id'], 'route_planned', f'{rid} stops={len(order)} km={km:.2f}'); db.commit()
    flash(f'Route planned with {len(order)} stops, {km:.1f} km.', 'ok'); return redirect(url_for('staff.route_detail', rid=rid))
def _route_or_404(rid):
    r = get_db().execute('SELECT r.*, z.name zone, u.name collector FROM routes r JOIN zones z ON z.id=r.zone_id JOIN users u ON u.id=r.collector_id WHERE r.id=?', (rid,)).fetchone()
    if not r: abort(404)
    if g.user['role'] == 'collector' and r['collector_id'] != g.user['id']: abort(403)
    return r
@bp.route('/routes/<int:rid>')
@login_required('admin', 'collector')
def route_detail(rid):
    r = _route_or_404(rid)
    stops = get_db().execute('SELECT s.*, b.label, b.kind, b.fill_pct, p.address, p.waste_type FROM route_stops s LEFT JOIN bins b ON b.id=s.bin_id LEFT JOIN pickup_requests p ON p.id=s.request_id WHERE s.route_id=? ORDER BY s.seq', (rid,)).fetchall()
    return render_template('route.html', r=r, stops=stops)
@bp.route('/my-routes')
@login_required('collector')
def my_routes():
    rows = get_db().execute("SELECT r.*, z.name zone, (SELECT COUNT(*) FROM route_stops s WHERE s.route_id=r.id) stops, (SELECT COUNT(*) FROM route_stops s WHERE s.route_id=r.id AND done=1) done_n FROM routes r JOIN zones z ON z.id=r.zone_id WHERE collector_id=? ORDER BY r.route_date DESC, r.id DESC", (g.user['id'],)).fetchall()
    return render_template('my_routes.html', routes=rows)
@bp.route('/routes/<int:rid>/start', methods=['POST'])
@login_required('collector')
def start_route(rid):
    r = _route_or_404(rid); db = get_db()
    if db.execute("UPDATE routes SET status='in_progress' WHERE id=? AND status='planned'", (rid,)).rowcount: audit(g.user['id'], 'route_started', str(rid)); flash('Route started.', 'ok')
    db.commit(); return redirect(url_for('staff.route_detail', rid=rid))
@bp.route('/stops/<int:sid>/done', methods=['POST'])
@login_required('collector')
def stop_done(sid):
    db = get_db(); s = db.execute('SELECT * FROM route_stops WHERE id=?', (sid,)).fetchone()
    if not s: abort(404)
    r = _route_or_404(s['route_id'])
    try: w = float(request.form.get('weight_kg', ''))
    except ValueError: w = -1
    if r['status'] != 'in_progress': flash('Start the route first.', 'error')
    elif not 0 < w <= 5000: flash('Enter the collected weight in kg (greater than 0).', 'error')
    elif db.execute('UPDATE route_stops SET done=1, weight_kg=? WHERE id=? AND done=0', (w, sid)).rowcount:
        if s['bin_id']: db.execute('UPDATE bins SET fill_pct=0, updated_at=CURRENT_TIMESTAMP WHERE id=?', (s['bin_id'],))
        if s['request_id']: db.execute("UPDATE pickup_requests SET status='collected', version=version+1 WHERE id=?", (s['request_id'],))
        if not db.execute('SELECT 1 FROM route_stops WHERE route_id=? AND done=0', (r['id'],)).fetchone():
            db.execute("UPDATE routes SET status='completed' WHERE id=?", (r['id'],)); flash('Route completed.', 'ok')
        audit(g.user['id'], 'stop_done', f'{sid} {w}kg'); db.commit()
    return redirect(url_for('staff.route_detail', rid=r['id']))
@bp.route('/reports')
@login_required('admin')
def reports():
    rows = get_db().execute('SELECT d.*, z.name zone, u.name reporter FROM dumping_reports d JOIN zones z ON z.id=d.zone_id JOIN users u ON u.id=d.reporter_id ORDER BY d.status="resolved", d.id DESC').fetchall()
    return render_template('reports.html', rows=rows)
@bp.route('/reports/<int:did>', methods=['POST'])
@login_required('admin')
def update_report(did):
    st, res = request.form.get('status'), request.form.get('resolution', '').strip()
    if st not in ('investigating', 'resolved'): abort(400)
    if st == 'resolved' and len(res) < 5: flash('A resolution note is required to close a report.', 'error')
    else:
        db = get_db(); db.execute('UPDATE dumping_reports SET status=?, resolution=? WHERE id=?', (st, res or None, did)); audit(g.user['id'], 'report_' + st, str(did)); db.commit()
    return redirect(url_for('staff.reports'))
@bp.route('/photo/<name>')
@login_required('admin')
def photo(name):
    if not re.fullmatch(r'[0-9a-f]{32}\.(png|jpg)', name): abort(404)
    return send_from_directory(current_app.instance_path + '/uploads', name)
@bp.route('/recycling', methods=['GET', 'POST'])
@login_required('admin', 'collector')
def recycling():
    db = get_db()
    if request.method == 'POST':
        m, z = request.form.get('material'), request.form.get('zone_id', '')
        try: kg = float(request.form.get('kg', ''))
        except ValueError: kg = 0
        if m not in MATERIALS or not z.isdigit() or not 0 < kg <= 10000: flash('Choose material, zone and a weight above 0.', 'error')
        else: db.execute('INSERT INTO recycling_log(zone_id,material,kg,logged_by) VALUES(?,?,?,?)', (int(z), m, kg, g.user['id'])); audit(g.user['id'], 'recycling_logged', f'{m} {kg}'); db.commit(); flash('Logged.', 'ok')
        return redirect(url_for('staff.recycling'))
    tot = db.execute('SELECT material, ROUND(SUM(kg),1) kg FROM recycling_log GROUP BY material ORDER BY kg DESC').fetchall()
    return render_template('recycling.html', tot=tot, zones=db.execute('SELECT * FROM zones ORDER BY name').fetchall(), materials=MATERIALS)
@bp.route('/analytics')
@login_required('admin')
def analytics():
    db = get_db()
    zone_rows = db.execute("SELECT z.name, (SELECT COUNT(*) FROM pickup_requests p WHERE p.zone_id=z.id) requests, (SELECT COUNT(*) FROM pickup_requests p WHERE p.zone_id=z.id AND p.status='collected') collected, (SELECT COUNT(*) FROM dumping_reports d WHERE d.zone_id=z.id) reports, (SELECT ROUND(AVG(fill_pct),0) FROM bins b WHERE b.zone_id=z.id) avg_fill FROM zones z ORDER BY z.name").fetchall()
    rt = db.execute("SELECT COUNT(*) n, COALESCE(SUM(distance_km),0) km, COALESCE(SUM(naive_km),0) nk FROM routes").fetchone()
    saving = round(100*(rt['nk']-rt['km'])/rt['nk'], 1) if rt['nk'] else 0
    return render_template('analytics.html', zones=zone_rows, rt=rt, saving=saving)
@bp.route('/export.csv')
@login_required('admin')
def export():
    rows = get_db().execute('SELECT p.id, u.name, z.name zone, p.address, p.waste_type, p.status, p.created_at FROM pickup_requests p JOIN users u ON u.id=p.resident_id JOIN zones z ON z.id=p.zone_id ORDER BY p.id').fetchall()
    out = io.StringIO(); w = csv.writer(out); w.writerow(['id', 'resident', 'zone', 'address', 'waste_type', 'status', 'created_at'])
    for r in rows: w.writerow([("'" + str(c)) if isinstance(c, str) and c[:1] in '=+-@' else c for c in tuple(r)])
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=requests.csv'})
@bp.route('/users', methods=['GET', 'POST'])
@login_required('admin')
def users():
    db = get_db()
    if request.method == 'POST':
        f = request.form; email = f.get('email', '').strip().lower()
        if f.get('action') == 'deactivate' and f.get('uid', '').isdigit() and int(f['uid']) != g.user['id']:
            db.execute('UPDATE users SET active=0 WHERE id=?', (int(f['uid']),)); audit(g.user['id'], 'user_deactivated', f['uid']); db.commit()
        elif f.get('action') == 'create' and f.get('role') in ('collector', 'admin') and f.get('name', '').strip() and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) and len(f.get('password', '')) >= 8 and not db.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
            db.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)', (f['name'].strip(), email, generate_password_hash(f['password']), f['role'])); audit(g.user['id'], 'user_created', email); db.commit(); flash('User created.', 'ok')
        else: flash('Check the details: valid unique email and a password of 8+ characters.', 'error')
        return redirect(url_for('staff.users'))
    return render_template('users.html', rows=db.execute('SELECT u.*, z.name zone FROM users u LEFT JOIN zones z ON z.id=u.zone_id ORDER BY u.role, u.name').fetchall())
@bp.route('/audit')
@login_required('admin')
def audit_log():
    return render_template('audit.html', rows=get_db().execute('SELECT a.*, u.name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200').fetchall())
