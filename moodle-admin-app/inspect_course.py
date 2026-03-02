from app.services.db import get_connection, execute_query, table

conn = get_connection()
course = execute_query(f"SELECT id, fullname FROM {table('course')} WHERE shortname='Residuos' LIMIT 1", fetchone=True)
print('course', course)
if course:
    rows = execute_query(f"SELECT id, itemname, itemtype, grademax FROM {table('grade_items')} WHERE courseid=%s", (course['id'],))
    print('grade_items:')
    for r in rows: print(r)
    gr = execute_query(f"SELECT gi.id as itemid, gi.itemname, gg.userid, gg.finalgrade, gi.grademax FROM {table('grade_items')} gi JOIN {table('grade_grades')} gg ON gg.itemid=gi.id WHERE gi.courseid=%s", (course['id'],))
    print('grade_grades:')
    for r in gr: print(r)
