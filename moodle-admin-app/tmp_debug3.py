from app import create_app
import app.routes.emails as emails_mod
from app.services.moodle import get_courses

orig = emails_mod.get_course_participants
# use real call
app = create_app(); app.config['TESTING']=True
with app.test_client() as client:
    with client.session_transaction() as s: s['user_id']=1
    courses,_ = get_courses(page=1, per_page=5)
    if courses:
        cid = courses[0]['id']
    else:
        cid = 1
    print('cid',cid)
    rv = client.get(f'/emails/send?course_id={cid}&template=recordatorio')
    data = rv.data.decode('utf-8')
    idx = data.find('user_ids')
    print(data[idx:idx+300])
    print('count options', data.count('<option'))
