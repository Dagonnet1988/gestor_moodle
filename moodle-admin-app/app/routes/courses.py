import math
from flask import Blueprint, render_template, request, flash, redirect, url_for
from app.decorators.auth import login_required
from app.services.moodle import (get_courses, get_course_by_id,
                                 get_course_participants,
                                 allow_extra_attempts_in_course,
                                 get_users_with_exhausted_attempts)
from app.services.auth import get_user_highest_role

courses_bp = Blueprint('courses', __name__, url_prefix='/courses')


@courses_bp.route('/')
@login_required
def index():
    """Lista de cursos con paginación."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
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
    """Detalle de un curso con participantes.

    El parámetro `status` en la query puede ser ``active`` (por defecto),
    ``suspended`` o ``all``; controla si se incluyen usuarios
    suspendidos en la lista.
    """
    status = request.args.get('status', 'active')

    try:
        course = get_course_by_id(course_id)
        if not course:
            flash('Curso no encontrado', 'warning')
            return redirect(url_for('courses.index'))
        
        participants = get_course_participants(course_id, status=status)
        exhausted_ids = get_users_with_exhausted_attempts(course_id)
        for p in participants:
            p['has_exhausted_attempts'] = p['id'] in exhausted_ids
        # override participant roles with user's global top roles
        from app.services.auth import get_role_label, get_user_top_roles
        for p in participants:
            top = get_user_top_roles(p['id'], n=2)
            if top:
                p['role_names'] = [get_role_label(r['shortname']) for r in top]
                p['role_shortname'] = top[0]['shortname']
                p['role_name'] = p['role_names'][0]
            else:
                p['role_names'] = [get_role_label('student')]
                p['role_name'] = p['role_names'][0]
    except Exception as e:
        flash(f'Error al obtener curso: {e}', 'danger')
        from flask import redirect, url_for
        return redirect(url_for('courses.index'))

    return render_template(
        'courses/detail.html',
        course=course,
        participants=participants,
        status=status,
    )


@courses_bp.route('/<int:course_id>/allow_retry', methods=['POST'])
@login_required
def allow_retry(course_id):
    """Concede un intento adicional en los quizzes del curso donde el
    usuario ya agotó sus intentos.  Modifica mdl_quiz_overrides."""
    user_id = request.form.get('user_id', type=int)
    if not user_id:
        flash('Usuario inválido', 'warning')
        return redirect(url_for('courses.detail', course_id=course_id))

    try:
        updated = allow_extra_attempts_in_course(course_id, user_id)
        if updated:
            names = ', '.join(u['quiz_name'] for u in updated)
            flash(f'Intento extra concedido en: {names}', 'success')
        else:
            flash('No se encontraron cuestionarios donde el usuario haya agotado intentos.', 'info')
    except Exception as e:
        flash(f'Error al conceder intento extra: {e}', 'danger')

    return redirect(url_for('courses.detail', course_id=course_id))
