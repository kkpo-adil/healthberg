"""Local test workflows: patient-approved linking, home care visits, and safe account deactivation.

This module does NOT implement CPS, carte Vitale, INS qualification, telehealth,
clinical prescribing, or remote notifications.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4
import json
from . import db, portal

PROVIDERS={'doctor','dentist','nurse','optician','radiologist','podiatrist','orthotist','pharmacist','lab'}
DIRECT_SCOPES={
    'doctor':['all'],
    'nurse':['glucose','vitals','meds','messages','tasks','notes'],
    'pharmacist':['meds','messages'],
    'lab':['lab_publish'],
    'dentist':['care_ref'], 'optician':['care_ref'], 'radiologist':['care_ref'],
    'podiatrist':['care_ref'], 'orthotist':['care_ref'],
}

def now():return datetime.now(timezone.utc)
def stamp():return now().isoformat()

def init():
    with db.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS aj_link_tokens(
            token_hash TEXT PRIMARY KEY, patient_id TEXT REFERENCES patients(id),
            provider_id TEXT REFERENCES portal_users(id), purpose TEXT NOT NULL,
            expires_at TEXT NOT NULL, used_at TEXT, created_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS aj_nurse_visits(
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            nurse_id TEXT NOT NULL REFERENCES portal_users(id), planner_id TEXT NOT NULL REFERENCES portal_users(id),
            starts_at TEXT NOT NULL, care TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'planned',
            pain_score INTEGER, mental_note TEXT NOT NULL DEFAULT '', medication_observed TEXT NOT NULL DEFAULT '',
            injection TEXT NOT NULL DEFAULT '', vaccine TEXT NOT NULL DEFAULT '',
            completed_at TEXT, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_aj_visits_nurse_date ON aj_nurse_visits(nurse_id,starts_at);
        CREATE TABLE IF NOT EXISTS aj_medication_checks(
            id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),
            medication_id TEXT NOT NULL REFERENCES meds(id), reporter_id TEXT NOT NULL REFERENCES portal_users(id),
            taken_at TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS aj_activity_imports(
            id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),
            recorded_on TEXT NOT NULL,kind TEXT NOT NULL,value REAL NOT NULL,unit TEXT NOT NULL,
            source TEXT NOT NULL,digest TEXT NOT NULL,imported_at TEXT NOT NULL,
            UNIQUE(patient_id,recorded_on,kind,digest));
        CREATE TABLE IF NOT EXISTS aj_account_deactivation(
            user_id TEXT PRIMARY KEY REFERENCES portal_users(id), requested_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'disabled');
        ''')

def _hash(raw):return sha256(raw.encode()).hexdigest()

def share_code(user):
    if user['role']!='patient' or not user.get('patient_id'):raise PermissionError('Réservé au titulaire du dossier')
    code='AJ-LINK-'+token_urlsafe(18)
    with db.connect() as c:
        c.execute('INSERT INTO aj_link_tokens VALUES(?,?,?, ?,?,?,?)',
          (_hash(code),user['patient_id'],None,'patient_invites', (now()+timedelta(minutes=10)).isoformat(),None,user['id']))
    return {'code':code,'expires_in_minutes':10}

def provider_invitation(user):
    if user['role'] not in PROVIDERS:raise PermissionError('Professionnel uniquement')
    code='AJ-PRO-'+token_urlsafe(18)
    with db.connect() as c:
        c.execute('INSERT INTO aj_link_tokens VALUES(?,?,?, ?,?,?,?)',
          (_hash(code),None,user['id'],'provider_invites',(now()+timedelta(days=2)).isoformat(),None,user['id']))
    return {'code':code,'expires_in_hours':48,'instructions':'Le patient crée son compte puis accepte cette invitation depuis Mon profil.'}

def redeem(user,code):
    code=(code or '').strip()
    if not 15<=len(code)<=96:raise ValueError('Code incomplet')
    with db.connect() as c:
        row=c.execute('SELECT * FROM aj_link_tokens WHERE token_hash=?',(_hash(code),)).fetchone()
        if not row or row['used_at'] or row['expires_at']<=stamp():raise ValueError('Code inconnu, expiré ou déjà utilisé')
        if row['purpose']=='patient_invites':
            if user['role'] not in PROVIDERS:raise PermissionError('Un professionnel doit saisir ce code')
            target=user['id'];pid=row['patient_id']
        else:
            if user['role']!='patient' or not user.get('patient_id'):raise PermissionError('Le patient doit confirmer ce rapprochement')
            target=row['provider_id'];pid=user['patient_id']
        provider=c.execute('SELECT role FROM portal_users WHERE id=?',(target,)).fetchone()
        if not provider or provider['role'] not in DIRECT_SCOPES:raise PermissionError('Professionnel non autorisé')
        updated=c.execute('UPDATE aj_link_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at>?',(stamp(),_hash(code),stamp()))
        if updated.rowcount!=1:raise ValueError('Code déjà utilisé')
        permissions=DIRECT_SCOPES[provider['role']]
        c.execute('''INSERT INTO portal_grants(user_id,patient_id,permissions,revoked,expires_at) VALUES(?,?,?,0,NULL)
                  ON CONFLICT(user_id,patient_id) DO UPDATE SET permissions=excluded.permissions,revoked=0''',
                  (target,pid,json.dumps(permissions)))
        portal.add_event(c,user,pid,'sharing','messages','Association patient-professionnel approuvée')
    portal.log(user,pid,'patient_provider_link')
    return {'patient_id':pid,'provider_id':target,'scope':permissions,'approved_by':'patient'}

def schedule_visit(user,pid,nurse_id,starts_at,care):
    if user['role'] not in {'doctor','nurse'} or not portal.scopes(user,pid):raise PermissionError('Dossier non autorisé')
    try:when=datetime.fromisoformat(starts_at.replace('Z','+00:00'))
    except ValueError:raise ValueError('Date et heure invalides')
    if when.tzinfo is None or when<now()-timedelta(hours=1):raise ValueError('Date future attendue')
    if not 3<=len(care.strip())<=300:raise ValueError('Soin à préciser')
    with db.connect() as c:
        nurse=c.execute('SELECT role FROM portal_users WHERE id=?',(nurse_id,)).fetchone()
        if not nurse or nurse['role']!='nurse':raise ValueError('Infirmier introuvable')
        access=c.execute('SELECT 1 FROM portal_grants WHERE user_id=? AND patient_id=? AND revoked=0',(nurse_id,pid)).fetchone()
        if not access:raise PermissionError('L’infirmier doit d’abord être autorisé par le patient')
        vid=str(uuid4())
        c.execute('INSERT INTO aj_nurse_visits(id,patient_id,nurse_id,planner_id,starts_at,care,created_at) VALUES(?,?,?,?,?,?,?)',
                  (vid,pid,nurse_id,user['id'],when.astimezone(timezone.utc).isoformat(),care.strip(),stamp()))
        portal.add_event(c,user,pid,'care_plan','tasks','Visite infirmière planifiée')
    return {'id':vid,'status':'planned'}

def visits(user,period='day'):
    if user['role']!='nurse':raise PermissionError('Réservé aux infirmiers')
    if period not in {'day','week','month'}:raise ValueError('Période inconnue')
    start=now().astimezone().date()
    if period=='week':start-=timedelta(days=start.weekday())
    if period=='month':start=start.replace(day=1)
    end=start+timedelta(days=1 if period=='day' else 7 if period=='week' else 32)
    if period=='month':end=end.replace(day=1)
    from datetime import time
    a=datetime.combine(start,time.min,tzinfo=timezone.utc).isoformat()
    b=datetime.combine(end,time.min,tzinfo=timezone.utc).isoformat()
    with db.connect() as c:
        rows=c.execute('''SELECT v.*,p.name AS patient_name,p.age AS patient_age,
             COALESCE(pr.address,'') AS address, COALESCE(pr.phone,'') AS phone, COALESCE(pr.entry_code,'') AS entry_code FROM aj_nurse_visits v
             JOIN patients p ON p.id=v.patient_id LEFT JOIN aj_patient_profiles pr ON pr.patient_id=p.id
             JOIN portal_grants g ON g.patient_id=v.patient_id AND g.user_id=v.nurse_id AND g.revoked=0
             WHERE v.nurse_id=? AND v.starts_at>=? AND v.starts_at<? ORDER BY v.starts_at''',(user['id'],a,b)).fetchall()
    # Access to home addresses only for care staff who are specifically scheduled and authorized.
    return [dict(r) for r in rows]

def complete_visit(user,vid,pain_score,mental_note,medication_observed,injection,vaccine):
    if user['role']!='nurse':raise PermissionError('Réservé aux infirmiers')
    if pain_score is not None and not 0<=pain_score<=10:raise ValueError('Douleur : nombre de 0 à 10')
    for value in (mental_note,medication_observed,injection,vaccine):
        if len(value)>300:raise ValueError('Observation trop longue')
    with db.connect() as c:
        visit=c.execute('SELECT * FROM aj_nurse_visits WHERE id=?',(vid,)).fetchone()
        if not visit:raise ValueError('Visite introuvable')
        if visit['nurse_id']!=user['id'] or not portal.can(user,visit['patient_id'],'notes'):
            raise PermissionError('Visite non autorisée')
        if visit['status']!='planned':raise ValueError('Cette visite a déjà été validée')
        c.execute('''UPDATE aj_nurse_visits SET status='completed',pain_score=?,mental_note=?,
            medication_observed=?,injection=?,vaccine=?,completed_at=? WHERE id=?''',
            (pain_score,mental_note.strip(),medication_observed.strip(),injection.strip(),vaccine.strip(),stamp(),vid))
        portal.add_event(c,user,visit['patient_id'],'visit','notes','Visite infirmière effectuée')
    portal.log(user,visit['patient_id'],'visit_completed')
    return {'id':vid,'status':'completed'}

def medication_check(user,pid,mid,status):
    if status not in {'taken','not_taken'}:raise ValueError('Statut non autorisé')
    if not(user['role']=='patient' and user['patient_id']==pid):raise PermissionError('Seul le patient confirme sa prise')
    with db.connect() as c:
        r=c.execute('SELECT id FROM meds WHERE id=? AND patient_id=?',(mid,pid)).fetchone()
        if not r:raise ValueError('Traitement non trouvé')
        c.execute('INSERT INTO aj_medication_checks VALUES(?,?,?,?,?,?,?)',(str(uuid4()),pid,mid,user['id'],stamp(),status,stamp()))
    portal.log(user,pid,'medication_'+status)
    return {'status':status}

def medication_history(user,pid):
    if not (user['role']=='patient' and user['patient_id']==pid or user['role']=='doctor' and portal.can(user,pid,'all')):
        raise PermissionError('Accès refusé')
    with db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM aj_medication_checks WHERE patient_id=? ORDER BY taken_at DESC LIMIT 100',(pid,))]


def deactivate_own_account(user,password,confirm):
    """Account access deactivation, not deletion of clinical facts or legal retention."""
    if confirm!='DESACTIVER MON COMPTE' or user['role']!='patient':
        raise ValueError('Confirmation exacte et compte patient requis')
    if not portal.authenticate(user['email'],password):raise PermissionError('Mot de passe incorrect')
    with db.connect() as c:
        c.execute('INSERT OR REPLACE INTO aj_account_deactivation VALUES(?,?,?)',(user['id'],stamp(),'disabled'))
        c.execute('DELETE FROM portal_sessions WHERE user_id=?',(user['id'],))
        c.execute('UPDATE portal_grants SET revoked=1 WHERE patient_id=?',(user['patient_id'],))
    return {'access_disabled':True,'clinical_record_deleted':False}


def import_activity_csv(user,raw):
    """CSV adapter for hand-exported activity summaries. No vendor/HealthKit API."""
    import csv,io
    from hashlib import sha256
    if user['role']!='patient' or not user.get('patient_id'):raise PermissionError('Réservé au patient')
    if len(raw)>250_000:raise ValueError('CSV supérieur à 250 Ko')
    try:content=raw.decode('utf-8-sig')
    except UnicodeError:raise ValueError('CSV UTF-8 requis')
    reader=csv.DictReader(io.StringIO(content),delimiter=',')
    fields=set(reader.fieldnames or [])
    if 'date' not in fields or not fields.intersection({'steps','sleep_hours','heart_rate'}):
        raise ValueError('Colonnes attendues : date, steps et/ou sleep_hours et/ou heart_rate')
    rows=list(reader)
    if not 1<=len(rows)<=366:raise ValueError('Entre 1 et 366 lignes attendues')
    digest=sha256(raw).hexdigest();entries=[]
    for row in rows:
        day=(row.get('date') or '').strip()
        try:datetime.strptime(day,'%Y-%m-%d')
        except ValueError:raise ValueError('Date attendue au format AAAA-MM-JJ')
        for code,unit,limit in [('steps','pas',100000),('sleep_hours','h',24),('heart_rate','bpm',260)]:
            value=(row.get(code) or '').strip()
            if not value:continue
            try:n=float(value.replace(',','.'))
            except ValueError:raise ValueError('Valeur non numérique dans '+code)
            if not 0<=n<=limit:raise ValueError('Valeur hors limites de saisie dans '+code)
            entries.append((str(uuid4()),user['patient_id'],day,code,n,unit,'CSV importé (source déclarée)',digest,stamp()))
    if not entries:raise ValueError('Aucune valeur à intégrer')
    with db.connect() as c:
        before=c.total_changes
        for entry in entries:c.execute('INSERT OR IGNORE INTO aj_activity_imports VALUES(?,?,?,?,?,?,?,?,?)',entry)
        added=c.total_changes-before
    portal.log(user,user['patient_id'],'activity_csv_import')
    return {'scanned_records':len(entries),'imported_records':added,'already_present':len(entries)-added,'status':'imported','sha256':digest,'note':'Les valeurs proviennent du fichier fourni par l’utilisateur, sans vérification de l’appareil.'}

def activities(user):
    if user['role']!='patient' or not user.get('patient_id'):raise PermissionError('Réservé au patient')
    with db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM aj_activity_imports WHERE patient_id=? ORDER BY recorded_on DESC,kind LIMIT 90',(user['patient_id'],))]
