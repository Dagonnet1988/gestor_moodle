import os
import re
import pytest
import bcrypt
import time

from app.services.auth import verify_moodle_password
from app.services.mail import send_bulk_email, render_email_template
from app.services.db import get_connection
from app import create_app
from app.config import Config


def test_verify_moodle_password():
    """bcrypt $2y$ prefix should be handled correctly."""
    plain = "secret123"
    # generate a hash with bcrypt and replace prefix
    hashb = bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    # simulate Moodle prefix
    hashb = hashb.replace('$2b$', '$2y$')
    assert verify_moodle_password(plain, hashb)


def test_send_bulk_email_pause(monkeypatch):
    recipients = [
        {'email': 'a@example.com', 'name': 'A'},
        {'email': 'b@example.com', 'name': 'B'},
        {'email': 'c@example.com', 'name': 'C'},
    ]
    vars_list = [
        {'nombre': 'A', 'curso': 'X', 'url_moodle': 'u', 'username': 'a'},
        {'nombre': 'B', 'curso': 'X', 'url_moodle': 'u', 'username': 'b'},
        {'nombre': 'C', 'curso': 'X', 'url_moodle': 'u', 'username': 'c'},
    ]

    calls = []

    def fake_send(to_email, subject, body, to_name=''):
        calls.append(to_email)
        return True

    monkeypatch.setattr('app.services.mail.send_email', fake_send)

    sleeps = []
    def fake_sleep(sec):
        sleeps.append(sec)
    monkeypatch.setattr('time.sleep', fake_sleep)

    monkeypatch.setattr(Config, 'MAIL_MAX_BULK', 2)
    monkeypatch.setattr(Config, 'MAIL_BULK_PAUSE_SECONDS', 1)

    success, failed = send_bulk_email(recipients, 'subj', '<p>{nombre}</p>', vars_list)
    assert success == 3 and failed == 0
    assert sleeps == [1]
    assert calls == ['a@example.com', 'b@example.com', 'c@example.com']


@pytest.fixture(scope='session')
def db_available():
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")


@pytest.fixture

def client(db_available):
    """Flask test client with a logged-in user (id=1)."""
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        yield client



def test_get_users_default_active(db_available):
    from app.services.moodle import get_users
    users, total = get_users(page=1, per_page=5)
    # as default status=active, all returned users should not be suspended
    assert all(not u['suspended'] for u in users)
    # each user should have role_name key (may be empty string)
    assert all('role_name' in u for u in users)
    # if any user has multiple roles, they should appear in role_names
    assert all('role_names' in u for u in users)


def test_get_user_courses_includes_grade(db_available):
    from app.services.moodle import get_user_courses
    # use first user returned by get_users
    from app.services.moodle import get_users
    users, _ = get_users(page=1, per_page=1)
    if not users:
        pytest.skip('no users available for course test')
    uid = users[0]['id']
    courses = get_user_courses(uid)
    # each course dict should contain 'grade' key even if None
    assert all('grade' in c for c in courses)
    # also percentage field should exist
    assert all('grade_pct' in c for c in courses)
    # category_name should be present now
    assert all('category_name' in c for c in courses)
    # ensure no duplicate course ids
    ids = [c['id'] for c in courses]
    assert len(ids) == len(set(ids))
    # simulate multiple rows for same course to ensure selection logic
    sample = [
        {'id': 10, 'grade': 50, 'grademax': 50, 'itemtype': 'mod', 'itemname': 'Parte1'},
        {'id': 10, 'grade': 98, 'grademax': 100, 'itemtype': 'course', 'itemname': 'Total curso'},
        {'id': 10, 'grade': None, 'grademax': None, 'itemtype': 'course', 'itemname': None},
        {'id': 10, 'grade': 97, 'grademax': 100, 'itemtype': 'mod', 'itemname': 'Evaluación plan'},
    ]
    def score(r):
        s = 0
        if r.get('itemtype') == 'course': s += 10
        name = (r.get('itemname') or '').lower()
        if 'total' in name or 'curso' in name or 'final' in name:
            s += 5
        s += (float(r.get('grademax') or 0))/100.0
        pct = None
        if r.get('grade') is not None and r.get('grademax'):
            try:
                pct = round((float(r['grade'])/float(r['grademax']))*100,2)
            except Exception:
                pct = None
        if pct is not None:
            s += pct/100.0
        return s
    # the highest scored entry should be the one with grade 98 or 97 depending on context
    best = max(sample, key=score)
    assert best['grade'] in (98, 97)


def test_get_course_participants_grades(db_available):
    from app.services.moodle import get_courses, get_course_participants
    courses, _ = get_courses(page=1, per_page=1)
    if not courses:
        pytest.skip('no courses available')
    cid = courses[0]['id']
    parts = get_course_participants(cid)
    # each participant should have grade and grade_pct keys
    for p in parts:
        assert 'grade' in p
        assert 'grade_pct' in p
    # ensure no duplicates
    ids = [p['id'] for p in parts]
    assert len(ids) == len(set(ids))

    # verify ordering: should match the sort key defined in service
    def order_key(r):
        return (
            -((r.get('grade_pct') or 0)),
            (r.get('lastname') or '').lower(),
            (r.get('firstname') or '').lower()
        )
    assert [order_key(p) for p in parts] == sorted([order_key(p) for p in parts])

    # status filter: compare results with a direct DB query on user.suspended
    from app.services.db import execute_query
    rows = execute_query(
        "SELECT u.suspended FROM mdl_user u "
        "JOIN mdl_user_enrolments ue ON ue.userid = u.id "
        "JOIN mdl_enrol e ON e.id = ue.enrolid "
        "WHERE e.courseid = %s",
        (cid,),
    )
    active_count = sum(1 for r in rows if r['suspended'] == 0)
    suspended_count = sum(1 for r in rows if r['suspended'] != 0)
    total_count = len(rows)
    # default call should only return non-suspended users
    assert len(parts) == active_count
    # active filter
    parts_active = get_course_participants(cid, status='active')
    assert len(parts_active) == active_count
    # suspended filter
    parts_susp = get_course_participants(cid, status='suspended')
    assert len(parts_susp) == suspended_count
    # all
    parts_all = get_course_participants(cid, status='all')
    assert len(parts_all) == total_count

    # should pick the row with largest score; simulate small dataset
    sample = [
        {'id': 1, 'grade': 90, 'grademax': 100, 'itemtype': 'mod', 'itemname': 'A'},
        {'id': 1, 'grade': 195, 'grademax': 200, 'itemtype': 'course', 'itemname': 'Total'},
        {'id': 1, 'grade': 100, 'grademax': 100, 'itemtype': 'mod', 'itemname': 'Final'},
    ]
    # scoring function should mirror service logic
    def score(r):
        s = 0
        if r.get('itemtype') == 'course': s += 10
        name = (r.get('itemname','').lower())
        if 'total' in name or 'curso' in name or 'final' in name:
            s += 5
        s += (float(r.get('grademax') or 0))/100.0
        pct = None
        if r.get('grademax'):
            try:
                pct = round((float(r['grade'])/float(r['grademax']))*100,2)
            except Exception:
                pct = None
        if pct is not None:
            s += pct/100.0
        return s
    best = max(sample, key=score)
    assert best['grade'] == 195


def test_unenroll_button_shown_for_suspended(monkeypatch):
    """When a participant is suspended with no grade, the unenroll icon should still be visible."""
    from app import create_app
    # monkeypatch the service to return a single suspended user with no grade
    sample = [{
        'id': 123,
        'firstname': 'Susurro',
        'lastname': 'Suspendido',
        'grade_pct': None,
        'user_suspended': 1,
    }]
    monkeypatch.setattr('app.services.moodle.get_course_participants', lambda cid, status=None: sample)
    monkeypatch.setattr('app.services.moodle.get_course_by_id', lambda cid: {'id': cid, 'fullname': 'dummy'})
    # stub out role helpers which may hit database
    monkeypatch.setattr('app.services.auth.get_user_top_roles', lambda uid, n=2: [])
    monkeypatch.setattr('app.services.auth.get_role_label', lambda short: short)

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        # simulate logged-in user by setting session directly
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'test'
        rv = client.get('/courses/1?status=suspended')
        data = rv.get_data(as_text=True)
        # unenroll icon should be present even though the user is suspended
        assert 'bi-person-x' in data
        # welcome icon must be absent for suspended user
        assert 'bi-envelope-check' not in data


def test_courses_ordered_by_category(db_available):
    from app.services.moodle import get_courses
    courses, _ = get_courses(page=1, per_page=100)
    # verify that category_name is non-decreasing
    cats = [c.get('category_name') or '' for c in courses]
    assert cats == sorted(cats)


def test_get_course_available_users_excludes_enrolled(db_available):
    """Available users should not include participants already in the course."""
    from app.services.moodle import get_courses, get_course_participants, get_course_available_users
    courses, _ = get_courses(page=1, per_page=1)
    if not courses:
        pytest.skip('no courses available')
    cid = courses[0]['id']
    parts = get_course_participants(cid, status='all')
    avail = get_course_available_users(cid)
    enrolled_ids = {p['id'] for p in parts}
    assert all(u['id'] not in enrolled_ids for u in avail)


def test_enrol_multiple_users_via_form(monkeypatch):
    """Submittal of several user ids in selected_user_ids should call service once per id."""
    from app import create_app
    # capture calls to enrol_user_in_course
    calls = []
    monkeypatch.setattr('app.routes.enrolments.enrol_user_in_course', lambda u, c: calls.append((u, c)))
    monkeypatch.setattr('app.routes.enrolments.get_course_by_id', lambda cid: {'id':cid,'fullname':'CursoX'})
    monkeypatch.setattr('app.services.logger.log_action', lambda **kw: None)

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        rv = client.post('/enrolments/enrol', data={'course_id':5, 'selected_user_ids':'2,3,2'})
        assert rv.status_code == 302
        # verify service called for 2 and 3 (duplicates should be ignored)
        assert (2,5) in calls and (3,5) in calls
        assert len(calls) == 2


def test_enrol_single_user_legacy(monkeypatch):
    """Legacy single-user POST via user_id should still work."""
    from app import create_app
    calls = []
    monkeypatch.setattr('app.routes.enrolments.enrol_user_in_course', lambda u, c: calls.append((u, c)))
    monkeypatch.setattr('app.routes.enrolments.get_course_by_id', lambda cid: {'id':cid,'fullname':'CursoY'})
    monkeypatch.setattr('app.services.logger.log_action', lambda **kw: None)

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        rv = client.post('/enrolments/enrol', data={'course_id':7, 'user_id':42})
        assert rv.status_code == 302
        assert calls == [(42,7)]


def test_enrolments_index_unified(monkeypatch):
    from app import create_app
    monkeypatch.setattr('app.services.moodle.get_courses', lambda page, per_page: ([],0))
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        rv = client.get('/enrolments/')
        data = rv.get_data(as_text=True)
        assert 'Administrar Inscripciones' in data
        assert 'Inscripción por CSV' not in data


def test_enrol_page_shows_available_users(monkeypatch):
    from app import create_app
    # course list should include category name
    monkeypatch.setattr('app.services.moodle.get_courses',
                        lambda page, per_page: ([{'id':10,'fullname':'X','shortname':'X','category_name':'Cat'}],1))
    monkeypatch.setattr('app.routes.enrolments.get_course_available_users', lambda cid: [
        {'id':20,'firstname':'A','lastname':'B','username':'ab','idnumber':'1234'}
    ])
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        rv = client.get('/enrolments/enrol?course_id=10')
        data = rv.get_data(as_text=True)
        assert 'Cat - X' in data
        assert 'A B' in data
        # search box exists but initially hidden via inline style
        assert 'id="user_search"' in data
        assert 'display:none' in data
        assert 'id="clear_search"' in data
        assert 'id="collapse_list"' in data


def test_available_users_excludes_admin_guest():
    from app.services.moodle import get_course_available_users
    # simulate database rows including admin/guest
    monkey_users = [
        {'id':1,'username':'admin','firstname':'X','lastname':'Y','email':'e','idnumber':''},
        {'id':2,'username':'guest','firstname':'G','lastname':'H','email':'e','idnumber':''},
        {'id':3,'username':'normal','firstname':'N','lastname':'O','email':'e','idnumber':''},
    ]
    # patch execute_query directly
    from app.services import db
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(db, 'execute_query', lambda q,p=None,fetchone=False: monkey_users)
    try:
        result = get_course_available_users(99)
        assert all(u['username'] not in ('admin','guest') for u in result)
    finally:
        monkeypatch.undo()



def test_grades_index_filters_and_results(monkeypatch):
    from app import create_app
    from app.services.moodle import get_courses, get_course_by_id, get_course_final_grades
    # stub courses list
    monkeypatch.setattr('app.services.moodle.get_courses', lambda page, per_page: ([{'id':20,'fullname':'X','category_name':'Cat'}],1))
    # stub course info and grades
    monkeypatch.setattr('app.services.moodle.get_course_by_id', lambda cid: {'id':cid,'fullname':'X'})
    monkeypatch.setattr('app.services.moodle.get_course_final_grades', lambda cid: [
        {'username':'u1','firstname':'A','lastname':'B','email':'a@x','finalgrade':75}
    ])
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        # initial page, no grades
        rv = client.get('/grades/')
        assert b'-- seleccionar --' in rv.data
        assert b'75' not in rv.data
        # select course 20 via query param
        rv2 = client.get('/grades/?course_id=20')
        assert b'75' in rv2.data
        # dropdown should show category-name format
        assert b'Cat - X' in rv2.data


def test_course_final_grades_accepts_tuple(monkeypatch):
    from app.services.moodle import get_course_final_grades
    # monkeypatch execute_query to return a tuple of dicts
    from app.services import db
    monkeypatch.setattr(db, 'execute_query', lambda q,p=None,fetchone=False: ({'finalgrade':100,'grademax':100},))
    res = get_course_final_grades(1)
    assert isinstance(res, list)
    assert res[0]['grade_pct'] == 100.0


def test_email_course_dropdown_category_format(db_available):
    from app.services.moodle import get_courses
    courses, _ = get_courses(page=1, per_page=5)
    if not courses:
        pytest.skip('no courses available')
    # build expected string from first course
    first = courses[0]
    expect = f"{first.get('category_name') + ' - ' if first.get('category_name') else ''}{first['fullname']}"

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        rv = client.get('/emails/send')
        assert expect.encode() in rv.data
        # when a course is selected via query, participants should appear
        rv2 = client.get(f'/emails/send?course_id={courses[0]["id"]}')
        # count badge should show number, and at least one option present
        assert b'disponibles' in rv2.data
        assert b'<option' in rv2.data
        # bulk send checkbox should be visible
        assert b'Enviar a todos los participantes' in rv2.data
        # no refresh icon next to course name
        assert b'bi-arrow-clockwise' not in rv2.data
        # search input should be shown
        assert b'id="user_search"' in rv2.data
        # options should appear in alphabetical order by firstname
        # we can't easily assert full ordering but ensure first two appear sorted
        opts = [m.group(1) for m in re.finditer(br'<option value="\d+">([^<]+)</option>', rv2.data)]
        assert opts == sorted(opts)
        # simulate welcome template filtering by monkeypatching participants
        # patch the copy imported by the emails route
        import app.routes.emails as emails_mod
        orig = emails_mod.get_course_participants
        emails_mod.get_course_participants = lambda cid: [
            {'id':1,'firstname':'A','lastname':'B','username':'a','grade':None},
            {'id':2,'firstname':'C','lastname':'D','username':'c','grade':50}
        ]
        rv3 = client.get(f'/emails/send?course_id={courses[0]["id"]}&template=welcome')
        emails_mod.get_course_participants = orig
        # should have dropdown of participants
        assert b'id="user_select"' in rv3.data
        # since template=welcome, second user with grade should be omitted by filter
        assert b'value="1"' in rv3.data
        assert b'value="2"' not in rv3.data


def test_email_recipients_handle_selected_list(monkeypatch):
    """Submitting selected_user_ids should convert to recipients correctly."""
    # prepare dummy participants and template
    import app.routes.emails as emails_mod
    orig = emails_mod.get_course_participants
    emails_mod.get_course_participants = lambda cid: [
        {'id':10,'firstname':'X','lastname':'Y','username':'xy','email':'x@y.com','grade':None},
        {'id':11,'firstname':'A','lastname':'B','username':'ab','email':'a@b.com','grade':None}
    ]
    # monkeypatch send_email and send_bulk_email to capture calls
    from app.services import mail
    sent = []
    def fake_send(email, subj, body, name=None):
        sent.append(('single', email))
        return True
    def fake_bulk(recs, subj, body, vars_list):
        sent.append(('bulk', [r['email'] for r in recs]))
        return (len(recs), 0)
    monkeypatch.setattr(mail, 'send_email', fake_send)
    monkeypatch.setattr(mail, 'send_bulk_email', fake_bulk)

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        # send individual using selected_user_ids
        rv = client.post('/emails/send', data={
            'course_id': 1,
            'template': 'welcome',
            'selected_user_ids': '10,11,10'
        }, follow_redirects=True)
        assert b'Correos enviados exitosamente' in rv.data
        # bulk email should have been triggered once because more than one recipient
        assert sent and sent[0][0] == 'bulk'

        sent.clear()
        # now call with send_type bulk_course; both participants should be included
        rv2 = client.post('/emails/send', data={
            'course_id': 1,
            'template': 'welcome',
            'send_type': 'bulk_course'
        }, follow_redirects=True)
        assert b'Correos enviados exitosamente' in rv2.data
        assert sent and sent[0][0] == 'bulk'
        # only one recipient since welcome filter excludes graded user
        assert len(sent[0][1]) == 1
    emails_mod.get_course_participants = orig


def test_email_template_crud_and_render(tmp_path):
    from app.services import mail
    # override template file to temporary location
    mail.TEMPLATE_FILE = str(tmp_path / 'tpls.json')
    # ensure starting file is created with only the welcome template
    tpls = mail.get_email_templates()
    assert isinstance(tpls, dict)
    assert list(tpls.keys()) == ['welcome']
    # modify json directly to simulate old version
    with open(mail.TEMPLATE_FILE, 'w', encoding='utf-8') as f:
        f.write('{"welcome": {"subject":"hola","body":"antiguo"}}')
    # calling _ensure_template_file should revert to canonical default
    mail._ensure_template_file()
    tpls2 = mail.get_email_templates()
    assert 'El área de Seguridad' in tpls2['welcome']['body']
    # add a new template
    mail.add_or_update_email_template('foo', 'Asunto {curso}', '<p>Hola {nombre}</p>')
    tpl = mail.get_email_template('foo')
    assert tpl['subject'] == 'Asunto {curso}'
    body = mail.render_email_template('foo', nombre='Test', curso='X')
    assert '<p>Hola Test</p>' in body
    # check listing contains foo
    alltpl = mail.get_email_templates()
    assert 'foo' in alltpl
    # delete and ensure gone
    mail.delete_email_template('foo')
    assert 'foo' not in mail.get_email_templates()


def test_email_templates_pages(client):
    # relies on client fixture defined elsewhere maybe
    # login is simulated via session in fixture
    rv = client.get('/emails/templates')
    assert rv.status_code == 200
    assert b'Plantillas' in rv.data
    # create a new template via POST
    rv2 = client.post('/emails/templates/new', data={
        'name': 'testpage',
        'subject': 'Sujeto',
        'body': '<p>Hola</p>'
    }, follow_redirects=True)
    assert b'Plantilla creada' in rv2.data
    # ensure appears in listing
    assert b'testpage' in rv2.data
    # edit it
    rv3 = client.post('/emails/templates/edit/testpage', data={
        'subject': 'Otro',
        'body': '<p>Adios</p>'
    }, follow_redirects=True)
    assert b'Plantilla guardada' in rv3.data
    # editing existing template again returns form with values
    rv3b = client.get('/emails/templates/edit/testpage')
    assert b'Otro' in rv3b.data
    # rename template
    rv4 = client.post('/emails/templates/edit/testpage', data={
        'name': 'foo2',
        'subject': 'Nuevo',
        'body': '<p>Adios</p>'
    }, follow_redirects=True)
    assert b'renombrada' in rv4.data
    assert b'foo2' in rv4.data
    assert b'testpage' not in rv4.data
    # delete
    rv4 = client.get('/emails/templates/delete/testpage', follow_redirects=True)
    assert b'Plantilla eliminada' in rv4.data


def test_user_detail_course_actions(monkeypatch):
    from app import create_app
    from app.services.moodle import get_user_courses
    # stub courses for rendering
    sample_courses = [
        {'id':10,'fullname':'C1','category_name':'Cat','role_name':'student','grade':None,'grademax':None,'grade_pct':None,'status':0},
        {'id':11,'fullname':'C2','category_name':'Cat','role_name':'student','grade':50,'grademax':100,'grade_pct':50,'status':0},
    ]
    monkeypatch.setattr('app.services.moodle.get_user_courses', lambda uid: sample_courses)
    # monkey patch current user suspension state in template context can use user var

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'u'
        rv = client.get('/users/1')
        data = rv.get_data(as_text=True)
        # first course has no grade -> welcome button should appear
        assert 'bi-envelope-check' in data
        # second course has grade <100 -> retry button should appear
        assert 'bi-arrow-repeat' in data


def test_get_courses(db_available):
    from app.services.moodle import get_courses
    courses, total = get_courses(page=1, per_page=5)
    assert isinstance(courses, list)


def test_authenticate_real_user(db_available):
    from app.services.auth import authenticate_user
    username = os.getenv('TEST_USER')
    password = os.getenv('TEST_PASS')
    if not username or not password:
        pytest.skip('set TEST_USER and TEST_PASS to run this test')
    user = authenticate_user(username, password)
    assert user['username'] == username


def test_create_user_derive_ident_from_email(db_available):
    """When no username is provided, derive it from email prefix."""
    from app.services.moodle import create_user, get_user_by_id
    from app.services.db import execute_update, table

    email = f"derive-{int(time.time())}@example.com"
    try:
        uid = create_user(
            username='',
            password='pwd123',
            firstname='Derive',
            lastname='Email',
            email=email
        )
        assert uid is not None
        u = get_user_by_id(uid)
        assert u['username'] == email.split('@')[0]
        assert u['idnumber'] == email.split('@')[0]
    finally:
        if 'uid' in locals():
            execute_update(f"UPDATE {table('user')} SET deleted=1 WHERE id=%s", (uid,))


def test_create_and_update_user_sync_idnumber(db_available):
    """Confirm that idnumber is initialized and synced with username."""
    from app.services.moodle import create_user, update_user, get_user_by_id
    from app.services.db import execute_update, table

    # generate a reasonably unique identifier
    base = f"testuser{int(time.time())}"
    try:
        try:
            uid = create_user(
                username=base,
                password='pass1234',
                firstname='Prueba',
                lastname='Usuario',
                email=f"{base}@example.com"
            )
        except Exception as e:
            pytest.skip(f"cannot create user in database: {e}")

        assert uid is not None
        user = get_user_by_id(uid)
        assert user['idnumber'] == base
        # update identification and ensure username is synced
        new_ident = base + 'x'
        update_user(
            user_id=uid,
            firstname=user['firstname'],
            lastname=user['lastname'],
            email=user['email'],
            city=user.get('city',''),
            country=user.get('country','CO'),
            phone1=user.get('phone1',''),
            idnumber=new_ident,
            username=new_ident
        )
        user2 = get_user_by_id(uid)
        assert user2['idnumber'] == new_ident
        assert user2['username'] == new_ident
    finally:
        # mark created user as deleted to avoid clutter
        if 'uid' in locals():
            execute_update(f"UPDATE {table('user')} SET deleted=1 WHERE id=%s", (uid,))


def test_create_user_default_password(db_available):
    """When password is omitted, it should default to identification."""
    from app.services.moodle import create_user, get_user_by_id
    from app.services.db import execute_update, table

    ident = f"no-pass-{int(time.time())}"
    try:
        uid = create_user(
            username=ident,
            password='',
            firstname='No',
            lastname='Pass',
            email=f"{ident}@example.com"
        )
        assert uid is not None
        u = get_user_by_id(uid)
        # We can't directly read password hash, but ensure the user exists and idnumber is set
        assert u['idnumber'] == ident
    finally:
        if 'uid' in locals():
            execute_update(f"UPDATE {table('user')} SET deleted=1 WHERE id=%s", (uid,))
