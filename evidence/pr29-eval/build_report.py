"""Render the four requested report sections from checked CSVs (no new measurements)."""
import csv
import json
from pathlib import Path
import re
import statistics

OUT = Path(__file__).resolve().parent


def read(name):
    with (OUT / name).open(encoding='utf-8') as f:
        return list(csv.DictReader(f))


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
                     + ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows])


def pair(row, suffix, places=3):
    return ' → '.join(f'{float(row[e+suffix]):.{places}f}' for e in ('interp', 'median'))


def main():
    phases, ends, replay = read('phase_summary.csv'), read('end_summary.csv'), read('replay.csv')
    # Positive errors are late; aggregate sample RMS and percentile of absolute circular errors.
    rows = []
    for a, b in zip(phases[::2], phases[1::2]):
        assert a['estimator'] == 'interp' and b['estimator'] == 'median'
        both = lambda k: f'{float(a[k]):+.4f} → {float(b[k]):+.4f}' if k == 'bias_deg' else f'{float(a[k]):.4f} → {float(b[k]):.4f}'
        n = int(a['seeds'])
        rows.append([a['media'].upper(), f"{float(a['tail_rate']):.0%}", f"{n}/{a['blocks']} (拒 {a['failed_blocks']})",
                     both('bias_deg'), both('rms_deg'), both('p95_abs_deg'),
                     f"{a['median_better_seeds']}/{n} ({int(a['median_better_seeds'])/n:.1%}); 平 {a['tied_seeds']}"])
    text = '# PR #29 中位数剪切评估\n\n'
    text += '基点 `9c3d6bd`，分支 `dev/pr29-geo-clip`；下列箭头均为 **interp（旧）→ median（新）**，所有运行离线、未连接光驱；详细口径、命令与限制见 [METHODS.md](METHODS.md)。\n\n'
    text += '## 1. 固定每级读数的相位误差\n\n'
    text += '命令 `python -B -X utf8 evidence/pr29-eval/evaluate.py --mode phase --seeds 200 --workers 2` 生成 `phase.csv`、`phase_seeds.csv`、`phase_summary.csv`；种子 1–200，每种条件固定 14 个 LBA，DVD 为 6.6 ms/16 对读数，CD-DA 为 48.35 ms/32 对读数，两种估计器共享同一组 `phase_offsets`，以模拟真周期 ±0.01% 为搜索先验并沿用 geo 的相干度≥0.93、周期差≤0.2% 的共同有效门限（拒绝数另列），真值来自模拟器几何（DVD 同时用 truth_u、truth_v 交叉核对）。\n\n'
    text += table(['时序', '新增晚尾比例', '种子/每级样本', '偏差 °', 'RMS °', '绝对误差 P95 °', '新更好种子（按 RMS）'], rows) + '\n\n'
    wide = read('wide_period_diagnostic/phase_summary.csv')
    raw_wide = read('wide_period_diagnostic/phase.csv')
    large = sum(abs(float(r['interp_error_deg'])) > 30 for r in raw_wide)
    text += f'尾巴是每次介质读取独立抽样的 `80% U(10,20°)+20% U(4,60°)`，同时作用于参考和目标，并非实测 BU20N 分布；宽周期先验 ±2% 的原始诊断保存在 `wide_period_diagnostic/`（{large}/22400 个旧估计误差超过 30°），不能把这些共同的周期别名误差归因于剪切器。\n\n'
    rows = []
    for r in ends:
        denom = int(r['completed'])
        rows.append([f"{float(r['tail_rate']):.0%}", {'plain': '普通盘：真值跨度', 'whole': '整块：相对普通盘跨度', 'rings': '纹理环盘：真值跨度'}[r['scenario']],
                     r['estimator'], f"{denom}/{r['seeds']}", f"{float(r['median_span_deg']):.3f}", f"{float(r['p90_span_deg']):.3f}",
                     f"{r['over_1_5']}/{denom} ({float(r['rate_over_1_5']):.1%})", r['errors']])
    text += '## 2. 三个梯子场景的端到端分布\n\n'
    text += '命令 `python -B -X utf8 evidence/pr29-eval/evaluate.py --mode end-to-end --end-seeds 30 --workers 2` 生成 `end_to_end.csv`、`end_summary.csv`，沿用 `_ladder` 的 14 级、reps=16、35 ms 重读开销、state_check 设置和取样范围；整块行严格采用 selftest 的相对普通盘差异，另在原始 CSV 的 `truth_span_deg` 保留它的真值误差（无尾巴时两种读法几何相同，0° 不代表真值误差为 0°）。\n\n'
    text += table(['新增尾巴', '检查指标', '估计器', '完成/种子', '跨度中位数 °', '跨度 P90 °', '>1.5°/完成', '异常'], rows) + '\n\n'
    errors = read('end_to_end.csv')
    bad = [r for r in errors if r['status'] != 'ok']
    descriptions = [f"{r['tail_rate']}/{r['estimator']}/{r['scenario']}/seed {r['seed']}" for r in bad]
    text += f"异常共 {len(bad)} 次（整圈消歧或修正探针停止：{'; '.join(descriptions)}），未当作成功或低误差样本，分位数和超阈值比例的分母仅为完成数，因而不能忽略异常直接比较胜率。\n\n"
    text += '## 3. 已有测量重放（按 summary 型号分组）\n\n'
    manifest = json.loads((OUT / 'replay_manifest.json').read_text(encoding='utf-8'))
    by_id = {r['run_id']: r for r in manifest['runs']}
    first, unique, duplicates = {}, [], {}
    for r in replay:
        sig = tuple(sorted(by_id[r['run_id']]['sha256'].items()))
        if sig in first:
            duplicates[r['run_id']] = first[sig]
        else:
            first[sig] = r['run_id']
            unique.append(r)
    real_valid = [r for r in unique if r['classification'] == 'real' and r['eligible'] == 'True']
    rows = []
    ordered = sorted(replay, key=lambda r: (r['classification'] == 'sim', r['drive'], r['eligible'] == 'True', r['run_id']))
    for r in ordered:
        label = r['run_id'] + ('=' + duplicates[r['run_id']] if r['run_id'] in duplicates else '')
        status = ('非 geo' if r['status'] == 'not_geo' else '排除' if r['eligible'] != 'True' else '可重建')
        group = ('模拟' if r['classification'] == 'sim' else '真实') + '/' + r['drive']
        if r['status'] != 'ok':
            rows.append([group, label, status, '—', '—', '—', '—', '—', '—'])
            continue
        check = f"{float(r['rebuild_deg']):.3f}° {status}"
        outer = pair(r, '_ro_mm_or_pitch_um', 9) if r['track'] == 'audio' else (' → '.join(f"{float(r[e+'_derived_ro_mm']):.9f}" for e in ('interp', 'median')) if r.get('interp_derived_ro_mm') else '未知')
        delta_ro = f"{float(r['delta_ro_nm']):+.3f}" if r.get('delta_ro_nm') else '未知'
        rows.append([group, label, check, pair(r, '_chi2_dof', 2), pair(r, '_rms_deg'), pair(r, '_ri_mm', 9), outer,
                     f"{float(r['delta_ri_nm']):+.3f}", delta_ro])
    text += f'命令 `python -B -X utf8 evidence/pr29-eval/evaluate.py --mode replay` 在卡列出的四处安全遍历，逐目录调用未改动的 `tools.geo_reanalyse.main`，生成 `replay.csv`、`replay_logs/` 与含输入 SHA256/路径的 `replay_manifest.json`，找到 {len(replay)} 个候选、{len(duplicates)} 个完全相同副本、{len(real_valid)} 个去重后真实且重建为 0.000° 的结果；表中 ID 对应 manifest，非零检查与非 geo 行排除，`ri` 对数据盘实为工具的 r0，`ro*` 是按 setup 可读扇区数和工具输出的 pitch 推算的条件外半径（并非已验证的物理盘缘），差值均为新减旧。\n\n'
    text += table(['类别/光驱', 'ID（=副本）', '重建检查', 'χ²/dof 旧→新', 'RMS ° 旧→新', 'ri/r0 mm 旧→新', 'ro* mm 旧→新', 'Δri nm', 'Δro* nm'], rows) + '\n\n'
    wins = sum(float(r['median_rms_deg']) < float(r['interp_rms_deg']) for r in real_valid)
    loss = sum(float(r['median_rms_deg']) > float(r['interp_rms_deg']) for r in real_valid)
    text += f'去重后可重建真实结果的 RMS 为新较低 {wins}、较高 {loss}、同值 {len(real_valid)-wins-loss}（工具打印至 0.001°），型号缺失归 UNKNOWN，未找到 BU20N/CD 音轨结果，故 PR 声称的两次音轨改善未复核；重建一致只证明重放相符，残差及条件半径变化不等同几何真值精度。\n\n'
    text += '## 4. 数据边界与交回主会话的问题\n\n'
    rows = []
    for media in ('dvd', 'cd'):
        for rate in (0, .03, .10, .20):
            rs = [r for r in phases if r['media'] == media and float(r['tail_rate']) == rate]
            old, new = map(lambda r: float(r['rms_deg']), rs)
            rows.append([f'{media.upper()} 每级/{rate:.0%} 尾巴', f'RMS {old:.4f} → {new:.4f}°', f'{(new/old-1)*100:+.1f}%', '模拟时序/给定尾巴模型，非全光驱结论'])
    for scene in ('plain', 'rings'):
        rs = [r for r in ends if float(r['tail_rate']) == 0 and r['scenario'] == scene]
        old, new = rs
        rows.append([{'plain': '普通盘原噪声', 'rings': '纹理环盘原噪声'}[scene],
                     f"旧 >1.5° {old['over_1_5']}/{old['completed']}；新 {new['over_1_5']}/{new['completed']}",
                     f"异常旧 {old['errors']}，新 {new['errors']}", '阈值本就存在种子失败，是否调整待决定'])
    for media in ('dvd','cd'):
        r = next(r for r in phases if r['media']==media and float(r['tail_rate'])==0 and r['estimator']=='median')
        win, tie, n = int(r['median_better_seeds']), int(r['tied_seeds']), int(r['seeds'])
        rows.append([f'{media.upper()} 原噪声，逐 seed RMS', f'新较好 {win}/{n}，较差 {n-win-tie}/{n}，相同 {tie}/{n}',
                     '汇总 RMS 不代表每 seed 改善', '共同有效级上的配对比较'])
    rows.append(['去重可重建真实记录', f'RMS 新较低 {wins}、较高 {loss}、同值 {len(real_valid)-wins-loss}',
                 '未找到 BU20N 音轨', '残差变化并非真值误差'])
    checks = []
    for path in sorted((OUT / 'checks').glob('results_*.csv')):
        checks.extend(read('checks/' + path.name))
    self_rows = [r for r in checks if r['name'] == 'selftest']
    selflog = (OUT / 'checks/selftest.log').read_text(encoding='utf-8') if self_rows else ''
    fails = [line.strip() for line in selflog.splitlines() if re.match(r'^\s*FAIL\s+', line)]
    if self_rows:
        rows.append(['本分支 selftest', f"exit {self_rows[-1]['exit_code']}", '；'.join(fails) or '见日志', '原阈值、原种子、代码不变'])
    for category, select in [('Python geo', lambda n: n == 'pytest_geo'), ('全部 test_*.mjs', lambda n: n.startswith('test_'))]:
        selected = list({r['name']:r for r in checks if select(r['name'])}.values())
        note = '首轮 CSP 写死输出目录缺失；仅该项重定向至 F 后复测通过' if category.startswith('全部') else '无失败'
        observed = f"通过 {sum(r['exit_code']=='0' for r in selected)}/{len(selected)} 个文件"
        if category=='Python geo' and selected:
            log = OUT.parents[1] / selected[-1]['log']
            match = re.search(r'(\d+) passed',log.read_text(encoding='utf-8'))
            if match:
                observed = f'{match[1]} passed；4 个文件，pytest -n 2'
        rows.append([category, observed, ', '.join(r['name'] for r in selected if r['exit_code'] != '0') or note, '`run_checks.py` 的逐项日志和 CSV'])
    if (OUT/'audit.json').exists():
        audit = json.loads((OUT/'audit.json').read_text(encoding='utf-8'))
        rows.append(['独立数值/来源复核', audit['status'], f"{audit['numerical_checks']} 项数值复核；最终脚本重现 {audit['final_script_reproduced_rows']} 行", '`python -B -X utf8 evidence/pr29-eval/audit.py`'])
    text += '本节模拟数字来自前两节命令及其汇总 CSV，重放结论来自第三节命令，验收命令为 `python -B -X utf8 evidence/pr29-eval/run_checks.py --only selftest`、`--only python`、`--only js`（pytest 固定 `-n 2`，JS 逐个串行）；固定 1.5° 的失败率和异常单独报告，30 个种子的分位数不作总体保证。\n\n'
    text += table(['条件/验收', '观测', '变化/失败项', '解释边界'], rows) + '\n\n'
    text += '在本模型 0–20% 尾巴范围内，共同有效级的汇总 RMS 均是新较低，但尾巴增多仍使新估计器自身 RMS 上升，普通盘和纹理环盘的原噪声端到端跨度中位数则是新较高，未观测到可据以给出统一取舍的临界比例；是否合并 PR #29、是否修改 selftest 阈值均交由主会话决定，本卡没有修改产品、测试或重放工具，未测任何新硬件读取、刻录或 BU20N 实测真值。\n'
    (OUT / 'REPORT.md').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
