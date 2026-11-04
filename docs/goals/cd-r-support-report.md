已在 `codex/cd-support` 分支完成 CD-R 软件支持。全程未刻录、未调用 isoburn、未向实体光驱发命令、未推送或合并；未安装软件。已有 DVD ISO、results、scans、photos 文件未改动。

交付包括 CD 扰码与 CIRC 双向映射，`rings/random/timing/geo/image/tiles/gridscan --media cd`，物理域多纹理、独立反向校验、参考 EFM 模拟器，以及 README、KNOWLEDGE 和物理模型说明。默认 DVD 路径保留。

目标卡四项验收结果：

1. **自检通过。** 扰码前缀/周期、字节交换、CIRC 正逆与 DIS 24 项对照、故意破坏检出、合成扫描均通过。四组 ±1% 几何的模拟梯子误差为 0.285–0.293°，低于 1.5°；EFM 游程 3T–11T，电平与 DSV 一致。原有 DVD 自检输出逐字一致，三个 DVD 小镜像与 main 逐字节一致。
2. **挂载与容量通过。** 环盘、随机盘、网格、色板分别为 308146、359849、316436、330451 扇区，全部通过 Windows 只读 CDFS 挂载，均未超过 ATIP 容量。
3. **独立重建通过。** 网格的 648,050,688 个可控用户字节全部匹配设计，排除文件系统五个扇区；重建图已查看。合成 CD `gridscan` 峰峰值 0.0016°。
4. **文档完成。** 证据在 `evidence/cd-support/` 和 `evidence/cd-support-20261104/`，包含测试、镜像 SHA-256、挂载和重建结果。

实盘尚未验证 CD 的 CAV/FUA、对比度、颜色、网格直线度、CIRC 物理原点及“扇区末尾加 108 帧”的读完成假设。字节交换方向已按 [ECMA-130 §16](https://ecma-international.org/wp-content/uploads/ECMA-130_2nd_edition_june_1996.pdf) 锁定并测试，但没有烧盘端到端观测。网格和色板验收镜像使用标称几何，须等 CD 实测后重新生成。

建议第一张选无需角度标定的纹理环盘：`D:\disc-probe\iso\cd-support-20261104-rings.iso`，631,083,008 字节，SHA-256：

```text
3a6219834737a4849668b3a720ee26076aa79d5a871b3a50f2f1bfd6aaea1b7b
```

生成命令已执行；已有同名文件时不要重跑，程序会拒绝覆盖：

```powershell
python -m discprobe rings --media cd --output "D:\disc-probe\iso\cd-support-20261104-rings.iso"
```

以下命令仅供你确认空盘并批准后刻录，本轮没有执行：

```powershell
isoburn.exe /Q H: "D:\disc-probe\iso\cd-support-20261104-rings.iso"
```

刻后请肉眼观察，并做至少三张 600 dpi 彩色扫描、每次旋转盘片，再运行：

```powershell
python -m discprobe ringscan scan1.png scan2.png scan3.png --layout "D:\disc-probe\iso\cd-support-20261104-rings.rings.json" --refs 0D,AA
```

之后再逐张批准随机盘刻录、计时标定和实测几何网格盘验证。
