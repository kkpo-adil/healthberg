"""Regressions found while reviewing the 0.9.7 application, not source-string checks."""
import pytest
from app import db, prescription_import
from app.extraction import extract_candidates, parse_date
from tests.test_api import preview, pdf_bytes
from tests.test_prescription_import_v092 import pdf_bytes as prescription_pdf


def test_blood_pressure_is_not_doubled_by_two_pdf_text_views():
    line='Date : 08/11/2026\nTension artérielle : 142/88 mmHg'
    candidates,_,_=extract_candidates([line+'\n'+line])
    assert [(x.code,x.value) for x in candidates]==[('systolic',142),('diastolic',88)]


def test_birthdate_is_not_used_as_measurement_date():
    assert parse_date('Patient : DEMO\nNé le 11.03.1980\nGlycémie : 1,2 g/L') is None


@pytest.mark.parametrize('raw',['abc','nan','inf'])
def test_invalid_manual_numeric_text_is_a_client_error(client,login_as,post,raw):
    login_as('patient');p=preview(client,data=pdf_bytes()).json()
    entry=dict(code='weight',label='Poids',value=70,unit='kg',original_value=raw,original_unit='kg',
               measured_at='2026-11-08T12:00:00+00:00',page=1,manual=True)
    body=dict(import_token=p['import_token'],patient_id='pat_marie',confirm_patient_identity=True,
              manual_verified=True,candidates=[entry])
    assert post('/api/documents/confirm',body).status_code==400
    assert not any(r['sha256']==p['sha256'] for r in db.list_receipts('pat_marie'))


def test_origin_matches_actual_local_port(client):
    assert client.get('/api/health',headers={'Origin':'http://testserver'}).status_code==200
    assert client.get('/api/health',headers={'Origin':'http://testserver:9999'}).status_code==403


def test_prescription_pdf_page_count_is_real():
    import fitz
    raw=prescription_pdf()
    doc=fitz.open(stream=raw,filetype='pdf');doc.new_page();data=doc.tobytes();doc.close()
    assert prescription_import.extract_pdf(data,'Marie Martin')['pages']==2
