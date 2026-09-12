#!/usr/bin/env python3
"""設定値の乖離を検査する。

単一ソース(ansible/group_vars/)と、それを写した各所
(cilium values / ArgoCD Application / terraform / HAProxy / Caddy)の整合を
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
    """inventory を辿り host → {wg_address, lan_address, site, group} を返す(group は直接の所属グループ)"""
    inv = load("ansible/inventory/hosts.yml")
    hosts: dict[str, dict] = {}

    def walk(node: dict, site: str | None, group: str | None) -> None:
        for name, sub in (node.get("children") or {}).items():
            walk(sub or {}, name if name in SITES else site, name)
        for name, hv in (node.get("hosts") or {}).items():
            if name in hosts and site is None:
                continue  # 別の親(spare 等)経由で再登場しても site を消さない
            hosts[name] = {
                "wg_address": (hv or {}).get("wg_address"),
                "lan_address": (hv or {}).get("lan_address"),
                "site": site,
                "group": group,
            }

    walk(inv["all"], None, None)
    return hosts


network = load("ansible/group_vars/all/network.yml")
versions = load("ansible/group_vars/all/versions.yml")
common_values = load("kubernetes/common/cilium/values.yaml")
k8s_cluster = load("ansible/group_vars/k8s_cluster/main.yml")
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
    # Ingress(hostNetwork)の listen ポートは、ノード側の nft フィルタ(roles/k8s_prereq)が
    # wg0 / lo からのみ許可するポートと同じであること
    ing = values["ingressController"]
    check(ing["enabled"] is True, f"[{site}] ingressController.enabled が true でない")
    check(ing["hostNetwork"]["enabled"] is True, f"[{site}] ingressController.hostNetwork.enabled が true でない")
    check(
        int(ing["hostNetwork"]["sharedListenerPort"]) == int(k8s_cluster["ingress_listener_port"]),
        f"[{site}] ingressController.hostNetwork.sharedListenerPort != ingress_listener_port",
    )

    # --- kube-vip VIP と各ノードの lan_address が cluster_lan_cidr 内にあること ------
    lan_net = ipaddress.ip_network(sv["cluster_lan_cidr"])
    check(
        ipaddress.ip_address(sv["kube_vip_address"]) in lan_net,
        f"[{site}] kube_vip_address={sv['kube_vip_address']} が cluster_lan_cidr={lan_net} の外",
    )
    for h, v in hosts.items():
        if v["site"] != site:
            continue
        check(
            v["lan_address"] is not None and ipaddress.ip_address(v["lan_address"]) in lan_net,
            f"[{site}] {h} の lan_address={v['lan_address']} が cluster_lan_cidr={lan_net} の外",
        )
        check(
            v["lan_address"] != sv["kube_vip_address"],
            f"[{site}] {h} の lan_address が kube_vip_address と重複",
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

# --- wg_address は全体で、lan_address は拠点内で一意であること --------------------
wg_all = [v["wg_address"] for v in hosts.values() if v["wg_address"]]
check(len(wg_all) == len(set(wg_all)), f"wg_address が重複している: {wg_all}")
for site in SITES:
    lan_site = [v["lan_address"] for v in hosts.values() if v["site"] == site and v["lan_address"]]
    check(len(lan_site) == len(set(lan_site)), f"[{site}] lan_address が重複している: {lan_site}")

# --- Gateway API CRD kustomization ↔ versions.yml ----------------------------
gwapi_kust = (ROOT / "kubernetes/common/gateway-api-crds/kustomization.yaml").read_text()
check(
    f"/{versions['gateway_api_version']}/" in gwapi_kust,
    f"gateway-api-crds が {versions['gateway_api_version']} を参照していない",
)

# --- longhorn App targetRevision ↔ versions.yml -------------------------------
for site in SITES:
    app_path = ROOT / f"kubernetes/sites/{site}/bootstrap/applications/storage.yaml"
    if not app_path.exists():
        continue
    app = yaml.safe_load(app_path.read_text())
    chart_rev = next(
        s["targetRevision"] for s in app["spec"]["sources"] if s.get("chart") == "longhorn"
    )
    check(
        chart_rev == versions["longhorn_version"],
        f"[{site}] longhorn App targetRevision={chart_rev} != longhorn_version={versions['longhorn_version']}",
    )

# --- monitoring(kube-prometheus-stack)App targetRevision ↔ versions.yml ------------
for site in SITES:
    app_path = ROOT / f"kubernetes/sites/{site}/bootstrap/applications/monitoring.yaml"
    if not app_path.exists():
        continue
    app = yaml.safe_load(app_path.read_text())
    # site2 は雛形(single source)のまま
    if "sources" not in app["spec"]:
        continue
    chart_rev = next(
        s["targetRevision"] for s in app["spec"]["sources"] if s.get("chart") == "kube-prometheus-stack"
    )
    check(
        chart_rev == versions["kube_prometheus_stack_version"],
        f"[{site}] monitoring App targetRevision={chart_rev} != kube_prometheus_stack_version={versions['kube_prometheus_stack_version']}",
    )

# --- headlamp App targetRevision ↔ versions.yml -------------------------------
for site in SITES:
    app_path = ROOT / f"kubernetes/sites/{site}/bootstrap/applications/headlamp.yaml"
    if not app_path.exists():
        continue
    app = yaml.safe_load(app_path.read_text())
    chart_rev = next(
        s["targetRevision"] for s in app["spec"]["sources"] if s.get("chart") == "headlamp"
    )
    check(
        chart_rev == versions["headlamp_version"],
        f"[{site}] headlamp App targetRevision={chart_rev} != headlamp_version={versions['headlamp_version']}",
    )

# --- tcp_routes + proxy_public_ports ↔ terraform public_tcp_ports -------------
proxy_ports = {int(p) for p in network["proxy_public_ports"]}
tcp_routes = network.get("tcp_routes") or []
tcp_ports = {int(r["port"]) for r in tcp_routes}
check(
    not (proxy_ports & tcp_ports),
    f"proxy_public_ports={sorted(proxy_ports)} と tcp_routes の port が重複している",
)
check(len(tcp_ports) == len(tcp_routes), "tcp_routes の port が重複している")
for r in tcp_routes:
    check(r.get("site") in SITES, f"tcp_routes {r.get('name')} の site={r.get('site')} が {SITES} に無い")
    for cidr in r.get("allowed_sources") or []:
        try:
            ipaddress.ip_network(cidr)
        except ValueError:
            errors.append(f"tcp_routes {r.get('name')} の allowed_sources={cidr} が CIDR でない")
tf_main = (ROOT / "terraform/envs/prod/main.tf").read_text()
m = re.search(r'variable\s+"public_tcp_ports"[^}]*default\s*=\s*\[([^\]]*)\]', tf_main, re.S)
if not m:
    errors.append("terraform の public_tcp_ports default をパースできない")
else:
    tf_ports = {int(p) for p in re.findall(r"\d+", m.group(1))}
    check(
        tf_ports == tcp_ports | proxy_ports,
        f"terraform public_tcp_ports={sorted(tf_ports)} != "
        f"tcp_routes(port) ∪ proxy_public_ports={sorted(tcp_ports | proxy_ports)}",
    )

# --- gateway/caddy/Caddyfile が import する snippet が Ansible 側に存在すること ------
caddyfile = (ROOT / "gateway/caddy/Caddyfile").read_text()
snippet_tpl = (ROOT / "ansible/roles/reverse_proxy/templates/generated.caddy.j2").read_text()
defined = set(re.findall(r"^\(([A-Za-z0-9_]+)\)\s*\{", snippet_tpl, re.M))
for site in SITES:
    defined.add(f"to_{site}")  # for ループで生成される
for name in re.findall(r"^\s*import\s+([A-Za-z0-9_]+)\s*$", caddyfile, re.M):
    check(name in defined, f"gateway/caddy/Caddyfile の import {name} が generated.caddy.j2 に無い")
for m in re.finditer(r"import\s+to_(site\d+)", caddyfile):
    check(m.group(1) in SITES, f"gateway/caddy/Caddyfile の to_{m.group(1)} が {SITES} に無い")
check(
    re.search(rf"^{re.escape(network['auth_host'])}\s*\{{", caddyfile, re.M) is not None,
    f"gateway/caddy/Caddyfile に auth_host({network['auth_host']})のブロックが無い",
)

# --- tcp_routes: 対応する NodePort Service(kubernetes/sites/<site>/apps/<name>/service.yaml)
#     があれば nodePort と externalTrafficPolicy を突合する ------------------------
for r in tcp_routes:
    svc_path = ROOT / f"kubernetes/sites/{r['site']}/apps/{r['name']}/service.yaml"
    if not svc_path.exists():
        continue
    svc = yaml.safe_load(svc_path.read_text())
    node_ports = {p.get("nodePort") for p in svc["spec"]["ports"]}
    check(
        int(r["node_port"]) in node_ports,
        f"{r['name']} Service nodePort={node_ports} に tcp_routes node_port={r['node_port']} が無い",
    )
    check(
        svc["spec"].get("externalTrafficPolicy", "Cluster") == "Cluster",
        f"{r['name']} Service は externalTrafficPolicy=Cluster にすること(HAProxy が全ノードへ振るため)",
    )

if errors:
    print("NG: 設定の乖離を検出:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("OK: check-consistency 全項目一致")
