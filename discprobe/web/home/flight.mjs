// The lobby camera and the top-down page are one move. Keep this shared by the drive and fax.
export const LOBBY_PUSH = 2.6, TOP_START = 1.5;
export const coverPoint = ([x, y], [w, h] = [2560, 1440]) => {
  const vw = innerWidth, vh = innerHeight, sw = Math.max(vw, vh * w / h), sh = sw * h / w;
  return [(vw - sw) / 2 + sw * x / w, (vh - sh) / 2 + sh * y / h];
};
const mid = () => [innerWidth / 2, innerHeight / 2];
export const topStart = point => {
  const [tx, ty] = point(), [cx, cy] = mid();
  return `translate(${cx - tx}px, ${cy - ty}px) scale(${TOP_START})`;
};
export function pushLobby(from, reverse = false) {
  const lobby = document.getElementById('lobby'), art = document.getElementById('lobby-art');
  const greet = lobby.querySelector('.lobby-greet');
  lobby.classList.add('leaving');
  const r = from.getBoundingClientRect(), [sx, sy] = [r.left + r.width / 2, r.top + r.height / 2], [cx, cy] = mid();
  art.style.transformOrigin = `${sx}px ${sy}px`;
  const frames = [{transform: 'none'}, {transform: `translate(${cx - sx}px, ${cy - sy}px) scale(${LOBBY_PUSH})`}];
  const fade = [{opacity: 1}, {opacity: 0}];
  const a = art.animate(reverse ? frames.reverse() : frames, {duration: 560,
    easing: reverse ? 'cubic-bezier(.2, .8, .2, 1)' : 'cubic-bezier(.5, 0, .6, 1)', fill: 'forwards'});
  const g = greet?.animate(reverse ? fade.reverse() : fade, {duration: reverse ? 400 : 200, fill: 'forwards'});
  return {finished: a.finished, done() {a.cancel(); g?.cancel(); art.style.transformOrigin = ''; lobby.classList.remove('leaving');}};
}
export function pageFlight(page, point, reverse = false) {
  const [tx, ty] = point();
  page.style.transformOrigin = `${tx}px ${ty}px`;
  return page.animate(reverse
    ? [{transform: 'none', opacity: 1}, {opacity: 1, offset: .55}, {transform: topStart(point), opacity: 0}]
    : [{transform: topStart(point), opacity: 0}, {opacity: 1, offset: .45}, {transform: 'none', opacity: 1}],
  reverse ? {duration: 520, easing: 'cubic-bezier(.5, 0, .9, .5)', fill: 'forwards'}
    : {duration: 760, easing: 'cubic-bezier(.2, .8, .2, 1)'});
}
