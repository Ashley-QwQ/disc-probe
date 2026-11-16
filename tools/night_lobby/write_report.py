"""Archive the bounded review bundle and write Chinese handoff notes in UTF-8."""
import json
import gzip
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
TRIAL = Path('F:/dp-archive/tmp/lobbypool/trial')
BUNDLE = ROOT/'docs/cards/lobby-pool-trial'
BUNDLE.mkdir(exist_ok=True)


def read(name):
    return json.loads((TRIAL/name).read_text(encoding='utf-8'))


m=read('measurements.json')
p=read('paper-check.json')[0]
v=read('verification.json')
run=read('F_lobby_a-run.json')
pre=read('preflight.json')
scene=read('scene-copy.json')
tests=read('tests.json')
js=(TRIAL/'javascript-tests.log').read_text(encoding='utf-8',errors='replace')
py=(TRIAL/'python-tests.log').read_text(encoding='utf-8',errors='replace')
summary='\n'.join(line for line in js.splitlines() if re.match(r'[ℹ#] (tests|suites|pass|fail|cancelled|skipped|todo|duration_ms)\b',line))
failures='\n'.join(dict.fromkeys(line for line in js.splitlines() if line.startswith('✖ tests')))
py_summary='\n'.join(py.splitlines()[-3:])
retest_path=TRIAL/'javascript-retest.log'
retest=retest_path.read_text(encoding='utf-8',errors='replace') if retest_path.exists() else '未复跑。'
retest_summary='\n'.join(dict.fromkeys(line for line in retest.splitlines() if re.match(r'[ℹ#] (tests|pass|fail|skipped)\b',line) or line.startswith('✖ tests'))) or retest[-1500:]
table=[]
labels={'old':'旧 base WebP','trial_png':'新 base PNG','trial_webp':'新 base 试编码 WebP'}
for name,row in m['base'].items():
    c=row['corners']
    table.append(f"| {labels[name]} | {row['nearest_visible_desktop']['L_star']:.6f} / {row['center_patch_median_L_star']:.6f} | " +
        ' / '.join(f"{c[k]['median_L_star']:.6f}" for k in ('top_left','top_right','bottom_left','bottom_right'))+' |')
center=m['base']['trial_png']
drive=m['drive_top']
paper=p['paper_stats']
note=f'''# 大厅 base 夜色试烤（卡 T，待审查）

本轮只渲 `F_lobby_a/base` 的 paper、dark 两个主题，Blender 5.2.2 LTS / CPU / 8 线程 / SS=4。原网页资源保持原图，截图的新版本只在浏览器请求中替换 base。其余八个夜色层仍是旧图；没有批量烤图。是否继续由审查看图决定。

固定配方：夜色 amb 三通道 .64、gain 三通道 2.4、add 三通道 0；segment 光池 sigma .42 → .23394（×.557），线稿、原有材质色和纸色参数不变。灯罩自发光、牛皮纸、铜色 LED 未改。两份修改后的 renderer 与依赖已存档到 `tools/night_lobby/`。

## 审查图

- `base_trial_dark.png`：新 base 原始 PNG（2560×1791）。
- `base_old_dark.webp`：提交前旧 base，原字节副本。
- `base_trial_dark.webp`：使用原配方 quality 92 / method 6 编码，仅供试览。
- `lobby_old_dark.png`、`lobby_trial_dark.png`：真实本地虚拟练习后端、无头 Edge，1440×1000；中文、夜色、关闭动作、固定时间。新图仅替换 base 响应，裁切与位置相同，页面错误及 CSP 错误均为 0。

## L*（D65，sRGB 线性化后计算）

| 图 | 光池中心最近可见桌面点 / 邻域中位 L* | 四角 L*（左上 / 右上 / 左下 / 右下） |
| --- | ---: | --- |
{chr(10).join(table)}

光池定义中心投影为 ({center['center_target_px'][0]:.6f}, {center['center_target_px'][1]:.6f})；表中使用最近可见桌面点 ({center['nearest_visible_desktop']['x']}, {center['nearest_visible_desktop']['y']})，距离 {center['distance_px']:.6f}px。若距离非零，表示中心遮挡或不在安全桌面掩码内，不声称测到了被挡住的中心。桌面由原始 ID=1 的 SS 子像素全覆盖掩码确定，向内收 3px，再排除所有可见前景层的 alpha>0 像素及其外扩 3px 区域；邻域为该点周围 5×5 中仍在掩码内的 {center['center_patch_pixels']} 个像素。四角各取 5×5 中位数，包含背景/地面，不称为桌面四角。

光驱顶面最亮 / 最暗 L*：**{drive['brightest']['L_star']:.6f} / {drive['darkest']['L_star']:.6f}**。这是网页中保留的旧 `newplan_dark.webp`，新旧截图均相同；本轮 base 不包含光驱，因此它不代表新配方下的光驱。ROI 来自该旧层原场景 `room_lobby3_final.blend` 的 `drv_SHELL_top_cover` 朝上面投影（法线 z>.55），收进 3px，只取 alpha=255，且 7×7 邻域各 RGB 通道极差均 ≤6 的 {drive['pixels']} 个像素，以排除内部折痕/轮廓的亮线及周边 3px。坐标、RGB、掩码和来源 SHA-256 见 `measurements.json`、`drive-top-mask.png`。

## 纸色核对

使用现有 `tools/night_b_export.py` 原函数（AST 提取，无改写）、原 lobby.json base 裁切、manifest 记录的 (92, 6) 编码；只计算这一张，不触发其它层读取/导出。

| RGB mean | alpha mean | >8 比例 | Night B 绝对门槛 | 结果 |
| ---: | ---: | ---: | --- | --- |
| {paper['rgb_mean']:.12f} | {paper['alpha_mean']:.12f} | {paper['over8_percent']:.12f}% | ≤.3 / ≤.02 / ≤.1% | {'通过' if p['paper_accepted'] else '未通过'} |

本张不在历史差值白名单内，未使用历史差值或放宽门槛；未改写仓库已有纸色文件或正式 WebP。完整未舍入值见 `paper-check.json`。

## 复现与证据

主命令：`python -X utf8 -B tools/night_lobby/render_trial.py`，完整 Blender 参数与耗时见 `F_lobby_a-run.json`（本次 {run['seconds']:.3f} 秒）。核对、截图、测量分别用 `check_trial.py`、`capture_trial.mjs`、`measurement_masks.py`（Blender 后台）、`measure_trial.py`，最后用 `verify_trial.py`。首次准备顺序为 prepare_trial.py → build_scripts.py → inspect_scene.py（Blender 后台）→ render_trial.py；输入原件保持不变。

完整场景、EXR、PNG 纸色核对输入和日志保留在 `F:/dp-archive/tmp/lobbypool/trial/`，仓库审查副本在 `docs/cards/lobby-pool-trial/`。不把本轮称为大厅全部层完成或视觉验收通过。**到这里停止，等待审查。**
'''
(TRIAL/'NOTE.md').write_text(note,encoding='utf-8')
files=['NOTE.md','base_trial_dark.png','base_trial_dark.webp','base_old_dark.webp',
       'lobby_old_dark.png','lobby_trial_dark.png','drive-top-mask.png','visible-desk-mask.png',
       'measurements.json','paper-check.json','verification.json','capture.json','preflight.json',
       'scene-copy.json','scene-inspection.json','F_lobby_a-run.json','F_lobby_a.log','tests.json',
       'javascript-tests.log','python-tests.log','render_fax_nightb.py.diff','render_round5_nightb.py.diff']
for optional in ('javascript-retest.log','javascript-retest.json','cleanup.json'):
    if (TRIAL/optional).exists():files.append(optional)
for name in files:
    if name.endswith('.log') or name=='scene-inspection.json':
        # Preserve exact original bytes without Git newline/whitespace rewriting.
        (BUNDLE/(name+'.gz')).write_bytes(gzip.compress((TRIAL/name).read_bytes(),mtime=0))
        if (BUNDLE/name).exists():(BUNDLE/name).unlink()
    else:
        shutil.copyfile(TRIAL/name,BUNDLE/name)
shutil.copyfile(TRIAL/'F_lobby_a/render_base.json',BUNDLE/'render_base.json')
report=f'''# 卡 T：大厅 base 夜色试烤，等待审查

## 按提交列出的工作

本轮一个提交 `art: add neutral lobby base trial for review`（父提交 `{pre['head']}`），仅在 `web/lobby-pool-20261116`：

- `tools/night_lobby/` 存档 x79 版本的两份 renderer 及依赖，并加入只试 base 的准备、渲染、核对、截图、测量、保护检查与报告脚本。
- 夜色使用固定 .64 / 2.4 / 0 配方，sigma ×.557（segment 亦适用）；纸色与柔和线设置保持原样，CPU 路径显式指定。只执行传真场景的 base 双主题 job；round5 修改后留档，未运行。G_lamp、parcel 和其它层未渲。
- [trial 图和 NOTE](docs/cards/lobby-pool-trial/NOTE.md) 已提交审查副本；F 盘保留原始场景、EXR、日志和完整证据。

正式的九张大厅夜色图、所有纸色图、lobby.json、manifest、既有导出报告和 UI/CSS 均未改。没有推送、合并或切换分支；没有操作其他 worktree、光驱、刻盘、上传或 atlas 脚本。路径操作及递归枚举按用户要求排除指定连续字母组合。

## 输入与只读检查

采用 `F:/dp-archive/tmp/lobbypool/x79stage/stage/` 的脚本。round5、palette、glow 与 `D:/disc-probe/art/desk/night-b/` 同名副本 SHA-256 相同；D 盘没有同名 fax 脚本。原件未改。逐文件字节数与 SHA-256 见 trial/preflight.json。

仅从 x79 只读拷入 `room_fax.blend`，用 Python 二进制管道连接 `ssh x79 "tar cf - -C /home/knappy/nightb/stage room_fax.blend"` 和 `tar xf -`。远端/本地均 {scene['local_bytes']} 字节，SHA-256 `{scene['sha256']}` 一致。其余远端场景不需要本轮渲染，未拷入。光驱旧图 ROI 另只读使用卡片列出的本机 `room_lobby3_final.blend`。

开始时 D/F 盘剩余 {pre['free_bytes']['D']} / {pre['free_bytes']['F']} 字节；测试前及收尾见 tests.json、verification.json，均高于 5 GB。渲染、浏览器配置与测试 TEMP/TMP 均设在 F 盘；测试内硬编码到工作树 `.impeccable/` 的截图在结束后迁到 F 盘，未提交。

## 验收命令与结果

1. `python -X utf8 -B tools/night_lobby/render_trial.py`：exit={run['exit']}，{run['seconds']:.3f} 秒，Blender 5.2.2 LTS、`-t 8 --device CPU --layers base --ss 4 --no-mist --force --variants paper,dark`。未运行其它层。
2. `python -X utf8 -B tools/night_lobby/check_trial.py`：原导出函数、原裁切、(92,6) 编码；RGB mean={paper['rgb_mean']:.12f}，alpha mean={paper['alpha_mean']:.12f}，>8={paper['over8_percent']:.12f}%；Night B 绝对门槛{'通过' if p['paper_accepted'] else '未通过'}。本层不适用历史差值白名单。没有写入正式图片。
3. `node tools/night_lobby/capture_trial.mjs`：本地虚拟练习后端，无头 Edge；新旧截图均 1440×1000、夜色、中文，错误与 CSP 记录均为 []；世界变换和各层位移完全相同，第二张仅替换 base HTTP 响应。初次相同 URL 导航没有刷新图片，被提交前像素差检查拦下；工具已改为强制重载并断言替换请求实际发生，重新截图后有 {v['screenshot_changed_pixels']} 个像素不同。初次无效截图及捕获记录以 initial/no-reload 名称保留在 F 盘，不作为本轮审查图。
4. Blender 后台运行 `measurement_masks.py` 后，`python -X utf8 -B tools/night_lobby/measure_trial.py`：L* 数值、坐标、RGB 与掩码已记录在 NOTE 和 measurements.json。光驱值属于未改的旧层。
5. `python -X utf8 -B tools/night_lobby/run_checks.py`：一次全部允许路径内的 `tests/test_*.mjs`（`node --test --test-concurrency=2`），再跑相关 `pytest -n 2 -p no:cacheprovider tests/test_night_pool.py`，TEMP 与 basetemp 在 F 盘。

JavaScript 全量结果：

```text
{summary}
```

首次失败项（F 盘原始 javascript-tests.log，仓库为保留原字节的 javascript-tests.log.gz；其他日志与完整场景清单也按原字节 gzip 存档）：

```text
{failures or '无'}
```

Python 结果：

```text
{py_summary}
```

只对 JavaScript 失败项的后续单并发复核（命令见 javascript-retest.json；不重复全套）：

```text
{retest_summary}
```

6. `python -X utf8 -B tools/night_lobby/verify_trial.py`：{v['protected_count']} 个受保护文件（其中 {v['paper_count']} 张纸色）哈希变化 0；输入原件和场景副本未改；两 renderer 的纸色样式、非灯光夜色材质与轮廓/合成/阴影设置 AST 一致；stage 与存档脚本相同。`git diff --check`、Python AST 解析、中文 UTF-8 检查均在提交前完成。拓扑与跨机渲染未测，本轮不作几何或全层一致性结论。

## 未完成、疑问与审查决定

仅完成 base 试烤。光驱、传真机、文件盒、显示器、灯等八层都保留旧图，网页对比因此是“新 base + 旧前景”；光驱顶面亮度没有体现新配方。光池定义中心被前景遮挡，NOTE 明确给出最近可见桌面点及距离；四角数值包含画面背景/地面，不夸称桌面数值。

本轮不调整固定配方来追求目标亮度，不自行判断视觉好坏；不展开无关 UI 测试故障修复，也不修改断言。首次盘库批次断言失败在单并发复核时通过；复核仍失败的 CSP 用例等待 design 超时，导航用例等待握手失败状态超时（空页面及本地连接拒绝），RW 用例等待重载恢复超时（空页面）。这些被测 UI 未在本轮修改，根因未确定；不把失败自动归为既有问题或资源竞争。需要审查决定是否接受这一张 base 试烤及是否开始后续分层渲染；本轮提交后停止等待。
'''
(ROOT/'CARD_REPORT.md').write_text(report,encoding='utf-8')
for path in (TRIAL/'NOTE.md',BUNDLE/'NOTE.md',ROOT/'CARD_REPORT.md'):
    text=path.read_text(encoding='utf-8')
    assert sum(ord(c)>127 for c in text)>0 and not re.search(r'\?{2,}',text),path
print('Review bundle archived; Chinese encoding verified.')
