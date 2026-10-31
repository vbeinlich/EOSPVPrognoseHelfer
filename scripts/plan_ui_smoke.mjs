// Real browser test of a synthetic static report; no server and no packages.
import {spawn} from 'node:child_process';
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const args=process.argv.slice(2), option=k=>args[args.indexOf(k)+1];
if(!args.includes('--browser')||!args.includes('--html'))throw Error('Usage: --browser EXECUTABLE --html SYNTHETIC_REPORT [--screenshot NEW_PNG]');
if(typeof WebSocket!=='function')throw Error('Node 22+ with built-in WebSocket is required');
const profile=mkdtempSync(path.join(tmpdir(),'eos-plan-ui-'));
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
 let loaded=false;for(let i=0;i<120;i++){if(await evaluate("document.querySelectorAll('#slots tbody tr').length===96")){loaded=true;break;}await sleep(100);}
 if(!loaded)throw Error('Static report did not render its 96 quarter-hour rows: '+errors.join('; '));
 const check=async expression=>{if(!await evaluate(expression))throw Error('UI assertion failed: '+expression);};
 await check("document.querySelectorAll('#plans option').length==="+(args.includes('--economic')?'1':'2'));
 await check("document.querySelector('#sync').textContent.includes('waiting-publication')");
 if(args.includes('--economic')){
  await check("[...document.querySelectorAll('.card strong')].every(n=>n.textContent.includes('EUR'))");
  await check("document.querySelector('#comparison').textContent.includes('Batterieverschleiß')");
  await check("document.querySelector('#comparison').textContent.includes('11.251')");
  await check("document.querySelector('#comparison table').rows.length===12");
 }else await check("[...document.querySelectorAll('.card strong')].filter(n=>n.textContent==='Nicht berechenbar').length===3");
 await check("(()=>{const d=JSON.parse(document.querySelector('#report-data').textContent);const i=d.plans.findIndex(p=>p.interval_seconds===3600);const s=document.querySelector('#plans');s.value=i;s.dispatchEvent(new Event('change'));return document.querySelectorAll('#slots tbody tr').length===96;})()");
 await check("(()=>{const s=document.querySelector('#grid');s.value='native';s.dispatchEvent(new Event('change'));return document.querySelectorAll('#slots tbody tr').length===24;})()");
 await check("document.querySelectorAll('#timeline rect').length===72");
 await check("(()=>{document.querySelector('#slots tbody tr').click();return document.querySelector('#detail').textContent.includes('Originalindex 0')&&document.querySelector('#detail').textContent.includes('ac_charge');})()");
 await check("document.querySelector('#quality').textContent.includes('"+(args.includes('--economic')?'Offline-Projektion':'Historische Eingabe nicht belegbar')+"')");
 if(errors.length)throw Error('Browser errors: '+errors.join('; '));
 if(requests.length)throw Error('Unexpected page network requests');
 if(args.includes('--screenshot')){const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false},sessionId);writeFileSync(option('--screenshot'),Buffer.from(shot.data,'base64'),{flag:'wx'});}
 console.log(JSON.stringify({passed:true,real_browser:true,static_file:true,plans:args.includes('--economic')?1:2,economic:args.includes('--economic'),quarter_rows:96,native_hour_rows:24,external_requests:requests.length,browser_errors:errors.length}));
 await call('Browser.close');
}finally{
 if(ws)ws.close();browser.kill();
 await sleep(700);
 const resolved=path.resolve(profile);
 if(path.dirname(resolved)!==path.resolve(tmpdir())||!path.basename(resolved).startsWith('eos-plan-ui-'))throw Error('Unsafe browser profile cleanup path');
 rmSync(resolved,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}
