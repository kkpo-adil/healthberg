from pathlib import Path


def test_ajour_multi_profile_frontend(client):
    response = client.get('/')
    assert response.status_code == 200
    assert '<title>Ajour' in response.text
    assert 'authScreen' in response.text and 'pageBody' in response.text
    assert 'mobileNav' in response.text
    assert '/static/ajour.css' in response.text
    source = (Path(__file__).resolve().parents[1] / 'static' / 'app.js').read_text()
    assert all(role in source for role in ('family', 'pharmacist', 'doctor', 'lab'))
    assert 'function patientHome()' in source
    assert "['dashboard','story','journeys','team']" in source


def test_local_version(client):
    data = client.get('/api/health').json()
    assert data['version'] == '0.9.7'
    assert data['status'] == 'synthetic-demo-only'
    assert data['retention_days_provisional'] == 730
    assert data['real_data_allowed'] is False


def test_ajour_assets(client):
    assert client.get('/static/ajour.css').status_code == 200
    assert client.get('/static/ajour-mark.svg').status_code == 200
