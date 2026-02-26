from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """Decorador que requiere que el usuario esté autenticado."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Decorador que requiere que el usuario tenga uno de los roles especificados.
    
    Uso:
        @role_required('manager', 'coursecreator')
        def admin_only_view():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Debe iniciar sesión para acceder a esta página.', 'warning')
                return redirect(url_for('auth.login'))
            
            user_role = session.get('role', '')
            if user_role not in allowed_roles:
                flash('No tiene permisos para acceder a esta sección.', 'danger')
                return redirect(url_for('dashboard.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
