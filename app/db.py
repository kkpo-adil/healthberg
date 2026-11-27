"""Local SQLite demo store: structured fictional data only, no original documents."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from uuid import uuid4
from .terminology import METRIC_BY_CODE

DB_PATH = Path(os.getenv('HEALTHBERG_DB',str(Path(__file__).resolve().parents[1]/'healthberg_demo.sqlite3')))
RETENTION_DAYS = int(os.getenv('HEALTHBERG_RETENTION_DAYS','730'))
if not (30 <= RETENTION_DAYS <= 3650):
    raise RuntimeError('HEALTHBERG_RETENTION_DAYS must be 30..3650')

PATIENTS=[
    ('pat_marie','Marie Martin',78,'Diabète type 2 · hypertension · suivi cardiologique','MM','2026-10-15'),
    ('pat_louis','Louis Martin',81,'Hypertension · traitement multiple','LM','2026-10-08'),
    ('pat_jeanne','Jeanne Bernard',73,'Diabète type 2 · bilans rénaux','JB','2026-09-23'),
    ('pat_robert','Robert Dubois',85,'Suivi cardiovasculaire · polymédication','RD','2026-11-04'),
    ('pat_sophie','Sophie Moreau',67,'Hypertension · suivi général','SM','2026-10-21'),
]


class _ClosingConnection(sqlite3.Connection):
    """Commit or roll back and *close* after each `with db.connect()` block.

    sqlite3.Connection.__exit__ does not close files on its own. This demo
    uses many short requests, so leaked handles can exhaust macOS file
    descriptors and produce OperationalError: unable to open database file.
    """
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(DB_PATH, factory=_ClosingConnection)
    try:
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys = ON')
        c.execute('PRAGMA journal_mode = WAL')
        return c
    except BaseException:
        c.close()
        raise


def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS patients(id TEXT PRIMARY KEY,name TEXT NOT NULL,age INTEGER NOT NULL,profile TEXT NOT NULL,initials TEXT NOT NULL,last_consultation TEXT NOT NULL,synthetic INTEGER NOT NULL CHECK(synthetic=1));
        CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),document_kind TEXT NOT NULL,issuer TEXT,document_date TEXT,imported_at TEXT NOT NULL,sha256 TEXT NOT NULL,page_count INTEGER NOT NULL,extraction_method TEXT NOT NULL,original_retained INTEGER NOT NULL DEFAULT 0 CHECK(original_retained=0), retention_until TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),code TEXT NOT NULL,label TEXT NOT NULL,value REAL NOT NULL,unit TEXT NOT NULL,measured_at TEXT NOT NULL,original_value TEXT NOT NULL,original_unit TEXT NOT NULL,source_id TEXT NOT NULL REFERENCES receipts(id),page INTEGER,context TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,reference_range TEXT,retention_until TEXT NOT NULL, UNIQUE(patient_id,source_id,page,code,measured_at,original_value,original_unit));
        CREATE INDEX IF NOT EXISTS idx_obs_patient_date ON observations(patient_id, measured_at);
        CREATE INDEX IF NOT EXISTS idx_obs_patient_code ON observations(patient_id,code,measured_at);
        CREATE TABLE IF NOT EXISTS document_pages(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),source_id TEXT NOT NULL REFERENCES receipts(id),page INTEGER NOT NULL,text TEXT NOT NULL,retention_until TEXT NOT NULL, UNIQUE(source_id,page));
        CREATE TABLE IF NOT EXISTS report_findings(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),source_id TEXT NOT NULL REFERENCES receipts(id),code TEXT NOT NULL,label TEXT NOT NULL,value TEXT NOT NULL,unit TEXT NOT NULL,kind TEXT NOT NULL,page INTEGER NOT NULL,measured_at TEXT NOT NULL,status TEXT NOT NULL,retention_until TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS meds(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),name TEXT NOT NULL,schedule TEXT NOT NULL,state TEXT NOT NULL,since TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',source_id TEXT REFERENCES receipts(id),page INTEGER,retention_until TEXT);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),at TEXT NOT NULL,label TEXT NOT NULL,category TEXT NOT NULL,detail TEXT NOT NULL);
        ''')
        # Additive migration from demo 0.1 schema; safe for any local fictional records.
        med_cols={row[1] for row in c.execute('PRAGMA table_info(meds)')}
        for col,sqltype in [('source_id','TEXT'),('page','INTEGER'),('retention_until','TEXT')]:
            if col not in med_cols:c.execute(f'ALTER TABLE meds ADD COLUMN {col} {sqltype}')
        if c.execute('SELECT COUNT(*) FROM patients').fetchone()[0] == 0:
            for p in PATIENTS:c.execute('INSERT INTO patients VALUES(?,?,?,?,?,?,1)',p)
            seed(c)


def seed(c):
    """Deterministic fixtures, visibly fictional; graph data is never clinical advice."""
    today=date(2026,11,22)
    for idx,p in enumerate(PATIENTS):
        pid=p[0]
        rid=f'syn_source_{idx}'
        c.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(
            rid,pid,'Jeu de données fictives','Laboratoire DEMO', '2025-01-01',
            '2026-11-22T09:00:00+00:00',f'{idx+1:064x}',12,'générateur synthétique',0,'2028-11-21T09:00:00+00:00'))
        for n in range(20):
            d=today-timedelta(days=(19-n)*31)
            # Distinct but smoothly varying series, clinical plausibility not asserted.
            vals={'glucose':round(1.22+idx*.035-n*.009+((n%4)-1.5)*.024,2),
                  'hba1c':round(7.2+idx*.12-n*.035+((n%3)-1)*.06,2),
                  'systolic':round(153+idx*1.7-n*.79+((n%5)-2)*1.6,1),
                  'diastolic':round(92+idx*.8-n*.36+((n%4)-1.5)*.8,1),
                  'creatinine':round(9.9+idx*.38+n*.045+((n%4)-1.5)*.13,2),
                  'weight':round(78+idx*3-n*.17+((n%4)-1.5)*.15,1),
                  'pulse':round(77+idx*.9-n*.16+((n%3)-1)*1.6,1)}
            for code,value in vals.items():
                m=METRIC_BY_CODE[code]
                c.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
                    f'syn_{idx}_{n}_{code}',pid,code,m.label,value,m.unit,
                    d.isoformat()+'T08:30:00+01:00',str(value),m.unit,rid,1,
                    'Jeu fictif', 'synthetic_verified',None,'2028-11-21T09:00:00+00:00'))
        if idx in (0,1,3):
            c.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(f'evt_{idx}_1',pid,'2026-08-14','Réévaluation du traitement (fictive)','médicaments','Aucun effet médical déduit de cette date.'))
        c.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(f'evt_{idx}_2',pid,p[5],'Consultation de suivi (fictive)','consultation','Bilan de suivi annuel.'))
    for m in [
        ('med_1','pat_marie','Metformine (exemple)','Matin et soir','historical','2024-10-01','Donnée synthétique, non prescriptive'),
        ('med_2','pat_marie','Traitement antihypertenseur A','Le matin','declared','2026-08-14','À vérifier avec un professionnel'),
        ('med_3','pat_marie','Traitement cardiovasculaire B','Le soir','declared','2025-05-11','À vérifier avec un professionnel'),
        ('med_4','pat_louis','Traitement antihypertenseur C','Le matin','historical','2023-04-12','Donnée synthétique'),
        ('med_5','pat_robert','Traitement chronique D','Selon plan prescrit','declared','2026-09-01','Plan non vérifié'),
    ]:c.execute('INSERT INTO meds VALUES(?,?,?,?,?,?,?,?,?,?)',m+(None,None,None))


def patient_exists(c,patient_id:str)->bool:
    return c.execute('SELECT 1 FROM patients WHERE id=?',(patient_id,)).fetchone() is not None


def list_patients():
    with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM patients ORDER BY name')]


def patient_detail(pid):
    with connect() as c:
        r=c.execute('SELECT * FROM patients WHERE id=?',(pid,)).fetchone()
        return dict(r) if r else None


def list_observations(pid,code=None):
    with connect() as c:
        rows=c.execute('SELECT * FROM observations WHERE patient_id=?'+(' AND code=?' if code else '')+' ORDER BY measured_at ASC', (pid,code) if code else (pid,)).fetchall()
        return [dict(r) for r in rows]


def list_receipts(pid):
    with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM receipts WHERE patient_id=? ORDER BY imported_at DESC',(pid,))]


def receipt_by_id(pid,rid):
    with connect() as c:
        r=c.execute('SELECT * FROM receipts WHERE patient_id=? AND id=?',(pid,rid)).fetchone()
        return dict(r) if r else None


def list_events(pid):
    with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM events WHERE patient_id=? ORDER BY at DESC',(pid,))]


def list_meds(pid):
    with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM meds WHERE patient_id=? ORDER BY name',(pid,))]


def save_confirmation(patient_id:str,meta:dict,candidates:list[dict],medications:list[dict]|None=None,findings:list[dict]|None=None,page_texts:list[tuple[int,str]]|None=None):
    from .terminology import normalize
    now=datetime.now(timezone.utc)
    expires=(now+timedelta(days=RETENTION_DAYS)).isoformat()
    with connect() as c:
        if not patient_exists(c,patient_id):raise ValueError('Patient inconnu')
        dupe=c.execute('SELECT id FROM receipts WHERE patient_id=? AND sha256=?',(patient_id,meta['sha256'])).fetchone()
        if dupe:raise ValueError('Document déjà importé pour ce patient : doublon détecté')
        rid=str(uuid4())
        c.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(
            rid,patient_id,meta['document_kind'],meta.get('issuer'),meta.get('document_date'),now.isoformat(),meta['sha256'],meta['page_count'],meta['extraction_method'],0,expires))
        count=0
        for item in candidates:
            code=item['code']
            norm=normalize(code,float(item['value']),str(item['unit']))
            if norm is None: raise ValueError(f'Unité non validée : {code}/{item["unit"]}')
            value,unit=norm
            c.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
                str(uuid4()),patient_id,code,METRIC_BY_CODE[code].label,value,unit,item['measured_at'],
                str(item['original_value']),str(item['original_unit']),rid,int(item['page']),str(item.get('context','')),'patient_confirmed',None,expires))
            count+=1
        med_count=0
        for med in medications or []:
            name=(str(med['name'])+' '+str(med['strength'])).strip()
            c.execute('INSERT INTO meds VALUES(?,?,?,?,?,?,?,?,?,?)', (str(uuid4()),patient_id,name,str(med['directions']) or 'Non précisé','historical',str(med['since']), 'Extraction historique confirmée par utilisateur, non ordonnance active',rid,int(med['page']),expires))
            med_count+=1
        for finding in findings or []:
            c.execute('INSERT INTO report_findings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (
                str(uuid4()),patient_id,rid,finding['code'],finding['label'],finding['value'],
                finding['unit'],finding['kind'],finding['page'],finding['measured_at'],
                'patient_confirmed',expires))
        for page,text in page_texts or []:
            c.execute('INSERT INTO document_pages VALUES(?,?,?,?,?,?)',
                (str(uuid4()),patient_id,rid,page,text,expires))
        return {'pages_retained':len(page_texts or []),'findings_created':len(findings or []),'receipt_id':rid,'observations_created':count,'medications_created':med_count,'retention_until':expires}


def purge_expired(now:str|None=None):
    now=now or datetime.now(timezone.utc).isoformat()
    with connect() as c:
        obs=c.execute("DELETE FROM observations WHERE retention_until < ? AND id NOT LIKE 'syn_%'",(now,)).rowcount
        meds=c.execute("DELETE FROM meds WHERE retention_until IS NOT NULL AND retention_until < ?",(now,)).rowcount
        c.execute("DELETE FROM document_pages WHERE retention_until < ?",(now,))
        c.execute("DELETE FROM report_findings WHERE retention_until < ?",(now,))
        receipts=c.execute("DELETE FROM receipts WHERE retention_until < ? AND id NOT LIKE 'syn_source_%'",(now,)).rowcount
        return {'observations_removed':obs,'medications_removed':meds,'receipts_removed':receipts}


def list_findings(pid):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM report_findings WHERE patient_id=? ORDER BY measured_at DESC,page,code',(pid,))]


def list_document_pages(pid):
    with connect() as c:
        return [dict(row) for row in c.execute('SELECT * FROM document_pages WHERE patient_id=? ORDER BY source_id,page',(pid,))]
