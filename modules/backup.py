from flask import Blueprint, request, render_template, jsonify, redirect, url_for
from classes.database import Database
from classes.bqckup import Bqckup, ConfigExceptions
from classes.storage import Storage
from classes.s3 import s3
from constant import SITE_CONFIG_PATH

backup = Blueprint('bqckup', __name__)

# filename is object name
@backup.post('/get_download_link')
def get_download_link(): 
    link = s3(storage_name=request.form.get('storage_name')).getLinkDownload(request.form.get('file_name'))
    
    if not link:
        return jsonify(error=True, message="Failed to get download link")
    
    return jsonify(error=False, url=link)

@backup.get('/backup_now/<name>')
def backup_now(name):
    try:
        from classes.queue import Queue
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
    try:
        storages = Storage().list()
    except:
        return jsonify(message="Failed to fetch storages"), 500
    else:
        return jsonify(storages)

@backup.post('/save')
def save():
    if Bqckup().is_limit():
        return redirect(url_for('index'))

    import json, os, ruamel.yaml as yaml
    post = request.form
    backup = json.loads(post.get('backup'))
    database = json.loads(post.get('database'))
    options = json.loads(post.get('options'))

    paths =  [p for p in backup['path'].split('\n') if len(p)]
    file_name =  os.path.join(SITE_CONFIG_PATH, f"{backup['name']}.yml")
    
    with open(file_name,"w+") as stream:
        content = {
            "bqckup": {
                'name': backup['name'],
                'path': paths,
                "options": options
            }
        }
        
        if database['user']:
            content['bqckup']['database'] = database
            
        if options['provider'] == 'local':
            options['storage'] = 'local'
        
        yaml = yaml.YAML()
        yaml.indent(sequence=4, offset=2)
        yaml.dump(content, stream)
        
    try:
        Bqckup().validate_config(backup['name'])
    except ConfigExceptions as cfgExc:
        os.unlink(file_name)
        return jsonify(error=True, message=str(cfgExc)), 500
    except Exception as e:
        return jsonify(error=True, message=f"Failed to save backup: {e}"), 500
    else:
        return jsonify(message="Success")

@backup.get('/add')
def view_add():
    if Bqckup().is_limit():
        return redirect(url_for('index'))
    return render_template('add_bqckup.html')

@backup.get('/detail/<backup_name>')
def detail(backup_name):
    from classes.bqckup import Bqckup
    backup = Bqckup().detail(backup_name)
    logs = Bqckup().get_logs(backup_name)
    return render_template('detail.html', logs=logs,  backup=backup)

@backup.post('/test_db_connection')
def test_db_connection():
    try:
        post = request.form
        Database(type=post.get('type')).test_connection(
            credentials={
                'user': post.get('user'),
                'host': post.get('host'),
                'password': post.get('password'),
                'name': post.get('name')
            }
        )
    except Exception as e:
        return jsonify(error=True, message=f"Can't connect to your database, {e}")
    else:
        return jsonify(error=False, message="Connection Success")