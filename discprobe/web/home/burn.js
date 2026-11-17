import { nextConfirm } from "./kit/nextconfirm.js";
import { expandBurnStop, closeBurnStop, stopWords, interruptedBurn } from './burn-stop.js';
/**
 * BURN · Operate. Arrive with a finished ISO; review, consent, slide, then read back.
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
import { afterBurn } from "./guidance.mjs";
import { cutaway, flyer } from "./drive-scene.js";
import * as sfx from "./sfx.js";
function burnFailed(r) {
  const v=r?.verification;
  return !!r && (r.result && r.result!=='completed' || r.disc_state?.status==='failed' ||
    v && v.status!=='skipped' && (v.status!=='completed' || v.differing || v.unreadable || v.untested));
}
const root = document.documentElement;
const STR = {
  zh: {
    title:'刻录光盘', intro:'核对文件和光盘，再滑动右下角确认刻录。', disc:'光盘', file:'刻录文件', speed:'刻录速度', speedUnknown:'放进空白盘后读出', recheckClosed:'再读一次光驱里的盘', reason:'DVD 默认选最接近 8x 的支持速度；CD 保持最低速度。较慢不一定更可靠。', estimate:'预计用时', unknown:'暂时无法估算', drive:'光驱', sectors:'扇区',
    consent:'光驱里是空白盘；我知道托盘会关闭，光驱会开始写入。', warning:'开始后托盘会关闭。请先放好空白盘，不要移动光驱。', hold:'滑动确认刻录', holding:'继续按住…', ready:'等待确认', writing:'正在刻录光盘', running:'请让光驱保持连接，等到写入完成。', elapsed:'已用时', remaining:'剩余时间', cancel:'取消刻录', cancelWarn:'取消会让光盘只写入一部分，这张盘将无法再用。', confirmCancel:'确认取消刻录', keep:'继续刻录', stopping:'正在停止写入…', done:'写入完成', doneNote:'光驱报告写完了。这只说明写入完成：读回是抽样（最多 96 块，不是全盘），盘上的图还没确认，要拿到灯下看。', read:'下一步：读回光盘', photo:'拍摄光盘', failed:'这次没有刻好', notStarted:'还没有开始刻，盘没有动过', failedNote:'请检查光驱连接，换一张空白盘，再重新确认刻录。', cancelled:'刻录已取消', cancelledNote:'这张盘已经写入了一部分。请换一张空白盘后再试。', retry:'准备另一张空白盘', other:'用别的软件刻录', copy:'复制文件路径', copied:'已复制文件路径', copyFail:'无法自动复制，请选中路径后复制。', back:'返回预览', mini:'查看刻录进度', missing:'先准备刻录文件和光驱', missingNote:'返回预览生成刻录文件，再选择可用的光驱和速度。', details:'查看文件详情', waiting:'等待光驱报告进度', percent:'完成', swapping:'换一张空白盘', finish:'完成，回到桌面', recheck:'重新检查光驱里的盘', whyConsent:'先勾选上面的确认', whySwap:'先换一张这批的空白盘', whyMissing:'先准备刻录文件和光驱', whyBurning:'正在刻，可以关掉网页', whyAgain:'先换盘或重新检查，再刻', copyCommand:'复制刻录命令', copiedCommand:'已复制刻录命令', otherCommandTitle:'刻录命令', otherOnly:'用刻录命令刻这张 CD', swapStopped:'等了一阵，没看到换盘。放好这批的空白盘、推上托盘，再点“重新检查光驱里的盘”。',
  },
  en: {
    title:'Burn the disc', intro:'Check the file and disc, then slide the confirmation at the bottom right.', disc:'Disc', file:'Burn file', speedUnknown:'Read once a blank is in', recheckClosed:'Read the disc in the drive again', speed:'Write speed', reason:'DVD defaults to the supported speed nearest 8x; CD keeps the lowest. Slower is not always more reliable.', estimate:'Estimated time', unknown:'Not enough information yet', drive:'Drive', sectors:'sectors',
    consent:'The disc in the drive is blank. I understand the tray will close and the drive will write to it.', warning:'The tray will close when you start. Place the blank disc first and keep the drive still.', hold:'Slide to burn', holding:'Keep holding…', ready:'Waiting for confirmation', writing:'Burning the disc', running:'Keep the drive connected until writing is complete.', elapsed:'Elapsed', remaining:'Remaining', cancel:'Cancel burning', cancelWarn:'Cancelling leaves the disc partly written and unusable.', confirmCancel:'Confirm cancellation', keep:'Continue burning', stopping:'Stopping the write…', done:'Written', doneNote:'The drive reports the write is complete. That is all it means: the read-back is a sample (up to 96 blocks, not the whole disc), and the picture on the disc is not confirmed until you look at it under a light.', read:'Next: read back the disc', photo:'Photograph the disc', failed:'The write did not finish', notStarted:'Nothing was written; the disc is untouched', failedNote:'Check the drive connection, replace the disc with a blank one, then confirm again.', cancelled:'Burning cancelled', cancelledNote:'This disc is partly written. Replace it with a blank disc before trying again.', retry:'Prepare another blank disc', other:'Burn with another program', copy:'Copy file path', copied:'File path copied', copyFail:'Automatic copy is unavailable. Select and copy the path.', back:'Back to preview', mini:'View burn progress', missing:'Prepare a burn file and drive first', missingNote:'Go back to preview to make the burn file, then choose an available drive and speed.', details:'View file details', waiting:'Waiting for progress from the drive', percent:'complete', swapping:'Change the disc', finish:'Done: back to the desk', recheck:'Check the disc in the drive again', whyConsent:'Tick the confirmation above first', whySwap:'Put in a blank from this batch first', whyMissing:'Prepare the burn file and drive first', whyBurning:'Burning; the page can be closed', whyAgain:'Change the disc or check again first', copyCommand:'Copy the burn command', copiedCommand:'Burn command copied', otherCommandTitle:'Burn command', otherOnly:'Burn this CD with a command', swapStopped:'No disc change was seen for a while. Put a blank from this batch in, close the tray, then press Check the disc in the drive again.',
  }
};
let scene = null, api, ctx, W, task = null, visible = false, speed, toastTimer, swapping = null;
const T = () => {
  const t=STR[api?.lang() === 'en' ? 'en' : 'zh'];
  if(!ctx?.drive?.rewritable)return t;
  const en=api.lang()==='en';
  return {...t,retry:en?'Erase and burn again':'擦除后重新刻',
    cancelledNote:en?'This recording cannot be used. Erase this rewritable disc before burning again.':'这次刻录不能使用，擦除这张可擦写盘后重新刻。',
    failedNote:en?'Check the drive, then erase this rewritable disc before burning again.':'请检查光驱连接，擦除这张可擦写盘后重新刻。',
    ...(ctx.drive.eraseRequired?{
      hold:en?'Slide to erase and burn again':'滑动确认擦除后重刻',
      warning:en?'The disc contents will be cleared. Erasing completes before burning starts.':'盘上的内容会被清掉。擦除完成后才开始刻录。',
      consent:en?'I understand this rewritable disc will be erased and recorded again.':'我知道盘上的内容会被清掉，然后重新刻录。',
    }:{})};
};
const X = v => `${+(+v).toFixed(1)}×`;   // a write speed as people say it (IMAPI reports 8x as 8.0148…)
const el = (tag, cls, text) => { const e = document.createElement(tag); if(cls)e.className=cls; if(text)e.textContent=text; return e; };
const time = s => Number.isFinite(s) ? `${Math.floor(Math.max(0,s)/60)}:${String(Math.floor(Math.max(0,s)%60)).padStart(2,'0')}` : T().unknown;
const ring = cls => { const n=el('span', `burn-ring live ${cls||''}`); n.innerHTML='<span></span>'; n.style.setProperty('--progress','0%'); return n; };
function build() {
  const css=el('link'); css.rel='stylesheet'; css.href=new URL('./burn.css',import.meta.url); document.head.append(css);
  const page=el('main','burn-page'); page.id='burn-page'; page.hidden=true;
  page.innerHTML=`<h1></h1><div class="burn-layout"><section class="burn-scene" aria-label=""><div class="burn-art"></div><div class="warn-sign" aria-hidden="true" style="left:50%;top:55%"><div class="flat"><span>!</span></div></div><div class="burn-disc live"><div class="burn-face"></div></div><p class="burn-scene-caption" aria-live="polite"></p></section><section class="burn-panel"><p class="burn-intro"></p><dl class="burn-facts"></dl><div class="burn-speed"><label for="burn-speed"></label><select id="burn-speed"></select><p></p></div><p class="burn-warning"></p><label class="burn-consent"><input type="checkbox"><span></span></label><div class="burn-result" role="status"><h2></h2><p></p></div><div class="burn-timing"><span></span><span></span></div><div class="burn-actions"><button type="button" data-a="cancel"></button><button type="button" data-a="retry"></button><button type="button" data-a="recheck"></button><button type="button" data-a="photo"></button></div><details class="burn-other"><summary></summary><p class="burn-path" tabindex="0"></p><button type="button" data-a="copy"></button></details></section></div>`;
  document.body.append(page);
  page.querySelector('.burn-panel').prepend(page.querySelector('h1'));   // the title heads the right column, as in calibration
  const q=s=>page.querySelector(s), mini=el('button','burn-mini live'); mini.type='button'; mini.hidden=true; const miniRing=ring(); mini.append(miniRing,el('span'));
  const progress=ring(); q('.burn-disc').append(progress);
  const toast=el('div','burn-toast'); toast.setAttribute('role','status'); document.body.append(mini,toast);
  W={page,q,mini,miniRing,progress,toast,consent:q('input'),select:q('select'),art:q('.burn-art'),next:null};
  W.select.onchange=()=>{speed=Number(W.select.value);words();}; W.consent.onchange=()=>{paint();};
  page.addEventListener('click',e=>{const a=e.target.closest('[data-a]')?.dataset.a;if(a)action(a);});
  mini.onclick=()=>start(api,ctx);
  addEventListener('dp-lang',words);
  new MutationObserver(()=>{ if(W) W.page.dataset.theme=root.dataset.theme; }).observe(root,{attributes:true,attributeFilter:['data-theme']});
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
  q('.burn-other summary').textContent=t.other;q('.burn-path').textContent=ctx.otherCommand||ctx.iso?.path||'—';q('[data-a="copy"]').disabled=!(ctx.otherCommand||ctx.iso?.path);
  for(const a of ['cancel','retry','recheck','photo','copy'])q(`[data-a="${a}"]`).textContent=t[a];
  W.mini.setAttribute('aria-label',t.mini);
  if(ctx.otherCommand){q('.burn-other summary').textContent=t.otherCommandTitle;q('[data-a="copy"]').textContent=t.copyCommand;}
  if(visible&&W.back)W.back.replaceChildren(t.back,...W.back.querySelectorAll('.key-cap'));
  if(W.help)W.help.textContent=api.lang()==='en'?'Hold Space or Enter for one second. Release to cancel.':'按住空格或回车一秒；松开即可取消。';
  facts();paint();
}
// [label, good|warn|unknown, words] for each thing known after a write. Only what the drive reported or what
// was read back counts as checked; the picture itself is only ever checked by looking at the disc.
export function afterChecks(job, en=api?.lang()==='en'){
  const r=job?.burnResult||job?.speedReport||{}, v=r.verification, actual=r.actual_speed_x, sel=r.selected_speed_x;
  const L=(zh,e)=>en?e:zh, rows=[];
  rows.push([L('写入','Written'),r.result && r.result!=='completed'?'warn':'good',sel?L(`光驱报告写完了（请求 ${X(sel)}，光驱报告 ${actual==null?'没报':X(actual)}）。`,`The drive reports the write finished (asked ${X(sel)}, drive reports ${actual==null?'nothing':X(actual)}).`):L('光驱报告写完了。','The drive reports the write finished.')]);
  const c=job?.closed;
  rows.push([L('关盘','Closed'),c===true?'good':c===false?'warn':'unknown',
    c===true?L('已关盘，别的光驱和电脑也能读。','Finalized: other drives and computers can read it.')
    :c===false?L('没有关盘：别的光驱可能读不出。用刻录软件给这张盘关盘（finalize）。','Not finalized: other drives may not read it. Finalize it with a burning program.')
    :c==='checking'?L('正在读光驱里的盘（只读）…','Reading the disc in the drive (read-only)…')
    :L('没读到，不知道。刻录时已要求关盘；可以在盘库里点光驱重新读一次。','Not read, so not known. The burn asked for it; read the drive again from the library to check.')]);
  if(!v)rows.push([L('回读','Read back'),'unknown',L('这次没有回读结果。','No read-back result for this burn.')]);
  else if(v.status==='skipped')rows.push([L('回读','Read back'),'unknown',L('跳过了（--no-verify）。','Skipped (--no-verify).')]);
  else if(v.status==='completed'&&!v.differing&&!v.unreadable&&!v.untested)rows.push([L('回读','Read back'),'good',L(`抽样读回通过：${v.ok} 块都对得上（最多抽 96 块，均匀分布在盘上）。这是抽样，不是整盘检查。`,`Sampled read-back passed: all ${v.ok} blocks match (up to 96, spread evenly over the disc). A sample, not a whole-disc check.`)]);
  else rows.push([L('回读','Read back'),'warn',L(`抽样里 ${v.unreadable} 块读不出、${v.differing} 块不对${v.untested?`、${v.untested} 块没查到`:''}。图案仍可能看得见；先看一眼，再决定要不要换速度重刻。`,`In the sample, ${v.unreadable} blocks unreadable, ${v.differing} differing${v.untested?`, ${v.untested} not checked`:''}. The picture may still show; look first, then decide whether to burn again at another speed.`)]);
  rows.push([L('图案','Picture'),'unknown',job?.observation?.choice === 'correct'
    ? L('你记录了：看到了，位置对。这是实物观察，不是程序验证。','You recorded: visible and aligned. This is your observation, not a software check.')
    : L('还没确认。程序看不到盘上的图，拿到灯下按下面的方法看一眼。','Not confirmed yet. The program cannot see the picture; look at the disc under a light as below.')]);
  return rows;
}
function paint() {
  if(task?.status==='success' && burnFailed(task.burnResult)) {
    task.status='failed';
    task.error=task.burnResult.reason || (api.lang()==='en'?'This burn did not check out. Re-read this disc and inspect the saved logs before another burn.':'这次刻录没有通过检查。请重新读取这张盘，查看保存的日志，再决定是否重刻。');
  }
  if(!W)return;const t=T(),q=W.q, status=task?.status||'ready', active=status==='burning', hasInput=valid();
  W.page.dataset.state=status;W.page.classList.toggle('burn-reduce',!!api.reduce);q('.burn-speed').hidden=status!=='ready'||!!ctx.otherOnly;q('.burn-consent').hidden=status!=='ready'||!hasInput;q('.burn-warning').hidden=status!=='ready'||!hasInput;
  q('.warn-sign').classList.toggle('on', ['failed','cancelled'].includes(status));
  W.select.disabled=active; q('[data-a="cancel"]').hidden=!active||q('[data-a="cancel"]').getAttribute('aria-expanded')==='true';q('[data-a="cancel"]').disabled=!!task?.stopping;q('[data-a="retry"]').hidden=!['failed','cancelled'].includes(status)||!!task?.notStarted;q('[data-a="recheck"]').hidden=!((status==='failed'&&task?.notStarted)||(!hasInput&&!task&&!swapping&&ctx.recheck&&ctx.drive?.id));q('[data-a="photo"]').hidden=status!=='success'||!ctx.photograph;
  q('[data-a="cancel"]').textContent=task?.erasing?(api.lang()==='en'?'Stop erasing':'停止擦除'):stopWords(api.lang()).stop;
  q('.burn-timing').hidden=!active;const times=q('.burn-timing').children;times[0].textContent=`${t.elapsed} ${time(task?.elapsed)}`;times[1].textContent=`${t.remaining} ${time(task?.remaining)}`;
  const key=ctx.otherOnly?'otherOnly':!hasInput?((swapping||ctx.needSwap)?'swapping':'missing'):status==='success'?'done':status==='ready'?'ready':status==='burning'?'writing':status;
  if(ctx.otherOnly)q('.burn-other').open=true;
  q('.burn-result h2').textContent=key==='failed'&&task?.notStarted?t.notStarted:t[key];q('.burn-result p').textContent=!hasInput?(ctx.driveProblem||t.missingNote):active?(task.stopping?t.stopping:t.running):(key==='failed'&&task?.error)||t[`${key}Note`]||'';
  if(active&&task?.erasing){q('.burn-result h2').textContent=api.lang()==='en'?'Erasing the disc':'正在擦除光盘';q('.burn-result p').textContent=api.lang()==='en'?'The disc contents are being cleared. Keep the drive connected. Stopping waits for the drive to finish; inspect and erase again before burning.':'正在清掉盘上的内容，请保持光驱连接。停止后需等待光驱收尾，重新检测并擦除后才能刻录。';}
  if(active&&task?.verifying)q('.burn-result p').textContent=api.lang()==='en'?'Write complete. Reading back a sample; drive retries may take time…':'写入完成，正在抽样回读；光驱重试可能需要一些时间…';
  if(active&&task?.verifying){
    q('[data-a="cancel"]').textContent=api.lang()==='en'?'Stop read-back':'停止回读';
  }
  if(status==='cancelled'&&task?.userStopped&&task.cancelPhase==='erase')q('.burn-result p').textContent=api.lang()==='en'?'Erasing stopped. Disc state is uncertain; inspect and erase again before burning.':'擦除已停止，盘的状态未知。重新检测并擦除后才能刻录。';
  else if(status==='cancelled'&&task?.userStopped&&!task.verifying)
    q('.burn-result p').textContent=interruptedBurn({rewritable:ctx.drive?.rewritable,cancelledByUser:{phase:'burn',fraction:task.progress}},api.lang());
  const report=task?.burnResult||task?.speedReport;
  if(report){
    const en=api.lang()==='en', actual=report.actual_speed_x;
    let note=en?`Requested: ${X(report.selected_speed_x)}; drive/utility reports: ${actual==null?'not reported':X(actual)}. `:`请求速度：${X(report.selected_speed_x)}；光驱/工具报告：${actual==null?'未报告':X(actual)}。`;
    const v=report.verification;
    if((status==='success'||status==='failed')&&v){
      if(status==='failed')note=(task.error||report.reason||'')+' '+note;
      if(v.status==='skipped')note+=en?'Read-back skipped.':'已跳过回读验证。';
      else {
        note+=en?`Sample: ${v.ok} blocks ok / ${v.differing} differing / ${v.unreadable} unreadable; ${v.untested} untested. `:`抽样：${v.ok} 块一致 / ${v.differing} 块不同 / ${v.unreadable} 块无法读取；${v.untested} 块未检查。`;
        if(v.status!=='completed'||v.differing||v.unreadable||v.untested){
          note+=en?'This burn did not check out. Re-read this same disc and inspect the saved logs before another burn. ':'这次刻录没有通过检查。请重新读取这张盘，查看保存的日志，再决定是否重刻。';
          q('.burn-result h2').textContent=en?'Burn check failed':'刻录检查未通过';
        }
        else note+=en?'Only a sample was checked, not the whole disc. ':'仅检查了样本，并非整盘验证。';
        note+=(v.failures||[]).map(f=>`LBA ${f.lba} (~${f.radius_mm.toFixed(2)} mm, ${en?'nominal':'标称'})`).join('; ');
      }
      // a clean sample is said once, in the checks below; the paragraph stays for problems and their places
      if(status==='success'&&v.status==='completed'&&!v.differing&&!v.unreadable)note='';
      q('.burn-result p').textContent=note;
    }else if(active)q('.burn-result p').textContent+=' '+note;
  }
  // four separate answers once the write is done: written, closed, read back, looks right (never one "done")
  let checks=q('.burn-checks');if(!checks){checks=el('dl','burn-checks');q('.burn-result').after(checks);}
  checks.hidden=status!=='success';
  if(status==='success'){
    // whether the disc was closed: read once, at most 20 s; a read that does not answer ends as "not read" with a
    // button to read again, never a row that stays "reading" (W11)
    if(task.closed===undefined&&ctx.checkDisc){const mine=task;mine.closed='checking';
      Promise.race([ctx.checkDisc(),new Promise(r=>setTimeout(()=>r('late'),20000))])
        .then(d=>{if(mine.closed==='checking')mine.closed=d==='late'?null:d?.present?d.closed??null:null;},()=>{if(mine.closed==='checking')mine.closed=null;})
        .finally(()=>{if(W)paint();});}
    checks.replaceChildren(...afterChecks(task).flatMap(([label,s,text])=>{const dd=el('dd','',text);dd.dataset.s=s;return [el('dt','',label),dd];}));
    if(task.closed===null&&ctx.checkDisc){const b=el('button','sbtn',T().recheckClosed);b.type='button';b.dataset.a='recheckClosed';checks.append(el('dt','',''),b);}
  }
  let advice=q('.burn-advice');if(!advice){advice=el('div','burn-advice');checks.after(advice);}
  // how to look and what each symptom means after a write; what to do next after a failed one
  const failedAfterStart=['failed','cancelled'].includes(status)&&!task?.notStarted;
  advice.hidden=status!=='success'&&!failedAfterStart;
  advice.replaceChildren(...(status==='success'?afterBurn.slice(0,2):afterBurn.slice(2)).map(words=>el('p','',words[api.lang()==='en'?'en':'zh'])));
  q('.burn-intro').hidden=status==='success'||!!ctx.otherOnly;
  // burned with a command: what to do and the command come first, under the title; nothing to hold here
  if(ctx.otherOnly)q('h1').after(q('.burn-result'),q('.burn-other'),checks,advice);
  else if(status==='success')q('h1').after(q('.burn-result'),checks,advice);
  else q('.burn-consent').after(q('.burn-result'),checks,advice);
  const p=Math.round((task?.progress||0)*100);W.progress.style.setProperty('--progress',`${p}%`);W.miniRing.style.setProperty('--progress',`${p}%`);
  const caption=active?`${p}% · ${t.percent}`:status==='success'?t.done:t[key];q('.burn-scene-caption').textContent=caption;W.mini.lastChild.textContent=active?`${p}%`:t[key];
  q('.burn-disc').setAttribute('role','progressbar');q('.burn-disc').setAttribute('aria-label',t.writing);q('.burn-disc').setAttribute('aria-valuemin','0');q('.burn-disc').setAttribute('aria-valuemax','100');q('.burn-disc').setAttribute('aria-valuenow',String(p));
  W.mini.hidden=visible||!task; if(!visible||!W.next)return;
  W.next.disabled=!ctx.otherOnly && status!=='success' && (status!=='ready'||!hasInput||!W.consent.checked);
  api.nextWhy?.(status==='burning'?t.whyBurning:status==='failed'||status==='cancelled'?t.whyAgain:!hasInput?(swapping||ctx.needSwap?t.whySwap:t.whyMissing):t.whyConsent);
  const text=api.$('next-text');if(text)text.textContent=ctx.otherOnly?(ctx.done?t.finish:t.back):status==='success'&&!ctx.iso?.target?(api.lang()==='en'?'Next: how did it look?':'下一步：结果怎么样？'):status==='success'?(ctx.readBack?t.read:ctx.done?t.finish:t.back):status==='burning'?t.writing:t.hold;
  nextConfirm(W.next, {active:status==='ready' && !ctx.otherOnly, disabled:W.next.disabled,
    lang:api.lang(), label:t.hold, done:beginBurn});
}
// the drive scene: the home page's drive flipped, a disc that drops in, the cutaway while it burns
function sceneOf(){return scene??={cut:cutaway(api,{mirrored:false,textLeft:()=>W.q('.burn-panel').getBoundingClientRect().left}),fly:flyer(api,{mirrored:false})};}
function waitForDisc(){api.setTray(true,false,undefined,true);setTimeout(()=>{if(visible&&!task)sceneOf().fly.hover(ctx.item?.name||'');},900);}
function fillSpeeds(){
  const speeds=[...new Set((ctx.drive?.speeds||[]).filter(x=>Number.isFinite(x)&&x>0))].sort((a,b)=>a-b);
  // the drive reports its write speeds only for a blank disc: until one is in, say so instead of an empty list
  if(!speeds.length){speed=undefined;W.select.replaceChildren(el('option','',T().speedUnknown));W.select.disabled=true;return;}
  W.select.disabled=false;
  if(!speeds.includes(speed))speed=ctx.media==='cd'?speeds[0]:speeds.reduce((best,s)=>Math.abs(s-8)<Math.abs(best-8)?s:best,speeds[0]);W.select.replaceChildren(...speeds.map(s=>{const o=el('option','',X(s));o.value=s;return o;}));W.select.value=speed;
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
    // the wait ended without a new disc (timed out, or the drive could not be watched): say so, and offer to look again
    swapping=null;ctx.driveProblem=T().swapStopped;paint();return;
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
// Clean read-back, something to review, nothing written, or a disc lost.
function chime(p){
  const v=(p.burnResult||task?.burnResult)?.verification;
  if(p.status==='success')(v&&v.status!=='skipped'&&(v.status!=='completed'||v.differing||v.unreadable))?sfx.problem():sfx.done();
  else if(p.status==='failed')(p.started===false?sfx.problem:sfx.failure)();
}
async function beginBurn() {
  if(!visible||!valid()||!W.consent.checked||task?.status==='burning')return;
  task={status:'burning',progress:0,elapsed:0,remaining:undefined,handle:null,stopping:false}; const current=task;
  sfx.step(0);
  closeBurnStop();paint();
  const sc=sceneOf(); if(!ctx.discIn)await sc.fly.drop(); if(task!==current)return;
  api.placeDisc(true);api.setTray(false,true);
  try { const handle=ctx.burn(p=>{if(task!==current||current.status!=='burning')return;if(p.erasing!==undefined){if(current.erasing&&!p.erasing)current.progress=0;current.erasing=p.erasing;} if(p.burnResult)current.burnResult=p.burnResult;if(p.speedReport)current.speedReport=p.speedReport;if(p.verifying&&!current.verifying){current.verifying=true;closeBurnStop();sfx.step(1);} current.progress=Number.isFinite(p.progress)?Math.max(current.progress,Math.min(1,p.progress)):current.progress;current.elapsed=p.elapsed;current.remaining=p.remaining;sc.cut.update(current.progress,current.remaining);if(['success','failed','cancelled'].includes(p.status)){current.status=p.status;chime(p);if(p.error)current.error=p.error;if(p.started===false)current.notStarted=true;if(p.status==='success')current.progress=1;closeBurnStop();setTimeout(()=>sc.cut.show(false),1200);}paint();},{speed,erase:!!ctx.drive.eraseRequired});current.handle=handle;
    setTimeout(()=>{if(task===current&&current.status==='burning'&&visible){sc.cut.update(current.progress,current.remaining);sc.cut.show(true);}},900); }
  catch (e) {current.status='failed';current.error=e?.message||'';current.notStarted=true;paint();}
}
function toast(message){W.toast.textContent=message;W.toast.classList.add('on');clearTimeout(toastTimer);toastTimer=setTimeout(()=>W.toast.classList.remove('on'),2600);}
async function action(a) {
  if(a==='recheckClosed'&&task){task.closed=undefined;paint();return;}
  if(a==='cancel'&&task?.status==='burning'&&!task.stopping){
    const current=task;
    const stop=async()=>{
      if(task!==current||current.status!=='burning'||current.stopping)return;
      current.cancelPhase=current.erasing?'erase':current.verifying?'read-back':'burn';current.stopping=true;paint();
      try{await current.handle.cancel();current.userStopped=true;}
      catch{current.stopping=false;toast(T().failedNote);}paint();
    };
    if(current.verifying||current.erasing)await stop();
    else expandBurnStop(W.q('[data-a="cancel"]'),{lang:api.lang(),rewritable:!!ctx.drive?.rewritable,valid:()=>task===current&&current.status==='burning'&&!current.verifying&&!current.stopping,done:stop});
  }
  if(a==='retry'&&ctx.drive?.rewritable){task=null;ctx.drive.eraseRequired=true;ctx.driveProblem='';ctx.needSwap=false;W.consent.checked=false;closeBurnStop();words();return;}
  if(a==='retry'){task=null;W.consent.checked=false;closeBurnStop();words();if(ctx.swap){ctx.discIn=false;ctx.needSwap=true;ctx.drive.speeds=[];fillSpeeds();swapFlow();}else waitForDisc();}
  if(a==='recheck'){task=null;W.consent.checked=false;ctx.driveProblem='';words();
    if(ctx.recheck){try{swapping={};ctx.driveProblem=ctx.swapWords?.checking||'';paint();await ctx.recheck();}catch(e){ctx.driveProblem=e?.message||'';}finally{swapping=null;}
      if(!visible)return;fillSpeeds();words();if(ctx.needSwap)swapFlow();}else waitForDisc();}
  if(a==='photo')ctx.photograph?.();
  if(a==='copy'){try{await navigator.clipboard.writeText(ctx.otherCommand||ctx.iso.path);toast(ctx.otherCommand?T().copiedCommand:T().copied);}catch{toast(T().copyFail);}}
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
  W.next=api.$('next');W.nextLabel=api.$('next-text')?.textContent;
  W.back=api.$('back');W.backHidden=W.back.hidden;W.back.hidden=false;W.backLabel=W.back.innerHTML;W.back.replaceChildren(T().back,...W.back.querySelectorAll('.key-cap'));
  W.events=new AbortController();const signal=W.events.signal, on=(node,event,fn)=>node.addEventListener(event,fn,{signal,capture:true});
  on(W.next,'click',async e=>{e.preventDefault();e.stopImmediatePropagation();if(task?.status==='success'&&!ctx.iso?.target){
    W.next.disabled=true;
    try { const review=await import('./afterburn.js'); await review.fromBurn(api,ctx); }
    catch(e){toast(e?.message||String(e));paint();}
    return;
  }if(task?.status==='success'||ctx.otherOnly){if(ctx.readBack&&!ctx.otherOnly)ctx.readBack();else{leave();(ctx.done||ctx.back)?.();}}});
  on(W.back,'click',e=>{e.preventDefault();e.stopImmediatePropagation();leave();ctx.back?.();});
  words();
  // Arrival is visual only: the tray in the picture opens, the real drive is not touched before confirmation.
  if(!task){if(ctx.needSwap)swapFlow();else if(ctx.swap){ctx.discIn=true;api.placeDisc(true);api.setTray(false,true,undefined,true);}else waitForDisc();} else if(task.status==='burning')setTimeout(()=>{if(visible)sceneOf().cut.show(true);},750);
}
export function leave() {
  if(!W||!visible)return;
  closeBurnStop();
  const from=W.q('.burn-disc').getBoundingClientRect();
  nextConfirm(W.next);visible=false;W.events.abort();if(swapping){swapping=null;ctx.stopSwap?.();}scene?.fly.hide();scene?.cut.show(false);W.page.hidden=true;W.next.disabled=false;W.back.innerHTML=W.backLabel;W.back.hidden=W.backHidden;if(api.$('next-text'))api.$('next-text').textContent=W.nextLabel;root.dataset.mode='';paint();
  if(task&&!api.reduce){const to=W.miniRing.getBoundingClientRect();W.mini.animate([{transform:`translate(${from.left-to.left}px,${from.top-to.top}px) scale(${from.width/to.width})`,opacity:.5},{transform:'none',opacity:1}],{duration:420,easing:'cubic-bezier(.2,.8,.2,1)'});}
}
