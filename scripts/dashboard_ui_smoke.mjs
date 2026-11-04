// Real browser test of a synthetic static report; no server and no packages.
import {spawn} from 'node:child_process';
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const args=process.argv.slice(2), option=k=>args[args.indexOf(k)+1];
const pageURL=args.includes('--url')?option('--url'):pathToFileURL(path.resolve(option('--html'))).href;
const allowedRequest=url=>/^(file:|data:|about:)/.test(url)||(args.includes('--url')&&new URL(url).origin===new URL(pageURL).origin&&['/','/index.html','/favicon.ico'].includes(new URL(url).pathname));
if(!args.includes('--browser')||!args.includes('--html'))throw Error('Usage: --browser EXECUTABLE --html SYNTHETIC_REPORT [--screenshot NEW_PNG]');
if(typeof WebSocket!=='function')throw Error('Node 22+ with built-in WebSocket is required');
const profile=mkdtempSync(path.join(tmpdir(),'eos-dashboard-ui-'));
const browser=spawn(option('--browser'),['--headless=new','--no-sandbox','--disable-gpu','--disable-background-networking','--disable-component-update','--disable-extensions','--disable-sync','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
let ws,seq=0;const pending=new Map(),errors=[],requests=[];
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
try{
 const endpoint=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('Browser startup timeout')),20000);browser.stderr.on('data',bytes=>{output+=bytes;const hit=output.match(/DevTools listening on (ws:\/\/127\.0\.0\.1:\d+\/\S+)/);if(hit){clearTimeout(timer);resolve(hit[1]);}});browser.on('error',reject);browser.on('exit',code=>reject(Error('Browser exited before connection: '+code)));});
 ws=new WebSocket(endpoint);await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 ws.addEventListener('message',e=>{const m=JSON.parse(String(e.data));if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);else if(m.method==='Log.entryAdded'&&m.params.entry.level==='error')errors.push(m.params.entry.text);else if(m.method==='Network.requestWillBeSent'&&!allowedRequest(m.params.request.url))requests.push(m.params.request.url);});
 const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++seq;const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},15000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});
 const {targetId}=await call('Target.createTarget',{url:'about:blank'});
 const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
 for(const method of ['Page.enable','Runtime.enable','Network.enable','Log.enable'])await call(method,{},sessionId);
 await call('Emulation.setDeviceMetricsOverride',{width:1280,height:1100,deviceScaleFactor:1,mobile:false},sessionId);
 await call('Page.navigate',{url:pageURL},sessionId);
 const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true},sessionId);if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;};

 const check=async expression=>{if(!await evaluate(expression))throw Error('UI assertion failed: '+expression+'; '+JSON.stringify(await evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(n=>n.getBoundingClientRect().right>innerWidth+1).slice(0,10).map(n=>[n.tagName,n.id,n.className,n.getBoundingClientRect().right])})")));};
 let loaded=false;for(let i=0;i<100;i++){if(await evaluate("document.querySelectorAll('#slots tr').length===96")){loaded=true;break}await sleep(100)}
 if(!loaded)throw Error('Dashboard did not render: '+errors.join('; '));
 await check("document.querySelectorAll('#history button').length>=3");
 await check("document.querySelector('#sync').textContent==='waiting-publication'");
 await check("document.querySelector('#advantage').textContent==='Nicht belegt'");
 await check("document.querySelector('#unknown-energy').textContent.includes('kWh')");
 await check("document.querySelector('#pv-energy').textContent==='Nicht belegt'");
 await check("document.querySelector('#grid-energy').textContent==='Nicht belegt'");
 await check("(()=>{document.querySelectorAll('#history button')[1].click();return document.querySelector('#pv-energy').textContent.includes('kWh')&&document.querySelector('#grid-energy').textContent.includes('2,64')})()");
 await check("[...document.querySelectorAll('#battery rect')].some(n=>n.getAttribute('fill')==='#37d597')&&[...document.querySelectorAll('#battery rect')].some(n=>n.getAttribute('fill')==='#5a9cff')");
 await check("(()=>{document.querySelector('#slots tr').click();return document.querySelector('#raw').textContent.includes('ac_charge')&&document.querySelector('#detail-proof').textContent.includes('Originalindex 0')})()");
 const shot=async suffix=>{if(args.includes('--screenshot')){const p=option('--screenshot').replace(/\.png$/,suffix+'.png');const result=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false},sessionId);writeFileSync(p,Buffer.from(result.data,'base64'),{flag:'wx'})}};
 await shot('-desktop');
 await check("(()=>{document.querySelector('[data-days=\"7\"]').click();return document.querySelector('#selected-label').textContent.includes('7 Tage')&&document.querySelectorAll('#slots tr').length===100})()");
 await check("(()=>{document.querySelector('#next').click();return document.querySelector('#page-label').textContent.startsWith('101')})()");
 await check("(()=>{document.querySelector('[data-days=\"30\"]').click();return document.querySelector('#energy-note').textContent.includes('Datenlücken')})()");
 await shot('-history');
 await evaluate("document.querySelectorAll('#history button')[0].click()");
 await shot('-unknown');
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:true},sessionId);
 await check("document.documentElement.scrollWidth<=390");
 await shot('-mobile');
 await call('Emulation.setDeviceMetricsOverride',{width:1280,height:1100,deviceScaleFactor:1,mobile:false},sessionId);
 if(args.includes('--expect-event')){
  const initial=await evaluate("document.querySelectorAll('#history button').length");
  if(args.includes('--event-python')){const child=spawn(option('--event-python'),[path.resolve('scripts/dashboard_event.py'),'--source',option('--event-source'),'--destination',path.dirname(path.resolve(option('--html')))],{windowsHide:true,stdio:'inherit'});await new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error('Synthetic event driver failed: '+code)))})}
  console.log('Awaiting synthetic event and automatic 60-second file reload');
  let updated=false;
  for(let i=0;i<75;i++){await sleep(1000);if(await evaluate("document.querySelectorAll('#history button').length>"+initial)){updated=true;break}}
  if(!updated)throw Error('Automatic reload did not show new event');
  await check("document.querySelectorAll('#slots tr').length===96");
 }
 if(errors.length)throw Error('Browser errors: '+errors.join('; '));
 if(requests.length)throw Error('Unexpected page network requests');
 console.log(JSON.stringify({passed:true,real_browser:true,static_file:!args.includes('--url'),http:args.includes('--url'),plans:await evaluate("document.querySelectorAll('#history button').length"),quarter_rows:96,ranges:[1,7,30],mobile_width:390,external_requests:requests.length,browser_errors:errors.length,automatic_event_reload:args.includes('--expect-event')}));
 await call('Browser.close');
}finally{
 if(ws)ws.close();browser.kill();
 await sleep(700);
 const resolved=path.resolve(profile);
 if(path.dirname(resolved)!==path.resolve(tmpdir())||!path.basename(resolved).startsWith('eos-dashboard-ui-'))throw Error('Unsafe browser profile cleanup path');
 rmSync(resolved,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}
