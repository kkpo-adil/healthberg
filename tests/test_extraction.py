import pytest
from app.extraction import extract_candidates, parse_file
from app.terminology import normalize

TEST='''LABORATOIRE FICTIF\nDate du bilan : 14/09/2025\nGlycémie : 1,23 g/L\nHbA1c : 7,2 %\nCréatinine : 12,4 mg/L\nDFG : 67 mL/min/1,73m²\nCholestérol total : 1,89 g/L\nTension artérielle : 142/88 mmHg'''

def test_conservative_extraction():
    c,d,w=extract_candidates([TEST])
    assert d=='2025-09-14' and not w
    assert {x.code for x in c}=={'glucose','hba1c','creatinine','egfr','cholesterol','systolic','diastolic'}
    assert next(x for x in c if x.code=='glucose').value==1.23

def test_glucose_units_no_cross_merge():
    assert normalize('glucose',100,'mg/dL')==(1.0,'g/L')
    assert abs(normalize('glucose',5.55,'mmol/L')[0]-1.0)<0.0002
    assert normalize('hba1c',45,'mmol/mol') is None
    assert normalize('systolic',13,'cmHg') is None

def test_censored_results_dropped():
    c,d,w=extract_candidates(['Date : 12/04/2024\nGlycémie : < 0,60 g/L\nCréatinine : 10 mg/L'])
    assert [x.code for x in c]==['creatinine']
    assert any('censurée' in s for s in w)

def test_date_not_invented():
    c,d,w=extract_candidates(['Glycémie : 0,96 g/L'])
    assert d is None and c[0].measured_at is None
    assert any('Date' in s for s in w)

def test_invalid_file_type_rejected():
    with pytest.raises(ValueError,match='Format'):
        parse_file(b'TRASH','text/plain','x.txt')

def test_pdf_native_text():
    import fitz
    doc=fitz.open()
    page=doc.new_page(width=600,height=700)
    page.insert_text((42,50),'Date du bilan : 14/09/2025\nGlycemie : 1,23 g/L\nHbA1c : 7,2 %',fontsize=14)
    data=doc.tobytes();doc.close()
    parsed=parse_file(data,'application/pdf','test.pdf')
    assert parsed.page_count==1
    assert parsed.method=='text-native'
    assert len(parsed.candidates)==2
    assert len(parsed.sha256)==64

def test_image_pixels_limited():
    with pytest.raises(ValueError): parse_file(b'','image/png','x.png')

def test_medication_lines_prescription_only():
    from app.extraction import extract_medications
    pages=['Ordonnance du 11/04/2023\nMetformine 850 mg - un comprime matin et soir\nAmlodipine 5 mg - un comprime le matin']
    meds=extract_medications(pages,'2023-04-11')
    assert len(meds)==2
    assert meds[0].name=='Metformine' and meds[0].strength=='850mg'
    assert extract_medications(['Analyse\nMetformine 850 mg - 1 le matin'],'2023-04-11')==[]
