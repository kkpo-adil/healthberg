"""Ajour v0.7 — synthetic-only connected health workflows."""
from __future__ import annotations
from .extraction import sample_date_options, report_conclusions
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4
import os
from math import isfinite

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import db, portal, experience, health_catalog, journeys, careflows, care_catalog, prescription_import, practice
from .extraction import parse_file, MAX_UPLOAD_BYTES
from .models import ImportConfirm
from .terminology import METRIC_BY_CODE

if os.getenv('HEALTHBERG_ENABLE_REAL_PATIENTS','false').lower()=='true':
    raise RuntimeError('REAL PATIENTS FORBIDDEN. Synthetic demo only.')

@asynccontextmanager
async def lifespan(_application):
    portal.init_portal();experience.init_experience();journeys.init_journeys();careflows.init_careflows();prescription_import.init();practice.init();journeys.purge_expired_journeys();careflows.purge();db.purge_expired();portal.purge_expired_portal();experience.purge_expired_experience()
    yield

app=FastAPI(title='Ajour — Parcours connectés',version='0.9.7',docs_url='/api/docs',redoc_url=None,lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
STATIC=Path(__file__).resolve().parents[1]/'static'
app.mount('/static',StaticFiles(directory=STATIC),name='static')
preview_sessions={}

@app.middleware('http')
async def local_demo_guard(request:Request,call_next):
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        return JSONResponse({'detail':'Origine externe interdite'},status_code=403)
    if request.url.path.startswith('/api/') and request.method in {'POST','PUT','PATCH','DELETE'} and request.headers.get('x-healthberg-action')!='demo':
        return JSONResponse({'detail':'En-tête d’action locale manquant'},status_code=403)
    result=await call_next(request)
    for key,value in {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"}.items():result.headers[key]=value
    return result

@app.get('/')
def home():return FileResponse(STATIC/'index.html')

@app.get('/api/health')
def health():return {'status':'synthetic-demo-only','version':'0.9.7','retention_days_provisional':db.RETENTION_DAYS,'real_data_allowed':False,'instance':os.getenv('AJOUR_INSTANCE_TOKEN','')}

class Login(BaseModel):
    email:str
    password:str

@app.get('/api/auth/accounts')
def accounts():
    # Only synthetic example identities; never production user enumeration.
    return [{**a,'role_name':portal.ROLES[a['role']]} for a in portal.list_demo_accounts()]

class DemoRegistration(BaseModel):
    role:str
    name:str=Field(min_length=3,max_length=70)
    synthetic_ack:bool=True
    birth_date:str=''
    address:str=''
    profession:str=''
    insurer:str=''
    member_test_id:str=''
    social_test_id:str=''
    phone:str=''
    entry_code:str=''

@app.post('/api/demo/accounts')
def create_demo_account(body:DemoRegistration):
    if not body.synthetic_ack:raise HTTPException(400,'Compte de démonstration requis')
    try:return portal.demo_register(body.role,body.name,body.model_dump())
    except ValueError as e:raise HTTPException(400,str(e))

@app.post('/api/auth/login')
def login(body:Login,response:Response):
    u=portal.authenticate(body.email,body.password)
    if not u:raise HTTPException(401,'Identifiants invalides')
    token=portal.new_session(u['id'])
    response.set_cookie('healthberg_demo_session',token,httponly=True,samesite='strict',secure=False,max_age=8*3600,path='/')
    return {'user':portal.public_user(u)}

@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    portal.revoke_session(request.cookies.get('healthberg_demo_session'))
    response.delete_cookie('healthberg_demo_session',path='/')
    return {'logged_out':True}


def current_user(request:Request):
    user=portal.session_user(request.cookies.get('healthberg_demo_session'))
    if not user:raise HTTPException(401,'Connectez-vous avec un compte de démonstration')
    return user


def check(user,pid,scope,write=False):
    if not db.patient_detail(pid):raise HTTPException(404,'Patient inconnu')
    if not portal.can(user,pid,scope,write):raise HTTPException(403,'Accès non autorisé pour ce rôle et ce patient')

@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    return {'user':portal.public_user(user),'patients':portal.visible_patients(user),'scopes':{p['id']:sorted(portal.scopes(user,p['id'])) for p in portal.visible_patients(user)},'roles':portal.ROLES}

@app.get('/api/patients')
def patients(user=Depends(current_user)):
    return portal.visible_patients(user)

class ProfileUpdate(BaseModel):
    birth_date:str=''
    address:str=''
    profession:str=''
    insurer:str=''
    member_test_id:str=''
    social_test_id:str=''
    phone:str=''
    entry_code:str=''

@app.get('/api/patients/{pid}/identity')
def identity_get(pid:str,user=Depends(current_user)):
    if user['role']=='patient' and user['patient_id']==pid or user['role']=='doctor' and portal.can(user,pid,'all'):
        return portal.get_patient_profile(pid)
    raise HTTPException(403,'Identité non accessible à ce compte')

@app.put('/api/patients/{pid}/identity')
def identity_update(pid:str,body:ProfileUpdate,user=Depends(current_user)):
    if user['role']!='patient' or user['patient_id']!=pid:
        raise HTTPException(403,'Seul le patient peut modifier son profil de démonstration')
    try:return portal.save_patient_profile(pid,body.model_dump())
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/patients/{pid}/overview')
def overview(pid:str,user=Depends(current_user)):
    if not portal.scopes(user,pid):raise HTTPException(403,'Dossier non autorisé')
    p=db.patient_detail(pid)
    if not p:raise HTTPException(404,'Patient introuvable')
    if user['role'] not in ('patient','doctor') or (user['role']=='doctor' and 'all' not in portal.scopes(user,pid)):
        p={key:p[key] for key in ('id','name','initials','age','synthetic') if key in p}
    obs=portal.visible_obs(user,pid)
    last={}
    for o in obs:
        if o['code'] not in last or o['measured_at']>last[o['code']]['measured_at']:last[o['code']]=o
    meds=portal.list_meds(user,pid)
    accessible_receipts=_visible_receipts(user,pid,obs,meds)
    # Labs see only identity necessary for their fictitious submissions.
    if user['role']=='lab':
        return {'patient':{'id':p['id'],'name':p['name'],'age':p['age'],'initials':p['initials'],'synthetic':1},'last_values':{},'observations':[],
                'medications':[],'receipts':[],'events':portal.events(user,pid),'notes':[],'tasks':[],'messages':[],
                'contacts':[], 'metrics':_permitted_metrics(user,pid),'role':user['role']}
    if user['role'] in ('patient','doctor') and (user['role']=='patient' or 'all' in portal.scopes(user,pid)):
        p['identity']=portal.get_patient_profile(pid)
    portal.log(user,pid,'read_overview')
    return {'patient':p,'last_values':last,'observations':obs,'findings':portal.visible_findings(user,pid),'document_pages':portal.visible_document_pages(user,pid),'medications':meds,'receipts':accessible_receipts,
            'events':portal.events(user,pid),'notes':portal.list_notes(user,pid),'tasks':portal.list_tasks(user,pid),
            'messages':portal.list_messages(user,pid),'contacts':portal.directory(user,pid) if portal.can(user,pid,'messages') else [],
            'metrics':_permitted_metrics(user,pid),'role':user['role'], 'scopes':sorted(portal.scopes(user,pid))}


def _permitted_metrics(user,pid):
    if user['role']=='lab':allowed=['glucose','hba1c','creatinine','egfr','cholesterol','ldl','hdl','triglycerides','hemoglobin','potassium','sodium','crp','tsh','ferritin','alat','asat','inr','psa','platelets','leukocytes','albuminuria']
    elif user['role']=='nurse':allowed=['glucose','systolic','diastolic','weight','pulse','spo2','temperature','respiratory_rate','height']
    elif user['role']=='pharmacist':allowed=[]
    else:allowed=[code for code in METRIC_BY_CODE if portal.can(user,pid,portal.MEASURE_SCOPES.get(code,'labs'))]
    return [{'code':code,'label':METRIC_BY_CODE[code].label,'unit':METRIC_BY_CODE[code].unit} for code in allowed]


def _visible_receipts(user,pid,obs=None,meds=None):
    if user['role']=='lab':return []
    obs=obs if obs is not None else portal.visible_obs(user,pid)
    meds=meds if meds is not None else portal.list_meds(user,pid)
    allowed={o['source_id'] for o in obs} | {m['source_id'] for m in meds if m.get('source_id')}
    allowed |= {f['source_id'] for f in portal.visible_findings(user,pid)}
    allowed |= {f['source_id'] for f in portal.visible_document_pages(user,pid)}
    return [r for r in db.list_receipts(pid) if r['id'] in allowed]

@app.get('/api/patients/{pid}/observations')
def observations(pid:str,code:str|None=None,user=Depends(current_user)):
    if not portal.scopes(user,pid):raise HTTPException(403,'Accès interdit')
    rows=portal.visible_obs(user,pid)
    return [r for r in rows if not code or r['code']==code]

@app.get('/api/patients/{pid}/receipts')
def receipts(pid:str,user=Depends(current_user)):
    if not portal.scopes(user,pid):raise HTTPException(403,'Accès interdit')
    return _visible_receipts(user,pid)

@app.get('/api/patients/{pid}/receipts/{rid}')
def receipt(pid:str,rid:str,user=Depends(current_user)):
    if not portal.scopes(user,pid):raise HTTPException(403,'Accès interdit')
    r=next((r for r in _visible_receipts(user,pid) if r['id']==rid),None)
    if not r:raise HTTPException(404,'Source inaccessible')
    portal.log(user,pid,'read_receipt')
    return r

class Measure(BaseModel):
    code:str
    value:float
    unit:str
    measured_at:str
    context:str=Field('',max_length=160)

@app.post('/api/patients/{pid}/measures')
def measure_submit(pid:str,body:Measure,user=Depends(current_user)):
    try:return portal.add_measure(user,pid,body.code,body.value,body.unit,body.measured_at,body.context)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

class Message(BaseModel):
    recipient_id:str
    body:str=Field(min_length=2,max_length=1400)

@app.post('/api/patients/{pid}/messages')
def message_send(pid:str,body:Message,user=Depends(current_user)):
    try:return {'id':portal.send_message(user,pid,body.recipient_id,body.body)}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

class CareNote(BaseModel):
    kind:str=Field(pattern='^(psychosocial|treatment_concern|visit)$')
    body:str=Field(min_length=2,max_length=1500)

@app.post('/api/patients/{pid}/notes')
def note_submit(pid:str,body:CareNote,user=Depends(current_user)):
    if user['role']!='nurse' or not portal.can(user,pid,'notes'):
        raise HTTPException(403,'Seules les infirmières affectées peuvent rédiger ces notes')
    return {'id':portal.note_create(user,pid,body.kind,body.body)}

class Prescription(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    schedule:str=Field(min_length=2,max_length=180)

@app.post('/api/patients/{pid}/prescriptions')
def prescription_submit(pid:str,body:Prescription,user=Depends(current_user)):
    try:return {'id':portal.prescribe(user,pid,body.name,body.schedule)}
    except PermissionError as e:raise HTTPException(403,str(e))

class Dispense(BaseModel):
    medication_id:str
    quantity:str=Field(min_length=1,max_length=75)
    note:str=Field('',max_length=200)

@app.post('/api/patients/{pid}/dispenses')
def dispensing(pid:str,body:Dispense,user=Depends(current_user)):
    try:return {'id':portal.dispense(user,pid,body.medication_id,body.quantity,body.note)}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

class NewTask(BaseModel):
    assignee_id:str
    title:str=Field(min_length=3,max_length=150)
    due_date:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')

@app.post('/api/patients/{pid}/tasks')
def task_submit(pid:str,body:NewTask,user=Depends(current_user)):
    try:return {'id':portal.task_create(user,pid,body.assignee_id,body.title,body.due_date)}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.post('/api/patients/{pid}/tasks/{task_id}/complete')
def task_complete(pid:str,task_id:str,user=Depends(current_user)):
    try:portal.task_complete(user,pid,task_id);return {'ok':True}
    except PermissionError as e:raise HTTPException(403,str(e))

@app.get('/api/patients/{pid}/grants')
def grants(pid:str,user=Depends(current_user)):
    try:return {'grants':portal.list_grants(user,pid),'allowed_permissions':portal.FAMILY_SCOPES}
    except PermissionError as e:raise HTTPException(403,str(e))

class GrantUpdate(BaseModel):
    family_id:str|None=None
    user_id:str|None=None
    permissions:list[str]
    revoked:bool=False

@app.post('/api/patients/{pid}/grants')
def grant_update(pid:str,body:GrantUpdate,user=Depends(current_user)):
    try:portal.grant_to_account(user,pid,body.user_id or body.family_id,body.permissions,body.revoked);return {'ok':True}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/demo/directory')
def demo_directory(user=Depends(current_user)):
    if user['role']!='patient':raise HTTPException(403,'Réservé au patient fictif')
    return [a for a in portal.list_demo_accounts() if a['role']!='patient']

@app.get('/api/patients/{pid}/audit')
def audit(pid:str,user=Depends(current_user)):
    try:return portal.audit(user,pid)
    except PermissionError as e:raise HTTPException(403,str(e))

@app.get('/api/patients/{pid}/lab-submissions')
def lab_submissions(pid:str,user=Depends(current_user)):
    check(user,pid,'lab_publish',True)
    with db.connect() as c:
        rows=c.execute("SELECT * FROM observations WHERE patient_id=? AND source_id IN (SELECT id FROM receipts WHERE patient_id=? AND issuer=?) ORDER BY measured_at DESC",(pid,pid,user['name'])).fetchall()
    return [dict(r) for r in rows]

@app.post('/api/documents/preview')
async def preview(file:Annotated[UploadFile,File()],patient_id:Annotated[str,Form()],synthetic_ack:Annotated[bool,Form()]=False,user=Depends(current_user)):
    check(user,patient_id,'import',True)
    if not synthetic_ack:raise HTTPException(400,'Mode local de validation requis')
    raw=await file.read(MAX_UPLOAD_BYTES+1)
    await file.close()
    try:parsed=await run_in_threadpool(parse_file,raw,file.content_type or '',file.filename or '')
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    finally:del raw
    now=datetime.now(timezone.utc)
    for key in [k for k,v in preview_sessions.items() if v['expires']<=now]:preview_sessions.pop(key,None)
    token=str(uuid4());exp=now+timedelta(minutes=10)
    preview_sessions[token]={'patient_id':patient_id,'user_id':user['id'],'expires':exp,
        'metadata':{'sha256':parsed.sha256,'page_count':parsed.page_count,'extraction_method':parsed.method,'document_kind':'Document fictif importé','issuer':None,'document_date':parsed.document_date},
        'page_texts':parsed.page_texts,'findings':[f.model_dump() for f in parsed.findings],'candidates':[c.model_dump() for c in parsed.candidates],'medications':[m.model_dump() for m in parsed.medications]}
    return {'import_token':token,'patient_id':patient_id,'patient_name':db.patient_detail(patient_id)['name'],
        'candidates':parsed.candidates,'findings':parsed.findings,'medications':parsed.medications,'warnings':parsed.warnings,
        'page_count':parsed.page_count,'sha256':parsed.sha256,'document_date':parsed.document_date,'extraction_method':parsed.method,'text_previews':parsed.text_previews,'sample_date_options':sample_date_options(parsed.page_texts or []),'conclusions':report_conclusions(parsed.page_texts or []),'expires_at':exp.isoformat()}

@app.post('/api/documents/confirm')
def confirm(body:ImportConfirm,user=Depends(current_user)):
    check(user,body.patient_id,'import',True)
    s=preview_sessions.get(body.import_token)
    if not s or s['expires']<datetime.now(timezone.utc):raise HTTPException(410,'Aperçu expiré')
    if not body.confirm_patient_identity or s['patient_id']!=body.patient_id or s['user_id']!=user['id']:
        raise HTTPException(403,'Patient ou importateur non confirmé')
    if any(x.manual for x in body.candidates) and not body.manual_verified:
        raise HTTPException(400,'Confirmez la vérification de chaque valeur saisie manuellement')
    meta=dict(s['metadata'])
    common_date=None
    if body.document_date:
        try:
            common_date=datetime.strptime(body.document_date,'%Y-%m-%d').date().isoformat()
        except ValueError:raise HTTPException(400,'Date commune invalide')
        meta['document_date']=common_date
    retained=[]
    if body.retained_pages:
        if not body.transcription_verified:raise HTTPException(400,'Vérifiez la transcription avant de la conserver')
        if len(set(body.retained_pages))!=len(body.retained_pages):raise HTTPException(400,'Page sélectionnée plusieurs fois')
        for n in body.retained_pages:
            texts=s.get('page_texts') or []
            if n<1 or n>len(texts):raise HTTPException(400,'Page inconnue')
            if not texts[n-1].strip():raise HTTPException(400,'Page illisible : aucune transcription à conserver')
            retained.append((n,texts[n-1]))
    consumed=set();items=[]
    for item in body.candidates:
        try:dt=datetime.fromisoformat((item.measured_at or (common_date+'T12:00:00+00:00' if common_date else '')).replace('Z','+00:00'))
        except ValueError:raise HTTPException(400,'Date invalide')
        if not dt.tzinfo:raise HTTPException(400,'Fuseau horaire requis')
        match=next((i for i,c in enumerate(s['candidates']) if i not in consumed and c['code']==item.code and c['page']==item.page and c['original_value']==item.original_value and c['original_unit']==item.original_unit),None)
        if match is None:
            if not item.manual:raise HTTPException(400,'Donnée non présente dans le document prévisualisé')
            if item.code not in METRIC_BY_CODE or item.page<1 or item.page>s['metadata']['page_count'] or not item.label:
                raise HTTPException(400,'Paramètre saisi manuellement invalide')
            if item.unit!=METRIC_BY_CODE[item.code].unit or not (-1e6<item.value<1e6):
                raise HTTPException(400,'Valeur ou unité manuelle invalide')
            try: original_value=float(item.original_value.replace(',','.'))
            except ValueError:raise HTTPException(400,'Valeur manuelle non numérique')
            if item.original_unit!=item.unit or not isfinite(original_value) or abs(original_value-item.value)>0.000001:
                raise HTTPException(400,'La valeur manuscrite doit correspondre à la valeur contrôlée')
            meta['extraction_method']=meta['extraction_method']+'+manual-user-entry'
        else:consumed.add(match)
        item_data=item.model_dump();item_data['measured_at']=dt.isoformat();items.append(item_data)
    consumed_med=set();meds=[]
    for med in body.medications:
        match=next((i for i,c in enumerate(s['medications']) if i not in consumed_med and c['name']==med.name and c['strength']==med.strength and c['page']==med.page and c['directions']==med.directions),None)
        if match is None:raise HTTPException(400,'Médicament non issu du document')
        since=med.since or common_date
        try: since=datetime.strptime(since or '', '%Y-%m-%d').date().isoformat()
        except ValueError:raise HTTPException(400,'Date de prescription manquante ou invalide')
        consumed_med.add(match);med_data=med.model_dump();med_data['since']=since;meds.append(med_data)
    findings=[];used_findings=set()
    for finding in body.findings:
        match=next((i for i,f in enumerate(s.get('findings',[])) if i not in used_findings and
            all(f[k]==getattr(finding,k) for k in ('code','label','value','unit','kind','page'))),None)
        if match is None:raise HTTPException(400,'Résultat non présent dans le document prévisualisé')
        try:
            dt=datetime.fromisoformat((finding.measured_at or (common_date+'T12:00:00+00:00' if common_date else '')).replace('Z','+00:00'))
            if not dt.tzinfo:raise ValueError('timezone')
        except ValueError:raise HTTPException(400,'Date du résultat manquante ou invalide')
        used_findings.add(match);item_data=finding.model_dump();item_data['measured_at']=dt.isoformat();findings.append(item_data)
    if not items and not meds and not findings and not retained:raise HTTPException(400,'Aucune donnée sélectionnée')
    try:res=db.save_confirmation(body.patient_id,meta,items,meds,findings,retained)
    except ValueError as e:raise HTTPException(409,str(e))
    preview_sessions.pop(body.import_token,None)
    portal.log(user,body.patient_id,'confirm_document_import')
    with db.connect() as c:portal.add_event(c,user,body.patient_id,'import','import','Import documentaire fictif vérifié par un utilisateur')
    return {'status':'import-confirmed','receipt':res,'original_stored':False}


# V0.4 — patient-first experience: all features are synthetic-only local demonstrations.
@app.get('/api/catalog/medical-domains')
def medical_domains(user=Depends(current_user)):
    return [{'label':name,'explanation':desc} for name,desc in experience.DOMAINS]

@app.get('/api/patients/{pid}/story')
def story(pid:str,user=Depends(current_user)):
    try:return experience.story(user,pid)
    except PermissionError as e:raise HTTPException(403,str(e))

@app.get('/api/patients/{pid}/vaccinations')
def vaccinations(pid:str,user=Depends(current_user)):
    try:return experience.vaccinations(user,pid)
    except PermissionError as e:raise HTTPException(403,str(e))

class Vaccination(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    administered_on:str|None=None
    source:str=Field('Déclaré par le patient (fictif)',max_length=160)
    status:str='declare'

@app.post('/api/patients/{pid}/vaccinations')
def vaccination_create(pid:str,body:Vaccination,user=Depends(current_user)):
    try:experience.add_vaccine(user,pid,body.name,body.administered_on,body.source,body.status);return {'ok':True}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/patients/{pid}/prevention')
def prevention(pid:str,user=Depends(current_user)):
    try:return experience.prevention(user,pid)
    except PermissionError as e:raise HTTPException(403,str(e))

class PreventionStatus(BaseModel):
    key:str
    status:str
    note:str=Field('',max_length=180)

@app.post('/api/patients/{pid}/prevention')
def prevention_update(pid:str,body:PreventionStatus,user=Depends(current_user)):
    try:experience.mark_prevention(user,pid,body.key,body.status,body.note);return {'ok':True}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/patients/{pid}/wellbeing')
def wellbeing(pid:str,user=Depends(current_user)):
    try:return experience.wellbeing(user,pid)
    except PermissionError as e:raise HTTPException(403,str(e))

class Wellbeing(BaseModel):
    category:str
    note:str=Field(min_length=2,max_length=600)
    recorded_on:str

@app.post('/api/patients/{pid}/wellbeing')
def wellbeing_add(pid:str,body:Wellbeing,user=Depends(current_user)):
    try:experience.add_wellbeing(user,pid,body.category,body.note,body.recorded_on);return {'ok':True}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/appointments/slots')
def available_slots(user=Depends(current_user)):
    return experience.slots(user)

class DoctorSlot(BaseModel):
    starts_at:str
    duration:int=30
    location:str=Field('Cabinet fictif',max_length=100)

@app.post('/api/appointments/slots')
def new_slot(body:DoctorSlot,user=Depends(current_user)):
    try:experience.add_slot(user,body.starts_at,body.duration,body.location);return {'ok':True}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/appointments')
def booked_appointments(patient_id:str|None=None,user=Depends(current_user)):
    try:return experience.list_appointments(user,patient_id or user.get('patient_id'))
    except PermissionError as e:raise HTTPException(403,str(e))

class BookAppointment(BaseModel):
    slot_id:str
    reason:str=Field('Consultation de suivi fictive',max_length=180)
    scopes:list[str]=Field(default_factory=list)

@app.post('/api/appointments')
def book_appointment(body:BookAppointment,user=Depends(current_user)):
    try:return {'id':experience.book(user,body.slot_id,body.reason,body.scopes)}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/appointments/{appointment_id}/cancel')
def cancel_appointment(appointment_id:str,user=Depends(current_user)):
    try:experience.cancel(user,appointment_id);return {'ok':True}
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(404,str(e))

@app.get('/api/appointments/{appointment_id}/brief')
def appointment_brief(appointment_id:str,user=Depends(current_user)):
    try:return experience.brief(user,appointment_id)
    except PermissionError as e:raise HTTPException(403,str(e))


@app.get('/api/catalog/professions')
def profession_directory(user=Depends(current_user)):
    return {'groups':[{'group':group,'items':items} for group,items in experience.SPECIALTIES.items()],
            'notice':'Répertoire de découverte produit non exhaustif des qualifications et activités ; ne vaut pas identification RPPS ni autorisation de soins.'}


# V0.5 — One medical catalogue for every view; specialty influences order only.
@app.get('/api/catalog/health-indicators')
def indicator_catalog(user=Depends(current_user)):
    return health_catalog.public_catalog()

def _doctor_specialties(uid):
    with db.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS hb_doctor_specialty(user_id TEXT PRIMARY KEY, specialty TEXT NOT NULL)')
        columns={r[1] for r in c.execute('PRAGMA table_info(hb_doctor_specialty)')}
        if 'secondary' not in columns:c.execute('ALTER TABLE hb_doctor_specialty ADD COLUMN secondary TEXT')
        row=c.execute('SELECT specialty,secondary FROM hb_doctor_specialty WHERE user_id=?',(uid,)).fetchone()
    return (row['specialty'] if row else 'Médecine générale', row['secondary'] if row else None)

@app.get('/api/preferences/specialty')
def get_specialty(user=Depends(current_user)):
    if user['role']!='doctor':raise HTTPException(403,'Réservé au profil médecin fictif')
    primary,secondary=_doctor_specialties(user['id'])
    return {'specialty':primary,'secondary_specialty':secondary,'profile':health_catalog.profile(primary),
            'secondary_profile':health_catalog.profile(secondary) if secondary else None}

class SpecialtyChoice(BaseModel):
    specialty:str
    secondary_specialty:str|None=None

@app.post('/api/preferences/specialty')
def set_specialty(body:SpecialtyChoice,user=Depends(current_user)):
    if user['role']!='doctor':raise HTTPException(403,'Réservé au profil médecin fictif')
    try:
        primary=health_catalog.profile(body.specialty)
        secondary=health_catalog.profile(body.secondary_specialty) if body.secondary_specialty else None
    except ValueError as exc:raise HTTPException(400,str(exc))
    if body.secondary_specialty==body.specialty:raise HTTPException(400,'Sélectionnez deux spécialités différentes')
    _doctor_specialties(user['id'])
    with db.connect() as c:
        c.execute('INSERT INTO hb_doctor_specialty(user_id,specialty,secondary) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET specialty=excluded.specialty,secondary=excluded.secondary',
                  (user['id'],body.specialty,body.secondary_specialty))
    return {'specialty':body.specialty,'secondary_specialty':body.secondary_specialty,'profile':primary,'secondary_profile':secondary}

@app.get('/api/patients/{pid}/health-map')
def health_map(pid:str,user=Depends(current_user)):
    if not db.patient_detail(pid):raise HTTPException(404,'Patient inconnu')
    specialty=secondary=None
    if user['role']=='doctor':specialty,secondary=_doctor_specialties(user['id'])
    try:return health_catalog.map_for_patient(user,pid,specialty,secondary)
    except PermissionError as exc:raise HTTPException(403,str(exc))


# V0.7 — prescription/laboratory pathways with temporary patient-issued QR.
class JourneyOrder(BaseModel):
    patient_id:str
    confirm_patient_identity:bool=False
    kind:str=Field(pattern='^(prescription|lab)$')
    label:str=Field(min_length=3,max_length=150)
    items:list[dict]
    note:str=Field('',max_length=500)

# PDF externe fictif : prévisualisation, vérification d'identité puis publication.
@app.post('/api/import-prescriptions/preview')
async def import_rx_preview(file:Annotated[UploadFile,File()], patient_id:Annotated[str,Form()], synthetic_ack:Annotated[bool,Form()],user=Depends(current_user)):
    if not synthetic_ack:raise HTTPException(400,'Document fictif uniquement')
    raw=await file.read(prescription_import.MAX_PDF_SIZE+1)
    await file.close()
    try:return prescription_import.preview(user,patient_id,raw,file.filename or 'ordonnance.pdf')
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

class ImportPrescriptionConfirm(BaseModel):
    preview_token:str
    patient_id:str
    items:list[dict]
    confirm_patient_identity:bool=False

@app.post('/api/import-prescriptions/confirm')
def import_rx_confirm(body:ImportPrescriptionConfirm,user=Depends(current_user)):
    try:return prescription_import.confirm(user,body.preview_token,body.patient_id,body.items,body.confirm_patient_identity)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/import-prescriptions/{order_id}/original')
def original_prescription(order_id:str,user=Depends(current_user)):
    try:path=prescription_import.attachment_for_user(user,order_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(404,str(e))
    return FileResponse(path,media_type='application/pdf',filename='Ordonnance_Ajour_specimen.pdf',content_disposition_type='inline')

@app.get('/api/import-prescriptions/ticket/{grant_id}/{order_id}/original')
def original_prescription_for_pharmacy(grant_id:str,order_id:str,user=Depends(current_user)):
    try:path=prescription_import.attachment_for_user(user,order_id,grant_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(404,str(e))
    return FileResponse(path,media_type='application/pdf',filename='Ordonnance_Ajour_specimen.pdf')

@app.post('/api/journeys/orders')
def journey_create(body:JourneyOrder,user=Depends(current_user)):
    if user['role']!='doctor':raise HTTPException(403,'Prescription réservée au médecin')
    if not body.confirm_patient_identity:raise HTTPException(400,'Confirmez explicitement le dossier patient concerné')
    try:return journeys.create_order(user,body.patient_id,body.kind,body.label,body.items,body.note)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/journeys/orders/{pid}')
def journey_orders(pid:str,user=Depends(current_user)):
    try:
        rows=journeys.list_orders(user,pid)
        for row in rows:row['has_original_pdf']=prescription_import.has_attachment(row['id'])
        return rows
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(404,str(e))

@app.post('/api/journeys/qr/{order_id}')
def journey_issue_qr(order_id:str,user=Depends(current_user)):
    try:return journeys.qr_issue(user,order_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

class RedeemBody(BaseModel):
    qr_payload:str=Field(min_length=15,max_length=130)

@app.post('/api/journeys/redeem')
def journey_redeem(body:RedeemBody,user=Depends(current_user)):
    try:
        result=journeys.redeem(user,body.qr_payload)
        result['order']['has_original_pdf']=prescription_import.has_attachment(result['order']['id'])
        return result
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/journeys/ticket/{grant_id}')
def journey_ticket(grant_id:str,user=Depends(current_user)):
    try:
        result=journeys.ticket(user,grant_id)
        result['order']['has_original_pdf']=prescription_import.has_attachment(result['order']['id'])
        return result
    except PermissionError as e:raise HTTPException(403,str(e))

class JourneyAction(BaseModel):
    kind:str=Field(pattern='^(dispense|results)$')
    detail:dict

@app.post('/api/journeys/ticket/{grant_id}/action')
def journey_action(grant_id:str,body:JourneyAction,user=Depends(current_user)):
    try:return journeys.action(user,grant_id,body.kind,body.detail)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/journeys/outcomes/{pid}')
def journey_outcomes(pid:str,user=Depends(current_user)):
    try:return journeys.outcomes(user,pid)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(404,str(e))

@app.get('/api/journeys/scenarios')
def journey_scenarios(user=Depends(current_user)):
    return journeys.scenarios_catalog()

@app.post('/api/journeys/orders/{order_id}/cancel')
def journey_cancel(order_id:str,user=Depends(current_user)):
    try:return journeys.cancel_order(user,order_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

class LabSlot(BaseModel):
    starts_at:str
    duration:int=20
    location:str=Field(min_length=3,max_length=140)

@app.post('/api/journeys/lab-slots')
def lab_slot_create(body:LabSlot,user=Depends(current_user)):
    try:return journeys.slot_add(user,body.starts_at,body.duration,body.location)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/journeys/lab-slots')
def lab_slots(user=Depends(current_user)):
    try:return journeys.slots(user)
    except PermissionError as e:raise HTTPException(403,str(e))

class LabBooking(BaseModel):
    order_id:str
    slot_id:str

@app.post('/api/journeys/lab-bookings')
def lab_booking_create(body:LabBooking,user=Depends(current_user)):
    try:return journeys.booking_create(user,body.order_id,body.slot_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/journeys/lab-bookings')
def lab_bookings(user=Depends(current_user)):
    try:return journeys.bookings(user)
    except PermissionError as e:raise HTTPException(403,str(e))

@app.post('/api/journeys/lab-bookings/{booking_id}/cancel')
def lab_booking_cancel(booking_id:str,user=Depends(current_user)):
    try:return journeys.booking_cancel(user,booking_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))


# V0.8 — universal specialty index and order / QR / medical media demo.
class CareCreate(BaseModel):
    patient_id:str
    kind:str
    title:str
    description:str=''
    items:list[dict]
    confirm_patient_identity:bool=False
    specialty_code:str=''

class CareCode(BaseModel):
    qr_payload:str

class CareAction(BaseModel):
    operation:str
    note:str=''

@app.get('/api/care/catalog')
def care_catalogue(user=Depends(current_user)):
    return care_catalog.public_catalog()

@app.post('/api/care/orders')
def care_order_create(body:CareCreate,user=Depends(current_user)):
    if not body.confirm_patient_identity:raise HTTPException(400,'Confirmez le patient concerné')
    try:return careflows.issue_order(user,body.patient_id,body.kind,body.title,body.items,body.description,body.specialty_code)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/care/orders')
def care_order_list(patient_id:str|None=None,user=Depends(current_user)):
    try:return careflows.list_orders(user,patient_id)
    except PermissionError as e:raise HTTPException(403,str(e))

@app.post('/api/care/orders/{order_id}/qr')
def care_order_qr(order_id:str,user=Depends(current_user)):
    try:return careflows.qr_issue(user,order_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/care/qr/redeem')
def care_qr_redeem(body:CareCode,user=Depends(current_user)):
    try:return careflows.redeem(user,body.qr_payload)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/care/tickets/{grant_id}')
def care_ticket(grant_id:str,user=Depends(current_user)):
    try:return careflows.ticket(user,grant_id)
    except PermissionError as e:raise HTTPException(403,str(e))

@app.post('/api/care/tickets/{grant_id}/actions')
def care_ticket_action(grant_id:str,body:CareAction,user=Depends(current_user)):
    try:return careflows.action(user,grant_id,body.operation,body.note)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/care/orders/{order_id}/cancel')
def care_cancel_order(order_id:str,user=Depends(current_user)):
    try:return careflows.cancel(user,order_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/care/media')
async def care_media_upload(file:Annotated[UploadFile,File()], patient_id:Annotated[str,Form()],
  category:Annotated[str,Form()], description:Annotated[str,Form()],
  exam_date:Annotated[str,Form()], anatomical_site:Annotated[str,Form()]='',
  order_id:Annotated[str|None,Form()]=None, grant_id:Annotated[str|None,Form()]=None,
  prior_media_id:Annotated[str|None,Form()]=None, synthetic_ack:Annotated[bool,Form()]=False,
  user=Depends(current_user)):
    if not synthetic_ack:raise HTTPException(400,'Confirmez que le fichier est entièrement fictif')
    # Bounded read: no unrestricted stream into process memory.
    payload=await file.read(careflows.MAX_MEDIA_BYTES+1)
    try:return careflows.upload_media(user,patient_id,payload,file.filename or 'document',category,
        description,anatomical_site,exam_date,order_id,grant_id,prior_media_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/care/media/{patient_id}')
def care_media_list(patient_id:str,user=Depends(current_user)):
    try:return careflows.list_media(user,patient_id)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(404,str(e))

@app.get('/api/care/media/file/{media_id}')
def care_media_file(media_id:str,user=Depends(current_user)):
    try:
        path,meta=careflows.media_for_download(user,media_id)
        return FileResponse(path,media_type=meta['media_type'],filename=meta['filename_original'],
            content_disposition_type='inline' if meta['media_type'].startswith('image/') else 'attachment')
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(404,str(e))

@app.get('/api/care/notifications')
def care_notifications(user=Depends(current_user)):
    return careflows.notifications(user)

@app.get('/api/journeys/ticket/{grant_id}/export')
def journey_ticket_export(grant_id:str,user=Depends(current_user)):
    try:
        row=journeys.ticket(user,grant_id)
        return JSONResponse({'format':'ajour_structured_order_demo_v1', 'kind':row['order']['kind'],
          'label':row['order']['label'],'items':row['order']['items'],
          'source_order_id':row['order']['id'],
          'warning':'Export local, à contrôler dans le logiciel métier. Aucune télétransmission ni validation officielle.'},
          headers={'Content-Disposition':'attachment; filename="ajour-ordonnance-demo.json"'})
    except PermissionError as e:raise HTTPException(403,str(e))


# Ajour 0.9.7 — patient-approved associations and professional workflows.
class LinkCode(BaseModel):
    code:str=Field(min_length=15,max_length=96)

@app.post('/api/practice/patient-code')
def patient_code(user=Depends(current_user)):
    try:return practice.share_code(user)
    except PermissionError as e:raise HTTPException(403,str(e))

@app.post('/api/practice/provider-invitation')
def provider_invitation(user=Depends(current_user)):
    try:return practice.provider_invitation(user)
    except PermissionError as e:raise HTTPException(403,str(e))

@app.post('/api/practice/link')
def link_patient(body:LinkCode,user=Depends(current_user)):
    try:return practice.redeem(user,body.code)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

class ScheduleVisit(BaseModel):
    patient_id:str
    nurse_id:str
    starts_at:str
    care:str=Field(min_length=3,max_length=300)

@app.post('/api/practice/visits')
def plan_nurse_visit(body:ScheduleVisit,user=Depends(current_user)):
    try:return practice.schedule_visit(user,body.patient_id,body.nurse_id,body.starts_at,body.care)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/practice/visits')
def nurse_visits(period:str='day',user=Depends(current_user)):
    try:return practice.visits(user,period)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

class FinishVisit(BaseModel):
    pain_score:int|None=Field(default=None,ge=0,le=10)
    mental_note:str=Field('',max_length=300)
    medication_observed:str=Field('',max_length=300)
    injection:str=Field('',max_length=300)
    vaccine:str=Field('',max_length=300)

@app.post('/api/practice/visits/{visit_id}/complete')
def finish_nurse_visit(visit_id:str,body:FinishVisit,user=Depends(current_user)):
    try:return practice.complete_visit(user,visit_id,**body.model_dump())
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

class MedicationCheck(BaseModel):
    status:str=Field(pattern='^(taken|not_taken)$')

@app.post('/api/practice/medication/{pid}/{medication_id}/check')
def confirm_medication(pid:str,medication_id:str,body:MedicationCheck,user=Depends(current_user)):
    try:return practice.medication_check(user,pid,medication_id,body.status)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/practice/medication/{pid}/checks')
def medication_checks(pid:str,user=Depends(current_user)):
    try:return practice.medication_history(user,pid)
    except PermissionError as e:raise HTTPException(403,str(e))

class Deactivation(BaseModel):
    password:str
    confirmation:str

@app.post('/api/practice/deactivate')
def deactivate(body:Deactivation,user=Depends(current_user)):
    try:return practice.deactivate_own_account(user,body.password,body.confirmation)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.post('/api/practice/activity/import')
async def activity_import(file:UploadFile=File(...),user=Depends(current_user)):
    raw=await file.read(250_001);await file.close()
    try:return practice.import_activity_csv(user,raw)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/practice/activity')
def activity_list(user=Depends(current_user)):
    try:return practice.activities(user)
    except PermissionError as e:raise HTTPException(403,str(e))
