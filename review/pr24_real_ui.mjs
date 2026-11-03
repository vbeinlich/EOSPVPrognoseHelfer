// Real browser test of a synthetic static report; no server and no packages.
import {spawn} from 'node:child_process';
import {mkdtempSync, writeFileSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const args=process.argv.slice(2), option=k=>args[args.indexOf(k)+1];
if(!args.includes('--browser')||!args.includes('--html'))throw Error('Usage: --browser EXECUTABLE --html SYNTHETIC_REPORT [--screenshot NEW_PNG]');
if(typeof WebSocket!=='function')throw Error('Node 22+ with built-in WebSocket is required');
const profile=mkdtempSync(path.join(tmpdir(),'eos-pr24-real-ui-'));
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


 const expected=JSON.parse(readFileSync(option('--expected'),'utf8')).originals;
 let loaded=false;for(let i=0;i<100;i++){if(await evaluate("document.querySelectorAll('#slots tr').length===24")){loaded=true;break}await sleep(100)}
 if(!loaded)throw Error('Real original dashboard did not render: '+errors.join('; '));
 const results=[];
 for(const original of expected){
  const e=original.ui_expected;
  await evaluate(`document.querySelector('[data-version="${original.source_sha256}"]').click()`);
  const view=await evaluate(`(()=>{const e=${JSON.stringify(e)}, close=(a,b)=>Math.abs(a-b)<1e-7;
   const pts=id=>[...document.querySelectorAll(id+' polyline')].flatMap(n=>n.getAttribute('points').trim().split(' ').filter(Boolean).map(p=>p.split(',').map(Number)));
   const s=pts('#battery'),forecasts=[['#price-chart',e.price,.00001],['#pv-chart',e.pv,1000],['#load-chart',e.load,1000]];
   const yOK=s.length===e.soc.length&&s.every((p,i)=>close(p[1],195-e.soc[i]*1.65));
   const startOK=s.every((p,i)=>close(p[0],48+902*i/e.soc.length));
   const curvesOK=forecasts.every(([id,values,divisor])=>{const points=pts(id),v=values.map(x=>x/divisor),lo=Math.min(0,...v),hi=Math.max(1,...v);return points.length===v.length&&points.every((p,i)=>close(p[1],140-(v[i]-lo)/(hi-lo)*105))});
   return {original_rows:document.querySelectorAll('#slots tr').length,soc_points:s.length,soc_values_correct:yOK,soc_at_native_start_timestamp:startOK,forecast_values_correct:curvesOK,
    colored_energy_bars:document.querySelectorAll('#battery rect[fill="#37d597"],#battery rect[fill="#5a9cff"],#battery rect[fill="#ffad57"]').length,
    pv:document.querySelector('#pv-energy').textContent,grid:document.querySelector('#grid-energy').textContent,discharge:document.querySelector('#dis-energy').textContent,cycles:document.querySelector('#cycles').textContent,
    first_time:document.querySelector('#slots tr td').textContent,status:document.querySelector('#status-value').textContent};})()`);
  // Record counterexamples instead of stopping the independent audit.
  results.push({date:original.start_utc.slice(0,10),...view});
 }
 await evaluate(`document.querySelector('[data-days="7"]').click()`);
 const empty=await evaluate("({rows:document.querySelectorAll('#slots tr').length,charge:document.querySelector('#charge-windows').textContent,discharge:document.querySelector('#discharge-windows').textContent})");
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:true},sessionId);
 const mobile=await evaluate('document.documentElement.scrollWidth<=390');
 if(errors.length||requests.length)throw Error('Browser/network errors: '+JSON.stringify({errors,requests}));
 let stacked=null;
 if(args.includes('--stacked-html')){
  await call('Page.navigate',{url:pathToFileURL(path.resolve(option('--stacked-html'))).href},sessionId);
  for(let i=0;i<100;i++){if(await evaluate("document.querySelectorAll('#battery rect').length>0"))break;await sleep(100)}
  await evaluate("document.querySelectorAll('#history button')[0].click()");
  stacked=await evaluate("({minimum_bar_y:Math.min(...[...document.querySelectorAll('#battery rect')].map(n=>Number(n.getAttribute('y')))),viewbox_top:0})");
 }
 const report={real_originals:true,results,empty_history_windows:empty,mobile_no_page_overflow:mobile,stacked_charge_counterexample:stacked,browser_errors:errors.length,external_requests:requests.length};
 if(args.includes('--output'))writeFileSync(option('--output'),JSON.stringify(report,null,2),{flag:'w'});
 console.log(JSON.stringify(report));
 await call('Browser.close');
}finally{
 if(ws)ws.close();browser.kill();
 await sleep(700);
 const resolved=path.resolve(profile);
 if(path.dirname(resolved)!==path.resolve(tmpdir())||!path.basename(resolved).startsWith('eos-pr24-real-ui-'))throw Error('Unsafe browser profile cleanup path');
 rmSync(resolved,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}
