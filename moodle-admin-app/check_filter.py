from app.services.moodle import get_course_participants

course_id = 35
print('all')
for p in get_course_participants(course_id, include_suspended=True):
    print(p['id'], 'suspended?', p.get('user_suspended'))

print('\nonly active')
for p in get_course_participants(course_id, include_suspended=False):
    print(p['id'], 'suspended?', p.get('user_suspended'))
