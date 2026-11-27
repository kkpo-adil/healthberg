/* Ajour 0.9.5 — task-first workflows. Uses existing authenticated API and role checks. */
'use strict';
const practiceState={visits:[],period:'day',meds:[],activity:[]};
const professionalRoles=new Set(['doctor','dentist','nurse','optician','radiologist','podiatrist','orthotist','pharmacist','lab']);
const scheduleRoles=new Set(['doctor','dentist','nurse','optician','radiologist','podiatrist','orthotist']);
const practiceBtn=(name,action,icon='＋')=>`<button class="aj-practice-action" data-practice="${action}"><span class="aj-practice-symbol">${icon}</span><b>${name}</b><span>›</span></button>`;
async function practiceReload(){
 if(!state.user)return;
 try{practiceState.visits=state.user.role==='nurse'?await api(`/practice/visits?period=${practiceState.period}`):[];}catch{practiceState.visits=[];}
 if(scheduleRoles.has(state.user.role)&&!pid()){try{const [appointments,slots]=await Promise.all([api('/appointments'),api('/appointments/slots')]);state.extra.appointments=appointments;state.extra.slots=slots;}catch{state.extra.appointments=[];state.extra.slots=[];}}
 try{practiceState.meds=state.user.role==='patient'&&pid()?await api(`/practice/medication/${pid()}/checks`):[];}catch{practiceState.meds=[];}
 try{practiceState.activity=state.user.role==='patient'&&pid()?await api('/practice/activity'):[];}catch{practiceState.activity=[];}
}
function patientAssociationUI(){return `<section class="aj-practice-strip"><h3>Relier mon dossier à un professionnel</h3><p>Un code temporaire, donné directement au professionnel de votre choix. Aucun accès n'est créé sans votre confirmation.</p><div class="aj-practice-action-row">${practiceBtn('Présenter mon code patient','patient-code','▣')}${practiceBtn('Accepter une invitation','accept-link','✓')}</div></section>`;}
function providerAssociationUI(){return `<section class="aj-practice-strip"><h3>Mes patients</h3><p>Associez un patient déjà inscrit avec son code temporaire, ou proposez-lui Ajour.</p><div class="aj-practice-action-row">${practiceBtn('Ajouter un patient','provider-link','♙')}${practiceBtn('Proposer Ajour à un patient','provider-invite','＋')}${scheduleRoles.has(state.user.role)?practiceBtn('Gérer mon agenda','appointments','▣'):''}</div></section>`;}
function clinicalSummaryUI(){
 const d=state.data||{},p=d.patient||{},profile=String(p.profile||'').toLocaleLowerCase('fr');
 const cards=[['◈','Diabète',/diab[èe]t/.test(profile),'analyses'],['♡','Cardiovasculaire',/hyperten|cardio|stent|infarct/.test(profile),'analyses'],['✳','Allergies',/allerg/.test(profile),'documents'],['▤','Opérations / implant',/chirurg|op[eé]ration|implant|stent/.test(profile),'story'],['♧','Handicap / autonomie',/handicap|autonomie/.test(profile),'notes'],['◉','Santé psychique',/psychi|anxi[eé]t|d[eé]press/.test(profile),'notes']];
 const meds=(d.medications||[]);
 return `<section class="aj-practice-strip"><h3>À connaître avant la consultation</h3><div class="aj-clinical-grid">${cards.map(([ico,label,found,tab])=>`<button data-tab="${tab}" class="aj-clinical-pill"><span>${ico}</span><strong>${label}</strong><small>${found?'Mention dans le dossier · à vérifier':'Non renseigné'}</small></button>`).join('')}</div>${meds.length?`<button class="btn outline" data-tab="medications">Traitements consignés (${meds.length})</button>`:''}<p class="small">Un élément absent n'est jamais considéré comme absent médicalement. Aucune interprétation automatique.</p></section>`;
}
function practiceAppointmentCard(){const data=(state.extra.appointments||[]).filter(x=>x.status==='booked').sort((a,b)=>a.starts_at.localeCompare(b.starts_at));const next=data[0];return `<section class="aj-practice-feature"><div><small>MON PROCHAIN RENDEZ-VOUS</small><h3>${next?esc(clock(next.starts_at)):'Aucun rendez-vous prévu'}</h3><p>${next?esc(next.provider)+' · '+esc(next.location):'Rechercher un professionnel ou consulter ses disponibilités'}</p></div><button class="btn primary" data-tab="appointments">${next?'Voir mes rendez-vous':'Prendre rendez-vous'}</button></section>`;}
const oldDoctorWorkspace=ajDoctorWorkspace;
ajDoctorWorkspace=function(){
 if(!state.data)return providerAssociationUI();
 const nurses=(state.data.contacts||[]).filter(x=>x.role==='nurse');
 const plan=nurses.length?`<section class="aj-practice-strip"><details><summary><strong>Programmer une visite infirmière</strong></summary><form id="practicePlanVisit" class="simple-form">
 <label>Infirmier autorisé<select name="nurse_id">${nurses.map(n=>`<option value="${esc(n.id)}">${esc(n.name)}</option>`).join('')}</select></label>
 <label>Jour et heure<input type="datetime-local" name="starts_at" required min="${localNow()}"></label>
 <label>Consigne validée par le prescripteur<textarea name="care" minlength="3" maxlength="300" required></textarea></label>
 <button class="btn primary">Ajouter au programme</button></form></details><p class="small">La consigne doit être vérifiée par le médecin ; Ajour ne déduit pas d'actes d'une ordonnance OCR.</p></section>`:'';
 return `${providerAssociationUI()}${clinicalSummaryUI()}${oldDoctorWorkspace()}${plan}`;
};
function nurseDaily(){
 const v=practiceState.visits||[],todo=v.filter(x=>x.status==='planned'),done=v.filter(x=>x.status==='completed');
 return `<section class="aj-practice-strip"><div class="aj-work-header"><h2>Ma tournée de soins</h2><div class="aj-practice-period">${['day','week','month'].map((q,i)=>`<button class="${practiceState.period===q?'active':''}" data-practice-period="${q}">${['Jour','Semaine','Mois'][i]}</button>`).join('')}</div></div><p>À effectuer : ${todo.length} · Passages validés : ${done.length}</p>${v.map(x=>`<article class="aj-nurse-visit"><div><strong>${esc(clock(x.starts_at))} · ${esc(x.patient_name)}</strong><small>${esc(x.address||'Adresse non renseignée')} ${x.phone?' · '+esc(x.phone):''}${x.entry_code?' · Accès '+esc(x.entry_code):''}</small><p>${esc(x.care)}</p><span>${x.status==='completed'?'Passage validé':'À effectuer'}</span></div>${x.status==='planned'?`<button class="btn primary" data-practice-visit="${esc(x.id)}">Valider mon passage</button>`:''}</article>`).join('')||'<div class="empty">Aucune visite enregistrée sur cette période.</div>'}</section>`;
}
const oldNurseWorkspace=ajNurseWorkspace;
ajNurseWorkspace=function(){return `${nurseDaily()}${providerAssociationUI()}${state.data?oldNurseWorkspace():''}`};
const oldCarePage=carePage;
carePage=function(){const role=state.user.role;if(role!=='optician')return oldCarePage();const orders=(careState.orders||[]),ready=orders.filter(o=>o.status==='ready').length;return `<section class="aj-practice-strip"><h2>Suivi des commandes clients</h2><p>${orders.length} dossier(s) lié(s) à votre compte · ${ready} indiqué(s) prêt(s)</p><div class="aj-practice-action-row">${practiceBtn('Lire une ordonnance','optical-qr','▣')}${practiceBtn('Proposer des créneaux','appointments','▣')}</div><p class="small">Les commandes n'apparaissent ici qu'après lecture d'un QR autorisé.</p></section>${oldCarePage()}`};
const oldProfile=ajProfilePage;
ajProfilePage=function(){
 let base=oldProfile();const x=state.data?.patient?.identity||{};
 base=base.replace('</form>',`<label>Téléphone pour les rendez-vous<input name="phone" maxlength="160" value="${esc(x.phone||'')}" placeholder="Téléphone"></label><label>Code d'accès domicile pour la tournée infirmière<input name="entry_code" maxlength="160" value="${esc(x.entry_code||'')}" placeholder="Code (facultatif)"></label></form>`);
 return `${patientAssociationUI()}${base}<section class="aj-practice-strip"><h3>Vérifier une clé de numéro de Sécurité sociale</h3><p class="small">Contrôle de forme uniquement, sur votre appareil : aucun numéro n'est envoyé ni enregistré. Ne prouve pas l'identité ni la qualification INS.</p><form id="practiceNirCheck"><label>Numéro et clé (15 chiffres, France métropolitaine)<input name="nir" inputmode="numeric" pattern="[0-9 ]{15,25}" autocomplete="off" required placeholder="Saisie locale uniquement"></label><button class="btn outline">Vérifier la clé</button><div id="nirResult" aria-live="polite"></div></form></section><details class="aj-practice-strip"><summary>Gestion de mon compte</summary><p>La désactivation bloque la connexion et les partages. Elle ne supprime pas automatiquement les données médicales conservées.</p><form id="practiceDeactivate"><label>Mot de passe<input name="password" type="password" required></label><label>Écrire DESACTIVER MON COMPTE<input name="confirmation" required></label><button class="btn outline">Désactiver mon accès</button></form></details>`};
function checkNir(value){let n=value.replace(/\s/g,'');if(!/^\d{15}$/.test(n))return '15 chiffres attendus';let body=n.slice(0,13),key=Number(n.slice(13));return key===97-Number(BigInt(body)%97n)?'Clé mathématique cohérente (identité non vérifiée)':'Clé incorrecte';}
const oldMedications=medications;
medications=function(){if(state.user.role!=='patient')return oldMedications();const meds=state.data?.medications||[],history=practiceState.meds||[];return `${oldMedications()}<section class="aj-practice-strip"><h3>Mon suivi des prises</h3><p>Déclarez une prise réellement effectuée. Cette action ne confirme pas une prescription active et ne remplace pas un rappel du médecin.</p>${meds.map(m=>`<div class="aj-med-row"><b>${esc(m.name)}</b><button class="pill-button" data-practice-med="${esc(m.id)}">J'ai pris ce médicament</button></div>`).join('')||'<div class="empty">Aucun traitement à suivre.</div>'}<small>${history.length} confirmation(s) saisie(s) dans ce dossier</small></section>`};
const oldAppointmentsPage=appointmentsPage;
appointmentsPage=function(){const role=state.user.role;const s=(state.extra.slots||[]);let page=oldAppointmentsPage();if(role!=='patient')return page;
 const professions=[...new Set(s.map(x=>x.provider_role))].filter(Boolean).map(r=>`<option value="${esc(r)}">${esc(ROLE[r]||r)}</option>`).join('');
 return `<section class="aj-practice-strip"><h3>Rechercher un rendez-vous</h3><div class="aj-appointment-filters"><label>Spécialité<select id="prSlotRole"><option value="">Toutes</option>${professions}</select></label><label>Ville ou cabinet<input id="prSlotCity" type="search" placeholder="Ex. Paris, Lyon, cabinet..."></label></div><p class="small">Les rendez-vous affichés proviennent uniquement des agendas publiés dans Ajour. La localisation automatique et les annuaires externes ne sont pas connectés.</p></section>${page}`;
};
function orientTopic(value){const s=value.toLocaleLowerCase('fr');let label='Médecin généraliste';if(/vision|flou|œil|yeux|lunette|lentille/.test(s))label='Ophtalmologie';else if(/br[uû]l|urin|zizi|p[eé]nis/.test(s))label='Médecine générale ou urologie';else if(/dent|m[aâ]choire/.test(s))label='Chirurgien-dentiste';else if(/pied|semelle|ongle/.test(s))label='Pédicure-podologue';else if(/vertig|tourn|t[eê]te/.test(s))label='Médecin généraliste';return label;}
const oldRender=render;
render=function(){if(!state.data&&professionalRoles.has(state.user?.role)){
    nav();hero();$('pageBody').innerHTML=state.tab==='appointments'&&scheduleRoles.has(state.user.role)?appointmentsPage():(state.user.role==='nurse'?`${nurseDaily()}${providerAssociationUI()}`:providerAssociationUI());return;
  }oldRender();};
async function practiceReauth(){const me=await api('/auth/me');const last=pid();state.patients=me.patients;state.scopes=me.scopes;state.patient=state.patients.find(x=>x.id===last)||state.patients[0]||null;await refresh();}
async function generatePatientCode(){const r=await send('/practice/patient-code',{});showModal(`<h2>Présenter mon code patient</h2><p>Le professionnel saisit ce code dans son espace Ajour. Il expire dans 10 minutes et ne fonctionne qu'une fois.</p><div class="aj-large-code">${esc(r.code)}</div><button class="btn outline" data-practice-copy="${esc(r.code)}">Copier le code</button>`);}
async function generateProviderInvitation(){const r=await send('/practice/provider-invitation',{});showModal(`<h2>Proposer Ajour à un patient</h2><p>Après création de son compte, le patient saisit ce code dans Mon profil pour autoriser le rapprochement.</p><div class="aj-large-code">${esc(r.code)}</div><button class="btn outline" data-practice-copy="${esc(r.code)}">Copier le code</button><p class="small">Valable 48 heures. Aucun dossier n'est accessible avant acceptation.</p>`);}
function linkCodeModal(isPatient=false){showModal(`<h2>${isPatient?'Accepter une invitation':'Ajouter un patient'}</h2><p>${isPatient?'Saisissez le code remis par le professionnel':'Demandez au patient de générer un code depuis Mon profil'}. Le patient garde le contrôle de ses autorisations.</p><form id="practiceLink"><label>Code d'association<input name="code" required minlength="15" autocomplete="off"></label><button class="btn primary">Confirmer l'association</button></form>`)}
function completeNurseVisitForm(id){const visit=practiceState.visits.find(x=>x.id===id);if(!visit)return;showModal(`<h2>Valider un passage</h2><p><strong>${esc(visit.patient_name)}</strong> · ${esc(clock(visit.starts_at))}</p><p>${esc(visit.care)}</p><form id="practiceCompleteVisit" data-visit="${esc(id)}"><label>Douleur observée ou déclarée (0 à 10, facultatif)<input type="number" min="0" max="10" name="pain_score"></label><label>Observation psychosociale factuelle<textarea name="mental_note" maxlength="300"></textarea></label><label>Prise de médicament constatée en présence<textarea name="medication_observed" maxlength="300"></textarea></label><label>Injection réalisée (produit tel que documenté)<input name="injection" maxlength="300"></label><label>Vaccin effectué, si applicable<input name="vaccine" maxlength="300"></label><button class="btn primary">Valider le passage</button></form>`)}
// Capturing the submit event first prevents the original generic form handler from swallowing our new forms.
document.addEventListener('submit',async e=>{
 const form=e.target;if(!['practiceLink','practiceCompleteVisit','practiceNirCheck','practiceOrient','practicePlanVisit','practiceDeactivate'].includes(form.id))return;
 e.preventDefault();e.stopImmediatePropagation();const fd=new FormData(form);
 try{
 if(form.id==='practiceLink'){await send('/practice/link',{code:String(fd.get('code'))});closeModal();toast('Association confirmée');await practiceReauth();}
 if(form.id==='practiceCompleteVisit'){const value=fd.get('pain_score');await send(`/practice/visits/${form.dataset.visit}/complete`,{pain_score:value===''?null:Number(value),mental_note:fd.get('mental_note')||'',medication_observed:fd.get('medication_observed')||'',injection:fd.get('injection')||'',vaccine:fd.get('vaccine')||''});closeModal();toast('Passage enregistré');await practiceReload();render();}
 if(form.id==='practiceNirCheck'){$('nirResult').textContent=checkNir(String(fd.get('nir')||''));form.elements.nir.value='';}
 if(form.id==='practicePlanVisit'){await send('/practice/visits',{patient_id:pid(),nurse_id:fd.get('nurse_id'),starts_at:new Date(fd.get('starts_at')).toISOString(),care:fd.get('care')});toast('Visite inscrite à la tournée de l’infirmier');await refresh();}
 if(form.id==='practiceDeactivate'){const result=await send('/practice/deactivate',{password:fd.get('password'),confirmation:fd.get('confirmation')});if(result.access_disabled){closeModal();await logout();toast('Accès désactivé');}}
 if(form.id==='practiceOrient'){$('practiceOrientResult').innerHTML=`<div class="aj-practice-recommend"><strong>Pour commencer : ${esc(orientTopic(String(fd.get('symptom')||'')))}</strong><p>Cette indication aide à rechercher un praticien ; elle ne permet pas de déterminer la gravité des symptômes.</p><button class="btn outline" data-tab="appointments">Voir les créneaux disponibles</button></div>`;}
 }catch(err){toast(err.message,true)}
},true);
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 try{
 if(b.dataset.practicePeriod){practiceState.period=b.dataset.practicePeriod;await practiceReload();render();return;}
 if(b.dataset.practiceVisit){completeNurseVisitForm(b.dataset.practiceVisit);return;}
 if(b.dataset.practiceMed){await send(`/practice/medication/${pid()}/${b.dataset.practiceMed}/check`,{status:'taken'});toast('Prise déclarée par le patient');await practiceReload();render();return;}
 if(b.dataset.practiceCopy){await GenCopy(b.dataset.practiceCopy);return;}
 if(!b.dataset.practice)return;
 switch(b.dataset.practice){
 case 'patient-code':await generatePatientCode();break;
 case 'provider-invite':await generateProviderInvitation();break;
 case 'provider-link':linkCodeModal();break;
 case 'accept-link':linkCodeModal(true);break;
 case 'story':state.tab='story';await refresh();break;
 case 'orders':state.tab='journeys';await refresh();break;
 case 'appointments':state.tab='appointments';await refresh();break;
 case 'optical-qr':state.tab='careflows';await refresh();break;
 }
 }catch(err){toast(err.message,true)}
});
async function GenCopy(value){try{await navigator.clipboard.writeText(value);toast('Code copié');}catch{toast('Sélectionnez le code pour le copier manuellement.',true)}}
// Search filters operate on the existing list of real published Ajour slots.
document.addEventListener('input',e=>{if(!['prSlotCity','prSlotRole'].includes(e.target.id))return;const role=$('prSlotRole')?.value||'',city=($('prSlotCity')?.value||'').toLocaleLowerCase('fr');const opts=document.querySelectorAll('#bookForm select[name="slot_id"] option');opts.forEach(o=>{const s=(state.extra.slots||[]).find(x=>x.id===o.value);o.disabled=!!s&&((role&&s.provider_role!==role)||(city&&!`${s.location} ${s.provider}`.toLocaleLowerCase('fr').includes(city)));});});

const oldWellbeing=wellbeingPage;
wellbeingPage=function(){if(state.user.role!=='patient')return oldWellbeing();const rows=practiceState.activity||[];return `${oldWellbeing()}<section class="aj-practice-strip"><h3>Activité et appareils connectés</h3><p>Importer un export CSV d'une montre ou d'une application santé. Ajour ne se connecte pas encore directement à Apple Santé, Garmin, Fitbit ou aux autres marques.</p><form id="practiceActivityUpload" class="simple-form"><label>Fichier CSV<input type="file" name="file" accept=".csv,text/csv" required></label><p class="small">Colonnes : date,steps,sleep_hours,heart_rate — dates au format AAAA-MM-JJ. Champs facultatifs sauf date.</p><button class="btn primary">Importer mon activité</button></form><h4>Mes derniers relevés</h4>${rows.slice(0,20).map(x=>`<div class="aj-med-row"><b>${esc(x.recorded_on)} · ${esc(({steps:'Pas',sleep_hours:'Sommeil',heart_rate:'Fréquence cardiaque'})[x.kind]||x.kind)}</b><span>${fmt(x.value)} ${esc(x.unit)}</span></div>`).join('')||'<p class="small">Aucune donnée d’activité importée.</p>'}</section>`};
document.addEventListener('submit',async e=>{if(e.target.id!=='practiceActivityUpload')return;e.preventDefault();e.stopImmediatePropagation();try{const result=await api('/practice/activity/import',{method:'POST',body:new FormData(e.target)});toast(`${result.imported_records} nouvelle(s) mesure(s) importée(s)${result.already_present?' · '+result.already_present+' déjà présente(s)':''}`);await practiceReload();render();}catch(err){toast(err.message,true)}},true);
