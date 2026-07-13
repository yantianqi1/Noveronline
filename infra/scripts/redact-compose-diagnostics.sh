#!/bin/sh
set -eu

sed -E \
  -e 's#(postgres(ql)?|redis)://[^/@[:space:]]+@#\1://[REDACTED]@#g' \
  -e 's/((authorization|Authorization|cookie|Cookie|password|PASSWORD|secret|SECRET|token|TOKEN|api_key|API_KEY)[=:][[:space:]]*)[^,[:space:]]+/\1[REDACTED]/g' \
  -e 's/(Bearer[[:space:]]+)[A-Za-z0-9._~+\/-]+/\1[REDACTED]/g'
