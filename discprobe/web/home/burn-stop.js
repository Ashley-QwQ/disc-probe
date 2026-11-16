// The existing burn slider, with a three-second reading lock before destructive cancellation.
import { slideConfirm } from './kit/slideconfirm.js';
let active = null;
export const stopWords = lang => lang === 'en' ? {
  stop:'Stop burn', risk:'Stopping makes this disc unusable: it cannot be burned again or measured.',
  keep:'Continue burning', slide:'Slide to stop burning', ready:'Unlocked. Slide to stop burning.',
} : {
  stop:'停止刻录', risk:'停止后这张盘作废：不能再刻，也不能拿来测。',
  keep:'继续刻录', slide:'滑动停止刻录', ready:'倒计时结束，可以滑动停止刻录。',
};
export function closeBurnStop() { active?.close(); }
export function expandBurnStop(button, {lang='zh', valid=()=>true, done=()=>{}}={}) {
  closeBurnStop();
  const t=stopWords(lang), doc=button.ownerDocument;
  const panel=doc.createElement('div'); panel.className='burn-stop';
  panel.innerHTML='<p class="burn-stop-risk" role="status" aria-live="assertive"></p><div class="burn-stop-slider"></div><p class="kit-sr" role="status" aria-live="polite"></p><button type="button" class="btn burn-stop-keep"></button>';
  button.after(panel); button.hidden=true;button.setAttribute('aria-expanded','true');
  const risk=panel.querySelector('.burn-stop-risk'), host=panel.querySelector('.burn-stop-slider');
  risk.textContent=t.risk;
  const keep=panel.querySelector('button'); keep.textContent=t.keep;
  let closed=false, timer;
  const close=()=>{
    if(closed)return; closed=true; clearInterval(timer); slider.destroy(); panel.remove();
    button.hidden=false;button.setAttribute('aria-expanded','false'); doc.removeEventListener('keydown',key,true); doc.removeEventListener('pointerdown',outside,true);
    if(active?.close===close)active=null;
  };
  const key=e=>{if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();close();button.focus();}};
  const outside=e=>{if(!host.contains(e.target)&&!keep.contains(e.target)&&e.target!==button)close();};
  const slider=slideConfirm(host,{lang,holdPress:true,disabled:true,label:t.slide,done:()=>{
    if(!valid()){close();return;} close();done();
  }});
  const caption=host.querySelector('.kit-slide-label'), until=performance.now()+3000;
  const tick=()=>{
    if(!valid()){close();return;}
    const left=Math.max(0,Math.ceil((until-performance.now())/1000));
    caption.textContent=left ? `${t.slide} · ${left}` : t.slide;
    if(!left){clearInterval(timer);slider.setDisabled(false);panel.querySelector('.kit-sr[role="status"]').textContent=t.ready;}
  };
  keep.onclick=()=>{close();button.focus();};
  doc.addEventListener('keydown',key,true); doc.addEventListener('pointerdown',outside,true);
  active={close};tick();timer=setInterval(tick,100);keep.focus();
}
export function paintStopButton(button, burning, lang) {
  const text=burning?stopWords(lang).stop:(lang==='en'?'Cancel':'取消');
  button.classList.toggle('btn-icon',!burning);button.setAttribute('aria-label',text);
  if(burning)button.textContent=text;
  else button.innerHTML='<svg class="icon" aria-hidden="true"><use href="#i-x"/></svg>';
}
export function shortDiscWords(disc, lang='zh') {
  const n=disc?.sectors, capacity=disc?.capacity_sectors;
  if(disc?.closed!==true||disc?.blank!==false||!Number.isInteger(n)||n<=0||n>(Number.isInteger(capacity)&&capacity>0?capacity*.01:4096))return null;
  const mb=Math.round(n*2048/1048576);
  return lang==='en'?`This disc has only the beginning recorded (${n} sectors, about ${mb} MB). Burning probably stopped partway; it cannot be used for measurement. Replace it with a blank disc and burn again.`
    :`这张盘只刻了开头一点（${n} 扇区，约 ${mb} MB），多半是刻录中途停了，不能用来测。换一张空白盘重新刻。`;
}
export function interruptedBurn(flow, lang='zh') {
  const burn=flow.burnCheck, cancelled=flow.cancelledByUser?.phase==='burn';
  if(!cancelled&&!['cancelled','failed','stopped'].includes(burn?.result)&&!flow.burnInterrupted)return null;
  const p=flow.cancelledByUser?.fraction ?? flow.burnP;
  const percent=Number.isFinite(p)?`${Math.round(Math.max(0,Math.min(1,p))*100)}%`:(lang==='en'?'unknown progress':'进度未知');
  if(cancelled)return lang==='en'?`You stopped the burn. It stopped at about ${percent}. This disc is unusable: it cannot be burned again or measured. Start again with a blank disc from the same batch.`
    :`你在刻录时点了停止。刻到约 ${percent} 停下，这张盘已经作废，不能再刻也测不了。换一张同批的空白盘，重新开始。`;
  return lang==='en'?`The burn did not finish: ${burn?.reason||flow.error||burn?.result||'cause unknown'}. Replace it with a blank disc from the same batch and burn again.`
    :`刻录没有完成：${burn?.reason||flow.error||burn?.result||'原因未知'}。换一张同批的空白盘重新刻。`;
}
