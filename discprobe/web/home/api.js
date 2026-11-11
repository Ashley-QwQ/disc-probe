// Local workflow client. GETs read saved state; commands require an explicit caller.
const query = new URLSearchParams(location.search);
export const mock = query.has('mock') || query.has('demo') || query.has('newdisc');
const token = query.get('token');
export const escapeHTML = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function errorText(error, lang = 'en') {
  if (error.status === 409) return lang === 'zh' ? '光驱正忙或状态已改变。等任务结束，再重新检测。' : 'The drive is busy or its state changed. Wait for the task, then check again.';
  // fetch() rejects with a TypeError when the server is gone; any other status-less error is a
  // message the page wrote for the person (no disc, wrong family, ...) and is shown as it is.
  if (!error.status && !(error instanceof TypeError)) return error.message;
  if (!error.status) return lang === 'zh' ? '连接不到后端。启动本机 webui 服务，再点重试。' : 'Cannot reach the backend. Start the local webui service, then retry.';
  return (lang === 'zh' ? '任务没有完成。检查光盘后重试：' : 'The task did not finish. Check the disc and retry: ') + error.message;
}
export async function request(path, payload) {
  const response = await fetch(path, {method: payload === undefined ? 'GET' : 'POST',
    headers: {...(token ? {'X-Discprobe-Token': token} : {}), ...(payload === undefined ? {} : {'Content-Type':'application/json'})},
    body: payload === undefined ? undefined : JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error || response.statusText), {status: response.status});
  return data;
}
export const state = () => request('/api/state');
export const run = (payload) => request('/api/run', payload);
export const answer = (job, id, yes) => request(`/api/jobs/${job}/answer`, {id, yes});
export const cancel = (job) => request(`/api/jobs/${job}/cancel`, {});
export function events(onEvent, onError) {
  const source = new EventSource('/api/events' + (token ? '?token=' + encodeURIComponent(token) : ''));
  for (const type of ['progress','ask','answer','result','stopped','done','state','log','tray']) source.addEventListener(type, event => onEvent(JSON.parse(event.data)));
  source.onerror = () => onError?.();
  return () => source.close();
}
export async function job(payload, onEvent = () => {}) {
  const {job: id} = await run(payload);
  onEvent({type:'started', job:id});
  return follow(id, onEvent);
}
// A job already running, maybe started before this page was (re)loaded: everything it has said so far,
// then what it says next, until it ends. Its result, or an error if it failed.
export async function follow(id, onEvent = () => {}) {
  const seen = new Set();
  const deliver = event => {
    if (event.job && event.job !== id) return;
    const key = JSON.stringify(event);
    if (!seen.has(key)) { seen.add(key); onEvent(event); }
  };
  const stop = events(deliver);
  try {
    // Snapshots recover fast completion and messages missed while SSE reconnects.
    for (;;) {
      const snapshot = await request(`/api/jobs/${id}`);
      snapshot.events.forEach(deliver);
      if (snapshot.exit !== null) {
        if (snapshot.exit !== 0) throw Object.assign(new Error('Job failed (' + snapshot.exit + ').'), {status:422});
        return snapshot.result;
      }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
  } finally { stop(); }
}
