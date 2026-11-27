"""Read real raster pixels with Tesseract, without mocking OCR results."""
import os
import fitz
import pytest
import pytesseract
from app.extraction import parse_file
from tests.test_report_import_v096 import report_bytes


def require_ocr():
    try:languages=pytesseract.get_languages(config='')
    except pytesseract.TesseractNotFoundError:
        if os.getenv('CI'):pytest.fail('Tesseract must be installed in CI')
        pytest.skip('Tesseract is not installed locally')
    if os.getenv('AJOUR_REQUIRE_FRENCH_OCR'):
        assert 'fra' in languages,'CI must exercise French OCR'


def test_scan_image_extracts_qualitative_and_bounded_results():
    require_ocr()
    with fitz.open(stream=report_bytes(),filetype='pdf') as doc:
        image=doc[0].get_pixmap(matrix=fitz.Matrix(2,2)).tobytes('png')
    parsed=parse_file(image,'image/png','synthetic-scan.png')
    assert parsed.method=='OCR'
    assert {f.code for f in parsed.findings}=={'hbs_ag','hbs_ag_index','hbs_ab','hbc_ab','hbc_ab_index'}
    assert next(f.value for f in parsed.findings if f.code=='hbs_ab')=='>1000'


def test_two_page_scanned_pdf_is_not_treated_as_empty():
    require_ocr();scanned=fitz.open()
    with fitz.open(stream=report_bytes(),filetype='pdf') as source:
        for page in list(source)[:2]:
            out=scanned.new_page(width=page.rect.width,height=page.rect.height)
            out.insert_image(out.rect,stream=page.get_pixmap(matrix=fitz.Matrix(3,3)).tobytes('png'))
    raw=scanned.tobytes(deflate=True);scanned.close()
    result=parse_file(raw,'application/pdf','synthetic-scanned.pdf')
    assert len(result.findings)==11
    assert result.page_count==2 and all(result.page_texts)
    assert 'OCR' in result.method


def report_with_two_dates(overlaid):
    with fitz.open(stream=report_bytes(), filetype='pdf') as doc:
        for page in doc:
            # Cover the original fixture heading and add a date field distinct
            # from the results. In the overlay case the first date stays in the
            # PDF text layer, although its glyphs are covered on the page.
            page.add_redact_annot(fitz.Rect(35, 30, 550, 60), fill=(1, 1, 1))
            page.apply_redactions()
            page.insert_text((40, 52), 'Prélevé le 08.04.2025', fontsize=11)
            if overlaid:
                page.draw_rect(fitz.Rect(37, 37, 165, 58), color=None, fill=(1, 1, 1))
            page.insert_text((40, 52 if overlaid else 73), 'Prélevé le 08.11.2026', fontsize=11)
        return doc.tobytes()


@pytest.mark.parametrize('overlaid', [True, False])
def test_pdf_rechecks_conflicting_dates_against_rendered_pixels(client, login_as, overlaid):
    from tests.test_api import preview

    require_ocr()
    login_as('patient')
    response = preview(client, data=report_with_two_dates(overlaid))
    assert response.status_code == 200
    payload = response.json()
    assert len(payload['findings']) == 11
    assert payload['document_date'] is None
    assert payload['sample_date_options'] == ['2025-04-08', '2026-11-08']
    evidence = payload['sample_date_evidence']
    if overlaid:
        assert evidence['date'] == '2026-11-08'
        assert evidence['page'] == 1
        assert '08.11.2026' in evidence['excerpt']
    else:
        assert evidence is None
