from pathlib import Path


def test_healthberg_name_and_export_present(client):
    response = client.get('/')
    assert response.status_code == 200
    assert 'HEALTHBERG' in response.text
    assert 'MEDTERMINAL' not in response.text
    assert 'summaryButton' in response.text
    script = Path(__file__).resolve().parents[1] / 'static' / 'app.js'
    js = script.read_text(encoding='utf-8')
    assert 'exportConsultationSummary' in js
    assert 'healthberg_synthese_' in js


def test_api_reports_version_and_provisional_retention(client):
    result = client.get('/api/health')
    assert result.status_code == 200
    data = result.json()
    assert data['version'] == '0.2.0'
    assert data['retention_days_provisional'] == 730
    assert data['status'] == 'synthetic-demo-only'
