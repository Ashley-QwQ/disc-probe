// Execute the existing result renderer against a tiny DOM and recorded job events.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const home = path.join(__dirname, '../discprobe/web/home');
const source = fs.readFileSync(path.join(home, 'burn.js'), 'utf8')
  .replace(/^import .*;$/mg, '').replace(/export /g, '').replace(/import\.meta\.url/g, '"file:///test"');
const node = () => ({textContent:'', dataset:{}, style:{setProperty(){}}, classList:{toggle(){}}, setAttribute(){}, replaceChildren(){}, after(){}, children:[{},{}], lastChild:{}});
const nodes = new Map();
const q = key => { if(!nodes.has(key))nodes.set(key,node());return nodes.get(key); };
const heard = [];
const sfx = {step:i=>heard.push('step'+i), done:()=>heard.push('done'), problem:()=>heard.push('problem'), failure:()=>heard.push('failure')};
let confirmOptions;
const sandbox = vm.createContext({document:{documentElement:node(),createElement:node}, console, q, node, assert, afterBurn:[], sfx, heard,
  nextConfirm:(button,options)=>{confirmOptions=options;},getConfirmation:()=>confirmOptions});
vm.runInContext(source, sandbox);
vm.runInContext(String.raw`
  api={lang:()=> 'en'};
  ctx={media:'dvd', iso:{path:'p.iso',bytes:32768,sectors:16},drive:{id:'fake',speeds:[4,8,16]}};
  W={q, page:node(), select:node(),progress:node(),miniRing:node(),mini:node()};
  fillSpeeds(); assert.equal(speed,8);
  speed=4; fillSpeeds(); assert.equal(speed,4); // explicit choice survives repaint
  speed=undefined;ctx.media='cd';fillSpeeds();assert.equal(speed,4);
  speed=undefined;ctx.media='dvd';ctx.drive.speeds=[4,6,10,16];fillSpeeds();assert.equal(speed,6);
  task={status:'success',burnResult:{selected_speed_x:8,actual_speed_x:8.01,verification:{status:'completed',ok:94,differing:1,unreadable:1,untested:0,failures:[{lba:772000,radius_mm:39.2}]}}};
  paint();
  assert.match(q('.burn-result p').textContent,/94 blocks ok \/ 1 differing \/ 1 unreadable/);
  assert.match(q('.burn-result p').textContent,/picture may still look fine/);
  assert.match(q('.burn-result p').textContent,/another speed/);
  assert.match(q('.burn-result p').textContent,/LBA 772000/);
  assert.match(q('.burn-result p').textContent,/39.20 mm/);
  assert.match(q('.burn-result p').textContent,/reports: 8×/);
  // IMAPI's speeds on a real GH70N (2026-11-11) read as people say them
  assert.deepEqual([4.00740740740741,8.01481481481481,16.0296296296296].map(X),['4×','8×','16×']);
  api.lang=()=> 'zh'; paint();
  assert.match(q('.burn-result p').textContent,/图案仍可能看起来正常/);
  assert.match(q('.burn-result p').textContent,/另一速度刻录/);
  task.burnResult.verification={status:'skipped'}; paint();
  assert.match(q('.burn-result p').textContent,/已跳过回读/);
  // after a write: written, closed, read back and picture are four separate answers
  const rows=(job,en)=>afterChecks(job,en).map(([label,s])=>label+':'+s).join(' ');
  const clean={status:'success',closed:true,burnResult:{selected_speed_x:8,actual_speed_x:8,verification:{status:'completed',ok:96,differing:0,unreadable:0,untested:0,failures:[]}}};
  assert.equal(rows(clean,true),'Written:good Closed:good Read back:good Picture:unknown');
  assert.equal(rows({...clean,closed:false},true),'Written:good Closed:warn Read back:good Picture:unknown');
  assert.equal(rows({...clean,closed:null},false),'写入:good 关盘:unknown 回读:good 图案:unknown');
  const bad={...clean,burnResult:{...clean.burnResult,verification:{status:'completed',ok:70,differing:0,unreadable:26,untested:0,failures:[]}}};
  assert.equal(rows(bad,true),'Written:good Closed:good Read back:warn Picture:unknown');
  assert.equal(rows({...clean,burnResult:{verification:{status:'skipped'}}},true),'Written:good Closed:good Read back:unknown Picture:unknown');
  // never a green picture: the program cannot see it
  assert.ok(!afterChecks(clean,true).some(([l,s])=>l==='Picture'&&s==='good'));
  // a clean sample is not repeated in the paragraph
  task=clean; paint(); assert.equal(q('.burn-result p').textContent,'');
  // what is heard at the end: clean read-back done, a bad sample a problem, nothing written a problem, a lost disc a failure
  heard.length=0;
  chime({status:'success',burnResult:clean.burnResult}); chime({status:'success',burnResult:bad.burnResult});
  chime({status:'success',burnResult:{verification:{status:'skipped'}}}); chime({status:'failed',started:false}); chime({status:'failed',started:true}); chime({status:'cancelled'});
  assert.deepEqual([...heard],['done','problem','done','problem','failure']);
  // The ready step replaces Next with a slider, retaining the checkbox gate.
  api.$=id=>q(id);api.nextWhy=()=>{};visible=true;W.next=node();W.consent={checked:false};
  ctx.discIn=true;ctx.media='dvd';speed=8;task=null;
  paint();assert.equal(getConfirmation().active,true);assert.equal(getConfirmation().disabled,true);
  getConfirmation().done();assert.equal(task,null,'unchecked consent cannot start a write');
  W.consent.checked=true;paint();assert.equal(getConfirmation().disabled,false);
  task={status:'burning',progress:.25};paint();assert.equal(getConfirmation().active,false);
  task={status:'success',progress:1};paint();assert.equal(getConfirmation().active,false);
  assert.equal(W.next.disabled,false,'normal Next remains available after success');
`, sandbox);

// Exercise realBurn's event forwarding using an in-memory EventSource; no HTTP or server.
const design = fs.readFileSync(path.join(home, 'design.js'), 'utf8');
const realBurn = design.slice(design.indexOf('function realBurn('), design.indexOf('\nfunction leave()', design.indexOf('function realBurn(')));
const listeners = {};
const updates = [];
const context = vm.createContext({S:{media:'dvd'},T:()=>({exp:{},burnFailed:'failed'}),
  fetch:async url=>({ok:true,json:async()=>url.includes('token')?{token:'fake'}:url.includes('burn-speeds')?{blank:true,speeds_x:[8]}:{job:'job1'}}),
  EventSource:class {addEventListener(name,callback){listeners[name]=callback;}close(){}}, updates});
vm.runInContext(realBurn + '\nrealBurn({path:"p.iso"},{id:"fake"},p=>updates.push(p),{speed:8});',context);
setImmediate(()=>{
  const send=(name,data)=>listeners[name]({data:JSON.stringify({job:'job1',...data})});
  send('burn_speed',{selected_speed_x:8,actual_speed_x:8.01});
  send('verify_progress',{fraction:.5});
  send('burn_result',{result:'completed',verification:{status:'completed',ok:95,unreadable:1}});
  send('done',{exit:0});
  assert.equal(updates[0].speedReport.actual_speed_x,8.01);
  assert.equal(updates[1].verifying,true);
  assert.equal(updates.at(-1).status,'success');
  assert.equal(updates.at(-1).burnResult.verification.unreadable,1);
  console.log('Burn page recorded-event checks passed');
});
