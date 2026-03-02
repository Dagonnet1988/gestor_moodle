from app import create_app
import app.routes.emails as emails_mod
from app.services.moodle import get_courses

# patch
orig = emails_mod.get_course_participants
emails_mod.get_course_participants = lambda cid: [
    {'id':1,'firstname':'A','lastname':'B','username':'a','grade':None},
    {'id':2,'firstname':'C','lastname':'D','username':'c','grade':50}
]

app = create_app()
app.config['TESTING'] = True
with app.test_client() as client:
    with client.session_transaction() as s:
        s['user_id'] = 1
    courses,_ = get_courses(page=1, per_page=5)
    if courses:
        cid = courses[0]['id']
    else:
        cid = 1
    print('using cid',cid)
    rv = client.get(f'/emails/send?course_id={cid}&template=welcome')
    data=rv.data.decode('utf-8')
    idx=data.find('user_ids')
    print(data[idx:idx+400])

emails_mod.get_course_participants = orig
