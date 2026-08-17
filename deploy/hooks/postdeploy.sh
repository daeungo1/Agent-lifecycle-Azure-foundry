#!/bin/sh
set -eu

export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"
mkdir -p artifacts

run_python() {
  if [ -n "${PYTHON:-}" ]; then
    "$PYTHON" "$@"
  elif command -v python >/dev/null 2>&1; then
    python "$@"
  elif command -v uv >/dev/null 2>&1; then
    uv run --no-project --python 3.13 --prerelease=allow \
      --with-requirements requirements-ops.txt python "$@"
  elif command -v python3 >/dev/null 2>&1; then
    python3 "$@"
  else
    echo "Python 3.13 or uv is required to run the postdeploy hook." >&2
    return 127
  fi
}

run_python -m lifecycle_ops.provisioning.rbac \
  --report-path artifacts/rbac.json
