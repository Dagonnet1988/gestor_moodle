from app.services.moodle import get_course_participants

user_id = 267
for cid in [35, 34, 17, 8, 2, 31]:
    parts = get_course_participants(cid)
    for p in parts:
        if p['id'] == user_id:
            print(f'course {cid} -> grade={p.get("grade")} grademax={p.get("grademax")} pct={p.get("grade_pct")}')
