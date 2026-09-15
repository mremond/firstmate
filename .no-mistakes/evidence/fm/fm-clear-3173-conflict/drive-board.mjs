import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {evaluate,call,screenshot,close} from './cdp.mjs';
const out='/Users/mremond/.no-mistakes/evidence/01M2J0R8DH0RSQP7P5KYP5P1D5';
const payload=JSON.parse(await fs.readFile(out+'/live-input.json','utf8'));
const results=[];
try {
  for(const width of [1440,620,390]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});
    await call('Emulation.setTouchEmulationEnabled',{enabled:width===390});
    await evaluate('document.fonts.ready.then(()=>true)');
    await evaluate('window.scrollTo(0,0); while(!document.querySelector("#bb-stack-prev").disabled)document.querySelector("#bb-stack-prev").click()');
    const rows=await evaluate(`JSON.stringify([...document.querySelectorAll('.bb-row')].map(row=>{const title=row.querySelector('.bb-row__title'),sub=row.querySelector('.bb-row__sub');const lines=e=>e?e.getBoundingClientRect().height/parseFloat(getComputedStyle(e).lineHeight):0;return {section:row.parentElement.id,titleLines:lines(title),subtitleLines:lines(sub),titleScrollWidth:title?.scrollWidth,titleClientWidth:title?.clientWidth,subScrollWidth:sub?.scrollWidth,subClientWidth:sub?.clientWidth}}))`);
    for(const r of JSON.parse(rows)){
      assert.ok(Math.abs(r.titleLines-3)<0.1,JSON.stringify({width,r}));
      if(r.section!=='bb-landed')assert.ok(Math.abs(r.subtitleLines-2)<0.1,JSON.stringify({width,r}));
      assert.ok(r.titleScrollWidth<=r.titleClientWidth+1,JSON.stringify(r));
      assert.ok(r.subScrollWidth<=r.subClientWidth+1,JSON.stringify(r));
    }
    results.push({width,rows:JSON.parse(rows),cards:[]});
    await screenshot(out+`/board-${width}.png`);
    for(let i=0;i<payload.captains_call.length;i++){
      const input=payload.captains_call[i];
      const actual=JSON.parse(await evaluate(`JSON.stringify((()=>{const c=document.querySelector('.bb-decision:not([hidden])'),r=c.getBoundingClientRect();const within=e=>{const x=e.getBoundingClientRect();return x.left>=r.left-1&&x.right<=r.right+1};return {title:c.querySelector('.bb-decision__title').textContent,badges:[...c.querySelectorAll('.fm-badge')].map(e=>({text:e.textContent,tone:[...e.classList].find(k=>k.startsWith('fm-badge--')),inside:within(e)})),ctx:[...c.querySelectorAll('.bb-ctx__row')].map(e=>{const v=e.querySelector('.bb-ctx__v');return {key:e.querySelector('.bb-ctx__k').textContent,value:v.textContent,inside:within(v),lines:v.getBoundingClientRect().height/parseFloat(getComputedStyle(v).lineHeight),scrollWidth:v.scrollWidth,clientWidth:v.clientWidth}}),viewport:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth}})())`));
      assert.equal(actual.title,input.title);
      let trimmed=input.risk.trim(),dot=trimmed.indexOf('.');
      const level=(dot<0?trimmed:trimmed.slice(0,dot)).trim(),detail=dot<0?'':trimmed.slice(dot+1).trim();
      assert.deepEqual(actual.badges.map(b=>({text:b.text,tone:b.tone})),[{text:'checks green',tone:'fm-badge--online'},...(level?[{text:'risk '+level,tone:['low','faible'].includes(level.toLowerCase())?'fm-badge--neutral':'fm-badge--warn'}]:[])]);
      assert.deepEqual(actual.ctx.map(c=>({key:c.key,value:c.value})),detail?[{key:'risk',value:detail}]:[]);
      assert.ok(actual.badges.every(b=>b.inside),'badge overflow '+JSON.stringify({width,input,actual}));
      assert.ok(actual.ctx.every(c=>c.inside&&c.scrollWidth<=c.clientWidth+1),'context overflow '+JSON.stringify({width,input,actual}));
      if(width>=620)assert.equal(actual.viewport,actual.scrollWidth,'document overflow '+input.key);
      results.at(-1).cards.push({key:input.key,...actual});
      if((width===1440&&['unknown','blank'].includes(input.key))||(width===620&&input.key==='long-level')||(width===390&&input.key==='long-detail'))await screenshot(out+`/risk-${input.key}-${width}.png`);
      if(i<payload.captains_call.length-1)await evaluate('document.querySelector("#bb-stack-next").click()');
    }
  }
  await call('Emulation.setEmulatedMedia',{media:'print'});
  const printDetail=await evaluate('document.querySelector(".bb-decision:not([hidden]) .bb-ctx__v").getBoundingClientRect().height');
  assert.ok(printDetail>0);
  results.push({printJustificationVisible:true});
  await call('Emulation.setEmulatedMedia',{media:''});
  await fs.writeFile(out+'/board-live-results.json',JSON.stringify({target:'c896d6e919017eb1466e8da03ffe89a888c3e30f',browser:await call('Browser.getVersion'),results},null,2));
  console.log('Real Lavish-served board: 3 viewport sizes; 10 risk cases per size; wrapped rows, retained underway status, compact tones, deck navigation, touch and print-visible context all passed.');
} catch(e) {await fs.writeFile(out+'/board-live-failure.json',JSON.stringify({results,error:String(e)},null,2));throw e;} finally {close();}
