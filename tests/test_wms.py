import os, re, tempfile, unittest, io
from wms import create_app
from wms.seed import seed
from wms.db import get_db
from wms.routing import haversine, nearest_neighbour, tour_length, plan, DEPOT
class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.app = create_app({'DATABASE': os.path.join(self.d.name, 't.sqlite'), 'TESTING': True}); seed(self.app)
        self.app.instance_path = self.d.name
        self.c = self.app.test_client()
    def tearDown(self): self.d.cleanup()
    def tok(self, c=None, path='/login'):
        r = (c or self.c).get(path, follow_redirects=True); return re.search(r'name="csrf" value="(\w+)"', r.get_data(as_text=True)).group(1)
    def login(self, email, pw, c=None):
        c = c or self.c; return c.post('/login', data={'email': email, 'password': pw, 'csrf': self.tok(c)}, follow_redirects=True)
    def post(self, path, data=None, c=None, **kw):
        c = c or self.c; d = dict(data or {}); d['csrf'] = self.tok(c, '/'); return c.post(path, data=d, follow_redirects=True, **kw)
    def q(self, sql, *a):
        with self.app.app_context(): return get_db().execute(sql, a).fetchall()
    def admin(self): self.login('admin@wms.test', 'Admin@12345'); return self
    def resident(self): self.login('resident1@wms.test', 'Resident@123'); return self
    def collector(self): self.login('collector1@wms.test', 'Collect@123'); return self
class TestAuth(Base):
    def test_t01_register_and_login(self):
        r = self.c.post('/register', data={'name': 'New Person', 'email': 'new@x.com', 'password': 'Secret123', 'zone_id': '1', 'csrf': self.tok(path='/register')}, follow_redirects=True)
        self.assertIn('Account created', r.get_data(as_text=True))
        self.assertIn('Hello, New Person', self.login('new@x.com', 'Secret123').get_data(as_text=True))
    def test_t02_weak_password_rejected(self):
        r = self.c.post('/register', data={'name': 'A B', 'email': 'a@b.com', 'password': 'short', 'zone_id': '1', 'csrf': self.tok(path='/register')})
        self.assertIn('Password must be', r.get_data(as_text=True))
    def test_t03_bad_login(self): self.assertIn('Invalid email or password', self.login('admin@wms.test', 'nope').get_data(as_text=True))
    def test_sec_lockout_after_five_failures(self):
        for _ in range(5): self.login('resident1@wms.test', 'bad')
        self.assertIn('locked', self.login('resident1@wms.test', 'Resident@123').get_data(as_text=True))
    def test_sec_passwords_are_hashed(self):
        h = self.q("SELECT password_hash FROM users WHERE email='admin@wms.test'")[0][0]
        self.assertNotIn('Admin@12345', h); self.assertTrue(h.startswith(('scrypt:', 'pbkdf2:')))
class TestResident(Base):
    def test_t04_create_request(self):
        self.resident(); r = self.post('/resident/request', {'waste_type': 'general', 'address': '12 Test Street'})
        self.assertIn('Pickup request submitted', r.get_data(as_text=True)); self.assertEqual(len(self.q("SELECT * FROM pickup_requests")), 1)
    def test_t05_invalid_request(self):
        self.resident(); r = self.post('/resident/request', {'waste_type': 'nuclear', 'address': 'x'})
        self.assertIn('Choose a waste type', r.get_data(as_text=True))
    def test_t06_cancel_pending(self):
        self.resident(); self.post('/resident/request', {'waste_type': 'bulky', 'address': '12 Test Street'})
        self.post('/resident/request/1/cancel'); self.assertEqual(self.q('SELECT status FROM pickup_requests')[0][0], 'cancelled')
    def test_t07_five_open_request_limit(self):
        self.resident()
        for i in range(6): self.post('/resident/request', {'waste_type': 'general', 'address': f'{i} Test Street'})
        self.assertEqual(len(self.q('SELECT * FROM pickup_requests')), 5)
    def test_t08_report_dumping(self):
        self.resident(); r = self.post('/resident/report', {'zone_id': '1', 'location': 'Behind market', 'description': 'Heaps of refuse on the road'})
        self.assertIn('Report received', r.get_data(as_text=True))
    def test_t09_report_needs_description(self):
        self.resident(); r = self.post('/resident/report', {'zone_id': '1', 'location': 'Market', 'description': 'bad'})
        self.assertIn('at least 10', r.get_data(as_text=True))
    def test_sec_fake_image_rejected(self):
        self.resident(); r = self.post('/resident/report', {'zone_id': '1', 'location': 'Market', 'description': 'Dumping on the road', 'photo': (io.BytesIO(b'<?php evil ?>'), 'a.png')}, content_type='multipart/form-data')
        self.assertIn('real PNG or JPEG', r.get_data(as_text=True))
    def test_sec_cannot_cancel_others_request(self):
        self.resident(); self.post('/resident/request', {'waste_type': 'general', 'address': '12 Test Street'})
        c2 = self.app.test_client(); self.login('resident2@wms.test', 'Resident@123', c2)
        self.assertEqual(c2.post('/resident/request/1/cancel', data={'csrf': self.tok(c2, '/resident/')}).status_code, 404)
class TestRouting(Base):
    def test_t10_haversine_zero_and_symmetry(self):
        a, b = (7.37, 3.94), (7.40, 3.91); self.assertEqual(haversine(a, a), 0); self.assertAlmostEqual(haversine(a, b), haversine(b, a))
    def test_t11_nearest_neighbour_orders_by_distance(self):
        pts = [(7.40, 3.95, 'far'), (7.378, 3.947, 'near'), (7.39, 3.95, 'mid')]
        self.assertEqual([p[2] for p in nearest_neighbour(pts)], ['near', 'mid', 'far'])
    def test_t12_plan_not_longer_than_unordered(self):
        import random; random.seed(1); pts = [(7.37 + random.random()*.06, 3.90 + random.random()*.06, i) for i in range(12)]
        _, km, naive = plan(pts); self.assertLessEqual(km, naive)
    def test_t13_empty_plan(self): self.assertEqual(tour_length([]), 0.0)
class TestStaff(Base):
    def plan(self, zone='1'):
        return self.post('/staff/routes/plan', {'zone_id': zone, 'collector_id': '2', 'route_date': '2026-12-01', 'vehicle': 'Truck 1'})
    def test_t14_plan_includes_full_bins_and_requests(self):
        self.resident(); self.post('/resident/request', {'waste_type': 'general', 'address': '12 Test Street'})
        self.c.post('/logout', data={'csrf': self.tok(path='/')}); self.admin(); r = self.plan()
        self.assertIn('Route planned', r.get_data(as_text=True))
        full = self.q('SELECT COUNT(*) FROM bins WHERE zone_id=1 AND fill_pct>=80')[0][0]
        self.assertEqual(self.q('SELECT COUNT(*) FROM route_stops')[0][0], full + 1)
        self.assertEqual(self.q('SELECT status FROM pickup_requests')[0][0], 'scheduled')
    def test_t15_nothing_to_collect(self):
        self.admin()
        with self.app.app_context(): get_db().execute('UPDATE bins SET fill_pct=10'); get_db().commit()
        self.assertIn('Nothing to collect', self.plan().get_data(as_text=True))
    def test_t16_collector_completes_route(self):
        self.admin(); self.plan(); self.c.post('/logout', data={'csrf': self.tok(path='/')})
        self.collector(); self.post('/staff/routes/1/start')
        for s in self.q('SELECT id FROM route_stops'): self.post(f'/staff/stops/{s[0]}/done', {'weight_kg': '25'})
        self.assertEqual(self.q('SELECT status FROM routes')[0][0], 'completed')
        self.assertEqual(self.q('SELECT COUNT(*) FROM bins WHERE zone_id=1 AND fill_pct>=80')[0][0], 0)
    def test_t17_stop_requires_start_and_weight(self):
        self.admin(); self.plan(); self.c.post('/logout', data={'csrf': self.tok(path='/')}); self.collector()
        self.assertIn('Start the route first', self.post('/staff/stops/1/done', {'weight_kg': '5'}).get_data(as_text=True))
        self.post('/staff/routes/1/start'); self.assertIn('Enter the collected weight', self.post('/staff/stops/1/done', {'weight_kg': '-3'}).get_data(as_text=True))
    def test_t18_resolve_needs_note(self):
        self.resident(); self.post('/resident/report', {'zone_id': '1', 'location': 'Market', 'description': 'Heaps of refuse here'})
        self.c.post('/logout', data={'csrf': self.tok(path='/')}); self.admin()
        self.assertIn('resolution note is required', self.post('/staff/reports/1', {'status': 'resolved', 'resolution': ''}).get_data(as_text=True))
        self.post('/staff/reports/1', {'status': 'resolved', 'resolution': 'Cleared by crew'}); self.assertEqual(self.q('SELECT status FROM dumping_reports')[0][0], 'resolved')
    def test_t19_fill_level_validated(self):
        self.admin(); self.post('/staff/bins/1/fill', {'fill_pct': '150'}); self.assertNotEqual(self.q('SELECT fill_pct FROM bins WHERE id=1')[0][0], 150)
        self.post('/staff/bins/1/fill', {'fill_pct': '55'}); self.assertEqual(self.q('SELECT fill_pct FROM bins WHERE id=1')[0][0], 55)
    def test_t20_recycling_log(self):
        self.admin(); n = len(self.q('SELECT * FROM recycling_log')); self.post('/staff/recycling', {'zone_id': '1', 'material': 'glass', 'kg': '12.5'})
        self.assertEqual(len(self.q('SELECT * FROM recycling_log')), n + 1)
    def test_t21_analytics_and_csv(self):
        self.admin(); self.plan(); self.assertIn('Shorter than', self.c.get('/staff/analytics').get_data(as_text=True))
        self.assertTrue(self.c.get('/staff/export.csv').data.startswith(b'id,resident'))
    def test_t22_admin_creates_and_deactivates_staff(self):
        self.admin(); self.post('/staff/users', {'action': 'create', 'name': 'New Driver', 'email': 'd@x.com', 'role': 'collector', 'password': 'Driver1234'})
        self.assertEqual(len(self.q("SELECT * FROM users WHERE email='d@x.com'")), 1)
        uid = self.q("SELECT id FROM users WHERE email='d@x.com'")[0][0]; self.post('/staff/users', {'action': 'deactivate', 'uid': str(uid)})
        self.assertEqual(self.q('SELECT active FROM users WHERE id=?', uid)[0][0], 0)
class TestSecurity(Base):
    def test_sec_anonymous_redirected(self): self.assertEqual(self.c.get('/staff/').status_code, 302)
    def test_sec_resident_blocked_from_admin(self): self.resident(); self.assertEqual(self.c.get('/staff/').status_code, 403)
    def test_sec_collector_blocked_from_other_route(self):
        self.admin(); self.post('/staff/routes/plan', {'zone_id': '1', 'collector_id': '2', 'route_date': '2026-12-01', 'vehicle': 'T'}); self.c.post('/logout', data={'csrf': self.tok(path='/')})
        c2 = self.app.test_client(); self.login('collector2@wms.test', 'Collect@123', c2); self.assertEqual(c2.get('/staff/routes/1').status_code, 403)
    def test_sec_csrf_required(self): self.resident(); self.assertEqual(self.c.post('/resident/request', data={'waste_type': 'general', 'address': '12 Test Street'}).status_code, 400)
    def test_sec_headers(self):
        h = self.c.get('/').headers; self.assertIn("default-src 'self'", h['Content-Security-Policy']); self.assertEqual(h['X-Frame-Options'], 'DENY')
    def test_sec_sql_injection_login(self): self.assertIn('Invalid email', self.login("' OR 1=1 --", 'x').get_data(as_text=True))
    def test_sec_xss_escaped(self):
        self.resident(); self.post('/resident/request', {'waste_type': 'general', 'address': '<script>alert(1)</script>'})
        self.assertNotIn('<script>alert(1)</script>', self.c.get('/resident/').get_data(as_text=True))
    def test_sec_photo_path_traversal(self): self.admin(); self.assertEqual(self.c.get('/staff/photo/..%2f..%2fetc%2fpasswd').status_code, 404)
    def test_sec_audit_log_written(self): self.resident(); self.assertTrue(any(r['action'] == 'login' for r in self.q('SELECT * FROM audit_log')))
if __name__ == '__main__': unittest.main()
