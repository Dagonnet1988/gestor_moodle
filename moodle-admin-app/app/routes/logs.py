import math
import csv
import io
from flask import Blueprint, render_template, request, flash, Response
from app.decorators.auth import login_required, role_required
from app.services.logger import get_logs

logs_bp = Blueprint('logs', __name__, url_prefix='/logs')


@logs_bp.route('/')
@login_required
@role_required('manager', 'coursecreator')
def index():
    """Vista de logs de actividad."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
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
    
    # Tipos de acción para el filtro
    action_types = [
        'LOGIN', 'LOGOUT', 'CREATE_USER', 'EDIT_USER', 'DISABLE_USER', 
        'ENABLE_USER', 'RESET_PASSWORD', 'ENROL_USER', 'UNENROL_USER', 
        'BULK_ENROL', 'SEND_EMAIL', 'BULK_EMAIL', 'RESEND_EMAIL',
        'EXPORT_GRADES', 'EXPORT_DATA'
    ]
    
    return render_template('logs/index.html',
        logs=logs, total=total, page=page, per_page=per_page,
        total_pages=total_pages, filters=filters, action_types=action_types
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
                log['action'] or '',
                log['target_type'] or '',
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
