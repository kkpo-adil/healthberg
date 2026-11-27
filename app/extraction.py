"""Conservative PDF/image extraction for local fictional demos only.

The extraction output is a *candidate*, not a clinical fact. Uploaded bytes are never saved
by this module. The caller may retain reviewed page transcriptions after explicit confirmation.
"""
from __future__ import annotations
import hashlib
import io
import re
import unicodedata
from datetime import datetime
from dataclasses import dataclass

from .models import Candidate,MedicationCandidate,ReportFinding
from .report_findings import extract_findings, unparsed_result_labels
from .terminology import METRIC_BY_CODE, normalize

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PAGES = 30

@dataclass
class ParsedDocument:
    sha256: str
    page_count: int
    method: str
    candidates: list[Candidate]
    medications: list[MedicationCandidate]
    findings: list[ReportFinding]
    document_date: str | None
    issuer: str | None
    warnings: list[str]
    text_previews: list[str] | None = None
    page_texts: list[str] | None = None


def clean(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')


def parse_date(text: str) -> str | None:
    # Prefer sample/measurement dates; never use the upload date or date of birth.
    date_pattern = r'(\d{2})[/.\-](\d{2})[/.\-](\d{4})'
    def valid_dates(part):
        values = []
        for m in re.finditer(date_pattern, part):
            try: values.append(datetime(int(m[3]), int(m[2]), int(m[1])).date().isoformat())
            except ValueError: pass
        return values
    explicit = []
    for line in text.splitlines():
        m = re.search(r'(?:pr[eé]lev[eé](?:pr[eé]lev[eé])?|pr[eé]l[eè]vement|date de mesure|date d.examen|date du bilan)\s*(?:le\s*)*[:\-]?\s*', line, re.I)
        if m:
            # A modified PDF can carry old and new dates in the same text layer.
            part = re.split(r'(?:[eé]dit[eé]|valid[eé]|prescrit|\s+[àa]\s+\d{1,2}:)', line[m.end():], flags=re.I)[0]
            explicit.extend(valid_dates(part))
    if explicit:
        unique = set(explicit)
        return next(iter(unique)) if len(unique) == 1 else None
    for line in text.splitlines():
        if re.search(r'naissance|\bne(?:e)?\s+le\b|antecedents|negatif.*\ble\b', clean(line), re.I): continue
        dates = valid_dates(line)
        if dates: return dates[0]
    return None


# Deliberately confined to well-formed lab lines to avoid accidental clinical hallucination.
LAB_REGEX = [
    ('glucose',r'\b(?:glyc[ée]mie|glucose)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]\d+|[<>≤≥]?\s*\d+)\s*(g\s*/\s*l|mg\s*/\s*dl|mmol\s*/\s*l)\b'),
    ('hba1c',r'\b(?:hba1c|h[ée]moglobine\s+glyqu[ée]e)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]\d+|[<>≤≥]?\s*\d+)\s*(%)'),
    ('creatinine',r'\b(?:cr[ée]atinine)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]\d+|[<>≤≥]?\s*\d+)\s*(mg\s*/\s*l|mg\s*/\s*dl|[µμ]mol\s*/\s*l)\b'),
    ('egfr',r'\b(?:d\.?f\.?g\.?|e\.?g\.?f\.?r\.?)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(ml\s*/\s*min\s*/\s*1[.,]73\s*m[²2])'),
    ('cholesterol',r'\b(?:cholest[ée]rol\s+total)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]\d+|[<>≤≥]?\s*\d+)\s*(g\s*/\s*l|mg\s*/\s*dl)\b'),
    ('weight',r'\b(?:poids)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(kg)\b'),
    ('pulse',r'\b(?:pouls|fr[ée]quence\s+cardiaque)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(bpm|/\s*min)\b'),
    ('ldl',r'\b(?:cholest[ée]rol\s+ldl|ldl(?:-cholest[ée]rol)?)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(g\s*/\s*l|mg\s*/\s*dl)\b'),
    ('hdl',r'\b(?:cholest[ée]rol\s+hdl|hdl(?:-cholest[ée]rol)?)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(g\s*/\s*l|mg\s*/\s*dl)\b'),
    ('triglycerides',r'\b(?:triglyc[ée]rides)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(g\s*/\s*l|mg\s*/\s*dl)\b'),
    ('hemoglobin',r'\b(?:h[ée]moglobine)(?!\s+glyqu[ée]e)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(g\s*/\s*dl|g\s*/\s*l)\b'),
    ('crp',r'\b(?:crp|prot[ée]ine\s+c[- ]r[ée]active)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(mg\s*/\s*l)\b'),
    ('potassium',r'\b(?:potassium)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(mmol\s*/\s*l)\b'),
    ('sodium',r'\b(?:sodium)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(mmol\s*/\s*l)\b'),
    ('tsh',r'\b(?:tsh)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(mUI\s*/\s*l)\b'),
    ('psa',r'\b(?:psa)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(ng\s*/\s*ml)\b'),
    ('ferritin',r'\b(?:ferritine)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*([µμ]g\s*/\s*l)\b'),
    ('alat',r'\b(?:alat|tgp)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(UI\s*/\s*L)\b'),
    ('asat',r'\b(?:asat|tgo)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(UI\s*/\s*L)\b'),
    ('platelets',r'\b(?:plaquettes)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(G\s*/\s*L)\b'),
    ('leukocytes',r'\b(?:leucocytes|globules\s+blancs)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(G\s*/\s*L)\b'),
    ('albuminuria',r'\b(?:albuminurie)\b[^\n\r]{0,36}?([<>≤≥]?\s*\d+[.,]?\d*)\s*(mg\s*/\s*L)\b'),


]
BP_REGEX=re.compile(r'\b(?:tension(?:\s+art[ée]rielle)?|pression\s+art[ée]rielle|TA)\s*[:\-]?\s*(\d{2,3})\s*[/\-]\s*(\d{2,3})\s*(?:mmHg)?\b',re.I)


def _rebuild_table_lines(page):
    """Rejoin words by physical row, not PDF drawing/content-stream order.

    Many labs use a separate PDF text block per table column; ``get_text('text')``
    then returns every analyte name followed by every result. Aligning words by
    y-position produces reviewable *candidates* without fabricating values.
    """
    words=page.get_text('words',sort=True)
    if not words:return ''
    rows=[]
    for w in sorted(words,key=lambda x:(round(x[1]/3),x[0])):
        y=(float(w[1])+float(w[3]))/2
        # Split at height difference of one printed line, not columns.
        target=next((row for row in reversed(rows[-4:]) if abs(y-row[0])<=3.0),None)
        if target is None:target=[y,[]];rows.append(target)
        target[1].append((float(w[0]),str(w[4])))
    return '\n'.join(' '.join(word for _,word in sorted(row[1])) for row in rows)


def _table_neighbor_lines(text):
    """Support analyte name on its own line and the next line containing a result.

    Never combine a name with a reference-range line such as ``0.7 - 1.1``;
    the accepted neighbor must START with a single numeric value + unit.
    """
    lines=[line.strip() for line in text.splitlines()]
    compiled=[(code,re.compile(p,re.I)) for code,p in LAB_REGEX]
    for index,line in enumerate(lines[:-1]):
        if not line or any(p.search(line) for _,p in compiled):continue
        if re.search(r'\d',line):continue
        if not any(re.search(r'\b'+re.escape(alias)+r'\b',clean(line),re.I) for metric in METRIC_BY_CODE.values() for alias in metric.aliases):continue
        neighbor=lines[index+1]
        if re.match(r'^\s*[<>≤≥]?\s*\d+(?:[.,]\d+)?\s*(?:g\s*/\s*l|mg\s*/\s*dl|mg\s*/\s*l|mmol\s*/\s*l|[µμ]mol\s*/\s*l|[µμ]g\s*/\s*l|g\s*/\s*dl|%|mUI\s*/\s*l|ng\s*/\s*ml|ml\s*/\s*min\s*/\s*1[.,]73\s*m[²2])',neighbor,re.I):
            yield line+' : '+neighbor

def extract_candidates(pages: list[str]) -> tuple[list[Candidate], str|None, list[str]]:
    candidates=[]; warnings=[]
    document_date=parse_date('\n'.join(pages))
    if not document_date: warnings.append('Date de prélèvement/mesure absente ou ambiguë : sélectionner une date vérifiée avant confirmation.')
    seen=set()
    for page_index,text in enumerate(pages,1):
        for line in [*text.splitlines(),*_table_neighbor_lines(text)]:
            line=line.strip()
            if not line or len(line)>1000: continue
            bp=BP_REGEX.search(line)
            if bp:
                for code,raw in [('systolic',bp[1]),('diastolic',bp[2])]:
                    key=(page_index,code,float(raw),'mmHg')
                    if key in seen:continue
                    seen.add(key)
                    candidates.append(Candidate(code=code,label=METRIC_BY_CODE[code].label,value=float(raw),unit='mmHg',original_value=raw,original_unit='mmHg',page=page_index,measured_at=document_date,source_text=line[:180],confidence='review',context='Tension mesurée ensemble'))
            for code,pat in LAB_REGEX:
                m=re.search(pat,line,re.I)
                if not m: continue
                raw=m[1].strip()
                if raw[0] in '<>≤≥':
                    warnings.append(f'Valeur censurée sur page {page_index} : {line[:70]}. Non convertie automatiquement.')
                    continue
                v=float(raw.replace(',','.')); raw_unit=m[2].replace(' ','')
                result=normalize(code,v,raw_unit)
                if result is None:
                    warnings.append(f'Unité non prise en charge page {page_index}: {raw_unit}')
                    continue
                normalized,unit=result
                key=(page_index,code,normalized,unit)
                if key in seen:continue
                seen.add(key)
                candidates.append(Candidate(code=code,label=METRIC_BY_CODE[code].label,value=normalized,unit=unit,original_value=raw,original_unit=raw_unit,page=page_index,measured_at=document_date,source_text=line[:180],confidence='review'))
    if not candidates: warnings.append('Aucune valeur structurée reconnue : lecture manuelle nécessaire. Aucun fait créé.')
    return candidates,document_date,warnings


RX_LINE = re.compile(r"^(?P<name>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{2,48}?)\s+(?P<strength>\d+(?:[.,]\d+)?\s*(?:mg|µg|μg|mcg|g))\b(?:\s*(?:[-—:]\s*)?(?P<directions>.*))?$",re.I)

def extract_medications(pages:list[str],document_date:str|None)->list[MedicationCandidate]:
    """Candidate medication lines only on clearly identified prescriptions. Historical by default."""
    out=[]
    for page,text in enumerate(pages,1):
        if not re.search(r'\b(?:ordonnance|prescription\s+m[ée]dicale)\b',text,re.I):continue
        for line in text.splitlines():
            line=line.strip()
            m=RX_LINE.fullmatch(line)
            if not m:continue
            name=m.group('name').strip()
            if clean(name) in {'date','patient','docteur','medecin','ordonnance','numero'}:continue
            out.append(MedicationCandidate(name=name,strength=m.group('strength').replace(' ',''),directions=(m.group('directions') or '').strip(),page=page,source_text=line[:180],document_date=document_date))
    return out

def _ocr_image(image,warnings:list[str])->str:
    import pytesseract
    from PIL import ImageEnhance, ImageOps
    try:
        languages=pytesseract.get_languages(config='')
        if 'fra' in languages and 'eng' in languages:lang='fra+eng'
        elif 'fra' in languages:lang='fra'
        elif 'eng' in languages:lang='eng';warnings.append('OCR français indisponible : lecture avec le modèle anglais, à vérifier.')
        else:raise ValueError('Moteur OCR sans données de langue (installer tesseract et tesseract-lang).')
        image=ImageOps.autocontrast(ImageOps.grayscale(image))
        if image.width<1250:
            scale=min(2.0,1600/max(1,image.width))
            image=image.resize((int(image.width*scale),int(image.height*scale)))
        image=ImageEnhance.Contrast(image).enhance(1.35)
        return pytesseract.image_to_string(image,lang=lang,config='--psm 3',timeout=18)
    except (pytesseract.TesseractNotFoundError,pytesseract.TesseractError,RuntimeError) as exc:
        warnings.append('OCR indisponible ou interrompu : '+str(exc)[:120])
        return ''

def _render_ocr_page(page):
    """Enough resolution for lab text, with a bounded pixel allocation."""
    import fitz
    from PIL import Image
    scale=min(3.0,(12_000_000/max(1,page.rect.width*page.rect.height))**0.5)
    pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
    return Image.open(io.BytesIO(pix.tobytes('png')))


def parse_file(data:bytes,content_type:str,filename:str) -> ParsedDocument:
    if not data: raise ValueError('Fichier vide')
    if len(data)>MAX_UPLOAD_BYTES: raise ValueError('Fichier supérieur à 12 Mo')
    is_pdf=data[:5]==b'%PDF-'
    is_png=data[:8]==b'\x89PNG\r\n\x1a\n'
    is_jpeg=data[:3]==b'\xff\xd8\xff'
    if not (is_pdf or is_png or is_jpeg): raise ValueError('Format non reconnu : PDF, PNG ou JPEG uniquement')
    import fitz
    from PIL import Image
    pages=[]; transcripts=[]; method='text-native'; warnings=[]
    if is_pdf:
        try:
            doc=fitz.open(stream=data,filetype='pdf')
            try:
                if len(doc)>MAX_PAGES: raise ValueError('Maximum 30 pages')
                for page in doc:
                    page_text=page.get_text('text',sort=True)
                    table_text=_rebuild_table_lines(page)
                    has_native=len(page_text.strip())>=18
                    if len(page_text.strip())<18:
                        image=_render_ocr_page(page)
                        page_text=_ocr_image(image,warnings)
                        method='text-native+OCR'
                    transcripts.append(page_text)
                    if table_text and table_text!=page_text and has_native:
                        # Both views describe the same page; candidate de-duplication handles repeated values.
                        page_text += '\n'+table_text
                    pages.append(page_text)
            finally: doc.close()
        except ValueError: raise
        except Exception as e: raise ValueError('PDF illisible ou protégé') from e
    else:
        try:
            image=Image.open(io.BytesIO(data))
            if image.width*image.height>24_000_000: raise ValueError('Image trop grande')
            image.verify()
            image=Image.open(io.BytesIO(data));image.load()
            pages=[_ocr_image(image,warnings)]
            transcripts=list(pages)
            method='OCR'
        except ValueError: raise
        except Exception as e: raise ValueError('Image impossible à lire') from e
    candidates,date,parse_warnings=extract_candidates(pages)
    findings=extract_findings(pages,date)
    # Text layers of lab PDFs are often positional or broken into unrelated
    # columns. If they yield zero fields, try a bounded OCR second pass even
    # though get_text() returned non-empty text. Never invent inferred values.
    if is_pdf and not candidates and not findings and not extract_medications(pages,date):
        try:
            with fitz.open(stream=data,filetype='pdf') as retry_doc:
                for page_index in range(min(len(retry_doc),4)):
                    page=retry_doc[page_index]
                    image=_render_ocr_page(page)
                    recognized=_ocr_image(image,warnings)
                    if recognized.strip():
                        pages[page_index]+='\n'+recognized
                        # Keep both explicit readings if the second differs.
                        if recognized.strip()!=transcripts[page_index].strip():
                            transcripts[page_index]+='\n\n[Seconde lecture OCR, à vérifier]\n'+recognized
                        method='text-native+OCR-seconde-lecture'
            candidates,date,parse_warnings=extract_candidates(pages)
            findings=extract_findings(pages,date)
            if not candidates and not findings: warnings.append('Seconde lecture OCR terminée : aucun résultat suffisamment fiable pour une extraction automatique. Vérifiez le texte ou saisissez la mesure.')
        except Exception as exc:
            warnings.append('Seconde lecture OCR indisponible : '+str(exc)[:110])
    warnings.extend(parse_warnings)
    if not any(t.strip() for t in pages):warnings.append('Le document ne contient aucun texte lisible : image trop faible, OCR indisponible ou PDF protégé.')
    medications=extract_medications(pages,date)
    if findings:
        warnings=[w for w in warnings if 'Aucune valeur structurée reconnue' not in w]
    warnings.extend(f'Résultat non structuré page {page} : {label}. Vérifiez la transcription et le document.'
                    for page,label in unparsed_result_labels(pages,findings))
    if medications:
        warnings=[w for w in warnings if 'Aucune valeur structurée reconnue' not in w]
        warnings.append('Prescription historique : ne jamais considérer ces médicaments comme actuellement pris sans vérification professionnelle.')
    return ParsedDocument(sha256=hashlib.sha256(data).hexdigest(),page_count=len(pages),method=method,candidates=candidates,medications=medications,document_date=date,issuer=None,warnings=list(dict.fromkeys(warnings)),findings=findings,text_previews=transcripts,page_texts=transcripts)


def sample_date_options(pages):
    """Return literal sample-date alternatives, never choose between conflicting dates."""
    options=set()
    for page in pages:
        for line in page.splitlines():
            m=re.search(r'pr[eé]lev[eé](?:pr[eé]lev[eé])?|pr[eé]l[eè]vement',line,re.I)
            if not m:continue
            part=re.split(r'(?:[eé]dit[eé]|valid[eé]|prescrit)',line[m.end():],flags=re.I)[0]
            for d in re.finditer(r'(\d{2})[/.\-](\d{2})[/.\-](\d{4})',part):
                try:options.add(datetime(int(d[3]),int(d[2]),int(d[1])).date().isoformat())
                except ValueError:pass
    return sorted(options)


def report_conclusions(pages):
    """Display only the literal conclusion line; complete context stays in page text."""
    out=[]
    for page,text in enumerate(pages,1):
        for line in text.splitlines():
            m=re.match(r'^\s*Conclusion\s*:\s*(.+)',line,re.I)
            if m:out.append({'page':page,'text':m[1].strip()})
    return out
