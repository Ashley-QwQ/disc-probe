#!/bin/sh
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        printf '%s\n' '请双击“Start (Windows).bat”。 / On Windows, double-click “Start (Windows).bat”.' >&2
        exit 1
        ;;
esac

CDPATH= cd -- "$(dirname -- "$0")" || exit 1
if [ ! -f ./linux/python/bin/python3 ] || [ ! -x ./linux/python/bin/python3 ]; then
    printf '%s\n' '这个包不是 Linux 完整包，或解压不完整，找不到可运行的包内 Python。 / Use the Linux full package and extract it completely. Bundled Python is missing or not executable.' >&2
    exit 1
fi
exec ./linux/python/bin/python3 -X utf8 -B -m discprobe webui --open "$@"
