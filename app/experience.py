"""Healthberg v0.4 synthetic-only patient experience: narrative, prevention, vaccines, appointments.
All access to these routes is server-checked. No medical advice or automated screening decisions.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from . import db, portal
import json

METRICS={
 'glucose':('Glycémie',"La glycémie est la quantité de sucre mesurée dans le sang. Une mesure seule ne raconte pas toute l'histoire."),
 'hba1c':('HbA1c',"L’HbA1c est un résultat d’analyse qui renseigne sur la glycémie sur une période passée. Elle n’est pas identique à une mesure de glycémie."),
 'systolic':('Tension (premier chiffre)',"La tension est la pression du sang dans les artères. Le premier chiffre est la pression quand le cœur se contracte."),
 'diastolic':('Tension (deuxième chiffre)',"Le deuxième chiffre est la pression quand le cœur se relâche. Les deux chiffres se lisent ensemble."),
 'pulse':('Pouls',"Le pouls indique combien de battements du cœur ont été mesurés par minute."),
 'weight':('Poids',"Le poids change pour de nombreuses raisons ; seul un professionnel peut interpréter son évolution dans votre contexte."),
 'creatinine':('Créatinine',"La créatinine est une substance mesurée dans le sang qui aide les professionnels à évaluer le fonctionnement des reins."),
}
# The catalogue is an onboarding/UX directory, not a binding French regulatory authorization list.
DOMAINS=[
 ('Cardiologie','Cœur et circulation'),('Diabétologie','Sucre dans le sang'),('Néphrologie','Reins'),
 ('Pneumologie','Poumons et respiration'),('Neurologie','Cerveau et nerfs'),('Gastroentérologie','Digestion'),
 ('Dermatologie','Peau'),('Oncologie','Suivi des cancers'),('Gériatrie','Santé des personnes âgées'),
 ('Pédiatrie','Santé des enfants'),('Gynécologie','Santé gynécologique'),('Urologie','Appareil urinaire'),
 ('Psychiatrie','Santé mentale'),('Ophtalmologie','Yeux'),('ORL','Oreilles, nez et gorge'),
 ('Odontologie','Dents'),('Rhumatologie','Articulations'),('Endocrinologie','Hormones'),
 ('Hématologie','Sang'),('Allergologie','Allergies'),('Maladies infectieuses','Infections'),
 ('Kinésithérapie','Mobilité et rééducation'),('Sage-femme','Grossesse et santé périnatale'),
 ('Orthophonie','Parole et langage'),('Diététique','Alimentation'),('Médecine générale','Santé globale')]

# Educational suggestions only, never individualized "due" claims.
PREVENTION_LIBRARY=[
 ('vaccinations','Faire le point sur mes vaccins',"Un professionnel peut vérifier votre carnet et discuter des rappels pertinents.",
  'https://sante.gouv.fr/prevention-en-sante/preserver-sa-sante/calendrier-vaccinal'),
 ('colorectal','Dépistage du cancer colorectal',"Le programme organisé concerne généralement les 50–74 ans à risque moyen. Selon votre histoire, le suivi peut être différent.",
  'https://www.ameli.fr/assure/sante/themes/cancer-colorectal/cancer-colorectal-depistage'),
 ('sein','Dépistage du cancer du sein',"Un programme existe pour les femmes de 50 à 74 ans à risque moyen. L'éligibilité personnelle doit être confirmée.",
  'https://www.ameli.fr/assure/sante/themes/cancer-sein/depistage-organise-50-74-ans'),
 ('col','Dépistage du col de l’utérus',"Un suivi existe entre 25 et 65 ans pour les personnes concernées ; le type de test varie notamment avec l'âge.",
  'https://www.ameli.fr/assure/sante/themes/cancer-col-uterus/depistage-organise-cancer-col-uterus'),
 ('prostate','Santé de la prostate',"Il n'existe pas de dépistage PSA systématique recommandé pour toute la population. Parlez-en avec votre médecin si nécessaire.",
  'https://www.has-sante.fr/jcms/c_1623737/fr/detection-precoce-du-cancer-de-la-prostate'),
 ('bilan','Faire le point sur ma prévention',"Les bilans et la prévention se discutent avec un professionnel selon l'âge et les besoins.",
  'https://www.ameli.fr/assure/sante/mon-bilan-prevention')]

# Product taxonomy, deliberately NOT an official RPPS classification or authorization.
SPECIALTIES={
 'Médecine — spécialités':[
 'Allergologie','Anatomie et cytologie pathologiques','Anesthésie-réanimation',
 'Dermatologie et vénéréologie','Endocrinologie, diabétologie, nutrition',
 'Génétique médicale','Gériatrie','Gynécologie médicale','Hématologie',
 'Hépato-gastro-entérologie','Maladies infectieuses et tropicales',
 'Médecine cardiovasculaire','Médecine d’urgence','Médecine et santé au travail',
 'Médecine générale','Médecine intensive-réanimation','Médecine interne et immunologie clinique',
 'Médecine légale','Médecine nucléaire','Médecine physique et de réadaptation',
 'Médecine vasculaire','Néphrologie','Neurologie','Oncologie','Pédiatrie',
 'Pneumologie','Psychiatrie','Radiologie et imagerie médicale','Rhumatologie','Santé publique'],
 'Chirurgie — spécialités':[
 'Chirurgie maxillo-faciale','Chirurgie orale','Chirurgie orthopédique et traumatologique',
 'Chirurgie pédiatrique','Chirurgie plastique reconstructrice et esthétique',
 'Chirurgie thoracique et cardiovasculaire','Chirurgie vasculaire',
 'Chirurgie viscérale et digestive','Gynécologie-obstétrique',
 'Neurochirurgie','Ophtalmologie','Oto-rhino-laryngologie et chirurgie cervico-faciale','Urologie'],
 'Biologie médicale':['Biologie médicale'],
 'Autres métiers et parcours':[
 'Chirurgien-dentiste','Sage-femme','Pharmacien','Préparateur en pharmacie',
 'Infirmier diplômé d’État','Infirmier en pratique avancée','Infirmier anesthésiste',
 'Infirmier de bloc opératoire','Puériculteur','Aide-soignant',
 'Masseur-kinésithérapeute','Ergothérapeute','Psychomotricien',
 'Orthophoniste','Orthoptiste','Pédicure-podologue','Diététicien',
 'Manipulateur d’électroradiologie médicale','Technicien de laboratoire médical',
 'Audioprothésiste','Opticien-lunetier','Orthoprothésiste',
 'Psychologue','Psychothérapeute','Ostéopathe','Chiropracteur',
 'Ambulancier','Assistant dentaire','Assistant médical','Coordinateur de parcours']
}

VALID_SHARES={'glucose','vitals','labs','meds'}


def now():return datetime.now(timezone.utc)
def iso():return now().isoformat()

def init_experience():
    with db.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS hb_vaccines(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),name TEXT NOT NULL,
            administered_on TEXT,source TEXT NOT NULL,status TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hb_prevention(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'a_discuter',note TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,UNIQUE(patient_id,key));
        CREATE TABLE IF NOT EXISTS hb_wellbeing(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),author_id TEXT NOT NULL REFERENCES portal_users(id),
            category TEXT NOT NULL,note TEXT NOT NULL,recorded_on TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hb_slots(id TEXT PRIMARY KEY,doctor_id TEXT NOT NULL REFERENCES portal_users(id),starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,location TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open');
        CREATE UNIQUE INDEX IF NOT EXISTS hb_slot_unique_doctor_start ON hb_slots(doctor_id,starts_at);
        CREATE TABLE IF NOT EXISTS hb_appointments(id TEXT PRIMARY KEY,slot_id TEXT NOT NULL REFERENCES hb_slots(id),
            patient_id TEXT NOT NULL REFERENCES patients(id),scope TEXT NOT NULL,reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'booked',created_at TEXT NOT NULL,revoked_at TEXT);
        CREATE INDEX IF NOT EXISTS hb_appointments_patient ON hb_appointments(patient_id,status);
        CREATE UNIQUE INDEX IF NOT EXISTS hb_single_live_booking ON hb_appointments(slot_id) WHERE status='booked';
        ''')
        # Content starts empty; the sample demo supports adding synthetic records interactively.


def _check(user,pid,permission):
    if not portal.can(user,pid,permission):raise PermissionError('Accès non autorisé')


def story(user,pid):
    if not portal.scopes(user,pid):raise PermissionError('Dossier non autorisé')
    obs=portal.visible_obs(user,pid)
    grouped={}
    for o in obs:grouped.setdefault(o['code'],[]).append(o)
    cards=[]
    for code,items in grouped.items():
        items.sort(key=lambda o:o['measured_at'])
        recent=items[-1]
        title,definition=METRICS.get(code,(recent['label'],"Cette donnée a été relevée lors d'un examen ou d'une mesure."))
        # No clinical comparisons; differing contexts (fasting etc.) cannot be inferred to be equivalent.
        cards.append({'code':code,'title':title,'explanation':definition,'value':recent['value'],'unit':recent['unit'],
                      'measured_at':recent['measured_at'],'source_id':recent['source_id'],'status':recent['status'],
                      'measure_count':len(items),'context':recent.get('context') or '',
                      'sentence':f"Vous avez {len(items)} mesure(s) enregistrée(s) pour ce sujet. La plus récente date du {recent['measured_at'][:10]}."})
    cards.sort(key=lambda d:d['measured_at'],reverse=True)
    receipt_count=len({o['source_id'] for o in obs})
    return {'title':'Mon histoire de santé, en clair','intro':"Ce dossier raconte ce qui a été mesuré, quand et d'où vient l'information. Il ne dit pas à lui seul si vous êtes malade ou en bonne santé.",
            'summary':f"{len(obs)} résultats visibles, sur {len(grouped)} sujets, issus de {receipt_count} sources consultables selon vos droits.",
            'cards':cards,'disclaimer':'Ces explications sont pédagogiques, sans diagnostic, seuil médical ou interprétation individuelle.'}


def vaccinations(user,pid):
    _check(user,pid,'vaccines')
    with db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM hb_vaccines WHERE patient_id=? ORDER BY administered_on DESC',(pid,))]


def add_vaccine(user,pid,name,date_value,source,status):
    if user['role']!='patient' or user['patient_id']!=pid:raise PermissionError('Saisie réservée au patient fictif')
    if status not in {'declare','incertain'}:raise ValueError('Statut incorrect')
    if date_value:
        try:datetime.strptime(date_value,'%Y-%m-%d')
        except ValueError:raise ValueError('Date invalide')
    with db.connect() as c:c.execute('INSERT INTO hb_vaccines VALUES(?,?,?,?,?,?,?,?)',
       (str(uuid4()),pid,name[:120],date_value,source[:160],status,user['id'],iso()))
    portal.log(user,pid,'add_vaccine')


def prevention(user,pid):
    _check(user,pid,'prevention')
    with db.connect() as c:stored={r['key']:dict(r) for r in c.execute('SELECT * FROM hb_prevention WHERE patient_id=?',(pid,))}
    return [{'key':k,'title':title,'description':desc,'reference':url,'status':stored.get(k,{}).get('status','inconnu'),
             'note':stored.get(k,{}).get('note',''),'rule_version':'catalogue-pedagogique-2026-v1',
             'warning':'Piste à discuter, pas une convocation ni une décision médicale.'} for k,title,desc,url in PREVENTION_LIBRARY]


def mark_prevention(user,pid,key,status,note):
    if user['role']!='patient' or user['patient_id']!=pid:raise PermissionError('Modification réservée au patient')
    if key not in {x[0] for x in PREVENTION_LIBRARY}:raise ValueError('Rubrique inconnue')
    if status not in {'inconnu','a_discuter','programme','realise','non_concerne'}:raise ValueError('Statut invalide')
    with db.connect() as c:c.execute('''INSERT INTO hb_prevention VALUES(?,?,?,?,?,?) ON CONFLICT(patient_id,key)
      DO UPDATE SET status=excluded.status,note=excluded.note,updated_at=excluded.updated_at''',
      (str(uuid4()),pid,key,status,note[:180],iso()))
    portal.log(user,pid,'prevention_update')


def wellbeing(user,pid):
    _check(user,pid,'wellbeing')
    if user['role'] not in {'patient','family'}:raise PermissionError('Journal personnel privé')
    with db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM hb_wellbeing WHERE patient_id=? ORDER BY recorded_on DESC LIMIT 90',(pid,))]


def add_wellbeing(user,pid,category,note,recorded_on):
    if user['role']!='patient' or user['patient_id']!=pid:raise PermissionError('Journal réservé au patient')
    if category not in {'sommeil','activite','humeur','douleur','energie','autre'}:raise ValueError('Rubrique inconnue')
    try:datetime.strptime(recorded_on,'%Y-%m-%d')
    except ValueError:raise ValueError('Date incorrecte')
    with db.connect() as c:c.execute('INSERT INTO hb_wellbeing VALUES(?,?,?,?,?,?,?)',
      (str(uuid4()),pid,user['id'],category,note[:600],recorded_on,iso()))
    portal.log(user,pid,'wellbeing_update')


def slots(user):
    # All users may see the nonclinical *available time slots* of fictitious providers.
    with db.connect() as c:return [dict(r) for r in c.execute('''SELECT s.*,u.name AS provider,u.role AS provider_role FROM hb_slots s JOIN portal_users u ON u.id=s.doctor_id
      WHERE s.status='open' AND s.starts_at>? ORDER BY s.starts_at LIMIT 100''',(iso(),))]


def add_slot(user,start,duration,location):
    if user['role'] not in {'doctor','dentist','nurse','optician','radiologist','podiatrist','orthotist'}:raise PermissionError('Ce métier ne gère pas de créneaux')
    try:dt=datetime.fromisoformat(start.replace('Z','+00:00'))
    except ValueError:raise ValueError('Date invalide')
    if not dt.tzinfo or dt.astimezone(timezone.utc)<=now():raise ValueError('Date future avec fuseau requise')
    if duration not in {20,30,45,60}:raise ValueError('Durée invalide')
    dt=dt.astimezone(timezone.utc)
    end=dt+timedelta(minutes=duration)
    with db.connect() as c:
        collision=c.execute('''SELECT 1 FROM hb_slots WHERE doctor_id=? AND status IN ('open','booked')
          AND starts_at<? AND ends_at>?''',(user['id'],end.isoformat(),dt.isoformat())).fetchone()
        if collision:raise ValueError('Créneau indisponible')
        c.execute('INSERT INTO hb_slots VALUES(?,?,?,?,?,?)',(str(uuid4()),user['id'],dt.isoformat(),end.isoformat(),location[:100],'open'))


def book(user,slot_id,reason,selected):
    if user['role']!='patient' or not user['patient_id']:raise PermissionError('Réservation réservée au patient fictif')
    if not isinstance(selected,list) or any(s not in VALID_SHARES for s in selected):raise ValueError('Partage inconnu')
    with db.connect() as c:
        row=c.execute('SELECT * FROM hb_slots WHERE id=?',(slot_id,)).fetchone()
        if not row or row['status']!='open' or row['starts_at']<=iso():raise ValueError('Créneau déjà pris ou expiré')
        updated=c.execute("UPDATE hb_slots SET status='booked' WHERE id=? AND status='open'",(slot_id,))
        if updated.rowcount!=1:raise ValueError('Créneau déjà réservé')
        aid=str(uuid4())
        c.execute('INSERT INTO hb_appointments VALUES(?,?,?,?,?,?,?,NULL)',
          (aid,slot_id,user['patient_id'],json.dumps(sorted(set(selected))),reason[:180],'booked',iso()))
    portal.log(user,user['patient_id'],'appointment_booked')
    return aid


def cancel(user,appointment_id):
    with db.connect() as c:
        r=c.execute('''SELECT a.*,s.doctor_id FROM hb_appointments a JOIN hb_slots s ON s.id=a.slot_id WHERE a.id=?''',(appointment_id,)).fetchone()
        if not r:raise ValueError('Rendez-vous introuvable')
        is_owner=user['role']=='patient' and user['patient_id']==r['patient_id']
        is_doctor=user['role'] in {'doctor','dentist','nurse','optician','radiologist','podiatrist','orthotist'} and user['id']==r['doctor_id']
        if not (is_owner or is_doctor):raise PermissionError('Accès refusé')
        c.execute("UPDATE hb_appointments SET status='cancelled',revoked_at=? WHERE id=?",(iso(),appointment_id))
        c.execute("UPDATE hb_slots SET status='open' WHERE id=? AND starts_at>?",(r['slot_id'],iso()))
    portal.log(user,r['patient_id'],'appointment_cancelled')


def list_appointments(user,pid=None):
    with db.connect() as c:
        if user['role'] in {'doctor','dentist','nurse','optician','radiologist','podiatrist','orthotist'}:
            rows=c.execute('''SELECT a.*,s.doctor_id,s.starts_at,s.ends_at,s.location,u.name AS provider,p.name AS patient_name
               FROM hb_appointments a JOIN hb_slots s ON s.id=a.slot_id JOIN portal_users u ON u.id=s.doctor_id
               JOIN patients p ON p.id=a.patient_id WHERE s.doctor_id=? ORDER BY s.starts_at DESC''',(user['id'],)).fetchall()
        else:
            if not pid or not portal.can(user,pid,'appointments'):raise PermissionError('Agenda non autorisé')
            rows=c.execute('''SELECT a.*,s.doctor_id,s.starts_at,s.ends_at,s.location,u.name AS provider,p.name AS patient_name
                FROM hb_appointments a JOIN hb_slots s ON s.id=a.slot_id JOIN portal_users u ON u.id=s.doctor_id
                JOIN patients p ON p.id=a.patient_id WHERE a.patient_id=? ORDER BY s.starts_at DESC''',(pid,)).fetchall()
    return [{**dict(r),'scope':json.loads(r['scope'])} for r in rows]


def appointment_scopes(user,pid):
    if user['role']!='doctor':return set()
    # J-7 until J+1, scoped to the specific doctor; revoked immediately on cancellation.
    with db.connect() as c:
        rows=c.execute('''SELECT a.scope,s.starts_at,s.ends_at FROM hb_appointments a JOIN hb_slots s ON s.id=a.slot_id
          WHERE a.patient_id=? AND s.doctor_id=? AND a.status='booked' AND a.revoked_at IS NULL''',(pid,user['id'])).fetchall()
    granted=set();t=now()
    for r in rows:
        start=datetime.fromisoformat(r['starts_at'])-timedelta(days=7)
        end=datetime.fromisoformat(r['ends_at'])+timedelta(days=1)
        if start<=t<=end:granted.update(json.loads(r['scope']))
    return granted


def appointment_patient_ids(user):
    if user['role']!='doctor':return set()
    with db.connect() as c:
        rows=c.execute('''SELECT DISTINCT a.patient_id FROM hb_appointments a JOIN hb_slots s ON s.id=a.slot_id
           WHERE s.doctor_id=? AND a.status='booked' AND a.revoked_at IS NULL''',(user['id'],)).fetchall()
    return {r['patient_id'] for r in rows if appointment_scopes(user,r['patient_id'])}


def brief(user,appointment_id):
    with db.connect() as c:
        r=c.execute('''SELECT a.*,s.doctor_id,s.starts_at FROM hb_appointments a JOIN hb_slots s ON s.id=a.slot_id WHERE a.id=?''',(appointment_id,)).fetchone()
    if not r or r['status']!='booked' or r['revoked_at']:raise PermissionError('Préparation indisponible')
    if user['role']!='doctor' or user['id']!=r['doctor_id']:raise PermissionError('Seul le praticien du rendez-vous')
    if not appointment_scopes(user,r['patient_id']):raise PermissionError('Hors fenêtre de partage ou aucun thème partagé')
    allowed=set(json.loads(r['scope']))
    obs=[o for o in portal.visible_obs(user,r['patient_id']) if portal.MEASURE_SCOPES.get(o['code'],'labs') in allowed]
    meds=portal.list_meds(user,r['patient_id']) if 'meds' in allowed else []
    # If doctor also has broad standing grant, enforce this appointment-specific consent on the brief.
    p=db.patient_detail(r['patient_id'])
    return {'appointment_id':appointment_id,'patient':p['name'],'starts_at':r['starts_at'],
            'motif':r['reason'],'shared_categories':sorted(allowed),'observations':obs[-40:],'medications':meds,
            'disclaimer':'Préparation factuelle de démonstration ; ne constitue pas un diagnostic.'}


def purge_expired_experience():
    """Demo-only best effort cleanup on startup; no production retention compliance claim."""
    cutoff=(now()-timedelta(days=db.RETENTION_DAYS)).isoformat()
    with db.connect() as c:
        c.execute('DELETE FROM hb_wellbeing WHERE created_at<?',(cutoff,))
        c.execute('DELETE FROM hb_vaccines WHERE created_at<?',(cutoff,))
        c.execute('DELETE FROM hb_prevention WHERE updated_at<?',(cutoff,))
        c.execute('DELETE FROM hb_appointments WHERE created_at<?',(cutoff,))
        c.execute('DELETE FROM hb_slots WHERE ends_at<? AND id NOT IN (SELECT slot_id FROM hb_appointments)',(cutoff,))
