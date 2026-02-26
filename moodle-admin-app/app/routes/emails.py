from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.decorators.auth import login_required
from app.services.moodle import (
    get_courses, get_course_participants, get_course_by_id,
    get_user_by_id, get_users
)
from app.services.mail import send_email, send_bulk_email, render_email_template
from app.services.logger import log_action
from app.config import Config

emails_bp = Blueprint('emails', __name__, url_prefix='/emails')


@emails_bp.route('/')
@login_required
def index():
    """Página principal de correos."""
    try:
        courses, _ = get_courses(page=1, per_page=500)
    except Exception as e:
        flash(f'Error al obtener cursos: {e}', 'danger')
        courses = []
    
    return render_template('emails/index.html', courses=courses)


@emails_bp.route('/send', methods=['GET', 'POST'])
@login_required
def send():
    """Enviar correo individual o masivo con plantilla."""
    if request.method == 'POST':
        template_name = request.form.get('template', 'welcome')
        course_id = request.form.get('course_id', type=int)
        send_type = request.form.get('send_type', 'individual')  # individual o bulk
        user_ids = request.form.getlist('user_ids')  # Para envío individual o selección múltiple
        
        if not course_id:
            flash('Debe seleccionar un curso', 'warning')
            return redirect(url_for('emails.index'))
        
        try:
            course = get_course_by_id(course_id)
            if not course:
                flash('Curso no encontrado', 'warning')
                return redirect(url_for('emails.index'))
            
            # Determinar destinatarios
            recipients = []
            if send_type == 'bulk_course':
                # Enviar a todos los participantes del curso
                participants = get_course_participants(course_id)
                for p in participants:
                    recipients.append(p)
            elif user_ids:
                # Enviar a usuarios seleccionados
                for uid in user_ids:
                    user = get_user_by_id(int(uid))
                    if user:
                        recipients.append(user)
            
            if not recipients:
                flash('No se encontraron destinatarios', 'warning')
                return redirect(url_for('emails.send'))
            
            # Preparar y enviar
            subject_map = {
                'welcome': f'Bienvenido al curso: {course["fullname"]}',
                'reminder': f'Recordatorio: {course["fullname"]}'
            }
            subject = subject_map.get(template_name, f'Información: {course["fullname"]}')
            
            success = 0
            failed = 0
            
            for recipient in recipients:
                body = render_email_template(
                    template_name,
                    nombre=f"{recipient['firstname']} {recipient['lastname']}",
                    curso=course['fullname'],
                    url_moodle=Config.MOODLE_URL,
                    username=recipient['username']
                )
                
                if send_email(recipient['email'], subject, body, 
                            f"{recipient['firstname']} {recipient['lastname']}"):
                    success += 1
                else:
                    failed += 1
            
            action = 'BULK_EMAIL' if len(recipients) > 1 else 'SEND_EMAIL'
            log_action(
                action=action,
                target_type='email',
                target_id=course_id,
                details={
                    'template': template_name,
                    'course': course['fullname'],
                    'recipients': len(recipients),
                    'success': success,
                    'failed': failed
                }
            )
            
            if failed == 0:
                flash(f'Correos enviados exitosamente: {success} de {len(recipients)}', 'success')
            else:
                flash(f'Envío parcial: {success} exitosos, {failed} fallidos de {len(recipients)}', 'warning')
            
        except Exception as e:
            flash(f'Error al enviar correos: {e}', 'danger')
        
        return redirect(url_for('emails.index'))
    
    # GET
    course_id = request.args.get('course_id', type=int)
    user_id = request.args.get('user_id', type=int)
    template = request.args.get('template', 'welcome')
    
    try:
        courses, _ = get_courses(page=1, per_page=500)
        participants = []
        selected_user = None
        
        if course_id:
            participants = get_course_participants(course_id)
        if user_id:
            selected_user = get_user_by_id(user_id)
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        courses, participants = [], []
        selected_user = None
    
    return render_template('emails/send.html',
        courses=courses, participants=participants,
        selected_course_id=course_id, selected_user=selected_user,
        selected_template=template
    )


@emails_bp.route('/resend/<int:user_id>/<int:course_id>/<template>')
@login_required
def resend(user_id, course_id, template):
    """Reenviar correo de bienvenida o recordatorio."""
    try:
        user = get_user_by_id(user_id)
        course = get_course_by_id(course_id)
        
        if not user or not course:
            flash('Usuario o curso no encontrado', 'warning')
            return redirect(url_for('courses.detail', course_id=course_id))
        
        subject_map = {
            'welcome': f'Bienvenido al curso: {course["fullname"]}',
            'reminder': f'Recordatorio: {course["fullname"]}'
        }
        
        body = render_email_template(
            template,
            nombre=f"{user['firstname']} {user['lastname']}",
            curso=course['fullname'],
            url_moodle=Config.MOODLE_URL,
            username=user['username']
        )
        
        subject = subject_map.get(template, f'Información: {course["fullname"]}')
        
        if send_email(user['email'], subject, body, f"{user['firstname']} {user['lastname']}"):
            log_action(
                action='RESEND_EMAIL',
                target_type='email',
                target_id=user_id,
                details={
                    'template': template,
                    'username': user['username'],
                    'course': course['fullname'],
                    'email': user['email']
                }
            )
            flash(f'Correo de {template} reenviado a {user["email"]}', 'success')
        else:
            flash(f'Error al enviar correo a {user["email"]}', 'danger')
            
    except Exception as e:
        flash(f'Error al reenviar correo: {e}', 'danger')
    
    return redirect(request.referrer or url_for('courses.detail', course_id=course_id))
