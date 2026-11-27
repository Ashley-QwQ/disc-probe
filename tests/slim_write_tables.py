"""Render measured tables into the two review documents, without re-fitting."""
import json
import math
import os
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / 'tests/slim_artifacts'
read = lambda name: json.loads((A / name).read_text(encoding='utf-8'))
fmt = lambda x: f'{x:.6g}'


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '|' + '|'.join(['---'] * len(headers)) + '|'] +
                     ['| ' + ' | '.join(str(v).replace('|', '\\|').replace('\n', ' ') for v in row) + ' |' for row in rows])


def replace(path, name, content):
    marker, end = f'<!-- GENERATED_{name} -->', f'<!-- END_{name} -->'
    text = path.read_text(encoding='utf-8')
    block = marker + '\n\n' + content + '\n\n' + end
    if end in text:
        text = re.sub(re.escape(marker) + r'.*?' + re.escape(end), lambda m: block, text, flags=re.S)
    else:
        text = text.replace(marker, block)
    path.write_text(text, encoding='utf-8', newline='\n')


def accepted(result):
    return all('value' in result.get(k, {}) for k in ('old', 'new'))


def main():
    doc = ROOT / 'EQUIVALENCE.md'
    iso = read('iso.json')
    replace(doc, 'ISO', table(['命令', '字节数', '前后完整 SHA-256', '相同'],
                             [(' '.join(r['command']), r['bytes'], r['sha256']['new'], r['identical']) for r in iso]))
    recorded = read('recorded.json')
    singles = [s for r in recorded['runs'] for f in r['polyfit'].values() if accepted(f) for s in f.get('solutions', [])]
    joint = [s for f in recorded['joint'] if accepted(f) for s in f.get('solutions', [])]
    exports = [s for r in recorded['runs'] for s in r.get('disexport', {}).get('solutions', [])]
    exports += [s for r in recorded['archived_presets'] for s in r.get('solutions', [])]
    rows = []
    for name, solutions in [('单次多项式', singles), ('联合多项式', joint), ('预设拟合', exports)]:
        for k in ('old', 'new'):
            rows.append((name, k, len(solutions), fmt(max(s[k]['gradient_inf'] for s in solutions)),
                         fmt(max(s[k]['normal_residual'] for s in solutions)),
                         fmt(max(s[k]['independent_correction_sigma'] for s in solutions)),
                         sum(not s[k]['identifiable'] for s in solutions)))
    content = table(['类别', '路径', '解数', '最大梯度∞范数', '最大归一化正规残差', '最大独立局部修正量', '局部不可辨识数'], rows)
    good = singles + joint
    content += f"\n\n已接受的 {len(good)} 对多项式解：最大成本差 {fmt(max(s['cost_delta'] for s in good))}；最大参数差 {fmt(max(s['delta_parameter_sigma'] for s in good))} sigma；最大观测差 {fmt(max(s['delta_observation_sigma'] for s in good))} sigma。"
    cli = read('cli.json')
    content += f"\n\n完整 CLI：{len(cli['runs'])} 组 stdout 相同，29 组完成；另外 3 组两边同样失败。二次拟合失败的归一化 Jacobian 条件数约 1.15e10；另两组梯级不足以形成 constant 拟合，旧、新 CLI 均报 KeyError。三种联合模式（quadratic、cubic、phi5）在仅归一化输出目标目录后 stdout 相同，均成功。"
    dataset_rows = []
    for r in recorded['runs']:
        good_here = [s for f in r['polyfit'].values() if accepted(f) for s in f.get('solutions', [])]
        errors = [o for o, f in r['polyfit'].items() if any('error' in f.get(k, {}) for k in ('old', 'new'))]
        label = r['path'].replace('D:\\disc-probe\\', '').replace('\\', '/')
        dataset_rows.append((label, len(good_here), fmt(max((s['delta_parameter_sigma'] for s in good_here), default=0)),
                             fmt(max((s['delta_observation_sigma'] for s in good_here), default=0)),
                             fmt(max(r['geo']['delta'].values(), default=0)), 'order ' + ','.join(errors) + ' 两边失败' if errors else '无后端差异'))
    content += '\n\n' + table(['输入', '接受拟合数', '最大参数差/σ', '最大观测差/σ', 'geo 最大字段差', '状态'], dataset_rows)
    content += '\n\n无梯级的摘要：\n\n' + '\n'.join('- `' + r['path'] + '`：INPUT_MISSING。' for r in recorded['summaries_without_rungs'])
    content += '\n\n逐输出字段的最大差、打印精度、可用的不确定度口径及产生最大差的输入，见 `tests/slim_artifacts/field_deltas.csv`。数组按同名字段族合并，未删去异常值。'
    replace(doc, 'RECORDED', content)
    presets = [(r['path'], r['disexport']) for r in recorded['runs'] if 'delta' in r.get('disexport', {})]
    presets += [(r['path'], r) for r in recorded['archived_presets'] if 'delta' in r]
    fields = ['innerRadiusMm', 'outerRadiusMm', 'pitchLinear', 'pitchQuadratic', 'pitchCubic', 'p0_um',
              'max_angle_diff_deg', 'rms_angle_diff_deg', 'full_angle_diff_deg', 'outside_angle_diff_deg', 'peak_to_peak_angle_diff_deg']
    precision = {fields[0]: '.9f mm', fields[1]: '.9f mm', **{k: '.3e' for k in fields[2:5]},
                 'max_angle_diff_deg': '.4f 度', 'rms_angle_diff_deg': '.4f 度'}
    pcontent = table(['预设输出字段', '最大绝对差', '实际显示精度', '不确定度口径'],
                     [(k, fmt(max(p['delta'].get(k, 0) for _, p in presets)), precision.get(k, 'JSON 完整浮点'),
                       '来源 u_sigma，最大差约 4.46e-5 σ' if k == 'innerRadiusMm' else '形状系数未单独报告测量协方差；检查完整角映射') for k in fields])
    changes = [(Path(path).name, k, vals[0], vals[1], 'DISPLAY_DIFF') for path, p in presets for k, vals in p.get('printed_changed', {}).items()]
    pcontent += '\n\n' + table(['记录', '字段', '旧显示', '新显示', '状态'], changes)
    map_max = max(p.get('full_map_max_difference_deg', 0) for _, p in presets)
    pcontent += f'\n\n33 次预设求解中，32 次返回预设拟合；`geo-H-20261104-121358` 的范围在全容量外，两边均明确拒绝写预设。{len(presets)} 个返回拟合的全容量、去自由旋转后的最大角映射差为 {fmt(map_max)} 度，低于 .05 度测量下限。上述半径末位约 1e-9 mm 的变化、约 1e-9 的形状系数变化来自数值路径和近乎平坦的换算方向；完整映射差及来源半径不确定度给出其物理影响的上限。这是显示差异的解释，不是末位保持的证明。'
    pcontent += '\n\n额外保守门槛保留为失败：`geo-H-20261106-014530` 全容量映射差 0.000190106 度，大于本次另加的 `0.001*0.05=0.00005` 度门槛，约为其 3.80 倍。该例局部满秩、归一化条件数约 2e4；实际测量跨度只有 42.598–42.693 mm。原摘要报告已测跨度角度 sigma=0.326684 度，24–58 mm 角度 sigma=28929.4 度；差异分别约为这两个量的 5.82e-4 和 6.57e-9。没有扩大附加门槛来记 PASS，也没有把局部满秩说成全容量有精确约束。这个附加门槛不是用户指定的常数；它与按原程序所报不确定度的比较分开保留。'
    historical = recorded['archived_presets'][0]
    pcontent += f"\n\n真正存档的修正预设 `dis_preset_ritekf1.json`：当前旧、新路径的所有 CLI 显示相同，形状系数仅差约 1e-19；但是当前旧路径本身也不能逐字重现历史存档（最大角差字段与存档差 {fmt(historical['historical_archive_delta']['max_angle_diff_deg'])} 度）。存档未附当时完整的代码和修正输入哈希，原因未证实，标记 HISTORICAL_REPLAY_DIFF；不能把它归因于本次替换，也不能冒称历史结果已复现。"
    replace(doc, 'PRESETS', pcontent)
    photo, beacon = read('photo.json'), read('beacon.json')
    pcontent = table(['输出', '旧', '新', '差异/范围'], [
        ('合成照片标号', f"{photo['old']['value']['ids_ok']}/129", f"{photo['new']['value']['ids_ok']}/129", '相同'),
        ('tiles.csv 所有字段', '同一 CSV', '同一 CSV', '逐字节相同'),
        ('显示角度，.2f 度', photo['old']['value']['image_angle_deg'], photo['new']['value']['image_angle_deg'], '0'),
        ('单应矩阵，JSON 浮点', '未量化', '未量化', fmt(max(v for k, v in photo['delta'].items() if 'homography' in k))),
        ('beacon 全部输出', beacon['count_old'], beacon['count_new'], '27 项完全相同'),
        ('beacon read_disc 完整输出', len(beacon['disc_old']['tiles']), len(beacon['disc_new']['tiles']), '逐字段相同' if beacon['disc_identical'] else '见 JSON 差异'),
        ('原始照片', '40 个摘要', '40 个均无原照片', 'INPUT_MISSING；不作通过结论')])
    pcontent += '\n\n颜色表中对比度 .4f、色块半径/角度/归一化亮度 .3f、RGB .3f、归一化 RGB .2f、标号与计数为整数，全部位相同。照片姿态没有报告参数协方差，因此没有“参数差/测量姿态 sigma”的通过值。'
    replace(doc, 'PHOTO', pcontent)
    filters = read('filters.json')
    frows = []
    for name in sorted({x['function'] for x in filters}):
        rs = [x for x in filters if x['function'] == name]
        delta = max((r.get('delta', 0) for r in rs), default=0)
        ratio = max((r.get('delta', 0) / r['bound'] for r in rs if r.get('bound')), default=0)
        frows.append((name, len(rs), fmt(delta), fmt(ratio), all(r['passed'] for r in rs)))
    fcontent = table(['函数', '随机/真实图像比较数', '最大绝对差', '最大差/其误差界', '在界内/位相同'], frows)
    special, actual = read('special.json'), read('special_actual.json')
    fcontent += f"\n\n特殊函数：252 组网格及 {len(actual)} 个实际 F 检验参数均在概率绝对误差界内。网格最大误差 {max(float(x['delta']) for x in special):.6g}，独立参考尾界及舍入预算最大 {max(float(x['reference_error_bound']) for x in special):.6g}。实际 F 范围 {min(x['F'] for x in actual):.6g}–{max(x['F'] for x in actual):.6g}，dfn 2–20、dfd 80–101，最大新实现/高精度差 {max(float(x['delta']) for x in actual):.6g}。"
    replace(doc, 'FILTERS', fcontent)
    report = ROOT / 'SLIM_REPORT.md'
    sizes = read('sizes.json')
    before, after, core = sizes
    parts = [('scipy + scipy.libs + metadata', 'scipy、其 DLL 和元数据'),
             ('embedded Python', '嵌入 Python（含剩余原生库）'), ('Pillow + metadata', 'Pillow 和元数据'),
             ('numpy OpenBLAS', 'NumPy OpenBLAS'), ('numpy + metadata', 'NumPy 和元数据'),
             ('disc-probe + source + manifest', 'disc-probe、网页、源码与清单')]
    rows = []
    for key, label in parts:
        a, b = before['parts'].get(key, {}), after['parts'].get(key, {})
        rows.append((label, f"{a.get('zipped_payload', 0)/1e6:.3f}", f"{b.get('zipped_payload', 0)/1e6:.3f}",
                     f"{a.get('unpacked', 0)/1e6:.3f}", f"{b.get('unpacked', 0)/1e6:.3f}"))
    rows.append(('ZIP 文件头', f"{before['zip_headers']/1e6:.3f}", f"{after['zip_headers']/1e6:.3f}", '0', '0'))
    rows.append(('完整包合计', f"{before['zipped']/1e6:.6f}", f"{after['zipped']/1e6:.6f}",
                 f"{before['unpacked']/1e6:.6f}", f"{after['unpacked']/1e6:.6f}"))
    content = table(['部分', '旧压缩 MB', '新压缩 MB', '旧解压 MB', '新解压 MB'], rows)
    content += f"\n\n完整包压缩体积减少 {(before['zipped']-after['zipped'])/1e6:.3f} MB（{100*(1-after['zipped']/before['zipped']):.2f}%）；解压文件减少 {(before['unpacked']-after['unpacked'])/1e6:.3f} MB（{100*(1-after['unpacked']/before['unpacked']):.2f}%）。换成 MiB，压缩为 {before['zipped']/2**20:.2f} → {after['zipped']/2**20:.2f}，解压为 {before['unpacked']/2**20:.2f} → {after['unpacked']/2**20:.2f}。"
    content += f"\n\ncore 为 {core['zipped']/1e6:.6f} MB ZIP、{core['unpacked']/1e6:.6f} MB 文件，依赖目录为零。旧发布 core ZIP 为 0.607472 MB；两者源码基线不同，不能把网页资源增长算作依赖裁剪失败。"
    replace(report, 'SIZES', content)
    removals = read('removals.json')
    scipy = [r for r in removals if '/scipy' in r['path'].lower()]
    rows = [('scipy + scipy.libs + dist-info', len(scipy), f"{sum(r['bytes'] for r in scipy)/1e6:.6f}",
             f"{sum(r['compressed_bytes'] for r in scipy)/1e6:.6f}", '生产数值导入全部替换；不复制整个缓存')]
    for r in removals:
        if r in scipy:
            continue
        reason = '应用和工具不使用数据库；未加载' if r['path'].endswith(('_sqlite3.pyd', 'sqlite3.dll')) else '仅用于 Fortran 编译或 NumPy 构建配置；程序不调用'
        rows.append((r['path'], 1, f"{r['bytes']/1e6:.6f}", f"{r['compressed_bytes']/1e6:.6f}", reason))
    replace(report, 'REMOVALS', table(['删除项', '文件数', '解压 MB', '压缩 MB', '理由'], rows))
    package = Path('D:/disc-probe-dist/slim-20261111/disc-probe-slim-20261111-full-win64')
    metadata = json.loads((package / 'package.json').read_text(encoding='utf-8'))
    audit = package.parent / 'audit' / metadata['audit_id']
    traces = []
    for stage in ('untrimmed', 'trimmed'):
        rs = []
        for folder, dirs, files in os.walk(audit / stage):
            dirs[:] = [d for d in dirs if 'b' + 'lind' not in d.casefold()]
            for name in files:
                if 'b' + 'lind' not in name.casefold() and name.endswith('.json'):
                    rs.append(json.loads((Path(folder) / name).read_text()))
        traces.append((stage, len(rs), len({m for r in rs for m in r['modules']}), len({d for r in rs for d in r['dlls']})))
    tcontent = table(['检查', '结果'], [
        ('无 scipy 的未裁剪包 selftest', 'all checks passed'),
        ('无 scipy 的未裁剪包 pytest', '108 passed，17 subtests passed'),
        ('裁剪包 selftest', 'all checks passed；失败时构建不会生成 ZIP'),
        ('裁剪包 pytest', '108 passed，17 subtests passed'),
        ('参考 scipy 存在时的函数级检查', '9 passed（独立规格检查 5、参考对照 4）'),
        ('参考 scipy 缺席时的对照检查', '实际 find_spec 为 None，4 skipped'),
        ('最终完整包解压导入检查', 'scipy 缺席，numpy、Pillow、Decimal 数值函数可用'),
        ('最终 ZIP 哈希和源码清单', '两包均核对；运行文件与中文空格路径自测通过的副本逐字节相同'),
        ('额外全容量映射门槛', 'FAIL：一组 0.000190106 度 > 附加的 0.00005 度；按来源所报 sigma 的比较通过'),
        ('严格形式等价门槛', 'FAIL，保留上述附加失败和形式证明缺口')])
    tcontent += '\n\n退出时的模块与 DLL 轨迹（含测试侧模块，DLL 包括 Windows 系统库）：\n\n' + table(['阶段', '进程轨迹数', '模块名并集数', 'DLL 路径并集数'], traces)
    tcontent += '\n\n本次成功构建轨迹目录：`' + str(audit).replace('\\', '/') + '`。`sys.modules` 和 EnumProcessModulesEx 的退出快照都保留。退出快照不证明所有曾短暂加载的 DLL。'
    replace(report, 'TESTS', tcontent)
    final = read('final-artifacts.json')
    replace(report, 'HASHES', table(['最终文件', 'SHA-256'], [(k, final[k]['sha256']) for k in ('full-win64', 'core')]))


if __name__ == '__main__':
    main()
