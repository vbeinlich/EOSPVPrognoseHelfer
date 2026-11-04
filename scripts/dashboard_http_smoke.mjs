// Local isolated Docker/HTTP test. Never targets Unraid or an existing container.
import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {mkdirSync,mkdtempSync,copyFileSync,chmodSync,writeFileSync,readFileSync,renameSync,unlinkSync,rmSync} from 'node:fs';
import path from 'node:path';
const args=process.argv.slice(2),option=k=>args[args.indexOf(k)+1];
if(!args.includes('--html')||!args.includes('--browser'))throw Error('Usage: --html SYNTHETIC_HTML --browser EXECUTABLE [--sidecar SYNTHETIC_SIDECAR] [--event-python PYTHON --event-source SOURCE]');
const root=path.resolve('private');mkdirSync(root,{recursive:true});
const temp=mkdtempSync(path.join(root,'lan-smoke-')),pub=path.join(temp,'publish');mkdirSync(pub,{mode:0o755});
const index=path.join(pub,'index.html');copyFileSync(option('--html'),index);chmodSync(index,0o644);
const baseline=readFileSync(index),project='ems-dashboard-test-'+path.basename(temp).toLowerCase();
const free=createServer();await new Promise((resolve,reject)=>{free.once('error',reject);free.listen(0,'127.0.0.1',resolve)});
const port=free.address().port;await new Promise(resolve=>free.close(resolve));
const env={...process.env,DASHBOARD_ROOT:temp,DASHBOARD_LAN_IP:'127.0.0.1',DASHBOARD_PORT:String(port)};
const compose=['compose','--project-name',project,'--file',path.resolve('deploy/dashboard/compose.yaml')];
const run=(command,argv)=>new Promise((resolve,reject)=>{const child=spawn(command,argv,{env,windowsHide:true,stdio:['ignore','pipe','pipe']});let out='',err='';child.stdout.on('data',b=>out+=b);child.stderr.on('data',b=>err+=b);child.on('error',reject);child.on('exit',code=>code===0?resolve(out):reject(Error(command+' failed ('+code+'): '+err+out)))});
const docker=argv=>run('docker',argv),url=`http://127.0.0.1:${port}`;
const assert=(ok,message)=>{if(!ok)throw Error(message)};
// Docker Desktop can briefly hold a Windows share handle during a GET. Linux
// rename is immediate; bounded retry preserves atomic replacement on Windows.
const replace=async(from,to)=>{for(let attempt=0;;attempt++){try{renameSync(from,to);return}catch(error){if(attempt>=100||!['EPERM','EACCES','EBUSY'].includes(error.code))throw error;await new Promise(resolve=>setTimeout(resolve,25));}}};
const get=async(route='/',options={})=>fetch(url+route,{...options,signal:AbortSignal.timeout(5000)});
try{
 await docker([...compose,'up','--detach','--pull','never','--wait','--wait-timeout','30']);
 const id=(await docker([...compose,'ps','--quiet'])).trim();
 const [state]=JSON.parse(await docker(['inspect',id]));
 assert(state.Config.User==='101:101'&&state.HostConfig.ReadonlyRootfs,'non-root / read-only root missing');
 assert(state.HostConfig.CapDrop.includes('ALL')&&state.HostConfig.SecurityOpt.includes('no-new-privileges:true'),'sandbox missing');
 assert(state.Mounts.filter(m=>m.Type==='bind').length===2&&state.Mounts.filter(m=>m.Type==='bind').every(m=>!m.RW),'unexpected or writable bind');
 assert(state.HostConfig.PortBindings['8080/tcp'][0].HostIp==='127.0.0.1','test exposed beyond loopback');
 const network=Object.keys(state.NetworkSettings.Networks)[0];
 const [net]=JSON.parse(await docker(['network','inspect',network]));
 assert(net.Driver==='bridge'&&net.Options['com.docker.network.bridge.enable_icc']==='false','dedicated bridge / peer isolation missing');
 assert((await docker(['exec',id,'id','-u'])).trim()==='101','actual Nginx UID differs');
 const processStatus=await docker(['exec',id,'cat','/proc/1/status']);
 assert(/^NoNewPrivs:\s+1$/m.test(processStatus)&&/^CapEff:\s+0+$/m.test(processStatus),'actual process privileges differ');
 await docker(['exec',id,'sh','-c','set -e; if touch /.write-probe 2>/dev/null; then exit 1; fi; if touch /srv/dashboard/.write-probe 2>/dev/null; then exit 1; fi; test ! -e /output; test ! -S /var/run/docker.sock; touch /tmp/health-probe; rm /tmp/health-probe']);
 for(const route of ['/','/index.html']){
  const response=await get(route);assert(response.status===200,'index inaccessible on published port');
  assert(Buffer.from(await response.arrayBuffer()).equals(baseline),'served HTML bytes differ');
  assert(response.headers.get('cache-control')==='no-store','HTML may be cached');
  assert(response.headers.get('x-content-type-options')==='nosniff','missing nosniff');
 }
 assert((await get('/',{method:'HEAD'})).status===200,'HEAD failed');
 assert((await get('/',{method:'POST',body:'reject'})).status===405,'POST accepted');
 writeFileSync(path.join(pub,'private-sidecar.json'),'SYNTHETIC-PRIVATE');
 for(const route of ['/private-sidecar.json','/.publish-secret','/output/','/../nginx.conf','/index.html/','/tools/'])assert((await get(route)).status===404,'unexpected public route '+route);
 unlinkSync(path.join(pub,'private-sidecar.json'));
 assert((await get('/',{headers:{'If-Modified-Since':new Date(Date.now()+86400000).toUTCString()}})).status===200,'conditional request retained stale HTML');
 const variants=[baseline,Buffer.from(baseline.toString().replace('</body></html>','<!-- synthetic atomic revision --></body></html>'))];
 let reads=0;
 for(let i=0;i<20;i++){
  const pending=Array.from({length:5},async()=>{const response=await get();const bytes=Buffer.from(await response.arrayBuffer());assert(response.status===200&&variants.some(v=>v.equals(bytes)),'partial/stale-inode publication');reads++});
  const temporary=path.join(pub,'.publish-test');writeFileSync(temporary,variants[i%2],{mode:0o644});await replace(temporary,index);
  await Promise.all(pending);
 }
 writeFileSync(path.join(pub,'.publish-test'),baseline,{mode:0o644});await replace(path.join(pub,'.publish-test'),index);
 const driver=args.includes('--sidecar')?'scripts/replay_ui_smoke.mjs':'scripts/dashboard_ui_smoke.mjs';
 const browserArgs=[driver,'--browser',option('--browser'),'--html',index,'--url',url+'/'];
 if(args.includes('--sidecar'))browserArgs.push('--sidecar',option('--sidecar'));
 if(args.includes('--screenshot'))browserArgs.push('--screenshot',option('--screenshot'));
 if(args.includes('--event-python'))browserArgs.push('--expect-event','--event-python',option('--event-python'),'--event-source',option('--event-source'));
 console.log(await run(process.execPath,browserArgs));
 console.log(JSON.stringify({passed:true,local_only:true,port,nginx:state.Config.Image,only_html:true,non_root:101,read_only:true,dedicated_bridge:true,peer_isolation:true,atomic_http_reads:reads,ranges:[1,7,30],mobile_width:390}));
}finally{
 // Scope deletion to this newly-created project and checked private test folder.
 await docker([...compose,'down','--timeout','3']).catch(error=>console.error(error.message));
 if(path.dirname(path.resolve(temp))!==root||!path.basename(temp).startsWith('lan-smoke-'))throw Error('Unsafe test cleanup');
 rmSync(temp,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}
