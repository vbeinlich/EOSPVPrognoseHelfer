"""Self-contained local HTML, fixed scripts/styles, sanitized data via textContent."""

import base64
import hashlib
import json

CSS = r"""
:root{color-scheme:light;--ink:#173047;--muted:#526879;--line:#dbe5eb;--teal:#007f78;--bg:#f3f7f9}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
header{padding:25px max(24px,calc((100vw - 1240px)/2));background:#173047;color:white}h1{font-size:27px;margin:3px 0}
header p{margin:5px 0;color:#d5e8ec}.pill{font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#bcebe1}
main{max-width:1288px;padding:24px;margin:auto}h2{font-size:19px;margin:0 0 12px}h3{font-size:15px}
section,.card{background:white;border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:18px}
.notice{border-left:4px solid #e8ac40;background:#fff8e9;padding:14px 18px;border-radius:6px;margin-bottom:18px}
.muted,small{color:var(--muted)}.toolbar{display:flex;gap:18px;align-items:center;flex-wrap:wrap}.toolbar label{display:flex;flex-direction:column;gap:5px;font-weight:600}
select{font:inherit;padding:9px;border:1px solid #a8bbc6;border-radius:6px;max-width:100%;background:white;color:var(--ink)}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card strong{display:block;font-size:25px;margin:6px 0}
.meta{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}.tag{font-size:12px;border-radius:5px;background:#edf5f5;padding:4px 8px}
code{font-size:12px;overflow-wrap:anywhere}.scroll{overflow:auto;max-height:590px;border:1px solid var(--line);border-radius:7px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:10px 11px;border-bottom:1px solid var(--line);white-space:nowrap}
th{position:sticky;top:0;background:#eaf1f5;z-index:1}tbody tr{cursor:pointer}tbody tr:hover,tbody tr.selected{background:#e7f5f2}
.phase{font-size:11px;color:var(--muted)}#timeline{width:100%;height:180px}.svglabel{font:12px system-ui;fill:var(--muted)}
button{cursor:pointer;font:inherit;border:1px solid #94b7b6;border-radius:6px;background:#e9f6f2;color:#005e59;padding:7px 13px}
details{margin:13px 0}summary{cursor:pointer;font-weight:600}dl{display:grid;grid-template-columns:minmax(150px,1fr) 2fr;gap:7px 18px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}
.detail{border-left:4px solid var(--teal);padding:15px 18px;background:#f1f8f7;margin:15px 0}.empty{padding:25px;color:var(--muted)}
footer{padding:8px 0 25px;color:var(--muted);font-size:12px}@media(max-width:720px){main{padding:12px}.cards{grid-template-columns:1fr}.card{margin-bottom:0}header{padding:18px}h1{font-size:23px}dl{grid-template-columns:1fr}dd{margin-bottom:8px}}
"""

JS = r"""
'use strict';
const report=JSON.parse(document.getElementById('report-data').textContent);
const el=id=>document.getElementById(id), make=(tag,text,parent)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(parent)parent.append(n);return n;};
const val=v=>v===null||v===undefined?'—':typeof v==='number'?new Intl.NumberFormat('de-DE',{maximumFractionDigits:6}).format(v):String(v);
const phase={control:'Steuerhorizont',tail:'Tail / Lookahead',prefix:'Alter Mitternachts-Präfix',undeclared:'Zeitraum nicht deklariert'};
const dl=(node,items)=>{const d=make('dl',undefined,node);for(const [k,v] of items){make('dt',k,d);make('dd',val(v),d);}return d;};
const plans=report.plans;let active=null;
el('sync').textContent='Aktueller Sync: '+report.latest_sync_status+' · '+report.timezone;
el('global').textContent=(report.latest_sync_status==='waiting-publication'?'Neue Preise noch nicht veröffentlicht. Vorhandene historische Pläne bleiben sichtbar. ':'')+report.warnings.join(' ');
if(!el('global').textContent)el('global').hidden=true;
plans.forEach((p,i)=>make('option',(p.start_local||'Zeit unbekannt')+' · '+p.claim_status+(p.solution_status==='unreadable'?' · Lösung fehlt/ungültig':'')+' · '+p.version.slice(0,12),el('plans')).value=i);
const preferred=plans.findIndex(p=>p.claim_status==='succeeded'&&p.rows.length);el('plans').value=preferred<0?0:preferred;
function detail(p,r,q){
 const node=el('detail');node.replaceChildren();make('h3','Slot-Details · Originalindex '+r.source_index,node);
 if(p.comparison?.status==='calculated'){
  for(const [key,label] of [['baseline','E3/DC-Referenz'],['genetic','GENETIC']]){
   const s=p.comparison.slots[key].find(x=>x.start_utc===r.start_utc);if(!s)continue;
   make('h3',label+' · simuliertes Originalintervall',node);
   dl(node,[['Netzbezug',val(s.grid_import_wh)+' Wh'],['Einspeisung',val(s.grid_export_wh)+' Wh'],['SoC Beginn / Ende',val(s.soc_start_percent)+' / '+val(s.soc_end_percent)+' %'],['Netzbezugskosten',val(s.grid_cost_eur)+' EUR'],['Verschleiß',val(s.wear_eur)+' EUR'],['Einspeiseerlös',val(s.feed_in_revenue_eur)+' EUR']]);
  }
  make('p','Energiemengen gelten für das ganze Originalintervall; Viertelstunden erzeugen keine zusätzlichen Messwerte.',node);
 }
 dl(node,[['Ausgewähltes Anzeigeintervall',q?q.local+' → '+q.end_local:'Originalraster'],['Originalentscheidung',r.local?r.local+' → '+r.end_local:'Zeitbasis nicht belegbar'],['UTC-Intervall',r.start_utc?r.start_utc+' → '+r.end_utc:'Nicht zugeordnet'],['Einordnung',phase[r.phase]],['Gespeicherte Freigaben',r.permissions.join(' · ')]]);
 make('p','Faktoren und Freigaben zeigen keine tatsächliche Lade-/Entladeleistung. Modellwerte unten gehören zum gesamten Originalslot; Viertelstunden sind keine zusätzlichen Entscheidungen.',node);
 dl(node,Object.entries(r.controls).map(([k,v])=>[k,val(v)]));
 if(Object.keys(r.model).length){make('h3','Gespeicherte Simulationswerte · Originalslot',node);dl(node,Object.entries(r.model).map(([k,v])=>[report.model_fields[k][0],val(v)+' '+report.model_fields[k][1]]));}
 if(q&&p.inputs.status==='verified')dl(node,[['Archivierter Preis',q.price_eur_kwh===undefined?'Für diesen Slot nicht vorhanden':val(q.price_eur_kwh)+' EUR/kWh'],['Archivierte PV-Prognose',q.pv_w===undefined?'Für diesen Slot nicht vorhanden':val(q.pv_w)+' W']]);
}
function chart(p){
 const svg=el('timeline');svg.replaceChildren();svg.setAttribute('viewBox','0 0 1180 180');
 const keys=['ac_charge','dc_charge','discharge_allowed'];const left=160,width=1000,count=p.rows.length;
 const add=(tag,attrs,text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;svg.append(n);return n;};
 keys.forEach((key,j)=>{add('text',{x:0,y:27+j*39,class:'svglabel'},p.controls[key]?p.controls[key][0]:key);p.rows.forEach((r,i)=>{const v=r.controls[key];const n=add('rect',{x:left+i*width/Math.max(1,count),y:10+j*39,width:Math.max(.5,width/Math.max(1,count)-1),height:26,rx:2,fill:v===undefined||v===null?'#dbe2e8':v>0?['#137c8b','#5b9b75','#ba8031'][j]:'#eff3f5',tabindex:0,role:'button','aria-label':'Originalslot '+i+' '+key+' '+val(v)});n.addEventListener('click',()=>detail(p,r,r.quarters[0]));n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();detail(p,r,r.quarters[0]);}});});});
 if(count){add('text',{x:left,y:150,class:'svglabel'},p.rows[0].local||'Keine Zeitzuordnung');add('text',{x:1160,y:174,'text-anchor':'end',class:'svglabel'},p.rows[count-1].end_local||'Originalindizes');}
}
function rows(p){
 const table=el('slots');table.replaceChildren();const header=make('tr',undefined,make('thead',undefined,table));
 const verified=p.inputs.status==='verified';const columns=['Lokalzeit inkl. Offset','Quelle / Horizont',...Object.values(p.controls).map(x=>x[0]),...(verified?['Preis EUR/kWh','PV W']:[])];columns.forEach(x=>make('th',x,header));
 const body=make('tbody',undefined,table);let count=0;
 for(const r of p.rows){const quarters=el('grid').value==='quarter'&&r.quarters.length?r.quarters:[null];for(const q of quarters){count++;const tr=make('tr',undefined,body);tr.tabIndex=0;
 make('td',q?q.local:(r.local||'Zeit nicht belegbar'),tr);make('td','#'+r.source_index+' · '+(phase[r.phase]||'Nicht zugeordnet'),tr);
 for(const k of Object.keys(p.controls))make('td',val(r.controls[k]),tr);
 if(verified){make('td',q?val(q.price_eur_kwh):'Im 15-Minuten-Raster öffnen',tr);make('td',q?val(q.pv_w):'Im 15-Minuten-Raster öffnen',tr);}
 const select=()=>{for(const n of body.querySelectorAll('.selected'))n.classList.remove('selected');tr.classList.add('selected');detail(p,r,q);};tr.addEventListener('click',select);tr.addEventListener('keydown',e=>{if(e.key==='Enter')select();});}}
 el('row-count').textContent=p.source_slots+' gespeicherte Quellslots · '+count+' Anzeigezeilen · Quellraster '+(p.interval_seconds?p.interval_seconds/60+' min':'unbekannt')+'. Bei 60-Minuten-Daten wiederholt die Viertelstundenansicht dieselbe Originalentscheidung mit demselben Index.';
 if(!count)make('p','Keine auswertbaren Steuerarrays vorhanden.',el('detail'));
}
function extra(p){
 const n=el('extra');n.replaceChildren();
 const model=make('details',undefined,n);make('summary','Modellzusammenfassung und Terminalwert',model);
 dl(model,Object.entries(p.summary).map(([k,v])=>[report.summary_fields[k][0],val(v)+' '+report.summary_fields[k][1]]));
 dl(model,Object.entries(p.terminal).map(([k,v])=>[k,val(v)]));make('p','Terminalwert wird hier weder erneut gutgeschrieben noch als Ersparnis verrechnet. Nur vorhandene Originalwerte.',model);
 if(p.tail.length){const d=make('details',undefined,n);make('summary',p.tail.length+' gespeicherte Tail-Entscheidungen · diagnostischer Lookahead, kein ausführbarer Steuerplan',d);const t=make('table',undefined,d);const h=make('tr',undefined,t);['Zeit','Originalindex',...Object.values(report.tail_fields).map(v=>v[0]),'Modell-SoC Beginn %','Modell-SoC Ende %'].forEach(x=>make('th',x,h));for(const r of p.tail){const tr=make('tr',undefined,t);[r.local||'Nicht zugeordnet',r.source_index,...Object.values(r.controls).map(val),val(r.soc_start_percentage),val(r.soc_end_percentage)].forEach(x=>make('td',x,tr));}}
 if(p.appliances.length){const d=make('details',undefined,n);make('summary','Gespeicherte Geräte-Starttermine · Namen anonymisiert',d);for(const a of p.appliances)make('p','Gerät '+a.device+': '+a.local+' · Termin verfehlt: '+(a.deadline_missed===null?'unbekannt':a.deadline_missed?'ja':'nein'),d);}
 if(p.appliance_running.length){const d=make('details',undefined,n);make('summary','Gespeicherte Geräte-Belegung · Modellwerte ab Planstart',d);for(const a of p.appliance_running)make('p','Gerät '+a.device+' · Start '+(a.start_utc||'unbekannt')+' · Raster '+val(a.interval_seconds)+' s: '+a.values.map(v=>v===null?'?':v?'an':'aus').join(', '),d);}
 if(Object.keys(p.unmapped_ev_arrays).length){const d=make('details',undefined,n);make('summary','Zusätzliche EV-Arrays ohne belegte Zeitbasis',d);for(const [k,v]of Object.entries(p.unmapped_ev_arrays))make('p',k+': '+v.map(val).join(', '),d);}
 if(p.legacy_washingstart!==null&&p.legacy_washingstart!==undefined)make('p','Legacy washingstart (Originalzahl, keine Zeitzuordnung): '+val(p.legacy_washingstart),n);
 const proof=make('details',undefined,n);make('summary','Herkunft und Datenbindung',proof);dl(proof,[['Version',p.version],['Quelldatei',p.file],['Lösungs-SHA256',p.solution_sha256||'nicht verfügbar'],['Claim-Zeitpunkt',p.claimed_at_utc||'nicht zugeordnet'],['Eingaben',p.inputs.message],['Archiv-SHA256',p.inputs.archive_sha256||'nicht vorhanden'],['Originale Erhebung',p.inputs.captured_at_utc||'nicht vorhanden']]);
 if(p.inputs.status==='verified')dl(proof,[['Historischer Anfangs-SoC',val(p.inputs.initial_soc_percent)+' %'],['Quellzeitpunkt SoC',p.inputs.soc_source_timestamp],['Aktuelle Frische geprüft','nein']]);
}
function economics(p){
 const c=p.comparison,n=el('comparison');n.replaceChildren();
 const ok=c?.status==='calculated';
 el('baseline-cost').textContent=ok?val(c.baseline.adjusted_cost_eur)+' EUR':'Nicht berechenbar';
 el('genetic-cost').textContent=ok?val(c.genetic.adjusted_cost_eur)+' EUR':'Nicht berechenbar';
 el('saving').textContent=ok?val(c.additional_savings_eur)+' EUR'+(c.additional_savings_percent===null?'':' · '+val(c.additional_savings_percent)+' %'):'Nicht berechenbar';
 make('h2','Wirtschaftlichkeit · prognostizierter Modellvergleich',n);
 make('p',c?.message||'Nicht berechenbar: historische Vergleichseingaben fehlen.',n);
 if(!ok)return;
 make('p','Vereinfachter E3/DC-Eigenverbrauch: PV-Überschuss laden, Hausbedarf aus Batterie decken, keine Netzladung. Beide Szenarien nutzen dieselbe EOS-Physik und dieselbe gespeicherte Endwertkurve. Eingaben stammen aus dem Plan, Quellfrische ist damit nicht unabhängig nachgewiesen.',n);
 const table=make('table',undefined,n),h=make('tr',undefined,table);
 ['Kostenbestandteil / Energie','E3/DC-Referenz','GENETIC'].forEach(x=>make('th',x,h));
 for(const [key,label,unit] of [['grid_cost_eur','Netzbezug','EUR'],['feed_in_revenue_eur','Einspeiseerlös (abziehen)','EUR'],['wear_eur','Batterieverschleiß','EUR'],['operating_cost_eur','Betriebskosten vor Endwert','EUR'],['terminal_credit_eur','Endwert (abziehen; kann negativ sein)','EUR'],['adjusted_cost_eur','Kosten einschließlich identischem Endwertmodell','EUR'],['grid_kwh','Netzbezug','kWh'],['feed_in_kwh','Einspeisung','kWh'],['losses_kwh','Verluste, bereits in Energieflüssen enthalten','kWh'],['end_soc_percent','SoC am tatsächlichen Kontrollende','%'],['end_usable_ac_kwh','Nutzbare Endenergie oberhalb Minimum','kWh']]){
  const r=make('tr',undefined,table);[label,val(c.baseline[key])+' '+unit,val(c.genetic[key])+' '+unit].forEach(x=>make('td',x,r));
 }
 make('p','Verluste werden nicht nochmals als Eurobetrag addiert. Die Endbewertung erfolgt genau einmal je Szenario. Negative Mehrersparnis bedeutet einen Modellnachteil; Prozentwerte entfallen bei nicht positiven Referenzkosten.',n);
 const d=make('details',undefined,n);make('summary','SoC und Netzbezug im gemeinsamen Originalraster',d);
 const t=make('table',undefined,d),head=make('tr',undefined,t);['Lokaler Slot','Referenz Netzbezug Wh','GENETIC Netzbezug Wh','Referenz End-SoC %','GENETIC End-SoC %','PV Wh','Last Wh','Preis EUR/kWh'].forEach(x=>make('th',x,head));
 c.slots.baseline.forEach((b,i)=>{const g=c.slots.genetic[i],r=make('tr',undefined,t);[p.rows[i]?.local||b.start_utc,b.grid_import_wh,g.grid_import_wh,b.soc_end_percent,g.soc_end_percent,b.pv_wh,b.load_wh,b.price_eur_kwh].forEach(x=>make('td',val(x),r));});
 if(c.sensitivity?.status==='calculated'){
  const s=make('details',undefined,n);make('summary','Isolierter Last-Annahmetest: 8.000 → 11.251 kWh',s);make('p',c.sensitivity.message,s);
  dl(s,[['Referenz inkl. Endwert',val(c.sensitivity.baseline.adjusted_cost_eur)+' EUR'],['Unveränderte GENETIC-Freigaben inkl. Endwert',val(c.sensitivity.genetic.adjusted_cost_eur)+' EUR'],['Modell-Mehrersparnis unter Annahme',val(c.sensitivity.additional_savings_eur)+' EUR']]);
 }
 make('p','Native Wiedergabe des Originals bestätigt · Eingabehash '+c.input_sha256+' · keine neue GENETIC-Optimierung.',n);
}
function show(){
 const p=plans[Number(el('plans').value)];active=p;if(!p){el('empty').hidden=false;el('content').hidden=true;return;}
 el('empty').hidden=true;el('content').hidden=false;el('cost').textContent=p.summary.total_costs===undefined||p.summary.total_costs===null?'Nicht gespeichert':val(p.summary.total_costs)+' EUR';
 const basis={run_relative:'ab Planstart',legacy_midnight_explicit_timezone:'Mitternachts-Präfix, Quellzeitzone bestätigt',unproven:'nicht belegbar'};
 el('meta').replaceChildren();[p.claim_status,p.start_local||'Startzeit unbekannt','Zeitbasis: '+(basis[p.time_basis]||'unbekannt'),'Steuerhorizont '+val(p.control_hours)+' h / Tail '+val(p.effective_tail_hours)+' h'].forEach(x=>{const n=make('span',x,el('meta'));n.className='tag';});
 el('quality').textContent=[...p.warnings,p.inputs.message].join(' ');el('detail').replaceChildren();chart(p);rows(p);extra(p);economics(p);if(p.rows.length)detail(p,p.rows[0],p.rows[0].quarters[0]);
}
el('plans').addEventListener('change',show);el('grid').addEventListener('change',()=>{if(active)rows(active);});show();
"""


def digest(text):
    return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()


def render(data):
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    policy = ("default-src 'none'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'; "
              "object-src 'none'; frame-src 'none'; script-src 'sha256-"+digest(JS)+"'; style-src 'sha256-"+digest(CSS)+"'")
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{policy}"><title>EOS GENETIC · Lokaler Plan-Inspector</title><style>{CSS}</style></head>
<body><header><div class="pill">Phase 2 · Offline-Modellvergleich · keine Gerätesteuerung</div><h1>Gespeicherte GENETIC-Pläne</h1>
<p>Originalentscheidungen verstehen. Keine neue Optimierung, keine Live-Messung.</p></header><main>
<p id="sync" class="muted"></p><div id="global" class="notice"></div><section><div class="toolbar"><label>Gespeicherter Plan<select id="plans" aria-label="Gespeicherten Plan auswählen"></select></label>
<label>Anzeige<select id="grid"><option value="quarter">15-Minuten-Ansicht</option><option value="native">Originalraster</option></select></label></div><div id="meta" class="meta"></div></section>
<div id="empty" class="empty" hidden>Keine gespeicherten Pläne vorhanden.</div><div id="content">
<div class="cards"><div class="card">E3/DC-Referenzkosten<strong id="baseline-cost">Nicht berechenbar</strong><small>Modellkosten einschließlich gemeinsamer Endwertbewertung</small></div>
<div class="card">GENETIC-Kosten<strong id="genetic-cost">Nicht berechenbar</strong><small>Modellkosten einschließlich derselben Endwertbewertung</small></div><div class="card">Prognostizierte Mehrersparnis<strong id="saving">Nicht berechenbar</strong><small>Referenz minus GENETIC · keine realisierte Ersparnis</small></div></div>
<section id="comparison"></section><p>Im Original gespeicherte Modellkosten vor Endwert: <span id="cost"></span></p>
<section><h2>Freigaben im Originalraster</h2><p class="muted">Farbflächen zeigen Faktoren/Freigaben, keine kW. Auswahl öffnet den Originalslot.</p><svg id="timeline" role="img" aria-label="Zeitachse gespeicherter Steuerfaktoren"></svg>
<div id="quality" class="notice"></div><p id="row-count" class="muted"></p><div class="scroll"><table id="slots"></table></div><div id="detail" class="detail" aria-live="polite"></div></section>
<section><h2>Weitere gespeicherte Ergebnisse</h2><div id="extra"></div></section></div>
<footer>Private lokale HTML-Datei. Keine Netzwerkressourcen, keine Anlagen-API und kein Tracking. Daten nur für diese private Diagnose verwenden.</footer>
</main><script type="application/json" id="report-data">{payload}</script><script>{JS}</script></body></html>'''
