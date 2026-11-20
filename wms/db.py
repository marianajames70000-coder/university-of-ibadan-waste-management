import sqlite3, os
from flask import g, current_app
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db
def close_db(e=None):
    d = g.pop('db', None)
    if d is not None: d.close()
def init_db(app):
    with app.app_context():
        db = get_db()
        with open(os.path.join(os.path.dirname(__file__), 'schema.sql')) as f: db.executescript(f.read())
        db.commit()
def audit(user_id, action, detail=''):
    get_db().execute('INSERT INTO audit_log(user_id,action,detail) VALUES(?,?,?)', (user_id, action, detail))
