from pathlib import Path
from app import portal

STATIC=Path(__file__).parents[1]/'static'

def test_complete_professional_roles_seeded():
    roles={u[3] for u in portal.SEED_USERS}
    assert {'doctor','nurse','pharmacist','lab','dentist','optician','radiologist','podiatrist','orthotist','patient','family'}<=roles

def test_login_exposes_all_care_roles():
    js=(STATIC/'app.js').read_text()
    assert "['pharmacist','lab','radiologist','optician','podiatrist','orthotist','nurse']" in js
    assert "state.accounts.filter(a=>a.role===role" in js

def test_doctor_workspace_has_four_quick_actions():
    js=(STATIC/'app.js').read_text()
    for title in ('Importer une ordonnance','Demander des analyses','Voir les résultats','Imagerie & soins'):
        assert "ajClinicalAction('"+title in js
    assert 'ajImportSection' in js and 'ajLabSection' in js

def test_provider_workspaces_prioritize_qr():
    js=(STATIC/'app.js').read_text()
    assert 'function ajPharmacyWorkspace()' in js
    assert 'function ajLabWorkspace()' in js
    assert 'Le patient présente son QR Ajour' in js
    assert "!['pharmacist','lab'].includes(role)" in js

def test_html_version_and_responsive_navigation():
    html=(STATIC/'index.html').read_text()
    css=(STATIC/'ajour.css').read_text()
    assert 'Application Mac 0.9.7' in html
    assert 'id="mobileNav"' in html
    assert '@media(max-width:600px)' in css

def test_doctor_forms_keep_identity_confirmation():
    js=(STATIC/'journeys.js').read_text()
    assert 'name="patient_ack" required' in js
    assert 'name="confirm_identity" required' in js
    assert 'ajPdfImportForm' in js
