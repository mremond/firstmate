import fs from 'node:fs/promises';
const pages=await(await fetch('http://127.0.0.1:19223/json/list')).json();
const ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
await new Promise((res,rej)=>{ws.onopen=res;ws.onerror=rej});
let seq=0;const pending=new Map();
ws.onmessage=({data})=>{const m=JSON.parse(data);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}};
export function call(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
export async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
export async function navigate(url){await call('Page.enable');await call('Page.navigate',{url});for(let i=0;i<80;i++){await new Promise(r=>setTimeout(r,100));if(await evaluate('document.readyState === "complete"'))break}}
export async function screenshot(path){const r=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,fromSurface:true});await fs.writeFile(path,Buffer.from(r.data,'base64'))}
export function close(){ws.close()}
