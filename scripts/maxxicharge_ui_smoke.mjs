// Offline CDP browser check: actual rendered values, all scenarios and mobile.
import {spawn} from 'node:child_process';
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const args=process.argv.slice(2), option=k=>args[args.indexOf(k)+1];
const phase2=args.includes('--phase2'), expectedScenarios=phase2?13:4;
if(!args.includes('--browser')||!args.includes('--html'))throw Error('--browser and --html required');
const profile=mkdtempSync(path.join(tmpdir(),'maxxi-ui-'));
const browser=spawn(option('--browser'),['--headless=new','--disable-gpu','--disable-background-networking','--disable-component-update','--disable-extensions','--disable-sync','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
const errors=[],requests=[],pending=new Map();let seq=0,ws;
try{
 const endpoint=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('Browser startup timeout')),30000);browser.stderr.on('data',bytes=>{out+=bytes;const m=out.match(/DevTools listening on (ws:\/\/127\.0\.0\.1:\d+\/\S+)/);if(m){clearTimeout(timer);resolve(m[1])}});browser.on('error',reject);browser.on('exit',code=>reject(Error('Browser exited: '+code)))});
 ws=new WebSocket(endpoint);await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})});
 ws.addEventListener('message',event=>{const m=JSON.parse(String(event.data));if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);else if(m.method==='Log.entryAdded'&&m.params.entry.level==='error')errors.push(m.params.entry.text);else if(m.method==='Network.requestWillBeSent'&&!/^(file:|data:|about:)/.test(m.params.request.url))requests.push(m.params.request.url)});
 const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++seq,timer=setTimeout(()=>reject(Error('CDP timeout: '+method)),15000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
 const {targetId}=await call('Target.createTarget',{url:'about:blank'});
 const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
 for(const method of ['Page.enable','Runtime.enable','Network.enable','Log.enable'])await call(method,{},sessionId);
 const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true},sessionId);if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value};
 const check=async expression=>{if(!await evaluate(expression))throw Error('UI assertion: '+expression)};
 await call('Emulation.setDeviceMetricsOverride',{width:1365,height:1100,deviceScaleFactor:1,mobile:false},sessionId);
 await call('Page.navigate',{url:pathToFileURL(path.resolve(option('--html'))).href},sessionId);
 let loaded=false;
 for(let i=0;i<60;i++){if(await evaluate("!!document.querySelector('#maxxi-panel')&&!document.querySelector('#maxxi-panel').hidden&&document.querySelectorAll('#maxxi-comparison tr').length==="+expectedScenarios)){loaded=true;break}await new Promise(resolve=>setTimeout(resolve,100))}
 if(!loaded)throw Error('SIM panel failed to render: '+errors.join('; '));
 await check("document.querySelectorAll('#maxxi-scenario option').length==="+expectedScenarios);
 await check("document.querySelector('#maxxi-soc').textContent.includes('%')");
 await check("document.querySelector('#maxxi-pv').textContent.includes('W')");
 await check("(()=>{const s=document.querySelector('#maxxi-slot');s.value=s.max;s.dispatchEvent(new Event('input'));return document.querySelector('#maxxi-time').textContent.includes('SIM')&&document.querySelector('#maxxi-savings').textContent.includes('€')})()");
 await check("(()=>{const s=document.querySelector('#maxxi-scenario');s.value='pv6_only';s.dispatchEvent(new Event('change'));return document.querySelector('#maxxi-soc').textContent==='Ohne Zusatzspeicher'})()");
 await check("(()=>{const s=document.querySelector('#maxxi-scenario');s.value='"+(phase2?'pv6_bat10__coordinated':'pv6_bat10')+"';s.dispatchEvent(new Event('change'));return document.querySelector('#maxxi-soc').textContent.includes('%')})()");
 if(phase2){for(const model of ['autonomous','coordinated','ideal'])await check("(()=>{const s=document.querySelector('#maxxi-scenario');s.value='pv2_bat5__"+model+"';s.dispatchEvent(new Event('change'));return document.querySelector('#maxxi-soc').textContent.includes('%')})()");await check("document.querySelector('#maxxi-comparison').parentElement.textContent.includes('LUOX')&&document.querySelector('#maxxi-comparison').parentElement.textContent.includes('32 ct')");}
 await check("document.documentElement.scrollWidth<=innerWidth+1");
 if(args.includes('--screenshot')){await evaluate("document.querySelector('#maxxi-panel').scrollIntoView()");const shot=await call('Page.captureScreenshot',{format:'png'},sessionId);writeFileSync(option('--screenshot'),Buffer.from(shot.data,'base64'))}
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true},sessionId);
 await check("document.documentElement.scrollWidth<=innerWidth+1");
 if(errors.length||requests.length)throw Error(JSON.stringify({errors,requests}));
 const result={passed:true,scenarios:expectedScenarios,desktop_width:1365,mobile_width:390,external_requests:0,javascript_errors:0};
 if(args.includes('--report'))writeFileSync(option('--report'),JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify(result));
 await call('Browser.close');
}finally{
 if(ws)ws.close();browser.kill();
 for(let i=0;i<30;i++){try{rmSync(profile,{recursive:true,force:true});break}catch{await new Promise(resolve=>setTimeout(resolve,100))}}
}
