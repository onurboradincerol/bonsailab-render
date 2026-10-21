'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/app.js','utf8').replace(/\ninit\(\);\s*$/,'\n');
assert(!source.endsWith('init();'));
function harness(){
 const nodes=new Map();
 function node(id){if(!nodes.has(id)){const flags=new Set(id==='resultBlock'?['hidden']:[]);nodes.set(id,{value:'',textContent:'',innerHTML:'',disabled:false,checked:true,className:'',classList:{add:x=>flags.add(x),remove:x=>flags.delete(x),contains:x=>flags.has(x),toggle:(x,on)=>{if(on===undefined)on=!flags.has(x);on?flags.add(x):flags.delete(x);}},querySelectorAll:()=>[]});}return nodes.get(id);}
 const context=vm.createContext({document:{getElementById:node,querySelectorAll:()=>[]},localStorage:{setItem(){}},AbortController,console,URL,setTimeout,clearTimeout});
 vm.runInContext(source,context);
 const defaults={max_components:'5',species:'T14',phase:'pre',pot:'air',height:'8',volume:'2000',climate:'mediterranean',location:'outdoor',light:'filtered',wind:'low',watering:'twice',gr_M01:'fine'};
 for(const [id,v] of Object.entries(defaults))node(id).value=v;
 node('req_M01').checked=false;
 vm.runInContext("DB={materials:[{id:'M01',name:'Akadama',grain_applicable:true}]};render=(r)=>{$('variantCompare').innerHTML='result:'+r.request.species_id+':'+r.request.volume;};",context);
 let calls=0;
 const result={application:'BonsaiLAB V32',technical:{status:'ok'},species:{id:'T14',name:'Carmona / Fukien tea'},request:{species_id:'T14',volume:2000,inventory:[{name:'Akadama',available:true,required:false,grain_group:'fine'}]},request_sha256:'old'};
 context.fetch=async()=>{calls++;return {status:200,ok:true,json:async()=>structuredClone(result)};};
 return {context,node,result,run:code=>vm.runInContext(code,context),calls:()=>calls};
}
async function main(){
 let groups=0;
 {
  const h=harness();h.run('invalidate()');assert.equal(h.calls(),0);assert.equal(h.node('resultBlock').classList.contains('hidden'),true);groups++;
 }
 {
  const h=harness();await h.run('runCalc()');const html=h.node('variantCompare').innerHTML;
  h.node('c_M01').checked=false;h.run('inputsChanged()');
  assert.equal(h.calls(),1);assert.equal(h.node('variantCompare').innerHTML,html);assert.equal(h.node('resultBlock').classList.contains('hidden'),false);assert.equal(h.node('exportBtn').disabled,false);
  assert.match(h.node('calcStatus').textContent,/Seçimler değişti/);assert.match(h.node('calcBtn').textContent,/Tekrar hesapla/);assert.match(h.node('resultContext').textContent,/Carmona/);groups++;
  h.node('c_M01').checked=true;h.run('inputsChanged()');assert.equal(h.run('resultIsStale()'),false);assert.equal(h.calls(),1);groups++;
  h.node('height').value='8.0';h.run('inputsChanged()');assert.equal(h.run('resultIsStale()'),false);groups++;
 }
 {
  const h=harness();await h.run('runCalc()');h.node('species').value='T10';h.run('inputsChanged()');
  const report=h.run('buildExport(last)');assert.equal(report.request.species_id,'T14');assert.equal(report.export_context.displayed_result_is_outdated,true);assert.equal(report.result.request_sha256,'old');groups++;
 }
 {
  const h=harness();await h.run('runCalc()');h.node('volume').value='3000';h.run('inputsChanged()');
  let finish;h.context.fetch=()=>new Promise(resolve=>{finish=resolve;});const pending=h.run('runCalc()');
  assert.equal(h.node('resultBlock').classList.contains('hidden'),false);assert.equal(h.node('exportBtn').disabled,false);assert.equal(h.node('calcBtn').disabled,true);groups++;
  finish({status:200,ok:true,json:async()=>({...h.result,request:{species_id:'T14',volume:3000},request_sha256:'new'})});await pending;
  assert.match(h.node('variantCompare').innerHTML,/3000/);assert.equal(h.run('resultIsStale()'),false);assert.equal(h.node('calcBtn').disabled,false);groups++;
 }
 {
  const h=harness();await h.run('runCalc()');const html=h.node('variantCompare').innerHTML;
  h.node('volume').value='3000';h.run('inputsChanged()');h.context.fetch=async()=>({status:400,ok:false,json:async()=>({error:'Girdi hatası'})});await h.run('runCalc()');
  assert.equal(h.node('variantCompare').innerHTML,html);assert.equal(h.node('resultBlock').classList.contains('hidden'),false);assert.equal(h.node('exportBtn').disabled,false);assert.match(h.node('errorMsg').textContent,/Önceki sonuç korunuyor/);groups++;
 }
 {
  const h=harness();await h.run('runCalc()');const html=h.node('variantCompare').innerHTML;
  let finish;h.context.fetch=()=>new Promise(resolve=>{finish=resolve;});const pending=h.run('runCalc()');h.node('volume').value='4000';h.run('inputsChanged()');
  finish({status:200,ok:true,json:async()=>({...h.result,request:{species_id:'T99',volume:9999}})});await pending;
  assert.equal(h.node('variantCompare').innerHTML,html);assert.equal(h.run('last.request.species_id'),'T14');assert.equal(h.run('resultIsStale()'),true);assert.equal(h.node('calcBtn').disabled,false);groups++;
 }
 {
  const h=harness();await h.run('runCalc()');h.context.fetch=async()=>{throw Error('Ağ hatası');};await h.run('runCalc()');assert.equal(h.run('last.request_sha256'),'old');assert.equal(h.node('resultBlock').classList.contains('hidden'),false);groups++;
 }
 {
  const h=harness();await h.run('runCalc()');const html=h.node('variantCompare').innerHTML;
  h.node('req_M01').checked=true;h.run('inputsChanged()');
  assert.equal(h.calls(),1);assert.equal(h.node('variantCompare').innerHTML,html);assert.equal(h.run('resultIsStale()'),true);
  assert.equal(h.run('payload().inventory[0].required'),true);
  assert.equal(h.run('buildExport(last).request.inventory[0].required'),false);groups++;
  h.node('req_M01').checked=false;h.run('inputsChanged()');assert.equal(h.run('resultIsStale()'),false);groups++;
 }
 {
  const h=harness();h.node('req_M01').checked=true;h.node('c_M01').checked=false;
  h.run('updateRow(DB.materials[0]);count()');
  assert.equal(h.node('req_M01').checked,false);assert.equal(h.node('req_M01').disabled,true);assert.equal(h.node('inventoryCount').textContent,'0 seçili');
  h.node('c_M01').checked=true;h.run('updateRow(DB.materials[0])');assert.equal(h.node('req_M01').disabled,false);assert.equal(h.node('req_M01').checked,false);groups++;
 }
 {
  const h=harness();h.run("DB.rules={shares:{Akadama:0}}");h.node('req_M01').checked=true;h.run('updateRow(DB.materials[0])');
  assert.equal(h.node('req_M01').checked,false);assert.equal(h.node('req_M01').disabled,true);groups++;
 }
 console.log(`PASS ${groups} frontend state scenarios: retained results, required selection, explicit recalculation, stale export, errors and late responses.`);
}
main().catch(error=>{console.error(error);process.exitCode=1;});
