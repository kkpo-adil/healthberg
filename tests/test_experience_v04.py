"""The shared patient record, sharing and booking tests are always synthetic."""
from datetime import datetime, timedelta, timezone
from app.portal import DEMO_PASSWORD

HEADERS={'X-Healthberg-Action':'demo'}

def change_login(client,email):
    r=client.post('/api/auth/login',json={'email':email,'password':DEMO_PASSWORD},headers=HEADERS)
    assert r.status_code==200,r.text

def post(client,path,body=None):
    return client.post(path,json=body or {},headers=HEADERS)

def test_story_is_simple_and_sourced(client):
    change_login(client,'marie@demo.healthberg.local')
    r=client.get('/api/patients/pat_marie/story')
    assert r.status_code==200
    x=r.json()
    assert 'en clair' in x['title']
    assert x['cards']
    assert x['cards'][0]['source_id']
    assert 'diagnostic' in x['disclaimer']
    assert all('source_id' in item and 'explanation' in item for item in x['cards'])


def test_family_cannot_see_private_wellbeing_or_vaccinations_without_grant(client):
    change_login(client,'marie@demo.healthberg.local')
    assert post(client,'/api/patients/pat_marie/vaccinations',{'name':'Vaccin fictif A','administered_on':'2025-08-14','source':'Carnet démo','status':'declare'}).status_code==200
    assert post(client,'/api/patients/pat_marie/wellbeing',{'category':'humeur','note':'Donnée totalement fictive privée','recorded_on':'2026-11-19'}).status_code==200
    change_login(client,'claire@demo.healthberg.local')
    assert client.get('/api/patients/pat_marie/wellbeing').status_code==403
    assert client.get('/api/patients/pat_marie/vaccinations').status_code==403
    change_login(client,'marie@demo.healthberg.local')
    assert post(client,'/api/patients/pat_marie/grants',{'user_id':'u_family','permissions':['vaccines','appointments'],'revoked':False}).status_code==200
    change_login(client,'claire@demo.healthberg.local')
    assert len(client.get('/api/patients/pat_marie/vaccinations').json())==1
    assert client.get('/api/patients/pat_marie/wellbeing').status_code==403


def test_pharmacist_cannot_access_vaccines_prevention_wellbeing(client):
    change_login(client,'pharmacie@demo.healthberg.local')
    for endpoint in ['vaccinations','prevention','wellbeing','story']:
        r=client.get(f'/api/patients/pat_marie/{endpoint}')
        if endpoint=='story':assert r.status_code==200 and r.json()['cards']==[]
        else: assert r.status_code==403


def test_prevention_is_not_claimed_to_be_due(client):
    change_login(client,'marie@demo.healthberg.local')
    rules=client.get('/api/patients/pat_marie/prevention').json()
    prostate=next(x for x in rules if x['key']=='prostate')
    assert 'pas de' in prostate['description'].lower() or "n'existe pas" in prostate['description'].lower()
    assert all(x['status']=='inconnu' for x in rules)
    assert post(client,'/api/patients/pat_marie/prevention',{'key':'bilan','status':'a_discuter','note':'À aborder'}).status_code==200
    assert next(x for x in client.get('/api/patients/pat_marie/prevention').json() if x['key']=='bilan')['status']=='a_discuter'


def test_booking_preconsultation_minimum_scope_and_cancellation(client):
    # New doctor has no default care relationship. Appointments grant only the selected category.
    reg=post(client,'/api/demo/accounts',{'role':'doctor','name':'Docteur Fictif Nouveau','synthetic_ack':True})
    assert reg.status_code==200
    doctor=reg.json()
    change_login(client,doctor['email'])
    date=(datetime.now(timezone.utc)+timedelta(days=2)).replace(microsecond=0).isoformat()
    assert post(client,'/api/appointments/slots',{'starts_at':date,'duration':30,'location':'Cabinet fictif'}).status_code==200
    available=client.get('/api/appointments/slots').json()
    slot=next(x for x in available if x['doctor_id']==doctor['id'])
    assert client.get('/api/patients/pat_marie/overview').status_code==403
    change_login(client,'marie@demo.healthberg.local')
    r=post(client,'/api/appointments',{'slot_id':slot['id'],'reason':'Courbe de glycémie fictive','scopes':['glucose']})
    assert r.status_code==200,r.text
    aid=r.json()['id']
    assert post(client,'/api/appointments',{'slot_id':slot['id'],'scopes':[]}).status_code==409
    change_login(client,doctor['email'])
    overview=client.get('/api/patients/pat_marie/overview')
    assert overview.status_code==200
    data=overview.json()
    assert data['patient'].get('profile') is None  # cannot see broad clinical profile
    assert data['observations'] and all(x['code']=='glucose' for x in data['observations'])
    assert data['medications']==[]
    brief=client.get('/api/appointments/'+aid+'/brief')
    assert brief.status_code==200
    assert brief.json()['shared_categories']==['glucose']
    assert brief.json()['medications']==[]
    change_login(client,'marie@demo.healthberg.local')
    assert post(client,'/api/appointments/'+aid+'/cancel').status_code==200
    change_login(client,doctor['email'])
    assert client.get('/api/patients/pat_marie/overview').status_code==403
    assert client.get('/api/appointments/'+aid+'/brief').status_code==403
    # Rebook the released slot, without rewriting prior cancellation history.
    change_login(client,'marie@demo.healthberg.local')
    assert post(client,'/api/appointments',{'slot_id':slot['id'],'scopes':['meds']}).status_code==200


def test_lab_cannot_read_patient_story(client):
    change_login(client,'laboratoire@demo.healthberg.local')
    assert client.get('/api/patients/pat_marie/story').json()['cards']==[]
