import sys, os, logging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from helpers import getAppPath
from core.rclone import Rclone
from models import Configuration
from flask import Blueprint, jsonify, request
from flask_login import login_required
from flask.templating import render_template


mConfig = Blueprint('mConfig', __name__)

@mConfig.route('/', methods=['GET'])
@mConfig.route('/index', methods=['GET'])
@login_required
def index():
    from core.ojtbackup import OJTBackup

    config = Configuration()

    turn_on_apps = config.generalConfig('turn_on_apps', '')
    cloud_storage = config.generalConfig('cloud_storage', '')
    region_name = config.generalConfig('cloud_storage_region_name', '')
    bucket_name = config.generalConfig('cloud_storage_bucket_name', '')
    url_endpoint = config.generalConfig('cloud_storage_endpoint', '')
    client_key = config.generalConfig('cloud_storage_key', '')
    client_secret = config.generalConfig('cloud_storage_secret', '')
    email_master = config.generalConfig('email_master', '')
    password_email_master = config.generalConfig('password_email_master', '')
    port_email_master = config.generalConfig('port_email_master', '')
    server_disk_limit = config.generalConfig('server_disk_limit', '')
    cloud_storage_limit = config.generalConfig('cloud_storage_limit', '')
    disk_full_notification = config.generalConfig('disk_full_notification', '')
    google_code = config.generalConfig('google_code', '')
    
    google_auth_link = Rclone().getAuthUri()
    google_auth = False
    
    try:
        c = Configuration().select().where(Configuration.name == 'google_config_name').get()
    except: pass
    else:
        config_location = getAppPath() + '/config/' + c.value
        if os.path.isfile(config_location):
            google_auth = True
            

    firstTime = True if not client_key else False

    return render_template('config/index.html',
        title_bar = "Configuration",
        turn_on_apps = turn_on_apps,
        cloud_storage = cloud_storage,
        region_name = region_name,
        url_endpoint = url_endpoint,
        client_key = client_key,
        client_secret = client_secret,
        email_master = email_master,
        password_email_master = password_email_master,
        port_email_master = port_email_master,
        server_disk_limit = server_disk_limit,
        cloud_storage_limit = cloud_storage_limit,
        bucket_name = bucket_name,
        disk_full_notification = disk_full_notification,
        firstTime = firstTime,
        google_auth_link = google_auth_link,
        google_auth = google_auth,
        google_code = google_code,
        is_authorized = OJTBackup().isAuthorized()
    )

@mConfig.route('/save_config', methods=['POST'])
@login_required
def save_config():
    from models import Configuration, User
    post = request.form
    storage = post.get('cloud_storage')
    
    if storage == 'drive':
        from helpers import generate_token
        unique = generate_token(7).lower()
        code = post.get('google_code')
        createConfig = Rclone().createConfig(unique, code)
        
        cfg, cfgCreated = Configuration().get_or_create(
            name='google_config_name',
            defaults={
                'name':'google_config_name',
                'value':unique + '.conf',
                'user_id':User().currentUser().id,
                'backup_id':0
            }
        )
        
        if not cfgCreated:
            configPath = getAppPath() + '/config/' + cfg.value
            
            # remove config if its do exists
            if os.path.exists(configPath):
                os.remove(configPath)

            cfg.name = 'google_config_name'
            cfg.value = unique + '.conf'
            cfg.user_id = User().currentUser().id
            cfg.backup_id = 0
            cfg.save()
        
        if not createConfig:
            return jsonify(error=1, msg="Config can't be created, make sure you put correct credentials")
    
    try:
        for p in post:

            if 'password' in post.get(p):
                if post.get(p) == 'do_not_change':
                    continue
            
            if not len(post.get(p)):
                continue

            value = 1 if post.get(p) == 'on' else post.get(p)
            c , created = Configuration.get_or_create(
                name=p,
                defaults={
                    'value':value,
                    'backup_id':0,
                    'user_id':User().currentUser().id,
                    'backup_id':0
                }
            )

            if not created:
                c.name = p
                c.value = value
                c.user_id = User().currentUser().id
                c.backup_id = 0
                c.save()

    except Exception as e:
        return jsonify(
            error=1,
            msg="Failed add config, because %s" % e
        )

    # renew cron
    turn_on_apps = Configuration().generalConfig('turn_on_apps', 1)

    if post.get('turn_on_apps'):
        from core.ojtbackup import OJTBackup
        OJTBackup().renewCron(turn_on_apps)

    return jsonify(error=0)