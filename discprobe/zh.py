"""The Chinese text of the command line: English wording -> Chinese wording.

A key with {name} parts matches a whole line with values in those places; each value is looked up
again, so messages compose. Written for someone using this for the first time: "rung" is 测量点,
"phase" is 盘面角度, and "CAV" is always glossed. A line with no entry simply stays English.
Developer output (selftest) stays English on purpose.
"""

TEXT = {
    "The first bend needs closer check points before assigning its whole-turn count.": "首次发现轨距弯曲，须先在近处补测，再确定远处测点的整圈计数。",
    "disable variable-pitch prediction and automatic repeated angle probes": "关闭变轨距预测和自动重复角度探测",
    "constant-pitch abort limit (default 25); variable pitch is followed automatically unless --no-auto-correction is given; whole-turn checks remain active": "恒定轨距拟合的停止门槛（默认 25）；默认自动跟随轨距变化，除非指定 --no-auto-correction；整圈检查始终启用",
    "Track pitch varies: measuring extra points and choosing a smooth correction from repeat reads.": "盘的轨距会变化：正在加密测量，并用重复读数选择平滑角度修正。",
    "measuring angle correction": "正在测量角度修正",
    "Track pitch varies. Extra repeated points were measured and a smooth angle correction was saved.": "盘的轨距会变化，已加密重复测量，并保存平滑角度修正。",
    "Correction residual: rms {rms} deg, max {max} deg; repeat CV {cv} deg.": "修正残差：均方根 {rms}°，最大 {max}°；重复测点交叉验证 {cv}°。",
    "Extra probing took {seconds} s. Thin radius intervals (mm): {intervals}.": "加密测量耗时 {seconds} 秒。测点稀疏的半径区间（毫米）：{intervals}。",
    "Measured radius range: {lo}-{hi} mm. Outside measured intervals is extrapolation.": "实测半径范围：{lo}–{hi} 毫米；实测区间以外属于外推。",
    "The correction is used automatically with this geometry. To disable extra probing on a new run, use geo --no-auto-correction.": "使用这份几何数据时会自动使用修正。新测量可用 geo --no-auto-correction 关闭变轨距预测和加密探测。",
    "A cubic-pitch DIS preset may not reproduce this spline; check its conversion error before use.": "DIS 的三次轨距预设可能无法复现这条样条曲线；使用前须检查转换误差。",
    "Partial measurement: candidates ran out; use only the measured radius intervals.": "测量只完成一部分：候选测点已耗尽；只可在实测半径区间内使用。",
    "Partial measurement: the correction did not pass all coverage or independent checks.": "测量只完成一部分：修正尚未通过全部覆盖范围或独立测点检查。",
    "Variable pitch is followed automatically, with closer rungs and repeated correction probes. Keep the whole-turn safety limit.": "程序会自动跟随轨距变化，缩短测点间距并重复探测修正；请保留整圈计数的安全门槛。",
    "Verdict: good. The model is compatible with the measured points, and {angle}.": "结论：好。模型与已测点相容，{angle}；测点之间的模型偏差尚未得到上界。",
    "Using the automatic angle correction: {path}": "使用自动生成的角度修正：{path}",
    "{rungs} rungs, corrected rms {rms} deg, repeat CV {cv} deg, {lo}-{hi} mm{state}": "{rungs} 个测量点，修正残差均方根 {rms}°，重复验证 {cv}°，{lo}–{hi} 毫米{state}",
    "Measured {rungs} points across {lo}-{hi} mm with a variable-pitch correction; independent check rms {rms} deg. Model bias between samples is not bounded.": "在 {lo}–{hi} 毫米测了 {rungs} 个点，并生成变轨距修正；独立检查均方根 {rms}°。测点之间的模型偏差尚无上界。",
    "Measured intervals (mm): {intervals}. Largest unsampled gap: {gap} mm. Model bias between samples is not bounded.": "实测区间（毫米）：{intervals}。最大未采样间隔：{gap} 毫米；测点之间的模型偏差尚无上界。",
    "Geometry measurement took {seconds} s; status: {status}.": "几何测量耗时 {seconds} 秒；状态：{status}。",
    "target_reached": "已达到目标测点数",
    "candidates_exhausted": "候选耗尽，仅部分完成",
    "partial_readable": "仅部分区域可读",
    "correction_unvalidated": "修正未通过独立检查",
    "correction_incomplete": "修正数据不足",
    "unwrap_ambiguous": "整圈计数存在歧义",
    "EXTRAPOLATION: requested radii {requested} mm extend outside measured intervals {measured} mm; extrapolated radii {extra} mm. Local angle sigma does not validate this range.": "外推警告：使用半径 {requested} 毫米超出实测区间 {measured} 毫米；外推半径为 {extra} 毫米。局部角度误差小，不能证明此范围可用。",
    "Measured radius coverage is unknown; extrapolation cannot be checked.": "实测半径覆盖范围未知，无法检查外推。",
    "Requested-range angle sigma is {sigma} deg (conditional on the model); measure this range again.": "使用范围内的模型条件角度误差为 {sigma}°；请重新测量这个范围。",
    "Too few repeated points for an angle correction; keep this as a partial measurement.": "重复测点太少，无法拟合角度修正；数据作为部分测量保留。",
    "Angle correction: {points} repeated points, rms {rms} deg, max {max} deg; repeat CV {cv} deg, {seconds} s. Thin intervals: {intervals}": "角度修正：{points} 个重复测点，均方根 {rms}°、最大 {max}°；重复测点交叉验证 {cv}°，耗时 {seconds} 秒。稀疏区间：{intervals}",
