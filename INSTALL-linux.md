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
| DVD / BD 写入 | `growisofs`（通常来自 `dvd+rw-tools`） |
| DVD / BD 介质检查 | `dvd+rw-mediainfo`（同一工具包） |
| CD DAO RAW16/RAW96 数据布局 | `cdrdao`，需支持对应布局的驱动和设备 |
| CD 普通模式／替代写入路径 | `wodim`，必须核对其支持的布局；不能用不支持的模式代替 RAW DAO |

BD 的具体写入支持以程序实际接受的命令和设备为准，本次未验证实盘。
Linux 用户需有 `/dev/sr*` 的读写权限，通常加入 `cdrom` 组后重新登录：

```sh
sudo usermod -aG cdrom "$USER"
```

无设备、权限不足或缺工具时先解决相应条件，不以 root 运行整个网页服务。
本次演练没有访问光驱或执行刻录。Windows CD DAO 也仍依赖外部刻录工具，
Windows 全量 ZIP 带齐 Python 照片依赖并不代表带齐所有介质的刻录程序。
