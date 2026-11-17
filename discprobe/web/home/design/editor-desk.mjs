// Screen furniture only: never used by preview(), the lamp renderer, or export.
// Review selected B (wood grain). A remains available by changing this constant.
export const DESK_VARIANT = 'B';
const TILE_MM = 80;

export function updateDesk(dom, view, focus) {
  const {desk, surface, shadow} = dom;
  const dark = document.documentElement.dataset.theme === 'dark';
  desk.style.backgroundImage = `url("${new URL(`./editor-desk-${DESK_VARIANT.toLowerCase()}-${dark ? 'dark' : 'paper'}.png`, import.meta.url)}")`;
  desk.style.backgroundSize = `${TILE_MM * view.s}px ${TILE_MM * view.s}px`;
  desk.style.backgroundPosition = `${view.cx}px ${view.cy}px`;
  // Mask the wrapper, not the transformed burn-view bitmap: the opening stays put while panning.
  surface.style.maskSize = `${focus.w}px ${focus.h}px, 100% 100%`;
  surface.style.maskPosition = `${focus.x}px ${focus.y}px, 0 0`;
  const radius = 60 * view.s;
  Object.assign(shadow.style, {
    left: `${view.cx - radius}px`, top: `${view.cy - radius}px`,
    width: `${radius * 2}px`, height: `${radius * 2}px`,
    // Same upper-right lamp as the other desks: 3 mm elevation, 5 mm penumbra.
    boxShadow: `${-0.5609 * 3 * view.s}px ${0.3085 * 3 * view.s}px ${5 * view.s}px ${dark ? 'rgb(10 17 20 / .6)' : 'rgb(29 27 24 / .15)'}`,
  });
}
