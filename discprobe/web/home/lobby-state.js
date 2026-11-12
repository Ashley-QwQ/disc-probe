// Read-only wording for the state already held by the home page. Never probes a drive.
export function lobbyStatus(state, lang = "zh") {
  const en = lang === "en";
  if (!state) return en ? "Your first disc starts at the drive" : "第一张盘从光驱开始";
  if (state.error) return en ? "Drive status is unavailable. Check the local service." : "暂时读不到光驱状态，请检查本机服务";
  const drives = state.drives ?? [];
  if (!drives.length) return en ? "No drive found. Connect one to start." : "还没找到光驱，接好后就能开始";
  const drive = drives.find(d => d.id === state.selectedDrive) ?? drives[0];
  const busy = (state.jobs ?? []).some(j => j.drive === drive.id && j.exit === null);
  if (busy) return en ? "The drive is busy. Let it finish." : "光驱正在工作，等它完成";
  const disc = drive.disc;
  if (!disc) return en ? "Your first disc starts at the drive" : "第一张盘从光驱开始";
  if (disc.tray === "open") return en ? "The tray is open. Put a disc in." : "托盘开着，放一张盘进去";
  if (disc.tray === "loading") return en ? "The drive is reading the disc. One moment." : "光驱正在认盘，稍等一下";
  if (disc.present === false) return en ? "The drive is empty. Put a blank disc in." : "光驱里还没有盘，放一张空白盘进去";
  if (disc.present !== true) return en ? "The disc has not been identified yet." : "还没认出光驱里的盘";
  // Keep the actual reported kind, never infer writable/blank from its name.
  const kind = String(disc.kind || "").trim().split(/\s+/)[0];
  const name = kind || (en ? "disc" : "光盘");
  if (disc.blank === true) return en ? `A blank ${name} is in the drive. Start here.` : `光驱里是一张空白 ${name}，可以开始新作品`;
  if (disc.blank === false) return en ? `The ${name} in the drive has been written. Use a blank disc for a new work.` : `光驱里的 ${name} 已写过，新作品请换空白盘`;
  return en ? `A ${name} is in the drive. Its blank status is unknown.` : `光驱里是 ${name}，还不知道是不是空白盘`;
}
