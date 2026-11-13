#!/usr/bin/env bash
set -euo pipefail
export PYTHONIOENCODING=utf-8
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Resolve a supplied lab path before moving to the unpacked package root.
args=(--config "$script_dir/dvd-r-3.json")
if [[ $# -gt 1 ]]; then
    echo "Usage: bash run-example.sh [NEW_LAB_FOLDER]" >&2
    exit 2
fi
if [[ $# -eq 1 ]]; then
    lab_path="$("${PYTHON:-python}" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$1")"
    args+=(--lab "$lab_path")
fi
cd -- "$script_dir/../.."
exec "${PYTHON:-python}" -B -m disclab.examples "${args[@]}"
