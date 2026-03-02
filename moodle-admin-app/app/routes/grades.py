import csv
import io
from flask import Blueprint, render_template, request, flash, Response, redirect, url_for, jsonify
from app.decorators.auth import login_required, role_required
from app.services.moodle import (
    get_courses, get_user_grades, get_course_final_grades,
    get_course_by_id, get_user_by_id,
    get_user_by_username, get_user_grades_detail, clone_grades
)
from app.services.logger import log_action

grades_bp = Blueprint('grades', __name__, url_prefix='/grades')


@grades_bp.route('/')
@login_required
def index():
    """Página principal de calificaciones.

    Si se pasa ``course_id`` en la query, también carga las calificaciones
    finales de ese curso para mostrarlas directamente en la misma página.
    """
    try:
        courses, _ = get_courses(page=1, per_page=500)
    except Exception as e:
        flash(f'Error al obtener cursos: {e}', 'danger')
        courses = []

    selected_course = None
    grades = []
    course_id = request.args.get('course_id', type=int)
    if course_id:
        try:
            selected_course = get_course_by_id(course_id)
            if selected_course:
                grades = get_course_final_grades(course_id)
            else:
                flash('Curso no encontrado', 'warning')
        except Exception as e:
            flash(f'Error al obtener calificaciones: {e}', 'danger')

    return render_template('grades/index.html', courses=courses,
                           selected_course=selected_course, grades=grades)


@grades_bp.route('/user/<int:user_id>')
@login_required
def by_user(user_id):
    """Calificaciones de un usuario."""
    try:
        user = get_user_by_id(user_id)
        if not user:
            flash('Usuario no encontrado', 'warning')
            return redirect(url_for('grades.index'))
        
        grades = get_user_grades(user_id)
    except Exception as e:
        flash(f'Error al obtener calificaciones: {e}', 'danger')
        user = None
        grades = []
    
    return render_template('grades/by_user.html', user=user, grades=grades)


@grades_bp.route('/export/course/<int:course_id>')
@login_required
def export_course(course_id):
    """Exportar calificaciones de un curso a CSV."""
    try:
        course = get_course_by_id(course_id)
        grades = get_course_final_grades(course_id)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Usuario', 'Nombre', 'Apellidos', 'Email', 'Nota Final', 'Nota Máxima'])
        
        for g in grades:
            writer.writerow([
                g['username'],
                g['firstname'],
                g['lastname'],
                g['email'],
                f"{g['finalgrade']:.2f}" if g['finalgrade'] is not None else 'Sin nota',
                f"{g['grademax']:.2f}" if g['grademax'] is not None else ''
            ])
        
        log_action(
            action='EXPORT_GRADES',
            target_type='course',
            target_id=course_id,
            details={'course': course['fullname'] if course else str(course_id), 'records': len(grades)}
        )
        
        output.seek(0)
        filename = f"calificaciones_{course['shortname'] if course else course_id}.csv"
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        flash(f'Error al exportar: {e}', 'danger')
        return redirect(url_for('grades.index', course_id=course_id))


# ============================================================
# CLONAR CALIFICACIONES (solo admin – sin log)
# ============================================================

@grades_bp.route('/clone', methods=['GET'])
@login_required
@role_required('manager')
def clone():
    """Página de clonación de calificaciones."""
    source_username = request.args.get('source', '').strip()
    dest_username = request.args.get('dest', '').strip()

    source_user = None
    dest_user = None
    source_grades = []
    dest_grades = []

    if source_username:
        try:
            source_user = get_user_by_username(source_username)
            if source_user:
                source_grades = get_user_grades_detail(source_user['id'])
            else:
                flash(f'Usuario origen "{source_username}" no encontrado.', 'warning')
        except Exception as e:
            flash(f'Error al buscar usuario origen: {e}', 'danger')

    if dest_username:
        try:
            dest_user = get_user_by_username(dest_username)
            if dest_user:
                dest_grades = get_user_grades_detail(dest_user['id'])
            else:
                flash(f'Usuario destino "{dest_username}" no encontrado.', 'warning')
        except Exception as e:
            flash(f'Error al buscar usuario destino: {e}', 'danger')

    # Filtrar solo cursos en común
    common_grades = []
    if source_user and dest_user and source_grades and dest_grades:
        dest_course_ids = {dg['course_id'] for dg in dest_grades}
        common_grades = [sg for sg in source_grades if sg['course_id'] in dest_course_ids]
        if source_grades and not common_grades:
            flash('Los usuarios no comparten ningún curso en común.', 'warning')
    elif source_user and source_grades and not dest_user:
        common_grades = source_grades  # aún no hay destino, mostrar todos

    return render_template('grades/clone.html',
                           source_user=source_user,
                           dest_user=dest_user,
                           source_grades=common_grades,
                           dest_grades=dest_grades,
                           source_username=source_username,
                           dest_username=dest_username)


@grades_bp.route('/clone', methods=['POST'])
@login_required
@role_required('manager')
def clone_execute():
    """Ejecuta la clonación de calificaciones. NO se registra en logs."""
    source_user_id = request.form.get('source_user_id', type=int)
    dest_user_id = request.form.get('dest_user_id', type=int)
    course_ids = request.form.getlist('course_ids', type=int)

    if not source_user_id or not dest_user_id:
        flash('Faltan datos de usuarios.', 'danger')
        return redirect(url_for('grades.clone'))

    if source_user_id == dest_user_id:
        flash('El usuario origen y destino no pueden ser el mismo.', 'warning')
        return redirect(url_for('grades.clone'))

    if not course_ids:
        flash('No seleccionaste ningún curso para clonar.', 'warning')
        return redirect(url_for('grades.clone'))

    try:
        results = clone_grades(source_user_id, dest_user_id, course_ids)
        total = sum(results.values())
        flash(f'Clonación exitosa: {total} registros actualizados en {len(course_ids)} curso(s).', 'success')
    except Exception as e:
        flash(f'Error al clonar calificaciones: {e}', 'danger')

    # Recargar con los mismos usuarios
    src = get_user_by_id(source_user_id)
    dest = get_user_by_id(dest_user_id)
    src_u = src['username'] if src else ''
    dest_u = dest['username'] if dest else ''
    return redirect(url_for('grades.clone', source=src_u, dest=dest_u))
