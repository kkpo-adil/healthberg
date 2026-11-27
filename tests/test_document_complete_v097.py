"""Full-page preservation and one confirmed date; synthetic reports only."""
import fitz
from app import db
from app.extraction import parse_file, sample_date_options, report_conclusions
from tests.test_api import preview
from tests.test_report_import_v096 import report_bytes, findings_body


def test_common_date_fills_results_and_receipt_without_choosing_hidden_date(client,login_as,post):
    login_as('patient');p=preview(client,data=report_bytes()).json()
    body=findings_body(p)
    body.update(document_date='2026-11-08',retained_pages=[1,2,3,4],transcription_verified=True)
    for f in body['findings']:f['measured_at']=None
    assert db.list_document_pages('pat_marie')==[]
    res=post('/api/documents/confirm',body)
    assert res.status_code==200,res.text
    assert res.json()['receipt']['pages_retained']==4
    pages=db.list_document_pages('pat_marie')
    assert [x['text'] for x in pages]==p['text_previews']
    assert all(f['measured_at'].startswith('2026-11-08') for f in db.list_findings('pat_marie'))
    rid=res.json()['receipt']['receipt_id']
    assert client.get('/api/patients/pat_marie/receipts/'+rid).json()['document_date']=='2026-11-08'
    assert len(client.get('/api/patients/pat_marie/overview').json()['document_pages'])==4
    for role in ('family','nurse','pharmacist','lab'):
        login_as(role)
        assert not client.get('/api/patients/pat_marie/overview').json().get('document_pages')
    db.purge_expired('2099-01-01T00:00:00+00:00')
    assert db.list_document_pages('pat_marie')==[]


def test_page_retention_requires_review_and_rejects_unknown_or_duplicate_pages(client,login_as,post):
    login_as('patient');p=preview(client,data=report_bytes()).json()
    body=findings_body(p);body['retained_pages']=[1]
    assert post('/api/documents/confirm',body).status_code==400
    body['transcription_verified']=True
    for bad in ([0],[5],[1,1]):
        body['retained_pages']=bad
        assert post('/api/documents/confirm',body).status_code==400
    assert db.list_document_pages('pat_marie')==[]


def test_preserve_unclassified_pages_even_without_structured_result(client,login_as,post):
    login_as('patient');p=preview(client,data=report_bytes()).json()
    body=dict(import_token=p['import_token'],patient_id='pat_marie',confirm_patient_identity=True,
              candidates=[],findings=[],retained_pages=[3,4],transcription_verified=True)
    res=post('/api/documents/confirm',body)
    assert res.status_code==200,res.text
    assert res.json()['receipt']['observations_created']==0
    assert res.json()['receipt']['findings_created']==0
    assert len(db.list_document_pages('pat_marie'))==2
    assert client.get('/api/patients/pat_marie/receipts/'+res.json()['receipt']['receipt_id']).status_code==200


def test_full_text_is_not_cut_off_at_preview_limit():
    doc=fitz.open();p=doc.new_page(width=2000,height=2000)
    text=('Informations non classees, a conserver. '*12+'\n')*35+'FIN_DU_DOCUMENT'
    p.insert_textbox(fitz.Rect(20,20,1980,1980),text,fontsize=8)
    raw=doc.tobytes();doc.close()
    result=parse_file(raw,'application/pdf','long.pdf')
    assert len(result.page_texts[0])>12000
    assert 'FIN_DU_DOCUMENT' in result.page_texts[0]
    assert result.text_previews==result.page_texts


def test_date_alternatives_and_literal_conclusions():
    pages=['Prélevé le 08.04.202508.11.2026 Edité le 09.11.2026\nConclusion : Patient immunisé',
           'Conclusion : Sérologie négative à ce jour sur ce prélèvement.']
    assert sample_date_options(pages)==['2025-04-08','2026-11-08']
    assert report_conclusions(pages)==[{'page':1,'text':'Patient immunisé'},
        {'page':2,'text':'Sérologie négative à ce jour sur ce prélèvement.'}]


def test_full_transcripts_not_exposed_through_partial_lab_permission(client,login_as,post):
    login_as('patient');p=preview(client,data=report_bytes()).json();body=findings_body(p)
    body.update(retained_pages=[1,2,3,4],transcription_verified=True)
    assert post('/api/documents/confirm',body).status_code==200
    assert post('/api/patients/pat_marie/grants',{'family_id':'u_family','permissions':['labs'],'revoked':False}).status_code==200
    login_as('family')
    overview=client.get('/api/patients/pat_marie/overview').json()
    assert len(overview['findings'])==11
    assert overview['document_pages']==[]
