# Linux 启动与安装

## 完整包

`disc-probe-<版本>-full.zip` 同时带 Windows 和 Linux x86_64 便携 Python 3.13
及依赖。Linux 需要 glibc 2.28 或更新。将整个 ZIP 解压到可写目录，
进入解压目录运行：

```sh
bash start-linux.sh
```

浏览器会打开大厅。也可以打开终端打印的地址。按 Ctrl+C 停止服务。
完整包启动时直接用包内的 Python，无需系统 Python、虚拟环境或安装依赖。
同一个 ZIP 在 Windows 上解压后，双击 `开始 Start (Windows).bat` 即可启动。

## 通用 wheel 或源码

这些安装方式需要 Python 3.11 或更新版本。离线使用时，提前准备与架构、
Python ABI 和 glibc 兼容的 NumPy、Pillow、SciPy 和 headless OpenCV wheel。
公开版本 `1.0.0.0-alpha` 在 wheel 文件名中按 PEP 440 写作 `1.0.0.0a0`。

把发行 wheel 和匹配的依赖 wheel 放进 `wheelhouse/`，可离线安装：

```sh
pipx install --pip-args='--no-index --find-links=wheelhouse' ./disc_probe-1.0.0.0a0-py3-none-any.whl
```

也可以用全新虚拟环境（系统需要提供 `python3-venv`）：

```sh
python3 -m venv dp-venv
dp-venv/bin/python -m pip install --no-index --find-links=wheelhouse ./disc_probe-1.0.0.0a0-py3-none-any.whl
dp-venv/bin/disc-probe version --json
dp-venv/bin/disc-probe webui --local-only --port 8765
# 浏览器打开 http://127.0.0.1:8765/home/
dp-venv/bin/disc-probe selftest
```

从源码 tar.gz 安装时，解包后对其目录运行同样的 pip install 命令。
构建后端仅使用 Python 标准库，不需要联网获取构建依赖。依赖 wheel
需提前备好，`pipx` 本身也需预先安装；发行包并未发布到 PyPI。

若 Ubuntu 缺少 ensurepip，又不能联网装 `python3.12-venv`，可由已有的
pip（22.3 或更新版）仅充当安装器，目标仍是全新隔离环境：

```sh
python3 -m venv --without-pip dp-new-venv
~/dp-venv/bin/python -m pip --python dp-new-venv install --no-index --find-links=wheelhouse ./disc_probe-1.0.0.0a0-py3-none-any.whl
```

上例不会把旧 venv 的 NumPy 等已安装依赖复用到新环境，仍需全部依赖 wheel。

网页、设计和自检无需光驱。光盘测量和写入需要另行安装发行版提供的工具：

| 介质／用途 | 外部工具 |
| --- | --- |
| DVD 内置写入；BD 的外部手动写入 | `growisofs`（通常来自 `dvd+rw-tools`） |
| DVD / BD 介质检查 | `dvd+rw-mediainfo`（同一工具包） |
| CD DAO 写入 | `cdrdao`，使用程序生成的 TOC，保持预扰码所用的 Mode 1 / Mode 2 布局 |
| CD 介质和速度检查 | `wodim`（内置 CD 路径也需要它，不能只装 `cdrdao`） |

当前内置 `burn` 只接受 DVD / CD；BD 需走生成镜像后的外部刻录步骤，
本次 Linux 验证机器没有光驱，实盘读取、刻录和网页发起刻录均未实测。
Linux 用户需有 `/dev/sr*` 的读写权限，通常加入 `cdrom` 组后重新登录：

```sh
sudo usermod -aG cdrom "$USER"
```

若 `/dev/sr*` 被独占，程序会回退到对应的 `/dev/sgN`，该设备也需要读写权限。
以普通用户运行网页服务。Windows 内置 CD DAO 尚未实现，
可使用 Linux 的 `cdrdao` 路径。上表中的刻录工具需另外安装。
