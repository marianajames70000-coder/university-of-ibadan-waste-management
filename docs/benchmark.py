"""Route-ordering benchmark used in Chapter 4. Run: python docs/benchmark.py"""
import random, itertools, json, statistics as st
from wms.routing import plan, tour_length, DEPOT
random.seed(33)
res = {'zones': [], 'synthetic': {}}
from wms import create_app
from wms.seed import seed
import tempfile, os
d = tempfile.mkdtemp(); app = create_app({'DATABASE': os.path.join(d, 'b.sqlite')}); seed(app)
from wms.db import get_db
with app.app_context():
    db = get_db()
    for z in db.execute('SELECT * FROM zones').fetchall():
        pts = [(b['lat'], b['lon'], b['id']) for b in db.execute('SELECT * FROM bins WHERE zone_id=? AND fill_pct>=80', (z['id'],))]
        order, nn, naive = plan(pts)
        pp = [(p[0], p[1]) for p in pts]
        best = min(tour_length(list(p)) for p in itertools.permutations(pp)) if len(pp) <= 8 else None
        rnd = st.mean(tour_length(random.sample(pp, len(pp))) for _ in range(300))
        res['zones'].append(dict(zone=z['name'], stops=len(pts), nn=round(nn, 2), naive=round(naive, 2), random=round(rnd, 2), optimal=round(best, 2) if best else None))
for n in (6, 10, 15):
    nn_l, rn_l, gap = [], [], []
    for _ in range(200):
        pts = [(7.35 + random.random()*.1, 3.88 + random.random()*.1, i) for i in range(n)]
        _, nn, naive = plan(pts); nn_l.append(nn); rn_l.append(naive)
    res['synthetic'][n] = dict(nn=round(st.mean(nn_l), 2), unordered=round(st.mean(rn_l), 2), saving_pct=round(100*(1-st.mean(nn_l)/st.mean(rn_l)), 1))
json.dump(res, open('docs/benchmark.json', 'w'), indent=1); print(json.dumps(res, indent=1))
