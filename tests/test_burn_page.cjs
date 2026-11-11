// Execute the existing result renderer against a tiny DOM and recorded job events.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const home = path.join(__dirname, '../discprobe/web/home');
const source = fs.readFileSync(path.join(home, 'burn.js'), 'utf8')
  .replace(/^import .*;$/mg, '').replace(/export /g, '').replace(/import\.meta\.url/g, '"file:///test"');
const node = () => ({textContent:'', dataset:{}, style:{setProperty(){}}, classList:{toggle(){}}, setAttribute(){}, replaceChildren(){}, children:[{},{}], lastChild:{}});
const nodes = new Map();
const q = key => { if(!nodes.has(key))nodes.set(key,node());return nodes.get(key); };
const sandbox = vm.createContext({document:{documentElement:node(),createElement:node}, console, q, node, assert});
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
  assert.match(q('.burn-result p').textContent,/8.01/);
  api.lang=()=> 'zh'; paint();
  assert.match(q('.burn-result p').textContent,/图案仍可能看起来正常/);
  assert.match(q('.burn-result p').textContent,/另一速度刻录/);
  task.burnResult.verification={status:'skipped'}; paint();
  assert.match(q('.burn-result p').textContent,/已跳过回读/);
`, sandbox);

// Exercise realBurn's event forwarding using an in-memory EventSource; no HTTP or server.
const design = fs.readFileSync(path.join(home, 'design.js'), 'utf8');
const realBurn = design.slice(design.indexOf('function realBurn('), design.indexOf('\nfunction leave()', design.indexOf('function realBurn(')));
const listeners = {};
const updates = [];
const context = vm.createContext({S:{media:'dvd'},T:()=>({exp:{},burnFailed:'failed'}),
  fetch:async url=>({ok:true,json:async()=>url.includes('token')?{token:'fake'}:{job:'job1'}}),
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
