import io
import fitz
from pathlib import Path


def pdf_bytes():
    doc=fitz.open();p=doc.new_page()
    p.insert_text((50,60),'Document fictif - laboratoire test',fontsize=12)
    p.insert_text((50,100),'Date du bilan : 14/09/2025',fontsize=12)
    p.insert_text((50,120),'Glycemie : 1,23 g/L',fontsize=12)
    p.insert_text((50,140),'HbA1c : 7,2 %',fontsize=12)
    data=doc.tobytes();doc.close();return data

def preview(client,patient='pat_marie',ack='true',data=None):
    data=data or pdf_bytes()
    return client.post('/api/documents/preview',data={'patient_id':patient,'synthetic_ack':ack},files={'file':('dummy.pdf',io.BytesIO(data),'application/pdf')})

def confirm_body(p,patient='pat_marie'):
    return {'import_token':p['import_token'],'patient_id':patient,'confirm_patient_identity':True,
    'candidates':[{'code':c['code'],'label':c['label'],'value':c['value'],'unit':c['unit'],'measured_at':c['measured_at']+'T12:00:00+01:00',
       'page':c['page'],'original_value':c['original_value'],'original_unit':c['original_unit']} for c in p['candidates']]}

def test_dashboard_returns_synthetic(client):
    r=client.get('/api/patients');assert r.status_code==200 and len(r.json())==5
    o=client.get('/api/patients/pat_marie/overview');assert o.status_code==200
    assert o.json()['last_values']['glucose']['value']>0
    assert o.json()['patient']['synthetic']==1
    assert client.get('/api/patients/unknown/overview').status_code==404

def test_document_import_no_original_saved(client):
    raw=pdf_bytes();a=preview(client,data=raw)
    assert a.status_code==200,a.text
    p=a.json();assert p['page_count']==1 and len(p['candidates'])==2
    assert p['patient_name']=='Marie Martin'
    b=client.post('/api/documents/confirm',json=confirm_body(p))
    assert b.status_code==200,b.text
    assert b.json()['original_stored'] is False
    rid=b.json()['receipt']['receipt_id']
    receipt=client.get(f'/api/patients/pat_marie/receipts/{rid}').json()
    assert receipt['sha256']==p['sha256'] and receipt['original_retained']==0
    obs=client.get('/api/patients/pat_marie/observations').json()
    assert len([x for x in obs if x['source_id']==rid])==2
    assert all(x['status']=='patient_confirmed' for x in obs if x['source_id']==rid)
    from app import db
    stored=Path(db.DB_PATH).read_bytes()
    assert raw not in stored
    assert b'Document fictif - laboratoire test' not in stored
    assert client.get(f'/api/patients/pat_louis/receipts/{rid}').status_code==404

def test_confirmation_wrong_patient_blocked(client):
    p=preview(client).json()
    b=client.post('/api/documents/confirm',json=confirm_body(p,patient='pat_louis'))
    assert b.status_code==403

def test_confirmation_requires_actual_previews(client):
    p=preview(client).json()
    body=confirm_body(p);body['candidates'][0]['code']='creatinine'
    assert client.post('/api/documents/confirm',json=body).status_code==400

def test_double_import_dedup(client):
    raw=pdf_bytes()
    p=preview(client,data=raw).json();r=client.post('/api/documents/confirm',json=confirm_body(p));assert r.status_code==200
    p2=preview(client,data=raw).json();r2=client.post('/api/documents/confirm',json=confirm_body(p2));assert r2.status_code==409

def test_ack_required(client):
    assert preview(client,ack='false').status_code==400

def test_cross_origin_denied(client):
    r=client.get('/api/patients',headers={'Origin':'https://evil.example'})
    assert r.status_code==403

def test_empty_measurements_rejected(client):
    p=preview(client).json();payload=confirm_body(p);payload['candidates']=[]
    assert client.post('/api/documents/confirm',json=payload).status_code==400

def test_unknown_patient_not_exposed(client):
    assert client.get('/api/patients/fake/observations').status_code==404
    assert client.get('/api/patients/fake/receipts').status_code==404

def test_historical_prescription_import(client):
    doc=fitz.open();page=doc.new_page()
    for idx,line in enumerate(['ORDONNANCE - FICTIVE','Date : 14/09/2025','Metformine 850 mg - un comprimé matin et soir']):
        page.insert_text((40,60+30*idx),line,fontsize=12)
    raw=doc.tobytes();doc.close()
    data=preview(client,data=raw).json()
    assert not data['candidates']
    assert len(data['medications'])==1
    m=data['medications'][0]
    payload={'import_token':data['import_token'],'patient_id':'pat_marie','confirm_patient_identity':True,'candidates':[],
        'medications':[{'name':m['name'],'strength':m['strength'],'directions':m['directions'],'page':m['page'],'since':'2025-09-14'}]}
    res=client.post('/api/documents/confirm',json=payload)
    assert res.status_code==200,res.text
    assert res.json()['receipt']['medications_created']==1
    meds=client.get('/api/patients/pat_marie/overview').json()['medications']
    assert any(m['name']=='Metformine 850mg' and m['state']=='historical' and m['source_id'] for m in meds)
