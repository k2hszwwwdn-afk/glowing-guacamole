#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
python="$project_dir/.venv/bin/python"

if [[ ! -x "$python" ]]; then
    printf 'Shaker Breaker is not installed yet. Run %s/install.sh first.\n' "$project_dir" >&2
    exit 1
fi

exec "$python" "$project_dir/app.py" "$@"
