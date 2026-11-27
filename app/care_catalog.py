"""Catalog of demo care pathways, not official legal credentialing.

Specialty labels are the product's November-2026 planning inventory and are
not a substitute for the versioned ANS/RPPS nomenclature. Imaging is a
capability, not a recommendation to order an exam.
"""
from __future__ import annotations

CARE_TYPES={
 'orientation': dict(label='Orientation / demande d’avis (non prescriptive)', provider_role='doctor', kind='referral', proof='Message d’orientation', outputs=['Orientation documentaire'], images=[], longitudinal='Consultations et observations du parcours'),
 'optical': dict(label='Lunettes & vision', provider_role='optician', kind='vision', proof='Ordonnance optique structurée', outputs=['Prescription de correction','Bon de commande','Avis de disponibilité','Mesures de correction'], images=['Ordonnance optique importée','Imagerie ophtalmologique si concernée'], longitudinal='Correction, équipement, dates de renouvellement'),
 'imaging': dict(label='Radiologie & imagerie', provider_role='radiologist', kind='imaging', proof='Demande d’examen d’imagerie', outputs=['Compte rendu','Images DICOM','Images et fichiers associés'], images=['Radiographie','Scanner','IRM','Échographie','Mammographie'], longitudinal='Examens, sites anatomiques et comptes rendus, comparés sans conclure automatiquement'),
 'dental': dict(label='Dentaire', provider_role='dentist', kind='dental', proof='Demande de soins dentaires', outputs=['Compte rendu de soins','Plan de traitement','Photographies et radiographies'], images=['Panoramique dentaire','Rétro-alvéolaire','CBCT','Photographie buccale'], longitudinal='Historique des soins, dents concernées et imagerie'),
 'podiatry': dict(label='Pieds & semelles', provider_role='podiatrist', kind='podiatry', proof='Demande de bilan podologique', outputs=['Bilan podologique','Empreinte et analyse de posture','Suivi des semelles'], images=['Empreinte plantaire','Photographies d’appui','Scan 3D du pied'], longitudinal='Mesures, posture déclarée par le professionnel, semelles et suivi comparatif'),
 'orthotics': dict(label='Orthèses & prothèses', provider_role='orthotist', kind='device', proof='Prescription d’appareillage', outputs=['Mesures d’ajustement','Dossier d’appareillage','Livraison et contrôle'], images=['Photographie','Scan 3D','Empreinte selon équipement'], longitudinal='Dates d’ajustement, tailles, entretien et évolution'),
}

# 44 product-category labels based on the requested medical training specialties.
# {name}|{area}|{imaging flag: yes/possible/rare}|{usual workflow types}; examples, not clinical guidance.
_MEDICAL_LINES='''
Chirurgie maxillo-faciale|chirurgie|yes|imaging,dental,orthotics
Chirurgie orale|chirurgie|yes|imaging,dental
Chirurgie orthopédique et traumatologique|chirurgie|yes|imaging,orthotics,podiatry
Chirurgie pédiatrique|chirurgie|yes|imaging,orthotics
Chirurgie plastique reconstructrice et esthétique|chirurgie|possible|imaging,orthotics
Chirurgie thoracique et cardiovasculaire|chirurgie|yes|imaging
Chirurgie vasculaire|chirurgie|yes|imaging,orthotics
Chirurgie viscérale et digestive|chirurgie|yes|imaging
Gynécologie obstétrique|chirurgie|yes|imaging
Neurochirurgie|chirurgie|yes|imaging,orthotics
Ophtalmologie|chirurgie|yes|imaging,optical
ORL et chirurgie cervico-faciale|chirurgie|yes|imaging,orthotics
Urologie|chirurgie|yes|imaging
Allergologie|médecine|possible|imaging
Anatomie et cytologie pathologiques|médecine|yes|imaging
Anesthésie-réanimation|médecine|yes|imaging
Dermatologie|médecine|yes|imaging
Endocrinologie-diabétologie-nutrition|médecine|possible|imaging,podiatry
Génétique médicale|médecine|possible|imaging
Gériatrie|médecine|possible|imaging,orthotics,podiatry
Gynécologie médicale|médecine|yes|imaging
Hématologie|médecine|yes|imaging
Hépato-gastro-entérologie|médecine|yes|imaging
Maladies infectieuses et tropicales|médecine|possible|imaging
Médecine cardiovasculaire|médecine|yes|imaging
Médecine d’urgence|médecine|yes|imaging
Médecine et santé au travail|médecine|possible|imaging
Médecine générale|médecine|possible|imaging,optical,dental,podiatry,orthotics
Médecine intensive-réanimation|médecine|yes|imaging
Médecine interne et immunologie clinique|médecine|possible|imaging
Médecine légale|médecine|yes|imaging
Médecine nucléaire|médecine|yes|imaging
Médecine physique et de réadaptation|médecine|yes|imaging,orthotics,podiatry
Médecine vasculaire|médecine|yes|imaging,orthotics
Néphrologie|médecine|yes|imaging
Neurologie|médecine|yes|imaging,orthotics
Oncologie|médecine|yes|imaging
Pédiatrie|médecine|possible|imaging,optical,orthotics
Pneumologie|médecine|yes|imaging
Psychiatrie|médecine|possible|imaging
Radiologie et imagerie médicale|médecine|yes|imaging
Rhumatologie|médecine|yes|imaging,orthotics,podiatry
Santé publique|médecine|rare|
Biologie médicale|biologie|possible|imaging
'''.strip().splitlines()

# Additional professions and care roles, with typical deliverables.
_OTHER_LINES='''
Chirurgien-dentiste|dentaire|yes|dental,imaging
Orthodontiste|dentaire|yes|dental,imaging
Sage-femme|maternité|yes|imaging
Pharmacien d’officine|pharmacie|rare|
Pharmacien hospitalier|pharmacie|rare|
Préparateur en pharmacie|pharmacie|rare|
Préparateur en pharmacie hospitalière|pharmacie|rare|
Physicien médical|technique|yes|imaging
Infirmier diplômé d’État|soins|possible|
Infirmier anesthésiste (IADE)|soins|possible|
Infirmier de bloc opératoire (IBODE)|soins|possible|
Infirmier puériculteur|soins|possible|
Infirmier en pratique avancée (IPA)|soins|possible|
Masseur-kinésithérapeute|rééducation|possible|imaging,orthotics
Pédicure-podologue|rééducation|yes|podiatry,orthotics
Ergothérapeute|rééducation|possible|orthotics
Psychomotricien|rééducation|possible|orthotics
Orthophoniste|rééducation|rare|
Orthoptiste|rééducation|yes|optical,imaging
Diététicien|rééducation|rare|
Manipulateur en électroradiologie médicale|technique|yes|imaging
Technicien de laboratoire médical|technique|possible|
Audioprothésiste|appareillage|possible|orthotics
Opticien-lunetier|appareillage|possible|optical
Orthopédiste-orthésiste|appareillage|yes|orthotics
Orthoprothésiste|appareillage|yes|orthotics
Podo-orthésiste|appareillage|yes|podiatry,orthotics
Épithésiste|appareillage|yes|orthotics
Oculariste|appareillage|yes|orthotics,optical
Aide-soignant|soins|rare|
Auxiliaire de puériculture|soins|rare|
Ambulancier|transport|rare|
Assistant dentaire|dentaire|yes|dental
Assistant de régulation médicale|coordination|rare|
Psychologue|psychologie|rare|
Psychothérapeute|psychologie|rare|
Ostéopathe|approches manuelles|possible|
Chiropracteur|approches manuelles|possible|
Conseiller en génétique|génétique|possible|
Assistant médical|coordination|rare|
Coordonnateur de parcours|coordination|rare|
Éducateur en activité physique adaptée|activité physique|rare|
Secrétaire médico-administrative|coordination|rare|
'''.strip().splitlines()


def _make(lines,group):
    out=[]
    for n,line in enumerate(lines):
        name,area,imaging,kinds=line.split('|')
        paths=[x for x in kinds.split(',') if x]
        out.append(dict(code=f'{group}-{n+1:02}',name=name,group=group,domain=area,
                        imaging=imaging,journey_types=paths,
                        media_formats=['DICOM','JPEG','PNG','PDF'] if imaging=='yes' else (['JPEG','PNG','PDF'] if imaging=='possible' else []),
                        workflows=['documents','results','history','sharing']+(['imaging'] if imaging!='rare' else [])+(['orders'] if paths else []),
                        regulation_note='Fonctions possibles, droits non déduits de la spécialité; vérifier la situation individuelle.'))
    return out

MEDICAL_SPECIALTIES=_make(_MEDICAL_LINES,'medical')
OTHER_PROFESSIONS=_make(_OTHER_LINES,'profession')
ALL_SPECIALTIES=MEDICAL_SPECIALTIES+OTHER_PROFESSIONS
INDEX={r['code']:r for r in ALL_SPECIALTIES}
assert len(MEDICAL_SPECIALTIES)==44,len(MEDICAL_SPECIALTIES)

def public_catalog(group=None):
    rows=ALL_SPECIALTIES if not group else [r for r in ALL_SPECIALTIES if r['group']==group]
    return {'count':len(rows),'medical_count':len(MEDICAL_SPECIALTIES),'profession_count':len(OTHER_PROFESSIONS),
            'items':rows,'care_types':CARE_TYPES,
            'limitations':['Catégories produit, pas preuve de titre ni d’habilitation RPPS','Une image n’est jamais interprétée automatiquement','Ajour n’a aucun module de facturation/Assurance maladie']}
