from flask import Blueprint, request, flash, redirect, url_for, session, render_template

backup = Blueprint('bqckup', __name__)

@backup.get('/add')
def view_add():
    return render_template('add_bqckup.html')