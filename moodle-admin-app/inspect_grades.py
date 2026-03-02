from app.services.db import execute_query

rows = execute_query(
    "SELECT gi.id, gi.itemname, gi.itemtype, gi.itemmodule, gi.grademax, gi.grademin, gi.courseid, gg.userid, gg.finalgrade, gg.rawgrade "
    "FROM mdl_grade_items gi "
    "LEFT JOIN mdl_grade_grades gg ON gg.itemid=gi.id AND gg.userid=262 "
    "WHERE gi.courseid=31;"
)
for row in rows:
    print(row)

print("\n--- quiz attempts ---")
rows2 = execute_query(
    "SELECT * FROM mdl_quiz_attempts WHERE userid=262 "
    "AND quiz=(SELECT id FROM mdl_quiz WHERE course=31 LIMIT 1);"
)
for r in rows2:
    print(r)

print("\n--- grade_grades for user---")
rows3 = execute_query(
    "SELECT * FROM mdl_grade_grades WHERE userid=262 "
    "AND itemid IN (SELECT id FROM mdl_grade_items WHERE courseid=31);"
)
for r in rows3:
    print(r)

print("\n--- grade_history for item 92 ---")
rows4 = execute_query(
    "SELECT * FROM mdl_grade_history WHERE itemid=92 AND userid=262;"
)
for r in rows4:
    print(r)
