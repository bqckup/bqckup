from flask import Blueprint
from flask.templating import render_template

profile = Blueprint('profile', __name__)

@profile.route('/', methods=['GET'])
@profile.route('/index', methods=['GET'])
def index():
    return render_template('docs/index.html', title_bar="Profile User")
