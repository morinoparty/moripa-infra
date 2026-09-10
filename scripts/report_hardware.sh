#!/usr/bin/env bash
# Post a node's hardware summary (CPU, memory, storage) to Discord via a webhook.
#
# Usage:
#   scripts/report_hardware.sh                 # report this machine
#   scripts/report_hardware.sh --host site1-node2.wg.morino.party   # collect over SSH, post from here
#   make hw-report HOST=site1-node2            # same, via the Makefile
#
# The webhook URL is a secret (anyone holding it can post). It is read from
# DISCORD_WEBHOOK_URL or, if unset, from ~/keys/discord-hw.webhook. Never commit it.
# Remote mode runs the collector on the node and posts from this machine, so the
# webhook never leaves the admin host.
set -euo pipefail

host=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host) host="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

webhook="${DISCORD_WEBHOOK_URL:-}"
if [ -z "$webhook" ] && [ -r "$HOME/keys/discord-hw.webhook" ]; then
  webhook=$(<"$HOME/keys/discord-hw.webhook")
fi
if [ -z "$webhook" ]; then
  echo "error: set DISCORD_WEBHOOK_URL or put the webhook URL in ~/keys/discord-hw.webhook" >&2
  exit 1
fi

# ---- collector: runs on the target machine, prints key=value lines ----------
collector=$(cat <<'COLLECT'
set -euo pipefail
kv() { printf '%s=%s\n' "$1" "$2"; }
kv hostname "$(hostname)"
kv os "$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}")"
kv kernel "$(uname -r)"
kv cpu_model "$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//; s/  */ /g')"
kv cpu_cores "$(nproc --all)"
mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
kv mem_gib "$(awk -v k="$mem_kb" 'BEGIN{printf "%.1f", k/1024/1024}')"
# Physical disks (no loop / rom / zram)
lsblk -dn -b -o NAME,SIZE,MODEL,TRAN,ROTA,TYPE 2>/dev/null | awk '$NF=="disk" && $1 !~ /^(loop|zram|sr)/ {
  size=$2/1024/1024/1024; model=""; for(i=3;i<=NF-3;i++) model=model (i>3?" ":"") $i;
  printf "disk=%s|%.0f|%s|%s|%s\n", $1, size, (model==""?"-":model), $(NF-2), ($(NF-1)=="1"?"HDD":"SSD")
}'
kv root_total_gib "$(df -BG --output=size / | tail -1 | tr -dc '0-9')"
kv root_used_gib  "$(df -BG --output=used / | tail -1 | tr -dc '0-9')"
# Physical NICs only (en*/eth*/wl*), so bridges and container interfaces stay out
kv lan_ipv4 "$(ip -4 -o addr show scope global 2>/dev/null | awk '$2 ~ /^(en|eth|wl)/ {print $2": "$4}' | paste -sd, | sed 's/,/, /g' || true)"
kv wg_ipv4  "$(ip -4 -o addr show dev wg0 2>/dev/null | awk '{print $4}' | paste -sd, | sed 's/,/, /g' || true)"
COLLECT
)

if [ -n "$host" ]; then
  data=$(ssh -o ConnectTimeout=10 "$host" bash -s <<<"$collector")
else
  data=$(bash -s <<<"$collector")
fi

# ---- build the embed and post (python3 is present on every Ubuntu node; jq is not) ----
DATA="$data" WEBHOOK="$webhook" python3 - <<'PY'
import json, os, sys, urllib.request, datetime

d, disks = {}, []
for line in os.environ["DATA"].splitlines():
    k, _, v = line.partition("=")
    if k == "disk":
        name, size, model, tran, kind = v.split("|")
        disks.append(f"`{name}` {size} GB {kind} {model} ({tran})")
    else:
        d[k] = v

storage = "\n".join(disks) if disks else "-"
storage += f"\n`/` {d.get('root_used_gib','?')} / {d.get('root_total_gib','?')} GB used"
fields = [
    {"name": "CPU", "value": f"{d.get('cpu_model','?')} ({d.get('cpu_cores','?')} threads)", "inline": False},
    {"name": "Memory", "value": f"{d.get('mem_gib','?')} GiB", "inline": True},
    {"name": "OS", "value": f"{d.get('os','?')} / {d.get('kernel','?')}", "inline": True},
    {"name": "Storage", "value": storage, "inline": False},
]
net = ", ".join(x for x in (d.get("lan_ipv4"), d.get("wg_ipv4") and f"wg0: {d['wg_ipv4']}") if x)
if net:
    fields.append({"name": "Network", "value": net, "inline": False})

payload = {
    "username": "moripa-infra",
    "embeds": [{
        "title": f"🖥️ {d.get('hostname','?')}",
        "color": 0x2F855A,
        "fields": fields,
        "footer": {"text": "scripts/report_hardware.sh"},
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }],
}
req = urllib.request.Request(
    os.environ["WEBHOOK"], data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "User-Agent": "moripa-infra/1.0"},
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"posted: {d.get('hostname','?')} (HTTP {r.status})")
except urllib.error.HTTPError as e:
    sys.exit(f"discord returned HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
PY
