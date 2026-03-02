from app.services.logger import get_logs

logs, total = get_logs(page=1, per_page=1)
print('logs count', len(logs))
print('total logs', total)
