"""Conservative PDF/image extraction for local fictional demos only.

The extraction output is a *candidate*, not a clinical fact. Uploaded bytes are never saved
by this module. Text, filename and original PDF page content are not persisted.
"""
from __future__ import annotations
import hashlib
import io
import re
import unicodedata
from datetime import datetime
from dataclasses import dataclass
from typing import Callable

from .models import Candidate,MedicationCandidate
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
    document_date: str | None
    issuer: str | None
    warnings: list[str]


def clean(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')


def parse_date(text: str) -> str | None:
    # Extract the date printed in a report; never use upload time as sample time.
    patterns=[r'(?:prelevement|prélèvement|date de mesure|date d.examen|date du bilan|date)\s*[:\-]?\s*(\d{2})[/.\-](\d{2})[/.\-](\d{4})',r'\b(\d{2})[/.\-](\d{2})[/.\-](\d{4})\b']
    for pat in patterns:
        m=re.search(pat,text,flags=re.I)
        if m:
            try: return datetime(int(m[3]),int(m[2]),int(m[1])).date().isoformat()
            except ValueError: continue
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
]
BP_REGEX=re.compile(r'\b(?:tension(?:\s+art[ée]rielle)?|pression\s+art[ée]rielle|TA)\s*[:\-]?\s*(\d{2,3})\s*[/\-]\s*(\d{2,3})\s*(?:mmHg)?\b',re.I)


def extract_candidates(pages: list[str]) -> tuple[list[Candidate], str|None, list[str]]:
    candidates=[]; warnings=[]
    document_date=parse_date('\n'.join(pages))
    if not document_date: warnings.append('Date de prélèvement/mesure introuvable : sélectionner une date réelle avant confirmation.')
    for page_index,text in enumerate(pages,1):
        for line in text.splitlines():
            line=line.strip()
            if not line or len(line)>1000: continue
            bp=BP_REGEX.search(line)
            if bp:
                for code,raw in [('systolic',bp[1]),('diastolic',bp[2])]:
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

def parse_file(data:bytes,content_type:str,filename:str) -> ParsedDocument:
    if not data: raise ValueError('Fichier vide')
    if len(data)>MAX_UPLOAD_BYTES: raise ValueError('Fichier supérieur à 12 Mo')
    is_pdf=data[:5]==b'%PDF-'
    is_png=data[:8]==b'\x89PNG\r\n\x1a\n'
    is_jpeg=data[:3]==b'\xff\xd8\xff'
    if not (is_pdf or is_png or is_jpeg): raise ValueError('Format non reconnu : PDF, PNG ou JPEG uniquement')
    import fitz
    from PIL import Image
    import pytesseract
    pages=[]; method='text-native'
    if is_pdf:
        try:
            doc=fitz.open(stream=data,filetype='pdf')
            try:
                if len(doc)>MAX_PAGES: raise ValueError('Maximum 30 pages')
                for page in doc:
                    page_text=page.get_text('text')
                    if len(page_text.strip())<18:
                        pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
                        image=Image.open(io.BytesIO(pix.tobytes('png')))
                        page_text=pytesseract.image_to_string(image,lang='fra+eng')
                        method='text-native+OCR'
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
            pages=[pytesseract.image_to_string(image,lang='fra+eng')]
            method='OCR'
        except ValueError: raise
        except Exception as e: raise ValueError('Image impossible à lire') from e
    candidates,date,warnings=extract_candidates(pages)
    medications=extract_medications(pages,date)
    if medications:
        warnings=[w for w in warnings if 'Aucune valeur structurée reconnue' not in w]
        warnings.append('Prescription historique : ne jamais considérer ces médicaments comme actuellement pris sans vérification professionnelle.')
    return ParsedDocument(sha256=hashlib.sha256(data).hexdigest(),page_count=len(pages),method=method,candidates=candidates,medications=medications,document_date=date,issuer=None,warnings=warnings)
