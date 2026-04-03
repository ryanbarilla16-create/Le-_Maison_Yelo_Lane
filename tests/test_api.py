import pytest
from app import app, db
from models import User

@pytest.fixture
def client():
    # Configure app for testing
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' # Use in-memory DB for safe testing
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            # db.session.remove()
            # db.drop_all()

def test_menu_endpoint(client):
    """Test if the menu API responds with a 200 OK and valid JSON."""
    response = client.get('/api/menu')
    assert response.status_code == 200
    assert isinstance(response.json, list)

def test_bestsellers_endpoint(client):
    """Test if the bestsellers API loads correctly."""
    response = client.get('/api/menu/bestsellers')
    assert response.status_code == 200
    assert isinstance(response.json, list)
    
def test_signup_validation(client):
    """Test that signup requires complete data."""
    response = client.post('/api/auth/signup', json={})
    assert response.status_code == 400
    assert "No data provided" in response.json.get("message", "")
