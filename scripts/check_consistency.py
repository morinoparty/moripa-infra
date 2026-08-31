#!/usr/bin/env python3
"""設定値の乖離を検査する。

単一ソース(ansible/group_vars/all/*.yml)と、それを写した各所
(cilium values / ArgoCD Application / terraform / minecraft Service)の
整合を突き合わせる。乖離があれば exit 1。
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []


def load(path: str):
    return yaml.safe_load((ROOT / path).read_text())


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


network = load("ansible/group_vars/all/network.yml")
versions = load("ansible/group_vars/all/versions.yml")
values = load("kubernetes/infrastructure/cilium/values.yaml")

# --- cilium values ↔ network.yml ---------------------------------------------
check(
    values["k8sServiceHost"] == network["kube_vip_address"],
    f"cilium values k8sServiceHost={values['k8sServiceHost']} != kube_vip_address={network['kube_vip_address']}",
)
check(
    int(values["k8sServicePort"]) == int(network["kube_api_port"]),
    "cilium values k8sServicePort != kube_api_port",
)
check(values["kubeProxyReplacement"] is True, "kubeProxyReplacement が true でない")
check(values["routingMode"] == "tunnel", "routingMode が tunnel でない")
check(values["tunnelProtocol"] == "vxlan", "tunnelProtocol が vxlan でない")
check(
    network["pod_cidr"] in values["ipam"]["operator"]["clusterPoolIPv4PodCIDRList"],
    f"pod_cidr={network['pod_cidr']} が cilium values の clusterPoolIPv4PodCIDRList に無い",
)
check(
    network["wg_interface"] in values["devices"],
    f"wg_interface={network['wg_interface']} が cilium values の devices に無い",
)

# --- ArgoCD cilium Application ↔ versions.yml --------------------------------
cilium_app = load("kubernetes/bootstrap/applications/cilium.yaml")
chart_rev = next(
    s["targetRevision"] for s in cilium_app["spec"]["sources"] if s.get("chart") == "cilium"
)
check(
    chart_rev == versions["cilium_version"],
    f"cilium App targetRevision={chart_rev} != versions.yml cilium_version={versions['cilium_version']}",
)

# --- Gateway API CRD kustomization ↔ versions.yml ----------------------------
gwapi_kust = (ROOT / "kubernetes/infrastructure/gateway-api-crds/kustomization.yaml").read_text()
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

# --- minecraft Service nodePort ↔ dnat_rules ---------------------------------
mc_rule = next((r for r in network["dnat_rules"] if r["name"] == "minecraft"), None)
if mc_rule:
    svc = load("kubernetes/apps/minecraft/service.yaml")
    node_ports = {p.get("nodePort") for p in svc["spec"]["ports"]}
    check(
        int(mc_rule["tport"]) in node_ports,
        f"minecraft Service nodePort={node_ports} に dnat tport={mc_rule['tport']} が無い",
    )

if errors:
    print("NG: 設定の乖離を検出:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("OK: check-consistency 全項目一致")
