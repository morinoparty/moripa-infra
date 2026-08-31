#!/usr/bin/env bash
# 平文の秘密がコミットされていないか検査する(pre-commit / CI 共用)。
# sops で暗号化済みのファイルは "sops:" メタデータを持ち、値は ENC[...] に
# なるため以下のパターンには一致しない。*.example は対象外。
set -euo pipefail

cd "$(dirname "$0")/.."

patterns=(
  'AGE-SECRET-KEY-1[0-9A-Z]'
  '-----BEGIN (OPENSSH|RSA|EC) PRIVATE KEY-----'
  '^PrivateKey *= *[A-Za-z0-9+/]{43}='
  # make wg-keygen が sops 暗号化前に書く YAML 形式(暗号化後は ENC[...] になる)
  'wg_private_key: *[A-Za-z0-9+/]{43}='
)

fail=0
for pat in "${patterns[@]}"; do
  if hits=$(git grep -nIE "$pat" -- ':!*.example' ':!scripts/check_secrets.sh' 2>/dev/null); then
    echo "NG: 平文の秘密らしき文字列を検出 (pattern: $pat)"
    echo "$hits"
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "→ sops -e -i で暗号化するか、ファイルを削除すること"
  exit 1
fi
echo "OK: 平文の秘密は検出されず"
