// Original preview wiring. Sample data only; no backend, network requests or drives.
import { flipNumber } from './flipnum.js';
import { statusBars } from './statusbars.js';
import { deviceList } from './devices.js';
import { slideConfirm } from './slideconfirm.js';
import { ringButton } from './ringbutton.js';
import { words } from './shared.js';

const copy = {
  title: ['小组件预览', 'Small UI kit'],
  intro: ['纸色与墨色，同一套交互。以下都是演示数据，确认操作只在此页显示结果.',
    'Paper and ink, the same interactions. All values are sample data; confirmation only updates this preview.'],
  numbers: ['变化的数字', 'Changing numbers'], increase: ['增加数字', 'Increase numbers'], decrease: ['减少数字', 'Decrease numbers'],
  history: ['测量记录', 'Measurement history'], historyHelp: ['指向、点按或聚焦细条可查看日期；方向键可切换记录。', 'Hover, tap or focus a bar for its date; use arrow keys to move between events.'],
  addOK: ['加一条正常记录', 'Add OK event'], addNeeds: ['加一条要看的记录', 'Add event needing attention'], addUnknown: ['加一条未知记录', 'Add unknown event'],
  devices: ['已连接的设备', 'Connected devices'], addDevice: ['连上一台手机', 'Connect a phone'], clearDevices: ['清空演示列表', 'Clear sample devices'],
  confirm: ['滑动确认', 'Slide to confirm'], resetConfirm: ['重置确认', 'Reset confirmation'], disableConfirm: ['禁用确认', 'Disable confirmation'],
  progress: ['按钮里的进度', 'Progress in a button'], runProgress: ['运行演示进度', 'Run sample progress'], waitProgress: ['演示未知进度', 'Show indeterminate progress'],
  resetProgress: ['重置进度', 'Reset progress'], progressHelp: ['进度从 0 到 100%，完成后显示勾；文字始终可读。', 'Progress runs from 0 to 100%, then shows a tick. The label stays readable.'],
};
let lang = 'zh';
const cleanups = [];
function localize(root) {
  root.querySelectorAll('[data-copy]').forEach(el => { el.textContent = words(lang, ...copy[el.dataset.copy]); });
}
function mount(theme) {
  const fragment = document.getElementById('theme-template').content.cloneNode(true);
  const sheet = fragment.querySelector('article');
  sheet.dataset.theme = theme;
  sheet.lang = lang === 'en' ? 'en' : 'zh-CN';
  const themeTitle = sheet.querySelector('.theme-title');
  themeTitle.textContent = theme === 'dark' ? words(lang, '墨色', 'Ink') : words(lang, '纸色', 'Paper');
  localize(sheet);
  document.getElementById('themes').append(fragment);
  const $ = selector => sheet.querySelector(selector);
  let percent = 62, minutes = 4, fraction = 1, serial = 0, timer = 0;
  const flips = ['percent', 'minutes', 'fraction'].map(key => flipNumber($(`[data-number="${key}"]`), { lang }));
  function numbers() {
    flips[0].set(`${percent}%`);
    flips[1].set(words(lang, `约 ${minutes} 分钟`, `About ${minutes} minutes`));
    flips[2].set(`${String(fraction).padStart(2, '0')} / 08`);
  }
  numbers();
  const events = Array.from({ length: 12 }, (_, i) => ({ state: i === 4 || i === 9 ? 'needs' : i === 7 ? 'unknown' : 'ok',
    label: words(lang, `演示测量 ${i + 1}`, `Sample measurement ${i + 1}`), when: `2026-11-${String(i + 1).padStart(2, '0')}` }));
  const bars = statusBars($('[data-status]'), events, { lang });
  let devices = [
    { id: 'here', name: words(lang, '这台电脑', 'This computer'), kind: 'computer', since: Date.now() - 180000, sent: 0, thisDevice: true },
    { id: 'phone', name: words(lang, '拍盘的手机', 'Disc photo phone'), kind: 'phone', since: Date.now() - 180000, sent: 2 },
  ];
  const list = deviceList($('[data-devices]'), devices, { lang, onDisconnect: id => { devices = devices.filter(device => device.id !== id); } });
  let disabled = false;
  const slide = slideConfirm($('[data-slide]'), { lang, label: words(lang, '滑动确认演示', 'Confirm sample action'),
    done: () => { $('[data-result]').textContent = words(lang, '演示已确认。没有执行刻录。', 'Sample confirmed. No disc was burned.'); } });
  const disabledSlide = slideConfirm($('[data-slide-disabled]'), { lang, label: words(lang, '等待空白盘', 'Waiting for a blank disc'), disabled: true });
  const ring = ringButton($('[data-ring]'), { lang });
  function stop() { clearInterval(timer); timer = 0; }
  $('[data-ring]').addEventListener('click', () => {
    stop(); ring.progress(0); let p = 0;
    timer = setInterval(() => { p = Math.min(1, p + .05); ring.progress(p); if (p >= 1) { stop(); ring.done(); } }, 100);
  });
  sheet.addEventListener('click', event => {
    const action = event.target.closest('[data-action]')?.dataset.action;
    if (action === 'increase' || action === 'decrease') {
      const step = action === 'increase' ? 1 : -1;
      percent = Math.max(0, Math.min(100, percent + step)); minutes = Math.max(0, minutes + step);
      fraction = Math.max(1, Math.min(8, fraction + step)); numbers();
    } else if (action?.startsWith('status-')) {
      events.push({ state: action.slice(7), label: words(lang, '新的演示测量', 'New sample measurement'), when: new Date() });
      bars.update(events);
    } else if (action === 'device-add') {
      devices.push({ id: `phone-${++serial}`, name: words(lang, `手机 ${serial}`, `Phone ${serial}`), kind: 'phone', since: Date.now(), sent: 0 });
      list.update(devices);
    } else if (action === 'device-clear') { devices = []; list.update(devices); }
    else if (action === 'slide-reset') { slide.reset(); $('[data-result]').textContent = ''; }
    else if (action === 'slide-disable') {
      disabled = !disabled; slide.setDisabled(disabled);
      $('[data-action="slide-disable"]').setAttribute('aria-pressed', String(disabled));
    } else if (action === 'progress-wait') { stop(); ring.progress(null); }
    else if (action === 'progress-reset') { stop(); ring.reset(); }
  });
  cleanups.push(() => { stop(); flips.forEach(flip => flip.destroy()); slide.destroy(); disabledSlide.destroy(); });
}
function rebuild() {
  cleanups.splice(0).forEach(cleanup => cleanup());
  document.getElementById('themes').replaceChildren();
  localize(document.querySelector('header'));
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
  document.title = `${words(lang, '小组件预览', 'Small UI kit')} · disc-probe`;
  document.getElementById('themes').setAttribute('aria-label', words(lang, '组件的两套主题', 'Components in both themes'));
  mount('light'); mount('dark');
  motionLabel();
}
function motionLabel() {
  const on = document.documentElement.dataset.motion !== 'off';
  document.getElementById('motion').textContent = words(lang, `动效：${on ? '开' : '关'}`, `Motion: ${on ? 'on' : 'off'}`);
  document.getElementById('motion').setAttribute('aria-pressed', String(on));
}
document.getElementById('language').addEventListener('click', event => {
  lang = lang === 'zh' ? 'en' : 'zh';
  event.currentTarget.textContent = lang === 'zh' ? 'English' : '中文';
  event.currentTarget.lang = lang === 'zh' ? 'en' : 'zh-CN';
  rebuild();
});
document.getElementById('motion').addEventListener('click', () => {
  const root = document.documentElement;
  root.dataset.motion = root.dataset.motion === 'off' ? 'on' : 'off'; motionLabel();
});
rebuild();
