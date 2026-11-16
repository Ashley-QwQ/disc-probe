"""Archive exact final evidence and write the bounded Chinese card report."""
import gzip
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[2]
FINAL=Path('F:/dp-archive/tmp/lobbypool/final')
BUNDLE=ROOT/'docs/cards/lobby-pool-final';BUNDLE.mkdir(exist_ok=True)
def read(name):return json.loads((FINAL/name).read_text(encoding='utf-8'))
pre=read('preflight.json');decision=read('export-decision.json');verify=read('verification.json')
surface=read('surface-check.json');drive=read('drive-prewrite.json');actual=read('drive-written.json')
jobs=verify['jobs'];rows=[]
absolute={Path(r['file']).name:r for r in decision['absolute']}
for row in decision['recorded']:
    name=Path(row['file']).name.removesuffix('_dark.webp');s=row['paper_stats']
    delta=row.get('paper_recorded_delta')
    detail='绝对' if row['paper_gate_applied']=='night-b' else '历史差值 '+('/'.join(f"{delta[k]:.9f}" for k in ('rgb_mean','alpha_mean','over8_percent')) if delta else '缺失记录')
    if name in decision.get('held_for_kraft_hue',[]):detail+='；候选牛皮纸色相未满足3度'
    rows.append(f"| {name} | {s['rgb_mean']:.9f} | {s['alpha_mean']:.9f} | {s['over8_percent']:.9f}% | {detail} | {'写入' if name in decision['written_layers'] else '保留旧图'} |")
warm=surface['desktop_warm'];kraft=surface['kraft_hue']
js=(FINAL/'javascript-tests.log').read_text(encoding='utf-8',errors='replace')
py=(FINAL/'python-tests.log').read_text(encoding='utf-8',errors='replace')
summary='\n'.join(line for line in js.splitlines() if re.match(r'[ℹ#] (tests|suites|pass|fail|cancelled|skipped|todo|duration_ms)\b',line))
failures='\n'.join(dict.fromkeys(line for line in js.splitlines() if line.startswith('✖ tests')))
job_table='\n'.join(f"| {r['job']} | {','.join(r['rendered_layers'])} | {','.join(r['reused_layers']) or '无'} | {r['seconds']:.3f} |" for r in jobs)
note=f'''# 大厅最终批量结果

七个 job 均按 manifest 分层执行 CPU、8 线程、SS=4 双主题。统一 amb=.64、gain=(5.8,5.8,5.8)、add=(0,0,0)、segment sigma=.42；物件与桌面同组。只复用用户已批准的第二版 base 双主题原始 PNG，原字节与来源哈希见 base-reused.json；其它层本轮重渲。所有 kraft 系列材质本色、灯罩自发光、铜色 LED、屏幕 glow 及线稿未改。

实际写入 **{len(decision['written_layers'])}/9** 层：{', '.join(decision['written_layers'])}。保留旧图：{', '.join(decision['kept_layers']) or '无'}。保留项的失败数字如下，不把候选图冒充已写入成果。

## 纸色门槛

绝对门槛为 RGB mean≤.3、alpha mean≤.02、>8≤.1%；绝对不通过时，对九个明确批准的大厅路径使用不可变 `3c3f66a:tools/night_b_manifest.json` 的历史数值，差值限 .05 / .01 / .1 个百分点。缺失记录拒绝写入，未放宽阈值。表中历史差值顺序也是 RGB / alpha / >8。

| 层 | RGB mean | alpha mean | >8 比例 | 实际规则或差值 | 写入结果 |
| --- | ---: | ---: | ---: | --- | --- |
{chr(10).join(rows)}

所有原始未舍入值、历史记录与 blob SHA 在 paper-absolute.json / paper-recorded.json，最终通过子集的实际导出在 paper-write.json。`tools/night_b_export.py --only lobby --paper-gate night-b-recorded --lobby-layers <通过层> --write` 执行写入；被选中的通过层整组核对后一次写入，未改纸色图片或 lobby.json。

独立 CPU 兼容试验仅禁用 AVX2，仍用 CPU、8 线程、SS=4、原材质与线稿；文件盒纸色差异仍未通过（见 cpu-compat-check.json），未采用该试验输出。源脚本与原 render_desk 的纸色、线稿参数/函数 AST 比较一致，根因仍未确定，没有据此改验证门槛。

## 光驱与桌面

写入前新 newplan 候选顶面最亮 / 最暗 L* = {drive['brightest']['L_star']:.9f} / {drive['darkest']['L_star']:.9f}，邻近桌面 (842,1074) 为 {drive['desktop']['L_star']:.9f}；最暗仍亮 {drive['min_contrast']:.9f}，超过 6，因此没有主角加档。测量沿用 top-cover 朝上面投影和 3px 轮廓/折痕排除规则。

实际写入后网页中的光驱顶面为 {actual['brightest']['L_star']:.9f} / {actual['darkest']['L_star']:.9f}，邻近桌面为 {actual['desktop']['L_star']:.9f}，最暗差值 {actual['min_contrast']:.9f}。如果 newplan 因纸色保留旧图，此处明确是旧图的实际读数。

## 桌面暖色与牛皮纸

暖色定义为 OKLCH H∈[30°,90°] 且 C>.02。只统计 desk_top ID=1 的完整覆盖像素，收进边缘并剔除前景 alpha；牛皮纸、灯罩、LED、地面和其它物件均不在桌面掩码中。暖色 **{warm['warm_pixels']} / {warm['pixels']} = {warm['ratio']*100:.9f}%**。

文件盒牛皮纸单独使用 kraft 系列 ID，保留完整覆盖、alpha=255、收进 3px、排除 7×7 通道极差>6 的线条邻域，色相比较只排除 C≤.005 的不稳定近灰像素（不套用桌面 C>.02 的暖色门槛）。共 {kraft['pixels']} 个同坐标像素。新旧圆均值色相 {kraft['old_hue_deg']:.9f}° → {kraft['new_hue_deg']:.9f}°，差 **{kraft['mean_hue_shift_deg']:.9f}°**，{'在' if kraft['material_hue_within_3deg'] else '不在'} 3° 范围内。逐像素绝对差中位 / p95 / 最大 = {kraft['median_abs_paired_delta_deg']:.9f}° / {kraft['p95_abs_paired_delta_deg']:.9f}° / {kraft['max_abs_paired_delta_deg']:.9f}°；超过 3° 的比例 {kraft['fraction_over_3deg']*100:.9f}%。不把区域均值的结论扩大为每个有损编码像素均满足 3°。像素选择与掩码见 surface-check.json、kraft-comparison-mask.png。

写入前统一中性配方的文件盒候选色相差为 {read('surface-prewrite.json')['kraft_hue']['mean_hue_shift_deg']:.9f}°（逐像素中位 {read('surface-prewrite.json')['kraft_hue']['median_abs_paired_delta_deg']:.9f}°），记录在 surface-prewrite.json。本轮文件盒同时因纸色和候选色相不符而保留旧图，写入后 0° 仅证明旧图未改，不代表中性候选满足了 3°。没有通过改材质或调整阈值来抹去候选失败，也未擅自给 kraft 沿用旧暖光响应的例外。

单独比图见 old/filebox_dark.webp 与 filebox-candidate.webp；后者是按正式配方编码的候选裁切，并非已经通过核对或已经写入的声明。

## 截图与来源

四张 1440×1000 实际网页夜色截图：lobby-dark.png、lobby-to-newplan-dark.png、lobby-to-faxnews-dark.png、lobby-to-pastworks-dark.png。通过真实大厅按钮依次进入目的页，使用与前轮相同的本地虚拟练习后端和无头 Edge；无图像请求替换，页面错误与 CSP 均为空。保留项仍显示原图。

完整场景、EXR、PNG、日志和核对记录在 `F:/dp-archive/tmp/lobbypool/final/`，审查副本在 `docs/cards/lobby-pool-final/`，原始日志以 gzip 保留原字节。没有推送或合并。
'''
(FINAL/'NOTE.md').write_text(note,encoding='utf-8')
files=['NOTE.md','preflight.json','scenes.json','scene-audit.json','source-comparison.json','cpu-compat-check.json','cpu-compat-filebox-run.json','cpu-compat-filebox.log','x79-cpu.json','lamp-cpu-preview.json','base-reused.json','drive-prewrite.json','drive-written.json',
    'surface-prewrite.json','surface-check.json','kraft-mask.json','filebox-candidate.webp','verification.json','export-decision.json',
    'paper-absolute.json','paper-recorded.json','paper-write.json','paper-absolute-run.json','paper-recorded-run.json','paper-write-run.json',
    'paper-absolute.log','paper-recorded.log','paper-write.log','capture.json','tests.json','javascript-tests.log','python-tests.log',
    'python-tests-before-fix.log','cleanup.json','desktop-only-mask.png','kraft-comparison-mask.png',
    'lobby-dark.png','lobby-to-newplan-dark.png','lobby-to-faxnews-dark.png','lobby-to-pastworks-dark.png']
for job in ['F_lobby_a','F_lobby_b','F_lobby_c','F_lobby_d','L_round5','L_lobby3','G_lamp']:files.extend([job+'-run.json',job+'.log'])
for name in files:
    if not (FINAL/name).exists():continue
    if name.endswith('.log'):(BUNDLE/(name+'.gz')).write_bytes(gzip.compress((FINAL/name).read_bytes(),mtime=0))
    else:shutil.copyfile(FINAL/name,BUNDLE/name)
old=BUNDLE/'old';old.mkdir(exist_ok=True)
shutil.copyfile(FINAL/'old/filebox_dark.webp',old/'filebox_dark.webp')
report=f'''# 卡 T 最终批量：统一大厅中性光池

本轮七个 job 已完成 CPU 渲染、九层纸色核对；实际写入 **{len(decision['written_layers'])}/9**，保留旧图 **{len(decision['kept_layers'])}/9**（{', '.join(decision['kept_layers']) or '无'}）。[完整数字与四张截图](docs/cards/lobby-pool-final/NOTE.md)。没有把未过门槛的图写进网页。

## 按提交列出的工作

- `8f879f8`：第一版 base 试烤；`3677c75`：第二版 sigma=.42 / amb=.64 / gain=5.8 / add=0，经用户确认采用。两版审查记录保留。
- 本轮 `art: apply neutral lobby pool with frozen paper checks`：按七个 manifest job 分层渲染，统一物件与桌面配方；牛皮纸、灯罩、LED、屏幕 glow 和线稿未改。增加大厅冻结历史门槛与按层选择，默认原子写入及其它组门槛保持不变；使用正式 exporter 写入通过子集，更新 manifest 和导出报告，未通过项附本轮失败数据并保留原来源。新增四张真实点击导航截图、桌面暖色和文件袋色相比对、测试及保护检查证据。

始终在 `web/lobby-pool-20261116`，父提交 `{pre['head']}`；未推送、未合并、未切分支、未改其它 worktree 或 evidence/atlas/*.py、未操作真实光驱或上传。所有路径操作和递归枚举排除用户禁止的名称。lobby.json 及 {verify['paper_count']} 张纸色原图哈希不变，非大厅 manifest/导出报告条目不变。

## 渲染和输入

CPU、`-t 8`、SS=4、16 samples，paper/dark。四个场景均为原 sigma=.42 的 segment；机位、几何及材质本色保持原输入。room_fax_parcel / room_round5 从指定 x79 stage 只读 tar 拷入，远端字节数和 SHA-256 与副本一致；room_lobby3_final 本机与远端哈希也一致。源脚本为已提交 tools/night_lobby，两份 renderer 与 stage 哈希一致，未更改 x79 或 D 盘原件。

| Job | 本轮渲染层 | 复用层 | 耗时秒 |
| --- | --- | --- | ---: |
{job_table}

F_lobby_a 的 base 来自已批准 trial2 双主题原始 PNG，按原字节复用；其余层全部本轮 CPU 重渲。逐 job 完整命令、scene/script SHA-256、manifest 原 args 和差异见 *-run.json。G_lamp 的 OPTIX 参数明确改为 CPU；没有使用 glassbox。开始 D/F 可用 {pre['free_bytes']['D']} / {pre['free_bytes']['F']} 字节；测试前和收尾均 >5GB，渲染与临时数据在 F 盘。

## 门槛、光驱和牛皮纸

逐层纸色原始统计、冻结记录和差值见 NOTE 表及 paper-*.json。Night B 绝对门槛仍为 .3 / .02 / .1%；历史差值仍为 .05 / .01 / .1 个百分点，直接读固定 Git blob，不从可变 manifest 取历史值。先做绝对检查，再做批准的历史比较；过不了的层保留旧图，数字原样报告。

newplan 候选顶面最亮/最暗 {drive['brightest']['L_star']:.6f}/{drive['darkest']['L_star']:.6f}，桌面 {drive['desktop']['L_star']:.6f}；最暗差 {drive['min_contrast']:.6f}≥6，所以未加主角档。实际网页光驱最暗差 {actual['min_contrast']:.6f}，来源是否保留旧图在 NOTE 中明确。

桌面暖色 {warm['warm_pixels']}/{warm['pixels']}（{warm['ratio']*100:.9f}%），只查桌面 ID，不把牛皮纸、灯罩或 LED 计为失败。文件盒中性候选的牛皮纸区域色相差 **{read('surface-prewrite.json')['kraft_hue']['mean_hue_shift_deg']:.9f}°>3°**，未通过；本轮保留旧文件盒，因此实际网页新旧色相差 {kraft['mean_hue_shift_deg']:.9f}°。这个 0° 不是新候选达标的结论。逐像素中位/p95/最大及超过 3° 比例均完整保留在 NOTE，没有通过改材质或旧暖光例外凑指标。

## 验收命令与测试

- `python -X utf8 -B tools/night_lobby/final_lobby.py prepare`，随后 render/all：输入拷贝、哈希及 CPU 批量。
- Blender 后台 `extract_final_masks.py`；`measure_final.py drive-prewrite / prewrite-surfaces / surfaces / drive-written`：光驱亮度、桌面暖色及 kraft 对比。
- `python -X utf8 -B tools/night_lobby/export_final.py export`：内部使用 `tools/night_b_export.py --only lobby --paper-gate night-b-recorded --lobby-layers <通过层> --write`；没有改 gate 值。
- `node tools/night_lobby/capture_final.mjs`：四张 1440×1000 夜色图，真实从大厅点击光驱、传真机、文件盒；错误和 CSP 均 []，最终截图已逐张查看。
- `final_tests.py python` / `final_tests.py javascript`：相关 pytest `-n 2` 和全部允许路径内 test_*.mjs `--test-concurrency=2`，TEMP/basetemp 在 F 盘。首次新增测试暴露了既有总开关不接受大厅，修复实现后复跑相关 Python；首次日志亦保留。

```text
{summary}
{chr(10).join(py.splitlines()[-3:])}
```

JavaScript 失败项：

```text
{failures or '无'}
```

没有修改无关 UI 或降低测试断言；未重复全量 JS。`verify_final.py` 检查 {verify['protected_count']} 个受保护文件变化 0、非大厅元数据不变、七个 job 均 CPU/8 线程、输入和源脚本不变、base 复用原字节、实际图片与门槛决策一致、四图尺寸与错误数组。`git diff --check`、UTF-8 中文检查和 gzip 原始证据字节核对在提交前完成。通过测试的临时数据清理，保留日志、截图和现存失败现场，见 cleanup.json。

## 未完成与限制

保留层 {', '.join(decision['kept_layers']) or '无'} 未完成新配方落地，原因及未舍入数字在 NOTE。没有自行放宽纸色或把更接近原图当作历史一致；原图仍显示在最终截图中。区域色相均值与逐像素色相误差分开报告，未做去饱和、向青色偏移或材质调色。跨机重现和未列出的页面未测；不会宣称大厅九层全通过，除非九层实际均已写入。
'''
(ROOT/'CARD_REPORT.md').write_text(report,encoding='utf-8')
for p in [FINAL/'NOTE.md',BUNDLE/'NOTE.md',ROOT/'CARD_REPORT.md']:
    t=p.read_text(encoding='utf-8');assert sum(ord(c)>127 for c in t)>0 and not re.search(r'\?{2,}',t)
print('Final report archived; Chinese verified')
