## このリポジトリの概要
morinoparty のインフラを管理するモノレポです。
リポジトリ名は `moripa-infra` です。

自宅サーバー 2 拠点 (site1 / site2) と、Linode Nanode 1 台 (WireGuard ハブ / 出口ゲートウェイ / リバースプロキシ) で構成されるインフラを、コードで管理します。

## 目的
- Linode のリソース (Nanode, Cloud Firewall) を Terraform でプロビジョニングする
- Linode ゲートウェイと各拠点のノードを Ansible で構成する (WireGuard, Caddy, HAProxy, oauth2-proxy, kubeadm による k8s ブートストラップなど)
- 各拠点の Kubernetes クラスタを、ArgoCD が監視する GitOps マニフェストで管理する
- 秘密情報は sops + age で暗号化してリポジトリに置く

## 構成の要点
- **2 拠点構成**。各拠点が独立した k8s クラスタと独立した ArgoCD を持ち、拠点間はクラスタレベルで接続しません。
  - site1: `site1-node1` 〜 `site1-node3` の 3 台がすべて control-plane (stacked etcd 3 メンバー)。`site1-node4` は予備 (`site1_spare`)
  - site2: `site2-node1` = control-plane、`site2-node2` = worker (HA ではない)。`site2-node3` / `site2-node4` は予備 (`site2_spare`)
  - 実際の構成は `ansible/inventory/hosts.yml` が正です。README の台数表記とずれている場合は inventory を優先してください。
- 各ノードの外向き通信は Linode 経由 (WireGuard のフルトンネル、`10.100.0.0/24`)。
- クラスタ内通信 (etcd / API / Pod の VXLAN) は各拠点の LAN 内で直接通信します。Ansible (`cluster_lan` ロール) がルーターと無関係な第 2 サブネット (`10.200.<site>.0/24`) を LAN NIC に追加し、kubelet の node-ip / kubeadm / Cilium の VXLAN (と kube-vip の VIP) はこのサブネットだけを使います。DHCP で貰う LAN IP はどこにも焼き込みません。
- HTTP/HTTPS の公開は Linode 上の Caddy (`gateway/caddy/Caddyfile`)、HTTP 以外 (Wings の SFTP・ゲームなど) は HAProxy (`tcp_routes`) が対象拠点のノードへ転送します。SSH は公開せず WireGuard 経由のみです。
- ネットワーク値の**唯一の正は `ansible/group_vars/all/network.yml`**、バージョンピンの唯一の正は `ansible/group_vars/all/versions.yml` です。README のテーブルは概要なので、値の変更は group_vars 側で行ってください。

## ブートストラップ順序
ArgoCD は CNI のないクラスタでは動けないため、順序が重要です。

1. Terraform: Linode Nanode を作成 (`terraform/envs/prod`)
2. Ansible `playbooks/gateway.yml`: Linode に WireGuard ハブ + nftables + dnsmasq + Caddy + HAProxy を設定
3. Ansible `playbooks/cluster.yml`: `base` + `wireguard` → `cluster_lan` → `k8s_prereq` → `k8s_bootstrap` (kubeadm init/join、Cilium を Helm で投入)
4. ArgoCD 導入 (拠点ごと): `make bootstrap-argocd SITE=site1` / `SITE=site2`
5. 以降は各拠点の ArgoCD が `kubernetes/common/` + `kubernetes/sites/<site>/` を同期する。Cilium の Helm リリースも ArgoCD が引き取るので、同じ values を使うこと

## 主な技術スタック
- Terraform (`>= 1.9`、provider `linode/linode ~> 3.0`)。state はローカル + gitignore (コミット禁止)、`.terraform.lock.hcl` はコミット対象
- Ansible (ansible-core / ansible-lint、collection: `community.sops`, `ansible.posix`, `kubernetes.core`, `community.general`)
- Kubernetes (kubeadm, Cilium (kube-proxy replacement), kube-vip, Gateway API CRDs, cert-manager)
- ArgoCD (app-of-apps、sync wave で順序制御) + kustomize + ksops
- Longhorn / RustFS / csi-s3 / kube-prometheus-stack / Headlamp (site1)
- Caddy (caddy-dns/cloudflare 入り) / HAProxy / oauth2-proxy (GitHub org / MineAuth staff) / dnsmasq (Linode 上)
- sops + age (`.sops.yaml`。admin / ci / cluster の 3 鍵)
- Python スクリプト (`scripts/check_consistency.py`, `scripts/gen_node_bootstrap.py`) と uv (`.venv` の作成)
- ドキュメントサイト: fumadocs (Next.js) を Cloudflare Workers の static assets として配信 (`docs/`、pnpm)

## 注意: Nanode の転送量上限
Nanode は 1TB/月の転送量制限と共有 1vCPU です。フルトンネル構成では全ノードの外向き通信 (イメージ pull、OS 更新、公開サービスのトラフィック) と Caddy / HAProxy の中継分がここを通ります。転送量を増やす変更は慎重に検討してください。
