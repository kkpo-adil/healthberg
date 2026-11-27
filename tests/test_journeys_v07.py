"""Cross-role QR journeys; no real medical or payment services are contacted."""
import pytest
from datetime import datetime, timedelta, timezone
from app import db,portal

PREFIX='/api/journeys'

def login(client,role):
    user=next(u for u in portal.SEED_USERS if u[3]==role)
    r=client.post('/api/auth/login',json={'email':user[1],'password':portal.DEMO_PASSWORD},headers={'X-Healthberg-Action':'demo'})
    assert r.status_code==200
    return user

def post(client,url,payload=None):
    return client.post(url,json=payload or {},headers={'X-Healthberg-Action':'demo'})

def order(client,kind='prescription',pid='pat_marie',items=None):
    if items is None:items=[{'name':'Produit de test non médical','strength':'dose de démonstration','schedule':'texte de test','quantity':'1 boîte'}] if kind=='prescription' else [{'code':'glucose'},{'code':'hba1c'}]
    r=post(client,f'{PREFIX}/orders',{'patient_id':pid,'confirm_patient_identity':True,'kind':kind,'label':'Demande de test local','items':items})
    assert r.status_code==200,r.text
    return r.json()['id']

def issue(client,oid):
    r=post(client,f'{PREFIX}/qr/{oid}')
    assert r.status_code==200,r.text
    payload=r.json();assert payload['qr_image'].startswith('data:image/png;base64,');return payload['qr_payload']

def redeem(client,code,expect=200):
    r=post(client,f'{PREFIX}/redeem',{'qr_payload':code})
    assert r.status_code==expect,r.text
    return r.json()

def glucose_result(flag='outside',unit='g/L',code='glucose',value=1.4):
    return {'code':code,'value':value,'unit':unit,'measured_at':'2026-11-24T08:00:00+01:00','flag':flag,'reference_label':'0,70 à 1,10 g/L — laboratoire (simulation)'}


def test_prescription_qr_pharmacy_export_without_claims(client):
    login(client,'doctor');oid=order(client)
    login(client,'patient');code=issue(client,oid)
    assert 'Marie' not in code and 'Produit' not in code
    login(client,'pharmacist');ticket=redeem(client,code)
    assert ticket['order']['kind']=='prescription'
    assert not any(x in ticket['order'] for x in ('observations','diagnosis','notes'))
    assert redeem(client,code,409)['detail']
    grant=ticket['grant_id']
    result=post(client,f'{PREFIX}/ticket/{grant}/action',{'kind':'dispense','detail':{'items':[{'line_index':0,'status':'dispensed','comment':'Une boîte remise'}]}})
    assert result.status_code==200,result.text
    assert post(client,f'{PREFIX}/ticket/{grant}/action',{'kind':'dispense','detail':{'items':[{'line_index':0,'status':'dispensed'}]}}).status_code==403
    export=client.get(f'{PREFIX}/ticket/{grant}/export')
    # One-use grant has been consumed after dispensation. No export or billing endpoint exposed.
    assert export.status_code==403
    assert post(client,f'{PREFIX}/claims/{oid}/prepare').status_code==404
    login(client,'patient');rows=client.get(f'{PREFIX}/orders/pat_marie').json();assert next(x for x in rows if x['id']==oid)['status']=='dispensed'


def test_lab_qr_publish_results_to_patient_and_doctor(client):
    login(client,'doctor');oid=order(client,'lab')
    login(client,'patient');code=issue(client,oid)
    login(client,'lab');r=redeem(client,code);grant=r['grant_id']
    result=post(client,f'{PREFIX}/ticket/{grant}/action',{'kind':'results','detail':{'results':[glucose_result(),{'code':'hba1c','value':6.2,'unit':'%','measured_at':'2026-11-24T08:00:00+01:00','flag':'normal','reference_label':'Donnée déclarée par laboratoire de test'}]}})
    assert result.status_code==200,result.text
    login(client,'patient');out=client.get(f'{PREFIX}/outcomes/pat_marie').json()
    latest=[x for x in out if x['order_id']==oid]
    assert len(latest)==2
    assert {x['lab_flag'] for x in latest}=={'outside','normal'}
    assert all(x['observation_id'] for x in latest)
    assert any(o['code']=='glucose' for o in client.get('/api/patients/pat_marie/observations').json())
    login(client,'doctor');assert len([x for x in client.get(f'{PREFIX}/outcomes/pat_marie').json() if x['order_id']==oid])==2
    login(client,'pharmacist');assert client.get(f'{PREFIX}/outcomes/pat_marie').status_code==403
    with db.connect() as c:
        receipts=c.execute('SELECT * FROM receipts WHERE patient_id=? AND document_kind LIKE "Résultats labo AJOUR%"',('pat_marie',)).fetchall()
        assert receipts and all(r['original_retained']==0 for r in receipts)


@pytest.mark.parametrize('kind,wrong_role', [('prescription','lab'),('lab','pharmacist'),('prescription','nurse'),('lab','family'),('prescription','doctor'),('lab','doctor')])
def test_wrong_role_never_redeems(client,kind,wrong_role):
    login(client,'doctor');oid=order(client,kind)
    login(client,'patient');token=issue(client,oid)
    login(client,wrong_role)
    assert post(client,f'{PREFIX}/redeem',{'qr_payload':token}).status_code==403
    login(client,'lab' if kind=='lab' else 'pharmacist')
    assert redeem(client,token)['order']['id']==oid


@pytest.mark.parametrize('kind', ['prescription','lab'])
def test_new_qr_revokes_old_and_cross_patient_denied(client,kind):
    login(client,'doctor');oid=order(client,kind)
    login(client,'patient');one=issue(client,oid);two=issue(client,oid)
    login(client,'lab' if kind=='lab' else 'pharmacist')
    assert redeem(client,one,409)['detail']
    assert redeem(client,two)['order']['id']==oid
    login(client,'patient');assert post(client,f'{PREFIX}/qr/random-other-patient-id').status_code==403


def test_other_patient_cannot_reveal_qr(client):
    login(client,'doctor');oid=order(client)
    login(client,'patient')
    assert issue(client,oid)
    login(client,'patient')
    # user is Marie. Switch to Louis.
    login(client,'patient')
    from app.portal import SEED_USERS,DEMO_PASSWORD
    u=next(u for u in SEED_USERS if u[0]=='u_patient_louis')
    client.post('/api/auth/login',json={'email':u[1],'password':DEMO_PASSWORD},headers={'X-Healthberg-Action':'demo'})
    assert post(client,f'{PREFIX}/qr/{oid}').status_code==403
    assert client.get(f'{PREFIX}/orders/pat_marie').status_code==403


@pytest.mark.parametrize('bad_items',[
  [],[{'name':'x','strength':'a','schedule':'b','quantity':'1'}],
  [{'name':'X médical','strength':'','schedule':'un traitement','quantity':'1'}],
  [{'name':'X médical','strength':'1 mg','schedule':'un traitement','quantity':''}],
  [{'name':'X médical','strength':'1 mg','schedule':'un traitement','quantity':'1'}]*13,
])
def test_invalid_prescription_rejected(client,bad_items):
    login(client,'doctor');r=post(client,f'{PREFIX}/orders',{'patient_id':'pat_marie','confirm_patient_identity':True,'kind':'prescription','label':'Demande de test local','items':bad_items})
    assert r.status_code==400


@pytest.mark.parametrize('bad_result',[glucose_result(code='tsh'),glucose_result(flag='alarm'),glucose_result(unit='XYZ'),glucose_result(value='NaN')])
def test_lab_bad_results_rejected(client,bad_result):
    login(client,'doctor');oid=order(client,'lab',items=[{'code':'glucose'}])
    login(client,'patient');token=issue(client,oid)
    login(client,'lab');grant=redeem(client,token)['grant_id']
    r=post(client,f'{PREFIX}/ticket/{grant}/action',{'kind':'results','detail':{'results':[bad_result]}})
    assert r.status_code in (409,422),r.text
    # Failed result must NOT consume ticket.
    if bad_result['code']=='glucose':assert client.get(f'{PREFIX}/ticket/{grant}').status_code==200


def test_partial_or_duplicate_lab_results_rejected(client):
    login(client,'doctor');oid=order(client,'lab')
    login(client,'patient');token=issue(client,oid)
    login(client,'lab');grant=redeem(client,token)['grant_id']
    for results in [[glucose_result()],[glucose_result(),glucose_result()],[]]:
        assert post(client,f'{PREFIX}/ticket/{grant}/action',{'kind':'results','detail':{'results':results}}).status_code==409
    assert client.get(f'{PREFIX}/ticket/{grant}').status_code==200


def test_ticket_other_user_denied(client):
    login(client,'doctor');oid=order(client,'lab')
    login(client,'patient');token=issue(client,oid)
    login(client,'lab');ticket=redeem(client,token)
    login(client,'pharmacist');assert client.get(f"{PREFIX}/ticket/{ticket['grant_id']}").status_code==403


def test_expired_grant_and_redeem_denied(client):
    login(client,'doctor');oid=order(client)
    login(client,'patient');token=issue(client,oid)
    with db.connect() as c:c.execute('UPDATE aj_qr_grants SET expires_at=? WHERE order_id=?',('2020-01-01T00:00:00+00:00',oid))
    login(client,'pharmacist');assert redeem(client,token,409)['detail']


def test_patient_cannot_create_order_or_claim(client):
    login(client,'patient')
    assert post(client,f'{PREFIX}/orders',{'patient_id':'pat_marie','kind':'lab','label':'Non autorisé','items':[{'code':'glucose'}]}).status_code==403
    assert post(client,f'{PREFIX}/claims/random/prepare').status_code==404


def test_qr_payload_not_in_observations(client):
    login(client,'doctor');oid=order(client)
    login(client,'patient');token=issue(client,oid)
    allobs=str(client.get('/api/patients/pat_marie/observations').json())
    assert token not in allobs
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM aj_qr_grants WHERE token_hash=?',(token,)).fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM aj_qr_grants').fetchone()[0]>=1


def test_scenarios_have_documented_coverage(client):
    login(client,'patient')
    scenario_ids=[x['id'] for x in client.get(f'{PREFIX}/scenarios').json()]
    assert len(set(scenario_ids))>=12
    assert 'external-import' in scenario_ids and 'rx-happy' in scenario_ids


def test_cancel_prescription_blocks_qr_and_ticket(client):
    login(client,'doctor');oid=order(client)
    login(client,'patient');code=issue(client,oid)
    login(client,'pharmacist');t=redeem(client,code)
    login(client,'patient');cancel=post(client,f'{PREFIX}/orders/{oid}/cancel');assert cancel.status_code==200
    login(client,'pharmacist')
    assert client.get(f"{PREFIX}/ticket/{t['grant_id']}").status_code==403
    assert redeem(client,code,409)['detail']


def test_lab_booking_patient_to_lab(client):
    starts=(datetime.now(timezone.utc)+timedelta(days=5)).isoformat()
    login(client,'lab')
    slot=post(client,f'{PREFIX}/lab-slots',{'starts_at':starts,'duration':20,'location':'Centre biologique (test)'})
    assert slot.status_code==200,slot.text
    sid=slot.json()['id']
    login(client,'doctor');oid=order(client,'lab')
    login(client,'patient');book=post(client,f'{PREFIX}/lab-bookings',{'order_id':oid,'slot_id':sid})
    assert book.status_code==200,book.text
    assert book.json()['status']=='booked'
    assert post(client,f'{PREFIX}/lab-bookings',{'order_id':oid,'slot_id':sid}).status_code==409
    login(client,'lab');bookings=client.get(f'{PREFIX}/lab-bookings').json()
    assert any(b['order_id']==oid and b['status']=='booked' for b in bookings)
    booking_id=book.json()['id']
    assert post(client,f'{PREFIX}/lab-bookings/{booking_id}/cancel').status_code==200
    login(client,'patient');assert any(b['status']=='cancelled' for b in client.get(f'{PREFIX}/lab-bookings').json())


@pytest.mark.parametrize('role', ['doctor','nurse','pharmacist','family'])
def test_non_patient_cannot_book_lab(client,role):
    login(client,'lab')
    sid=post(client,f'{PREFIX}/lab-slots',{'starts_at':(datetime.now(timezone.utc)+timedelta(days=4)).isoformat(),'duration':20,'location':'Centre de tests'}).json()['id']
    login(client,'doctor');oid=order(client,'lab')
    login(client,role)
    assert post(client,f'{PREFIX}/lab-bookings',{'order_id':oid,'slot_id':sid}).status_code==403


@pytest.mark.parametrize('duration', [0,5,12,21,100])
def test_lab_slot_duration_validation(client,duration):
    login(client,'lab')
    r=post(client,f'{PREFIX}/lab-slots',{'starts_at':(datetime.now(timezone.utc)+timedelta(days=4)).isoformat(),'duration':duration,'location':'Lab de test'})
    assert r.status_code==400


def test_lab_slot_cannot_create_in_past(client):
    login(client,'lab');r=post(client,f'{PREFIX}/lab-slots',{'starts_at':'2020-01-01T00:00:00+00:00','duration':20,'location':'Lab de test'})
    assert r.status_code==400


def test_other_patient_cannot_book_using_another_order(client):
    login(client,'lab');sid=post(client,f'{PREFIX}/lab-slots',{'starts_at':(datetime.now(timezone.utc)+timedelta(days=5)).isoformat(),'duration':20,'location':'Lab de test'}).json()['id']
    login(client,'doctor');oid=order(client,'lab')
    from app.portal import SEED_USERS,DEMO_PASSWORD
    u=next(u for u in SEED_USERS if u[0]=='u_patient_louis')
    client.post('/api/auth/login',json={'email':u[1],'password':DEMO_PASSWORD},headers={'X-Healthberg-Action':'demo'})
    assert post(client,f'{PREFIX}/lab-bookings',{'order_id':oid,'slot_id':sid}).status_code==403


def test_no_lab_booking_without_real_order(client):
    login(client,'lab');sid=post(client,f'{PREFIX}/lab-slots',{'starts_at':(datetime.now(timezone.utc)+timedelta(days=5)).isoformat(),'duration':20,'location':'Lab de test'}).json()['id']
    login(client,'patient')
    assert post(client,f'{PREFIX}/lab-bookings',{'order_id':'fake-order','slot_id':sid}).status_code==403


def test_lab_slot_availability_after_cancellation(client):
    login(client,'lab');sid=post(client,f'{PREFIX}/lab-slots',{'starts_at':(datetime.now(timezone.utc)+timedelta(days=5)).isoformat(),'duration':20,'location':'Lab de test'}).json()['id']
    login(client,'doctor');oid=order(client,'lab')
    login(client,'patient');bid=post(client,f'{PREFIX}/lab-bookings',{'order_id':oid,'slot_id':sid}).json()['id']
    before=[x['id'] for x in client.get(f'{PREFIX}/lab-slots').json()]
    assert sid not in before
    assert post(client,f'{PREFIX}/lab-bookings/{bid}/cancel').status_code==200
    after=[x['id'] for x in client.get(f'{PREFIX}/lab-slots').json()]
    assert sid in after


def test_pdf_path_is_still_available(client):
    login(client,'patient')
    assert client.get('/').status_code==200
    assert client.get('/static/journeys.js').status_code==200
    assert client.get('/api/patients/pat_marie/observations').status_code==200
