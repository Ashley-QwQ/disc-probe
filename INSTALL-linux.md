# Linux 安装（1.0.0-alpha）

这是源码和通用 wheel，需要系统 Python 3.11 或更新版本；本次验证使用
Ubuntu x86_64、Python 3.12。NumPy、Pillow、SciPy、OpenCV 的二进制 wheel
必须与机器架构、Python ABI 和 glibc 兼容。没有打包 Linux Python 运行时。
公开版本写作 `1.0.0-alpha`，pip 按 PEP 440 将其规范成 `1.0.0a0`。

把发行 wheel 和匹配的依赖 wheel 放进 `wheelhouse/`，可离线安装：

```sh
pipx install --pip-args='--no-index --find-links=wheelhouse' ./disc_probe-1.0.0a0-py3-none-any.whl
```

也可以用全新虚拟环境（系统需要提供 `python3-venv`）：

```sh
python3 -m venv dp-venv
dp-venv/bin/python -m pip install --no-index --find-links=wheelhouse ./disc_probe-1.0.0a0-py3-none-any.whl
dp-venv/bin/disc-probe version --json
dp-venv/bin/disc-probe webui --local-only --port 8765
# 浏览器打开 http://127.0.0.1:8765/home/
dp-venv/bin/disc-probe selftest
```

从源码 tar.gz 安装时，解包后对其目录运行同样的 pip install 命令。
构建后端仅使用 Python 标准库，不需要联网获取构建依赖。依赖 wheel
需提前备好，`pipx` 本身也需预先安装；发行包并未发布到 PyPI。

网页、设计和自检无需光驱。光盘测量和写入需要另行安装发行版提供的工具：

| 介质／用途 | 外部工具 |
| --- | --- |
| DVD 内置写入；BD 的外部手动写入 | `growisofs`（通常来自 `dvd+rw-tools`） |
| DVD / BD 介质检查 | `dvd+rw-mediainfo`（同一工具包） |
| CD DAO 写入 | `cdrdao`，使用程序生成的 TOC，保持预扰码所用的 Mode 1 / Mode 2 布局 |
| CD 介质和速度检查 | `wodim`（内置 CD 路径也需要它，不能只装 `cdrdao`） |

当前内置 `burn` 只接受 DVD / CD；BD 需走生成镜像后的外部刻录步骤，
本次没有验证这些实盘路径。
Linux 用户需有 `/dev/sr*` 的读写权限，通常加入 `cdrom` 组后重新登录：

```sh
sudo usermod -aG cdrom "$USER"
```

无设备、权限不足或缺工具时先解决相应条件，不以 root 运行整个网页服务。
本次演练没有访问光驱或执行刻录。Windows 内置 CD DAO 尚未实现，
后端会明确拒绝；可转到 Linux 的 `cdrdao` 路径。Windows 全量 ZIP 带齐
Python 照片依赖并不代表带齐所有介质的刻录程序。
