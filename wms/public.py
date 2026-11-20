from flask import Blueprint, render_template, g, redirect
from .db import get_db
from .auth import home_for
bp = Blueprint('public', __name__)
@bp.route('/')
def index():
    if g.user: return redirect(home_for(g.user['role']))
    db = get_db()
    zones = db.execute('SELECT z.name, z.collection_day, (SELECT COUNT(*) FROM bins b WHERE b.zone_id=z.id) bins FROM zones z ORDER BY z.name').fetchall()
    return render_template('index.html', zones=zones)
