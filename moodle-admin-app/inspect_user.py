from app.services.db import execute_query

uid = 267
print('courses and grades for user', uid)
rows = execute_query(
    "SELECT c.id,c.fullname,c.shortname,gg.finalgrade,gi.grademax,gi.itemtype,gi.itemname "
    "FROM mdl_user_enrolments ue "
    "JOIN mdl_enrol e ON e.id=ue.enrolid "
    "JOIN mdl_course c ON c.id=e.courseid "
    "LEFT JOIN mdl_grade_grades gg ON gg.userid=ue.userid "
    "LEFT JOIN mdl_grade_items gi ON gi.id=gg.itemid AND gi.courseid=c.id "
    "WHERE ue.userid=%s", (uid,)
)
for r in rows:
    print(r)

# show raw grade_items/grades for suspect course 35
print("\nraw grade_items for course 35")
rows3 = execute_query(
    "SELECT gi.id, gi.itemname, gi.grademax, gg.userid, gg.finalgrade "
    "FROM mdl_grade_items gi "
    "LEFT JOIN mdl_grade_grades gg ON gg.itemid=gi.id AND gg.userid=%s "
    "WHERE gi.courseid=35", (uid,)
)
for r in rows3:
    print(r)

print('\nquiz attempts with 100%?')
rows2 = execute_query(
    "SELECT qa.id, qa.quiz, qa.userid, qa.sumgrades FROM mdl_quiz_attempts qa "
    "WHERE qa.userid=%s AND qa.sumgrades>=99.99", (uid,)
)
for r in rows2:
    print(r)
