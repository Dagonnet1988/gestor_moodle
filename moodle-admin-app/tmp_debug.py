from app import create_app
import app.routes.emails as emails_mod

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
    rv = client.get('/emails/send?course_id=1&template=welcome')
    data = rv.data.decode('utf-8')
    idx = data.find('user_ids')
    print(data[idx:idx+400])

emails_mod.get_course_participants = orig
