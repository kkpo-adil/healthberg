"""Literal report results kept outside numeric curves. No clinical inference."""
import re
from .models import ReportFinding

ANALYTES = (
    ('hbs_ag', 'Antigène HBs', r'antig[eèé]ne\s+HBs'),
    ('hbs_ab', 'Anticorps anti-HBs', r'anticorps\s+anti[- ]?HBs'),
    ('hbc_ab', 'Anticorps anti-HBc', r'anticorps\s+anti[- ]?HBc'),
    ('hiv_ab', 'Anticorps anti-HIV (1+2)', r'anticorps\s+anti[- ]?(?:HIV|VIH)\s*(?:\(1\+2\)|1\s*(?:et|\+)\s*2)?'),
    ('tpha', 'TPHA', r'T\.?P\.?H\.?A\.?\s*(?:\(sp[eé]cifique\))?'),
    ('chlamydia', 'Chlamydiae trachomatis', r'chlamydiae?\s+trachomatis'),
    ('gonorrhoeae', 'Neisseria gonorrhoeae', r'neisseria\s+gonorrhoeae'),
)
QUAL = r'(?:n[eé]gatif|positif|douteux|ind[eé]termin[eé]|non\s+d[eé]tect[eé]|d[eé]tect[eé])'
NUM = r'[<>≤≥]?\s*\d+(?:[.,]\d+)?'


def extract_findings(pages, document_date):
    out = []
    seen = set()
    for page_number, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        current = None
        for index, line in enumerate(lines):
            # Anchoring excludes reference ranges and paragraphs mentioning tests.
            matched = False
            for code, label, pattern in ANALYTES:
                m = re.match(r'^' + pattern + r'(?:\s*[:_\-]?\s+|\s*$)', line, re.I)
                if not m:
                    continue
                tail = line[m.end():]
                if not tail and index + 1 < len(lines):
                    tail = lines[index + 1]
                result = re.match(r'^(' + QUAL + r')\b', tail, re.I)
                if result and re.match(r'\s*[<>≤≥]', tail[result.end():]):
                    continue  # A reference threshold is not a patient result.
                unit = ''
                kind = 'qualitative'
                if not result:
                    result = re.match(r'^(' + NUM + r')\s*(UI\s*/\s*L|IU\s*/\s*L)\b', tail, re.I)
                    if result:
                        unit = result[2].replace(' ', '')
                        kind = 'bounded' if re.match(r'[<>≤≥]', result[1].strip()) else 'reported_number'
                if not result:
                    continue
                value = result[1].strip()
                current = (code, label)
                matched = True
                key = (page_number, code)
                if key not in seen:
                    seen.add(key)
                    out.append(ReportFinding(code=code, label=label, value=value,
                        unit=unit, kind=kind, page=page_number, measured_at=document_date))
                break
            if matched:
                continue
            if current:
                m = re.match(r'^Index\s*[:\-]?\s+(' + NUM + r')(?:\s|$)', line, re.I)
                if m and not re.match(r'[<>≤≥]', m[1].strip()):
                    code, label = current
                    key = (page_number, code + '_index')
                    if key not in seen:
                        seen.add(key)
                        out.append(ReportFinding(code=code + '_index', label=label + ' · index',
                            value=m[1].strip(), unit='index', kind='reported_number',
                            page=page_number, measured_at=document_date))
                    current = None
                elif not re.match(r'^(?:ECLIA|CMIA|PCR)\b', line, re.I):
                    current = None
    return out


def unparsed_result_labels(pages, findings):
    """Flag known exam rows whose result was unreadable; do not guess a correction."""
    recognized={(f.page,f.code) for f in findings}
    missing=set()
    for page,text in enumerate(pages,1):
        for line in text.splitlines():
            for code,label,pattern in ANALYTES:
                if (page,code) in recognized:continue
                if re.match(r'^\s*'+pattern+r'(?:\s*[:_\-]?\s+|\s*$)',line,re.I):
                    missing.add((page,label))
    return sorted(missing)
