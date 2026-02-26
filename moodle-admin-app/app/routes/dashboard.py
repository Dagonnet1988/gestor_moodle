from flask import Blueprint, render_template
from app.decorators.auth import login_required
from app.services.db import execute_query, table

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """Página principal - Dashboard."""
    # Contar usuarios activos
    users_active = execute_query(
        f"SELECT COUNT(*) as total FROM {table('user')} WHERE deleted = 0 AND suspended = 0 AND id > 1",
        fetchone=True
    )['total']
    
    # Contar usuarios suspendidos
    users_suspended = execute_query(
        f"SELECT COUNT(*) as total FROM {table('user')} WHERE deleted = 0 AND suspended = 1",
        fetchone=True
    )['total']
    
    # Contar cursos visibles
    courses_total = execute_query(
        f"SELECT COUNT(*) as total FROM {table('course')} WHERE id > 1 AND visible = 1",
        fetchone=True
    )['total']
    
    # Contar inscripciones activas
    enrolments_total = execute_query(
        f"""SELECT COUNT(*) as total FROM {table('user_enrolments')} ue
            JOIN {table('enrol')} e ON e.id = ue.enrolid
            WHERE ue.status = 0""",
        fetchone=True
    )['total']
    
    # Últimos 10 logs de actividad
    try:
        from app.services.logger import get_logs
        recent_logs, _ = get_logs(page=1, per_page=10)
    except Exception:
        recent_logs = []
    
    return render_template('dashboard.html',
        users_active=users_active,
        users_suspended=users_suspended,
        courses_total=courses_total,
        enrolments_total=enrolments_total,
        recent_logs=recent_logs
    )
