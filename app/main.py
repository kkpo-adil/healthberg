"""HEALTHBERG: demonstration on fictional data, NOT an online clinical service.

No authentication, no HDS guarantee. Bind to localhost only. Never upload real health data.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from typing import Annotated
import os
import tempfile

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import db
from .extraction import parse_file, MAX_UPLOAD_BYTES
from .models import ImportConfirm
from .terminology import METRIC_BY_CODE

if os.getenv('HEALTHBERG_ENABLE_REAL_PATIENTS','false').lower() == 'true':
    raise RuntimeError('Real patients are forbidden in this demonstration build.')

@asynccontextmanager
async def lifespan(application):
    db.init_db()
    db.purge_expired()
    yield

app=FastAPI(title='HEALTHBERG — Démonstrateur synthétique',version='0.2.0',docs_url='/api/docs',redoc_url=None,lifespan=lifespan)
STATIC=Path(__file__).resolve().parents[1]/'static'
app.mount('/static',StaticFiles(directory=STATIC),name='static')
# Contains metadata and ephemeral candidate text, not the uploaded file bytes or raw pages.
preview_sessions:dict[str,dict]={}

@app.middleware('http')
async def demo_safety(request:Request,call_next):
    # Disallow cross-site script calls as this app has no authentication.
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/') not in {'http://127.0.0.1:8765','http://localhost:8765','http://testserver'}:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403,content={'detail':'Origine non autorisée dans la démonstration'})
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return response

@app.get('/')
def index():return FileResponse(STATIC/'index.html')

@app.get('/api/health')
def health():return {'status':'synthetic-demo-only','version':'0.2.0','retention_days_provisional':db.RETENTION_DAYS}

@app.get('/api/patients')
def patients():return db.list_patients()

def ensure_patient(pid):
    p=db.patient_detail(pid)
    if p is None:raise HTTPException(404,'Patient inconnu')
    return p

@app.get('/api/patients/{pid}/overview')
def overview(pid:str):
    p=ensure_patient(pid)
    obs=db.list_observations(pid)
    last={}
    for o in obs:
        if o['code'] not in last or o['measured_at']>last[o['code']]['measured_at']:
            last[o['code']]=o
    since=p['last_consultation']
    recent=[o for o in obs if o['measured_at'][:10]>since]
    return {'patient':p,'last_values':last,'recent_observation_count':len(recent),
            'recent_observations':sorted(recent,key=lambda o:o['measured_at'],reverse=True)[:6],
            'events':db.list_events(pid),'medications':db.list_meds(pid),
            'metrics':[{'code':m.code,'label':m.label,'unit':m.unit} for m in METRIC_BY_CODE.values()],
            'receipt_count':len(db.list_receipts(pid))}

@app.get('/api/patients/{pid}/observations')
def observations(pid:str,code:str|None=None):
    ensure_patient(pid)
    if code is not None and code not in METRIC_BY_CODE:raise HTTPException(400,'Code inconnu')
    return db.list_observations(pid,code)

@app.get('/api/patients/{pid}/receipts')
def receipts(pid:str):ensure_patient(pid);return db.list_receipts(pid)

@app.get('/api/patients/{pid}/receipts/{rid}')
def receipt(pid:str,rid:str):
    ensure_patient(pid)
    r=db.receipt_by_id(pid,rid)
    if r is None:raise HTTPException(404,'Source indisponible pour ce patient')
    return r

@app.post('/api/documents/preview')
async def preview(file:Annotated[UploadFile,File()], patient_id:Annotated[str,Form()], synthetic_ack:Annotated[bool,Form()] = False):
    p=ensure_patient(patient_id)
    if not synthetic_ack:raise HTTPException(400,'Confirmer que ce document contient uniquement des données fictives')
    data=await file.read(MAX_UPLOAD_BYTES+1)
    await file.close()
    try: parsed=parse_file(data,file.content_type or '',file.filename or '')
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    finally:del data
    now=datetime.now(timezone.utc)
    # Process-local only; 10 minute expiration, empty source text discarded after approval.
    for key in [k for k,v in preview_sessions.items() if v['expires'] <= now]:
        preview_sessions.pop(key,None)
    token=str(uuid4())
    expires=now+timedelta(minutes=10)
    preview_sessions[token]={'patient_id':p['id'],'expires':expires,
        'metadata':{'sha256':parsed.sha256,'page_count':parsed.page_count,'extraction_method':parsed.method,
                    'document_kind':'Document importé (fictif)','issuer':None,'document_date':parsed.document_date},
        'candidates':[c.model_dump() for c in parsed.candidates], 'medications':[m.model_dump() for m in parsed.medications]}
    return {'import_token':token,'patient_id':p['id'],'patient_name':p['name'],
            'sha256':parsed.sha256,'document_kind':'Document importé (fictif)',
            'issuer':None,'document_date':parsed.document_date,'page_count':parsed.page_count,
            'extraction_method':parsed.method,'candidates':parsed.candidates,'medications':parsed.medications,'warnings':parsed.warnings,
            'expires_at':expires.isoformat()}

@app.post('/api/documents/confirm')
def confirm(body:ImportConfirm):
    ensure_patient(body.patient_id)
    s=preview_sessions.get(body.import_token)
    if not s or s['expires']<datetime.now(timezone.utc):
        raise HTTPException(410,'Prévisualisation expirée, réimporter le fichier')
    if not body.confirm_patient_identity or body.patient_id!=s['patient_id']:
        raise HTTPException(403,'Identification du patient non confirmée')
    # Strict membership validation: client cannot add arbitrary measurements to approved preview.
    approved=s['candidates']
    consumed=set()
    items=[]
    for item in body.candidates:
        if item.measured_at[:10]=='':raise HTTPException(400,'Date de mesure manquante')
        try:datetime.fromisoformat(item.measured_at.replace('Z','+00:00'))
        except ValueError:raise HTTPException(400,'Date de mesure invalide')
        match=next((i for i,c in enumerate(approved) if i not in consumed and
                    c['code']==item.code and c['page']==item.page and c['original_value']==item.original_value and
                    c['original_unit']==item.original_unit),None)
        if match is None:raise HTTPException(400,'Valeur non issue du document prévisualisé')
        # Users may correct extracted value/unit, but only within the candidate metric.
        if item.code not in METRIC_BY_CODE:raise HTTPException(400,'Paramètre inconnu')
        consumed.add(match);items.append(item.model_dump())
    med_approved=s['medications']
    med_consumed=set();med_items=[]
    for med in body.medications:
        if len(med.name)>100 or len(med.directions)>280 or len(med.strength)>30:
            raise HTTPException(400,'Texte de médicament trop long')
        try:datetime.fromisoformat(med.since.replace('Z','+00:00'))
        except ValueError:raise HTTPException(400,'Date de prescription invalide')
        match=next((i for i,c in enumerate(med_approved) if i not in med_consumed and c['name']==med.name and c['strength']==med.strength and c['page']==med.page),None)
        if match is None:raise HTTPException(400,'Médicament non issu du document prévisualisé')
        med_consumed.add(match);med_items.append(med.model_dump())
    if not items and not med_items:raise HTTPException(400,'Sélectionner au moins une mesure ou prescription')
    try:r=db.save_confirmation(body.patient_id,s['metadata'],items,med_items)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    preview_sessions.pop(body.import_token,None)
    return {'status':'import-confirmed','receipt':r,'original_stored':False}

@app.post('/api/admin/purge-expired')
def purge():
    # DEMO ONLY; for production this would require a privileged authenticated background job.
    return db.purge_expired()
