import math
import csv
import io
from flask import Blueprint, render_template, request, flash, Response
from app.decorators.auth import login_required, role_required
from app.services.logger import get_logs

logs_bp = Blueprint('logs', __name__, url_prefix='/logs')

# Etiquetas legibles para cada tipo de acción
ACTION_LABELS = {
    'LOGIN':          'Inicio de sesión',
    'LOGOUT':         'Cierre de sesión',
    'CREATE_USER':    'Crear usuario',
    'EDIT_USER':      'Editar usuario',
    'DISABLE_USER':   'Suspender usuario',
    'ENABLE_USER':    'Habilitar usuario',
    'RESET_PASSWORD': 'Restablecer contraseña',
    'ENROL_USER':     'Inscribir usuario',
    'UNENROL_USER':   'Desinscribir usuario',
    'BULK_ENROL':     'Inscripción masiva',
    'SEND_EMAIL':     'Enviar correo',
    'BULK_EMAIL':     'Correo masivo',
    'RESEND_EMAIL':   'Reenviar correo',
    'SEND_REMINDER':  'Enviar recordatorio',
    'WELCOME_EMAIL':  'Correo de bienvenida',
    'EXPORT_GRADES':  'Exportar calificaciones',
    'EXPORT_DATA':    'Exportar datos',
    'ALLOW_RETRY':    'Permitir reintento',
}

TARGET_TYPE_LABELS = {
    'user':      'Usuario',
    'course':    'Curso',
    'enrolment': 'Inscripción',
    'email':     'Correo',
    'quiz':      'Cuestionario',
}


@logs_bp.route('/')
@login_required
@role_required('manager', 'coursecreator')
def index():
    """Vista de logs de actividad."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    
    filters = {
        'username': request.args.get('username', '').strip() or None,
        'action': request.args.get('action', '').strip() or None,
        'date_from': request.args.get('date_from', '').strip() or None,
        'date_to': request.args.get('date_to', '').strip() or None,
        'target_type': request.args.get('target_type', '').strip() or None,
    }
    
    try:
        logs, total = get_logs(page=page, per_page=per_page, filters=filters)
        total_pages = math.ceil(total / per_page) if total > 0 else 1
    except Exception as e:
        flash(f'Error al obtener logs: {e}', 'danger')
        logs, total, total_pages = [], 0, 1
    
    # Enriquecer logs con etiquetas legibles y detalles parseados
    import json
    for log in logs:
        log['action_label'] = ACTION_LABELS.get(log['action'], log['action'])
        log['target_type_label'] = TARGET_TYPE_LABELS.get(log.get('target_type'), log.get('target_type') or '')
        # Parsear detalles JSON a dict para presentar mejor
        if log.get('details') and isinstance(log['details'], str):
            try:
                log['details_parsed'] = json.loads(log['details'])
            except (json.JSONDecodeError, TypeError):
                log['details_parsed'] = None
        else:
            log['details_parsed'] = None
        
        # Enriquecer con información del usuario si hay user_id
        if log.get('details_parsed') and 'user_id' in log['details_parsed']:
            from app.services.moodle import get_user_by_id
            user_id = log['details_parsed']['user_id']
            try:
                user = get_user_by_id(user_id)
                if user:
                    log['details_parsed']['username'] = user['username']
                    log['details_parsed']['name'] = f"{user['firstname']} {user['lastname']}"
            except Exception:
                pass  # Si falla, continuar sin enriquecer

    return render_template('logs/index.html',
        logs=logs, total=total, page=page, per_page=per_page,
        total_pages=total_pages, filters=filters,
        action_labels=ACTION_LABELS,
        target_type_labels=TARGET_TYPE_LABELS
    )


@logs_bp.route('/export')
@login_required
@role_required('manager')
def export():
    """Exportar logs a CSV."""
    filters = {
        'username': request.args.get('username', '').strip() or None,
        'action': request.args.get('action', '').strip() or None,
        'date_from': request.args.get('date_from', '').strip() or None,
        'date_to': request.args.get('date_to', '').strip() or None,
        'target_type': request.args.get('target_type', '').strip() or None,
    }
    
    try:
        logs, _ = get_logs(page=1, per_page=10000, filters=filters)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Fecha', 'Usuario', 'Acción', 'Tipo Entidad', 'ID Entidad', 'Detalles', 'IP'])
        
        for log in logs:
            writer.writerow([
                log['created_at'].strftime('%Y-%m-%d %H:%M:%S') if log['created_at'] else '',
                log['username'] or '',
                ACTION_LABELS.get(log['action'], log['action']),
                TARGET_TYPE_LABELS.get(log.get('target_type'), log.get('target_type') or ''),
                log['target_id'] or '',
                log['details'] or '',
                log['ip_address'] or ''
            ])
        
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=logs_actividad.csv'}
        )
    except Exception as e:
        flash(f'Error al exportar logs: {e}', 'danger')
        from flask import redirect, url_for
        return redirect(url_for('logs.index'))
