"""Synthetic fixtures only; the user's original report is never packaged."""
import fitz
from app.extraction import parse_file, extract_findings, parse_date
from app import db
from tests.test_api import preview


def report_bytes(ambiguous_date=False):
    doc=fitz.open()
    header=('LABORATOIRE FICTIF - Prélevé le 08.04.202508.11.2026' if ambiguous_date
            else 'LABORATOIRE FICTIF - Date du bilan : 08.11.2026')
    for n in range(4):
        p=doc.new_page()
        p.insert_text((40,50),header,fontsize=11)
        lines = [
            ['Antigène HBs    Négatif   Négatif Le 07.08.2023', 'ECLIA - DEMO', 'Index    0,25    0,40',
             'Anticorps anti-HBs    >1000 UI/L    Seuil : 10    >900',
             'Anticorps anti-HBc    Négatif', 'ECLIA - DEMO', 'Index    2,28    2,32',
             'Interprétation :', 'Index Antigène HBs    Négatif <0,9    Positif >1,0'],
            ['Anticorps anti-HIV(1+2)    Négatif', 'Index    0,23    0,19',
             'T.P.H.A (spécifique)    Négatif', 'Index    0,05    0,04',
             'Chlamydiae trachomatis    Négatif', 'Neisseria gonorrhoeae    Négatif'],
            ['Informations de laboratoire fictives'], ['Informations administratives fictives']][n]
        for i,line in enumerate(lines): p.insert_text((40,100+i*24),line,fontsize=11)
    data=doc.tobytes();doc.close();return data


def test_four_page_serology_native_does_not_require_ocr(monkeypatch):
    monkeypatch.setattr('app.extraction._ocr_image', lambda *args: (_ for _ in ()).throw(AssertionError('unexpected OCR')))
    r=parse_file(report_bytes(),'application/pdf','synthetic.pdf')
    assert r.method=='text-native' and len(r.findings)==11
    assert r.document_date=='2026-11-08'
    assert r.page_count==4 and len(r.text_previews)==4
    assert not r.candidates and not r.medications
    assert r.warnings==[]
    assert {(f.code,f.value) for f in r.findings} >= {('hbs_ab','>1000'),('hbs_ag_index','0,25'),('tpha_index','0,05')}
    assert {f.page for f in r.findings}=={1,2}


def test_ambiguous_sample_date_is_not_silently_chosen():
    assert parse_date('Né le 11.03.1980\nPrélevé le 08.04.202508.11.2026 à 11:53') is None
    assert parse_date('Né le 11.03.1980\nPrélevé le 08.11.2026 à 11:53')=='2026-11-08'


def test_reference_paragraphs_and_thresholds_are_not_results():
    assert extract_findings(['Index Antigène HBs Négatif <0,9\nAntigène HBs Négatif <0,9\nLes résultats Chlamydiae trachomatis négatif\nSeuil : 10 UI/L'],None)==[]
    fs=extract_findings(['Antigène HBs\nNégatif'],None)
    assert len(fs)==1 and fs[0].value=='Négatif'


def findings_body(p):
    return dict(import_token=p['import_token'],patient_id='pat_marie',confirm_patient_identity=True,
                candidates=[],findings=[{**f,'measured_at':'2026-11-08T12:00:00+01:00'} for f in p['findings']])


def test_confirmation_visibility_provenance_and_no_numeric_fabrication(client,login_as,post):
    login_as('patient')
    p=preview(client,data=report_bytes()).json()
    assert len(p['findings'])==11
    assert db.list_findings('pat_marie')==[]
    before=len(db.list_observations('pat_marie'))
    res=post('/api/documents/confirm',findings_body(p))
    assert res.status_code==200,res.text
    assert res.json()['receipt']['findings_created']==11
    assert len(db.list_observations('pat_marie'))==before
    ov=client.get('/api/patients/pat_marie/overview').json()
    assert len(ov['findings'])==11
    source=ov['findings'][0]['source_id']
    assert client.get('/api/patients/pat_marie/receipts/'+source).status_code==200
    login_as('doctor')
    assert len(client.get('/api/patients/pat_marie/overview').json()['findings'])==11
    for role in ('family','pharmacist','nurse','lab'):
        login_as(role)
        assert not client.get('/api/patients/pat_marie/overview').json().get('findings')
        assert client.get('/api/patients/pat_marie/receipts/'+source).status_code==404


def test_tampered_result_and_missing_date_rejected(client,login_as,post):
    login_as('patient');p=preview(client,data=report_bytes()).json();body=findings_body(p)
    body['findings'][0]['value']='Positif'
    assert post('/api/documents/confirm',body).status_code==400
    body=findings_body(p);body['findings'][0]['measured_at']=None
    assert post('/api/documents/confirm',body).status_code==400
    assert db.list_findings('pat_marie')==[]


def test_retention(client,login_as,post):
    login_as('patient');p=preview(client,data=report_bytes()).json()
    assert post('/api/documents/confirm',findings_body(p)).status_code==200
    db.purge_expired('2099-01-01T00:00:00+00:00')
    assert db.list_findings('pat_marie')==[]
