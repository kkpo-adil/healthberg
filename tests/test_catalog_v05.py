"""V0.5: catalog, clinical specialty projections and privacy remain synthetic-only."""
from datetime import datetime, timezone


def test_registry_is_universal_but_not_a_medical_order_set(client,login_as):
    login_as('patient')
    r=client.get('/api/catalog/health-indicators')
    assert r.status_code==200
    data=r.json()
    assert len(data['metrics']) >= 45
    assert len(data['specialties']) >= 44
    codes={m['code'] for m in data['metrics']}
    assert {'glucose','hba1c','systolic','diastolic','cholesterol','vaccination','screening','surgery','oncology','mood'} <= codes
    assert any(m['code']=='surgery' and not m['numeric_available'] for m in data['metrics'])
    assert all('simple' in m and 'domain' in m for m in data['metrics'])
    assert 'aucun examen' in data['notice'].lower()


def test_patient_map_values_provenance_and_unrecorded_are_distinct(client,login_as):
    login_as('patient')
    r=client.get('/api/patients/pat_marie/health-map')
    assert r.status_code==200
    data=r.json()
    glucose=next(x for x in data['items'] if x['code']=='glucose')
    assert glucose['status']=='measured'
    assert glucose['latest']['source_id']
    assert glucose['latest']['measured_at']
    assert 'sucre' in glucose['explanation'].lower()
    future=next(x for x in data['items'] if x['code']=='surgery')
    assert future['status']=='not_recorded'
    assert future['latest'] is None
    assert 'pas qu’un examen est nécessaire' in data['notice']
    meds=next(x for x in data['items'] if x['code']=='medication')
    assert meds['status']=='documented'
    assert meds['summary']


def test_specialist_projection_does_not_enlarge_authorizations(client,login_as,post):
    login_as('doctor')
    initial=client.get('/api/preferences/specialty').json()
    assert initial['specialty']=='Médecine générale'
    r=post('/api/preferences/specialty',{'specialty':'Médecine cardiovasculaire'})
    assert r.status_code==200,r.text
    report=client.get('/api/patients/pat_marie/health-map').json()
    assert report['specialty']['specialty']=='Médecine cardiovasculaire'
    assert report['items'][0]['code'] in report['specialty']['priority']
    assert report['specialty']['workflow']
    assert post('/api/preferences/specialty',{'specialty':'Spécialité inventée'}).status_code==400
    assert client.get('/api/patients/inconnu/health-map').status_code==404
    login_as('family')
    assert client.get('/api/preferences/specialty').status_code==403
    assert post('/api/preferences/specialty',{'specialty':'Médecine générale'}).status_code==403
    family_map=client.get('/api/patients/pat_marie/health-map').json()
    codes={x['code'] for x in family_map['items']}
    assert 'glucose' in codes and 'systolic' in codes
    assert 'hba1c' not in codes and 'mood' not in codes and 'creatinine' not in codes
    assert 'psychosocial' not in str(family_map).lower()


def test_pharmacy_and_lab_cannot_read_universal_patient_map(client,login_as):
    for role in ('lab','pharmacist'):
        login_as(role)
        assert client.get('/api/patients/pat_marie/health-map').status_code==403


def test_new_lab_measure_in_patient_story_but_not_pharmacist_or_family(client,login_as,post):
    login_as('lab')
    data={'code':'crp','value':4.7,'unit':'mg/L','measured_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat(),'context':'Analyse fictive'}
    assert post('/api/patients/pat_marie/measures',data).status_code==200
    login_as('patient')
    new=next(x for x in client.get('/api/patients/pat_marie/health-map').json()['items'] if x['code']=='crp')
    assert new['status']=='measured' and new['latest']['value']==4.7
    observations=client.get('/api/patients/pat_marie/observations?code=crp').json()
    assert len(observations)==1 and observations[0]['source_id']
    login_as('family')
    assert 'crp' not in {x['code'] for x in client.get('/api/patients/pat_marie/health-map').json()['items']}
    login_as('pharmacist')
    assert 'crp' not in {x['code'] for x in client.get('/api/patients/pat_marie/overview').json()['observations']}


def test_measures_reject_unknown_units_or_nonfinite(client,login_as,post):
    login_as('patient')
    now=datetime.now(timezone.utc).isoformat()
    for value,unit in [(4.5,'g/L'), ('NaN','mmol/L')]:
        resp=post('/api/patients/pat_marie/measures',{'code':'potassium','value':value,'unit':unit,'measured_at':now})
        assert resp.status_code in (400,422)


def test_expanded_report_parser_extracts_only_explicit_documented_values():
    from app.extraction import extract_candidates
    report='''Date du bilan : 19/10/2025
LDL : 1,20 g/L
Triglycérides : 92 mg/dL
CRP : 3,7 mg/L
Potassium : 4,2 mmol/L
TSH : 1,8 mUI/L
Hémoglobine : 13,4 g/dL
'''
    candidates,day,warnings=extract_candidates([report])
    values={x.code:x.value for x in candidates}
    assert day=='2025-10-19' and not warnings
    assert values=={'ldl':1.2,'triglycerides':0.92,'crp':3.7,'potassium':4.2,'tsh':1.8,'hemoglobin':13.4}
    # A censored value (< / >) cannot become an ordinary numeric result.
    censored,_,warnings=extract_candidates(['Date : 19/10/2025\nCRP : < 2 mg/L'])
    assert censored==[] and any('censurée' in x for x in warnings)
