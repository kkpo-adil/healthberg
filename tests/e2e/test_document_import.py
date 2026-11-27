"""Exercise the UI, real upload, confirmation payload, DB persistence and reload."""
from playwright.sync_api import expect
import pytest
from app.portal import SEED_USERS
from tests.test_report_import_v096 import report_bytes

pytestmark=pytest.mark.e2e


def login(page,origin,role='patient'):
    email=next(u[1] for u in SEED_USERS if u[3]==role)
    page.set_default_timeout(8000)
    page.goto(origin)
    page.locator(f'[data-account="{email}"]').click()
    page.locator('#loginBtn').click()
    expect(page.locator('#appShell')).to_be_visible()
    expect(page.locator('#pageBody')).not_to_be_empty()


@pytest.mark.parametrize('ambiguous_date',[False,True],ids=['date-read','date-ambiguous'])
def test_complete_document_round_trip(browser_session,ambiguous_date):
    browser,origin=browser_session
    context=browser.new_context();page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        login(page,origin)
        page.locator('#pageBody [data-tab="documents"]').click()
        page.locator('#openImport').click()
        page.locator('#docFile').set_input_files({'name':'synthetic.pdf','mimeType':'application/pdf','buffer':report_bytes(ambiguous_date=ambiguous_date)})
        page.get_by_role('button',name='Analyser le document',exact=True).click()
        expect(page.locator('#previewSpace')).to_contain_text('11 résultats structurés')
        expect(page.locator('[data-finding]')).to_have_count(11)
        expect(page.locator('[data-retain-page]')).to_have_count(4)
        expect(page.locator('#ajImportDate')).to_have_value('' if ambiguous_date else '2026-11-08')
        if ambiguous_date:
            page.get_by_role('button',name='08/11/2026',exact=True).click()
        else:
            page.locator('#ajImportDate').fill('2026-11-08')
        expect(page.locator('#ajImportDate')).to_have_value('2026-11-08')
        expect(page.locator('[data-finding-date="10"]')).to_have_value('2026-11-08')
        # A user's individual override must survive changing the common date.
        page.locator('[data-finding-date="0"]').fill('2026-11-07')
        page.locator('#ajImportDate').fill('2026-11-09');page.locator('#ajImportDate').press('Tab')
        expect(page.locator('[data-finding-date="0"]')).to_have_value('2026-11-07')
        expect(page.locator('[data-finding-date="10"]')).to_have_value('2026-11-09')
        page.locator('#ajTranscriptAck').check()
        with page.expect_response(lambda r:r.url.endswith('/api/documents/confirm')) as result:
            page.locator('#confirmDocument').click()
        assert result.value.status==200,result.value.text()
        receipt=result.value.json()['receipt']
        assert receipt['findings_created']==11 and receipt['pages_retained']==4
        expect(page.locator('#modal')).to_be_hidden()
        expect(page.locator('#pageBody')).to_contain_text('>1000')
        page.reload()
        page.locator('#pageBody [data-tab="documents"]').click()
        page.get_by_text('Page 4 · transcription vérifiée par l’utilisateur',exact=True).click()
        expect(page.get_by_text('Informations administratives fictives',exact=False)).to_be_visible()
        overview=page.request.get(origin+'/api/patients/pat_marie/overview').json()
        assert len(overview['findings'])==11 and len(overview['document_pages'])==4
        dates={finding['code']:finding['measured_at'][:10] for finding in overview['findings']}
        assert dates['hbs_ag']=='2026-11-07'
        assert dates['gonorrhoeae']=='2026-11-09'
        assert not errors,errors
    finally:context.close()


def test_professional_without_patient_can_open_agenda(browser_session):
    browser,origin=browser_session
    context=browser.new_context();page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        login(page,origin,'optician')
        page.get_by_role('button',name='Gérer mon agenda').click()
        expect(page.locator('#slotForm')).to_be_visible()
        assert not errors,errors
    finally:context.close()
