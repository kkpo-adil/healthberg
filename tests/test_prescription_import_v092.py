"""External fictive PDF -> same patient -> temporary provider QR, no mistaken identity."""
import fitz
from app import portal,db

H={'X-Healthberg-Action':'demo'}

def auth(client, role):
    user=next(u for u in portal.SEED_USERS if u[3]==role)
    result=client.post('/api/auth/login',json={'email':user[1],'password':portal.DEMO_PASSWORD},headers=H)
    assert result.status_code==200,result.text

def pdf_bytes(name='Marie Martin'):
    doc=fitz.open();page=doc.new_page()
    lines=['ORDONNANCE SPECIMEN - NON VALABLE','Patient : '+name,'Date : 25/11/2026',
        'Professionnel : Dr Test','Produit 1 : Produit fictif Alpha','Dosage 1 : 500 mg',
        'Posologie 1 : Une fois le matin','Quantite 1 : 1 boite','Duree 1 : 5 jours']
    for i,line in enumerate(lines):page.insert_text((40,60+i*30),line)
    out=doc.tobytes();doc.close();return out

def preview(client,name='Marie Martin',pid='pat_marie',raw=None):
    return client.post('/api/import-prescriptions/preview',data={'patient_id':pid,'synthetic_ack':'true'},
        files={'file':('specimen.pdf',raw if raw is not None else pdf_bytes(name),'application/pdf')},headers=H)

def test_doc_to_patient_qr_to_pharmacist(client):
    auth(client,'doctor')
    response=preview(client)
    assert response.status_code==200,response.text
    data=response.json();assert data['patient']=='Marie Martin' and len(data['items'])==1
    check=client.post('/api/import-prescriptions/confirm',json={'preview_token':data['preview_token'],
        'patient_id':'pat_marie','items':data['items'],'confirm_patient_identity':True},headers=H)
    assert check.status_code==200,check.text
    oid=check.json()['id']
    doctor_doc=client.get(f'/api/import-prescriptions/{oid}/original');assert doctor_doc.status_code==200
    assert doctor_doc.content.startswith(b'%PDF-')
    auth(client,'patient')
    orders=client.get('/api/journeys/orders/pat_marie').json();assert any(o['id']==oid and o['has_original_pdf'] for o in orders)
    assert client.get(f'/api/import-prescriptions/{oid}/original').status_code==200
    qr=client.post(f'/api/journeys/qr/{oid}',headers=H).json()['qr_payload']
    auth(client,'pharmacist')
    assert client.get(f'/api/import-prescriptions/{oid}/original').status_code==403
    ticket=client.post('/api/journeys/redeem',json={'qr_payload':qr},headers=H)
    assert ticket.status_code==200,ticket.text
    grant=ticket.json()['grant_id']
    doc=client.get(f'/api/import-prescriptions/ticket/{grant}/{oid}/original')
    assert doc.status_code==200 and doc.content.startswith(b'%PDF-')
    summary=client.get('/api/patients/pat_marie/overview')
    assert summary.status_code==200 and not summary.json()['observations'] and not summary.json()['notes']
    auth(client,'lab');assert client.get(f'/api/import-prescriptions/ticket/{grant}/{oid}/original').status_code==403

def test_wrong_patient_rejected(client):
    auth(client,'doctor')
    result=preview(client,'Roger Moore')
    assert result.status_code==400
    assert 'Identité différente' in result.json()['detail']
    with db.connect() as c:assert c.execute('SELECT COUNT(*) FROM aj_imported_prescription_pdfs').fetchone()[0]==0

def test_patient_cannot_publish_or_preview(client):
    auth(client,'patient')
    assert preview(client).status_code==403
    assert client.post('/api/import-prescriptions/confirm',json={'preview_token':'a','patient_id':'pat_marie',
        'items':[],'confirm_patient_identity':True},headers=H).status_code==403

def test_confirmation_required_one_shot(client):
    auth(client,'doctor');session=preview(client).json()
    request={'preview_token':session['preview_token'],'patient_id':'pat_marie',
             'items':session['items'],'confirm_patient_identity':False}
    assert client.post('/api/import-prescriptions/confirm',json=request,headers=H).status_code==400
    request['confirm_patient_identity']=True
    first=client.post('/api/import-prescriptions/confirm',json=request,headers=H)
    assert first.status_code==200,first.text
    assert client.post('/api/import-prescriptions/confirm',json=request,headers=H).status_code==403

def test_secondary_specialty_combined_not_access(client):
    auth(client,'doctor')
    res=client.post('/api/preferences/specialty',json={'specialty':'Médecine générale',
        'secondary_specialty':'Médecine cardiovasculaire'},headers=H)
    assert res.status_code==200,res.text
    assert res.json()['secondary_specialty']=='Médecine cardiovasculaire'
    m=client.get('/api/patients/pat_marie/health-map')
    assert m.status_code==200,m.text
    assert m.json()['secondary_specialty']['specialty']=='Médecine cardiovasculaire'
    auth(client,'pharmacist')
    assert client.get('/api/preferences/specialty').status_code==403


def test_duplicate_document_is_blocked(client):
    auth(client,'doctor')
    raw=pdf_bytes()
    first=preview(client,raw=raw).json()
    payload={'preview_token':first['preview_token'],'patient_id':'pat_marie','items':first['items'],'confirm_patient_identity':True}
    assert client.post('/api/import-prescriptions/confirm',json=payload,headers=H).status_code==200
    second=preview(client,raw=raw).json()
    payload.update(preview_token=second['preview_token'],items=second['items'])
    r=client.post('/api/import-prescriptions/confirm',json=payload,headers=H)
    assert r.status_code==400 and 'déjà présente' in r.json()['detail']
