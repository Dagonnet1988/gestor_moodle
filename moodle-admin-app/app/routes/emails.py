from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.decorators.auth import login_required
from app.services.moodle import (
    get_courses, get_course_participants, get_course_by_id,
    get_user_by_id, get_users
)
from app.services.mail import (
    send_email, send_bulk_email, render_email_template,
    get_email_templates, get_email_template,
    add_or_update_email_template, delete_email_template,
    _replace_vars
)
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
    # cargar lista de plantillas para el formulario
    templates = get_email_templates()

    if request.method == 'POST':
        template_name = request.form.get('template')
        course_id = request.form.get('course_id', type=int)
        send_type = request.form.get('send_type', 'individual')  # 'bulk_course' or 'individual'
        # user_ids comes from previous dropdown selection; new UI uses hidden field selected_user_ids
        user_ids = request.form.getlist('user_ids')  # still support old field if present
        sel_ids_raw = request.form.get('selected_user_ids', '')
        if sel_ids_raw:
            # parse comma-separated list, ignore empties
            extra = [x for x in sel_ids_raw.split(',') if x]
            user_ids.extend(extra)
        
        # normalize checkbox value
        if send_type == 'on':
            send_type = 'bulk_course'

        if not course_id:
            flash('Debe seleccionar un curso', 'warning')
            return redirect(url_for('emails.index'))
        
        try:
            course = get_course_by_id(course_id)
            if not course:
                flash('Curso no encontrado', 'warning')
                return redirect(url_for('emails.index'))
            
            recipients = []
            if send_type == 'bulk_course':
                participants = get_course_participants(course_id)
                if template_name == 'welcome':
                    participants = [p for p in participants if not p.get('grade')]
                for p in participants:
                    recipients.append(p)
            elif user_ids:
                # remove duplicates if any
                for uid in set(user_ids):
                    try:
                        user = get_user_by_id(int(uid))
                    except (TypeError, ValueError):
                        user = None
                    if user:
                        recipients.append(user)
            
            if not recipients:
                flash('No se encontraron destinatarios', 'warning')
                return redirect(url_for('emails.send'))
            
            # build the full variable dict for this course
            course_vars = {
                'curso': course['fullname'],
                'coursefullname': course['fullname'],
                'courseshortname': course.get('shortname', ''),
                'categoryname': course.get('category_name', ''),
                'url_moodle': Config.MOODLE_URL,
                'courselink': f"{Config.MOODLE_URL}/course/view.php?id={course['id']}",
            }

            # subject and body are taken from the template file
            tpl = templates.get(template_name, {})
            subj = tpl.get('subject', f'Información: {course["fullname"]}')
            subj = _replace_vars(subj, course_vars)
            
            if len(recipients) > 1:
                vars_list = []
                for recipient in recipients:
                    v = dict(course_vars)
                    v.update({
                        'nombre': f"{recipient['firstname']} {recipient['lastname']}",
                        'fullname': f"{recipient['firstname']} {recipient['lastname']}",
                        'firstname': recipient['firstname'],
                        'lastname': recipient['lastname'],
                        'email': recipient['email'],
                        'username': recipient['username'],
                    })
                    vars_list.append(v)
                success, failed = send_bulk_email(recipients, subj,
                                                  render_email_template(template_name),
                                                  vars_list)
                action = 'BULK_EMAIL'
            else:
                recipient = recipients[0]
                body = render_email_template(
                    template_name,
                    nombre=f"{recipient['firstname']} {recipient['lastname']}",
                    fullname=f"{recipient['firstname']} {recipient['lastname']}",
                    firstname=recipient['firstname'],
                    lastname=recipient['lastname'],
                    email=recipient['email'],
                    username=recipient['username'],
                    **course_vars
                )
                subj = _replace_vars(subj, {
                    'nombre': f"{recipient['firstname']} {recipient['lastname']}",
                    'firstname': recipient['firstname'],
                    'lastname': recipient['lastname'],
                })
                success = 1 if send_email(recipient['email'], subj, body,
                                          f"{recipient['firstname']} {recipient['lastname']}") else 0
                failed = 0 if success else 1
                action = 'SEND_EMAIL'
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
            # apply welcome template filter: omit users with any grade
            if template == 'welcome':
                participants = [p for p in participants if not p.get('grade')]
            # sort alphabetically by firstname+lastname for dropdown
            participants.sort(key=lambda p: ((p.get('firstname') or '').lower(), (p.get('lastname') or '').lower()))
        if user_id:
            selected_user = get_user_by_id(user_id)
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        courses, participants = [], []
        selected_user = None
    
    # also provide display name map for selector
    display_map = {k: _display_name(k) for k in templates}
    return render_template('emails/send.html',
        courses=courses, participants=participants,
        selected_course_id=course_id, selected_user=selected_user,
        selected_template=template, templates=templates,
        template_display=display_map
    )


@emails_bp.route('/templates')
@login_required

def templates():
    """Lista todas las plantillas existentes."""
    templates = get_email_templates()
    # convert keys to display names for interface
    display_map = {k: _display_name(k) for k in templates}
    return render_template('emails/templates.html', templates=templates, display_map=display_map)


@emails_bp.route('/templates/new', methods=['GET', 'POST'])
@login_required

def new_template():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        subject = request.form.get('subject', '')
        body = request.form.get('body', '')
        if not name:
            flash('El nombre de la plantilla es requerido', 'warning')
        else:
            add_or_update_email_template(name, subject, body)
            flash('Plantilla creada', 'success')
            return redirect(url_for('emails.templates'))
    return render_template('emails/edit_template.html', name='', subject='', body='')

# helper for display names
_display_names = {
    'welcome': 'Bienvenida',
    'reminder': 'Recordatorio'
}

def _display_name(key):
    return _display_names.get(key, key.capitalize())


@emails_bp.route('/templates/edit/<name>', methods=['GET', 'POST'])
@login_required

def edit_template(name):
    tpl = get_email_template(name) or {'subject': '', 'body': ''}
    if request.method == 'POST':
        newname = request.form.get('name', '').strip()
        subject = request.form.get('subject', '')
        body = request.form.get('body', '')
        # if name changed and not empty, we rename by writing new and deleting old
        if newname and newname != name:
            # copy existing or just overwrite
            add_or_update_email_template(newname, subject, body)
            delete_email_template(name)
            flash('Plantilla renombrada y guardada', 'success')
        else:
            add_or_update_email_template(name, subject, body)
            flash('Plantilla guardada', 'success')
        return redirect(url_for('emails.templates'))
    return render_template('emails/edit_template.html', name=name, subject=tpl['subject'], body=tpl['body'])


@emails_bp.route('/templates/delete/<name>')
@login_required

def delete_template(name):
    delete_email_template(name)
    flash('Plantilla eliminada', 'success')
    return redirect(url_for('emails.templates'))


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
        
        tpl = get_email_template(template) or {}

        course_vars = {
            'curso': course['fullname'],
            'coursefullname': course['fullname'],
            'courseshortname': course.get('shortname', ''),
            'categoryname': course.get('category_name', ''),
            'url_moodle': Config.MOODLE_URL,
            'courselink': f"{Config.MOODLE_URL}/course/view.php?id={course['id']}",
        }
        user_vars = {
            'nombre': f"{user['firstname']} {user['lastname']}",
            'fullname': f"{user['firstname']} {user['lastname']}",
            'firstname': user['firstname'],
            'lastname': user['lastname'],
            'email': user['email'],
            'username': user['username'],
        }
        all_vars = {**course_vars, **user_vars}

        body = render_email_template(template, **all_vars)
        subject = tpl.get('subject', f'Información: {course["fullname"]}')
        subject = _replace_vars(subject, all_vars)
        
        if send_email(user['email'], subject, body, f"{user['firstname']} {user['lastname']}"):
            action_name = 'SEND_REMINDER' if template == 'reminder' else 'RESEND_EMAIL'
            log_action(
                action=action_name,
                target_type='email',
                target_id=user_id,
                details={
                    'template': template,
                    'username': user['username'],
                    'course': course['fullname'],
                    'email': user['email']
                }
            )
            tpl_label = 'recordatorio' if template == 'reminder' else template
            flash(f'Correo de {tpl_label} enviado a {user["email"]}', 'success')
        else:
            flash(f'Error al enviar correo a {user["email"]}', 'danger')
            
    except Exception as e:
        flash(f'Error al reenviar correo: {e}', 'danger')
    
    return redirect(request.referrer or url_for('courses.detail', course_id=course_id))
