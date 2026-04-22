import traceback
from app import app

try:
    with app.test_client() as client:
        response = client.get('/')
        print(response.data.decode('utf-8'))
except Exception as e:
    traceback.print_exc()
