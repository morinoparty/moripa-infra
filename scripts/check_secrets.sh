#!/usr/bin/env bash
# Detect plaintext secrets committed to the repository (shared by pre-commit and CI).
# Files encrypted with sops carry a "sops:" metadata block and their values are
# ENC[...], so they never match the patterns below. *.example files are excluded.
set -euo pipefail

cd "$(dirname "$0")/.."

patterns=(
  'AGE-SECRET-KEY-1[0-9A-Z]'
  '-----BEGIN (OPENSSH|RSA|EC) PRIVATE KEY-----'
  '^PrivateKey *= *[A-Za-z0-9+/]{43}='
  # YAML written by `make wg-keygen` before sops encryption (becomes ENC[...] afterwards)
  'wg_private_key: *[A-Za-z0-9+/]{43}='
  # First-contact node password (becomes ENC[...] afterwards)
  '^ansible(_become)?_password: *[^E ].*'
  # Cloudflare token / OAuth client secrets / cookie secrets (group_vars/gateway/auth.sops.yml)
  '^cloudflare_dns_api_token: *[^E ].*'
  '^oauth2_proxy_[a-z]+_(client_secret|cookie_secret): *[^E ].*'
  # Discord webhook URL (anyone holding it can post to the channel)
  'discord(app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+'
)

fail=0
for pat in "${patterns[@]}"; do
  if hits=$(git grep -nIE "$pat" -- ':!*.example' ':!scripts/check_secrets.sh' 2>/dev/null); then
    echo "NG: possible plaintext secret detected (pattern: $pat)"
    echo "$hits"
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "-> encrypt with 'sops -e -i <file>' or remove the file"
  exit 1
fi
echo "OK: no plaintext secrets found"
