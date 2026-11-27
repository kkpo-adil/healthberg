from app.portal import DEMO_PASSWORD

def test_register_fictional_lab_then_patient_grant(client,login_as,post):
    r=post('/api/demo/accounts',{'role':'lab','name':'Laboratoire Fictif Deux','synthetic_ack':True})
    assert r.status_code==200,r.text
    new=r.json(); assert new['email'].endswith('@demo.healthberg.local')
    assert client.post('/api/auth/login',json={'email':new['email'],'password':DEMO_PASSWORD},headers={'X-Healthberg-Action':'demo'}).status_code==200
    assert client.get('/api/patients').json()==[]
    assert post('/api/patients/pat_marie/measures',{'code':'glucose','value':1.2,'unit':'g/L','measured_at':'2026-11-22T09:00:00+01:00'}).status_code==403
    login_as('patient')
    r=post('/api/patients/pat_marie/grants',{'user_id':new['id'],'permissions':['glucose','vitals'],'revoked':False})
    assert r.status_code==200,r.text
    client.post('/api/auth/login',json={'email':new['email'],'password':DEMO_PASSWORD},headers={'X-Healthberg-Action':'demo'})
    assert len(client.get('/api/patients').json())==1
    assert post('/api/patients/pat_marie/measures',{'code':'hba1c','value':7.1,'unit':'%','measured_at':'2026-11-22T09:00:00+01:00'}).status_code==200
    assert client.get('/api/patients/pat_marie/observations').json()==[]

def test_patient_can_register_new_empty_fictional_dossier(client,post):
    res=post('/api/demo/accounts',{'role':'patient','name':'Patient Fictif Deux','synthetic_ack':True})
    assert res.status_code==200,res.text
    u=res.json();assert u['patient_id'].startswith('pat_')
    resp=post('/api/auth/login',{'email':u['email'],'password':DEMO_PASSWORD})
    assert resp.status_code==200
    pts=client.get('/api/patients').json()
    assert len(pts)==1 and pts[0]['id']==u['patient_id']
    overview=client.get(f'/api/patients/{u["patient_id"]}/overview').json()
    assert overview['observations']==[]
    assert client.get('/api/patients/pat_marie/overview').status_code==403

def test_registration_rejected_if_not_fictional(client,post):
    assert post('/api/demo/accounts',{'role':'nurse','name':'Test Démo','synthetic_ack':False}).status_code==400
    assert post('/api/demo/accounts',{'role':'admin','name':'Test Démo','synthetic_ack':True}).status_code==400
