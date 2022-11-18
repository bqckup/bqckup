from flask import Blueprint, request, flash, redirect, url_for, session, render_template, jsonify
from classes.database import Database

backup = Blueprint('bqckup', __name__)

@backup.get('/add')
def view_add():
    return render_template('add_bqckup.html')

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