import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.decorators.auth import login_required
from app.services.moodle import (
    get_courses, get_course_by_id, get_user_by_id,
    enrol_user_in_course, unenrol_user_from_course, get_course_participants,
    get_course_available_users
)
from app.services.mail import (
    send_email, render_email_template, get_email_template, _replace_vars
)
from app.services.logger import log_action
from app.config import Config

enrolments_bp = Blueprint('enrolments', __name__, url_prefix='/enrolments')


def _send_welcome(user, course):
    """Send the welcome e-mail to a freshly enrolled user.

    Silently catches any exception so that an SMTP failure never prevents
    the enrolment itself from succeeding.  Returns *True* on success.
    """
    try:
        tpl = get_email_template('welcome') or {}
        variables = {
            'nombre': f"{user['firstname']} {user['lastname']}",
            'fullname': f"{user['firstname']} {user['lastname']}",
            'firstname': user['firstname'],
            'lastname': user['lastname'],
            'email': user['email'],
            'username': user['username'],
            'curso': course['fullname'],
            'coursefullname': course['fullname'],
            'courseshortname': course.get('shortname', ''),
            'categoryname': course.get('category_name', ''),
            'url_moodle': Config.MOODLE_URL,
            'courselink': f"{Config.MOODLE_URL}/course/view.php?id={course['id']}",
        }
        body = render_email_template('welcome', **variables)
        subject = _replace_vars(
            tpl.get('subject', f"Bienvenido al curso: {course['fullname']}"),
            variables,
        )
        ok = send_email(
            user['email'], subject, body,
            f"{user['firstname']} {user['lastname']}",
        )
        if ok:
            log_action(
                action='WELCOME_EMAIL',
                target_type='email',
                target_id=user['id'],
                details={
                    'username': user['username'],
                    'course': course['fullname'],
                    'email': user['email'],
                },
            )
        return ok
    except Exception as exc:
        print(f"[WARN] Welcome email failed for {user.get('username')}: {exc}")
        return False


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
    """Inscribir uno o varios usuarios en un curso.

    La vista combina inscripción individual y masiva. En la petición GET se
    muestra un selector de cursos y, si se ha elegido uno, una lista de usuarios
    activos no suspendidos que aún no están inscritos en ese curso. El usuario
    puede apilar selecciones en un listado dinámico; el formulario POST recibe
    los identificadores concatenados en ``selected_user_ids``.
    """
    if request.method == 'POST':
        course_id = request.form.get('course_id', type=int)
        # el formulario puede enviar un único usuario antiguo o varios nuevos
        single = request.form.get('user_id', type=int)
        multi = request.form.get('selected_user_ids', '')
        user_ids = []
        if single:
            user_ids.append(single)
        if multi:
            for part in multi.split(','):
                try:
                    uid = int(part)
                    if uid not in user_ids:
                        user_ids.append(uid)
                except ValueError:
                    continue
        
        if not course_id or not user_ids:
            flash('Debe seleccionar al menos un usuario y un curso', 'warning')
            return redirect(url_for('enrolments.index'))
        
        course = get_course_by_id(course_id)
        success = 0
        emails_ok = 0
        for uid in user_ids:
            try:
                enrol_user_in_course(uid, course_id)
                success += 1
                user = get_user_by_id(uid)
                log_action(
                    action='ENROL_USER',
                    target_type='enrolment',
                    target_id=course_id,
                    details={
                        'user_id': uid,
                        'username': user['username'] if user else str(uid),
                        'course': course['fullname'] if course else str(course_id)
                    }
                )
                # Send welcome email automatically
                if user and course:
                    if _send_welcome(user, course):
                        emails_ok += 1
            except ValueError as e:
                flash(f'[{uid}] {e}', 'warning')
            except Exception as e:
                flash(f'Error al inscribir usuario {uid}: {e}', 'danger')
        
        if success:
            msg = f'{success} usuario(s) inscritos correctamente'
            if emails_ok:
                msg += f' — {emails_ok} correo(s) de bienvenida enviados'
            flash(msg, 'success')
        return redirect(url_for('courses.detail', course_id=course_id))
    
    # GET → preparar datos para selección
    course_id = request.args.get('course_id', type=int)
    try:
        courses, _ = get_courses(page=1, per_page=500)
        available_users = []
        if course_id:
            # sólo usuarios activos y no inscritos
            available_users = get_course_available_users(course_id)
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        courses, available_users = [], []

    return render_template('enrolments/enrol.html', 
        courses=courses, users=available_users, selected_course_id=course_id)


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
            emails_ok = 0
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

                    # Send welcome email automatically
                    full_user = get_user_by_id(user['id'])
                    if full_user and course:
                        if _send_welcome(full_user, course):
                            emails_ok += 1
                    
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
                    'errors': error_count,
                    'emails_sent': emails_ok
                }
            )
            
            msg = f'Inscripción masiva completada: {success_count} exitosos, {error_count} errores'
            if emails_ok:
                msg += f' — {emails_ok} correo(s) de bienvenida enviados'
            flash(msg, 'success' if error_count == 0 else 'warning')
            
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
