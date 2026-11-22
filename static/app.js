/* HEALTHBERG 0.2 — demonstration UI, fictional records only.
   DOM output is escaped; original document bytes remain ephemeral on upload.
*/
'use strict';
const state = { patients: [], patientId: 'pat_marie', overview: null, observations: [], receipts: [], metric: 'glucose', analysisMetric: 'glucose', period: 'all', tab: 'dashboard', preview: null, file: null };
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const niceDate = iso => { if(!iso) return 'Date inconnue'; try { return new Intl.DateTimeFormat('fr-FR',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(iso.length===10?iso+'T12:00:00':iso)); }catch { return iso; } };
const fmt = (n,d=2) => Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d,minimumFractionDigits: Number.isInteger(Number(n))?0:Math.min(d,1)});
const shortMetric = { glucose:'Glycémie',hba1c:'HbA1c',systolic:'Tension SYS',diastolic:'Tension DIA',creatinine:'Créatinine',egfr:'DFG rapporté',weight:'Poids',pulse:'Fréquence cardiaque',cholesterol:'Cholestérol'};
const icons = { glucose:'↗',hba1c:'%',systolic:'⌁',diastolic:'⌁',creatinine:'◇',egfr:'◇',weight:'⌗',pulse:'♥',cholesterol:'◉' };
const statusLabel = {synthetic_verified:'Fictif',extracted_pending:'Extraction à revoir',patient_confirmed:'Confirmé utilisateur',professional_verified:'Vérifié par soignant'};
async function api(url, options={}) { let res; try{res=await fetch(url,{cache:'no-store',...options});}catch(e){throw new Error('Connexion impossible. Le serveur local est-il démarré ?');} let data; try {data=await res.json()}catch{throw new Error('Réponse serveur invalide');} if(!res.ok)throw new Error(data.detail||`Erreur ${res.status}`); return data; }
function busy(text){$('patientName').textContent=text;}
function report(err){console.error(err);const main=document.querySelector('.content');if(main){const x=document.createElement('div');x.className='notice error-msg';x.textContent='Erreur : '+err.message;main.prepend(x);setTimeout(()=>x.remove(),9000)}}

async function start(){
 try{
  state.patients=await api('/api/patients');
  if(!state.patients.length){busy('Aucun profil fictif');return;}
  if(!state.patients.some(p=>p.id===state.patientId))state.patientId=state.patients[0].id;
  renderPatientList(); await changePatient(state.patientId); installListeners();
 }catch(err){report(err)}
}
function renderPatientList(){
 $('patientList').innerHTML=state.patients.map(p=>`<button class="patient-row ${p.id===state.patientId?'selected':''}" data-patient="${esc(p.id)}"><span class="mini-avatar">${esc(p.initials)}</span><span><strong>${esc(p.name)}</strong><small>${p.age} ans · Données fictives</small></span></button>`).join('');
 document.querySelectorAll('[data-patient]').forEach(b=>b.addEventListener('click',()=>changePatient(b.dataset.patient)));
}
async function changePatient(id){
 state.patientId=id;
 try{[state.overview,state.observations,state.receipts]=await Promise.all([
  api(`/api/patients/${encodeURIComponent(id)}/overview`),api(`/api/patients/${encodeURIComponent(id)}/observations`),api(`/api/patients/${encodeURIComponent(id)}/receipts`)]);
  renderPatientList();renderAll();$('sidebar').classList.remove('open');
 }catch(err){report(err)}
}
function renderAll(){
 const o=state.overview, p=o.patient;
 $('patientName').innerHTML=`${esc(p.name)} <span class="hero-age">${p.age} ans</span>`;
 $('patientProfile').textContent=p.profile;
 $('heroInitials').textContent=p.initials;
 $('patientCode').textContent=`HB-${String(state.patients.findIndex(x=>x.id===p.id)+1).padStart(4,'0')}`;
 $('lastConsult').textContent=niceDate(p.last_consultation);
 $('receiptCount').textContent=o.receipt_count;
 renderMetrics(); renderMetricSelectors();renderChartPanel();renderLatest();renderSince();renderTimeline();renderAnalyses();renderReceipts();renderMeds();
}
function latestFor(code){return [...state.observations].filter(x=>x.code===code).sort((a,b)=>b.measured_at.localeCompare(a.measured_at))[0];}
function renderMetrics(){
 const codes=['systolic','glucose','hba1c','creatinine'];
 $('metricsGrid').innerHTML=codes.map(code=>{
  const x=latestFor(code);
  const val=code==='systolic'&&x?`${fmt(x.value,0)}<span style="color:#8096aa;font-weight:400">/</span>${fmt(latestFor('diastolic')?.value ?? '—',0)}`:x?fmt(x.value):'—';
  const unit=code==='systolic'?'mmHg':x?.unit||'';
  return `<div class="metric-card" data-metric-card="${code}" tabindex="0" role="button" aria-label="Afficher les séries de ${esc(shortMetric[code])}"><div class="metric-top"><span class="metric-label">${esc(shortMetric[code])}</span><span class="metric-symbol">${icons[code]}</span></div><div class="metric-value">${val} <small>${esc(unit)}</small></div><div class="metric-bottom"><span>${x?niceDate(x.measured_at):'Aucune mesure'}</span><span class="status-tag ${x?.status==='extracted_pending'?'pending-tag':''}">${esc(statusLabel[x?.status]||'Inconnu')}</span></div></div>`;
 }).join('');
 document.querySelectorAll('[data-metric-card]').forEach(b=>{const go=()=>{state.metric=b.dataset.metricCard;state.analysisMetric=state.metric;setTab('analyses')};b.addEventListener('click',go);b.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' ')go()})});
}
function metricOptions(){const codes=Array.from(new Set(state.observations.map(o=>o.code)));return codes.map(code=>`<option value="${esc(code)}">${esc(shortMetric[code]||code)}</option>`).join('')}
function renderMetricSelectors(){const opts=metricOptions();$('metricSelect').innerHTML=opts;$('analysisMetricSelect').innerHTML=opts;
 if(!state.observations.some(o=>o.code===state.metric))state.metric=state.observations[0]?.code||'glucose';
 if(!state.observations.some(o=>o.code===state.analysisMetric))state.analysisMetric=state.metric;
 $('metricSelect').value=state.metric;$('analysisMetricSelect').value=state.analysisMetric;
}
function filteredSeries(code,period='all'){
 let a=state.observations.filter(x=>x.code===code&&Number.isFinite(x.value)).sort((a,b)=>a.measured_at.localeCompare(b.measured_at));
 if(period!=='all'&&a.length){const max=new Date(a[a.length-1].measured_at);const cutoff=new Date(max);cutoff.setMonth(cutoff.getMonth()-Number(period));a=a.filter(x=>new Date(x.measured_at)>=cutoff)}
 return a;
}
function chartHTML(series,unit,large=false){
 if(!series.length)return '<div class="empty-state">Aucune mesure pour cette période.</div>';
 const width=800,height=large?315:237,left=58,right=20,top=18,bottom=39,plotW=width-left-right,plotH=height-top-bottom;
 const values=series.map(x=>x.value),min=Math.min(...values),max=Math.max(...values),pad=Math.max((max-min)*.18,Math.abs(max)*.035,.1),lo=Math.max(0,min-pad),hi=max+pad;
 const dates=series.map(s=>new Date(s.measured_at).getTime()),xmin=Math.min(...dates),xmax=Math.max(...dates),diff=xmax-xmin||1;
 const X=i=>left+(dates[i]-xmin)/diff*plotW;
 const Y=v=>top+((hi-v)/(hi-lo))*plotH;
 const coords=series.map((x,i)=>[X(i),Y(x.value)]);
 const points=coords.map(p=>p.join(',')).join(' ');
 const line=coords.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(' ');
 const area=line+` L${coords[coords.length-1][0]},${top+plotH} L${coords[0][0]},${top+plotH} Z`;
 const ticks=Array.from({length:5},(_,i)=>lo+(hi-lo)*(4-i)/4);
 let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${series.length} points datés en ${esc(unit)}"><defs><linearGradient id="chart-grad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#22d8c5" stop-opacity=".22"/><stop offset="100%" stop-color="#22d8c5" stop-opacity="0"/></linearGradient></defs>`;
 for(const tick of ticks){const y=Y(tick);svg+=`<line x1="${left}" x2="${width-right}" y1="${y}" y2="${y}" class="chart-grid"/><text x="${left-10}" y="${y+4}" text-anchor="end" class="chart-label">${esc(fmt(tick,2))}</text>`}
 const xticks=[0,Math.floor((series.length-1)/3),Math.floor((series.length-1)*2/3),series.length-1];
 for(const i of [...new Set(xticks)]){svg+=`<text x="${X(i)}" y="${height-10}" text-anchor="middle" class="chart-label">${esc(new Intl.DateTimeFormat('fr-FR',{month:'short',year:'2-digit'}).format(new Date(series[i].measured_at)))}</text>`}
 svg+=`<path d="${area}" class="chart-area"/><path d="${line}" class="chart-line"/>`;
 coords.forEach((p,i)=>svg+=`<circle data-chart-point="${i}" class="chart-point" cx="${p[0]}" cy="${p[1]}" r="4" tabindex="0" role="button" aria-label="${esc(niceDate(series[i].measured_at))}, ${esc(fmt(series[i].value))} ${esc(unit)}"><title>${esc(fmt(series[i].value))} ${esc(unit)} · ${esc(niceDate(series[i].measured_at))}</title></circle>`);
 svg+='</svg>';return svg;
}
function wireChart(container,series){container.querySelectorAll('[data-chart-point]').forEach(el=>{const action=()=>showSource(series[+el.dataset.chartPoint]);el.addEventListener('click',action);el.addEventListener('keydown',e=>{if(e.key==='Enter')action()})})}
function renderChartPanel(){
 const a=filteredSeries(state.metric,state.period),last=a.at(-1);
 $('chartMetricLabel').textContent=shortMetric[state.metric]||state.metric;$('chartUnit').textContent=last?.unit||'';
 $('chartCount').textContent=a.length+' points';$('metricSelect').value=state.metric;$('periodSelect').value=state.period;
 $('lineChart').innerHTML=chartHTML(a,last?.unit||'');wireChart($('lineChart'),a);
}
function renderLatest(){
 const top=[...state.observations].sort((a,b)=>b.measured_at.localeCompare(a.measured_at)).slice(0,5);
 $('latestObservations').innerHTML=top.map(o=>`<div class="observation-row" data-observation="${esc(o.id)}" tabindex="0" role="button"><div class="obs-icon">${icons[o.code]||'◇'}</div><div class="obs-detail"><span class="observation-name">${esc(shortMetric[o.code]||o.label)}</span><span class="observation-meta">${esc(niceDate(o.measured_at))} · ${esc(statusLabel[o.status]||o.status)}</span></div><div class="obs-value">${esc(fmt(o.value))} <small>${esc(o.unit)}</small></div></div>`).join('')||'<div class="empty-state">Aucune observation</div>';
 $('latestObservations').querySelectorAll('[data-observation]').forEach(el=>{const click=()=>showSource(state.observations.find(o=>o.id===el.dataset.observation));el.addEventListener('click',click);el.addEventListener('keydown',e=>{if(e.key==='Enter')click()})})
}
function renderSince(){const o=state.overview;$('newFacts').textContent=o.recent_observation_count+' valeurs';
 $('sinceConsultation').innerHTML=`<div class="since-value">${o.recent_observation_count}</div><div class="since-text">nouvelles observations documentées depuis le ${esc(niceDate(o.patient.last_consultation))}. Chaque mesure est consultable avec sa provenance.</div><div class="since-note"><b>À préparer avant la consultation</b><p>Consulter les changements datés, confirmer les traitements réellement pris et vérifier les éventuelles discordances.</p></div>`;
}
function renderTimeline(){const rows=state.overview.events||[];$('timeline').innerHTML=rows.map(e=>`<div class="timeline-row"><strong>${esc(e.label)}</strong><time>${esc(niceDate(e.at))}</time><p>${esc(e.detail)}</p></div>`).join('')||'<div class="empty-state">Aucun événement.</div>'}
function renderAnalyses(){
 const code=state.analysisMetric,series=filteredSeries(code),unit=series[0]?.unit||'';
 $('analysisMetricSelect').value=code;$('analysisTitle').textContent=shortMetric[code]||code;
 $('analysisChart').innerHTML=chartHTML(series,unit,true);wireChart($('analysisChart'),series);
 $('analysisRows').innerHTML=`<div class="analysis-row" style="color:#879ab0;font-size:10px"><span>DATE</span><span>RÉSULTAT</span><span>STATUT</span><span>SOURCE</span></div>`+
 [...series].reverse().slice(0,18).map(o=>`<div class="analysis-row" data-analyses-obs="${esc(o.id)}" tabindex="0" role="button" style="cursor:pointer"><span>${esc(niceDate(o.measured_at))}</span><strong>${esc(fmt(o.value))} <small>${esc(o.unit)}</small></strong><span><small>${esc(statusLabel[o.status]||o.status)}</small></span><span><small>Voir la provenance ↗</small></span></div>`).join('');
 $('analysisRows').querySelectorAll('[data-analyses-obs]').forEach(el=>{const go=()=>showSource(state.observations.find(o=>o.id===el.dataset.analysesObs));el.addEventListener('click',go);el.addEventListener('keydown',e=>{if(e.key==='Enter')go()})});
}
function renderReceipts(){
 $('receiptRows').innerHTML=state.receipts.map(r=>`<div class="registry-row" data-receipt="${esc(r.id)}" tabindex="0" role="button"><span><strong>${esc(r.document_kind)}</strong><small>${esc(r.issuer||'Émetteur non identifié')} · ${r.page_count} page(s)</small></span><span class="receipt-hash">${esc(r.sha256.substring(0,20))}…<small>${esc(niceDate(r.document_date))}</small></span><span><span class="status-tag">Original absent</span></span></div>`).join('')||'<div class="empty-state">Aucun document référencé.</div>';
 document.querySelectorAll('[data-receipt]').forEach(el=>{const go=()=>showReceipt(el.dataset.receipt);el.addEventListener('click',go);el.addEventListener('keydown',e=>{if(e.key==='Enter')go()})});
}
function renderMeds(){const meds=state.overview.medications;
 $('medRows').innerHTML=meds.map(m=>`<div class="med-row" ${m.source_id?`data-medsource="${esc(m.source_id)}" tabindex="0" role="button" style="cursor:pointer"`:''}><span><strong>${esc(m.name)}</strong><small>${esc(m.note)}</small></span><span>${esc(m.schedule)}</span><span><span class="status-tag ${m.state==='declared'?'pending-tag':''}">${esc(m.state==='historical'?'Historique':m.state==='declared'?'Déclaré':'Vérifié')}</span><small style="display:block;margin-top:6px">Depuis ${esc(niceDate(m.since))}</small></span></div>`).join('')||'<div class="empty-state">Aucune information médicamenteuse.</div>';
 $('medRows').querySelectorAll('[data-medsource]').forEach(el=>{const go=()=>showReceipt(el.dataset.medsource);el.addEventListener('click',go);el.addEventListener('keydown',e=>{if(e.key==='Enter')go()})});
}
function sourceFact(label,val,wide=false){return `<div class="source-fact ${wide?'wide':''}"><b>${esc(label)}</b><span>${esc(val??'Inconnu')}</span></div>`}
function showReceipt(id,observation){const r=state.receipts.find(x=>x.id===id);if(!r)return;
 $('sourceTitle').textContent=observation?'Source de la mesure':'Fiche de provenance documentaire';
 let html='<div class="source-facts">';
 if(observation){html+=sourceFact('PARAMÈTRE',observation.label)+sourceFact('VALEUR',`${fmt(observation.value)} ${observation.unit}`)+sourceFact('MESURE DATÉE',niceDate(observation.measured_at))+sourceFact('PAGE D’ORIGINE',observation.page??'Non disponible')+sourceFact('STATUT',statusLabel[observation.status]||observation.status)+sourceFact('CONTEXTE',observation.context||'Non renseigné');}
 html+=sourceFact('TYPE DE DOCUMENT',r.document_kind)+sourceFact('ÉMETTEUR',r.issuer||'Non identifié')+sourceFact('DATE DU DOCUMENT',niceDate(r.document_date))+sourceFact('DATE D’IMPORT',niceDate(r.imported_at))+sourceFact('MÉTHODE D’EXTRACTION',r.extraction_method)+sourceFact('PAGES',r.page_count)+sourceFact('EMPREINTE SHA-256',r.sha256,true)+sourceFact('CONSERVATION',`Jusqu’au ${niceDate(r.retention_until)} — durée provisoire, réexaminable`,true);html+='</div><div class="source-note"><strong>Original non conservé.</strong> Cette fiche indique l’origine déclarée et l’empreinte du fichier importé. Elle ne prouve ni l’authenticité du document, ni la justesse médicale des données. Pour revérifier le texte original, il faudra réimporter le fichier.</div>';
 $('sourceContent').innerHTML=html;$('sourceOverlay').classList.remove('hidden')}
function showSource(o){if(o)showReceipt(o.source_id,o)}
function setTab(tab){state.tab=tab;for(const name of ['dashboard','analyses','documents','medications'])$(name+'Tab').classList.toggle('hidden',name!==tab);
 document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n.dataset.tab===tab));
 $('breadcrumb').textContent=({dashboard:"Vue d'ensemble",analyses:'Analyses & courbes',documents:'Sources documentaires',medications:'Médicaments'})[tab];
 if(tab==='analyses')renderAnalyses();
 $('sidebar').classList.remove('open');
}
// Export documentaire non clinique : seules les valeurs déjà affichées sont reprises.
// Chaque ligne garde l'identifiant de la fiche source; aucun document original n'est intégré.
function exportConsultationSummary(){
 const o=state.overview,p=o?.patient;
 if(!p)return;
 const codes=['glucose','hba1c','systolic','diastolic','creatinine','egfr','cholesterol','weight','pulse'];
 const metrics=codes.map(code=>latestFor(code)).filter(Boolean);
 const receiptById=Object.fromEntries(state.receipts.map(r=>[r.id,r]));
 const metricsRows=metrics.map(m=>{
  const r=receiptById[m.source_id];
  const origin=r?`${r.document_kind} — ${r.document_date||'date de document inconnue'}`:'Fiche source indisponible';
  return `<tr><td>${esc(m.label)}</td><td>${esc(fmt(m.value))} ${esc(m.unit)}</td><td>${esc(niceDate(m.measured_at))}</td><td>${esc(statusLabel[m.status]||m.status)}</td><td>${esc(origin)}<br><small>Source ${esc(m.source_id)} · p. ${esc(m.page??'?')}</small></td></tr>`;
 }).join('');
 const medRows=(o.medications||[]).map(m=>`<tr><td>${esc(m.name)}</td><td>${esc(m.schedule)}</td><td>${esc(m.state==='historical'?'Historique (activité non confirmée)':m.state==='declared'?'Déclaré — à vérifier':'Statut : '+m.state)}</td></tr>`).join('');
 const eventRows=(o.events||[]).slice(0,8).map(e=>`<li>${esc(niceDate(e.at))} · ${esc(e.label)}</li>`).join('');
 const documentHtml=`<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Healthberg · Synthèse de démonstration</title><style>body{font:14px/1.55 system-ui,Arial,sans-serif;max-width:1000px;margin:36px auto;color:#1c2733;padding:0 16px}header{border-bottom:3px solid #147c8e;padding-bottom:18px}h1{font-size:24px;margin:4px 0}h2{font-size:17px;margin:28px 0 10px}small,footer{color:#627282}table{width:100%;border-collapse:collapse;font-size:12px}th,td{border:1px solid #cdd8de;text-align:left;padding:9px;vertical-align:top}th{background:#e9f4f5}.warn{padding:12px;background:#fff2df;border:1px solid #f0d29a}.brand{color:#126d7b;letter-spacing:.15em;font-weight:800}@media print{body{margin:0;max-width:none}tr{break-inside:avoid}}</style></head><body><header><div class="brand">HEALTHBERG / HEALTH INTELLIGENCE</div><h1>Synthèse de consultation — DÉMONSTRATION</h1><div>${esc(p.name)} · ${esc(p.age)} ans · ${esc(p.profile)}</div><small>Dossier fictif · dernier rendez-vous référencé : ${esc(niceDate(p.last_consultation))}</small></header><p class="warn"><strong>DONNÉES SYNTHÉTIQUES UNIQUEMENT.</strong> Document non médical, non validé et impropre à toute décision de soin. Les valeurs sont reprises sans calcul ni interprétation. Les originaux des sources ne sont pas conservés.</p><h2>Dernières valeurs documentées</h2><table><thead><tr><th>Paramètre</th><th>Valeur</th><th>Date de mesure</th><th>Statut</th><th>Provenance</th></tr></thead><tbody>${metricsRows||'<tr><td colspan="5">Aucune valeur</td></tr>'}</tbody></table><h2>Médicaments / historique, non assimilable à une prescription active</h2><table><thead><tr><th>Nom</th><th>Indications figurant dans les données</th><th>Statut</th></tr></thead><tbody>${medRows||'<tr><td colspan="3">Aucune information</td></tr>'}</tbody></table><h2>Événements documentés</h2><ul>${eventRows||'<li>Aucun événement</li>'}</ul><footer>Healthberg v0.2 · export local le ${esc(new Date().toLocaleDateString('fr-FR'))} · fichier généré uniquement côté navigateur. Une empreinte de source ne prouve pas son authenticité.</footer></body></html>`;
 const url=URL.createObjectURL(new Blob([documentHtml],{type:'text/html;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download=`healthberg_synthese_${p.id}_FICTIF.html`;link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1500);
}
function exportCsv(){const columns=['date','parametre','valeur','unite','statut','source_id','page','valeur_originale','unite_originale'];
 const rows=state.observations.map(o=>[o.measured_at,o.code,o.value,o.unit,o.status,o.source_id,o.page??'',o.original_value,o.original_unit]);
 const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
 const csv='\ufeff'+[columns,...rows].map(row=>row.map(quote).join(';')).join('\r\n');
 const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));link.download=`healthberg_${state.patientId}_DEMO.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
}
function openImport(){state.preview=null;state.file=null;$('fileInput').value='';$('uploadStatus').textContent='';$('reviewStatus').textContent='';$('syntheticAck').checked=false;$('patientAck').checked=false;$('uploadStep').classList.remove('hidden');$('reviewStep').classList.add('hidden');$('importOverlay').classList.remove('hidden');$('startExtraction').disabled=true}
function closeImport(){$('importOverlay').classList.add('hidden');state.file=null;state.preview=null}
function loadFile(file){if(!file)return;state.file=file;$('uploadArea').querySelector('strong').textContent=file.name;$('uploadArea').querySelector('span').textContent=`${(file.size/1024).toFixed(0)} Ko`; $('startExtraction').disabled=!$('syntheticAck').checked}
async function runPreview(){
 if(!state.file||!$('syntheticAck').checked)return;
 $('uploadStatus').textContent='Lecture du document…';$('startExtraction').disabled=true;
 try{const f=new FormData();f.append('file',state.file);f.append('patient_id',state.patientId);f.append('synthetic_ack','true');const data=await api('/api/documents/preview',{method:'POST',body:f});state.preview=data;
 $('uploadStep').classList.add('hidden');$('reviewStep').classList.remove('hidden');$('reviewPatient').textContent=data.patient_name;
 $('reviewMeta').textContent=`${data.page_count} page(s) · ${data.extraction_method} · ${data.candidates.length} mesure(s) · ${(data.medications||[]).length} prescription(s)`;
 $('reviewWarnings').innerHTML=data.warnings.map(w=>`<div class="notice">${esc(w)}</div>`).join('');
 $('reviewTable').innerHTML=data.candidates.map((c,i)=>`<tr data-candidate="${i}"><td><input type="checkbox" checked aria-label="Inclure la mesure ${esc(c.label)}"></td><td><strong>${esc(c.label)}</strong><br><small>Source : ${esc(c.original_value)} ${esc(c.original_unit)}</small></td><td><input type="number" step="any" value="${c.value}" aria-label="Valeur ${esc(c.label)}"></td><td>${esc(c.unit)}</td><td><input type="date" value="${esc(c.measured_at||'')}" aria-label="Date ${esc(c.label)}"></td><td>${c.page}</td></tr>`).join('');
 $('medReviewGroup').classList.toggle('hidden', !(data.medications||[]).length);
 $('reviewMeds').innerHTML=(data.medications||[]).map((m,i)=>`<tr data-medcandidate="${i}"><td><input type="checkbox" checked aria-label="Inclure le médicament"></td><td>${esc(m.name)}</td><td>${esc(m.strength)}</td><td><input type="text" maxlength="280" class="med-dir" value="${esc(m.directions)}" aria-label="Instructions de prescription"></td><td><input type="date" value="${esc(m.document_date||'')}" aria-label="Date de prescription"></td></tr>`).join('');
 $('reviewStatus').textContent=(data.candidates.length||(data.medications||[]).length)?'':'Aucune donnée extractible : vérification manuelle nécessaire.';
 }catch(e){$('uploadStatus').textContent=e.message}finally{$('startExtraction').disabled=false}
}
async function confirmPreview(){const p=state.preview;if(!p)return;if(!$('patientAck').checked){$('reviewStatus').textContent='Confirmez d’abord le patient et les valeurs.';return}
 const candidates=[];for(const row of document.querySelectorAll('[data-candidate]')){if(!row.querySelector('input[type="checkbox"]').checked)continue;const orig=p.candidates[Number(row.dataset.candidate)];const newValue=Number(row.querySelector('input[type="number"]').value);const date=row.querySelector('input[type="date"]').value;
 if(!date||!Number.isFinite(newValue)||row.querySelector('input[type="number"]').value===''){$('reviewStatus').textContent='Chaque valeur sélectionnée nécessite une date valide et un nombre.';return;}
 candidates.push({code:orig.code,label:orig.label,value:newValue,unit:orig.unit,measured_at:date+'T12:00:00+01:00',page:orig.page,original_value:orig.original_value,original_unit:orig.original_unit,context:orig.context})}
 const medications=[];for(const row of document.querySelectorAll('[data-medcandidate]')){if(!row.querySelector('input[type="checkbox"]').checked)continue;const orig=p.medications[Number(row.dataset.medcandidate)];const since=row.querySelector('input[type="date"]').value;const directions=row.querySelector('.med-dir').value; if(!since){$('reviewStatus').textContent='La date de prescription doit être renseignée.';return;} medications.push({name:orig.name,strength:orig.strength,directions,page:orig.page,since});}
 if(!candidates.length&&!medications.length){$('reviewStatus').textContent='Sélectionnez au moins une mesure ou prescription.';return}
 $('confirmImport').disabled=true;$('reviewStatus').textContent='Intégration en cours…';
 try{const r=await api('/api/documents/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({import_token:p.import_token,patient_id:p.patient_id,confirm_patient_identity:true,candidates,medications})});closeImport();await changePatient(state.patientId);setTab('analyses');}
 catch(e){$('reviewStatus').textContent=e.message}finally{$('confirmImport').disabled=false}
}
function installListeners(){
 document.querySelectorAll('[data-tab]').forEach(btn=>btn.addEventListener('click',()=>setTab(btn.dataset.tab)));
 $('metricSelect').addEventListener('change',e=>{state.metric=e.target.value;renderChartPanel()});
 $('periodSelect').addEventListener('change',e=>{state.period=e.target.value;renderChartPanel()});
 $('analysisMetricSelect').addEventListener('change',e=>{state.analysisMetric=e.target.value;renderAnalyses()});
 $('seeAnalyses').addEventListener('click',()=>setTab('analyses'));
 $('summaryButton').addEventListener('click',exportConsultationSummary);$('exportButton').addEventListener('click',exportCsv);
 for(const id of ['importButton','secondaryImportButton'])$(id).addEventListener('click',openImport);
 $('closeImport').addEventListener('click',closeImport);$('closeSource').addEventListener('click',()=>$('sourceOverlay').classList.add('hidden'));
 $('importOverlay').addEventListener('click',e=>{if(e.target.id==='importOverlay')closeImport()});$('sourceOverlay').addEventListener('click',e=>{if(e.target.id==='sourceOverlay')$('sourceOverlay').classList.add('hidden')});
 $('menuButton').addEventListener('click',()=>$('sidebar').classList.toggle('open'));
 $('uploadArea').addEventListener('click',()=>$('fileInput').click());$('fileInput').addEventListener('change',e=>loadFile(e.target.files[0]));
 $('syntheticAck').addEventListener('change',()=>{$('startExtraction').disabled=!$('syntheticAck').checked||!state.file});
 $('uploadArea').addEventListener('dragover',e=>{e.preventDefault();$('uploadArea').classList.add('dragover')});
 $('uploadArea').addEventListener('dragleave',()=>$('uploadArea').classList.remove('dragover'));
 $('uploadArea').addEventListener('drop',e=>{e.preventDefault();$('uploadArea').classList.remove('dragover');loadFile(e.dataTransfer.files[0])});
 $('startExtraction').addEventListener('click',runPreview);$('confirmImport').addEventListener('click',confirmPreview);
 $('resetImport').addEventListener('click',()=>{$('uploadStep').classList.remove('hidden');$('reviewStep').classList.add('hidden')});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeImport();$('sourceOverlay').classList.add('hidden');$('sidebar').classList.remove('open')}});
}
window.addEventListener('DOMContentLoaded',start);
