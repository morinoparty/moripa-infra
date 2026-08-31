#!/usr/bin/env python3
"""設定値の乖離を検査する。

単一ソース(ansible/group_vars/)と、それを写した各所
(cilium values / ArgoCD Application / terraform / minecraft)の整合を
サイトごとに突き合わせる。乖離があれば exit 1。
"""

import ipaddress
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITES = ["site1", "site2"]
errors: list[str] = []


def load(path: str):
    return yaml.safe_load((ROOT / path).read_text())


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def inventory_hosts() -> dict:
    """inventory を辿り host → {wg_address, site} を返す"""
    inv = load("ansible/inventory/hosts.yml")
    hosts: dict[str, dict] = {}

    def walk(node: dict, site: str | None) -> None:
        for name, sub in (node.get("children") or {}).items():
            walk(sub or {}, name if name in SITES else site)
        for name, hv in (node.get("hosts") or {}).items():
            hosts[name] = {"wg_address": (hv or {}).get("wg_address"), "site": site}

    walk(inv["all"], None)
    return hosts


network = load("ansible/group_vars/all/network.yml")
versions = load("ansible/group_vars/all/versions.yml")
common_values = load("kubernetes/common/cilium/values.yaml")
hosts = inventory_hosts()

for site in SITES:
    sv = load(f"ansible/group_vars/{site}.yml")
    values = deep_merge(
        common_values, load(f"kubernetes/sites/{site}/infrastructure/cilium/values.yaml")
    )

    # --- cilium values (common + site) ↔ group_vars ---------------------------
    check(
        values["k8sServiceHost"] == sv["kube_vip_address"],
        f"[{site}] cilium k8sServiceHost={values['k8sServiceHost']} != kube_vip_address={sv['kube_vip_address']}",
    )
    check(
        int(values["k8sServicePort"]) == int(network["kube_api_port"]),
        f"[{site}] cilium k8sServicePort != kube_api_port",
    )
    check(values["kubeProxyReplacement"] is True, f"[{site}] kubeProxyReplacement が true でない")
    check(values["routingMode"] == "tunnel", f"[{site}] routingMode が tunnel でない")
    check(values["tunnelProtocol"] == "vxlan", f"[{site}] tunnelProtocol が vxlan でない")
    check(
        network["pod_cidr"] in values["ipam"]["operator"]["clusterPoolIPv4PodCIDRList"],
        f"[{site}] pod_cidr が clusterPoolIPv4PodCIDRList に無い",
    )
    check(
        network["wg_interface"] in values["devices"],
        f"[{site}] wg_interface が cilium devices に無い",
    )

    # --- kube-vip VIP がその拠点の LAN CIDR 内にあること ----------------------
    check(
        ipaddress.ip_address(sv["kube_vip_address"])
        in ipaddress.ip_network(sv["lan_cidr"]),
        f"[{site}] kube_vip_address={sv['kube_vip_address']} が lan_cidr={sv['lan_cidr']} の外",
    )

    # --- ArgoCD cilium Application ↔ versions.yml -----------------------------
    app = load(f"kubernetes/sites/{site}/bootstrap/applications/cilium.yaml")
    chart_rev = next(
        s["targetRevision"] for s in app["spec"]["sources"] if s.get("chart") == "cilium"
    )
    check(
        chart_rev == versions["cilium_version"],
        f"[{site}] cilium App targetRevision={chart_rev} != cilium_version={versions['cilium_version']}",
    )

# --- Gateway API CRD kustomization ↔ versions.yml ----------------------------
gwapi_kust = (ROOT / "kubernetes/common/gateway-api-crds/kustomization.yaml").read_text()
check(
    f"/{versions['gateway_api_version']}/" in gwapi_kust,
    f"gateway-api-crds が {versions['gateway_api_version']} を参照していない",
)

# --- dnat_rules ↔ terraform public_tcp_ports ---------------------------------
tf_main = (ROOT / "terraform/envs/prod/main.tf").read_text()
m = re.search(r'variable\s+"public_tcp_ports"[^}]*default\s*=\s*\[([^\]]*)\]', tf_main, re.S)
if not m:
    errors.append("terraform の public_tcp_ports default をパースできない")
else:
    tf_ports = {int(p) for p in re.findall(r"\d+", m.group(1))}
    dnat_tcp = {int(r["dport"]) for r in network["dnat_rules"] if r["proto"] == "tcp"}
    check(
        tf_ports == dnat_tcp,
        f"terraform public_tcp_ports={sorted(tf_ports)} != dnat_rules(tcp dport)={sorted(dnat_tcp)}",
    )

# --- dnat target が実在する wg アドレスであること ----------------------------
wg_by_host = {h: v["wg_address"] for h, v in hosts.items()}
for r in network["dnat_rules"]:
    check(
        r["target"] in wg_by_host.values(),
        f"dnat {r['name']} の target={r['target']} がどのホストの wg_address でもない",
    )

# --- minecraft: nodePort と nodeSelector ↔ dnat_rules ------------------------
mc_rule = next((r for r in network["dnat_rules"] if r["name"] == "minecraft"), None)
if mc_rule:
    svc = load("kubernetes/sites/site1/apps/minecraft/service.yaml")
    node_ports = {p.get("nodePort") for p in svc["spec"]["ports"]}
    check(
        int(mc_rule["tport"]) in node_ports,
        f"minecraft Service nodePort={node_ports} に dnat tport={mc_rule['tport']} が無い",
    )
    sts = load("kubernetes/sites/site1/apps/minecraft/statefulset.yaml")
    pinned = sts["spec"]["template"]["spec"]["nodeSelector"]["kubernetes.io/hostname"]
    check(
        wg_by_host.get(pinned) == mc_rule["target"],
        f"minecraft の nodeSelector={pinned} (wg={wg_by_host.get(pinned)}) と "
        f"dnat target={mc_rule['target']} が一致しない",
    )

if errors:
    print("NG: 設定の乖離を検出:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("OK: check-consistency 全項目一致")
