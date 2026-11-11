/**
 * BURN · Operate. Arrive with a finished ISO; review, consent, hold, then read back.
 * States: missing input, ready, writing, success, cancelled, failure. Long names wrap;
 * unknown estimates stay unknown. No drive I/O lives in this module.
 * @typedef {Object} BurnContext
 * @property {'dvd'|'cd'|'bd'} media
 * @property {{name?:string, title?:string}} item
 * @property {{path:string,sectors:number,bytes:number}} iso
 * @property {{id:string,name:string,speeds:number[]}} drive
 * @property {(onProgress:(p:{progress:number,elapsed?:number,remaining?:number,status?:'burning'|'success'|'failed'|'cancelled'})=>void, options:{speed:number})=>{cancel:()=>void}} burn
 * @property {()=>void} back
 * @property {()=>void} [readBack]
 * @property {()=>void} [photograph]
 * Callback progress is 0–1. Report success only after finalizing. cancel() must eventually
 * report cancelled or failed; the UI keeps the task active until that acknowledgement.
 * Host calls leave() before navigating. Tasks survive leave(); start() restores them.
 */
import { cutaway, flyer } from "./drive-scene.js";
const root = document.documentElement;
const STR = {
  zh: {
    title:'刻录光盘', intro:'核对文件和光盘，再按住右下角开始刻录。', disc:'光盘', file:'刻录文件', speed:'刻录速度', reason:'DVD 默认选最接近 8x 的支持速度；CD 保持最低速度。较慢不一定更可靠。', estimate:'预计用时', unknown:'暂时无法估算', drive:'光驱', sectors:'扇区',
    consent:'光驱里是空白盘；我知道托盘会关闭，光驱会开始写入。', warning:'开始后托盘会关闭。请先放好空白盘，不要移动光驱。', hold:'按住 1 秒，开始刻录', holding:'继续按住…', ready:'等待确认', writing:'正在刻录光盘', running:'请让光驱保持连接，等到写入完成。', elapsed:'已用时', remaining:'剩余时间', cancel:'取消刻录', cancelWarn:'取消会让光盘只写入一部分，这张盘将无法再用。', confirmCancel:'确认取消刻录', keep:'继续刻录', stopping:'正在停止写入…', done:'光盘刻好了', doneNote:'接下来读回检查，或拍照看看实际的图案。', read:'下一步：读回光盘', photo:'拍摄光盘', failed:'这次没有刻好', notStarted:'还没有开始刻，盘没有动过', failedNote:'请检查光驱连接，换一张空白盘，再重新确认刻录。', cancelled:'刻录已取消', cancelledNote:'这张盘已经写入了一部分。请换一张空白盘后再试。', retry:'准备另一张空白盘', other:'用别的软件刻录', copy:'复制文件路径', copied:'已复制文件路径', copyFail:'无法自动复制，请选中路径后复制。', back:'返回预览', mini:'查看刻录进度', missing:'先准备刻录文件和光驱', missingNote:'返回预览生成刻录文件，再选择可用的光驱和速度。', details:'查看文件详情', waiting:'等待光驱报告进度', placeholder:'此入口将在接入读回或拍照页面后启用。', percent:'完成', swapping:'换一张空白盘',
  },
  en: {
    title:'Burn the disc', intro:'Check the file and disc, then hold the button at the bottom right.', disc:'Disc', file:'Burn file', speed:'Write speed', reason:'DVD defaults to the supported speed nearest 8x; CD keeps the lowest. Slower is not always more reliable.', estimate:'Estimated time', unknown:'Not enough information yet', drive:'Drive', sectors:'sectors',
    consent:'The disc in the drive is blank. I understand the tray will close and the drive will write to it.', warning:'The tray will close when you start. Place the blank disc first and keep the drive still.', hold:'Hold 1 second to burn', holding:'Keep holding…', ready:'Waiting for confirmation', writing:'Burning the disc', running:'Keep the drive connected until writing is complete.', elapsed:'Elapsed', remaining:'Remaining', cancel:'Cancel burning', cancelWarn:'Cancelling leaves the disc partly written and unusable.', confirmCancel:'Confirm cancellation', keep:'Continue burning', stopping:'Stopping the write…', done:'Your disc is ready', doneNote:'Read it back to check the result, or photograph the pattern.', read:'Next: read back the disc', photo:'Photograph the disc', failed:'The write did not finish', notStarted:'Nothing was written; the disc is untouched', failedNote:'Check the drive connection, replace the disc with a blank one, then confirm again.', cancelled:'Burning cancelled', cancelledNote:'This disc is partly written. Replace it with a blank disc before trying again.', retry:'Prepare another blank disc', other:'Burn with another program', copy:'Copy file path', copied:'File path copied', copyFail:'Automatic copy is unavailable. Select and copy the path.', back:'Back to preview', mini:'View burn progress', missing:'Prepare a burn file and drive first', missingNote:'Go back to preview to make the burn file, then choose an available drive and speed.', details:'View file details', waiting:'Waiting for progress from the drive', placeholder:'This opens when the read-back or photography page is connected.', percent:'complete', swapping:'Change the disc',
  }
};
let scene = null, api, ctx, W, task = null, visible = false, speed, holdTimer, holdStart, holdSource, toastTimer, swapping = null;
const T = () => STR[api?.lang() === 'en' ? 'en' : 'zh'];
const el = (tag, cls, text) => { const e = document.createElement(tag); if(cls)e.className=cls; if(text)e.textContent=text; return e; };
const time = s => Number.isFinite(s) ? `${Math.floor(Math.max(0,s)/60)}:${String(Math.floor(Math.max(0,s)%60)).padStart(2,'0')}` : T().unknown;
const ring = cls => { const n=el('span', `burn-ring live ${cls||''}`); n.innerHTML='<span></span>'; n.style.setProperty('--progress','0%'); return n; };
function build() {
  const css=el('link'); css.rel='stylesheet'; css.href=new URL('./burn.css',import.meta.url); document.head.append(css);
  const page=el('main','burn-page'); page.id='burn-page'; page.hidden=true;
  page.innerHTML=`<h1></h1><div class="burn-layout"><section class="burn-scene" aria-label=""><div class="burn-art"></div><div class="burn-disc live"><div class="burn-face"></div></div><p class="burn-scene-caption" aria-live="polite"></p></section><section class="burn-panel"><p class="burn-intro"></p><dl class="burn-facts"></dl><div class="burn-speed"><label for="burn-speed"></label><select id="burn-speed"></select><p></p></div><p class="burn-warning"></p><label class="burn-consent"><input type="checkbox"><span></span></label><div class="burn-result" role="status"><h2></h2><p></p></div><div class="burn-timing"><span></span><span></span></div><div class="burn-actions"><button type="button" data-a="cancel"></button><button type="button" data-a="retry"></button><button type="button" data-a="photo"></button></div><div class="burn-cancel-check" hidden><p></p><button type="button" data-a="confirmCancel"></button><button type="button" data-a="keep"></button></div><details class="burn-other"><summary></summary><p class="burn-path" tabindex="0"></p><button type="button" data-a="copy"></button></details></section></div>`;
  document.body.append(page);
  page.querySelector('.burn-panel').prepend(page.querySelector('h1'));   // the title heads the right column, as in calibration
  const q=s=>page.querySelector(s), mini=el('button','burn-mini live'); mini.type='button'; mini.hidden=true; const miniRing=ring(); mini.append(miniRing,el('span'));
  const progress=ring(); q('.burn-disc').append(progress);
  const holdRing=ring('burn-hold-ring');
  const toast=el('div','burn-toast'); toast.setAttribute('role','status'); document.body.append(mini,toast);
  W={page,q,mini,miniRing,progress,holdRing,toast,consent:q('input'),select:q('select'),art:q('.burn-art'),next:null};
  W.select.onchange=()=>{speed=Number(W.select.value);words();}; W.consent.onchange=()=>{stopHold();paint();};
  page.addEventListener('click',e=>{const a=e.target.closest('[data-a]')?.dataset.a;if(a)action(a);});
  mini.onclick=()=>start(api,ctx);
  addEventListener('dp-lang',words);
  new MutationObserver(()=>{ if(W) W.page.dataset.theme=root.dataset.theme; }).observe(root,{attributes:true,attributeFilter:['data-theme']});
  addEventListener('blur',stopHold); document.addEventListener('visibilitychange',()=>{if(document.hidden)stopHold();});
}
function valid() {return !!(ctx?.iso?.path && Number.isFinite(ctx.iso.bytes) && ctx.iso.bytes>0 && Number.isFinite(ctx.iso.sectors) && ctx.iso.sectors>0 && ctx.drive?.id && Number.isFinite(speed));}
function facts() {
  const t=T(), list=W.q('.burn-facts'); list.replaceChildren();
  const add=(label,value,cls)=>{list.append(el('dt','',label),el('dd',cls,value));};
  add(t.disc,ctx.item?.name||ctx.item?.title||`${(ctx.media||'').toUpperCase()}-R`);
  add(t.file,ctx.iso?.path?.split(/[\\/]/).pop()||'—');
  add(t.drive,ctx.drive?.name||'—');
  add(t.estimate,valid()?time(ctx.iso.bytes / ((ctx.media==='cd'?176400:ctx.media==='bd'?4500000:1385000)*speed)+90):t.unknown,'burn-data');
  if(Number.isFinite(ctx.iso?.bytes)&&Number.isFinite(ctx.iso?.sectors)) {const dd=el('dd','burn-file-details'),d=el('details'),s=el('summary','',t.details);d.append(s,el('p','burn-data',`${(ctx.iso.bytes/1048576).toLocaleString(api.lang(),{maximumFractionDigits:1})} MiB · ${ctx.iso.sectors.toLocaleString(api.lang())} ${t.sectors}`));dd.append(d);list.append(dd);}
}
function words() {
  if(!W||!ctx)return; const t=T(),q=W.q;
  q('h1').textContent=t.title;q('.burn-intro').textContent=t.intro;q('.burn-scene').setAttribute('aria-label',t.drive);q('.burn-speed label').textContent=t.speed;q('.burn-speed p').textContent=t.reason;q('.burn-warning').textContent=t.warning;q('.burn-consent span').textContent=t.consent;
  q('.burn-other summary').textContent=t.other;q('.burn-path').textContent=ctx.iso?.path||'—';q('[data-a="copy"]').disabled=!ctx.iso?.path;
  for(const a of ['cancel','retry','photo','copy','confirmCancel','keep'])q(`[data-a="${a}"]`).textContent=t[a];
  q('.burn-cancel-check p').textContent=t.cancelWarn; W.mini.setAttribute('aria-label',t.mini);
  if(visible&&W.back)W.back.replaceChildren(t.back,...W.back.querySelectorAll('.key-cap'));
  if(W.help)W.help.textContent=api.lang()==='en'?'Hold Space or Enter for one second. Release to cancel.':'按住空格或回车一秒；松开即可取消。';
  facts();paint();
}
function paint() {
  if(!W)return;const t=T(),q=W.q, status=task?.status||'ready', active=status==='burning', hasInput=valid();
  W.page.dataset.state=status;W.page.classList.toggle('burn-reduce',!!api.reduce);q('.burn-speed').hidden=status!=='ready';q('.burn-consent').hidden=status!=='ready'||!hasInput;q('.burn-warning').hidden=status!=='ready'||!hasInput;
  W.select.disabled=active; q('[data-a="cancel"]').hidden=!active;q('[data-a="cancel"]').disabled=!!task?.stopping;q('[data-a="retry"]').hidden=!['failed','cancelled'].includes(status)||!!task?.notStarted;q('[data-a="photo"]').hidden=status!=='success';
  q('.burn-timing').hidden=!active;const times=q('.burn-timing').children;times[0].textContent=`${t.elapsed} ${time(task?.elapsed)}`;times[1].textContent=`${t.remaining} ${time(task?.remaining)}`;
  const key=!hasInput?(swapping?'swapping':'missing'):status==='success'?'done':status==='ready'?'ready':status==='burning'?'writing':status;
  q('.burn-result h2').textContent=key==='failed'&&task?.notStarted?t.notStarted:t[key];q('.burn-result p').textContent=!hasInput?(ctx.driveProblem||t.missingNote):active?(task.stopping?t.stopping:t.running):(key==='failed'&&task?.error)||t[`${key}Note`]||'';
  if(active&&task?.verifying)q('.burn-result p').textContent=api.lang()==='en'?'Write complete. Reading back a sample; drive retries may take time…':'写入完成，正在抽样回读；光驱重试可能需要一些时间…';
  if(active&&task?.verifying){
    q('[data-a="cancel"]').textContent=api.lang()==='en'?'Stop read-back':'停止回读';
    q('.burn-cancel-check p').textContent=api.lang()==='en'?'The write is complete. Stopping now leaves the read-back check unfinished.':'写入已完成。现在停止会留下未检查的回读样本。';
  }
  const report=task?.burnResult||task?.speedReport;
  if(report){
    const en=api.lang()==='en', actual=report.actual_speed_x;
    let note=en?`Requested: ${report.selected_speed_x}×; drive/utility reports: ${actual==null?'not reported':actual+'×'}. `:`请求速度：${report.selected_speed_x}×；光驱/工具报告：${actual==null?'未报告':actual+'×'}。`;
    const v=report.verification;
    if(status==='success'&&v){
      if(v.status==='skipped')note+=en?'Read-back skipped.':'已跳过回读验证。';
      else {
        note+=en?`Sample: ${v.ok} blocks ok / ${v.differing} differing / ${v.unreadable} unreadable; ${v.untested} untested. `:`抽样：${v.ok} 块一致 / ${v.differing} 块不同 / ${v.unreadable} 块无法读取；${v.untested} 块未检查。`;
        if(v.status!=='completed'||v.differing||v.unreadable){
          note+=en?'The write completed. Reading failed or could not finish; the picture may still look fine. Try another blank disc at another speed. ':'写入已完成。回读失败或未能完成，图案仍可能看起来正常。建议换一张空白光盘，以另一速度刻录。';
          q('.burn-result h2').textContent=en?'Write completed; check read-back results':'写入完成，请检查回读结果';
        }
        else note+=en?'Only a sample was checked, not the whole disc. ':'仅检查了样本，并非整盘验证。';
        note+=(v.failures||[]).map(f=>`LBA ${f.lba} (~${f.radius_mm.toFixed(2)} mm, ${en?'nominal':'标称'})`).join('; ');
      }
      q('.burn-result p').textContent=note;
    }else if(active)q('.burn-result p').textContent+=' '+note;
  }
  const p=Math.round((task?.progress||0)*100);W.progress.style.setProperty('--progress',`${p}%`);W.miniRing.style.setProperty('--progress',`${p}%`);
  const caption=active?`${p}% · ${t.percent}`:status==='success'?t.done:t[key];q('.burn-scene-caption').textContent=caption;W.mini.lastChild.textContent=active?`${p}%`:t[key];
  q('.burn-disc').setAttribute('role','progressbar');q('.burn-disc').setAttribute('aria-label',t.writing);q('.burn-disc').setAttribute('aria-valuemin','0');q('.burn-disc').setAttribute('aria-valuemax','100');q('.burn-disc').setAttribute('aria-valuenow',String(p));
  W.mini.hidden=visible||!task; if(!visible||!W.next)return;
  W.next.disabled=status!=='success' && (status!=='ready'||!hasInput||!W.consent.checked);
  const text=api.$('next-text');if(text)text.textContent=status==='success'?t.read:holdSource?t.holding:t.hold;
  W.next.setAttribute('aria-describedby', 'burn-hold-help');
}
// the drive scene: the home page's drive flipped, a disc that drops in, the cutaway while it burns
function sceneOf(){return scene??={cut:cutaway(api,{mirrored:false,textLeft:()=>W.q('.burn-panel').getBoundingClientRect().left}),fly:flyer(api,{mirrored:false})};}
function waitForDisc(){api.setTray(true,false);setTimeout(()=>{if(visible&&!task)sceneOf().fly.hover(ctx.item?.name||'');},900);}
function fillSpeeds(){
  const speeds=[...new Set((ctx.drive?.speeds||[]).filter(x=>Number.isFinite(x)&&x>0))].sort((a,b)=>a-b);
  if(!speeds.includes(speed))speed=ctx.media==='cd'?speeds[0]:speeds.reduce((best,s)=>Math.abs(s-8)<Math.abs(best-8)?s:best,speeds[0]);W.select.replaceChildren(...speeds.map(s=>{const o=el('option','',`${s}×`);o.value=s;return o;}));W.select.value=speed;
}
// The disc in the drive is not a blank of this batch. As on the calibration page: it rises out of the tray
// and goes; the page waits, read-only, while the person opens the drive, changes the disc and closes it
// (the picture follows what the drive reports); a blank comes down into the tray; then the page looks again.
async function swapFlow(){
  if(swapping||!ctx.swap)return;
  const run=swapping={}, sc=sceneOf(), w=ctx.swapWords||{}, name=ctx.item?.name||'';
  let phase='in';
  const live=()=>swapping===run&&visible;
  const say=(text)=>{if(!live())return;ctx.driveProblem=text;paint();};
  const goOut=()=>{if(phase!=='in')return;phase='out';sc.fly.away();setTimeout(()=>{if(live()&&phase==='out'){phase='hover';sc.fly.hover(name);}},1400);};
  api.setTray(true,true,undefined,true);
  setTimeout(()=>{if(live()&&phase==='in')sc.fly.lift(name);},900);
  paint();
  try{
    await ctx.swap(state=>{
      if(!live())return;
      if(state==='open'){api.setTray(true,false,undefined,true);goOut();say(w.open);}
      else if(state==='empty'){goOut();say(w.put);}
      else if(state==='changed'||state==='loading'||(state==='ready'&&phase!=='in')){
        if(phase==='in')goOut();
        if(phase!=='down'){const was=phase;phase='down';say(w.checking);
          // the blank comes down over the tray (if it isn't hovering there yet) and drops in; the tray closes
          (async()=>{if(was!=='hover'){await new Promise(r=>setTimeout(r,was==='in'?1400:0));if(!live())return;await sc.fly.hover(name);}
            if(!live())return;await sc.fly.drop();api.placeDisc(true);api.setTray(false,true,undefined,true);})();}
      }
    });
  }catch(e){
    if(swapping!==run)return;
    swapping=null;ctx.driveProblem=(e?.message||'')+' '+(w.put||'');paint();return;
  }
  if(!live())return;
  say(w.checking);
  try{await ctx.recheck();}catch(e){ctx.driveProblem=e?.message||'';}
  if(swapping!==run)return;
  swapping=null;
  if(visible){fillSpeeds();words();}
  if(ctx.needSwap){if(visible)swapFlow();}
  else{ctx.discIn=true;api.placeDisc(true);api.setTray(false,true,undefined,true);}
}
function stopHold() {clearInterval(holdTimer);holdTimer=null;holdSource=null;if(W){W.holdRing.style.setProperty('--progress','0%');if(visible)paint();}}
function beginHold(source) {
  if(holdSource||W.next.disabled||task?.status==='success')return;
  holdSource=source;holdStart=performance.now();paint();
  holdTimer=setInterval(()=>{const p=Math.min(1,(performance.now()-holdStart)/1000);W.holdRing.style.setProperty('--progress',`${p*100}%`);if(p===1){stopHold();beginBurn();}},20);
}
async function beginBurn() {
  if(!visible||!valid()||!W.consent.checked||task?.status==='burning')return;
  task={status:'burning',progress:0,elapsed:0,remaining:undefined,handle:null,stopping:false}; const current=task;
  W.q('.burn-cancel-check').hidden=true;paint();
  const sc=sceneOf(); if(!ctx.discIn)await sc.fly.drop(); if(task!==current)return;
  api.placeDisc(true);api.setTray(false,true);
  try { const handle=ctx.burn(p=>{if(task!==current||current.status!=='burning')return; if(p.burnResult)current.burnResult=p.burnResult;if(p.speedReport)current.speedReport=p.speedReport;if(p.verifying)current.verifying=true; current.progress=Number.isFinite(p.progress)?Math.max(current.progress,Math.min(1,p.progress)):current.progress;current.elapsed=p.elapsed;current.remaining=p.remaining;sc.cut.update(current.progress,current.remaining);if(['success','failed','cancelled'].includes(p.status)){current.status=p.status;if(p.error)current.error=p.error;if(p.started===false)current.notStarted=true;if(p.status==='success')current.progress=1;W.q('.burn-cancel-check').hidden=true;setTimeout(()=>sc.cut.show(false),1200);}paint();},{speed});current.handle=handle;
    setTimeout(()=>{if(task===current&&current.status==='burning'&&visible){sc.cut.update(current.progress,current.remaining);sc.cut.show(true);}},900); }
  catch (e) {current.status='failed';current.error=e?.message||'';current.notStarted=true;paint();}
}
function toast(message){W.toast.textContent=message;W.toast.classList.add('on');clearTimeout(toastTimer);toastTimer=setTimeout(()=>W.toast.classList.remove('on'),2600);}
async function action(a) {
  if(a==='cancel')W.q('.burn-cancel-check').hidden=false;
  if(a==='keep')W.q('.burn-cancel-check').hidden=true;
  if(a==='confirmCancel'&&task?.status==='burning'&&!task.stopping){task.stopping=true;W.q('.burn-cancel-check').hidden=true;paint();try{task.handle.cancel();}catch{task.stopping=false;toast(T().failedNote);paint();}}
  if(a==='retry'){task=null;W.consent.checked=false;W.q('.burn-cancel-check').hidden=true;words();if(ctx.swap){ctx.discIn=false;ctx.needSwap=true;ctx.drive.speeds=[];fillSpeeds();swapFlow();}else waitForDisc();}
  if(a==='photo')ctx.photograph?ctx.photograph():toast(T().placeholder);
  if(a==='copy'){try{await navigator.clipboard.writeText(ctx.iso.path);toast(T().copied);}catch{toast(T().copyFail);}}
}
/** @param {Object} homeApi @param {BurnContext} context */
export function start(homeApi,context) {
  if(visible)leave();api=homeApi;
  if(ctx!==context && task?.status==='burning')throw new Error('A burn is already active; restore its context first.');
  const changed=ctx!==context;
  if(changed){ctx=context;task=null;speed=undefined;} if(!W)build();
  if(changed)W.consent.checked=false;
  fillSpeeds();
  visible=true;root.dataset.mode='burn';W.page.hidden=false;if(changed)W.page.scrollTop=0;W.page.dataset.theme=root.dataset.theme;api.focusDrive?.();
  W.next=api.$('next');W.nextLabel=api.$('next-text')?.textContent;W.next.classList.add('burn-primary');W.next.append(W.holdRing);W.holdRing.setAttribute('aria-hidden','true');
  W.help=el('span','burn-sr',api.lang()==='en'?'Hold Space or Enter for one second. Release to cancel.':'按住空格或回车一秒；松开即可取消。');W.help.id='burn-hold-help';W.page.append(W.help);
  W.back=api.$('back');W.backHidden=W.back.hidden;W.back.hidden=false;W.backLabel=W.back.innerHTML;W.back.replaceChildren(T().back,...W.back.querySelectorAll('.key-cap'));
  W.events=new AbortController();const signal=W.events.signal, on=(node,event,fn)=>node.addEventListener(event,fn,{signal,capture:true});
  on(W.next,'pointerdown',e=>{if(e.button!==0)return;e.preventDefault();W.next.focus();W.next.setPointerCapture(e.pointerId);beginHold('pointer');});
  on(W.next,'pointerup',stopHold);on(W.next,'pointercancel',stopHold);on(W.next,'lostpointercapture',stopHold);on(W.next,'pointerleave',stopHold);
  on(W.next,'keydown',e=>{if(![' ','Enter'].includes(e.key))return;e.preventDefault();e.stopImmediatePropagation();if(!e.repeat)beginHold(e.key);});
  on(W.next,'keyup',e=>{if([' ','Enter'].includes(e.key)){e.preventDefault();stopHold();}});on(W.next,'blur',stopHold);
  on(W.next,'click',e=>{e.preventDefault();e.stopImmediatePropagation();if(task?.status==='success')ctx.readBack?ctx.readBack():toast(T().placeholder);});
  on(W.back,'click',e=>{e.preventDefault();e.stopImmediatePropagation();leave();ctx.back?.();});
  words();
  // Arrival is visual only: the tray in the picture opens, the real drive is not touched before the hold.
  if(!task){if(ctx.needSwap)swapFlow();else if(ctx.swap){ctx.discIn=true;api.placeDisc(true);api.setTray(false,true,undefined,true);}else waitForDisc();} else if(task.status==='burning')setTimeout(()=>{if(visible)sceneOf().cut.show(true);},750);
}
export function leave() {
  if(!W||!visible)return;
  const from=W.q('.burn-disc').getBoundingClientRect();
  stopHold();visible=false;W.events.abort();if(swapping){swapping=null;ctx.stopSwap?.();}scene?.fly.hide();scene?.cut.show(false);W.page.hidden=true;W.help?.remove();W.next.classList.remove('burn-primary');W.holdRing.remove();W.next.removeAttribute('aria-describedby');W.next.disabled=false;W.back.innerHTML=W.backLabel;W.back.hidden=W.backHidden;if(api.$('next-text'))api.$('next-text').textContent=W.nextLabel;root.dataset.mode='';paint();
  if(task&&!api.reduce){const to=W.miniRing.getBoundingClientRect();W.mini.animate([{transform:`translate(${from.left-to.left}px,${from.top-to.top}px) scale(${from.width/to.width})`,opacity:.5},{transform:'none',opacity:1}],{duration:420,easing:'cubic-bezier(.2,.8,.2,1)'});}
}
