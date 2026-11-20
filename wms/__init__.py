import os, secrets
from datetime import timedelta
from flask import Flask, session, request, abort, g, render_template
from .db import close_db, init_db, get_db
def create_app(config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('WMS_SECRET', 'dev-change-me-' + 'x'*16),
        DATABASE=os.path.join(app.instance_path, 'wms.sqlite'), FILL_THRESHOLD=80,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30), SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=2*1024*1024)
    if config: app.config.update(config)
    os.makedirs(app.instance_path, exist_ok=True)
    app.teardown_appcontext(close_db)
    init_db(app)
    from . import auth, resident, staff, public
    for m in (auth, resident, staff, public): app.register_blueprint(m.bp)
    @app.before_request
    def csrf_and_session():
        session.permanent = True
        if request.method == 'POST':
            if not session.get('csrf') or request.form.get('csrf') != session.get('csrf'): abort(400, 'Invalid CSRF token')
        uid = session.get('uid')
        g.user = get_db().execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone() if uid else None
    @app.context_processor
    def inject():
        if 'csrf' not in session: session['csrf'] = secrets.token_hex(16)
        return dict(csrf=session['csrf'], user=g.get('user'))
    @app.after_request
    def headers(r):
        r.headers['X-Content-Type-Options'] = 'nosniff'; r.headers['X-Frame-Options'] = 'DENY'
        r.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'"
        r.headers['Referrer-Policy'] = 'same-origin'; r.headers['Cache-Control'] = 'no-store'
        return r
    @app.errorhandler(403)
    def e403(e): return render_template('error.html', code=403, msg='You are not allowed to view this page.'), 403
    @app.errorhandler(404)
    def e404(e): return render_template('error.html', code=404, msg='Page not found.'), 404
    @app.errorhandler(400)
    def e400(e): return render_template('error.html', code=400, msg=getattr(e, 'description', 'Bad request')), 400
    return app
