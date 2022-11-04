from flask import Blueprint
from flask.templating import render_template

docs = Blueprint('docs', __name__)

@docs.route('/', methods=['GET'])
@docs.route('/index', methods=['GET'])
def index():
    
    return render_template('docs/index.html', title_bar="Documentation")
