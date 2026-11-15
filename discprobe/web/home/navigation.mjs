// URLs identify views; snapshots belong to this tab. Reopening a route never runs a job.
export const views = new Set(['lobby', 'library', 'newplan', 'design', 'preview', 'burn', 'cal', 'pastworks', 'presets', 'faxnews']);
export function routeFrom(hash) {
  const view = hash.replace(/^#\/?/, '').split('?')[0];
  return views.has(view) ? view : null;
}
export function navigation({read, capture, restore, win = window, observe, status = () => {}}) {
  const memory = new Map();
  let active = win.history.state?.dpNav || {id: crypto.randomUUID(), view: read()}, moving = false;
  let queue = Promise.resolve(), backIntent = false, nativePending = false;
  const url = view => { const u = new URL(win.location.href); u.hash = '/' + view; return u; };
  const save = () => { if (!moving) memory.set(active.id, capture(active)); };
  win.history.replaceState({...win.history.state, dpNav: active}, '', url(active.view));
  observe(() => {
    if (moving) return;
    const view = read();
    if (view === active.view) return;
    const isBack = backIntent; backIntent = false;
    save();
    const next = {id: crypto.randomUUID(), view};
    // The app's Back button follows the same prior entry when it has the same destination.
    if (isBack && active.parent?.view === view) {
      nativePending = true; status('restoring'); win.history.back(); return;
    }
    next.parent = {id: active.id, view: active.view};
    active = next;
    win.history.pushState({dpNav: active}, '', url(view));
    save();
  });
  const travel = (target, saveDeparture = true) => {
    if (saveDeparture) save();
    const departing = memory.get(active.id);
    moving = true;
    status('restoring');
    queue = queue.catch(() => {}).then(async () => {
      try {
        await departing;
        await restore(target, await memory.get(target.id)); active = target;
        if (active.view !== read()) { active = {...active, view: read()}; win.history.replaceState({dpNav: active}, '', url(active.view)); }
      }
      finally { moving = false; save(); status('ready'); }
    });
    return queue;
  };
  win.addEventListener('popstate', e => {
    nativePending = false;
    const target = e.state?.dpNav || {id: crypto.randomUUID(), view: routeFrom(win.location.hash) || 'lobby'};
    travel(target).catch(error => {
      win.history.replaceState({dpNav: active}, '', url(active.view));
      console.error('navigation restore', error);
    });
  });
  return {save, busy: () => moving || nativePending, requestBack: () => {backIntent = true;}, start: target => travel(target || active, false), current: () => active};
}
