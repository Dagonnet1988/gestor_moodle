import math
from flask import Blueprint, render_template, request, flash
from app.decorators.auth import login_required
from app.services.moodle import get_courses, get_course_by_id, get_course_participants

courses_bp = Blueprint('courses', __name__, url_prefix='/courses')


@courses_bp.route('/')
@login_required
def index():
    """Lista de cursos con paginación."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    search = request.args.get('search', '').strip()
    
    try:
        courses, total = get_courses(page=page, per_page=per_page, search=search or None)
        total_pages = math.ceil(total / per_page) if total > 0 else 1
    except Exception as e:
        flash(f'Error al consultar cursos: {e}', 'danger')
        courses, total, total_pages = [], 0, 1
    
    return render_template('courses/index.html',
        courses=courses, total=total, page=page,
        per_page=per_page, total_pages=total_pages, search=search
    )


@courses_bp.route('/<int:course_id>')
@login_required
def detail(course_id):
    """Detalle de un curso con participantes."""
    try:
        course = get_course_by_id(course_id)
        if not course:
            flash('Curso no encontrado', 'warning')
            return redirect(url_for('courses.index'))
        
        participants = get_course_participants(course_id)
    except Exception as e:
        flash(f'Error al obtener curso: {e}', 'danger')
        from flask import redirect, url_for
        return redirect(url_for('courses.index'))
    
    return render_template('courses/detail.html', course=course, participants=participants)
