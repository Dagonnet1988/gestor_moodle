import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.decorators.auth import login_required
from app.services.moodle import (
    get_courses, get_users, get_course_by_id, get_user_by_id,
    enrol_user_in_course, unenrol_user_from_course, get_course_participants
)
from app.services.logger import log_action

enrolments_bp = Blueprint('enrolments', __name__, url_prefix='/enrolments')


@enrolments_bp.route('/')
@login_required
def index():
    """Página de inscripciones - seleccionar curso."""
    try:
        courses, _ = get_courses(page=1, per_page=500)
    except Exception as e:
        flash(f'Error al obtener cursos: {e}', 'danger')
        courses = []
    
    return render_template('enrolments/index.html', courses=courses)


@enrolments_bp.route('/enrol', methods=['GET', 'POST'])
@login_required
def enrol():
    """Inscribir un usuario en un curso."""
    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        course_id = request.form.get('course_id', type=int)
        
        if not user_id or not course_id:
            flash('Debe seleccionar un usuario y un curso', 'warning')
            return redirect(url_for('enrolments.index'))
        
        try:
            enrol_user_in_course(user_id, course_id)
            
            user = get_user_by_id(user_id)
            course = get_course_by_id(course_id)
            
            log_action(
                action='ENROL_USER',
                target_type='enrolment',
                target_id=course_id,
                details={
                    'user_id': user_id,
                    'username': user['username'] if user else str(user_id),
                    'course': course['fullname'] if course else str(course_id)
                }
            )
            
            flash(f'Usuario inscrito exitosamente en el curso', 'success')
            
            # TODO: Enviar correo de bienvenida automático
            
        except ValueError as e:
            flash(str(e), 'warning')
        except Exception as e:
            flash(f'Error al inscribir usuario: {e}', 'danger')
        
        return redirect(url_for('courses.detail', course_id=course_id))
    
    # GET - mostrar formulario
    course_id = request.args.get('course_id', type=int)
    try:
        courses, _ = get_courses(page=1, per_page=500)
        users, _ = get_users(page=1, per_page=1000, status='active')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        courses, users = [], []
    
    return render_template('enrolments/enrol.html', 
        courses=courses, users=users, selected_course_id=course_id)


@enrolments_bp.route('/unenrol', methods=['POST'])
@login_required
def unenrol():
    """Desinscribir un usuario de un curso."""
    user_id = request.form.get('user_id', type=int)
    course_id = request.form.get('course_id', type=int)
    
    if not user_id or not course_id:
        flash('Datos incompletos', 'warning')
        return redirect(url_for('enrolments.index'))
    
    try:
        user = get_user_by_id(user_id)
        course = get_course_by_id(course_id)
        
        unenrol_user_from_course(user_id, course_id)
        
        log_action(
            action='UNENROL_USER',
            target_type='enrolment',
            target_id=course_id,
            details={
                'user_id': user_id,
                'username': user['username'] if user else str(user_id),
                'course': course['fullname'] if course else str(course_id)
            }
        )
        
        flash('Usuario desinscrito correctamente', 'success')
    except ValueError as e:
        flash(str(e), 'warning')
    except Exception as e:
        flash(f'Error al desinscribir: {e}', 'danger')
    
    return redirect(url_for('courses.detail', course_id=course_id))


@enrolments_bp.route('/bulk', methods=['GET', 'POST'])
@login_required
def bulk_enrol():
    """Inscripción masiva desde CSV."""
    if request.method == 'POST':
        course_id = request.form.get('course_id', type=int)
        csv_file = request.files.get('csv_file')
        
        if not course_id or not csv_file:
            flash('Debe seleccionar un curso y subir un archivo CSV', 'warning')
            return redirect(url_for('enrolments.bulk_enrol'))
        
        try:
            course = get_course_by_id(course_id)
            if not course:
                flash('Curso no encontrado', 'warning')
                return redirect(url_for('enrolments.bulk_enrol'))
            
            # Leer CSV
            content = csv_file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))
            
            success_count = 0
            error_count = 0
            errors = []
            
            for row in reader:
                username = row.get('username', '').strip()
                if not username:
                    continue
                
                try:
                    # Buscar usuario por username
                    from app.services.db import execute_query, table
                    user = execute_query(
                        f"SELECT id FROM {table('user')} WHERE username = %s AND deleted = 0",
                        (username,), fetchone=True
                    )
                    
                    if not user:
                        errors.append(f"Usuario '{username}' no encontrado")
                        error_count += 1
                        continue
                    
                    enrol_user_in_course(user['id'], course_id)
                    success_count += 1
                    
                except ValueError as e:
                    errors.append(f"{username}: {e}")
                    error_count += 1
            
            log_action(
                action='BULK_ENROL',
                target_type='enrolment',
                target_id=course_id,
                details={
                    'course': course['fullname'],
                    'success': success_count,
                    'errors': error_count
                }
            )
            
            flash(f'Inscripción masiva completada: {success_count} exitosos, {error_count} errores', 
                  'success' if error_count == 0 else 'warning')
            
            if errors:
                for err in errors[:10]:  # Mostrar primeros 10 errores
                    flash(err, 'danger')
                    
        except Exception as e:
            flash(f'Error al procesar CSV: {e}', 'danger')
        
        return redirect(url_for('courses.detail', course_id=course_id))
    
    # GET
    try:
        courses, _ = get_courses(page=1, per_page=500)
    except Exception:
        courses = []
    
    return render_template('enrolments/bulk.html', courses=courses)
