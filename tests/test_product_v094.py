"""Product acceptance for 0.9.4, synthetic-only patient/provider workflows."""

import fitz
from app import care_catalog, db, portal
from app.extraction import parse_file


def _pdf(texts):
    doc=fitz.open();page=doc.new_page(width=640,height=720)
    for x,y,text in texts:page.insert_text((x,y),text,fontsize=12)
    raw=doc.tobytes();doc.close();return raw


def test_pdf_table_separate_columns_readable():
    pdf=_pdf([(40,65,'Date : 23/11/2026'),(40,135,'Glycemie'),(270,135,'1,25 g/L'),(425,135,'0,70 - 1,10'),(40,175,'Creatinine'),(275,175,'12,4 mg/L'),(425,175,'6,0 - 12,0'),(40,215,'HbA1c'),(270,215,'7,2 %')])
    p=parse_file(pdf,'application/pdf','bilan-laboratoire.pdf')
    assert {x.code for x in p.candidates}>={'glucose','creatinine','hba1c'}
    assert next(x.value for x in p.candidates if x.code=='glucose')==1.25
    assert p.text_previews and 'Glycemie' in p.text_previews[0]


def test_broken_text_hint_and_manual_fallback(client,login_as,post):
    login_as('patient')
    pdf=_pdf([(40,65,'Date : 23/11/2026'),(40,115,'BIOLOGIE NON RECONNUE XYZ'),(40,135,'Voir les valeurs sur le document original')])
    r=client.post('/api/documents/preview',files={'file':('bilan.pdf',pdf,'application/pdf')},data={'patient_id':'pat_marie','synthetic_ack':'true'},headers={'X-Healthberg-Action':'demo'})
    assert r.status_code==200,r.text
    p=r.json(); assert p['candidates']==[];assert p['text_previews']
    entry={'code':'glucose','label':'Glycémie','value':1.16,'unit':'g/L','measured_at':'2026-11-23T12:00:00+01:00','page':1,'original_value':'1.16','original_unit':'g/L','manual':True}
    result=post('/api/documents/confirm',{'import_token':p['import_token'],'patient_id':'pat_marie','confirm_patient_identity':True,'candidates':[entry], 'medications':[],'manual_verified':True})
    assert result.status_code==200,result.text
    assert any(x['value']==1.16 for x in db.list_observations('pat_marie','glucose'))
    assert 'manual-user-entry' in db.receipt_by_id('pat_marie',result.json()['receipt']['receipt_id'])['extraction_method']


def test_manual_import_rejects_unsupported_unit(client,login_as,post):
    login_as('patient')
    r=client.post('/api/documents/preview',files={'file':('bilan.pdf',_pdf([(40,65,'Bilan inconnu')]),'application/pdf')},data={'patient_id':'pat_marie','synthetic_ack':'true'},headers={'X-Healthberg-Action':'demo'})
    p=r.json();entry={'code':'glucose','label':'Glycémie','value':100,'unit':'cmHg','measured_at':'2026-11-23T12:00:00+01:00','page':1,'original_value':'100','original_unit':'cmHg','manual':True}
    response=post('/api/documents/confirm',{'import_token':p['import_token'],'patient_id':'pat_marie','confirm_patient_identity':True,'candidates':[entry],'manual_verified':True})
    assert response.status_code==400


def test_profile_update_and_access(client,login_as):
    login_as('patient')
    data={'birth_date':'1960-03-12','address':'10 rue des Tests, Paris','profession':'Architecte','insurer':'Mutuelle Démo','member_test_id':'TEST-ADH-1','social_test_id':'TEST-MARIE-0001'}
    r=client.put('/api/patients/pat_marie/identity',json=data,headers={'X-Healthberg-Action':'demo'});assert r.status_code==200,r.text
    assert client.get('/api/patients/pat_marie/identity').json()['social_test_id']=='TEST-MARIE-0001'
    assert client.get('/api/patients/pat_marie/overview').json()['patient']['identity']['profession']=='Architecte'
    bad=client.put('/api/patients/pat_marie/identity',json={**data,'social_test_id':'123456789012345'},headers={'X-Healthberg-Action':'demo'})
    assert bad.status_code==400
    login_as('pharmacist')
    assert client.get('/api/patients/pat_marie/identity').status_code==403


def test_registration_patient_profile(client):
    r=client.post('/api/demo/accounts',json={'role':'patient','name':'Madame Test Ajour','synthetic_ack':True,'birth_date':'1981-04-10','address':'3 rue du Test','profession':'Secrétaire','insurer':'Démo','social_test_id':'TEST-UNE','member_test_id':'TEST-MUTUELLE'},headers={'X-Healthberg-Action':'demo'})
    assert r.status_code==200,r.text
    assert portal.get_patient_profile(r.json()['patient_id'])['profession']=='Secrétaire'


def test_orientation_to_any_specialty(client,login_as,post):
    login_as('doctor')
    assert len(care_catalog.ALL_SPECIALTIES)==87
    chosen=next(x for x in care_catalog.ALL_SPECIALTIES if x['name']=='Ophtalmologie')
    data={'patient_id':'pat_marie','kind':'orientation','specialty_code':chosen['code'],'title':'Avis ophtalmologique','description':'Patient fictif','items':[{'description':'Consultation pour gêne visuelle'}], 'confirm_patient_identity':True}
    r=post('/api/care/orders',data)
    assert r.status_code==200,r.text
    oid=r.json()['id']
    login_as('patient')
    orders=client.get('/api/care/orders').json()
    assert any(x['id']==oid and x['specialty_code']==chosen['code'] for x in orders)
    reject=client.post(f'/api/care/orders/{oid}/qr',headers={'X-Healthberg-Action':'demo'})
    assert reject.status_code in (400,409)


def test_unknown_specialty_rejected(client,login_as,post):
    login_as('doctor')
    r=post('/api/care/orders',{'patient_id':'pat_marie','kind':'orientation','specialty_code':'NOT-A-REAL-CODE','title':'Essai','items':[{'description':'Consultation'}],'confirm_patient_identity':True})
    assert r.status_code==400


def test_static_navigation_and_profile_ui():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'static'
    app=(root/'app.js').read_text();care=(root/'careflows.js').read_text();html=(root/'index.html').read_text()
    assert 'data-home' in html and 'data-nav-back' in html
    assert 'Mon profil' in app and 'patientIdentityForm' in app
    assert 'careSpecialty' in care and 'updateCareLabels' in care
    assert 'ajManualLine' in app and 'text_previews' in app
