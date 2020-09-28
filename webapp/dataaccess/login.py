from flask_ldap3_login import LDAP3LoginManager, AuthenticationResponseStatus

from .app import app, db
from .models import User

authenticate = None


def init_login_backend():
    global authenticate
    kind = app.config.get('LOGIN_BACKEND', 'ldap')
    if kind == 'ldap':
        ldap_manager = LDAP3LoginManager(app)
        authenticate = ldap_authenticate
    elif kind == 'demo':
        authenticate = demo_authenticate
    else:
        raise Exception(f'Unsupported login backend: {kind}')


def get_or_add_user(username, fullname):
    user = User.query.filter_by(username=username).one_or_none()
    if not user:
        user = User(username, fullname)
        db.session.add(user)
        db.session.commit()
    return user


def ldap_authenticate(username, password):
    response = app.ldap3_login_manager.authenticate(username, password)
    if response.status == AuthenticationResponseStatus.fail:
        raise Exception('Error authenticating with LDAP server')
    return get_or_add_user(username, response.user_info['displayName'])


def demo_authenticate(username, password):
    if username == 'demo@dataplate.io' and password == 'demo':
        return get_or_add_user(username, 'Demo User')
    raise Exception('Wrong user/password combination!')


init_login_backend()