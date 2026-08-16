#!/bin/sh
set -eu

export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"
mkdir -p artifacts
python -m lifecycle_ops.provisioning.knowledge_bases \
  --output artifacts/knowledge-bases.json
python -m lifecycle_ops.provisioning.toolboxes
