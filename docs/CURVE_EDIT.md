# 曲线辅助修正 / Assisted curve correction

这是自动 φ(r) 不够好时的平滑辅助修正。初值来自已有 `correction.json`，不会用照片参考环或沿轨常数 L 伪造曲线。半径单位 mm，φ 单位度，数据面看逆时针为正；轨道角使用 `base - phi`，图像采样使用 `theta + phi`。有效范围沿用原曲线，编辑不会扩大适用范围。

## CLI

```powershell
python -B -m discprobe curve-edit --run results/geo-example
python -B -m discprobe curve-edit --run results/geo-example --edit D:/dp-dev/tmp/f1/edit.json
python -B -m discprobe curve-edit --run results/geo-example --edit D:/dp-dev/tmp/f1/edit.json --save
```

第一条输出 JSON，取其中 `edit` 对象保存为 UTF-8 文件，只改 `controls` 中的 `delta_deg`。每个控制点表示在该半径处希望增加的 φ；`radius_mm` 必须严格递增，首尾等于自动有效范围，点数 4–64。初始五点的偏移均为零。不要在 PowerShell 5.1 用默认重定向生成 JSON 文件（可能为 UTF-16）。例如用以下 Python 命令保存编辑初值，路径替换为实际目录：

```powershell
python -B -c "import json;from pathlib import Path;from discprobe.curve_edit import run_operation;r=run_operation('results/geo-example');Path('D:/dp-dev/tmp/f1/edit.json').write_text(json.dumps(r['edit'],ensure_ascii=False,indent=2),encoding='utf-8')"
```

无 `--save` 只预览，不改任何结果文件。有 `--save` 仍会重新读取来源和独立证据并验证，不能用旧的通过结果跳过。拒绝返回 `ok:false, saved:false, validation.reason`、退出码 2；初值可用但原曲线验证未过时，读取命令仍成功并如实返回失败状态。`--edit-json` 接受同一文档用于自动化调用；网页只传控制点与冻结契约/哈希，核心从服务器补上原始曲线，避免完整 spline 超过 Windows 命令行长度。

控制点以最小二乘拟合最高三次平滑偏移；原 spline 次数为 1 或 2 时对应降阶。响应 `degree` 给实际阶数。偏移叠加到原多项式或原 spline 的系数，不用显示采样点替代原模型；零修改往返保留整个 JSON 对象。这一版不支持任意局部高频描线，控制点期望不一定被逐点穿过，以返回的重拟合曲线为准。

## 独立证据

计时 geo 目录自动使用 `probes.json` 中的独立读取；拟合点、几何 targets、参考 LBA 必须与检查 LBA 分离。检查目标为 `original_phi - error_deg`。后续编辑始终使用最初自动结果和原始读取残差，不把前一次人工结果冒充真值。未覆盖的有效范围、thin intervals、缺少检查、训练/验证重叠、非有限数值、来源改变都会拒绝。

照片网格的自动多项式可提供 `curve-evidence.json`（显式来源协议），与 `correction.json` 放在同一目录，再用同一 CLI。协议例子中的检查值只是结构示意，实际至少四点，必须使用没有参与自动拟合或控制点拟合的数据：

```json
{
  "version": 1,
  "coordinates": {"radius": "mm", "angle": "deg", "positive": "ccw-data-side", "meaning": "picture-phi"},
  "automatic_sha256": "由 curve_edit.digest(自动 correction 对象) 产生",
  "dataset_id": "冻结的数据划分版本",
  "source": "照片读取器版本及来源说明",
  "input_sha256": {"training-photo": "输入文件 SHA256", "held-out-photo": "输入文件 SHA256"},
  "fit_ids": ["train-1", "train-2"],
  "checks": [{"id": "held-out-1", "radius_mm": 27.0, "phi_deg": 0.1}],
  "holes_mm": []
}
```

该协议记录调用者声明的划分、来源和输入哈希，不代替照片读取器验收，也不会重新读取原图核实这些声明。当前 pcal / photo 的 L 输出不具备这份完整 φ 证据，不能直接用于此入口。内存 API `begin(core,evidence)`、`to_core(edit)`、`preview(edit,evidence)` 可用于来源适配。

固定门槛为 RMS ≤ 0.5°，最大误差 ≤ 1°；至少四个唯一检查半径覆盖内、中、外段，相邻检查间隔不得超过范围的 40%。不按编辑或噪声放宽门槛，不将整圈误差取模消除。这只检查给定独立点，不保证点间的未知高频误差；反复观看同一验证集调参也不能作为新的封存留出试验。

## 保存及网页

通过后保留 `correction.automatic.json`、`curve-edit-history/<hash>.json`，再原子替换 `correction.json`；现有 image / disexport 自动加载同一路径。原始自动结果只备份一次，不覆盖。历史记录含编辑契约、父结果哈希、独立验证与来源。`summary.json` 的原覆盖和完成结论不改；既有生成/导出门仍会拒绝不可用的几何。

`.curve-edit.lock` 防止同时保存，哈希拒绝陈旧窗口；在替换前重读文件检测外部写入。这不是跨多个文件的事务：磁盘故障可能留下备份或历史文件，原 correction 在替换之前仍保留。若进程被强杀后留下锁，确认同目录没有正在运行的修正作业后，人工删除该锁再重试。不要在 geo 测量仍写文件时编辑它。

实际标定结果页展开“辅助修正”，读取自动曲线、修改偏移、“重拟合并验证”，通过后才可“保存修正”。修改或重读清除通过状态；虚线在重算前明确标为上次计算。修正任务期间“下一步”暂时禁用；保存修正后再“保存测量”会重新导出预设。关闭浏览器不会终止已启动的 CLI 子进程。自动曲线不存在时显示实际缺失原因并拒绝保存。

The CLI and web share the same engine and validation gate. All current acceptance fixtures are synthetic. No physical-disc or new photo-reader accuracy is claimed.
