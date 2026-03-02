from app import create_app

def render_user(user_id):
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        rv = client.get(f'/users/{user_id}')
        return rv.get_data(as_text=True)

if __name__ == '__main__':
    html = render_user(267)
    print(html)
