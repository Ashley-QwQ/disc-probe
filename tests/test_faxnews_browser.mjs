// The news fax page in a real browser (file URL, mocked fetch for the paper; no server, no drive).
// First visit note -> dial -> paper; order a skin -> parcel; no line, bad paper and a missing paper end in
// receipts with ways on; reduced motion skips the call; with motion, Enter skips it; back returns to the lobby.
import assert from 'node:assert/strict';
import {existsSync, readFileSync, writeFileSync, mkdtempSync, mkdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

const browser = process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
if (!existsSync(browser)) throw Error('faxnews browser test requires Chromium; set KIT_TEST_BROWSER');
const dir = mkdtempSync(join(tmpdir(), 'discprobe-faxnews-'));
const home = new URL('../discprobe/web/home/', import.meta.url);
const index = readFileSync(new URL('index.html', home), 'utf8');
const style = index.match(/<style>([\s\S]*?)<\/style>/)[1];
const sample = readFileSync(new URL('faxnews/news.json', home), 'utf8');
const communitySample = readFileSync(new URL('faxnews/community.json', home), 'utf8');
const screenshotDir = resolve(process.env.FAX_SHOTS_DIR || join(tmpdir(), 'faxnews-shots')); mkdirSync(screenshotDir, {recursive: true});
const fixture = join(dir, 'fax.html');
const html = `<!doctype html><html data-theme="paper"><meta charset="utf-8"><base href="${home.href}">
<style>${style}</style>
<body><header class="top"><button id="back" class="back" hidden>back</button><span id="wm-ver">v0.1.2.1</span></header>
<section id="lobby" class="lobby"><div id="lobby-art"><button id="fax-in-lobby" style="position:absolute;left:300px;top:500px;width:120px;height:90px">fax</button></div></section>
<pre id="result" hidden>PENDING</pre>
<script type="module">
const check=(x,m)=>{if(!x)throw Error(m)};
const $=id=>document.getElementById(id), q=s=>document.querySelector(s), qa=s=>[...document.querySelectorAll(s)];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const waitFor=async(p,m,n=600)=>{for(let i=0;i<n;i++){if(p())return;await pause(20)}throw Error('timed out: '+m)};
localStorage.clear();
const params=new URL(location.href).searchParams;
document.documentElement.dataset.theme=params.get('theme')||'paper';
let reduce=true, lobbyVisits=0;
const api={$,lang:()=>params.get('lang')||'zh',get reduce(){return reduce},toLobby(){lobbyVisits++}};
// every request the page makes goes through here; the paper's answer is chosen per step
const calls=[]; let answer='ok'; const SAMPLE=${JSON.stringify(sample)}, COMMUNITY=${communitySample};
const nativeFetch=window.fetch.bind(window);
window.fetch=async(url,opts={})=>{
  const u=new URL(String(url),document.baseURI);
  if(u.pathname.endsWith('/api/news/asset')) { calls.push({url:u.href,opts}); return nativeFetch(new URL('faxnews/'+u.searchParams.get('path'),document.baseURI),opts); }
  if(u.pathname.endsWith('/faxnews/fax.json'))
    {if(u.pathname.includes('/skins/'))calls.push({url:u.href,opts});return nativeFetch(url,opts);}
  calls.push({url:u.href,opts});
  if(u.pathname.endsWith('/api/community')) {
    if(opts.method==='POST')return new Response(JSON.stringify({written:[{index:0}],duplicates:[]}));
    return new Response(JSON.stringify({feed:COMMUNITY,date:COMMUNITY.date,count:COMMUNITY.count,from:answer==='cache'?'cache':answer==='bundled'?'bundled':'network'}));
  }
  if(answer==='offline')throw new TypeError('Failed to fetch');
  if(answer==='404')return new Response('no',{status:404});
  if(answer==='bad')return new Response(JSON.stringify({paper:{format:'rss',version:1}}),{status:200});
  if(answer==='notjson')return new Response('<html>',{status:200});
  return new Response(JSON.stringify({paper:JSON.parse(SAMPLE),from:answer==='cache'?'cache':answer==='bundled'?'bundled':'network',source:'https://news.example/news/news.json'}),{status:200});
};
window.AudioContext=class{constructor(){throw Error('no audio in the test')}};
try{
  const fax=await import('./faxnews.js');
  const from=$('fax-in-lobby');
  // 1. first visit: the note says what it is, does and never does; the source address is checked
  await fax.start(api,{from});
  check(document.documentElement.dataset.mode==='faxnews','mode');
  check(!$('back').hidden,'back shown');
  const notice=q('.fx-notice');
  check(!notice.hidden,'first visit shows the note');
  check(qa('.fx-notice h3').length===3,'three parts');
  check(/永远不做/.test(notice.textContent)&&/不上传/.test(notice.textContent),'says it never uploads');
  check(calls.length===0,'nothing fetched before the note is answered');
  const input=q('.fx-src input'); check(input.value==='/api/news','default source');
  input.value='javascript:alert(1)'; q('.fx-notice .fx-btn.primary').click();
  check(!q('.fx-src-err').hidden&&!notice.hidden,'a bad address is refused');
  input.value='/api/news'; q('.fx-notice .fx-btn.primary').click();
  check(notice.hidden,'note closes');
  await waitFor(()=>!q('.fx-paper').hidden&&q('.fx-mast'),'paper');
  check(localStorage.getItem('dp-fax-seen')==='1','seen remembered');
  // the one request: a plain GET with nothing of ours in it
  check(calls.length===2,'paper and community data each fetched once: '+calls.length);
  const c0=calls.find(c=>new URL(c.url).pathname.endsWith('/api/news')); check(!new URL(c0.url).search,'no query');
  const cc=calls.find(c=>new URL(c.url).pathname.endsWith('/api/community'));
  check(new URL(cc.url).searchParams.get('refresh')==='1'&&cc.opts.method==='GET'&&cc.opts.credentials==='omit','community refresh is a plain local GET');
  check(c0.opts.method==='GET'&&c0.opts.credentials==='omit'&&c0.opts.referrerPolicy==='no-referrer'&&!c0.opts.body&&!c0.opts.headers,'GET only, no cookies, no referrer, no body');
  // 2. the paper: the newer release leads; ads, the disc of the day, a background, a joke, what comes
  const P=q('.fx-paper');
  check(/1\\.0\\.0\\.0-alpha/.test(q('.fx-lead').textContent),'release leads');
  check(q('.fx-stamp')?.textContent==='样张','sample stamp');
  check(qa('.fx-ad').length===2,'two ads');
  check(qa('article.fx-story').length===3,'three stories');
  const community=q('.fx-community'); check(community&&community.textContent.includes(COMMUNITY.date)&&community.textContent.includes(String(COMMUNITY.count)),'community date and count');
  check(community.textContent.includes('联网')&&community.textContent.includes('不是 DP 测的')&&community.textContent.includes('没有实测范围'),'community provenance and range');
  const select=community.querySelector('select'); select.value='dvd';select.dispatchEvent(new Event('change'));
  check(community.querySelector('details a').href.startsWith('https://github.com/'),'GitHub source links');
  check(![...community.querySelectorAll('summary')].some(e=>e.textContent.includes('有人用这组失败了')),'failed rows hidden by default');
  const failed=community.querySelector('input');failed.checked=true;failed.dispatchEvent(new Event('change'));
  check([...community.querySelectorAll('summary')].some(e=>e.textContent.includes('有人用这组失败了')),'failed rows explicit');
  const importButton=community.querySelector('details button');importButton.click();
  await waitFor(()=>community.textContent.includes('已进预设库'),'explicit local import');
  check(calls.filter(c=>c.opts.method==='POST').length===1,'only explicit import writes locally');
  const detail=community.querySelector('details');detail.open=true;
  check(detail.scrollWidth<=detail.clientWidth+1,'expanded numeric record stays inside the column');detail.open=false;
  check(q('.fx-art img')?.getAttribute('src'),'artwork');
  check(q('.fx-art img').getAttribute('src').startsWith('/api/news/asset?path='),'artwork stays on local API');
  check(q('.fx-bg canvas'),'background preset');
  check(q('.fx-joke p')?.textContent.length>4,'joke');
  check(qa('.fx-coming li').length===3,'coming');
  check(/只下载/.test(q('.fx-foot').textContent),'footer says download only');
  check(q('.fx-lcd').textContent.startsWith('已收到'),'display: received');
  const pr=P.getBoundingClientRect(); check(pr.right<=innerWidth&&pr.left>=0,'paper inside the window');
  const customSource='https://news.example/custom/news.json';
  await fax.download(customSource);
  const forwarded=new URL(calls.at(-1).url);
  check(forwarded.pathname.endsWith('/api/news')&&forwarded.searchParams.get('source')===customSource,'custom source goes to the core');
  check(!fax.validSource('http://127.0.0.1/news.json'),'browser cannot enable the test exception');
  // 3. order a skin: ordered at once, a parcel after the delivery, the lobby told
  let parcelEvents=0; addEventListener('dp-fax-parcel',()=>parcelEvents++);
  const ad=q('.fx-ad'); ad.querySelector('.fx-btn.primary').click();
  check(ad.dataset.state==='shipping'&&ad.querySelector('.fx-ordered'),'ordered at once');
  await waitFor(()=>q('.fx-ad').dataset.state==='delivered','delivered',800);
  check(parcelEvents===1,'lobby told once');
  const parcels=JSON.parse(localStorage.getItem('dp-fax-parcels')); check(parcels.length===1&&parcels[0].id==='kraft-office','parcel kept');
  const skinCall=calls.find(c=>new URL(c.url).searchParams.get('path')==='skins/kraft-office.json'); check(skinCall&&skinCall.opts.credentials==='omit','the parcel is one more plain GET');
  // 4. no line: a receipt with redial, the last paper and the source
  answer='offline'; q('.fx-foot .fx-btn').click();
  await waitFor(()=>q('.fx-slip'),'offline receipt');
  check(/没接通/.test(q('.fx-slip').textContent),'no line said');
  check(q('.fx-lcd').textContent==='线路不通','display: no line');
  const lastBtn=qa('.fx-slip .fx-btn').find(b=>/上次的报纸/.test(b.textContent)); check(lastBtn,'last paper offered');
  lastBtn.click(); check(q('.fx-stamp')?.textContent==='旧报','old paper stamped');
  // 5. not a paper, and not JSON: what was wrong is printed
  answer='bad'; q('.fx-foot .fx-btn').click();
  await waitFor(()=>q('.fx-slip-detail'),'bad receipt');
  check(/format/.test(q('.fx-slip-detail').textContent),'names the field');
  answer='notjson'; q('.fx-slip .fx-btn.primary').click();
  await waitFor(()=>/not JSON/.test(q('.fx-slip-detail')?.textContent||''),'not JSON');
  // 6. a missing paper
  answer='404'; q('.fx-slip .fx-btn.primary').click();
  await waitFor(()=>/号码不存在/.test(q('.fx-slip')?.textContent||''),'404 receipt');
  check(/404/.test(q('.fx-lcd').textContent),'display: 404');
  // 7. change the source from the receipt; then with motion, Enter skips the call
  answer='ok'; qa('.fx-slip .fx-btn').find(b=>/数据源/.test(b.textContent)).click();
  check(!q('.fx-notice').hidden,'note again');
  q('.fx-notice .fx-btn.primary').click();
  await waitFor(()=>q('.fx-mast'),'paper after the note');
  reduce=false;
  q('.fx-foot .fx-btn').click();
  await waitFor(()=>q('.fx-handset').getAnimations().length>0,'the handset lifts with motion');
  await waitFor(()=>/拨号/.test(q('.fx-lcd').textContent),'dialling');
  dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
  await waitFor(()=>q('.fx-mast'),'skipped to the paper');
  check(q('.fx-paper').getAnimations().length===0,'no flight left after a skip');
  // 8. back to the lobby
  reduce=true; $('back').click();
  await waitFor(()=>!document.documentElement.dataset.mode,'left');
  check(lobbyVisits===1&&q('.fx').hidden&&$('back').hidden,'back in the lobby');
  // the parcel slip over the lobby
  await fax.openParcel(api,from); check(/牛皮纸/.test(q('.fx-parcel').textContent),'parcel slip');
  const sr=q('.fx-parcel').getBoundingClientRect(); check(sr.width<=340&&sr.right<=innerWidth,'parcel slip has its own width');
  qa('.fx-parcel .fx-btn')[0].click(); check(!JSON.parse(localStorage.getItem('dp-fax-parcels')).length,'parcel put away');
  // Core fallback is still a readable paper, with a small provenance note.
  await fax.start(api,{from}); await waitFor(()=>q('.fx-mast'),'paper before fallback');
  answer='cache'; q('.fx-foot .fx-btn').click();
  await waitFor(()=>q('.fx-note')?.textContent.includes('上次的报纸'),'cached paper note');
  dispatchEvent(new Event('dp-lang'));
  check(q('.fx-note')?.textContent.includes('上次的报纸'),'note survives repaint');
  answer='bundled'; q('.fx-foot .fx-btn').click();
  await waitFor(()=>q('.fx-note')?.textContent.includes('自带的样张'),'bundled paper note');
  answer='ok';
  // the screenshot: the paper again
  await fax.start(api,{from}); await waitFor(()=>q('.fx-mast'),'final paper');
  if(params.get('slip')) { answer='offline'; q('.fx-foot .fx-btn').click(); await waitFor(()=>q('.fx-slip'),'final slip'); }
  $('result').textContent='PASS: faxnews browser '+innerWidth+'x'+innerHeight+' '+document.documentElement.dataset.theme;
}catch(e){$('result').textContent='FAIL: '+e.stack}
</script></body></html>`;
writeFileSync(fixture, html);
if (process.env.FAX_FIXTURE_OUT) { writeFileSync(process.env.FAX_FIXTURE_OUT, html); rmSync(dir, {recursive: true, force: true}); process.exit(0); }
try {
  const cases = [{width: 1440, height: 900, theme: 'paper'}, {width: 1440, height: 900, theme: 'dark', slip: 1}, {width: 390, height: 844, theme: 'paper'}];
  for (const [i, c] of cases.entries()) {
    const url = new URL(pathToFileURL(fixture));
    for (const [k, v] of Object.entries(c)) url.searchParams.set(k, v);
    const wrapper = join(dir, 'view-' + i + '.html');
    writeFileSync(wrapper, '<!doctype html><html><meta charset="utf-8"><style>html,body{margin:0;overflow:hidden}iframe{display:block;border:0}</style><body><iframe style="width:' + c.width + 'px;height:' + c.height + 'px" src="' + url.href + '"></iframe><pre id="result" hidden>PENDING</pre><script>setInterval(()=>{const r=document.querySelector("iframe").contentDocument?.getElementById("result");if(r)document.getElementById("result").textContent=r.textContent},20)<\/script></body></html>');
    const screenshot = join(screenshotDir, `faxnews-${c.theme}-${c.width}${c.slip ? '-slip' : ''}.png`);
    const result = spawnSync(browser, ['--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check',
      '--allow-file-access-from-files', '--user-data-dir=' + join(dir, 'profile-' + i), '--window-size=' + Math.max(500, c.width) + ',' + c.height,
      '--force-device-scale-factor=1', '--hide-scrollbars', '--virtual-time-budget=60000', '--dump-dom', '--screenshot=' + screenshot, pathToFileURL(wrapper).href],
    {encoding: 'utf8', timeout: 90000, maxBuffer: 8 * 1024 * 1024, windowsHide: true});
    assert.ifError(result.error);
    const report = result.stdout.match(/<pre id="result"[^>]*>([\s\S]*?)<\/pre>/)?.[1];
    if (!/^PASS/.test(report || '')) console.error(report || result.stderr.slice(-2000));
    assert.match(report || result.stderr, /^PASS: faxnews browser/);
    console.log(report + ' (mocked paper, file URL)');
  }
} finally {
  const target = resolve(dir), tempRoot = resolve(tmpdir());
  assert.equal(resolve(target, '..'), tempRoot); assert.ok(target.startsWith(join(tempRoot, 'discprobe-faxnews-')));
  try { rmSync(target, {recursive: true, force: true, maxRetries: 5, retryDelay: 200}); } catch (e) { console.warn('could not remove', target, e.code); }
}
