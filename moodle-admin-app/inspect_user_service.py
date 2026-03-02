from app.services.moodle import get_course_participants
from app.services.db import execute_query

uid = 267
# print all courses as before
courses = execute_query(
    "SELECT DISTINCT c.id FROM mdl_course c "
    "JOIN mdl_enrol e ON e.courseid=c.id "
    "JOIN mdl_user_enrolments ue ON ue.enrolid=e.id "
    "WHERE ue.userid=%s", (uid,)
)
for c in courses:
    cid = c['id']
    parts = get_course_participants(cid)
    for p in parts:
        if p['id'] == uid:
            print('course', cid, '->', p)

# additional explicit checks
for cid in [35, 8, 34, 31]:
    print('explicit check', cid)
    parts = get_course_participants(cid)
    for p in parts:
        if p['id']==uid:
            print('  ', p)
