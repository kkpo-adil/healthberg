"""Ajour v0.8: typed cross-specialty journeys and synthetic-only medical-media demo.

No billing/claims/Assurance-maladie integration. Demo roles are not credentialed.
QR token is a one-order capability, never an all-patient access token.
"""
from __future__ import annotations
import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4
import qrcode
from . import db, portal
from .care_catalog import CARE_TYPES, INDEX

MAX_MEDIA_BYTES=15*1024*1024  # Demonstrator limit, not a DICOM study server
MAX_NOTE=1500


def now():return datetime.now(timezone.utc)
def stamp():return now().isoformat()
def expiry(minutes=15):return (now()+timedelta(minutes=minutes)).isoformat()

def media_root():return db.DB_PATH.parent/'ajour_media_demo'

def init_careflows():
    with db.connect() as c:
        c.executescript('''
          CREATE TABLE IF NOT EXISTS aj_care_orders(
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            author_id TEXT NOT NULL REFERENCES portal_users(id), kind TEXT NOT NULL,
            title TEXT NOT NULL, description TEXT NOT NULL, payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'issued', specialty_code TEXT NOT NULL DEFAULT '');
          CREATE INDEX IF NOT EXISTS aj_care_orders_patient ON aj_care_orders(patient_id,created_at);
          CREATE TABLE IF NOT EXISTS aj_care_grants(
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES aj_care_orders(id),
            token_hash TEXT UNIQUE NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
            expires_at TEXT NOT NULL, redeemed_by TEXT REFERENCES portal_users(id),
            created_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS aj_care_grants_order ON aj_care_grants(order_id);
          CREATE TABLE IF NOT EXISTS aj_care_actions(
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES aj_care_orders(id),
            actor_id TEXT NOT NULL REFERENCES portal_users(id), action TEXT NOT NULL,
            note TEXT NOT NULL, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS aj_care_media(
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            order_id TEXT REFERENCES aj_care_orders(id), uploader_id TEXT NOT NULL REFERENCES portal_users(id),
            category TEXT NOT NULL, filename_original TEXT NOT NULL, media_type TEXT NOT NULL,
            storage_key TEXT UNIQUE NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            description TEXT NOT NULL, anatomical_site TEXT NOT NULL, exam_date TEXT NOT NULL,
            source_status TEXT NOT NULL, prior_media_id TEXT REFERENCES aj_care_media(id),
            created_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS aj_care_media_patient ON aj_care_media(patient_id,created_at);
          CREATE TABLE IF NOT EXISTS aj_care_notifications(
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            order_id TEXT REFERENCES aj_care_orders(id), text TEXT NOT NULL,
            created_at TEXT NOT NULL, read_at TEXT);
        ''')
        cols={r[1] for r in c.execute('PRAGMA table_info(aj_care_orders)')}
        if 'specialty_code' not in cols:c.execute("ALTER TABLE aj_care_orders ADD COLUMN specialty_code TEXT NOT NULL DEFAULT ''")

def _row(c,oid):
    row=c.execute('SELECT * FROM aj_care_orders WHERE id=?',(oid,)).fetchone()
    return dict(row) if row else None

def _summary(row):
    result={k:row[k] for k in ('id','patient_id','author_id','kind','title','description','created_at','updated_at','status','specialty_code')}
    result['items']=json.loads(row['payload_json'])
    return result

def _owns(user,pid):return user['role']=='patient' and user['patient_id']==pid

def _doctor(user,pid):return user['role']=='doctor' and portal.can(user,pid,'all')

def _actor_granted(c,user,oid):
    return c.execute('''SELECT g.id FROM aj_care_grants g WHERE g.order_id=? AND
        g.redeemed_by=? AND g.status='redeemed' AND g.expires_at>?''',(oid,user['id'],stamp())).fetchone() is not None

def _allowed_to_read(user,row):
    if _owns(user,row['patient_id']) or _doctor(user,row['patient_id']):return True
    with db.connect() as c:return _actor_granted(c,user,row['id'])

def issue_order(user,pid,kind,title,items,description='',specialty_code=''):
    if kind not in CARE_TYPES:raise ValueError('Parcours inconnu')
    if specialty_code and specialty_code not in INDEX:raise ValueError('Spécialité inconnue')
    if kind=='orientation' and not specialty_code:raise ValueError('Sélectionnez la spécialité destinataire')
    if not _doctor(user,pid):raise PermissionError('Médecin affecté nécessaire dans le scénario actuel')
    if not 3<=len(title.strip())<=150:raise ValueError('Titre obligatoire')
    if len(description)>1000:raise ValueError('Description trop longue')
    if not isinstance(items,list) or not 1<=len(items)<=12:raise ValueError('Entre 1 et 12 lignes de prescription/examen')
    clean=[]
    for item in items:
        if not isinstance(item,dict):raise ValueError('Ligne invalide')
        text=str(item.get('description','')).strip()
        if not 3<=len(text)<=250:raise ValueError('Description de chaque élément requise')
        clean.append({'description':text})
    oid=str(uuid4());ts=stamp()
    with db.connect() as c:
        c.execute('INSERT INTO aj_care_orders(id,patient_id,author_id,kind,title,description,payload_json,created_at,updated_at,status,specialty_code) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                  (oid,pid,user['id'],kind,title.strip(),description, json.dumps(clean,ensure_ascii=False),ts,ts,'issued',specialty_code))
        portal.add_event(c,user,pid,'care_order','care',f'Nouvelle demande : {CARE_TYPES[kind]["label"]}')
        _notify(c,pid,oid,'Nouvelle demande de soins disponible')
    portal.log(user,pid,'care_issue_'+kind)
    return {'id':oid,'status':'issued'}

def _notify(c,pid,oid,text):
    c.execute('INSERT INTO aj_care_notifications VALUES(?,?,?,?,?,NULL)',(str(uuid4()),pid,oid,text,stamp()))

def list_orders(user,pid=None):
    if user['role']=='patient':pid=user['patient_id']
    if user['role']=='doctor':
        if not pid or not _doctor(user,pid):raise PermissionError('Patient non autorisé')
    elif user['role']!='patient':
        # Provider sees ONLY the specific orders it has redeemed. No patient dossier.
        with db.connect() as c:
            rows=c.execute('''SELECT DISTINCT o.* FROM aj_care_orders o JOIN aj_care_grants g ON g.order_id=o.id
                 WHERE g.redeemed_by=? AND g.status='redeemed' AND g.expires_at>? ORDER BY o.created_at DESC''',(user['id'],stamp())).fetchall()
        return [_summary(dict(r)) for r in rows]
    with db.connect() as c:
        rows=c.execute('SELECT * FROM aj_care_orders WHERE patient_id=? ORDER BY created_at DESC',(pid,)).fetchall()
    return [_summary(dict(r)) for r in rows]

def qr_issue(user,oid):
    if user['role']!='patient':raise PermissionError('Code généré par le patient uniquement')
    with db.connect() as c:
        o=_row(c,oid)
        if not o or not _owns(user,o['patient_id']):raise PermissionError('Demande inaccessible')
        if o['status']!='issued':raise ValueError('Demande non partageable dans cet état')
        if o['kind']=='orientation':raise ValueError('Une orientation simple n’est pas une ordonnance et ne génère pas de QR professionnel dans cette version')
        raw='AJCARE1.'+token_urlsafe(32)
        c.execute('UPDATE aj_care_grants SET status="revoked" WHERE order_id=? AND status="ready"',(oid,))
        c.execute('INSERT INTO aj_care_grants VALUES(?,?,?,?,?,?,?)',
                  (str(uuid4()),oid,sha256(raw.encode()).hexdigest(),'ready',expiry(),None,stamp()))
    qr=qrcode.QRCode(box_size=7,border=3,error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(raw);qr.make(fit=True)
    bio=BytesIO();qr.make_image(fill_color='black',back_color='white').save(bio,format='PNG')
    return {'qr_payload':raw,'qr_image':'data:image/png;base64,'+base64.b64encode(bio.getvalue()).decode(),
            'expires_in_minutes':15,'destination_role':CARE_TYPES[o['kind']]['provider_role'],
            'kind':o['kind'],'order_id':oid}

def redeem_policy(kind,role,grant_status,order_status,is_unexpired):
    return kind in CARE_TYPES and CARE_TYPES[kind]['provider_role']==role and grant_status=='ready' and order_status=='issued' and is_unexpired

def redeem(user,code):
    if not isinstance(code,str) or not code.startswith('AJCARE1.') or len(code)>130:raise ValueError('Code QR invalide')
    with db.connect() as c:
        g=c.execute('SELECT * FROM aj_care_grants WHERE token_hash=?',(sha256(code.encode()).hexdigest(),)).fetchone()
        if not g:raise ValueError('Code inexistant')
        o=_row(c,g['order_id'])
        if not o or user['role']!=CARE_TYPES[o['kind']]['provider_role']:raise PermissionError('Métier non autorisé')
        if not redeem_policy(o['kind'],user['role'],g['status'],o['status'],g['expires_at']>stamp()):raise ValueError('QR expiré ou révoqué')
        count=c.execute('UPDATE aj_care_grants SET status="redeemed",redeemed_by=? WHERE id=? AND status="ready"',(user['id'],g['id'])).rowcount
        if count!=1:raise ValueError('QR déjà utilisé')
        c.execute('INSERT INTO portal_audit VALUES(?,?,?,?,?)',(str(uuid4()),user['id'],o['patient_id'],'care_qr_'+o['kind'],stamp()))
    return {'grant_id':g['id'],'expires_at':g['expires_at'],'order':_summary(o),
            'scope':'Seulement cette demande ; aucun accès aux analyses, aux notes ou à la liste de patients'}

def _ticket(c,user,gid):
    g=c.execute('SELECT * FROM aj_care_grants WHERE id=?',(gid,)).fetchone()
    if not g or g['redeemed_by']!=user['id'] or g['status']!='redeemed' or g['expires_at']<=stamp():
        raise PermissionError('Accès QR inexistant ou expiré')
    o=_row(c,g['order_id'])
    if not o or user['role']!=CARE_TYPES[o['kind']]['provider_role']:
        raise PermissionError('Accès impossible pour ce métier')
    return dict(g),o

def ticket(user,gid):
    with db.connect() as c:
        g,o=_ticket(c,user,gid)
        return {'grant_id':g['id'],'expires_at':g['expires_at'],'order':_summary(o)}

def action(user,gid,operation,note=''):
    if operation not in ('accepted','ready','completed'):raise ValueError('Action inconnue')
    if len(note)>MAX_NOTE:raise ValueError('Note trop longue')
    with db.connect() as c:
        g,o=_ticket(c,user,gid)
        if o['status'] not in ('issued','in_progress'):raise ValueError('Demande close')
        if operation=='ready' and o['kind'] not in ('optical','orthotics','podiatry'):
            raise ValueError('État « prêt » réservé à l’appareillage')
        target={'accepted':'in_progress','ready':'ready','completed':'completed'}[operation]
        c.execute('UPDATE aj_care_orders SET status=?,updated_at=? WHERE id=?',(target,stamp(),o['id']))
        c.execute('INSERT INTO aj_care_actions VALUES(?,?,?,?,?,?)',(str(uuid4()),o['id'],user['id'],operation,note.strip(),stamp()))
        text={'accepted':'Un professionnel a pris en charge votre demande', 'ready':'Votre équipement est prêt', 'completed':'Un soin ou examen a été terminé'}[operation]
        _notify(c,o['patient_id'],o['id'],text)
    portal.log(user,o['patient_id'],'care_'+operation)
    return {'ok':True,'status':target}

def cancel(user,oid):
    with db.connect() as c:
        o=_row(c,oid)
        if not o or not (_owns(user,o['patient_id']) or (_doctor(user,o['patient_id']) and user['id']==o['author_id'])):
            raise PermissionError('Annulation non autorisée')
        if o['status'] not in ('issued','in_progress'):raise ValueError('Demande déjà exécutée')
        c.execute('UPDATE aj_care_orders SET status="cancelled",updated_at=? WHERE id=?',(stamp(),oid))
        c.execute('UPDATE aj_care_grants SET status="revoked" WHERE order_id=?',(oid,))
        _notify(c,o['patient_id'],oid,'La demande a été annulée')
    return {'ok':True}

def _media_type(payload):
    if payload.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png','.png'
    if payload.startswith(b'\xff\xd8\xff') and payload.endswith(b'\xff\xd9'):return 'image/jpeg','.jpg'
    if payload.startswith(b'%PDF-'):return 'application/pdf','.pdf'
    if len(payload)>132 and payload[128:132]==b'DICM':return 'application/dicom','.dcm'
    # Binary STL: signed uint32 triangle count at offset 80; exact length.
    if len(payload)>=84 and 84+int.from_bytes(payload[80:84],'little')*50==len(payload):return 'model/stl','.stl'
    raise ValueError('Format non reconnu : PNG, JPEG, PDF, DICOM Part10, STL binaire uniquement')

def upload_media(user,pid,payload,filename,category,description,anatomical_site,exam_date,order_id=None,gid=None,prior_id=None):
    if not db.patient_detail(pid):raise ValueError('Patient inconnu')
    if not payload or len(payload)>MAX_MEDIA_BYTES:raise ValueError('Fichier vide ou supérieur à 15 Mo')
    if not 3<=len(description.strip())<=240:raise ValueError('Description requise')
    if len(anatomical_site)>120 or len(filename)>160:raise ValueError('Métadonnées trop longues')
    if category not in ('radiology','dental','podiatry','optical','orthotics','other'):
        raise ValueError('Catégorie non reconnue')
    try:
        event=datetime.fromisoformat(exam_date)
        if event.date()>now().date():raise ValueError()
    except (ValueError,TypeError):raise ValueError('Date d’examen valide requise (AAAA-MM-JJ)')
    mime,extension=_media_type(payload)
    if mime=='model/stl' and category not in ('podiatry','orthotics'):
        raise ValueError('STL réservé aux scans d’appareillage ou des pieds')
    with db.connect() as c:
        if _owns(user,pid):
            if order_id:
                o=_row(c,order_id)
                if not o or o['patient_id']!=pid:raise PermissionError('Demande étrangère au patient')
            source='patient_import_unverified'
        else:
            if not gid or not order_id:raise PermissionError('QR de demande nécessaire pour publier un examen')
            g,o=_ticket(c,user,gid)
            if o['id']!=order_id or o['patient_id']!=pid:raise PermissionError('Liaison patient/demande invalide')
            if o['status'] in ('cancelled',):raise ValueError('Demande annulée')
            if category not in ({'imaging':('radiology',),'dental':('dental',),'podiatry':('podiatry',),'optical':('optical',),'orthotics':('orthotics',)}[o['kind']]):
                raise PermissionError('Cette catégorie n’est pas autorisée pour le métier')
            source='provider_demo_not_credentialed'
        if prior_id:
            prior=c.execute('SELECT patient_id,category FROM aj_care_media WHERE id=?',(prior_id,)).fetchone()
            if not prior or prior['patient_id']!=pid or prior['category']!=category:raise PermissionError('Comparaison avec document d’un autre patient')
        mid=str(uuid4()); storage=uuid4().hex+extension
        root=media_root();root.mkdir(mode=0o700,parents=True,exist_ok=True)
        target=root/storage
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
        fd=os.open(target,flags,0o600)
        try:
            with os.fdopen(fd,'wb') as f:f.write(payload)
            c.execute('INSERT INTO aj_care_media VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (mid,pid,order_id,user['id'],category,Path(filename).name[:160],mime,storage,
                       sha256(payload).hexdigest(),len(payload),description.strip(),anatomical_site.strip(),event.date().isoformat(),source,prior_id,stamp()))
            _notify(c,pid,order_id,'Nouvelle image ou pièce médicale ajoutée à votre dossier')
        except Exception:
            target.unlink(missing_ok=True)
            raise
    portal.log(user,pid,'care_media_upload')
    return {'id':mid,'sha256':sha256(payload).hexdigest(),'size_bytes':len(payload),'media_type':mime,'source_status':source}

def list_media(user,pid):
    if not db.patient_detail(pid):raise ValueError('Patient inconnu')
    if not (_owns(user,pid) or _doctor(user,pid)):
        # Provider may only view media belonging to orders it has actively redeemed.
        with db.connect() as c:
            rows=c.execute('''SELECT m.* FROM aj_care_media m JOIN aj_care_grants g ON g.order_id=m.order_id
              WHERE m.patient_id=? AND g.redeemed_by=? AND g.status='redeemed' AND g.expires_at>?
              ORDER BY m.created_at DESC''',(pid,user['id'],stamp())).fetchall()
    else:
        with db.connect() as c:rows=c.execute('SELECT * FROM aj_care_media WHERE patient_id=? ORDER BY created_at DESC',(pid,)).fetchall()
    # The actual server storage key is never exposed; media served through authenticated ID endpoint.
    return [{k:r[k] for k in ('id','patient_id','order_id','category','filename_original','media_type','sha256','size_bytes','description','anatomical_site','exam_date','source_status','prior_media_id','created_at')} for r in rows]

def media_for_download(user,mid):
    with db.connect() as c:
        row=c.execute('SELECT * FROM aj_care_media WHERE id=?',(mid,)).fetchone()
    if not row:raise ValueError('Image introuvable')
    if mid not in {r['id'] for r in list_media(user,row['patient_id'])}:raise PermissionError('Accès image refusé')
    path=media_root()/row['storage_key']
    if not path.is_file():raise ValueError('Fichier non disponible')
    portal.log(user,row['patient_id'],'care_media_download')
    return path,dict(row)

def notifications(user):
    if user['role']!='patient':return []
    with db.connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM aj_care_notifications WHERE patient_id=? ORDER BY created_at DESC LIMIT 60',(user['patient_id'],)).fetchall()]

def purge():
    """Best-effort demo cleanup; not a certified retention system."""
    cutoff=(now()-timedelta(days=db.RETENTION_DAYS)).isoformat()
    with db.connect() as c:
        rows=c.execute('SELECT id,storage_key FROM aj_care_media WHERE created_at<?',(cutoff,)).fetchall()
        for r in rows:
            (media_root()/r['storage_key']).unlink(missing_ok=True)
            c.execute('DELETE FROM aj_care_media WHERE id=?',(r['id'],))
        c.execute('DELETE FROM aj_care_notifications WHERE created_at<?',(cutoff,))
