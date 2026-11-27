"""Ajour 0.9.5 acceptance: explicit consent, provider slots, nurse routes, retention."""
from datetime import datetime, timedelta, timezone
from app import portal, db

def test_patient_releases_one_use_provider_code(client,login_as,post):
    login_as('patient');r=post('/api/practice/patient-code',{})
    assert r.status_code==200,r.text
    code=r.json()['code'];assert 'Marie' not in code
    login_as('doctor');r=post('/api/practice/link',{'code':code})
    assert r.status_code==200,r.text
    assert r.json()['approved_by']=='patient'
    assert post('/api/practice/link',{'code':code}).status_code==400
    assert post('/api/practice/link',{'code':'AJ-LINK-malformed123456789'}).status_code==400

def test_provider_invites_patient_not_automatic(client,login_as,post):
    login_as('dentist');inv=post('/api/practice/provider-invitation',{}).json()['code']
    assert post('/api/practice/link',{'code':inv}).status_code==403
    login_as('patient');resp=post('/api/practice/link',{'code':inv})
    assert resp.status_code==200,resp.text
    login_as('dentist');ps=client.get('/api/patients').json()
    assert any(p['id']=='pat_marie' for p in ps)
    # Association is not consent for a full medical record.
    assert client.get('/api/patients/pat_marie/identity').status_code==403
    assert client.get('/api/patients/pat_louis/overview').status_code==403

def test_nurse_daily_route_and_double_click_rejection(client,login_as,post):
    login_as('doctor');future=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    r=post('/api/practice/visits',{'patient_id':'pat_marie','nurse_id':'u_nurse','starts_at':future,'care':'Visite de suivi prescrit'})
    assert r.status_code==200,r.text
    vid=r.json()['id'];login_as('nurse')
    data=client.get('/api/practice/visits?period=week');assert data.status_code==200,data.text
    assert any(x['id']==vid for x in data.json())
    done=post(f'/api/practice/visits/{vid}/complete',{'pain_score':4,'mental_note':'Fatigue déclarée','medication_observed':'Prise de traitement constatée','injection':'','vaccine':''})
    assert done.status_code==200,done.text
    assert post(f'/api/practice/visits/{vid}/complete',{}).status_code==400
    login_as('patient');assert client.get('/api/practice/visits').status_code==403

def test_unauthorized_nurse_not_scheduled(client,login_as,post):
    login_as('doctor')
    r=post('/api/practice/visits',{'patient_id':'pat_jeanne','nurse_id':'u_nurse','starts_at':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),'care':'Test'} )
    assert r.status_code==403

def test_optician_can_publish_slots_for_patient(client,login_as,post):
    login_as('optician');future=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
    r=post('/api/appointments/slots',{'starts_at':future,'duration':30,'location':'Paris, France'});assert r.status_code==200,r.text
    slots=client.get('/api/appointments/slots').json()
    slot=next(s for s in slots if s['provider_role']=='optician')
    login_as('patient');book=post('/api/appointments',{'slot_id':slot['id'],'reason':'Essayage lunettes','scopes':[]})
    assert book.status_code==200,book.text
    assert client.get('/api/appointments').status_code==200
    login_as('optician');r=client.get('/api/appointments');assert r.status_code==200,r.text
    assert any(x['reason']=='Essayage lunettes' for x in r.json())

def test_patient_medication_confirmation_only_self(client,login_as,post):
    login_as('patient');r=client.get('/api/patients/pat_marie/overview');assert r.status_code==200
    mids=[m['id'] for m in r.json()['medications']];assert mids
    r=post(f'/api/practice/medication/pat_marie/{mids[0]}/check',{'status':'taken'})
    assert r.status_code==200,r.text
    assert client.get('/api/practice/medication/pat_marie/checks').json()
    login_as('doctor');assert post(f'/api/practice/medication/pat_marie/{mids[0]}/check',{'status':'taken'}).status_code==403

def test_deactivation_reversible_retains_clinical_data(client,login_as,post):
    login_as('patient');user=client.get('/api/auth/me').json()['user'];assert user['id']=='u_patient'
    assert post('/api/practice/deactivate',{'password':'wrong','confirmation':'DESACTIVER MON COMPTE'}).status_code==403
    resp=post('/api/practice/deactivate',{'password':portal.DEMO_PASSWORD,'confirmation':'DESACTIVER MON COMPTE'})
    assert resp.status_code==200,resp.text
    assert resp.json()['clinical_record_deleted'] is False
    assert client.get('/api/auth/me').status_code==401
    assert post('/api/auth/login',{'email':user['email'],'password':portal.DEMO_PASSWORD}).status_code==401
    with db.connect() as c:assert c.execute('SELECT 1 FROM patients WHERE id=?',('pat_marie',)).fetchone()

def test_activity_csv_local_import_permission_and_idempotence(client,login_as):
    sample=b'date,steps,sleep_hours,heart_rate\n2026-11-25,3450,6.5,72\n2026-11-26,6810,7.2,68\n'
    login_as('patient')
    def upload(raw):return client.post('/api/practice/activity/import',files={'file':('activity.csv',raw,'text/csv')},headers={'X-Healthberg-Action':'demo'})
    r=upload(sample);assert r.status_code==200,r.text
    assert r.json()['scanned_records']==6
    assert upload(sample).status_code==200
    assert len(client.get('/api/practice/activity').json())==6
    assert upload(b'date,steps\n2026-11-25,steps\n').status_code==400
    login_as('doctor');assert client.get('/api/practice/activity').status_code==403

def test_nurse_sees_patient_provided_logistics_on_authorized_visit(client,login_as,post):
    login_as('patient')
    r=client.put('/api/patients/pat_marie/identity',json={'phone':'0102030405','entry_code':'TEST-CODE-15','address':'10 rue du Test'},headers={'X-Healthberg-Action':'demo'})
    assert r.status_code==200,r.text
    login_as('doctor')
    r=post('/api/practice/visits',{'patient_id':'pat_marie','nurse_id':'u_nurse','starts_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'care':'Surveillance prescrite'})
    assert r.status_code==200,r.text
    login_as('nurse')
    rows=client.get('/api/practice/visits?period=week').json()
    v=next(x for x in rows if x['id']==r.json()['id'])
    assert v['phone']=='0102030405' and v['entry_code']=='TEST-CODE-15'
    login_as('pharmacist')
    assert client.get('/api/practice/visits?period=week').status_code==403
