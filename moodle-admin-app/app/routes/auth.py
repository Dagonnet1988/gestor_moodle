from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.services.auth import authenticate_user
from app.services.logger import log_action

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Página de inicio de sesión."""
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Debe ingresar usuario y contraseña.', 'warning')
            return render_template('login.html')
        
        try:
            user = authenticate_user(username, password)
            
            # Crear sesión
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['firstname'] = user['firstname']
            session['lastname'] = user['lastname']
            session['email'] = user['email']
            session['role'] = user['role']
            session['role_name'] = user['role_name']
            
            # Registrar log de acceso
            log_action(
                action='LOGIN',
                details={'message': f"Inicio de sesión exitoso como {user['role']}"}
            )
            
            flash(f"Bienvenido, {user['firstname']} {user['lastname']}", 'success')
            return redirect(url_for('dashboard.index'))
            
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('login.html', username=username)
        except Exception as e:
            flash('Error de conexión con la base de datos. Verifique la configuración.', 'danger')
            return render_template('login.html', username=username)
    
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Cerrar sesión."""
    if 'user_id' in session:
        log_action(action='LOGOUT', details={'message': 'Cierre de sesión'})
    
    session.clear()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('auth.login'))
