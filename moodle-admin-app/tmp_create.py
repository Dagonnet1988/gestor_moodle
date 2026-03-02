from app.services.moodle import create_user
import time

email = f"test-{int(time.time())}@example.com"
try:
    print("calling create_user with blank username")
    create_user(username='', password='pwd123', firstname='F', lastname='L', email=email)
    print("success")
except Exception as e:
    print("error", type(e), e)
