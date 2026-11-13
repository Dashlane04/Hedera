// Offline logic/DOM-contract check. No browser launch, network or third-party packages.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const file=process.argv[2];
if(!file)throw Error('Usage: node tests/replay-tests.mjs replay.html');
const html=fs.readFileSync(file,'utf8');
const payload=html.match(/<script id="dataset" type="application\/json">([\s\S]*?)<\/script>/)?.[1];
const code=html.match(/<script>\s*('use strict';[\s\S]*?)<\/script>/)?.[1];
assert(payload&&code,'standalone data and script');
assert(!html.includes('__HEDERA_DATA__'),'export replaced data placeholder');
assert(!/<script[^>]+src=|<link[^>]+href=/.test(html),'no external runtime assets');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.attributes={};this.events={};this.textContent='';this.value='';}
  append(...nodes){for(const n of nodes){this.children.push(n);if(this.tag==='select'&&this.children.length===1)this.value=n.value;}}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  setAttribute(k,v){assert(!/NaN|Infinity|undefined/.test(String(v)),`invalid SVG attribute ${k}: ${v}`);this.attributes[k]=v;}
  addEventListener(name,callback){this.events[name]=callback;}
}
const ids=['dataset','run','flow','timeline','play','speed','meanGoodput','fairness','population','fct','completion','plans','runTitle','configuration','phase','network','chart','time','flowPath','flowMetrics','decision','events','error'];
const elements=Object.fromEntries(ids.map(id=>[id,new Element(['run','flow','speed'].includes(id)?'select':'div')]));
elements.dataset.textContent=payload;elements.speed.value='1';
let interval=null;
const context=vm.createContext({document:{getElementById:id=>{assert(elements[id],id);return elements[id];},createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)},
  setInterval:callback=>{interval=callback;return 1;},clearInterval:()=>{interval=null;},console});
vm.runInContext(code,context,{timeout:10000});
const data=JSON.parse(payload);let renders=0;
for(let i=0;i<data.runs.length;i++){
  elements.run.value=String(i);elements.run.events.change();
  assert(elements.flow.children.length===data.runs[i].flows.length,'flow selector population');
  for(const flow of data.runs[i].flows){
    elements.flow.value=String(flow.flow_id);elements.flow.events.change();
    for(const at of [0,Math.floor(data.runs[i].frames.length/2),data.runs[i].frames.length-1]){
      elements.timeline.value=String(at);elements.timeline.events.input();
      assert.equal(elements.error.textContent,'');
      assert(elements.network.children.length>data.runs[i].nodes.length,'network SVG populated');
      assert(elements.chart.children.length>5,'chart SVG populated');renders++;
    }
  }
  elements.timeline.value='0';elements.timeline.events.input();
  elements.play.events.click();assert(interval,'play starts');interval();
  elements.play.events.click();assert(!interval,'pause stops');
}
console.log(`PASS: ${data.runs.length} runs, ${renders} flow/time renders, SVG finite geometry, selection, play/pause, standalone assets`);
