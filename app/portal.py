"""Healthberg connected-role simulation, on SYNTHETIC local accounts only.

No remote exposure or suitability for real health data. Permissions are always checked server side.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
from hmac import compare_digest
from secrets import token_urlsafe, token_bytes
from uuid import uuid4
import json

from . import db
from .terminology import METRIC_BY_CODE, normalize

DEMO_PASSWORD = 'Demo-Healthberg-2026!'
ROLES = {'patient':'Particulier','family':'Proche','doctor':'Médecin','pharmacist':'Pharmacien','nurse':'Infirmier·ère','lab':'Laboratoire','optician':'Opticien','radiologist':'Radiologie','dentist':'Dentiste','podiatrist':'Podologue','orthotist':'Orthésiste'}
MEASURE_SCOPES = {'glucose':'glucose','hba1c':'labs','creatinine':'labs','systolic':'vitals','diastolic':'vitals','weight':'vitals','pulse':'vitals','spo2':'vitals','temperature':'vitals','respiratory_rate':'vitals','height':'vitals'}
FAMILY_SCOPES = ['glucose','vitals','labs','meds','messages','tasks','import','vaccines','prevention','appointments','wellbeing']
SEED_USERS = [
 ('u_patient','marie@demo.healthberg.local','Marie Martin','patient','pat_marie'),
 ('u_patient_louis','louis@demo.healthberg.local','Louis Martin','patient','pat_louis'),
 ('u_family','claire@demo.healthberg.local','Claire Martin','family',None),
 ('u_family_2','nicolas@demo.healthberg.local','Nicolas Martin','family',None),
 ('u_doctor','docteur@demo.healthberg.local','Dr Camille Bernard','doctor',None),
 ('u_pharmacist','pharmacie@demo.healthberg.local','Alexandre Laurent','pharmacist',None),
 ('u_nurse','infirmiere@demo.healthberg.local','Sophie Renard','nurse',None),
 ('u_lab','laboratoire@demo.healthberg.local','Laboratoire BioTest','lab',None),
 ('u_optician','opticien@demo.healthberg.local','Optique Démonstration','optician',None),
 ('u_radiologist','radiologie@demo.healthberg.local','Centre Imagerie Démo','radiologist',None),
 ('u_dentist','dentiste@demo.healthberg.local','Cabinet Dentaire Démo','dentist',None),
 ('u_podiatrist','podologue@demo.healthberg.local','Cabinet Podologie Démo','podiatrist',None),
 ('u_orthotist','orthese@demo.healthberg.local','Atelier Orthèses Démo','orthotist',None),
]
SEED_GRANTS = [
 ('u_family','pat_marie',['glucose','vitals','meds','messages','tasks','import']),
 ('u_family_2','pat_louis',['glucose','vitals','messages']),
 ('u_doctor','pat_marie',['all']),('u_doctor','pat_louis',['all']),('u_doctor','pat_jeanne',['all']),
 ('u_pharmacist','pat_marie',['meds','messages']),('u_pharmacist','pat_louis',['meds','messages']),
 ('u_nurse','pat_marie',['glucose','vitals','meds','messages','tasks','notes']),('u_nurse','pat_louis',['glucose','vitals','meds','messages','tasks','notes']),
 ('u_lab','pat_marie',['lab_publish']),('u_lab','pat_louis',['lab_publish']),
]


def utcnow(): return datetime.now(timezone.utc).isoformat()


def encrypt_password(password: str, salt: bytes):
    return pbkdf2_hmac('sha256',password.encode(),salt,240_000).hex()


def init_portal():
    db.init_db()
    with db.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS portal_users(
            id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,
            patient_id TEXT,salt TEXT NOT NULL,password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS portal_grants(
            user_id TEXT NOT NULL REFERENCES portal_users(id),patient_id TEXT NOT NULL REFERENCES patients(id),
            permissions TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,expires_at TEXT,
            PRIMARY KEY(user_id,patient_id));
        CREATE TABLE IF NOT EXISTS portal_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES portal_users(id),expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS portal_messages(
            id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),sender_id TEXT NOT NULL REFERENCES portal_users(id),
            recipient_id TEXT NOT NULL REFERENCES portal_users(id),body TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS portal_notes(
            id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),author_id TEXT NOT NULL REFERENCES portal_users(id),
            kind TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS portal_dispenses(
            id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),medication_id TEXT NOT NULL REFERENCES meds(id),
            author_id TEXT NOT NULL REFERENCES portal_users(id),quantity TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS portal_tasks(
            id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),author_id TEXT NOT NULL REFERENCES portal_users(id),
            assignee_id TEXT NOT NULL REFERENCES portal_users(id),title TEXT NOT NULL,due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'todo',completed_at TEXT);
        CREATE TABLE IF NOT EXISTS portal_events(
            id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),actor_id TEXT NOT NULL REFERENCES portal_users(id),
            kind TEXT NOT NULL,scope TEXT NOT NULL,description TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS portal_audit(
            id TEXT PRIMARY KEY,actor_id TEXT NOT NULL,patient_id TEXT,action TEXT NOT NULL,at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_portal_messages_recipient ON portal_messages(recipient_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_portal_events_patient ON portal_events(patient_id,created_at);
        ''')
        c.execute('''CREATE TABLE IF NOT EXISTS aj_patient_profiles(
            patient_id TEXT PRIMARY KEY REFERENCES patients(id),
            birth_date TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
            profession TEXT NOT NULL DEFAULT '', insurer TEXT NOT NULL DEFAULT '',
            member_test_id TEXT NOT NULL DEFAULT '', social_test_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '');''')
        for col in ('phone','entry_code'):
            if col not in {r[1] for r in c.execute('PRAGMA table_info(aj_patient_profiles)')}:
                c.execute(f"ALTER TABLE aj_patient_profiles ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        for uid,email,name,role,pid in SEED_USERS:
            salt=sha256(('healthberg-local-demo:'+uid).encode()).digest()[:16]
            c.execute('INSERT OR IGNORE INTO portal_users VALUES(?,?,?,?,?,?,?)',
                      (uid,email,name,role,pid,salt.hex(),encrypt_password(DEMO_PASSWORD,salt)))
        for uid,pid,scopes in SEED_GRANTS:
            c.execute('INSERT OR IGNORE INTO portal_grants(user_id,patient_id,permissions,revoked,expires_at) VALUES(?,?,?,0,NULL)',(uid,pid,json.dumps(scopes)))
        if c.execute('SELECT COUNT(*) FROM portal_notes').fetchone()[0]==0:
            c.execute('INSERT INTO portal_notes VALUES(?,?,?,?,?,?)',
                ('note_demo','pat_marie','u_nurse','psychosocial','Patiente fictive : exprime une inquiétude concernant un ancien traitement. À transmettre au médecin.','2026-11-17T11:00:00+00:00'))
        if c.execute('SELECT COUNT(*) FROM portal_messages').fetchone()[0]==0:
            c.execute('INSERT INTO portal_messages VALUES(?,?,?,?,?,?)',
                ('msg_demo','pat_marie','u_nurse','u_doctor','Démonstration : la patiente souhaite discuter de son traitement lors du prochain échange.','2026-11-17T11:10:00+00:00'))
        if c.execute('SELECT COUNT(*) FROM portal_tasks').fetchone()[0]==0:
            c.execute('INSERT INTO portal_tasks VALUES(?,?,?,?,?,?,?,?)',
                ('task_demo','pat_marie','u_doctor','u_nurse','Relever la tension et la glycémie lors de la visite (fictif)','2026-11-23','todo',None))


def public_user(u):return {k:u.get(k) for k in ('id','email','name','role','patient_id')}


def user_by_id(uid):
    with db.connect() as c:
        r=c.execute('SELECT * FROM portal_users WHERE id=?',(uid,)).fetchone()
        return dict(r) if r else None


def authenticate(email,password):
    with db.connect() as c:
        r=c.execute('SELECT * FROM portal_users WHERE email=?',(email.lower().strip(),)).fetchone()
        if not r:return None
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='aj_account_deactivation'").fetchone() and c.execute('SELECT 1 FROM aj_account_deactivation WHERE user_id=?',(r['id'],)).fetchone():return None
        u=dict(r)
        if not compare_digest(encrypt_password(password,bytes.fromhex(u['salt'])),u['password_hash']):return None
        return u


def new_session(user_id):
    token=token_urlsafe(40)
    with db.connect() as c:
        c.execute('INSERT INTO portal_sessions VALUES(?,?,?)',(sha256(token.encode()).hexdigest(),user_id,(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
    return token


def session_user(token):
    if not token:return None
    with db.connect() as c:
        r=c.execute('SELECT u.* FROM portal_sessions s JOIN portal_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?',(sha256(token.encode()).hexdigest(),utcnow())).fetchone()
        return dict(r) if r else None


def revoke_session(token):
    if token:
        with db.connect() as c:c.execute('DELETE FROM portal_sessions WHERE token_hash=?',(sha256(token.encode()).hexdigest(),))


def scopes(user,pid):
    from . import experience
    if user['role']=='patient':return {'all'} if user['patient_id']==pid else set()
    with db.connect() as c:
        r=c.execute('SELECT permissions,revoked,expires_at FROM portal_grants WHERE user_id=? AND patient_id=?',(user['id'],pid)).fetchone()
    standing=set()
    if r and not r['revoked'] and (not r['expires_at'] or r['expires_at']>=utcnow()):standing=set(json.loads(r['permissions']))
    if user['role']=='doctor':standing.update(experience.appointment_scopes(user,pid))
    return standing


def can(user,pid,scope,write=False):
    ss=scopes(user,pid)
    if not ss:return False
    role=user['role']
    if role=='patient':return True
    if role=='doctor':return 'all' in ss or (not write and scope in ss)
    if role=='family':
        if scope in ('notes','lab_publish','prescribe','dispense','write_measure','write_task'):return False
        return scope in ss and (not write or scope in ('messages','import'))
    if role=='nurse':
        if scope in ('vaccines','prevention','appointments','wellbeing'):return False
        if scope=='write_measure':return write and 'vitals' in ss
        if scope=='write_task':return False
        return scope in ss and scope in ('glucose','vitals','meds','messages','tasks','notes')
    if role=='pharmacist':
        if scope in ('vaccines','prevention','appointments','wellbeing'):return False
        if scope=='dispense':return write and 'meds' in ss
        return scope in ss and scope in ('meds','messages')
    if role=='lab':return scope=='lab_publish' and write and 'lab_publish' in ss
    return False


def visible_patients(user):
    from . import experience
    with db.connect() as c:
        if user['role']=='patient':
            rows=c.execute('SELECT * FROM patients WHERE id=?',(user['patient_id'],)).fetchall()
        else:
            rows=c.execute('SELECT p.* FROM patients p JOIN portal_grants g ON p.id=g.patient_id WHERE g.user_id=? AND g.revoked=0 AND (g.expires_at IS NULL OR g.expires_at>?) ORDER BY p.name',(user['id'],utcnow())).fetchall()
    items={r['id']:dict(r) for r in rows}
    if user['role']=='doctor':
        appointment_ids=experience.appointment_patient_ids(user)
        with db.connect() as c:
            for patient_id in appointment_ids:
                r=c.execute('SELECT * FROM patients WHERE id=?',(patient_id,)).fetchone()
                if r:items[patient_id]=dict(r)
    result=[]
    for item in items.values():
        if user['role'] not in ('patient','doctor') or (user['role']=='doctor' and 'all' not in scopes(user,item['id'])):
            item={key:item[key] for key in ('id','name','initials','age','synthetic') if key in item}
        result.append(item)
    return sorted(result,key=lambda x:x['name'])


def visible_obs(user,pid):
    ss=scopes(user,pid)
    if not ss:return []
    if user['role'] in ('pharmacist','lab'):return []
    values=db.list_observations(pid)
    return [o for o in values if can(user,pid,MEASURE_SCOPES.get(o['code'],'labs'))]


def events(user,pid):
    if not scopes(user,pid):return []
    with db.connect() as c:rows=c.execute('SELECT * FROM portal_events WHERE patient_id=? ORDER BY created_at DESC LIMIT 40',(pid,)).fetchall()
    return [dict(r) for r in rows if can(user,pid,r['scope']) or user['role']=='lab' and r['actor_id']==user['id']]


def log(user,patient_id,action):
    with db.connect() as c:c.execute('INSERT INTO portal_audit VALUES(?,?,?,?,?)',(str(uuid4()),user['id'],patient_id,action,utcnow()))


def add_event(c,user,pid,kind,scope,description):
    c.execute('INSERT INTO portal_events VALUES(?,?,?,?,?,?,?)',(str(uuid4()),pid,user['id'],kind,scope,description,utcnow()))


def note_create(user,pid,kind,body):
    with db.connect() as c:
        nid=str(uuid4());c.execute('INSERT INTO portal_notes VALUES(?,?,?,?,?,?)',(nid,pid,user['id'],kind,body,utcnow()))
        add_event(c,user,pid,'note','notes','Nouvelle note de suivi pour l’équipe soignante')
    log(user,pid,'create_note');return nid


def list_notes(user,pid):
    if not can(user,pid,'notes'):return []
    with db.connect() as c:rows=c.execute('SELECT n.*,u.name AS author FROM portal_notes n JOIN portal_users u ON n.author_id=u.id WHERE n.patient_id=? ORDER BY n.created_at DESC',(pid,)).fetchall()
    return [dict(r) for r in rows if user['role'] in ('patient','doctor') or r['author_id']==user['id']]


def directory(user,pid):
    if not scopes(user,pid):return []
    with db.connect() as c:
        rows=c.execute('SELECT u.id,u.name,u.role FROM portal_users u JOIN portal_grants g ON g.user_id=u.id WHERE g.patient_id=? AND g.revoked=0 AND (g.expires_at IS NULL OR g.expires_at>?)',(pid,utcnow())).fetchall()
        patient=c.execute('SELECT id,name,role FROM portal_users WHERE patient_id=?',(pid,)).fetchone()
    people=[dict(r) for r in rows]
    if patient and patient['id'] not in [p['id'] for p in people]:people.append(dict(patient))
    return people


def list_messages(user,pid):
    if not can(user,pid,'messages'):return []
    with db.connect() as c:
        rows=c.execute('''SELECT m.*,a.name AS author,b.name AS recipient FROM portal_messages m
           JOIN portal_users a ON a.id=m.sender_id JOIN portal_users b ON b.id=m.recipient_id
           WHERE m.patient_id=? AND (m.sender_id=? OR m.recipient_id=?) ORDER BY m.created_at DESC''',(pid,user['id'],user['id'])).fetchall()
    return [dict(r) for r in rows]


def send_message(user,pid,recipient_id,body):
    directory_ids={u['id'] for u in directory(user,pid)}
    recipient=user_by_id(recipient_id)
    if recipient_id not in directory_ids or recipient_id==user['id'] or recipient is None or not can(recipient,pid,'messages'):
        raise ValueError('Destinataire non autorisé')
    if not can(user,pid,'messages',True):raise PermissionError('Messagerie non autorisée')
    with db.connect() as c:
        mid=str(uuid4())
        c.execute('INSERT INTO portal_messages VALUES(?,?,?,?,?,?)',(mid,pid,user['id'],recipient_id,body,utcnow()))
        # Not a clinical alert; recipient checks inbox manually.
        add_event(c,user,pid,'message','messages','Message déposé dans la messagerie interne')
    log(user,pid,'send_message');return mid


def list_meds(user,pid):
    if not can(user,pid,'meds'):return []
    meds=db.list_meds(pid)
    with db.connect() as c:
        disp=[dict(r) for r in c.execute('SELECT d.*,u.name AS author FROM portal_dispenses d JOIN portal_users u ON u.id=d.author_id WHERE d.patient_id=? ORDER BY d.created_at DESC',(pid,))]
    for med in meds:med['dispenses']=[d for d in disp if d['medication_id']==med['id']]
    return meds


def prescribe(user,pid,name,schedule):
    if user['role']!='doctor' or not can(user,pid,'all'):raise PermissionError('Seul un médecin affecté peut saisir une prescription de démo')
    with db.connect() as c:
        mid=str(uuid4())
        c.execute('INSERT INTO meds VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,pid,name,schedule,'professional_verified',utcnow()[:10],f'Prescription fictive structurée par {user["name"]}',None,None,(datetime.now(timezone.utc)+timedelta(days=db.RETENTION_DAYS)).isoformat()))
        add_event(c,user,pid,'prescription','meds','Nouvelle prescription structurée (fictive)')
    log(user,pid,'prescribe');return mid


def dispense(user,pid,med_id,qty,note):
    if not can(user,pid,'dispense',True):raise PermissionError('Délivrance réservée à la pharmacie affectée')
    with db.connect() as c:
        exists=c.execute('SELECT 1 FROM meds WHERE id=? AND patient_id=?',(med_id,pid)).fetchone()
        if not exists:raise ValueError('Prescription introuvable pour ce patient')
        did=str(uuid4())
        c.execute('INSERT INTO portal_dispenses VALUES(?,?,?,?,?,?,?)',(did,pid,med_id,user['id'],qty,note,utcnow()))
        add_event(c,user,pid,'dispense','meds','Délivrance enregistrée par la pharmacie (fictive)')
    log(user,pid,'dispense');return did


def task_create(user,pid,assignee,title,due):
    if user['role']!='doctor' or not can(user,pid,'all'):raise PermissionError('Planification réservée au médecin affecté')
    p=user_by_id(assignee)
    if not p or p['role']!='nurse' or not can(p,pid,'tasks'):raise ValueError('Infirmier non affecté à ce patient')
    with db.connect() as c:
        tid=str(uuid4());c.execute('INSERT INTO portal_tasks VALUES(?,?,?,?,?,?,?,?)',(tid,pid,user['id'],assignee,title,due,'todo',None))
        add_event(c,user,pid,'task','tasks','Nouvelle consigne de soin (fictive)')
    log(user,pid,'task_create');return tid


def task_complete(user,pid,task_id):
    if not can(user,pid,'tasks'):raise PermissionError('Consignes non accessibles')
    with db.connect() as c:
        row=c.execute('SELECT * FROM portal_tasks WHERE id=? AND patient_id=?',(task_id,pid)).fetchone()
        if not row or (user['id']!=row['assignee_id'] and user['role']!='doctor'):
            raise PermissionError('Consigne non attribuée à ce compte')
        c.execute('UPDATE portal_tasks SET status=?,completed_at=? WHERE id=?',('done',utcnow(),task_id))
        add_event(c,user,pid,'task','tasks','Acte de démonstration marqué comme réalisé')
    log(user,pid,'task_complete')


def list_tasks(user,pid):
    if not can(user,pid,'tasks'):return []
    with db.connect() as c:
        rows=c.execute('''SELECT t.*,u.name AS assignee FROM portal_tasks t JOIN portal_users u ON u.id=t.assignee_id WHERE t.patient_id=? ORDER BY t.due_date,t.status''',(pid,)).fetchall()
    return [dict(r) for r in rows]


def add_measure(user,pid,code,value,unit,measured_at,context=''):
    if code not in METRIC_BY_CODE:raise ValueError('Paramètre non pris en charge')
    role=user['role']
    if role=='lab':
        if not can(user,pid,'lab_publish',True) or code not in {'glucose','hba1c','creatinine','ldl','hdl','triglycerides','hemoglobin','potassium','sodium','crp','tsh','ferritin','alat','asat','inr','psa','platelets','leukocytes','albuminuria','egfr','cholesterol'}:raise PermissionError('Laboratoire : résultats biologiques attribués uniquement')
    elif role=='nurse':
        if not can(user,pid,'write_measure',True) or code not in {'glucose','systolic','diastolic','pulse','weight','spo2','temperature','respiratory_rate','height'}:raise PermissionError('Infirmière : constantes autorisées uniquement')
    elif role in ('patient','doctor'):
        if not can(user,pid,'glucose',True) and not can(user,pid,'all',True):raise PermissionError('Mesure non autorisée')
    else:raise PermissionError('Saisie de mesure non autorisée')
    try: normalized=normalize(code,float(value),unit)
    except (ValueError,TypeError):normalized=None
    if not normalized:raise ValueError('Valeur / unité non reconnue')
    value2,unit2=normalized
    try:
        dt=datetime.fromisoformat(measured_at.replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError()
    except ValueError:raise ValueError('Horodatage avec fuseau requis')
    if dt>datetime.now(timezone.utc)+timedelta(days=1):raise ValueError('Date future non autorisée')
    rid=str(uuid4());oid=str(uuid4());now=utcnow();exp=(datetime.now(timezone.utc)+timedelta(days=db.RETENTION_DAYS)).isoformat()
    status='professional_verified' if role in ('lab','nurse','doctor') else 'patient_confirmed'
    with db.connect() as c:
        c.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(rid,pid,'Résultat laboratoire fictif' if role=='lab' else 'Mesure manuelle fictive',user['name'],measured_at[:10],now,sha256(('fictional:'+rid).encode()).hexdigest(),0,'saisie structurée',0,exp))
        c.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(oid,pid,code,METRIC_BY_CODE[code].label,value2,unit2,measured_at,str(value),unit,rid,None,context,status,None,exp))
        add_event(c,user,pid,'measurement',MEASURE_SCOPES.get(code,'labs'),f'Nouvelle mesure {METRIC_BY_CODE[code].label} (fictive)')
    log(user,pid,'create_observation');return {'observation_id':oid,'receipt_id':rid,'status':status}


def list_grants(user,pid):
    if user['role']!='patient' or user['patient_id']!=pid:raise PermissionError('Réservé au patient')
    with db.connect() as c:
        rows=c.execute('SELECT g.*,u.name,u.role FROM portal_grants g JOIN portal_users u ON u.id=g.user_id WHERE g.patient_id=? ORDER BY u.name',(pid,)).fetchall()
    return [{**dict(r),'permissions':json.loads(r['permissions'])} for r in rows]


def modify_family_grant(user,pid,family_id,permissions,revoked):
    if user['role']!='patient' or user['patient_id']!=pid:raise PermissionError('Seul le patient peut gérer ses proches')
    family=user_by_id(family_id)
    if not family or family['role']!='family':raise ValueError('Compte proche inconnu')
    if not isinstance(permissions,list) or not all(s in FAMILY_SCOPES for s in permissions):raise ValueError('Droits invalides')
    with db.connect() as c:
        c.execute('INSERT INTO portal_grants(user_id,patient_id,permissions,revoked,expires_at) VALUES(?,?,?,?,NULL) ON CONFLICT(user_id,patient_id) DO UPDATE SET permissions=excluded.permissions,revoked=excluded.revoked',(family_id,pid,json.dumps(sorted(set(permissions))),int(revoked)))
        add_event(c,user,pid,'sharing','vitals','Autorisations de partage familial modifiées')
    log(user,pid,'grant_update')



def list_demo_accounts():
    with db.connect() as c:
        rows=c.execute("SELECT id,email,name,role,patient_id FROM portal_users ORDER BY CASE WHEN id='u_patient' THEN -1 WHEN role='patient' THEN 0 WHEN role='family' THEN 1 WHEN role='doctor' THEN 2 WHEN role='pharmacist' THEN 3 WHEN role='nurse' THEN 4 ELSE 5 END,name").fetchall()
    return [dict(r) for r in rows]


def demo_register(role: str,name: str,profile:dict|None=None):
    """Create an unverified, fiction-only demonstration identity. No clinical eligibility implied."""
    if role not in ROLES:raise ValueError('Rôle inconnu')
    name=name.strip()
    if len(name)<3 or len(name)>70:raise ValueError('Nom fictif : 3 à 70 caractères')
    uid='u_'+uuid4().hex[:18]
    email='demo-'+uuid4().hex[:10]+'@demo.healthberg.local'
    pid=None
    if role=='patient':pid='pat_'+uuid4().hex[:16]
    if pid and profile:_validated_profile(profile)
    salt=token_bytes(16)
    with db.connect() as c:
        if pid:
            first=''.join(p[0] for p in name.split() if p)[:2].upper()
            c.execute('INSERT INTO patients VALUES(?,?,?,?,?,?,1)',(pid,name,55,'Dossier fictif à compléter',first,utcnow()[:10]))
        c.execute('INSERT INTO portal_users VALUES(?,?,?,?,?,?,?)',(uid,email,name,role,pid,salt.hex(),encrypt_password(DEMO_PASSWORD,salt)))
    if pid and profile:
        save_patient_profile(pid,profile)
    return {'id':uid,'email':email,'name':name,'role':role,'patient_id':pid}


def grant_to_account(user,pid,target_id,permissions=None,revoked=False):
    if user['role']!='patient' or user['patient_id']!=pid:raise PermissionError('Partage réservé au patient concerné')
    target=user_by_id(target_id)
    if not target or target['role']=='patient':raise ValueError('Compte destinataire invalide')
    role=target['role']
    allowed={
        'doctor':['all'],
        'pharmacist':['meds','messages'],
        'nurse':['glucose','vitals','meds','messages','tasks','notes'],
        'lab':['lab_publish'],
    }
    if role=='family':
        permissions=permissions if permissions is not None else ['glucose','vitals','meds','messages']
        if not isinstance(permissions,list) or any(p not in FAMILY_SCOPES for p in permissions):raise ValueError('Permissions proches non autorisées')
        chosen=sorted(set(permissions))
    else:
        # Fixed-by-role synthetic scope, never client-controlled professional privileges.
        # Ajour's new specialty providers NEVER get a general patient grant; they must use a patient-issued order QR.
        if role not in allowed:raise ValueError('Ce professionnel utilise un QR limité à la demande, sans accès permanent au dossier')
        chosen=allowed[role]
    with db.connect() as c:
        c.execute('INSERT INTO portal_grants(user_id,patient_id,permissions,revoked,expires_at) VALUES(?,?,?,?,NULL) ON CONFLICT(user_id,patient_id) DO UPDATE SET permissions=excluded.permissions,revoked=excluded.revoked',(target_id,pid,json.dumps(chosen),int(revoked)))
        add_event(c,user,pid,'sharing','vitals','Partage du dossier fictif modifié')
    log(user,pid,'grant_update')


def audit(user,pid):
    if user['role']!='patient' or user['patient_id']!=pid:raise PermissionError('Journal privé réservé au patient')
    with db.connect() as c:
        rows=c.execute('SELECT a.*,u.name AS actor FROM portal_audit a LEFT JOIN portal_users u ON u.id=a.actor_id WHERE a.patient_id=? ORDER BY a.at DESC LIMIT 100',(pid,)).fetchall()
    return [dict(r) for r in rows]


def purge_expired_portal(now: str|None=None):
    """Best-effort demo TTL for event payloads. Not a legal retention policy or production scheduler."""
    now=now or utcnow()
    cutoff=(datetime.fromisoformat(now)-timedelta(days=db.RETENTION_DAYS)).isoformat()
    with db.connect() as c:
        removed={}
        for table,col in [('portal_messages','created_at'),('portal_notes','created_at'),('portal_dispenses','created_at'),('portal_tasks','completed_at'),('portal_events','created_at'),('portal_audit','at')]:
            if table=='portal_tasks':
                removed[table]=c.execute('DELETE FROM portal_tasks WHERE status=? AND completed_at IS NOT NULL AND completed_at<?',('done',cutoff)).rowcount
            else:
                removed[table]=c.execute(f'DELETE FROM {table} WHERE {col}<?',(cutoff,)).rowcount
        removed['sessions']=c.execute('DELETE FROM portal_sessions WHERE expires_at<?',(now,)).rowcount
    return removed


PATIENT_PROFILE_FIELDS=('birth_date','address','profession','insurer','member_test_id','social_test_id','phone','entry_code')

def _validated_profile(values):
    from datetime import date
    data={k:str(values.get(k) or '').strip() for k in PATIENT_PROFILE_FIELDS}
    if any(len(v)>160 for v in data.values()):raise ValueError('Champ de profil trop long')
    if data['birth_date']:
        try:
            birthday=date.fromisoformat(data['birth_date'])
            if not date(1900,1,1)<=birthday<=date.today():raise ValueError('Date de naissance invalide')
        except ValueError as e:raise ValueError('Date de naissance invalide') from e
    if data['social_test_id'] and not data['social_test_id'].upper().startswith('TEST-'):
        raise ValueError('Numéro de démonstration uniquement : utiliser TEST-... et jamais un véritable numéro de Sécurité sociale')
    if data['member_test_id'] and not data['member_test_id'].upper().startswith('TEST-'):
        raise ValueError('Adhérent de démonstration uniquement : utiliser TEST-...')
    return data

def save_patient_profile(pid,profile):
    from datetime import date
    values=_validated_profile(profile)
    with db.connect() as c:
        if not db.patient_exists(c,pid):raise ValueError('Patient introuvable')
        c.execute('''INSERT INTO aj_patient_profiles(patient_id,birth_date,address,profession,insurer,member_test_id,social_test_id,phone,entry_code,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(patient_id) DO UPDATE SET
          birth_date=excluded.birth_date,address=excluded.address,profession=excluded.profession,
          insurer=excluded.insurer,member_test_id=excluded.member_test_id,
          social_test_id=excluded.social_test_id,phone=excluded.phone,entry_code=excluded.entry_code,updated_at=excluded.updated_at''',
          (pid,*(values[k] for k in PATIENT_PROFILE_FIELDS),utcnow()))
        if values['birth_date']:
            birthday=date.fromisoformat(values['birth_date']);today=date.today()
            age=today.year-birthday.year-((today.month,today.day)<(birthday.month,birthday.day))
            c.execute('UPDATE patients SET age=? WHERE id=?',(age,pid))
    return values

def get_patient_profile(pid):
    with db.connect() as c:
        row=c.execute('SELECT * FROM aj_patient_profiles WHERE patient_id=?',(pid,)).fetchone()
    return {**{k:'' for k in PATIENT_PROFILE_FIELDS},**(dict(row) if row else {}),'identity_status':'unverified_demo'}


def visible_findings(user,pid):
    if user['role'] in ('lab','pharmacist') or not can(user,pid,'labs'):
        return []
    return db.list_findings(pid)


def visible_document_pages(user,pid):
    # Unclassified text cannot safely inherit a limited clinical category.
    if user['role'] not in ('patient','doctor') or 'all' not in scopes(user,pid):
        return []
    return db.list_document_pages(pid)
