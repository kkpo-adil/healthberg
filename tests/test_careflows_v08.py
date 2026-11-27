"""Clinical imaging and allied healthcare: comprehensive synthetic-only regression."""
import io
import struct
from datetime import date
from app import db, portal, careflows

BASE='/api/care'

def login(client,role,uid=None):
    values=next(x for x in portal.SEED_USERS if x[0]==uid) if uid else next(x for x in portal.SEED_USERS if x[3]==role)
    r=client.post('/api/auth/login',json={'email':values[1],'password':portal.DEMO_PASSWORD},headers={'X-Healthberg-Action':'demo'})
    assert r.status_code==200,r.text
    return values

def post(client,path,body=None):return client.post(path,json=body or {},headers={'X-Healthberg-Action':'demo'})

def issue(client,kind):
    login(client,'doctor')
    req={'patient_id':'pat_marie','confirm_patient_identity':True,'kind':kind,
         'title':'Prescription de test '+kind,'description':'Consultation de démonstration',
         'items':[{'description':'Examens ou équipements prescrits à titre fictif'}]}
    r=post(client,BASE+'/orders',req)
    assert r.status_code==200,r.text
    return r.json()['id']

def share(client,oid):
    login(client,'patient')
    r=post(client,f'{BASE}/orders/{oid}/qr')
    assert r.status_code==200,r.text
    v=r.json()
    assert 'pat_marie' not in v['qr_payload'] and 'Marie' not in v['qr_payload']
    return v['qr_payload']

def redeem(client,role,token):
    login(client,role)
    r=post(client,BASE+'/qr/redeem',{'qr_payload':token})
    assert r.status_code==200,r.text
    return r.json()

def upload(client,pid='pat_marie',category='radiology',order_id=None,grant_id=None,prior_id=None,contents=None):
    payload=contents if contents is not None else b'\x89PNG\r\n\x1a\n'+b'unit test synthetic only'
    data={'patient_id':pid,'category':category,'description':'Examen fictif avant ou après','anatomical_site':'pied gauche',
          'exam_date':str(date(2026,11,24)),'synthetic_ack':'true'}
    if order_id:data['order_id']=order_id
    if grant_id:data['grant_id']=grant_id
    if prior_id:data['prior_media_id']=prior_id
    return client.post(BASE+'/media',data=data,files={'file':('test.png',io.BytesIO(payload),'image/png')},headers={'X-Healthberg-Action':'demo'})

def test_specialties_cover_requested_scope(client):
    login(client,'patient')
    c=client.get(BASE+'/catalog').json()
    assert c['medical_count']==44
    assert c['profession_count']>=40
    assert c['count']>=84
    names={r['name'] for r in c['items']}
    assert {'Ophtalmologie','Chirurgie orale','Pédicure-podologue','Radiologie et imagerie médicale',
            'Opticien-lunetier','Psychologue','Biologie médicale','Audioprothésiste'}<=names
    assert {'dental','imaging','optical','podiatry','orthotics'}<=set(c['care_types'])
    assert 'Assurance maladie' in ' '.join(c['limitations'])

def test_optician_patient_qr_and_ready_notification(client):
    oid=issue(client,'optical');token=share(client,oid)
    login(client,'dentist')
    assert post(client,BASE+'/qr/redeem',{'qr_payload':token}).status_code==403
    t=redeem(client,'optician',token)
    assert t['order']['kind']=='optical'
    assert post(client,BASE+'/qr/redeem',{'qr_payload':token}).status_code==409
    assert 'observations' not in t['order']
    r=post(client,f"{BASE}/tickets/{t['grant_id']}/actions",{'operation':'ready','note':'Monture disponible'})
    assert r.status_code==200,r.text
    login(client,'patient')
    assert any('prêt' in n['text'] for n in client.get(BASE+'/notifications').json())
    rows=client.get(BASE+'/orders').json()
    assert next(x for x in rows if x['id']==oid)['status']=='ready'
    login(client,'family')
    assert client.get(BASE+'/notifications').json()==[]
    assert client.get(BASE+'/media/pat_marie').status_code==200  # private media empty, not 403 yet
    assert client.get(BASE+'/media/pat_marie').json()==[]

def test_radiology_provider_uses_qr_then_patient_sees_image(client,monkeypatch):
    oid=issue(client,'imaging');token=share(client,oid)
    t=redeem(client,'radiologist',token)
    payload=b'\x89PNG\r\n\x1a\n' + b'fictional imaging file'
    r=upload(client,order_id=oid,grant_id=t['grant_id'],contents=payload)
    assert r.status_code==200,r.text
    mid=r.json()['id']
    login(client,'patient')
    ls=client.get(BASE+'/media/pat_marie').json()
    assert any(x['id']==mid for x in ls)
    f=client.get(BASE+'/media/file/'+mid)
    assert f.status_code==200 and f.content==payload
    assert f.headers['cache-control']=='no-store'
    root=careflows.media_root()
    assert any(x.is_file() for x in root.iterdir())
    login(client,'pharmacist')
    assert client.get(BASE+'/media/pat_marie').json()==[]
    assert client.get(BASE+'/media/file/'+mid).status_code==403
    login(client,'family')
    assert client.get(BASE+'/media/file/'+mid).status_code==403

def test_podiatry_footprint_comparison_provenance(client):
    oid=issue(client,'podiatry');token=share(client,oid)
    t=redeem(client,'podiatrist',token)
    before=upload(client,category='podiatry',order_id=oid,grant_id=t['grant_id'])
    assert before.status_code==200,before.text
    after=upload(client,category='podiatry',order_id=oid,grant_id=t['grant_id'],prior_id=before.json()['id'])
    assert after.status_code==200,after.text
    login(client,'patient');imgs=client.get(BASE+'/media/pat_marie').json()
    assert any(x['prior_media_id']==before.json()['id'] for x in imgs)
    # No automatic clinical improvement classification.
    assert not any('amelioration' in str(x).lower() for x in imgs)

def test_patient_external_unsupported_provider_manual_import(client):
    login(client,'patient')
    r=upload(client,category='dental')
    assert r.status_code==200,r.text
    assert r.json()['source_status']=='patient_import_unverified'
    assert client.get(BASE+'/media/pat_marie').json()[0]['source_status']=='patient_import_unverified'

def test_no_cross_patient_upload_or_unauthorized_role(client):
    oid=issue(client,'dental');token=share(client,oid)
    t=redeem(client,'dentist',token)
    assert upload(client,pid='pat_louis',category='dental',order_id=oid,grant_id=t['grant_id']).status_code==403
    assert upload(client,category='radiology',order_id=oid,grant_id=t['grant_id']).status_code==403
    login(client,'patient',uid='u_patient_louis')
    assert post(client,f'{BASE}/orders/{oid}/qr').status_code==403
    assert client.get(BASE+'/media/file/'+str('bogus')).status_code==404

def test_cancel_revoke_qr(client):
    oid=issue(client,'orthotics');token=share(client,oid)
    login(client,'patient');assert post(client,f'{BASE}/orders/{oid}/cancel').status_code==200
    login(client,'orthotist');assert post(client,BASE+'/qr/redeem',{'qr_payload':token}).status_code==409

def test_invalid_files_rejected(client):
    login(client,'patient')
    assert upload(client,contents=b'just text pretending to be picture').status_code==400
    assert upload(client,contents=b'').status_code==400
    assert upload(client,contents=b'a'*(careflows.MAX_MEDIA_BYTES+1)).status_code==400
    dcm=b'\x00'*128+b'DICM'+b'FAKE_DATA'
    assert upload(client,contents=dcm).status_code==200
    binary_stl=b'\x00'*80+struct.pack('<I',0)
    assert upload(client,category='podiatry',contents=binary_stl).status_code==200
    assert upload(client,category='dental',contents=binary_stl).status_code==400

def test_no_claim_endpoint_and_billing_table_removed(client):
    login(client,'pharmacist')
    assert post(client,'/api/journeys/claims/anything/prepare').status_code==404
    with db.connect() as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='aj_claim_outbox'").fetchone() is None

def test_new_specialty_users_no_unasked_patient_grants(client):
    login(client,'optician')
    assert client.get('/api/patients').json()==[]
    assert client.get('/api/patients/pat_marie/overview').status_code==403
    assert client.get(BASE+'/orders').json()==[]
    login(client,'patient')
    r=post(client,'/api/demo/grants',{})  # Nonexistent / legacy route is harmless
    assert r.status_code in (404,422)
