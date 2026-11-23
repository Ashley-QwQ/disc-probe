import {navigation, routeFrom} from './navigation.mjs';

// IndexedDB holds portable .discdesign text (including images); History state only holds small route IDs.
const db = () => new Promise((resolve, reject) => {
  const r = indexedDB.open('dp-navigation', 1);
  r.onupgradeneeded = () => r.result.createObjectStore('views');
  r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error);
});
async function stored(id, value) {
  const database = await db();
  try {
    return await new Promise((resolve, reject) => {
      const tx = database.transaction('views', value === undefined ? 'readonly' : 'readwrite');
      const r = value === undefined ? tx.objectStore('views').get(id) : tx.objectStore('views').put(value, id);
      tx.oncomplete = () => resolve(r.result); tx.onerror = () => reject(tx.error);
    });
  } finally { database.close(); }
}
export async function install(api, {setHome}) {
  const root = document.documentElement, $ = api.$;
  const requested = routeFrom(location.hash);
  const initial = root.dataset.mode === 'cal' ? {id: crypto.randomUUID(), view: 'cal'}
    : history.state?.dpNav || {id: crypto.randomUUID(), view: requested || root.dataset.mode || root.dataset.home || 'lobby'};
  const read = () => root.dataset.mode || root.dataset.home || 'lobby';
  let persist = Promise.resolve(), controller, internalAction = false;
  async function capture(entry) {
    const view = entry.view, place = api.current();
    const snap = {view, col: place.col, batch: place.item?.id};
    if (view === 'newplan') snap.form = (await import('./newplan.js')).navigationState();
    if (view === 'cal') snap.photo = (await import('./calibrate.js')).navigationState?.() || null;
    if (['design', 'preview', 'burn'].includes(view)) {
      try {
        const actions = (await import('./design.js')).editorActions();
        snap.plan = actions.state();
        // The serializer reads the active plan. Finish before any restore changes it.
        snap.name = snap.plan.name;
        snap.work = snap.plan.work;
        snap.dirty = snap.plan.dirty;
        snap.text = await actions.projectText();
      } catch {}
      if (view !== 'design') snap.preview = (await import('./preview.js')).navigationState();
    }
    const portable = {...snap}; delete portable.plan;
    if (portable.preview) {
      const state = snap.preview.state;
      // A running task owns DOM/AbortController objects; keep it live in memory, never clone/replay it.
      portable.preview = snap.preview.context?.imageWork?.() && !state?.checkIso ? undefined
        : {state: state?.phase === 'making' ? {phase: 'idle'} : state};
    }
    if (portable.form) portable.form = {...portable.form, file: portable.form.file};
    persist = persist.catch(() => {}).then(() => stored(entry.id, portable));
    persist.catch(e => console.error('navigation snapshot', e));
    return snap;
  }
  async function dismiss() {
    const mode = root.dataset.mode;
    if (mode === 'newplan') (await import('./newplan.js')).suspendNavigation();
    else if (mode === 'preview') (await import('./preview.js')).leave(false);
    else if (mode === 'cal') (await import('./calibrate.js')).suspendNavigation();
    else if (mode === 'burn') (await import('./burn.js')).leave();
    else if (mode) {
      // Existing owners perform their cleanup, save/return handling and animation.
      internalAction = true;
      try { $('back').click(); } finally { internalAction = false; }
      for (let n = 0; root.dataset.mode === mode && n < 120; n++) await new Promise(r => setTimeout(r, 25));
      if (root.dataset.mode === mode) throw Error('Page is still handling its Back action');
    }
  }
  async function restore(entry, live) {
    await persist.catch(() => {});
    const saved = live || await stored(entry.id).catch(() => null) || {};
    // The app's Back owner may already have restored its form/callback context.
    if (read() === entry.view) return;
    await dismiss();
    if (saved.col && ['dvd', 'cd', 'bd'].includes(saved.col)) {
      const list = api.catalogue(saved.col), item = list.find(i => i.id === saved.batch);
      api.goTo(saved.col, Math.max(0, list.indexOf(item)));
    }
    const view = entry.view;
    if (view === 'lobby' || view === 'library') { setHome(view); return; }
    if (view === 'newplan') { await (await import('./newplan.js')).start(api, {resume: saved.form}); return; }
    if (view === 'cal') {
      const calibrate = await import('./calibrate.js');
      if (saved.photo?.geo) {
        // back to that batch's photo page, with Back leading to the batch in the library as before
        const list = saved.col ? api.catalogue(saved.col) : [], item = list.find(i => i.id === saved.photo.batch) || null;
        calibrate.photograph(api, {item, media: saved.photo.media, geo: saved.photo.geo, returnTo: () => {
          if (item) api.goTo(...api.locate(item));
          setHome('library');
        }});
        return;
      }
      calibrate.start(api, {keep: true}); return;
    }
    if (view === 'presets') { (await import('./presetio.js')).open(); return; }
    if (view === 'pastworks') { await (await import('./pastworks.js')).start(api); return; }
    if (view === 'faxnews') { await (await import('./faxnews.js')).start(api); return; }
    if (['design', 'preview', 'burn'].includes(view)) {
      const design = await import('./design.js');
      if (saved.plan) design.start(api, {plan: saved.plan, fly: false});
      else {
        design.start(api, {newPlan: true, fly: false, name: saved.name, noDisc: !saved.batch});
        if (saved.text) await design.editorActions().openProject(new File([saved.text], `${saved.name || 'recovered'}.discdesign`), null, saved.work, saved.dirty);
      }
      if (view !== 'design' && !$('next').disabled) {
        internalAction = true;
        try { $('next').click(); } finally { internalAction = false; }
        for (let n = 0; root.dataset.mode !== 'preview' && n < 120; n++) await new Promise(r => setTimeout(r, 25));
        await (await import('./preview.js')).resumeNavigation(api, saved.preview);
        // Only opens the confirmation page. No press-and-hold or job is replayed.
        if (view === 'burn' && !$('next').disabled) {
          internalAction = true;
          try { $('next').click(); } finally { internalAction = false; }
        }
      }
    }
  }
  // Keep the requested view before navigation replaces an unrecognised/empty hash.
  history.replaceState({...history.state, dpNav: initial}, '');
  controller = navigation({read, capture, restore, status: value => {root.dataset.navigation = value;}, observe: fn => {
    new MutationObserver(fn).observe(root, {attributes: true, attributeFilter: ['data-mode', 'data-home']});
  }});
  let timer;
  const saveSoon = () => { clearTimeout(timer); timer = setTimeout(() => controller.save(), 120); };
  for (const type of ['input', 'change', 'pointerup', 'keyup']) document.addEventListener(type, saveSoon, true);
  document.addEventListener('dp-image-work-saved', () => controller.save());
  document.addEventListener('click', event => {
    if (internalAction) return;
    if (controller.busy() && event.target.closest?.('#back, #next')) { event.preventDefault(); event.stopImmediatePropagation(); return; }
    if (event.target.closest?.('#back')) controller.requestBack();
    controller.save(); saveSoon();
  }, true);
  addEventListener('pagehide', () => controller.save());
  // A running calibration attached by startup takes precedence over a stale URL.
  if (root.dataset.mode === 'cal') controller.save();
  else await controller.start(initial);
  controller.save();
  root.dataset.navigation = 'ready';
  return controller;
}
