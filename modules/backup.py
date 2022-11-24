from flask import Blueprint, request, render_template, jsonify
from classes.database import Database
from classes.storage import Storage
from classes.s3 import s3
from config import BQ_PATH

backup = Blueprint('bqckup', __name__)

@backup.post('/get_download_link')
def get_download_link():    
    link = s3().getLinkDownload(request.form['file'])
    if not link:
        return jsonify(error=True, message="Failed to get download link")
    return jsonify(error=False, url=link)

@backup.get('/backup_now/<name>')
def backup_now(name):
    try:
        from classes.queue import Queue
        from classes.bqckup import Bqckup
        queue = Queue()
        bqckup = Bqckup()
        backup = bqckup.detail(name)
        queue.add(name, bqckup.do_backup, backup['file_name'])
    except Exception as e:
        return jsonify(error=True, message=f"Backup failed: {e}"), 500
    else:
        return jsonify(error=False, message=f"Backup Queued")
    
@backup.get('/get_storages')
def get_storages():
    storages = Storage().list()
    
    if not storages:
        return jsonify(message="No Storages found"), 404
    
    return jsonify(storages)

@backup.post('/save')
def save():
    import json, os, ruamel.yaml as yaml
    post = request.form
    backup = json.loads(post.get('backup'))
    database = json.loads(post.get('database'))
    options = json.loads(post.get('options'))

    paths =  [p for p in backup['path'].split('\n') if len(p)]

    with open(
        os.path.join(
            BQ_PATH,
            '.config',
            'bqckups',
            f"{backup['name']}.yml"
        ),
        "w+"
    ) as stream:
        content = {
            "bqckup": {
                'name': backup['name'],
                'path': paths,
                "database": database,
                "options": options
            }
        }
        
        yaml = yaml.YAML()
        yaml.indent(sequence=4, offset=2)
        yaml.dump(content, stream)
    
    return jsonify(message="Success")

@backup.get('/add')
def view_add():
    return render_template('add_bqckup.html')

@backup.get('/detail/<backup_name>')
def detail(backup_name):
    from classes.bqckup import Bqckup
    from classes.log import Log
    backup = Bqckup().detail(backup_name)
    logs = Log().list(backup_name)
    return render_template('detail.html', logs=logs,  backup=backup)

@backup.post('/test_db_connection')
def test_db_connection():
    try:
        post = request.form
        Database(type=post.get('type')).test_connection(
            credentials={
                'user': post.get('user'),
                'host': post.get('host'),
                'user': post.get('user'),
                'name': post.get('name')
            }
        )
    except Exception as e:
        return jsonify(error=True, message=f"Can't connect to your database, {e}")
    else:
        return jsonify(error=False, message="Connection Success")