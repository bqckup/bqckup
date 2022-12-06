from modules.auth import auth
from modules.backup import backup
from classes.server import Server
from classes.s3 import s3
from helpers import today24Format, timeSince, bytes_to
from config import *
import sys, logging, os, ruamel.yaml as rYaml
from datetime import timedelta
from flask.json import jsonify
from flask import Flask, render_template, request, redirect, url_for
from classes.storage import Storage
from werkzeug.utils import secure_filename


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
    currentVersion = "1.0.0"

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
    from classes.auth import Auth
    
    allowed_path = ['login', 'static', 'setup']
    if not Auth.is_authorized() and (request.path in allowed_path and '/' != request.path):
        return jsonify(message="Access blocked"), 401

@app.get('/setup')
def setup():
    return render_template('wizard.html')

"""
Create key
Validate the config is it success connected to s3
"""
@app.post('/setup/save')
def save_setup():
    # Write security key
    try:
        with open(os.path.join(BQ_PATH, '.key'), 'w+') as f:
            f.write(request.form.get('key'))
            f.close()
            
        # Storage config
        
        if len(request.files.getlist('config_storage')) > 0:
            for cs in request.files.getlist('config_storage'):
                if not cs.filename.endswith('.yml'):
                    return jsonify(message="Config storage must be .yml file"), 400
                cs.save(os.path.join(BQ_PATH, 'config', 'storages.yml'))
                
        if len(request.files.getlist('config_storage')) <= 0:
            with open(os.path.join(BQ_PATH, 'config', 'storages.yml'), 'w+') as f:
                config_content = {
                    "storages": {
                        request.form.get('name'): {
                            "bucket": request.form.get('bucket'),
                            "access_key_id": request.form.get('client_id'),
                            "secret_access_key": request.form.get('client_secret'),
                            "region": request.form.get('region'),
                            "endpoint": request.form.get('endpoint_url'),
                            "primary": "yes"
                        }
                    }
                }
                yaml = rYaml.YAML()
                yaml.indent(sequence=4, offset=2)
                yaml.dump(config_content, f)
            
        # Test connection    
        try:
            _s3 = s3(storage_name=request.form.get('name'))
            _s3.list()
        except Exception as e:
            print(e)
            return jsonify(message="Failed to connect to your s3 account"), 500
        
        # Backup config
        if len(request.files.getlist('config_bqckup')) > 0:
            for cb in request.files.getlist('config_bqckup'):
                if not cb.filename.endswith('.yml'):
                    return jsonify(message="Backup config must be .yml file"), 400
                cb.save(os.path.join(BQ_PATH, 'config', 'bqckups', secure_filename(cb.filename)))
                
        return jsonify(message=f"Success"), 200
    except Exception as e:
        return jsonify(message=f"Failed to save config, {str(e)}"), 500
        
        
        
    

@app.get("/do_update")
def do_update():
    pass

@app.get("/")
@app.get("/index")
# @cache.cached(timeout=60)
def index():
    from classes.auth import Auth
    from classes.bqckup import Bqckup
    
    if not Auth.is_authorized():
        return redirect(url_for('auth.login'))


    if not os.path.exists(os.path.join(BQ_PATH, 'config', 'storages.yml')) or not Storage().get_primary_storage():
        return redirect(url_for('setup'))

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


@app.template_filter('get_base_name')
def get_base_name(path):
    return os.path.basename(path)

@app.template_filter('time_since')
def time_since(unix):
    from helpers import time_since
    return time_since(unix)

# if __name__ == "__main__":
#     from models.log import Log, database
    
#     if not os.path.exists(os.path.join(BQ_PATH, 'database', 'bqckup.db')):
#         os.system(f"touch {os.path.join(BQ_PATH, 'database', 'bqckup.db')} && chmod 755 {os.path.join(BQ_PATH, 'database', 'bqckup.db')}")
#         database.connect()
#         database.create_tables([Log])
#         database.close()
        
#     app.run(host="0.0.0.0", debug=True, port=9393)
# else:
#     logging.basicConfig(
#         filename="Bqckup.log",
#         level=logging.INFO,
#         format="%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s",
#     )
    # logging.basicConfig(filename='demo.log', level=logging.DEBUG)
    # gunicorn_logger = logging.getLogger("gunicorn.error")
    # app.logger.handlers = gunicorn_logger.handlers
    # app.logger.setLevel(gunicorn_logger.level)
