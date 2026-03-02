import math
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.decorators.auth import login_required
from app.services.moodle import (
    get_users, get_user_by_id, create_user, update_user,
    toggle_user_suspension, reset_user_password, get_user_courses,
    user_has_exhausted_attempts
)
from app.services.auth import get_user_highest_role
from app.services.logger import log_action

users_bp = Blueprint('users', __name__, url_prefix='/users')


@users_bp.route('/')
@login_required
def index():
    """Lista de usuarios con paginación y búsqueda."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    search = request.args.get('search', '').strip()
    # por defecto solo activos si no se especifica
    status = request.args.get('status', '') or 'active'
    
    try:
        users, total = get_users(page=page, per_page=per_page, search=search or None, 
                                  status=status or None)
        total_pages = math.ceil(total / per_page) if total > 0 else 1
    except Exception as e:
        flash(f'Error al consultar usuarios: {e}', 'danger')
        users, total, total_pages = [], 0, 1
    
    return render_template('users/index.html',
        users=users,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        search=search,
        status=status
    )


@users_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Crear un nuevo usuario."""
    if request.method == 'POST':
        try:
            ident = request.form.get('username', '').strip()
            # derivar identificador del email si no se proporciona
            if not ident:
                email = request.form.get('email', '').strip()
                ident = email.split('@')[0] if '@' in email else ''
            pwd = request.form.get('password', '').strip()
            user_id = create_user(
                username=ident,
                password=pwd,
                firstname=request.form.get('firstname', '').strip(),
                lastname=request.form.get('lastname', '').strip(),
                email=request.form.get('email', '').strip(),
                country=request.form.get('country', 'CO'),
                city=request.form.get('city', '').strip(),
                phone1=request.form.get('phone1', '').strip()
            )
            
            log_action(
                action='CREATE_USER',
                target_type='user',
                target_id=user_id,
                details={
                    'username': request.form.get('username'),
                    'firstname': request.form.get('firstname'),
                    'lastname': request.form.get('lastname'),
                    'email': request.form.get('email')
                }
            )
            
            flash(f'Usuario creado exitosamente (ID: {user_id})', 'success')
            return redirect(url_for('users.index'))
            
        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            flash(f'Error al crear usuario: {e}', 'danger')
    
    return render_template('users/create.html')


@users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(user_id):
    """Editar un usuario existente."""
    try:
        user = get_user_by_id(user_id)
        if not user:
            flash('Usuario no encontrado', 'warning')
            return redirect(url_for('users.index'))
    except Exception as e:
        flash(f'Error al obtener usuario: {e}', 'danger')
        return redirect(url_for('users.index'))
    
    if request.method == 'POST':
        try:
            ident = request.form.get('idnumber', '').strip() or request.form.get('username', '').strip()
            update_user(
                user_id=user_id,
                firstname=request.form.get('firstname', '').strip(),
                lastname=request.form.get('lastname', '').strip(),
                email=request.form.get('email', '').strip(),
                country=request.form.get('country', 'CO'),
                city=request.form.get('city', '').strip(),
                phone1=request.form.get('phone1', '').strip(),
                idnumber=ident,
                username=ident
            )
            
            log_action(
                action='EDIT_USER',
                target_type='user',
                target_id=user_id,
                details={
                    'firstname': request.form.get('firstname'),
                    'lastname': request.form.get('lastname'),
                    'email': request.form.get('email')
                }
            )
            
            flash('Usuario actualizado correctamente', 'success')
            return redirect(url_for('users.detail', user_id=user_id))
            
        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            flash(f'Error al actualizar usuario: {e}', 'danger')
        
        # Recargar datos del usuario
        user = get_user_by_id(user_id)
    
    return render_template('users/edit.html', user=user)


@users_bp.route('/<int:user_id>')
@login_required
def detail(user_id):
    """Ver detalle de un usuario."""
    try:
        user = get_user_by_id(user_id)
        if not user:
            flash('Usuario no encontrado', 'warning')
            return redirect(url_for('users.index'))
        # si no hay identificación se muestra el mismo username
        if not user.get('idnumber'):
            user['idnumber'] = user['username']
        
        courses = get_user_courses(user_id)
        for c in courses:
            c['has_exhausted_attempts'] = user_has_exhausted_attempts(c['id'], user_id)
        # obtener rol global más alto (utilizado para login) y aplicarlo si la fila de curso no tenga
        highest = get_user_highest_role(user_id)
        default_role_short = highest['shortname'] if highest else None
        default_role_name = highest['name'] if highest else None
        for c in courses:
            if not c.get('role_name'):
                c['role_shortname'] = default_role_short
                c['role_name'] = default_role_name
    except Exception as e:
        flash(f'Error al obtener datos del usuario: {e}', 'danger')
        return redirect(url_for('users.index'))
    
    return render_template('users/detail.html', user=user, courses=courses)


@users_bp.route('/<int:user_id>/toggle', methods=['POST'])
@login_required
def toggle_status(user_id):
    """Habilitar/deshabilitar un usuario."""
    try:
        user = get_user_by_id(user_id)
        if not user:
            flash('Usuario no encontrado', 'warning')
            return redirect(url_for('users.index'))
        
        new_status = not user['suspended']
        toggle_user_suspension(user_id, suspend=new_status)
        
        action = 'DISABLE_USER' if new_status else 'ENABLE_USER'
        log_action(
            action=action,
            target_type='user',
            target_id=user_id,
            details={
                'username': user['username'],
                'new_status': 'suspended' if new_status else 'active'
            }
        )
        
        status_text = 'suspendido' if new_status else 'habilitado'
        flash(f'Usuario {user["firstname"]} {user["lastname"]} {status_text} correctamente', 'success')
        
    except Exception as e:
        flash(f'Error al cambiar estado del usuario: {e}', 'danger')
    
    return redirect(request.referrer or url_for('users.index'))


@users_bp.route('/<int:user_id>/reset-password', methods=['POST'])
@login_required
def reset_password(user_id):
    """Resetear la contraseña de un usuario."""
    new_password = request.form.get('new_password', '')
    
    if len(new_password) < 6:
        flash('La contraseña debe tener al menos 6 caracteres', 'warning')
        return redirect(url_for('users.detail', user_id=user_id))
    
    try:
        user = get_user_by_id(user_id)
        if not user:
            flash('Usuario no encontrado', 'warning')
            return redirect(url_for('users.index'))
        
        reset_user_password(user_id, new_password)
        
        log_action(
            action='RESET_PASSWORD',
            target_type='user',
            target_id=user_id,
            details={'username': user['username']}
        )
        
        flash(f'Contraseña de {user["username"]} actualizada correctamente', 'success')
        
    except Exception as e:
        flash(f'Error al resetear contraseña: {e}', 'danger')
    
    return redirect(url_for('users.detail', user_id=user_id))
