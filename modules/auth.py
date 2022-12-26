import os
from constant import BQ_PATH
from flask import Blueprint, request, flash, redirect, url_for, session, render_template

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    # from models import User
    if request.method == 'GET':
        if not os.path.exists(os.path.join(BQ_PATH, 'config', 'storages.yml')):
            return redirect(url_for('setup'))
        return render_template('auth/login.html')

    elif request.method == 'POST':
        from classes.auth import Auth
        from pathlib import Path
        
        
        session.permanent = True
        form = request.form
        key = form.get('key')
        
        if Auth.authorize(key):
            session['name'] = 'Bqckup'
            return redirect(url_for('index'))
        
            
        legit = Path(os.path.join(BQ_PATH, 'key')).read_text()
        flash(f"Authentication failed {legit} and {key}", "error")
        return redirect(url_for('auth.login'))
        
            
    
@auth.get('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))