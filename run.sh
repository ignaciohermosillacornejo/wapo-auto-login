#!/bin/bash
set -euo pipefail

# Paths are relative to the project root; cd there first.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1Password service account token. On seattle-server it lives at
# /home/nach/.config/op/service-account-token; on the Mac, override OP_TOKEN_FILE.
OP_TOKEN_FILE="${OP_TOKEN_FILE:-$HOME/.config/op/service-account-token}"

if [[ ! -f "$OP_TOKEN_FILE" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)	fail	missing-op-token	path=$OP_TOKEN_FILE" \
    | tee -a renew.log
  exit 2
fi

OP_SERVICE_ACCOUNT_TOKEN="$(cat "$OP_TOKEN_FILE")"
export OP_SERVICE_ACCOUNT_TOKEN

# `op run --env-file=secrets.env` resolves the op:// references and exports
# the real values into the child process environment (never written to disk).
# Those env vars are then forwarded into the container with `-e VAR`.
op run --env-file="$SCRIPT_DIR/secrets.env" -- \
  docker run --rm \
    -v "$SCRIPT_DIR/profile:/profile" \
    -v "$SCRIPT_DIR/debug:/debug" \
    -e WAPO_EMAIL \
    -e WAPO_PASSWORD \
    wapo-renew:latest \
  | tee -a renew.log
