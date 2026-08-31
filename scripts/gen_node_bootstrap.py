#!/usr/bin/env python3
"""ノード用ブートストラップスクリプトを生成する。

現地作業者が OS インストール後に1回実行するスクリプトを標準出力に出す。
実行するとノードが WireGuard spoke としてハブへ接続し、以降は管理者が
リモート(wg 経由 SSH)で Ansible を実行できるようになる。

使い方(管理者マシンで。sops と age 秘密鍵が必要):
    make node-bootstrap HOST=site1-node1
    # → bootstrap-site1-node1.sh が生成される(gitignore 対象)

注意:
- 生成物には wg 秘密鍵が平文で入る。安全な経路で渡し、実行後は削除させること
- wg0.conf の内容は ansible/roles/wireguard/templates/wg0.conf.j2 (spoke) と
  同等にしてある。初回の `make cluster` で Ansible が同じ内容で上書きするため、
  多少の乖離があっても一時的
"""

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load(path: str):
    return yaml.safe_load((ROOT / path).read_text())


def find_host(host: str):
    inv = load("ansible/inventory/hosts.yml")

    def walk(node: dict, site: str | None):
        for name, sub in (node.get("children") or {}).items():
            found = walk(sub or {}, name if name.startswith("site") and "_" not in name else site)
            if found:
                return found
        for name, hv in (node.get("hosts") or {}).items():
            if name == host:
                return (hv or {}), site
        return None

    found = walk(inv["all"], None)
    if not found:
        sys.exit(f"error: host {host} が inventory に無い")
    return found


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <host>  (例: site1-node1)")
    host = sys.argv[1]
    hv, site = find_host(host)
    if site is None:
        sys.exit(f"error: {host} は site 配下のノードではない(gateway には使えない)")

    net = load("ansible/group_vars/all/network.yml")
    sv = load(f"ansible/group_vars/{site}.yml")
    gw_pub = load("ansible/host_vars/linode-gw/main.yml")["wg_public_key"]
    if gw_pub == "REPLACE_WITH_REAL_PUBKEY":
        sys.exit("error: linode-gw の wg 公開鍵が未生成(make wg-keygen HOST=linode-gw)")

    dec = subprocess.run(
        ["sops", "-d", str(ROOT / f"ansible/host_vars/{host}/wireguard.sops.yml")],
        capture_output=True,
        text=True,
        check=True,
    )
    priv = yaml.safe_load(dec.stdout)["wg_private_key"]

    exclude = [sv["lan_cidr"], net["pod_cidr"], net["service_cidr"]]
    post_up = "\n".join(f"PostUp   = ip rule add to {c} lookup main priority 100" for c in exclude)
    post_down = "\n".join(f"PostDown = ip rule del to {c} lookup main priority 100" for c in exclude)

    print(f"""#!/usr/bin/env bash
# {host} 用ブートストラップ(moripa-infra scripts/gen_node_bootstrap.py が生成)
# このファイルには秘密鍵が含まれる。実行後は必ず削除すること:
#   sudo bash このファイル && rm このファイル
set -euo pipefail
[ "$(id -u)" = 0 ] || {{ echo "sudo で実行してください"; exit 1; }}

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q wireguard

umask 077
cat > /etc/wireguard/wg0.conf <<'WGEOF'
[Interface]
Address    = {hv["wg_address"]}/32
PrivateKey = {priv}
MTU        = {net["wg_mtu"]}
{post_up}
{post_down}

[Peer]  # linode-gw (hub)
PublicKey           = {gw_pub}
Endpoint            = {net["gateway_public_ip"]}:{net["wg_port"]}
AllowedIPs          = 0.0.0.0/0
PersistentKeepalive = 25
WGEOF

systemctl enable --now wg-quick@wg0

echo "接続を確認しています..."
if ping -c 3 -W 5 {net["wg_hub_address"]} > /dev/null; then
    echo "OK: Connected - 現地作業は完了です。管理者に連絡してください。"
else
    echo "NG: ハブに接続できません。管理者に連絡してください。"
    exit 1
fi""")


if __name__ == "__main__":
    main()
