import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {navigate,evaluate,call,screenshot,close} from './cdp.mjs';
const out='/Users/mremond/.no-mistakes/evidence/01M2J0R8DH0RSQP7P5KYP5P1D5';
try{
 await navigate('http://127.0.0.1:14387/session/7c08231bb44f2c12');
 await navigate(await evaluate('document.querySelector("#artifact").src'));
 const results=[];
 for(const width of [1440,620,390]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});
  await evaluate('document.fonts.ready.then(()=>true)');
  const m=JSON.parse(await evaluate(`JSON.stringify((()=>{const c=document.querySelector('.bb-decision:not([hidden])'),r=c.getBoundingClientRect(),pin=[...c.querySelectorAll('.fm-badge')].at(-1),p=pin.getBoundingClientRect(),row=document.querySelector('#bb-charted .bb-row'),t=row.querySelector('.bb-row__title'),s=row.querySelector('.bb-row__sub'),sign=document.querySelector('#bb-call').parentElement.querySelector('.fm-sign--muted');return {titleLines:t.getBoundingClientRect().height/parseFloat(getComputedStyle(t).lineHeight),subtitleLines:s.getBoundingClientRect().height/parseFloat(getComputedStyle(s).lineHeight),riskBadgeText:pin.textContent,riskBadgeClass:pin.className,riskBadgeInsideCard:p.left>=r.left-1&&p.right<=r.right+1,riskContextRows:c.querySelectorAll('.bb-ctx__row').length,documentWidth:document.documentElement.scrollWidth,viewport:document.documentElement.clientWidth,overflowing:[...document.querySelectorAll('body *')].filter(e=>{const b=e.getBoundingClientRect();return b.width&&b.right>document.documentElement.clientWidth+1}).map(e=>({class:e.className,text:e.textContent.slice(0,90),right:e.getBoundingClientRect().right}))}})())`));
  results.push({width,...m});
  assert.ok(Math.abs(m.titleLines-1)<0.1);assert.ok(Math.abs(m.subtitleLines-1)<0.1);assert.ok(m.riskBadgeClass.includes('warn'));assert.ok(m.riskBadgeText.includes('La vue'));assert.equal(m.riskContextRows,0);
  if(width===390)assert.ok(m.overflowing.some(e=>e.class==='fm-sign fm-sign--muted'&&e.right>480));
  await screenshot(out+`/base-board-${width}.png`);
 }
 await fs.writeFile(out+'/base-comparison.json',JSON.stringify({base:'b85e28b5f8aad91a553e33d461da9f238bbdac38',results,note:'Base reproduces one-line rows and whole, alert-colored French risk badge. The section heading also exceeds 390px on base; that unchanged heading is outside this rework.'},null,2));
 console.log('Base reproduced both requested rendering failures; 390px section-heading overflow also exists on base.');
}finally{close()}
