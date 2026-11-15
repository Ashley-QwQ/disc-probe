// Where the phone (camera and flash) is for the lamp view, and the two controls on it: the disc's rotation and the
// phone's height. The height scale is the placement sheet's ruler, the same heights the colour palettes are made for
// (tools/editor_pose_swatches.py, design/pose-swatches.json): 21 cm is the design height, the lens 206.5 mm above
// the disc's top face; the other marks are the ruler less the disc and the sheet under it (1.3 mm).
import { materialPose } from "./editor-materials.mjs";

export const DESIGN_Z_MM = 206.5;
export const DISC_AND_SHEET_MM = 1.3;
export const HEIGHT_MARKS_CM = [21, 30, 40, 50, 70];
export const HEIGHT_RANGE_CM = [12, 80];

// ruler cm <-> lens height above the disc (mm). From 30 cm up: the mark less disc and sheet; below, the line through
// the design height (21 cm, measured) and the 30 cm mark.
const Z30 = 30 * 10 - DISC_AND_SHEET_MM, SLOPE = (Z30 - DESIGN_Z_MM) / 9;
export const zOfCm = cm => cm >= 30 ? cm * 10 - DISC_AND_SHEET_MM : DESIGN_Z_MM + (cm - 21) * SLOPE;
export const cmOfZ = z => z >= Z30 ? (z + DISC_AND_SHEET_MM) / 10 : 21 + (z - DESIGN_Z_MM) / SLOPE;
// a mark within `snap` cm pulls the lever onto it
export function snapCm(cm, snap = .8) {
  cm = Math.max(HEIGHT_RANGE_CM[0], Math.min(HEIGHT_RANGE_CM[1], cm));
  const near = HEIGHT_MARKS_CM.find(m => Math.abs(m - cm) <= snap);
  return near ?? Math.round(cm * 2) / 2;
}

// state.lampLook = { rotate: degrees counterclockwise, z: lens height in mm or null }: the lamp view's own, never saved with
// the work. z is only a height between the palette's marks while the lever is there; at a mark the lever writes the
// colour panel's scene.rig instead (editor.setRig) and z is null. The rest is the colour panel's pose (materialPose:
// scene.rig's phone and height, or the scene's camera), so the lamp view and the swatches are the same phone.
export function lampPose(state) {
  const base = materialPose(state.scene, state.lookY);
  const view = state.lampLook ?? {}, follows = state.scene?.follows !== false;
  if (Number.isFinite(view.z) && view.z > 0) {
    if (follows) base.flash[2] += view.z - base.camera[2];
    base.camera[2] = view.z;
  }
  const pose = { camera: base.camera, flash: base.flash, rotate: ((view.rotate ?? 0) % 360 + 360) % 360 };
  if (Number.isFinite(base.delta_scale) && base.delta_scale !== 1) pose.delta_scale = base.delta_scale;
  return pose;
}
