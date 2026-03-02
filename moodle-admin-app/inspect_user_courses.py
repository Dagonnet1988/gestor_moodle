from app.services.moodle import get_user_courses

uid = 267
courses = get_user_courses(uid)
for c in courses:
    print(c)
