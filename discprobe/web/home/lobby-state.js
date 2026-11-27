import { discDisplayKind } from "./batches.mjs";

export const lobbyDrive = (state) => state?.drives?.find(d => d.id === state.selectedDrive) ?? state?.drives?.[0];
export function lastDiscCheck(state, lang, now = Date.now()) {
  const at = lobbyDrive(state)?.disc?.read_at;
  if (!Number.isFinite(at)) return "";
  const minutes = Math.max(0, Math.floor((now - at * 1000) / 60000));
  if (!minutes) return lang === "en" ? "Last checked just now" : "上次检测：刚刚";
  return lang === "en" ? `Last checked ${minutes} min ago` : `上次检测：${minutes} 分钟前`;
}

export function lobbyStatus(state, lang = "zh") {
  const en = lang === "en";
  if (!state) return en ? "Your first disc starts at the drive" : "第一张盘从光驱开始";
  if (state.error) return en ? "Drive status is unavailable. Check the local service." : "暂时读不到光驱状态，请检查本机服务";
  const drives = state.drives ?? [];
  if (!drives.length) return en ? "No drive found. Connect one to start." : "还没找到光驱，接好后就能开始";
  const drive = lobbyDrive(state);
  const busy = (state.jobs ?? []).some(j => j.drive === drive.id && j.exit === null);
  if (busy) return en ? "The drive is busy. Let it finish." : "光驱正在工作，等它完成";
  if (state.checking) return en ? "Checking the disc…" : "正在检测光盘…";
  if (state.checkFailed) return en ? "Could not check the disc. Try again." : "没能检测光盘，请重试";
  const disc = drive.disc;
  if (!disc) return en ? "Your first disc starts at the drive" : "第一张盘从光驱开始";
  if (disc.tray === "open") return en ? "The tray was open at the last check." : "上次检测时托盘开着";
  if (disc.tray === "loading") return en ? "The drive is reading the disc. One moment." : "光驱正在认盘，稍等一下";
  if (disc.present === false) return en ? "The drive was empty at the last check." : "上次检测时光驱里没有盘";
  if (disc.present !== true) return en ? "The disc has not been identified yet." : "还没认出光驱里的盘";
  const name = discDisplayKind({ ...disc, kind: disc.kind?.trim().split(/\s+/)[0] }, lang);
  if (disc.blank === true) return en ? `Last check found a blank ${name}.` : `上次检测到空白 ${name}`;
  if (disc.blank === false) {
    if (/^DVD-ROM\b/i.test(disc.kind)) return name;
    return en ? `The ${name} found at the last check has been written.` : `上次检测到的 ${name} 已写过`;
  }
  return en ? `Last check found a ${name}. Its blank status is unknown.` : `上次检测到 ${name}，还不知道是不是空白盘`;
}
