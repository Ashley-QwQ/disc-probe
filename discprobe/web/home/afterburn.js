// Operate: inspect a saved burn. Opening this page never sends a drive command.
import { isMeasurementWork, worksFor } from './pastworks/works.mjs';
import { afterChecks, leave as leaveBurn, start as startBurn } from './burn.js';
import { checkBurn, confirmBurn } from './burn-preflight.js';
import { afterBurn, troubleChecks, cdPhoto } from './guidance.mjs';
import { burnChecklist } from './checkburn.js';
import { colourShootGuide, mountColourShootStyles } from './design/colour-shoot-guide.mjs';

export function latestBurn(works) {
  return works.filter(work => !isMeasurementWork(work)).map(work => ({work, record:[...(work.discs ?? [])].reverse().find(r => r.type === 'burn' && !r.measurement)}))
    .filter(x => x.record).sort((a,b) => Date.parse(b.record.time) - Date.parse(a.record.time))[0]?.work ?? null;
}
export function closedFromReport(report) {
  const disc = report?.disc_state?.disc;
  return disc?.disc_status === 'complete' && disc.last_session_state === 3 ? true
    : disc && (disc.disc_status === 'incomplete' || disc.last_session_state != null && disc.last_session_state !== 3) ? false : null;
}
export function reviewTask(record) {
  return {burnResult:record.report ?? {result:record.result,selected_speed_x:record.speed,
    actual_speed_x:record.actual_speed_x, verification:record.verification},
    closed:closedFromReport(record.report), observation:record.observation};
}
const choices = {
  correct:['看到了，位置对','Visible and aligned'], invisible:['看不见','No picture'],
  distorted:['歪了或扭了','Skewed or twisted'], gaps:['断开或缺块','Gaps or missing pieces'],
};
let api, client, data, page, life, thumbURL, checkPanel, colourSetup, saving=false;
const root = document.documentElement;
const L = (zh,en) => api.lang() === 'en' ? en : zh;
const words = pair => pair[api.lang() === 'en' ? 'en' : 'zh'];
const el = (tag,cls,text) => {const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
const button = (zh,en,run) => {
  const b=el('button','',L(zh,en));b.type='button';
  b.onclick=async()=>{if(b.disabled)return;b.disabled=true;b.setAttribute('aria-busy','true');
    try{await run(b);}finally{b.disabled=false;b.removeAttribute('aria-busy');}};
  return b;
};
function message(text) { const p=page.querySelector('.ab-message');p.textContent=text;p.hidden=!text; }
async function attempt(run) {try {await run();}catch(e){message(L('没有完成：','Could not complete: ')+(e?.message ?? e));}}
function basePath() {return `/api/works/${encodeURIComponent(data.work_id)}/after-burn`;}

export async function fromBurn(homeApi,context) {
  const c=await worksFor(homeApi), list=await c.list();
  const path=String(context.iso.path).replaceAll('\\','/');
  const matches=list.flatMap(work=>(work.discs??[]).filter(r=>r.type==='burn' && (String(r.iso_path).replaceAll('\\','/')===path || String(r.iso_path).replaceAll('\\','/').endsWith('/'+path))).map(record=>({work,record})));
  const jobId=context.iso.burnResult?.job;
  const found=(jobId && matches.find(x=>x.record.job_id===jobId)) || matches.sort((a,b)=>Date.parse(b.record.time)-Date.parse(a.record.time))[0];
  if (!found) throw Error(homeApi.lang()==='en'?'No saved burn record was found. Keep the burn log and save the work before leaving.':'没有找到已保存的刻录记录。请保留刻录日志，存好作品后再离开。');
  // Load before stepping aside so an I/O error leaves the existing result accessible.
  await c.afterBurn(found.work.id,found.record.burn_id);
  leaveBurn();return open(homeApi,found.work.id,found.record.burn_id,context.iso.colourGuide??null);
}
export async function open(homeApi,id,burnId=null,setup=undefined) {
  api=homeApi;client=await worksFor(api);
  const nextData=await client.afterBurn(id,burnId);
  leave();data=nextData;
  // Archived reports do not store the exact rig used for that ISO.
  colourSetup=setup===undefined&&data.media==='dvd'?{}:setup;
  if(colourSetup)mountColourShootStyles();
  if(!page){
    for(const file of ['burn.css','afterburn.css','checkburn.css']) {const link=el('link');link.rel='stylesheet';link.href=new URL(file,import.meta.url);document.head.append(link);}
    page=el('main','burn-page after-burn');page.hidden=true;document.body.append(page);
  }
  root.dataset.mode='afterburn';page.hidden=false;life=new AbortController();
  const signal=life.signal;
  checkPanel=burnChecklist(api,id,data.record.burn_id,signal);
  api.$('back').hidden=false;
  api.$('back').addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();leave();api.toLobby?.();},{capture:true,signal});
  api.$('next').addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();if(!saving){leave();api.toLobby?.();}},{capture:true,signal});
  addEventListener('dp-lang',render,{signal});render();
  // A missing legacy snapshot is stated explicitly, never replaced with today's design.
  try {
    if(data.record.preview_available===false)throw Error('no source design');
    const blob=await client.burnThumb(id,data.record.burn_id);
    if(signal.aborted)return;
    thumbURL=URL.createObjectURL(blob);const img=page.querySelector('.ab-disc');img.src=thumbURL;img.hidden=false;
  } catch {if(!signal.aborted)page.querySelector('.ab-preview-note').textContent=L('这次刻录没有保存预览。当前设计仍可从作品库打开。','No preview was saved with this burn. The current design is still in the library.');}
}
export function leave() {
  life?.abort();life=null;if(page){page.hidden=true;page.replaceChildren();}
  if(thumbURL)URL.revokeObjectURL(thumbURL);thumbURL=null;
  if(root.dataset.mode==='afterburn')root.dataset.mode='';
}
function render() {
  if(!life)return;
  const r=data.record, choice=r.observation?.choice;
  const guideOpen=page.querySelector('.colour-shoot-guide')?.open;
  page.replaceChildren();
  const layout=el('div','burn-layout'), hero=el('section','ab-hero'), img=el('img','ab-disc');
  img.alt=L('本次刻录保存的设计预览','Design preview saved with this burn');img.hidden=!thumbURL;if(thumbURL)img.src=thumbURL;
  hero.append(img,el('p','ab-preview-note',L('本次刻录的设计缩略图 · 512 像素，不是实物照片','Saved design thumbnail · 512 pixels, not a physical photograph')));
  const sheet=el('section','burn-panel ab-sheet');
  sheet.append(el('h1','',L('结果怎么样？','How did it look?')),el('p','ab-name',data.name));
  if(colourSetup)sheet.insertAdjacentHTML('beforeend',colourShootGuide(colourSetup,api.lang(),guideOpen));
  const group=el('div','ab-choices');group.setAttribute('role','group');group.setAttribute('aria-label',L('记录实物结果','Record what you saw'));
  for(const [key,pair] of Object.entries(choices)) {
    const b=button(...pair,()=>observe(key));b.dataset.choice=key;b.setAttribute('aria-pressed',String(choice===key));b.disabled=saving;group.append(b);
  }
  sheet.append(group,el('p','ab-message',''));
  const troubleshooter=checkPanel();if(troubleshooter)sheet.append(troubleshooter);
  const branch=el('section','ab-branch');branch.setAttribute('aria-live','polite');
  if(choice==='correct')branch.append(el('h2','',L('已存进作品库','Saved in the library')),el('p','',L('已记录你看到了图，位置正确。以后同批盘可以复用这次测量。','Your observation is saved. Reuse this measurement for later discs from the same batch.')));
  if(choice==='invisible'){
    branch.append(el('h2','',L('先看光照，再看报告','Check the light, then the report')),el('p','',words(afterBurn[0])),
      button('打开光照说明（带图）','Open illustrated lighting guide',async b=>(await import('./guide.js')).open(b)));
  }
  if(choice==='distorted'){
    branch.append(el('h2','',L('先核对这条路径','Check this path first')),el('p','',words(troubleChecks[2].body)));
    const geo=r.geo_run;
    branch.append(button('回到这次测量看覆盖和检查','Review this measurement and its coverage',()=>attempt(measurement)));
    if(data.media==='dvd')branch.append(el('p','',L('DVD：换同批空白盘刻检查盘，拍照修正沿轨偏移，再打开作品重新生成。','DVD: burn a check disc on a fresh blank from this batch, photograph it to correct the along-track offset, then regenerate the work.')),
      button('生成检查盘并去刻录','Generate a check disc and review burning',()=>attempt(checkDisc)));
    else branch.append(el('p','',words(cdPhoto)),button('拍照读取这次测量的沿轨偏移','Read the along-track offset from photos',()=>attempt(async()=>{
      if(!geo)throw Error(L('这次刻录没有关联测量，先从作品库核对。','No measurement is linked to this burn. Check the work first.'));
      const current=data;leave();(await import('./calibrate.js')).photograph(api,{media:'cd',geo,burnCheck:r.report,returnTo:()=>open(api,current.work_id,r.burn_id)});
    })));
    branch.append(button('打开作品，修正后重新生成','Open the work to regenerate after correction',()=>attempt(edit)),
      el('p','',words(troubleChecks[2].reburn)));
    const last=el('details');last.append(el('summary','',L('前面都没问题，才重新测量','Remeasure only after those checks pass')),
      el('p','',L('保留测量盘；先核对光照、报告、盘批次和光驱。仅在这些都没问题且线条仍扭曲时，才继续检查几何。','Keep the measurement disc. Check lighting, reports, batch and drive first. Investigate the geometry further only if all those are fine and lines still twist.')),
      button('核对后进入标定','Open calibration after checking',()=>attempt(async()=>{leave();(await import('./calibrate.js')).start(api,{returnTo:()=>open(api,data.work_id,r.burn_id)});})));branch.append(last);
  }
  if(choice==='gaps')branch.append(el('h2','',L('查看刻录报告','Review the burn report')),el('p','',words(troubleChecks[1].body)),el('p','',words(afterBurn[2])),
    button('打开作品，换速度重新准备刻录','Open the work to prepare another write speed',()=>attempt(edit)));
  if(choice)sheet.append(branch);
  const report=el('details','ab-report');report.open=['invisible','gaps'].includes(choice);
  report.append(el('summary','',L('刻录报告：写入、关盘、回读、图案','Burn report: written, closed, read back, picture')));
  const checks=el('dl','burn-checks');
  for(const [label,status,text] of afterChecks(reviewTask(r),api.lang()==='en')) {const dd=el('dd','',text);dd.dataset.s=status;checks.append(el('dt','',label),dd);}
  if(r.result!=='completed') {checks.children[1].dataset.s='warn';checks.children[1].textContent=L('写入或检查没有完成。请查看原始报告。','The write or its checks did not complete. Read the original report.');}
  report.append(checks);
  const raw=el('details');raw.append(el('summary','',L('原始报告和文件','Original report and files')),el('pre','burn-data',JSON.stringify(r,null,2)));report.append(raw);sheet.append(report);
  const links=el('div','burn-actions');
  if(r.preview_available)links.append(button('查看本次预览','View this burn’s preview',()=>attempt(preview)));
  links.append(button('打开作品','Open work',()=>attempt(edit)));sheet.append(links);
  layout.append(hero,sheet);page.append(layout);
  api.$('back').replaceChildren(L('返回大厅','Back to the lobby'));api.$('next-text').textContent=L('完成，回到大厅','Done: back to the lobby');api.$('next').disabled=saving;api.nextWhy?.('');
}
async function observe(choice) {
  if(saving)return;saving=true;render();
  try {
    data=await client.observeBurn(data.work_id,data.record.burn_id,choice);
    // W13 extension point: a future listener may celebrate a user-confirmed picture. No animation here.
    if(choice==='correct')dispatchEvent(new CustomEvent('dp-after-burn-confirmed',{detail:{workId:data.work_id,burnId:data.record.burn_id}}));
  }catch(e){saving=false;render();message(L('没有保存，请重试：','Not saved; retry: ')+(e?.message??e));return;}
  saving=false;render();
}
async function edit() {
  const work=await client.get(data.work_id), text=await client.design(data.work_id);leave();
  (await import('./design.js')).start(api,{fly:false,work:{...work,text}});
}
async function preview() {
  if(!thumbURL)throw Error(L('保存的预览还没有读到，请稍后再试。','The saved preview is not loaded yet. Try again shortly.'));
  const image=new Image();image.src=thumbURL;await image.decode();
  const canvas=el('canvas');canvas.width=canvas.height=512;canvas.getContext('2d').drawImage(image,0,0);
  const current=data;leave();
  (await import('./preview.js')).start(api,{media:current.media,reviewSaved:true,project:{name:current.name,render:()=>canvas},
    back:()=>open(api,current.work_id,current.record.burn_id),next:()=>open(api,current.work_id,current.record.burn_id)});
}
async function measurement() {
  const m=await api.backend.request(basePath()+`/measurement?burn=${encodeURIComponent(data.record.burn_id)}`);
  const box=el('section','ab-measurement');box.append(el('h2','',L('这次测量：覆盖和检查','This measurement: coverage and checks')),el('p','burn-data',m.path));
  const chart=await import('./calchart.js');box.insertAdjacentHTML('beforeend',chart.resultChart(m.measurement,{zh:api.lang()!=='en'}));
  const details=el('details');details.append(el('summary','',L('测量原始检查','Original measurement checks')),el('pre','burn-data',JSON.stringify(m,null,2)));box.append(details);
  page.querySelector('.ab-measurement')?.remove();page.querySelector('.ab-branch').append(box);box.scrollIntoView({block:'nearest'});
}
async function checkDisc() {
  const current=data, r=current.record, geo=r.geo_run;
  if(!geo)throw Error(L('这次刻录没有关联测量，请先核对作品。','No measurement is linked to this burn. Check the work first.'));
  message(L('正在生成检查盘；还不会刻录。','Generating a check disc; no write has started.'));
  const output=`iso/check-${Date.now()}.iso`;
  await api.backend.job({action:'checkdisc',media:'dvd',args:{geo,output}});
  const iso=await api.backend.request(`/api/iso?path=${encodeURIComponent(output)}`);iso.target=true;iso.geo=geo;
  const drive={id:r.drive,name:r.drive,speeds:[]};
  const request=(speed,erase)=>({action:'burn',drive:drive.id,media:'dvd',
    args:{iso:iso.path,...(speed?{speed}:{}),...(erase?{erase:true}:{})}});
  const ctx={media:'dvd',item:{name:current.name},iso,drive,preflight:true,
    back:()=>open(api,current.work_id,r.burn_id),done:()=>ctx.photograph(),
    async recheck(){
      const seen=await checkBurn(api.backend,request(null,drive.eraseRequired));
      ctx.burnDisc=seen.disc;ctx.burnGate=seen.gate;ctx.discIn=!!seen.disc?.present;
      drive.speeds=seen.speeds_x??[];drive.rewritable=!!seen.disc?.rewritable;
    },
    burn(onProgress,{speed,erase,confirmed}) {
      let jobId, reason, gate;
      (async()=>{try {
        const approved=await confirmBurn(api.backend,request(speed,erase),confirmed,api.lang());
        await api.backend.job(approved,e=>{
          if(e.type==='started')jobId=e.job;
          if(e.type==='error'){reason=e.message;gate=e.burn_gate||gate;}
          if(e.type==='progress')onProgress({progress:e.fraction,elapsed:e.elapsed_s,remaining:e.eta_s});
          if(e.type==='burn_result'){iso.burnResult=e;onProgress({burnResult:e});}   // goes with the photos (burn path)
        });onProgress({status:'success',progress:1});
      }catch(error){if(reason)error.message=reason;if(gate)error.burnGate=gate;
        onProgress({status:'failed',errorInfo:error,started:!!jobId});}})();
      return {cancel(){if(jobId)api.backend.cancel(jobId);}};
    },
    async photograph(){leaveBurn();(await import('./calibrate.js')).photograph(api,{media:'dvd',geo,burnCheck:iso.burnResult??null,returnTo:()=>open(api,current.work_id,r.burn_id)});},
    async photographSaved(){leaveBurn();const resume=()=>startBurn(api,ctx);
      (await import('./calibrate.js')).photographSaved(api,{geo,returnTo:resume,burnAgain:resume});},
  };
  leave();startBurn(api,ctx);
}
