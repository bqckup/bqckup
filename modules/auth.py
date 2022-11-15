from datetime import timedelta
from flask import Blueprint, request, flash, redirect, url_for, session, render_template
from flask_login import current_user, login_user
from werkzeug.security import generate_password_hash, check_password_hash
from helpers import generate_token


auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    from models import User
    if request.method == 'GET':
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        try:
            User().select().get()
        except:
            return redirect(url_for('auth.register'))

        return render_template('auth/login.html')

    elif request.method == 'POST':
        session.permanent = True
        form = request.form
        username = form.get('username')
        password = form.get('password')

        try:
            user = User().select().where(User.username == username).get()
        except Exception as e:
            print(e)
            flash(f"User {username} not found", "error")
            return redirect(url_for('auth.login'))

        if user and check_password_hash(user.password, password):
            login_user(user, remember=False, duration=timedelta(minutes=1))

            session['check_update'] = True
            session['name'] = user.name

            return redirect(url_for('index'))
        else:
            flash("Wrong username/password", 'error')
            return redirect(url_for('auth.login'))


@auth.route('/register', methods=['GET', 'POST'])
def register():
    from models import User

    if 'username' in session:
        return redirect(url_for('index'))

    if request.method == 'GET':
        try:
            User().select().get()
        except Exception as e:
            return render_template('auth/register.html')

        return redirect(url_for('auth.login'))

    elif request.method == 'POST':
        form = request.form
        name = form.get('name')
        email = form.get('email')
        username = form.get('username')
        password = form.get('password')

        try:
            User().create(
                token=generate_token(20),
                name=name,
                email=email,
                username=username,
                password=generate_password_hash(password)
            )

            flash(f"Register user {username} Success, Please login", 'success')
        except Exception as e:
            print(e)
            flash(f"Register for user {username} failed, cause : {e}", 'error')

        else:
            return redirect(url_for('auth.login'))

        return redirect(url_for('auth.register'))


@auth.route('/change_password', methods=['GET', 'POST'])
def change_password():
    from models import User

    # check if the link is valid token
    code = request.args.get('token')

    if not code:
        flash("Invalid Request", 'error')
        return redirect(url_for('auth.login'))

    user = User().getByTmpCode(code)

    from datetime import datetime

    # check if code still valid
    if not user or datetime.now() > user.forgot_password_time:

        User().resetTmpCode(user.id)

        flash("Invalid Code or code expired", 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        user.password = generate_password_hash(request.form.get('password'))
        user.save()

        User().resetTmpCode(user.id)

        flash("Your password has changed, Try to log in", 'success')
        return redirect(url_for('auth.login'))

    elif request.method == 'GET':
        return render_template('auth/change_password.html')


@auth.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    from models import User
    if 'username' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        form = request.form
        email = form.get('email').strip()
        # check if email exists
        user = User().getByColumn(User.email, email)

        if not user:
            flash(f"{email} not found", 'error')
            return redirect(url_for('auth.forgot_password'))

        # create a code
        code = User().generateTmpCode(user)

        from urllib.parse import urlparse
        from core.mail import Mail

        baseUrl = urlparse(request.base_url)
        linkReset = f"{baseUrl.scheme}://{baseUrl.netloc}/auth/change_password?token={code}"

        # send mail
        data = {
            'target': user.email,
            'subject': 'Reset your password',
            'message': f"Here's the link to reset your password<br>{linkReset}"
        }

        Mail(data).send()

        flash(f"Email was sent to {user.email}", 'success')
        return redirect(url_for('auth.forgot_password'))

    elif request.method == 'GET':
        return render_template('auth/forgot_password.html')
