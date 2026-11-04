// Real browser test of a synthetic static report; no server and no packages.
import {spawn} from 'node:child_process';
import {mkdtempSync, writeFileSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const args=process.argv.slice(2), option=k=>args[args.indexOf(k)+1];
if(!args.includes('--browser')||!args.includes('--html'))throw Error('Usage: --browser EXECUTABLE --html SYNTHETIC_REPORT [--screenshot NEW_PNG]');
if(typeof WebSocket!=='function')throw Error('Node 22+ with built-in WebSocket is required');
const profile=mkdtempSync(path.join(tmpdir(),'eos-replay-ui-'));
const browser=spawn(option('--browser'),['--headless=new','--no-sandbox','--disable-gpu','--disable-background-networking','--disable-component-update','--disable-extensions','--disable-sync','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
let ws,seq=0;const pending=new Map(),errors=[],requests=[];
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
try{
 const endpoint=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('Browser startup timeout')),20000);browser.stderr.on('data',bytes=>{output+=bytes;const hit=output.match(/DevTools listening on (ws:\/\/127\.0\.0\.1:\d+\/\S+)/);if(hit){clearTimeout(timer);resolve(hit[1]);}});browser.on('error',reject);browser.on('exit',code=>reject(Error('Browser exited before connection: '+code)));});
 ws=new WebSocket(endpoint);await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 ws.addEventListener('message',e=>{const m=JSON.parse(String(e.data));if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);else if(m.method==='Log.entryAdded'&&m.params.entry.level==='error')errors.push(m.params.entry.text);else if(m.method==='Network.requestWillBeSent'&&!/^(file:|data:|about:)/.test(m.params.request.url))requests.push(m.params.request.url);});
 const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++seq;const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},15000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});
 const {targetId}=await call('Target.createTarget',{url:'about:blank'});
 const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
 for(const method of ['Page.enable','Runtime.enable','Network.enable','Log.enable'])await call(method,{},sessionId);
 await call('Emulation.setDeviceMetricsOverride',{width:1280,height:1100,deviceScaleFactor:1,mobile:false},sessionId);
 await call('Page.navigate',{url:pathToFileURL(path.resolve(option('--html'))).href},sessionId);
 const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true},sessionId);if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;};


 const sidecar=JSON.parse(readFileSync(option('--sidecar'),'utf8'));
 const check=async expression=>{if(!await evaluate(expression))throw Error('Replay UI assertion failed: '+expression)};
 let loaded=false;for(let i=0;i<100;i++){if(await evaluate("document.querySelectorAll('#slots tr').length>0")){loaded=true;break}await sleep(100)}
 if(!loaded)throw Error('Replay dashboard did not render: '+errors.join('; '));
 const screenshot=async suffix=>{if(args.includes('--screenshot')){const p=option('--screenshot').replace(/\.png$/,suffix+'.png');const result=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false},sessionId);writeFileSync(p,Buffer.from(result.data,'base64'),{flag:'wx'})}};
 const results=[];
 for(const p of sidecar.plans){
  await evaluate(`document.querySelector('[data-version="${p.source_solution_sha256}"]').click()`);
  const checks=await evaluate(`(()=>{const p=${JSON.stringify(p)},near=(a,b)=>Math.abs(a-b)<1e-7;
    const points=[...document.querySelectorAll('#battery polyline')].flatMap(n=>n.getAttribute('points').trim().split(' ').filter(Boolean).map(v=>v.split(',').map(Number)));
    const pv=p.summary.pv_charge_internal_wh/1000,grid=p.summary.grid_charge_internal_wh/1000,dis=p.summary.discharge_internal_wh/1000;
    const shown=(id,v,d=2)=>document.querySelector('#'+id).textContent.startsWith(v.toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d}));
    return {soc_points_at_interval_start:points.length===p.control_slots&&points.every((v,i)=>near(v[0],48+902*i/p.control_slots)&&near(v[1],195-p.slots[i].soc_start_percent*1.65)),
      pv_correct:shown('pv-energy',pv),grid_correct:shown('grid-energy',grid),discharge_correct:shown('dis-energy',dis),
      efc_internal_correct:shown('cycles',p.summary.equivalent_full_cycles,3),
      charge_windows:document.querySelector('#charge-windows').textContent===String(p.summary.charge_windows.length),
      discharge_windows:document.querySelector('#discharge-windows').textContent===String(p.summary.discharge_windows.length),
      marked_posthoc:document.querySelector('#flow-warning').textContent.includes('Nachträglich berechnete'),
      no_false_success:document.querySelector('#status-value').textContent!=='Erfolgreich',
      original_rows:document.querySelectorAll('#slots tr').length===p.control_slots,
      no_clipping:[...document.querySelectorAll('#battery rect')].every(n=>Number(n.getAttribute('y'))>=0&&Number(n.getAttribute('y'))+Number(n.getAttribute('height'))<=240),
      original_detail:(()=>{document.querySelector('#slots tr').click();return document.querySelector('#raw').textContent.includes('replay_sidecar_sha256')&&document.querySelector('#raw').textContent.includes('original_replay_values')})()};})()`);
  if(!Object.values(checks).every(Boolean))throw Error('Incorrect replay view: '+JSON.stringify(checks));
  if(p.start_utc.startsWith('2026-03-29')||p.start_utc.startsWith('2026-10-25')){
   await check("(()=>{const rows=[...document.querySelectorAll('#slots tr td:first-child')].map(n=>n.textContent);return rows.some(s=>s.includes('MESZ'))&&rows.some(s=>s.includes('MEZ'))})()");
   if(p.start_utc.startsWith('2026-03-29'))await check("![...document.querySelectorAll('#slots tr td:first-child')].some(n=>n.textContent.includes('02:'))");
  }
  results.push({date:p.start_utc.slice(0,10),seconds:p.interval_seconds,...checks});
  await screenshot('-plan-'+p.start_utc.slice(0,10));
 }
 if(args.includes('--stack-regression')){
  await check("data.synthetic_only===true");
  await check("(()=>{const saved=selected.rows[0].flow;selected.rows[0].flow={...saved,pv_wh:1000,grid_wh:1000,unknown_wh:0,charge_wh:2000};render();const ok=[...document.querySelectorAll('#battery rect')].every(n=>+n.getAttribute('y')>=0);selected.rows[0].flow=saved;render();return ok})()");
 }
 await screenshot('-desktop');
 await evaluate("document.querySelector('#model-coverage').checked=true;document.querySelector('#model-coverage').dispatchEvent(new Event('change'))");
 for(const days of [7,30]){
  await evaluate(`document.querySelector('[data-days="${days}"]').click()`);
  await check("document.querySelector('#selected-label').textContent.includes('Claims ungeprüft')");
  await check("document.querySelector('#charge-windows').textContent==='Nicht belegt'&&document.querySelector('#discharge-windows').textContent==='Nicht belegt'&&document.querySelector('#cycles').textContent==='Nicht belegt'");
  await check("document.querySelectorAll('#battery rect').length>0");
 }
 await screenshot('-history');
 await evaluate("document.querySelector('#model-coverage').checked=false;document.querySelector('#model-coverage').dispatchEvent(new Event('change'))");
 await check("document.querySelectorAll('#slots tr').length===0&&document.querySelector('#charge-windows').textContent==='Nicht belegt'&&document.querySelector('#cycles').textContent==='Nicht belegt'");
 await evaluate("document.querySelectorAll('#history button')[0].click()");
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:1100,deviceScaleFactor:1,mobile:true},sessionId);
 await check('document.documentElement.scrollWidth<=390');
 await screenshot('-mobile');
 if(errors.length||requests.length)throw Error('Browser/network error: '+JSON.stringify({errors,requests}));
 const output={passed:true,plans:results,ranges:[1,7,30],empty_and_partial_unknown:true,mobile_width:390,external_requests:requests.length,browser_errors:errors.length};
 if(args.includes('--report'))writeFileSync(option('--report'),JSON.stringify(output,null,2),{flag:'wx'});
 console.log(JSON.stringify(output));
 await call('Browser.close');
}finally{
 if(ws)ws.close();browser.kill();
 await sleep(700);
 const resolved=path.resolve(profile);
 if(path.dirname(resolved)!==path.resolve(tmpdir())||!path.basename(resolved).startsWith('eos-replay-ui-'))throw Error('Unsafe browser profile cleanup path');
 rmSync(resolved,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}
