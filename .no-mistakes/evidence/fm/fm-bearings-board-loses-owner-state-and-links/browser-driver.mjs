import {spawn} from 'node:child_process';
import {writeFileSync,readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const [url,label,action='inspect']=process.argv.slice(2);
const root=process.cwd(), evidence='/Users/mremond/.no-mistakes/evidence/01M2GAWMSDQK4B5EA9GZW35RXE';
const browser=spawn('/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking',`--user-data-dir=${root}/.test-lab/brave-profile-${Date.now()}`,'--remote-debugging-pipe','about:blank'],{stdio:['ignore','ignore','pipe','pipe','pipe']});
let serial=0, buffer='', stderr='';const pending=new Map();
function call(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});browser.stdio[3].write(JSON.stringify({id,method,params,sessionId})+'\0');});}
browser.stderr.on('data',b=>stderr=(stderr+b).slice(-2000));
browser.stdio[4].on('data',b=>{buffer+=b;let end;while((end=buffer.indexOf('\0'))>=0){const m=JSON.parse(buffer.slice(0,end));buffer=buffer.slice(end+1);const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}}});
const closed=new Promise(resolve=>browser.on('close',()=>{for(const p of pending.values())p.reject(Error(stderr));resolve();}));
const deadline=setTimeout(()=>browser.kill('SIGKILL'),55000);
try{
 const {targetId}=await call('Target.createTarget',{url:'about:blank'});
 const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
 let evalSession=sessionId;
 const ev=async expression=>{const r=await call('Runtime.evaluate',{expression,userGesture:true,returnByValue:true,awaitPromise:true},evalSession);assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;};
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1700,deviceScaleFactor:1,mobile:false},sessionId);
 await call('Page.navigate',{url},sessionId);
 let state;
 for(let i=0;i<50;i++){const {targetInfos}=await call('Target.getTargets');const artifact=targetInfos.find(t=>t.type==='iframe'&&t.url.includes('/artifact/'));if(artifact){evalSession=(await call('Target.attachToTarget',{targetId:artifact.targetId,flatten:true})).sessionId;break;}await new Promise(r=>setTimeout(r,200));}
 for(let i=0;i<100;i++){
  try { state=await ev(`(()=>{let f=document.querySelector('iframe');let d=f?.contentDocument||document;return {ready:!!d.querySelector('#bb-stats .bb-stat'),body:document.body?.innerText,frames:[...document.querySelectorAll('iframe')].map(f=>({src:f.src,id:f.id})),board:d.body?.innerText}})()`);
  } catch(e) {if(!String(e).includes('execution context'))throw e;state={ready:false};}
  if(state.ready)break;await new Promise(r=>setTimeout(r,200));
 }
 assert.ok(state.ready,JSON.stringify(state));
 await ev(`Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,2500))]).then(()=>true)`);
 const surface=await ev(`(()=>{const d=document.querySelector('iframe')?.contentDocument||document;return {stats:[...d.querySelectorAll('.bb-stat')].map(x=>x.innerText),regime:d.querySelector('#bb-awaiting-sub').innerText,delivered:[...d.querySelectorAll('#bb-awaiting .bb-row')].map(x=>x.innerText),underway:[...d.querySelectorAll('#bb-underway .bb-row')].map(x=>x.innerText),charted:[...d.querySelectorAll('#bb-charted .bb-row')].map(x=>({text:x.innerText,links:[...x.querySelectorAll('a')].map(a=>a.href)})),links:[...d.querySelectorAll('a')].map(a=>({text:a.innerText,href:a.href})),buttons:[...document.querySelectorAll('button')].map(b=>({text:b.innerText,title:b.title,disabled:b.disabled})),forms:[...d.querySelectorAll('form')].map(f=>({text:f.innerText,html:f.outerHTML}))}})()`);
 if(action==='off'){
  assert.equal(surface.stats[0].toLowerCase(),'2\nneed you');assert.equal(surface.stats.length,5);
  assert.ok(surface.stats.find(s=>s.toLowerCase().includes('underway')).includes('1 (main) · 1 mate'));
  assert.ok(surface.stats.find(s=>s.toLowerCase().includes('charted next')).includes('2 (main) · 2 mate'));
  assert.match(surface.regime.toLowerCase(),/no nudge threshold set/);assert.equal(surface.delivered.length,4);
  assert.ok(surface.delivered[0].toLowerCase().includes('21d'));
  assert.equal(surface.charted.filter(r=>r.links.includes('https://github.com/acme/repo/pull/2')).length,2);
  assert.ok(surface.links.every(a=>!a.href.endsWith('/pull/99')));
 }
 if(action==='on'){assert.match(surface.regime.toLowerCase(),/7 days/);assert.equal(surface.delivered.length,2);assert.equal(surface.stats[0].toLowerCase(),'3\nneed you');}
 if(action==='all'){assert.match(surface.regime.toLowerCase(),/1 days/);assert.equal(surface.delivered.length,0);assert.equal(surface.stats[0].toLowerCase(),'3\nneed you');}
 if(action==='empty'){assert.match(surface.regime.toLowerCase(),/no nudge threshold set/);assert.equal(surface.delivered.length,0);}
 if(action==='links'){
  surface.openedLinks=[];
  for(const selector of ['#bb-underway a','#bb-charted a']){
    const href=await ev(`(()=>{const a=document.querySelector(${JSON.stringify(selector)});a.click();return a.href})()`);
    let opened;for(let i=0;i<30;i++){const {targetInfos}=await call('Target.getTargets');opened=targetInfos.find(t=>t.targetId!==targetId&&t.type==='page'&&t.url===href);if(opened)break;await new Promise(r=>setTimeout(r,100));}
    if(!opened)console.log(JSON.stringify(await call('Target.getTargets')));assert.ok(opened,href);surface.openedLinks.push(href);await call('Target.closeTarget',{targetId:opened.targetId});
  }
 }
 if(action==='nudge'){
  const clicked=await ev(`(()=>{const d=document;d.querySelector('#bb-stack-next').click();d.querySelector('#bb-stack-next').click();const radio=d.querySelector('input[value="wait"]');const forms=[...d.querySelectorAll('form')];const f=forms.find(f=>f.innerText.includes('Leave it waiting'));f.querySelector('input[value="wait"]').click();f.querySelector('button[type="submit"]').click();return {body:document.body.innerText,board:d.body.innerText}})()`);
  surface.afterQueue=clicked;
  const frameSession=evalSession;evalSession=sessionId;
  surface.beforeSend=await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText==='Show anyway');if(b)b.click();return document.body.innerText})()`);
  await new Promise(r=>setTimeout(r,500));
  surface.send=await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText==='Send to Agent');if(!b||b.disabled)throw Error('Send unavailable');b.click();return document.body.innerText})()`);
  evalSession=frameSession;
 }
 await call('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText==='Show anyway');if(b)b.click();})()`},sessionId);
 await new Promise(r=>setTimeout(r,800));
 const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true},sessionId);
 writeFileSync(`${evidence}/${label}.png`,Buffer.from(shot.data,'base64'));
 writeFileSync(`${evidence}/${label}.json`,JSON.stringify(surface,null,2));
 console.log(JSON.stringify({label,stats:surface.stats,regime:surface.regime,delivered:surface.delivered,charted:surface.charted,buttons:surface.buttons,openedLinks:surface.openedLinks,afterQueue:surface.afterQueue},null,2));
}finally{clearTimeout(deadline);browser.kill('SIGTERM');const kill=setTimeout(()=>browser.kill('SIGKILL'),2000);await closed;clearTimeout(kill);}
