import io
from pathlib import Path
import fitz
from app import db

def pdf_bytes():
    doc=fitz.open();p=doc.new_page()
    p.insert_text((50,60),'Document fictif - laboratoire test',fontsize=12)
    p.insert_text((50,100),'Date du bilan : 14/09/2025',fontsize=12)
    p.insert_text((50,120),'Glycemie : 1,23 g/L',fontsize=12)
    p.insert_text((50,140),'HbA1c : 7,2 %',fontsize=12)
    raw=doc.tobytes();doc.close();return raw

def preview(client,patient='pat_marie',ack='true',data=None):
    return client.post('/api/documents/preview',data={'patient_id':patient,'synthetic_ack':ack},files={'file':('fictif.pdf',io.BytesIO(data or pdf_bytes()),'application/pdf')},headers={'X-Healthberg-Action':'demo'})

def confirm_body(p,patient='pat_marie'):
    return {'import_token':p['import_token'],'patient_id':patient,'confirm_patient_identity':True,
        'candidates':[{'code':c['code'],'label':c['label'],'value':c['value'],'unit':c['unit'],
         'measured_at':(c['measured_at'] or p['document_date'] or '2025-09-14')+'T12:00:00+01:00','page':c['page'],
         'original_value':c['original_value'],'original_unit':c['original_unit']} for c in p['candidates']]}

def test_auth_required(client):
    assert client.get('/api/auth/accounts').status_code==200
    assert client.get('/api/patients').status_code==401
    assert client.get('/api/patients/pat_marie/overview').status_code==401
    assert client.post('/api/auth/login',json={'email':'x','password':'x'}).status_code==403
    assert client.post('/api/auth/login',json={'email':'x','password':'x'},headers={'X-Healthberg-Action':'demo'}).status_code==401

def test_patient_self_only(client,login_as):
    login_as('patient')
    p=client.get('/api/patients').json()
    assert len(p)==1 and p[0]['id']=='pat_marie'
    o=client.get('/api/patients/pat_marie/overview')
    assert o.status_code==200 and 'glucose' in o.json()['last_values']
    assert client.get('/api/patients/pat_louis/overview').status_code==403
    assert client.get('/api/patients/pat_marie/audit').status_code==200

def test_family_privacy_and_access_revoke(client,login_as,post):
    login_as('family')
    p=client.get('/api/patients/pat_marie/overview').json()
    assert {'glucose','systolic','diastolic'}<=set(p['last_values'])
    assert 'hba1c' not in p['last_values'] and 'creatinine' not in p['last_values']
    assert p['notes']==[]
    assert client.get('/api/patients/pat_marie/audit').status_code==403
    assert client.get('/api/patients/pat_louis/overview').status_code==403
    login_as('patient')
    r=post('/api/patients/pat_marie/grants',{'family_id':'u_family','permissions':['glucose'],'revoked':False})
    assert r.status_code==200,r.text
    login_as('family')
    p=client.get('/api/patients/pat_marie/overview').json()
    assert list(p['last_values'])==['glucose']
    assert p['medications']==[]
    login_as('patient')
    assert post('/api/patients/pat_marie/grants',{'family_id':'u_family','permissions':['glucose'],'revoked':True}).status_code==200
    login_as('family')
    assert client.get('/api/patients/pat_marie/overview').status_code==403

def test_pharmacist_cannot_read_labs_or_notes(client,login_as,post):
    login_as('pharmacist')
    overview=client.get('/api/patients/pat_marie/overview').json()
    assert overview['last_values']=={} and overview['observations']==[] and overview['notes']==[]
    assert len(overview['medications'])>=1
    assert client.get('/api/patients/pat_marie/observations').json()==[]
    assert post('/api/patients/pat_marie/prescriptions',{'name':'Fictive A','schedule':'matin'}).status_code==403
    med=overview['medications'][0]
    assert post('/api/patients/pat_marie/dispenses',{'medication_id':med['id'],'quantity':'Une boîte fictive','note':''}).status_code==200
    assert len(client.get('/api/patients/pat_marie/overview').json()['medications'][0]['dispenses']) in (0,1)
    login_as('patient')
    assert any(m['dispenses'] for m in client.get('/api/patients/pat_marie/overview').json()['medications'])

def test_nurse_note_hidden_from_family_but_visible_to_doctor(client,login_as,post):
    login_as('nurse')
    r=post('/api/patients/pat_marie/notes',{'kind':'psychosocial','body':'La patiente fictive évoque un stress important.'})
    assert r.status_code==200,r.text
    assert any('stress' in n['body'] for n in client.get('/api/patients/pat_marie/overview').json()['notes'])
    login_as('family')
    assert client.get('/api/patients/pat_marie/overview').json()['notes']==[]
    login_as('doctor')
    assert any('stress' in n['body'] for n in client.get('/api/patients/pat_marie/overview').json()['notes'])

def test_lab_publishes_to_patient_and_doctor_not_pharmacy(client,login_as,post):
    login_as('lab')
    p=client.get('/api/patients/pat_marie/overview').json()
    assert p['observations']==[] and p['medications']==[] and p['contacts']==[]
    new={'code':'hba1c','value':6.8,'unit':'%','measured_at':'2026-11-21T09:00:00+01:00','context':'Bilan de laboratoire fictif'}
    res=post('/api/patients/pat_marie/measures',new)
    assert res.status_code==200,res.text
    assert res.json()['status']=='professional_verified'
    assert len(client.get('/api/patients/pat_marie/lab-submissions').json())==1
    assert post('/api/patients/pat_marie/measures',{**new,'code':'systolic','unit':'mmHg'}).status_code==403
    login_as('patient')
    assert any(o['value']==6.8 for o in client.get('/api/patients/pat_marie/overview').json()['observations'] if o['code']=='hba1c')
    login_as('doctor')
    assert any(o['value']==6.8 for o in client.get('/api/patients/pat_marie/overview').json()['observations'] if o['code']=='hba1c')
    login_as('pharmacist')
    assert client.get('/api/patients/pat_marie/observations').json()==[]
    login_as('family')
    assert all(o['code']!='hba1c' for o in client.get('/api/patients/pat_marie/observations').json())

def test_nurse_measure_restricted_to_authorized_vitals(client,login_as,post):
    login_as('nurse')
    good={'code':'glucose','value':1.17,'unit':'g/L','measured_at':'2026-11-21T11:00:00+01:00'}
    assert post('/api/patients/pat_marie/measures',good).status_code==200
    bad={**good,'code':'creatinine','unit':'mg/L'}
    assert post('/api/patients/pat_marie/measures',bad).status_code==403
    login_as('family')
    assert any(o['value']==1.17 for o in client.get('/api/patients/pat_marie/observations').json() if o['code']=='glucose')

def test_doctor_assigned_no_global_patients(client,login_as,post):
    login_as('doctor')
    p=client.get('/api/patients').json()
    assert {p['id'] for p in p}=={'pat_marie','pat_louis','pat_jeanne'}
    assert client.get('/api/patients/pat_robert/overview').status_code==403
    assert post('/api/patients/pat_marie/prescriptions',{'name':'Traitement fictif K','schedule':'Dose fictive 1x/jour'}).status_code==200
    login_as('pharmacist')
    assert any('Traitement fictif K' in m['name'] for m in client.get('/api/patients/pat_marie/overview').json()['medications'])

def test_messages_are_recipient_scoped(client,login_as,post):
    login_as('family')
    msg=post('/api/patients/pat_marie/messages',{'recipient_id':'u_doctor','body':'Demande fictive de retour sur une ordonnance.'})
    assert msg.status_code==200,msg.text
    login_as('doctor')
    messages=client.get('/api/patients/pat_marie/overview').json()['messages']
    assert any('Demande fictive' in m['body'] for m in messages)
    login_as('pharmacist')
    assert not any('Demande fictive' in m['body'] for m in client.get('/api/patients/pat_marie/overview').json()['messages'])

def test_tasks_doctor_to_nurse(client,login_as,post):
    login_as('doctor')
    r=post('/api/patients/pat_marie/tasks',{'assignee_id':'u_nurse','title':'Mesurer la glycémie fictive','due_date':'2026-12-01'})
    assert r.status_code==200,r.text
    task_id=r.json()['id']
    login_as('nurse')
    assert any(t['id']==task_id for t in client.get('/api/patients/pat_marie/overview').json()['tasks'])
    assert post(f'/api/patients/pat_marie/tasks/{task_id}/complete',{}).status_code==200
    login_as('patient')
    assert next(t for t in client.get('/api/patients/pat_marie/overview').json()['tasks'] if t['id']==task_id)['status']=='done'

def test_import_confirm_and_no_original(client,login_as,post):
    login_as('patient')
    raw=pdf_bytes();p=preview(client,data=raw)
    assert p.status_code==200,p.text
    data=p.json();assert len(data['candidates'])==2
    r=post('/api/documents/confirm',confirm_body(data))
    assert r.status_code==200,r.text
    rid=r.json()['receipt']['receipt_id']
    rec=client.get(f'/api/patients/pat_marie/receipts/{rid}').json()
    assert rec['sha256']==data['sha256'] and rec['original_retained']==0
    assert raw not in Path(db.DB_PATH).read_bytes()
    assert b'Document fictif - laboratoire test' not in Path(db.DB_PATH).read_bytes()
    assert len([x for x in client.get('/api/patients/pat_marie/observations').json() if x['source_id']==rid])==2
    assert preview(client,data=raw).status_code==200
    p2=preview(client,data=raw).json()
    assert post('/api/documents/confirm',confirm_body(p2)).status_code==409

def test_import_different_user_cannot_confirm_token(client,login_as,post):
    login_as('patient');p=preview(client).json()
    login_as('doctor')
    assert post('/api/documents/confirm',confirm_body(p)).status_code==403
    login_as('pharmacist')
    assert preview(client).status_code==403

def test_patient_mismatch_and_cross_origin(client,login_as,post):
    login_as('patient')
    p=preview(client).json()
    assert post('/api/documents/confirm',confirm_body(p,'pat_louis')).status_code==403
    assert client.get('/api/patients',headers={'Origin':'https://example.org'}).status_code==403
    assert client.get('/api/patients/pat_louis/receipts').status_code==403

def test_logout_invalidates_cookie(client,login_as):
    login_as('patient')
    assert client.get('/api/auth/me').status_code==200
    assert client.post('/api/auth/logout',headers={'X-Healthberg-Action':'demo'}).status_code==200
    assert client.get('/api/auth/me').status_code==401
