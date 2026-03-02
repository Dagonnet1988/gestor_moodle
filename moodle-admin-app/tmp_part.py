from app.services.moodle import get_course_participants
print('count', len(get_course_participants(35)))
print(get_course_participants(35)[:3])
