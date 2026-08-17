#!/bin/sh
set -eu

export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"
mkdir -p artifacts
python -m lifecycle_ops.provisioning.rbac \
  --report-path artifacts/rbac.json
