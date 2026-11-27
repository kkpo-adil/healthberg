"""Import local d'ordonnances PDF entièrement fictives, sans émission de prescription.

Le PDF d'origine est conservé pour la consultation et l'export. Aucune identité réelle
ni document clinique réel ne sont acceptés dans cette démonstration.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from threading import Lock
from uuid import uuid4
import os
import json
import re
import unicodedata
import fitz

from . import db, portal, journeys

MAX_PDF_SIZE=8*1024*1024
PREVIEWS={}
_LOCK=Lock()

def stamp():return datetime.now(timezone.utc)

def normalize_name(s):
    s=''.join(c for c in unicodedata.normalize('NFKD',s.lower().strip()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z]+',s))

def init():
    with db.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS aj_imported_prescription_pdfs (
            order_id TEXT PRIMARY KEY REFERENCES aj_orders(id), patient_id TEXT NOT NULL REFERENCES patients(id),
            filename TEXT NOT NULL, sha256 TEXT NOT NULL, storage_file TEXT NOT NULL,
            imported_by TEXT NOT NULL REFERENCES portal_users(id), issuer TEXT NOT NULL,
            date_on_document TEXT, imported_at TEXT NOT NULL)''')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_pdf_patient_hash ON aj_imported_prescription_pdfs(patient_id,sha256)')

def extract_pdf(data:bytes,patient_name:str):
    if not data.startswith(b'%PDF-') or not 0 < len(data) <= MAX_PDF_SIZE:
        raise ValueError('PDF obligatoire, 8 Mo maximum')
    try:
        with fitz.open(stream=data,filetype='pdf') as pdf:
            if not 1 <= len(pdf) <= 10:raise ValueError('Document : maximum 10 pages')
            page_count=len(pdf)
            text='\n'.join(page.get_text('text') for page in pdf)
    except ValueError:raise
    except Exception as e:raise ValueError('Document PDF illisible') from e
    if 'SPECIMEN' not in text.upper() or 'NON VALABLE' not in text.upper():
        raise ValueError('Seuls les documents clairement identifiés comme specimens peuvent être importés dans cet essai')
    patient_matches=re.findall(r'(?im)^\s*Patient(?:e)?\s*:\s*([^\r\n]+)',text)
    if len(patient_matches)!=1:
        raise ValueError('Identité du destinataire absente ou ambiguë : import refusé')
    extracted_name=' '.join(patient_matches[0].split())
    if normalize_name(extracted_name)!=normalize_name(patient_name):
        raise ValueError(f'Identité différente : le document est au nom de {extracted_name}, dossier sélectionné {patient_name}')
    items=[]
    for match in re.finditer(r'(?im)^\s*Produit\s+(\d+)\s*:\s*([^\r\n]+)',text):
        i=match.group(1)
        def field(label):
            pattern=rf'(?im)^\s*{label}\s+{re.escape(i)}\s*:\s*([^\r\n]+)'
            found=re.search(pattern,text)
            return found.group(1).strip() if found else ''
        item=dict(name=match.group(2).strip(), strength=field('Dosage'),schedule=field('Posologie'),quantity=field('Quantit[ée]'),duration=field('Dur[ée]e'))
        items.append(item)
    if not items:raise ValueError('Aucune ligne exploitable détectée : ce format PDF demande une revue manuelle, non disponible dans ce premier parcours')
    validated=journeys._items('prescription',items)
    date_match=re.search(r'(?im)^\s*Date\s*:\s*([^\r\n]+)',text)
    issuer_match=re.search(r'(?im)^\s*Professionnel\s*:\s*([^\r\n]+)',text)
    return dict(patient_name=extracted_name,items=validated,document_date=date_match.group(1).strip() if date_match else None,
        issuer=issuer_match.group(1).strip() if issuer_match else 'Non identifié',
        sha256=sha256(data).hexdigest(),pages=page_count)

def preview(user,pid,data,filename):
    if user['role']!='doctor' or not portal.can(user,pid,'all'):
        raise PermissionError('Réservé au médecin autorisé pour cette patiente')
    patient=db.patient_detail(pid)
    if not patient:raise ValueError('Patient inconnu')
    info=extract_pdf(data,patient['name'])
    token=token_urlsafe(32)
    with _LOCK:
        now=stamp()
        for key,value in list(PREVIEWS.items()):
            if value['expires']<now:PREVIEWS.pop(key,None)
        PREVIEWS[token]={'expires':now+timedelta(minutes=10),'uid':user['id'],'pid':pid,'pdf':data,'info':info}
    return {'preview_token':token,'patient':patient['name'],'issuer':info['issuer'],'date':info['document_date'],
            'items':info['items'],'sha256':info['sha256'],'expires_in_minutes':10,
            'warning':'Document fictif importé. À contrôler avant publication; ne crée aucune prescription officielle.'}

def confirm(user,token,pid,items,ack):
    if not ack:raise ValueError('Confirmez l’identité et chaque ligne de la prescription')
    with _LOCK:
        session=PREVIEWS.get(token)
        if not session or session['uid']!=user['id'] or session['pid']!=pid or session['expires']<=stamp():
            raise PermissionError('Prévisualisation expirée ou inaccessible')
        if user['role']!='doctor' or not portal.can(user,pid,'all'):
            raise PermissionError('Accès dossier refusé')
        normalized=journeys._items('prescription',items)
        if normalized!=session['info']['items']:
            raise ValueError('Les lignes ont été modifiées : ce premier test requiert une concordance exacte avec le PDF')
        data=session['pdf'];info=session['info']
        with db.connect() as check_db:
            duplicate=check_db.execute('SELECT 1 FROM aj_imported_prescription_pdfs WHERE patient_id=? AND sha256=?',(pid,info['sha256'])).fetchone()
        if duplicate:raise ValueError('Cette ordonnance est déjà présente dans le dossier de ce patient')
        folder=db.DB_PATH.parent/'ajour_ordon_pdf_test'
        folder.mkdir(parents=True,exist_ok=True)
        oid=str(uuid4());ts=stamp().isoformat()
        filename=f'{oid}.pdf'; dest=folder/filename
        # Exclusion de liens et fichier unique, réservé à l'utilisateur courant.
        fd=os.open(str(dest),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(fd,'wb') as out:out.write(data)
            with db.connect() as c:
                c.execute('INSERT INTO aj_orders VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (oid,pid,user['id'],'prescription',ts,'issued','Ordonnance externe importée - démonstration',
                     json.dumps(normalized,ensure_ascii=False),
                     'Source PDF externe fictive ; n’est pas une prescription créée par Ajour',ts))
                c.execute('INSERT INTO aj_imported_prescription_pdfs VALUES(?,?,?,?,?,?,?,?,?)',
                    (oid,pid,'Ordonnance_importee.pdf',info['sha256'],filename,user['id'],info['issuer'],info['document_date'],ts))
                portal.add_event(c,user,pid,'prescription','meds','Ordonnance externe importée et disponible dans le compte patient')
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
        PREVIEWS.pop(token,None)
    portal.log(user,pid,'pdf_prescription_import_test')
    return {'id':oid,'patient_id':pid,'published':True,'original_pdf':True}

def _attachment(oid):
    with db.connect() as c:
        row=c.execute('SELECT * FROM aj_imported_prescription_pdfs WHERE order_id=?',(oid,)).fetchone()
    return dict(row) if row else None

def attachment_for_user(user,oid,grant_id=None):
    r=_attachment(oid)
    if not r:raise ValueError('Aucun PDF original associé')
    pid=r['patient_id']
    if grant_id:
        if user['role']!='pharmacist':raise PermissionError('Seul le pharmacien muni du QR peut ouvrir le document')
        t=journeys.ticket(user,grant_id)
        if t['order']['id']!=oid:raise PermissionError('Ordonnance différente du QR présenté')
    elif user['role']=='patient' and user['patient_id']==pid:pass
    elif user['role']=='doctor' and portal.can(user,pid,'all'):pass
    else:raise PermissionError('Aucun accès à cette ordonnance')
    path=db.DB_PATH.parent/'ajour_ordon_pdf_test'/r['storage_file']
    if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=r['sha256']:
        raise ValueError('Le fichier original est introuvable ou modifié')
    portal.log(user,pid,'view_pdf_prescription')
    return path

def has_attachment(oid):
    return _attachment(oid) is not None
