"""Write the second bounded trial handoff and copy an exact review bundle."""
import gzip
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[2]
TRIAL=Path('F:/dp-archive/tmp/lobbypool/trial2')
BUNDLE=ROOT/'docs/cards/lobby-pool-trial2'
BUNDLE.mkdir(exist_ok=True)


def read(name):return json.loads((TRIAL/name).read_text(encoding='utf-8'))


selection=read('selection.json')
metrics=read('measurements.json')
paper=read('paper-check.json')[0]
verify=read('verification.json')
run=read('F_lobby_a-run.json')
pre=read('preflight.json')
candidates=[read(name+'-metrics.json') for name in selection['candidate_labels']]
stats=paper['paper_stats']
tables=[]
for key,title in [('old','原暖色 base WebP'),('trial1_png','第一版 base PNG'),('trial_png','第二版 base PNG'),('trial_webp','第二版试编码 WebP')]:
    row=metrics['base'][key]
    tables.append(f"| {title} | {row['nearest_visible_desktop']['L_star']:.6f} | {row['center_patch_median_L_star']:.6f} | "+
        ' / '.join(f"{row['corners'][corner]['median_L_star']:.6f}" for corner in ('top_left','top_right','bottom_left','bottom_right'))+' |')
candidate_table='\n'.join(f"| {r['gain']:.1f} | {r['center_L_star']:.6f} | {max(r['corners_L_star']):.6f} | {r['label']} |" for r in candidates)
drive=metrics['drive_top']
row=metrics['base']['trial_png']
note=f'''# 大厅 base 第二版试烤，待审查

按用户对第一版的审查意见，本版恢复 segment 光池 sigma=**0.42**（不收窄），amb 三通道保持 **.64**，gain 三通道均为 **{selection['gain']}**，add 三通道为 **0**。只渲 base；材质本色、自发光、纸色、线稿、机位和裁切数据保持原样。其余八个前景夜色层均为旧图，光驱未在本轮重渲。正式网页资源未替换。

## 图与命令

- `base_trial_dark.png`：SS=4 正式夜色 PNG，2560×1791。
- `base_trial_dark.webp`：沿用 (92,6) 的试编码图，网页截图只替换这一张响应。
- `lobby_trial_dark.png`：1440×1000 大厅夜色截图；同第一轮的本地虚拟练习服务、无头 Edge、中文、固定时间和关闭动作，强制刷新，断言替换请求实际发生。错误与 CSP 记录均为 []。
- `base_trial1_dark.png` / `lobby_trial1_dark.png`：第一版原字节参考副本；`base_old_dark.webp` / `lobby_old_dark.png` 为正式网页原暖色参考。

准备：`python -X utf8 -B tools/night_lobby/trial2.py prepare`。生成脚本时设 `LOBBY_TRIAL=F:/dp-archive/tmp/lobbypool/trial2`、`LOBBY_GAIN={selection['gain']}`，运行 `build_scripts.py`。

两次 SS=1 小图均为 CPU、8 线程、16 samples，只渲 dark/base：

| gain | 固定桌面点 L* | 四角最高 L* | 记录 |
| ---: | ---: | ---: | --- |
{candidate_table}

两点的线性 Y 拟合在 L*=16.1 时给出 gain={selection['fitted_gain_for_L16_1']:.9f}，取 5.8；`trial2.py select` 可复算同一选择，没有把 5.8 宣称为第三次低 SS 渲染。正式命令为 `python -X utf8 -B tools/night_lobby/trial2.py render --gain {selection['gain']} --ss 4 --label F_lobby_a --variants paper,dark`，CPU / 8 线程 / SS=4，实际耗时 {run['seconds']:.3f} 秒。完整命令见 `F_lobby_a-run.json`。

## 同口径 L*

测点仍为第一版的 (842,1074)，光池定义中心投影 (856.818619,1117.521146)，距离 {row['distance_px']:.6f}px。中心被前景遮挡，所以使用安全桌面掩码内最近点，并列出其 5×5 邻域内 {row['center_patch_pixels']} 像素的中位数。掩码继续使用同场景 SS=4 ID=1 全覆盖、收进 3px，再排除可见前景 alpha>0 及外扩 3px；未移动测点或放宽目标。

| 图 | 桌面固定点 L* | 邻域中位 L* | 四角 L*（左上 / 右上 / 左下 / 右下） |
| --- | ---: | ---: | --- |
{chr(10).join(tables)}

第一版 PNG 同点 L*=11.041125。第二版 PNG 和网页实际用的试编码 WebP 均已按原值检查：桌面点在 **15.5–17**，四角各自 **≤7**。四角各取画面 5×5 中位数，包含背景/地面，不称为桌面角落。

光驱顶面最亮 / 最暗 L*：**{drive['brightest']['L_star']:.6f} / {drive['darkest']['L_star']:.6f}**，来自未改的旧 `newplan_dark.webp`，不代表新 gain 下的光驱。ROI、线条排除规则和坐标沿用第一轮，详见 measurements.json 与 drive-top-mask.png。

## 纸色及保护核对

本轮 SS=4 纸色也重新渲染，PNG 与第一轮原始纸色 PNG 的 SHA-256 相同（paper-repeat.json）；沿用原 exporter 的函数、lobby.json 裁切及 manifest 的 (92,6) 编码，使用 Night B 绝对门槛，未放宽：

| RGB mean | alpha mean | >8 比例 | 结果 |
| ---: | ---: | ---: | --- |
| {stats['rgb_mean']:.12f} | {stats['alpha_mean']:.12f} | {stats['over8_percent']:.12f}% | {'通过' if paper['paper_accepted'] else '未通过'} |

门槛分别 ≤.3 / ≤.02 / ≤.1%。{verify['protected_count']} 个受保护文件（含 {verify['paper_count']} 张纸色）哈希变化 0，第一版整个审查副本未改。输入场景、源脚本和复用的只读几何测量数据均按 SHA-256 核对。完整渲染原始数据、日志与失败现场在 `F:/dp-archive/tmp/lobbypool/trial2/`；仓库副本在 `docs/cards/lobby-pool-trial2/`。原始日志和完整场景清单以 gzip 保留原字节。

仅完成第二版 base 试烤，不批量、不推送、不合并，停止等待审查。
'''
(TRIAL/'NOTE.md').write_text(note,encoding='utf-8')
files=['NOTE.md','base_trial_dark.png','base_trial_dark.webp','base_old_dark.webp','base_trial1_dark.png',
    'lobby_trial_dark.png','lobby_old_dark.png','lobby_trial1_dark.png','paper-check.json','paper-repeat.json','measurements.json',
    'capture.json','verification.json','preflight.json','scene-copy.json','scene-inspection.json',
    'reused-geometry.json','geometry-check.json','drive-top-mask.png','visible-desk-mask.png','selection.json',
    'F_lobby_a-run.json','F_lobby_a-metrics.json','F_lobby_a.log','tests.json','javascript-tests.log',
    'python-tests.log','cleanup.json']
for label in ['candidate-g4','candidate-g4-r1','candidate-g5_5']:
    for suffix in ('-run.json','-metrics.json','.log'):
        if (TRIAL/(label+suffix)).exists():files.append(label+suffix)
    if (TRIAL/label/'desk_base_dark.png').exists():
        shutil.copyfile(TRIAL/label/'desk_base_dark.png',BUNDLE/(label+'.png'))
        shutil.copyfile(TRIAL/label/'render_base.json',BUNDLE/(label+'-render_base.json'))
for name in files:
    if name.endswith('.log') or name=='scene-inspection.json':
        (BUNDLE/(name+'.gz')).write_bytes(gzip.compress((TRIAL/name).read_bytes(),mtime=0))
    else:shutil.copyfile(TRIAL/name,BUNDLE/name)
shutil.copyfile(TRIAL/'F_lobby_a/render_base.json',BUNDLE/'render_base.json')
js=(TRIAL/'javascript-tests.log').read_text(encoding='utf-8',errors='replace')
py=(TRIAL/'python-tests.log').read_text(encoding='utf-8',errors='replace')
summary='\n'.join(line for line in js.splitlines() if re.match(r'[ℹ#] (tests|suites|pass|fail|cancelled|skipped|todo|duration_ms)\b',line))
failures='\n'.join(dict.fromkeys(line for line in js.splitlines() if line.startswith('✖ tests')))
png=metrics['base']['trial_png']; webp=metrics['base']['trial_webp']
report=f'''# 卡 T 第二版：恢复大厅光池宽度并按目标提亮

## 按提交列出的工作

- 第一版 `8f879f8`：仅 base 试烤，sigma=.42×.557、gain=2.4；图和记录仍保存在 [第一版 NOTE](docs/cards/lobby-pool-trial/NOTE.md)，本轮未改其任何文件。
- 本轮提交 `art: brighten lobby base with original pool width`：按最新审查恢复 sigma=.42，amb=.64、add=0，gain 三通道相等并经两个低 SS 候选确定为 {selection['gain']}。只执行 base；两份 renderer 一起存档，round5 未运行。加入 trial2 驱动与交付脚本，并让已有核对/截图/测试工具可通过 LOBBY_TRIAL 指定本轮目录。[第二版 NOTE 与图](docs/cards/lobby-pool-trial2/NOTE.md)。

分支始终为 `web/lobby-pool-20261116`；本轮父提交 `{pre['head']}`。未推送、未合并、未切分支、未动其他 worktree、光驱或 atlas 脚本。路径操作及递归枚举均排除用户指定的连续字母组合。所有正式网页资源、纸色图、lobby.json、manifest、原导出报告、CSS 和前景夜色层均未改。

## 渲染和数字验收

1. `python -X utf8 -B tools/night_lobby/trial2.py prepare`：复用第一版已验明的 room_fax.blend 副本，字节数与 SHA-256 再次相同；不重新访问远端。只读复用原场景清单、ID 桌面覆盖和光驱投影数据，逐文件哈希见 reused-geometry.json。x79 源脚本、原场景和第一版审查副本保持不变。开始 D/F 剩余 {pre['free_bytes']['D']} / {pre['free_bytes']['F']} 字节，测试前和收尾均高于 5 GB；全部临时数据在 F 盘。
2. 两个有效 SS=1 CPU 候选：gain=4 → L*={candidates[0]['center_L_star']:.9f}；gain=5.5 → L*={candidates[1]['center_L_star']:.9f}；四角最高均 {max(candidates[0]['corners_L_star']):.9f}。线性亮度拟合到 L*=16.1 后取 gain=5.8，详见 selection.json。首次 gain=4 启动因新 stage 缺 palette 依赖而退出、未出图；已修复准备脚本并重跑，失败日志保留，不算一个有效候选。
3. 正式命令 `python -X utf8 -B tools/night_lobby/trial2.py render --gain {selection['gain']} --ss 4 --label F_lobby_a --variants paper,dark`：CPU、8 线程、16 samples，只渲 base 双主题，exit={run['exit']}，{run['seconds']:.3f} 秒。没有批量渲其它层。
4. 同一安全桌面测点 (842,1074)，PNG **L*={png['nearest_visible_desktop']['L_star']:.9f}**，试编码 WebP **L*={webp['nearest_visible_desktop']['L_star']:.9f}**；均在 15.5–17。PNG 四角最大 **{max(c['median_L_star'] for c in png['corners'].values()):.9f}**，WebP 四角最大 **{max(c['median_L_star'] for c in webp['corners'].values()):.9f}**，均 ≤7。没有挪测点、改掩码或调整阈值。光池中心遮挡及光驱仍是旧前景的限制见 NOTE。
5. `LOBBY_TRIAL=F:/dp-archive/tmp/lobbypool/trial2` 下运行 `check_trial.py`：本轮重新渲纸色，原 exporter 函数、原裁切、(92,6) 编码；RGB mean={stats['rgb_mean']:.12f}、alpha mean={stats['alpha_mean']:.12f}、>8={stats['over8_percent']:.12f}%，Night B 绝对门槛通过（≤.3 / ≤.02 / ≤.1%）。未使用历史白名单或写入仓库纸色。
6. 同环境运行 `node tools/night_lobby/capture_trial.mjs`：本地虚拟练习后端、无头 Edge，1440×1000 中文夜色；相同固定时间、机位、布局和动作设置；强制重载并记录 base 响应替换，页面错误及 CSP 均 []。新旧截图差异 {verify['screenshot_changed_pixels']} 像素，其余层位置一致；最终截图已查看。
7. `verify_trial.py`：{verify['protected_count']} 个受保护文件，含 {verify['paper_count']} 张纸色，哈希变化 0；第一版整个 docs 副本不变；两份 renderer 的纸色样式、非灯光夜色样式、线稿/阴影相关函数 AST 与原输入相同。stage 与存档 renderer 相同；SS=4 输出及试编码各自满足亮度范围。`git diff --check`、Python 语法和中文 UTF-8 检查在提交前执行。

## 测试

`LOBBY_TRIAL=F:/dp-archive/tmp/lobbypool/trial2` 下运行 `python -X utf8 -B tools/night_lobby/run_checks.py`：一次允许路径内全部 `tests/test_*.mjs`，`node --test --test-concurrency=2`；相关 Python 为 `pytest -n 2 -p no:cacheprovider tests/test_night_pool.py`。完整命令和耗时见 tests.json，原始日志以 .log.gz 存档。

```text
{summary}
{chr(10).join(py.splitlines()[-3:])}
```

JavaScript 失败项：

```text
{failures or '无'}
```

唯一失败为导航浏览器测试：本地 handshake.mjs、api.js 等资源出现 ERR_CONNECTION_REFUSED，重载后空页面，在 design 状态等待超时。未修改测试断言或相关 UI 来消除失败，未重复跑全量。根因未在本轮判定，详细诊断与可用截图保留；测试自身 finally 清理的失败夹具未复原。通过测试的临时数据已清理，截图移入 F 盘，见 cleanup.json。

## 停止点与未测

只完成第二版 base。光驱、传真、文件盒、显示器、灯等八个前景层仍是旧图；光驱顶面数值不代表 gain=5.8 的新光驱。未测其它层、跨机和全场景一致性；没有把光池中心遮挡处当作实测桌面。本轮不再做视觉取舍或后续批量，提交后停止等待用户审查。
'''
(ROOT/'CARD_REPORT.md').write_text(report,encoding='utf-8')
for path in (TRIAL/'NOTE.md',BUNDLE/'NOTE.md',ROOT/'CARD_REPORT.md'):
    text=path.read_text(encoding='utf-8')
    assert sum(ord(c)>127 for c in text)>0 and not re.search(r'\?{2,}',text),path
print('Trial2 report and review bundle written; Chinese verified')
