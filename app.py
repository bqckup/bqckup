from modules.auth import auth
from modules.backup import backup
from classes.server import Server
from helpers import today24Format, timeSince, bytes_to
from config import *
import sys, logging, os
from datetime import timedelta
from flask.json import jsonify
from decouple import config
from flask import Flask, render_template, request, redirect, url_for
from classes.storage import Storage

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))

# SECRET_KEY=os.urandom(24)
SECRET_KEY="secret_key"

app = Flask(__name__)

app.permanent_session_lifetime = timedelta(minutes=30)
app.secret_key = SECRET_KEY
# app.cache_type = "SimpleCache"
# app.cache_default_timeout = 300

app.register_blueprint(auth, url_prefix="/auth/")
app.register_blueprint(backup, url_prefix="/backup/")

# cache = Cache(app)

# assign global variable
# ref : https://stackoverflow.com/a/43336023
@app.context_processor
def globalVariable():
    currentUrl = request.url
    currentUrlSplit = request.url.split("/")
    currentTime = today24Format()
    currentVersion = config("VERSION")

    return dict(
        currentUrl=currentUrl,
        currentUrlSplit=currentUrlSplit,
        currentTime=currentTime,
        currentVersion=currentVersion,
    )

@app.errorhandler(500)
def page_internal_error(e):
    return render_template("500.html"), 500

@app.errorhandler(401)
def page_unauthorized(e):
    return redirect(url_for('auth.login'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.before_request
def before_request():
    pass
    from classes.auth import Auth
    if not Auth.is_authorized() and ('login' not in request.path and 'static' not in request.path and '/' != request.path):
        return jsonify(message="Access blocked"), 401


@app.route("/do_update", methods=["GET"])
def do_update():
    pass

@app.route("/", methods=["GET"])
@app.route("/index", methods=["GET"])
# @cache.cached(timeout=60)
def index():
    from classes.auth import Auth
    from classes.bqckup import Bqckup
    
    if not Auth.is_authorized():
        return redirect(url_for('auth.login'))

    if not Storage().get_primary_storage():
        return redirect(url_for('mConfig.index'))

    _server_storage = Server().get_storage_information()
    
    server_storage = {
        "used": bytes_to('g', _server_storage.used),
        "free": bytes_to('g', _server_storage.free),
        "total": bytes_to('g', _server_storage.total),
    }
    
    return render_template(
        "index.html",
        server_storage=server_storage,
        bqckups=Bqckup().list(),
    )

# jinja
@app.template_filter("tSince")
def tSince(s):
    if not s:
        return "-"
    return timeSince(s)


@app.template_filter("humanReadableSize")
def humanReadableSize(s):
    if not isinstance(s, int):
        return "-"

    from hurry.filesize import size, alternative

    return size(s, system=alternative)


@app.template_filter('time_since')
def time_since(unix):
    from helpers import time_since
    return time_since(unix)

if __name__ == "__main__":
    from models.log import Log, database
    
    if not os.path.exists(os.path.join(BQ_PATH, 'database', 'bqckup.db')):
        os.system(f"touch {os.path.join(BQ_PATH, 'database', 'bqckup.db')} && chmod 755 {os.path.join(BQ_PATH, 'database', 'bqckup.db')}")
        database.connect()
        database.create_tables([Log])
        database.close()
        
    app.run(host="0.0.0.0", debug=True, port=9393)
else:
    logging.basicConfig(
        filename="Bqckup.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s",
    )
    # logging.basicConfig(filename='demo.log', level=logging.DEBUG)
    # gunicorn_logger = logging.getLogger("gunicorn.error")
    # app.logger.handlers = gunicorn_logger.handlers
    # app.logger.setLevel(gunicorn_logger.level)
