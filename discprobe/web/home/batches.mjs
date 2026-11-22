export const calibrated = (item) => ["good", "usable"].includes(item?.s);

export const geometryId = (item) => item?.geo?.replace(/\\/g, "/").replace(/\/(?:summary\.json)?$/, "").split("/").at(-1);

export function libraryBatchName(item, media, lang) {
  const name = item.name?.trim();
  const raw = geometryId(item);
  if (name && name !== raw) return name;
  if (item.mid?.trim()) return item.mid.trim();
  const medium = item.media_kind || media.toUpperCase();
  const date = /^\d{4}-(\d{2}-\d{2})$/.exec(item.last)?.[1];
  const drive = item.drive === "unknown drive" ? null : item.drive;
  return [medium, drive, date || (lang === "zh" ? "日期未记录" : "Date not recorded")].filter(Boolean).join(" · ");
}

export const needsCdPhoto = (item, media) => media === "cd" && calibrated(item) && !!item.geo && item.along_track?.known !== true;

export function sameMaker(a, b) {
  return !!a && !!b && String(a).trim().toLowerCase() === String(b).trim().toLowerCase();
}

export function calibratedBatch(entries, item, disc) {
  const exact = entries.find(x => calibrated(x) && item?.id && x.id === item.id);
  if (exact) return exact;
  if (item?.manualBatch) return undefined;
  const mid = item?.mid || item?.readMid || disc?.mid;
  return entries.find(x => calibrated(x) && sameMaker(x.mid, mid));
}

export function driveCalibrationCounts(drive, catalogue) {
  const batches = Object.values(catalogue).flat().filter(batch =>
    sameMaker(batch.drive_id, drive.id) || [drive.name, drive.disc?.drive_name].some(model => sameMaker(batch.drive, model)));
  return { passed: batches.filter(calibrated).length, incomplete: batches.filter(batch => batch.s === "incomplete").length };
}

export function discDisplayKind(disc, lang) {
  const kind = disc?.kind || (lang === "en" ? "disc" : "光盘");
  if (disc?.blank === false && /^DVD-ROM\b/i.test(kind)) {
    return lang === "en" ? "Recorded disc (drive reports DVD-ROM)" : "已刻好的光盘（光驱报告为 DVD-ROM）";
  }
  return kind;
}

export function localDay(date = new Date()) {
  return [date.getFullYear(), date.getMonth() + 1, date.getDate()];
}
