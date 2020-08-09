import re
from flask import request, render_template, flash, redirect, url_for, Blueprint, Response
from flask_login import current_user, login_user, logout_user, login_required

from ..app import db, app
from ..models import *
from ..forms import LoginForm, AccessKeyForm
from ..ldap import ldap_login
from ..audit import log_action
from ..livy import LivyClient
from ..filesystem import list_files, read_file
from ..views.helpers import requires_roles, flash_errors

home = Blueprint('home', __name__)


@home.route('/version')
def health():
    return Response(
        'Version: {}'.format(app.config['VERSION']), mimetype='text/plain')


@home.route('/')
@home.route('/home')
@login_required
def index():
    return render_template('index.html')


@home.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        flash('You are already logged in.')
        return redirect(url_for('home.index'))

    form = LoginForm(request.form)

    if request.method == 'POST' and form.validate():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        try:
            user = ldap_login(username, email, password)
        except Exception as e:
            flash(str(e), 'danger')
            return render_template('login.html', form=form)

        login_user(user)
        log_action('login')
        flash('You have successfully logged in.', 'success')
        return redirect(url_for('home.index'))

    flash_errors(form)
    return render_template('login.html', form=form)


@home.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home.login'))


@home.route('/accesskey', methods=['GET', 'POST'])
@login_required
def access_key():
    form = AccessKeyForm(request.form, obj=current_user)

    if request.method == 'POST' and form.validate():
        current_user.generate_access_key()
        db.session.commit()
        form.access_key.data = current_user.access_key
        flash('Private access key has been regenerated!', 'success')
        return render_template('access_key.html', form=form)

    flash_errors(form)
    return render_template('access_key.html', form=form)


@home.route('/datasets')
@login_required
def datasets():
    return render_template(
        'datasets.html', datasets=Dataset.query.order_by(Dataset.name).all())


@home.route('/apidoc')
@login_required
def api_doc():
    return render_template('api_doc.html')


@home.route('/current_session', methods=['GET', 'POST'])
@login_required
def current_session():
    if request.method == 'POST':
        try:
            LivyClient().update_session_status()
            flash('Session status has been updated!', 'success')
        except:
            db.session.rollback()
            app.logger.exception('Error updating session status')
            flash('Error updating session status', 'danger')
    return render_template('current_session.html', form=request.form)


@home.route('/query/<id>/run', methods=['GET'])
@login_required
def run_query(id):
    query = Query.query.get(int(id))
    parameters = re.findall(r'\$\{(\w+)\}', query.sql)
    return render_template(
        'run_query.html',
        query=query,
        parameters=parameters,
        form=request.form)


@home.route('/report_file')
@login_required
@requires_roles('admin', 'report-viewer')
def report_file():
    config = GlobalConfig.get()
    f = config.reports_location + request.args.get('file')
    log_action('view_report', f)
    return Response(read_file(f), mimetype='text/html')


@home.route('/report')
@login_required
@requires_roles('admin', 'report-viewer')
def report():
    config = GlobalConfig.get()
    filters = {}
    values = {}

    path = config.reports_location
    for name, value in request.args.items():
        if value:
            path += '/' + name + '=' + value
            filters[name] = value

    files = []
    for p in list_files(path, recursively=False):
        if p.endswith('.html'):
            files.append(p[len(config.reports_location):])
        for name, value in re.findall(r'([^/]+)=([^/]+)', p):
            if not name in filters:
                filters[name] = None
            if not name in values:
                values[name] = set([value])
            else:
                values[name].add(value)

    return render_template(
        'report.html', filters=filters, values=values, files=files)
