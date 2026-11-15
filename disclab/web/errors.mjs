export function commandError(result, log = '', lang = 'zh') {
  const zh = lang !== 'en';
  const messages = (result?.errors || []).map(e => e.message || '').join('\n');
  const text = `${log}\n${messages}`.replace(/\x1b\[[0-9;]*m/g, '');
  if (/No space left|not enough space|disk full|磁盘空间不足|WinError 112|Errno 28/i.test(text)) {
    return zh ? '磁盘空间不足：清理实验目录中不再需要的镜像，或换一个有空间的 --lab 目录，再重试。'
      : 'Disk space is insufficient: remove unneeded lab images or use a --lab directory with free space, then retry.';
  }
  const lines = text.split(/\r?\n/).map(s => s.trim()).filter(s => s && !/^(?:.*failed with )?exit code \d+$/i.test(s)
    && !/^(?:File "|Traceback \(|\^)/.test(s));
  const reason = lines.at(-1) || (zh ? '命令没有成功。' : 'The command failed.');
  return reason + (zh ? ' 请查看日志，处理上述原因后重试。' : ' Check the log, resolve this cause, then retry.');
}
