import csv
import io
from flask import Blueprint, render_template, request, flash, Response
from app.decorators.auth import login_required
from app.services.moodle import (
    get_courses, get_user_grades, get_course_final_grades,
    get_course_by_id, get_user_by_id
)
from app.services.logger import log_action

grades_bp = Blueprint('grades', __name__, url_prefix='/grades')


@grades_bp.route('/')
@login_required
def index():
    """Página principal de calificaciones."""
    try:
        courses, _ = get_courses(page=1, per_page=500)
    except Exception as e:
        flash(f'Error al obtener cursos: {e}', 'danger')
        courses = []
    
    return render_template('grades/index.html', courses=courses)


@grades_bp.route('/course/<int:course_id>')
@login_required
def by_course(course_id):
    """Calificaciones de un curso."""
    try:
        course = get_course_by_id(course_id)
        if not course:
            flash('Curso no encontrado', 'warning')
            from flask import redirect, url_for
            return redirect(url_for('grades.index'))
        
        grades = get_course_final_grades(course_id)
    except Exception as e:
        flash(f'Error al obtener calificaciones: {e}', 'danger')
        course = None
        grades = []
    
    return render_template('grades/by_course.html', course=course, grades=grades)


@grades_bp.route('/user/<int:user_id>')
@login_required
def by_user(user_id):
    """Calificaciones de un usuario."""
    try:
        user = get_user_by_id(user_id)
        if not user:
            flash('Usuario no encontrado', 'warning')
            from flask import redirect, url_for
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
        from flask import redirect, url_for
        return redirect(url_for('grades.by_course', course_id=course_id))
