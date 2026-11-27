"""Versioned, non-diagnostic medical information catalogue for synthetic Healthberg.

The catalogue describes how to PRESENT previously recorded information. It is not
an order set, a clinical recommendation, a risk model or an RPPS authorization list.
Specialty selection affects display priority, never data entitlement.
"""
from __future__ import annotations
from dataclasses import dataclass
from .terminology import METRIC_BY_CODE
from .experience import SPECIALTIES

CATALOG_VERSION = '2026-11-demo-v1'

@dataclass(frozen=True)
class CatalogMetric:
    code: str
    title: str
    domain: str
    explanation: str
    unit: str = ''
    kind: str = 'measurement'


def metric(code, title, domain, simple, unit=''):
    return CatalogMetric(code, title, domain, simple, unit)

# Only the codes also defined in terminology.py can be entered and graphed as numbers.
# Other catalogue entries describe the future scope, never imply a result exists.
CATALOG = [
 metric('systolic','Tension (premier chiffre)','Cœur et circulation','La pression du sang lorsque le cœur se contracte. Elle se lit avec le second chiffre.','mmHg'),
 metric('diastolic','Tension (deuxième chiffre)','Cœur et circulation','La pression du sang lorsque le cœur se relâche. Elle se lit avec le premier chiffre.','mmHg'),
 metric('pulse','Pouls','Cœur et circulation','Combien de battements du cœur sont mesurés en une minute.','bpm'),
 metric('spo2','Saturation en oxygène','Poumons et respiration','Une mesure de la part de l’oxygène transporté par le sang.','%'),
 metric('respiratory_rate','Fréquence respiratoire','Poumons et respiration','Combien de respirations sont comptées en une minute.','/min'),
 metric('temperature','Température','Signes vitaux','Température du corps au moment de la mesure.','°C'),
 metric('glucose','Glycémie','Diabète et métabolisme','La quantité de sucre dans le sang au moment de la mesure. Le contexte, à jeun ou non, est important.','g/L'),
 metric('hba1c','HbA1c','Diabète et métabolisme','Un résultat sanguin donnant une idée de la glycémie sur les derniers mois. Ce n’est pas une mesure instantanée.','%'),
 metric('weight','Poids','Nutrition et croissance','Poids constaté à une date donnée.','kg'),
 metric('height','Taille','Nutrition et croissance','Taille mesurée, utile notamment pour suivre la croissance.','cm'),
 metric('bmi_reported','IMC rapporté','Nutrition et croissance','Indice indiqué par une source médicale. Healthberg ne le calcule pas.','kg/m²'),
 metric('cholesterol','Cholestérol total','Cœur et circulation','Quantité totale de cholestérol mesurée dans le sang.','g/L'),
 metric('ldl','Cholestérol LDL','Cœur et circulation','Une fraction du cholestérol, mesurée lors du bilan lipidique.','g/L'),
 metric('hdl','Cholestérol HDL','Cœur et circulation','Une autre fraction du cholestérol, mesurée lors du bilan lipidique.','g/L'),
 metric('triglycerides','Triglycérides','Cœur et circulation','Une forme de graisse mesurée dans le sang.','g/L'),
 metric('egfr','DFG rapporté','Reins','Une estimation du fonctionnement rénal, déjà calculée et rapportée par le laboratoire.','mL/min/1,73m²'),
 metric('creatinine','Créatinine','Reins','Une substance dont le dosage aide les soignants à évaluer les reins.','mg/L'),
 metric('albuminuria','Albuminurie','Reins','Quantité d’albumine retrouvée dans les urines, selon le test réalisé.','mg/L'),
 metric('potassium','Potassium','Sang et électrolytes','Un minéral mesuré dans le sang.','mmol/L'),
 metric('sodium','Sodium','Sang et électrolytes','Un minéral mesuré dans le sang.','mmol/L'),
 metric('hemoglobin','Hémoglobine','Sang et électrolytes','Une protéine des globules rouges qui transporte l’oxygène.','g/dL'),
 metric('platelets','Plaquettes','Sang et électrolytes','Cellules du sang participant notamment à la coagulation.','G/L'),
 metric('leukocytes','Globules blancs','Sang et électrolytes','Cellules participant aux défenses de l’organisme.','G/L'),
 metric('ferritin','Ferritine','Sang et électrolytes','Un marqueur des réserves de fer de l’organisme.','µg/L'),
 metric('crp','CRP','Inflammation et infection','Une protéine mesurée dans certains bilans de l’inflammation.','mg/L'),
 metric('tsh','TSH','Hormones','Une hormone utilisée pour explorer le fonctionnement de la thyroïde.','mUI/L'),
 metric('alat','ALAT','Foie et digestion','Une enzyme mesurée dans certains bilans du foie.','UI/L'),
 metric('asat','ASAT','Foie et digestion','Une autre enzyme souvent mesurée dans les bilans du foie.','UI/L'),
 metric('inr','INR rapporté','Coagulation','Un indice de coagulation communiqué par un laboratoire.',''),
 metric('fevg','Fraction d’éjection rapportée','Cœur et circulation','Une valeur fournie par l’examen du cœur ; Healthberg ne la calcule pas.','%'),
 metric('psa','PSA','Urologie','Une protéine mesurée lors de certains examens prescrits et interprétés par un médecin.','ng/mL'),
 metric('vems','VEMS rapporté','Poumons et respiration','Quantité d’air expirée dans la première seconde d’un examen respiratoire.','L'),
 metric('pain','Douleur déclarée','Bien-être et mobilité','Votre ressenti à une date donnée, s’il a été consigné.',''),
 metric('mobility','Mobilité et autonomie','Bien-être et mobilité','Observations sur la marche, l’équilibre et les gestes du quotidien.',''),
 metric('sleep','Sommeil','Bien-être et mobilité','Durée et qualité du sommeil déclarées ou mesurées selon la source.',''),
 metric('mood','Humeur et ressenti','Bien-être et mobilité','Ressenti du patient, qui peut rester privé.',''),
 metric('ecg','ECG','Cœur et circulation','Examen enregistrant l’activité électrique du cœur.',''),
 metric('imaging','Imagerie médicale','Imagerie et examens','Radiographie, scanner, IRM, échographie et leurs comptes rendus.',''),
 metric('histology','Anatomopathologie','Imagerie et examens','Analyse d’un prélèvement et compte rendu du spécialiste.',''),
 metric('hearing','Audiogramme','Yeux et audition','Examen de l’audition, avec résultats et dates.',''),
 metric('vision','Acuité visuelle','Yeux et audition','Résultat d’un examen de la vision.',''),
 metric('dental','Suivi dentaire','Santé bucco-dentaire','Soins, examens et équipements dentaires.',''),
 metric('development','Développement de l’enfant','Enfance et maternité','Observations de suivi adaptées à l’âge de l’enfant.',''),
 metric('pregnancy','Suivi de grossesse','Enfance et maternité','Consultations, examens et événements de grossesse.',''),
 metric('oncology','Parcours oncologique','Parcours de soins','Examens, traitements et événements enregistrés dans le suivi d’un cancer.',''),
 metric('surgery','Interventions chirurgicales','Parcours de soins','Dates, comptes rendus et suites des interventions pratiquées.',''),
 metric('hospital','Hospitalisations','Parcours de soins','Dates et comptes rendus des séjours à l’hôpital.',''),
 metric('allergy','Allergies déclarées','Traitements et sécurité','Substances et réactions signalées ou documentées.',''),
 metric('medication','Traitements','Traitements et sécurité','Ordonnances, délivrances et prises déclarées ne sont pas la même chose.',''),
 metric('vaccination','Vaccins','Prévention','Vaccins documentés, dates, doses et justificatifs disponibles.',''),
 metric('screening','Dépistages','Prévention','Examens de prévention effectués, programmés ou à discuter, sans présumer de leur nécessité.',''),
 metric('appointment','Rendez-vous','Parcours de soins','Consultations programmées et préparation d’une visite.',''),
]
METRICS_BY_CODE={m.code:m for m in CATALOG}

# Curated specialty presentation priorities. These NEVER increase access rights.
COMMON=['systolic','diastolic','pulse','glucose','hba1c','weight','creatinine','egfr','medication','allergy','vaccination','appointment']
SPECIFIC={
 'Médecine générale': COMMON+['cholesterol','ldl','hdl','triglycerides','screening','hospital','surgery','pain','sleep'],
 'Médecine cardiovasculaire':['systolic','diastolic','pulse','fevg','ecg','cholesterol','ldl','hdl','triglycerides','weight','potassium','creatinine','medication','hospital'],
 'Endocrinologie, diabétologie, nutrition':['glucose','hba1c','weight','bmi_reported','tsh','creatinine','egfr','albuminuria','ldl','hdl','medication','vision'],
 'Néphrologie':['creatinine','egfr','albuminuria','potassium','sodium','systolic','diastolic','hemoglobin','medication'],
 'Pneumologie':['spo2','respiratory_rate','vems','pulse','imaging','sleep','medication'],
 'Neurologie':['mobility','sleep','pain','imaging','medication','hospital'],
 'Oncologie':['oncology','histology','imaging','hemoglobin','leukocytes','platelets','weight','pain','medication'],
 'Hématologie':['hemoglobin','leukocytes','platelets','ferritin','inr','histology','medication'],
 'Psychiatrie':['mood','sleep','medication','appointment','pain'],
 'Gériatrie':['mobility','weight','pain','sleep','systolic','diastolic','hospital','medication','vaccination'],
 'Pédiatrie':['height','weight','development','vaccination','appointment'],
 'Gynécologie médicale':['pregnancy','screening','imaging','medication'],
 'Gynécologie-obstétrique':['pregnancy','imaging','systolic','diastolic','hospital','surgery'],
 'Urologie':['psa','creatinine','egfr','imaging','surgery','medication'],
 'Rhumatologie':['pain','mobility','crp','imaging','medication'],
 'Dermatologie et vénéréologie':['imaging','histology','allergy','medication'],
 'Hépato-gastro-entérologie':['alat','asat','inr','albuminuria','screening','imaging','histology','medication'],
 'Médecine intensive-réanimation':['systolic','diastolic','pulse','spo2','respiratory_rate','temperature','creatinine','sodium','potassium','hospital','medication'],
 'Médecine d’urgence':['systolic','diastolic','pulse','spo2','temperature','allergy','medication','hospital'],
 'Biologie médicale':['glucose','hba1c','creatinine','egfr','cholesterol','ldl','hdl','hemoglobin','potassium','sodium','crp','tsh'],
 'Ophtalmologie':['vision','imaging','glucose','hba1c','medication','surgery'],
 'Oto-rhino-laryngologie et chirurgie cervico-faciale':['hearing','imaging','surgery','medication'],
 'Anesthésie-réanimation':['allergy','medication','systolic','diastolic','pulse','spo2','hospital','surgery'],
 'Radiologie et imagerie médicale':['imaging','surgery','allergy','medication'],
 'Médecine et santé au travail':['mobility','sleep','appointment','prevention'],
}
CHIRURGICAL=['allergy','medication','surgery','hospital','imaging','pain','mobility','hemoglobin','creatinine','appointment']

# Clinical workflows cannot be reduced to numeric KPI. "Not available" is not a clinical alert.
WORKFLOWS={
 'consultation': ['Motif de consultation', 'Antécédents documentés', 'Traitements et allergies pertinents', 'Examens disponibles', 'Questions du patient'],
 'surgery': ['Avant : indication et bilan documentés', 'Pendant : compte rendu de l’intervention', 'Après : douleur, cicatrisation, mobilité et suivi'],
 'laboratory': ['Prélèvement et date', 'Méthode et unité', 'Validation biologique', 'Compte rendu et rectificatifs'],
 'nursing': ['Constantes', 'Plan de soins', 'Actes réalisés', 'Observations transmises au médecin'],
}

def specialties():
    # Medical DES only. Allied-health professions remain visible via /catalog/professions.
    return [x for group in ('Médecine — spécialités','Chirurgie — spécialités','Biologie médicale') for x in SPECIALTIES[group]]

def profile(specialty: str):
    if specialty not in specialties(): raise ValueError('Spécialité de démonstration inconnue')
    if specialty in SPECIFIC:priorities=SPECIFIC[specialty]
    elif specialty in SPECIALTIES['Chirurgie — spécialités']:priorities=CHIRURGICAL
    else:priorities=COMMON
    kind='surgery' if specialty in SPECIALTIES['Chirurgie — spécialités'] else ('laboratory' if specialty=='Biologie médicale' else 'consultation')
    return {'specialty':specialty,'priority':list(dict.fromkeys(p for p in priorities if p in METRICS_BY_CODE)),
            'workflow':WORKFLOWS[kind],
            'disclaimer':'Classement d’affichage fictif uniquement. Aucune recommandation, diagnostic ou autorisation supplémentaire.'}

def public_catalog():
    return {'version':CATALOG_VERSION,'metrics':[{'code':m.code,'label':m.title,'domain':m.domain,
       'simple':m.explanation,'unit':m.unit,'numeric_available':m.code in METRIC_BY_CODE} for m in CATALOG],
       'specialties':specialties(),
       'notice':'Données descriptives et non exhaustives ; aucun examen manquant ne signifie qu’il est nécessaire.'}

def map_for_patient(user,pid,active_specialty=None,secondary_specialty=None):
    from . import portal
    if not portal.scopes(user,pid): raise PermissionError('Dossier non autorisé')
    if user['role'] in ('lab','pharmacist'): raise PermissionError('Aucune mesure accessible à ce rôle dans cette démo')
    allowed_obs=portal.visible_obs(user,pid)
    by_code={}
    for row in allowed_obs:
        if row['code'] not in by_code or row['measured_at']>by_code[row['code']]['measured_at']:
            by_code[row['code']]=row
    # Non-numeric sections use existing, accessible workflow records only.
    # Their existence must never be treated as a clinical conclusion.
    known_narratives={}
    if portal.can(user,pid,'meds'):
        medications=portal.list_meds(user,pid)
        if medications:known_narratives['medication']=f'{len(medications)} mention(s) de traitement dans le dossier'
    from . import db
    with db.connect() as connection:
        if portal.can(user,pid,'vaccines'):
            count=connection.execute('SELECT COUNT(*) FROM hb_vaccines WHERE patient_id=?',(pid,)).fetchone()[0]
            if count:known_narratives['vaccination']=f'{count} vaccination(s) déclarée(s) ou documentée(s)'
        if portal.can(user,pid,'prevention'):
            count=connection.execute("SELECT COUNT(*) FROM hb_prevention WHERE patient_id=? AND status NOT IN ('inconnu','a_discuter')",(pid,)).fetchone()[0]
            if count:known_narratives['screening']=f'{count} élément(s) de prévention renseigné(s)'
        if portal.can(user,pid,'wellbeing'):
            for code,category in (('sleep','sommeil'),('mood','humeur'),('pain','douleur')):
                count=connection.execute('SELECT COUNT(*) FROM hb_wellbeing WHERE patient_id=? AND category=?',(pid,category)).fetchone()[0]
                if count:known_narratives[code]=f'{count} note(s) personnelle(s) sur ce sujet'
    # Catalogue filtered by the same scope model as actual observations; no side-channel.
    visible=[]
    for m in CATALOG:
        category=portal.MEASURE_SCOPES.get(m.code,'labs') if m.kind=='measurement' else 'labs'
        if m.code in ('medication','allergy'):
            category='meds'
        elif m.code=='vaccination':category='vaccines'
        elif m.code=='screening':category='prevention'
        elif m.code=='appointment':category='appointments'
        elif m.code in ('sleep','mood','pain','mobility'): category='wellbeing'
        if not portal.can(user,pid,category):continue
        row=by_code.get(m.code)
        narrative=known_narratives.get(m.code)
        visible.append({'code':m.code,'title':m.title,'domain':m.domain,'explanation':m.explanation,
                        'unit':m.unit,'type':'number' if m.code in METRIC_BY_CODE else 'document_or_report',
                        'status':'measured' if row else ('documented' if narrative else 'not_recorded'),'summary':narrative,
                        'latest':({k:row.get(k) for k in ('value','unit','measured_at','source_id','status','context')} if row else None)})
    focus=profile(active_specialty) if user['role']=='doctor' and active_specialty else None
    focus_secondary=profile(secondary_specialty) if user['role']=='doctor' and secondary_specialty else None
    if focus:
        preferred=list(dict.fromkeys(focus['priority']+(focus_secondary['priority'] if focus_secondary else [])))
        priority={code:i for i,code in enumerate(preferred)}
        visible.sort(key=lambda x:(x['code'] not in priority,priority.get(x['code'],999),x['domain'],x['title']))
    elif user['role']=='patient':
        high={'glucose':0,'systolic':1,'diastolic':2,'hba1c':3,'pulse':4,'weight':5,'medication':6,'vaccination':7}
        visible.sort(key=lambda x:(x['code'] not in high,high.get(x['code'],999),x['domain'],x['title']))
    else:visible.sort(key=lambda x:(x['domain'],x['title']))
    return {'version':CATALOG_VERSION,'specialty':focus,'secondary_specialty':focus_secondary,'items':visible,
            'measured_count':sum(x['status']=='measured' for x in visible),
            'documented_count':sum(x['status']=='documented' for x in visible),
            'notice':'« Non renseigné » signifie seulement qu’aucune donnée accessible n’est enregistrée, pas qu’un examen est nécessaire.',
            'synthetic_only':True}
