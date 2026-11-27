"""Ajour v0.7 — end-to-end *synthetic-only* clinical journeys.

All provider QR grants are explicitly issued by the patient and scoped to one order.
Never use this module for real medical prescriptions, reimbursements or care.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4
import io
import base64
import qrcode
import json

from . import db, portal
from .terminology import METRIC_BY_CODE, normalize

KINDS = {'prescription', 'lab'}
FLAGS = {'normal', 'outside', 'critical', 'unknown'}
TYPES = {'prescription': 'pharmacist', 'lab': 'lab'}

def now(): return datetime.now(timezone.utc)
def stamp(): return now().isoformat()
def iso_after(minutes): return (now()+timedelta(minutes=minutes)).isoformat()

def init_journeys():
    with db.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS aj_orders (
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id), author_id TEXT NOT NULL REFERENCES portal_users(id),
            kind TEXT NOT NULL CHECK(kind IN ('prescription','lab')), issued_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'issued',
            label TEXT NOT NULL, items_json TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS aj_orders_patient ON aj_orders(patient_id,issued_at);
        CREATE TABLE IF NOT EXISTS aj_qr_grants (
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES aj_orders(id), token_hash TEXT UNIQUE NOT NULL,
            issued_by TEXT NOT NULL REFERENCES portal_users(id), expires_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
            redeemed_by TEXT REFERENCES portal_users(id), redeemed_at TEXT, processed_at TEXT);
        CREATE INDEX IF NOT EXISTS aj_qr_order ON aj_qr_grants(order_id);
        CREATE TABLE IF NOT EXISTS aj_order_actions (
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES aj_orders(id), actor_id TEXT NOT NULL REFERENCES portal_users(id),
            kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS aj_result_items (
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES aj_orders(id), patient_id TEXT NOT NULL REFERENCES patients(id),
            author_id TEXT NOT NULL REFERENCES portal_users(id), observation_id TEXT REFERENCES observations(id),
            code TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL, measured_at TEXT NOT NULL,
            lab_flag TEXT NOT NULL, reference_label TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS aj_result_patient ON aj_result_items(patient_id,created_at);
        CREATE TABLE IF NOT EXISTS aj_lab_slots (
          id TEXT PRIMARY KEY, lab_id TEXT NOT NULL REFERENCES portal_users(id), starts_at TEXT NOT NULL,
          duration_minutes INTEGER NOT NULL DEFAULT 20, location TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS aj_lab_bookings (
          id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES aj_orders(id), slot_id TEXT UNIQUE NOT NULL REFERENCES aj_lab_slots(id),
          patient_id TEXT NOT NULL REFERENCES patients(id), status TEXT NOT NULL DEFAULT 'booked', booked_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS aj_lab_booking_patient ON aj_lab_bookings(patient_id,status);
        ''')
        c.execute("DROP TABLE IF EXISTS aj_claim_outbox")

def _order(c, oid):
    row=c.execute('SELECT * FROM aj_orders WHERE id=?',(oid,)).fetchone()
    return dict(row) if row else None

def _safe_order(o, *, patient=False, provider=False):
    out={k:o[k] for k in ('id','patient_id','kind','issued_at','status','label','note','updated_at')}
    out['items']=json.loads(o['items_json'])
    return out

def _items(kind,items):
    if not isinstance(items,list) or not (1 <= len(items) <= 12):raise ValueError('Entre 1 et 12 lignes sont nécessaires')
    normalized=[]
    for x in items:
        if not isinstance(x,dict):raise ValueError('Ligne invalide')
        if kind=='prescription':
            name=str(x.get('name','')).strip(); strength=str(x.get('strength','')).strip()
            schedule=str(x.get('schedule','')).strip(); qty=str(x.get('quantity','')).strip()
            duration=str(x.get('duration','')).strip()
            if not (2<=len(name)<=120 and 1<=len(strength)<=80 and 2<=len(schedule)<=180 and 1<=len(qty)<=80):
                raise ValueError('Médicament, dosage, posologie et quantité nécessaires')
            normalized.append(dict(name=name,strength=strength,schedule=schedule,quantity=qty,duration=duration[:80]))
        else:
            code=str(x.get('code','')).strip()
            if code not in METRIC_BY_CODE:raise ValueError('Analyse non reconnue dans le catalogue')
            if code in [a['code'] for a in normalized]:raise ValueError('Analyse en double')
            normalized.append(dict(code=code,label=METRIC_BY_CODE[code].label,unit=METRIC_BY_CODE[code].unit))
    return normalized

def create_order(user,pid,kind,label,items,note=''):
    if kind not in KINDS:raise ValueError('Type non pris en charge')
    if user['role']!='doctor' or not portal.can(user,pid,'all'):raise PermissionError('Prescription réservée au médecin affecté')
    if not (3<=len(label.strip())<=150):raise ValueError('Libellé obligatoire')
    if len(note)>500:raise ValueError('Note trop longue')
    items=_items(kind,items)
    oid=str(uuid4());ts=stamp()
    with db.connect() as c:
        c.execute('INSERT INTO aj_orders VALUES(?,?,?,?,?,?,?,?,?,?)',(oid,pid,user['id'],kind,ts,'issued',label.strip(),json.dumps(items,ensure_ascii=False),note,ts))
        portal.add_event(c,user,pid,kind,'meds' if kind=='prescription' else 'labs',f'Nouvelle demande de {"traitement" if kind=="prescription" else "biologie"} disponible dans le dossier')
    portal.log(user,pid,'issue_'+kind);return {'id':oid}

def list_orders(user,pid):
    if not db.patient_detail(pid):raise ValueError('Patient inconnu')
    if user['role']=='patient' and user['patient_id']==pid:pass
    elif user['role']=='doctor' and portal.can(user,pid,'all'):pass
    else:raise PermissionError('Liste des demandes réservée au patient et au médecin')
    with db.connect() as c:
        rows=c.execute('SELECT * FROM aj_orders WHERE patient_id=? ORDER BY issued_at DESC',(pid,)).fetchall()
    return [_safe_order(dict(r)) for r in rows]

def qr_issue(user,oid):
    if user['role']!='patient':raise PermissionError('Seul le patient peut afficher son code de partage')
    with db.connect() as c:
        o=_order(c,oid)
        if not o or o['patient_id']!=user['patient_id']:raise PermissionError('Demande inaccessible')
        if o['status']!='issued':raise ValueError('Cette demande est déjà exécutée ou clôturée')
        raw=token_urlsafe(25)
        token='AJOUR1.'+o['kind'].upper()+'.'+raw
        c.execute('UPDATE aj_qr_grants SET status="revoked" WHERE order_id=? AND status="ready"',(oid,))
        c.execute('INSERT INTO aj_qr_grants(id,order_id,token_hash,issued_by,expires_at,status) VALUES (?,?,?,?,?,"ready")',
                  (str(uuid4()),oid,sha256(token.encode()).hexdigest(),user['id'],iso_after(15)))
    qr=qrcode.QRCode(box_size=7,border=3,error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(token);qr.make(fit=True)
    image=qr.make_image(fill_color='black',back_color='white');buff=io.BytesIO();image.save(buff,format='PNG')
    return {'qr_payload':token,'qr_image':'data:image/png;base64,'+base64.b64encode(buff.getvalue()).decode(),
            'expires_in_minutes':15,'kind':o['kind'],'order_id':oid,'no_patient_identity_in_qr':True}

def _grant(c,grant_id,provider_id):
    row=c.execute('SELECT * FROM aj_qr_grants WHERE id=?',(grant_id,)).fetchone()
    if not row or row['status']!='redeemed' or row['redeemed_by']!=provider_id or row['expires_at']<=stamp():
        raise PermissionError('Accès expiré ou non attribué à ce professionnel')
    return dict(row)

def redeem_policy(kind,role,order_status,grant_status,is_unexpired):
    """Policy kernel also exercised by the 480-case scenario matrix."""
    return kind in KINDS and TYPES[kind]==role and order_status=='issued' and grant_status=='ready' and is_unexpired


def redeem(user,payload):
    if not (isinstance(payload,str) and payload.startswith('AJOUR1.') and len(payload)<=130):raise ValueError('QR Ajour non reconnu')
    with db.connect() as c:
        row=c.execute('SELECT * FROM aj_qr_grants WHERE token_hash=?',(sha256(payload.encode()).hexdigest(),)).fetchone()
        if not row:raise ValueError('Code non reconnu')
        g=dict(row);o=_order(c,g['order_id'])
        if (not o or TYPES[o['kind']]!=user['role']):raise PermissionError('Ce code ne correspond pas à votre profession')
        if not redeem_policy(o['kind'],user['role'],o['status'],g['status'],g['expires_at']>stamp()):
            raise ValueError('Code déjà lu, expiré ou révoqué')
        c.execute('UPDATE aj_qr_grants SET status="redeemed",redeemed_by=?,redeemed_at=? WHERE id=? AND status="ready"',(user['id'],stamp(),g['id']))
        if c.execute('SELECT changes()').fetchone()[0]!=1:raise ValueError('Code déjà utilisé')
        # Provider-specific read receipt; this is never an access to the patient's complete dossier.
        c.execute('INSERT INTO portal_audit VALUES(?,?,?,?,?)',(str(uuid4()),user['id'],o['patient_id'],'qr_read_'+o['kind'],stamp()))
        return {'grant_id':g['id'],'order':_safe_order(o),'expires_at':g['expires_at'],'limitations':'Accès à cette demande uniquement ; aucune autre donnée du patient'}

def ticket(user,grant_id):
    with db.connect() as c:
        g=_grant(c,grant_id,user['id']);o=_order(c,g['order_id'])
        return {'grant_id':g['id'],'order':_safe_order(o),'expires_at':g['expires_at']}

def action(user,grant_id,kind,detail):
    with db.connect() as c:
        g=_grant(c,grant_id,user['id']);o=_order(c,g['order_id'])
        if not o or o['status']!='issued':raise ValueError('Demande déjà traitée')
        if o['kind']=='prescription':
            if user['role']!='pharmacist' or kind!='dispense':raise PermissionError('Action réservée au pharmacien')
            line_items=detail.get('items')
            if not isinstance(line_items,list) or len(line_items)!=len(json.loads(o['items_json'])):raise ValueError('La délivrance doit détailler chaque ligne')
            for i,x in enumerate(line_items):
                if x.get('line_index')!=i or x.get('status') not in ('dispensed','not_dispensed') or len(str(x.get('comment','')))>160:
                    raise ValueError('Ligne de délivrance invalide')
            next_status='dispensed'
        else:
            if user['role']!='lab' or kind!='results':raise PermissionError('Action réservée au laboratoire')
            results=detail.get('results')
            if not isinstance(results,list) or len(results)<1 or len(results)>12:raise ValueError('Résultats invalides')
            requested={item['code'] for item in json.loads(o['items_json'])}
            seen=set()
            for r in results:
                code=r.get('code');flag=r.get('flag')
                if code not in requested or code in seen or flag not in FLAGS:raise ValueError('Résultat non demandé, doublon ou interprétation invalide')
                seen.add(code)
                try:
                    val=float(r['value']);result=normalize(code,val,str(r['unit']))
                    if result is None:raise ValueError()
                    t=datetime.fromisoformat(str(r['measured_at']).replace('Z','+00:00'))
                    if t.tzinfo is None:raise ValueError()
                except (ValueError,KeyError,TypeError,OverflowError):raise ValueError('Valeur, unité ou date invalide')
                ref=str(r.get('reference_label','')).strip()
                if len(ref)>140 or (flag!='unknown' and len(ref)<3):raise ValueError('Le statut doit être accompagné de la référence déclarée par le laboratoire')
            if seen!=requested:raise ValueError('Résultats manquants pour des examens demandés')
            next_status='completed'
        action_id=str(uuid4());ts=stamp()
        c.execute('INSERT INTO aj_order_actions VALUES(?,?,?,?,?,?)',(action_id,o['id'],user['id'],kind,json.dumps(detail,ensure_ascii=False),ts))
        if kind=='results':
            receipt_id=str(uuid4())
            expires=(now()+timedelta(days=db.RETENTION_DAYS)).isoformat()
            c.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(receipt_id,o['patient_id'],'Résultats labo AJOUR (simulation)',user['name'],ts[:10],ts,sha256((o['id']+action_id).encode()).hexdigest(),1,'transmission structurée (simulation)',0,expires))
            for r in results:
                code=r['code'];v=float(r['value']);norm,unit=normalize(code,v,str(r['unit']))
                obs_id=str(uuid4())
                c.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(obs_id,o['patient_id'],code,METRIC_BY_CODE[code].label,norm,unit,r['measured_at'],str(r['value']),r['unit'],receipt_id,None,'Compte rendu labo simulé','lab_submitted_demo',str(r.get('reference_label','')),expires))
                c.execute('INSERT INTO aj_result_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(str(uuid4()),o['id'],o['patient_id'],user['id'],obs_id,code,norm,unit,r['measured_at'],r['flag'],str(r.get('reference_label','')),ts))
        c.execute('UPDATE aj_orders SET status=?, updated_at=? WHERE id=?',(next_status,ts,o['id']))
        c.execute('UPDATE aj_qr_grants SET status="used", processed_at=? WHERE id=?',(ts,grant_id))
        portal.add_event(c,user,o['patient_id'],kind,'meds' if kind=='dispense' else 'labs','Délivrance enregistrée' if kind=='dispense' else 'Nouveaux résultats biologiques disponibles')
    portal.log(user,o['patient_id'],'action_'+kind)
    return {'ok':True,'order_id':o['id'],'status':next_status,'simulation':True}

def outcomes(user,pid):
    if not db.patient_detail(pid):raise ValueError('Patient inconnu')
    if user['role']=='patient' and user['patient_id']==pid:pass
    elif user['role']=='doctor' and portal.can(user,pid,'all'):pass
    else:raise PermissionError('Résultats accessibles seulement au patient et médecin autorisé dans la démonstration')
    with db.connect() as c:
        rows=c.execute('''SELECT r.*,o.label AS order_label,o.issued_at FROM aj_result_items r JOIN aj_orders o ON o.id=r.order_id
            WHERE r.patient_id=? ORDER BY r.created_at DESC''',(pid,)).fetchall()
    return [dict(r) for r in rows]

def scenarios_catalog():
    # Extensible matrix; entries are cases to run with isolated test databases, not promises of exhaustive coverage.
    return [
      dict(id='rx-happy',title='Ordonnance → QR → pharmacie → délivrance enregistrée',kind='pharmacy'),
      dict(id='lab-happy',title='Demande de biologie → QR → labo → résultats → courbes',kind='lab'),
      dict(id='qr-wrong-role',title='QR pharmacie refusé à un laboratoire',kind='security'),
      dict(id='qr-replay',title='QR à usage unique : deuxième lecture refusée',kind='security'),
      dict(id='qr-expired',title='QR expiré : accès refusé',kind='security'),
      dict(id='qr-cross-patient',title='Aucun échange entre deux dossiers patients',kind='security'),
      dict(id='lab-unrequested',title='Résultat non demandé : rejet',kind='lab'),
      dict(id='lab-abnormal-reported',title='Résultat hors intervalle signalé par le labo',kind='lab'),
      dict(id='lab-unknown-flag',title='Absence de statut transmis : neutralité',kind='lab'),
      dict(id='external-import',title='Praticien non inscrit : patient photographie son document',kind='manual'),
      dict(id='offline-professional',title='Professionnel sans Ajour : import patient et provenance',kind='manual'),
      dict(id='rx-cancel',title='Ordonnance annulée ou remplacée : QR inutilisable',kind='pharmacy'),
      dict(id='existing-grants',title='Droits familiaux respectés',kind='security'),
      dict(id='duplicate-results',title='Double publication bloquée',kind='lab'),
    ]

def cancel_order(user,oid):
    with db.connect() as c:
        o=_order(c,oid)
        if not o:raise ValueError('Demande inconnue')
        owns=user['role']=='patient' and user['patient_id']==o['patient_id']
        doctor=user['role']=='doctor' and user['id']==o['author_id'] and portal.can(user,o['patient_id'],'all')
        if not owns and not doctor:raise PermissionError('Annulation réservée au patient ou au prescripteur')
        if o['status']!='issued':raise ValueError('Cette demande ne peut plus être annulée ici')
        c.execute('UPDATE aj_orders SET status="cancelled",updated_at=? WHERE id=?',(stamp(),oid))
        c.execute('UPDATE aj_qr_grants SET status="revoked" WHERE order_id=? AND status IN ("ready","redeemed")',(oid,))
        portal.add_event(c,user,o['patient_id'],'cancel','meds' if o['kind']=='prescription' else 'labs','Demande annulée')
    portal.log(user,o['patient_id'],'cancel_order')
    return {'ok':True,'status':'cancelled'}


def slot_add(user,starts_at,duration,location):
    if user['role']!='lab':raise PermissionError('Seul le laboratoire peut proposer un créneau')
    try:d=datetime.fromisoformat(starts_at.replace('Z','+00:00'))
    except ValueError:raise ValueError('Date invalide')
    if not d.tzinfo or not (now() < d <= now()+timedelta(days=180)):raise ValueError('Date future dans les 180 jours requise')
    if duration not in (15,20,30,45,60):raise ValueError('Durée non proposée')
    if not 3<=len(location.strip())<=140:raise ValueError('Lieu de rendez-vous nécessaire')
    slot_id=str(uuid4())
    with db.connect() as c:
        c.execute('INSERT INTO aj_lab_slots VALUES(?,?,?,?,?,?)',(slot_id,user['id'],d.isoformat(),duration,location.strip(),stamp()))
    return {'id':slot_id}


def slots(user):
    if user['role'] not in ('patient','lab'):raise PermissionError('Réservé au patient et au laboratoire')
    with db.connect() as c:
        rows=c.execute('''SELECT s.*,u.name AS lab_name FROM aj_lab_slots s JOIN portal_users u ON u.id=s.lab_id
           LEFT JOIN aj_lab_bookings b ON b.slot_id=s.id AND b.status='booked'
           WHERE s.starts_at>? AND b.id IS NULL ORDER BY s.starts_at LIMIT 100''',(stamp(),)).fetchall()
    return [dict(r) for r in rows]


def booking_create(user,oid,slot_id):
    if user['role']!='patient':raise PermissionError('Réservé au patient')
    with db.connect() as c:
        o=_order(c,oid)
        if not o or o['kind']!='lab' or o['status']!='issued' or o['patient_id']!=user['patient_id']:
            raise PermissionError('Demande de laboratoire non autorisée')
        s=c.execute('SELECT * FROM aj_lab_slots WHERE id=?',(slot_id,)).fetchone()
        if not s or s['starts_at']<=stamp():raise ValueError('Créneau non disponible')
        existing=c.execute('SELECT * FROM aj_lab_bookings WHERE slot_id=?',(slot_id,)).fetchone()
        if existing and existing['status']=='booked':raise ValueError('Créneau déjà réservé')
        if existing:c.execute('DELETE FROM aj_lab_bookings WHERE id=?',(existing['id'],))
        booking_id=str(uuid4())
        c.execute('INSERT INTO aj_lab_bookings VALUES(?,?,?,?,?,?)',(booking_id,oid,slot_id,user['patient_id'],'booked',stamp()))
        portal.add_event(c,user,user['patient_id'],'appointment','appointments','Rendez-vous de laboratoire réservé')
    return {'id':booking_id,'status':'booked'}


def bookings(user):
    if user['role'] not in ('patient','lab'):raise PermissionError('Accès au planning non autorisé')
    with db.connect() as c:
        if user['role']=='patient':
            rows=c.execute('''SELECT b.*,s.starts_at,s.location,u.name as lab_name,o.label AS order_label FROM aj_lab_bookings b
                JOIN aj_lab_slots s ON s.id=b.slot_id JOIN portal_users u ON u.id=s.lab_id JOIN aj_orders o ON o.id=b.order_id
                WHERE b.patient_id=? ORDER BY s.starts_at DESC''',(user['patient_id'],)).fetchall()
        else:
            rows=c.execute('''SELECT b.*,s.starts_at,s.location,o.label AS order_label,p.name AS patient_name
                FROM aj_lab_bookings b JOIN aj_lab_slots s ON s.id=b.slot_id JOIN aj_orders o ON o.id=b.order_id
                JOIN patients p ON p.id=b.patient_id WHERE s.lab_id=? ORDER BY s.starts_at DESC''',(user['id'],)).fetchall()
    return [dict(r) for r in rows]


def booking_cancel(user,booking_id):
    with db.connect() as c:
        row=c.execute('''SELECT b.*,s.lab_id FROM aj_lab_bookings b JOIN aj_lab_slots s ON b.slot_id=s.id WHERE b.id=?''',(booking_id,)).fetchone()
        if not row:raise ValueError('Rendez-vous inconnu')
        if user['role']=='patient' and user['patient_id']==row['patient_id']:pass
        elif user['role']=='lab' and user['id']==row['lab_id']:pass
        else:raise PermissionError('Annulation non autorisée')
        if row['status']!='booked':raise ValueError('Déjà annulé')
        c.execute('UPDATE aj_lab_bookings SET status="cancelled" WHERE id=?',(booking_id,))
    return {'ok':True}


def purge_expired_journeys():
    """Remove old QR and result links before standard observation retention cleanup."""
    now_iso=stamp();cutoff=(now()-timedelta(days=db.RETENTION_DAYS)).isoformat()
    with db.connect() as c:
        c.execute('DELETE FROM aj_result_items WHERE observation_id IN (SELECT id FROM observations WHERE retention_until<=?)',(now_iso,))
        c.execute('DELETE FROM aj_qr_grants WHERE expires_at<=? AND status IN ("ready","used","revoked")',(now_iso,))
        expired=[r['id'] for r in c.execute('SELECT id FROM aj_orders WHERE issued_at<?',(cutoff,))]
        for oid in expired:
            c.execute('DELETE FROM aj_result_items WHERE order_id=?',(oid,))
            c.execute('DELETE FROM aj_order_actions WHERE order_id=?',(oid,))
            c.execute('DELETE FROM aj_lab_bookings WHERE order_id=?',(oid,))
            c.execute('DELETE FROM aj_qr_grants WHERE order_id=?',(oid,))
            c.execute('DELETE FROM aj_orders WHERE id=?',(oid,))
        c.execute('DELETE FROM aj_lab_slots WHERE starts_at<? AND id NOT IN (SELECT slot_id FROM aj_lab_bookings)',(cutoff,))
