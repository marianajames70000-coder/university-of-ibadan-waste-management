"""Demo data. Run: python -m wms.seed"""
import random
from werkzeug.security import generate_password_hash
from . import create_app
from .db import get_db
ZONES = [('UI Campus', 'Monday', 7.3775, 3.9470), ('Agbowo', 'Tuesday', 7.3989, 3.9124), ('Bodija', 'Wednesday', 7.4290, 3.9086),
         ('Sango', 'Thursday', 7.4210, 3.9220), ('Mokola', 'Friday', 7.4030, 3.8970)]
def seed(app):
    with app.app_context():
        db = get_db()
        if db.execute('SELECT COUNT(*) FROM zones').fetchone()[0]: return
        random.seed(33)
        for i, (n, d, la, lo) in enumerate(ZONES, 1):
            db.execute('INSERT INTO zones(name,collection_day) VALUES(?,?)', (n, d))
            for j in range(1, 7):
                db.execute('INSERT INTO bins(zone_id,label,kind,capacity_l,fill_pct,lat,lon) VALUES(?,?,?,?,?,?,?)',
                    (i, f'{n.replace(" ","")[:3].upper()}-{j:02d}', random.choice(['general', 'general', 'recyclable', 'organic']), random.choice([240, 660, 1100]),
                     random.choice([15, 30, 45, 60, 82, 88, 93, 97]), la + random.uniform(-.006, .006), lo + random.uniform(-.006, .006)))
        pw = lambda p: generate_password_hash(p)
        db.execute("INSERT INTO users(name,email,password_hash,role) VALUES('Municipal Admin','admin@wms.test',?, 'admin')", (pw('Admin@12345'),))
        for n, e in (('Musa Collector', 'collector1@wms.test'), ('Tunde Driver', 'collector2@wms.test')):
            db.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?, 'collector')", (n, e, pw('Collect@123')))
        for n, e, z in (('Ade Resident', 'resident1@wms.test', 1), ('Ngozi Resident', 'resident2@wms.test', 2)):
            db.execute("INSERT INTO users(name,email,password_hash,role,zone_id) VALUES(?,?,?, 'resident',?)", (n, e, pw('Resident@123'), z))
        for z in range(1, 6):
            for m, kg in (('plastic', 40), ('paper', 55), ('glass', 20), ('metal', 12), ('organic', 90)):
                db.execute('INSERT INTO recycling_log(zone_id,material,kg,logged_by) VALUES(?,?,?,1)', (z, m, kg + random.randint(0, 25)))
        db.commit()
if __name__ == '__main__': seed(create_app()); print('Seeded.')
