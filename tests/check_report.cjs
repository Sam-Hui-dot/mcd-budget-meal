// Offline DOM model for report logic and clipboard failure branches, not a browser.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../docs/preview.html'), 'utf8');
const data = JSON.parse(html.match(/<script id="mealReportData" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const script = html.match(/<\/script><script>([\s\S]*?)<\/script>/)[1];
function create(options = {}) {
  const elements = new Map();
  function element(id) {
    return {id, value:'', textContent:'', innerHTML:'', hidden:true, style:{}, dataset:{}, handlers:{},
      addEventListener(name,fn){this.handlers[name]=fn;}, setAttribute(k,v){this[k]=v;},
      focus(){}, select(){}, blur(){}, remove(){}, querySelectorAll(){return [];}};
  }
  const document={getElementById(id){if(!elements.has(id)) elements.set(id,element(id));return elements.get(id);},
    querySelectorAll(){return [];},createElement:element,body:{appendChild(){}},
    execCommand(){return options.legacy !== false;}};
  let now = Date.parse('2026-10-16T05:00:00Z');
  const source=structuredClone(options.data || data);
  document.getElementById('mealReportData').textContent=JSON.stringify(source);
  const navigator=options.noApi ? {} : {clipboard:{writeText: options.writeText || (()=>Promise.resolve())}};
  const context={document,navigator,console,Date:{parse:Date.parse,now:()=>now},setInterval(fn){context.tick=fn;}};
  vm.createContext(context);
  const injected=script.replace('render(); var wasStale=stale();',
    'globalThis.testApi={parseAmount,plans,differences,setBudget,stale,resultText,commit}; render(); var wasStale=stale();');
  vm.runInContext(injected,context);
  return {api:context.testApi,el:id=>document.getElementById(id),context,advance(ms){now+=ms;}};
}
async function flush(){await new Promise(resolve=>setImmediate(resolve));}
(async()=>{
  let checks=0;
  const a=create();
  assert.match(a.el('summary').innerHTML,/3 份餐单/);checks++;
  a.api.setBudget(1490);assert.equal(a.el('budgetRange').value,1490);assert.equal(a.el('budgetInput').value,'14.90');assert.match(a.el('summary').innerHTML,/¥0.00/);checks++;
  a.api.setBudget(1489);assert.match(a.el('summary').innerHTML,/全部超预算/);assert.match(a.el('summary').innerHTML,/¥0.01/);checks++;
  for(const value of ['-5','abc','14.905','1 4','','1e2']) assert.equal(a.api.parseAmount(value),null);
  assert.equal(a.api.parseAmount('14.90'),1490);checks++;
  a.api.setBudget(500);assert.equal(a.el('budgetInput').value,'10.00');assert.match(a.el('budgetHint').textContent,/调整/);checks++;
  const change=a.api.differences(a.api.plans())[1];assert.equal(change.delta,400);assert.equal(change.rows.unchanged.length,2);assert.equal(change.rows.removed.length,1);checks++;
  const b=create({writeText:()=>Promise.reject(new Error('denied')),legacy:true});b.el('copyBtn').handlers.click();await flush();assert.match(b.el('copyStatus').textContent,/已复制/);checks++;
  const c=create({noApi:true,legacy:false});c.el('copyBtn').handlers.click();await flush();assert.equal(c.el('manualCopy').hidden,false);assert.match(c.el('manualCopyText').value,/差价不是单品售价/);c.api.setBudget(2000);assert.equal(c.el('manualCopy').hidden,true);assert.equal(c.el('manualCopyText').value,'');checks++;
  let rejectCopy;const d=create({writeText:()=>new Promise((_,reject)=>{rejectCopy=reject;}),legacy:false});d.el('copyBtn').handlers.click();d.api.setBudget(2000);rejectCopy(new Error('denied'));await flush();assert.equal(d.el('manualCopy').hidden,true);checks++;
  const live=structuredClone(data);live.kind='live';live.meals.forEach(m=>m.variants.forEach(v=>{v.quotedAt='2026-10-16T05:00:00Z';}));
  const e=create({data:live});assert.equal(e.api.stale(),false);e.advance(900001);e.context.tick();assert.equal(e.api.stale(),true);assert.match(e.el('freshness').textContent,/超过/);checks++;
  const empty=structuredClone(data);empty.meals=[];empty.kind='demo';const f=create({data:empty});assert.match(f.el('summary').innerHTML,/没有有效报价/);assert.match(f.el('kindLabel').textContent,/模拟/);checks++;
  const g=create({writeText:()=>Promise.resolve()});g.el('copyBtn').handlers.click();await flush();assert.match(g.el('copyStatus').textContent,/已复制/);checks++;
  g.el('showTextBtn').handlers.click();assert.equal(g.el('manualCopy').hidden,false);assert.match(g.el('manualCopyText').value,/总价相差 ¥4.00/);assert.match(g.el('manualCopyText').value,/预算：¥30.00/);assert.ok(g.el('manualCopyText').value.includes('\n| 方案 |'));checks++;
  const archived=structuredClone(live);archived.historical=true;
  const h=create({data:archived});assert.match(h.el('kindLabel').textContent,/历史比较结果/);assert.match(h.el('freshness').textContent,/没有发出新请求/);assert.match(h.api.resultText(),/未重新核价/);checks++;
  console.log(`${checks} offline report logic scenarios passed (mock DOM).`);
})().catch(error=>{console.error(error);process.exitCode=1;});
