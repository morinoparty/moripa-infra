# moripa-infra

自宅サーバー4台(2拠点 × 2台) + Linode Nanode(踏み台/出口ゲートウェイ/リバースプロキシ) のインフラ管理モノレポ。

- **Terraform**: Linode リソース(Nanode, Firewall)のプロビジョニング
- **Ansible**: Linode + 4台のサーバーの構成管理(WireGuard, Caddy, k8s ブートストラップ)
- **kubernetes/**: ArgoCD が監視する GitOps マニフェスト群

## 構成概要

**2拠点構成**。各拠点が独立した k8s クラスタ(node1 = control-plane、node2 = worker)
と独立した ArgoCD を持つ。障害ドメインは完全に分離され、拠点間にクラスタの依存はない。

```
[インターネット]
      │ 80/443 → Caddy(L7, TLS 終端) / 25565 → HAProxy(L4)
[Linode Nanode]  ← WireGuard ハブ / 出口 / リバースプロキシ (10.100.0.1)
      │ wg0 (hub-and-spoke)
      │
      ├─ site1 (クラスタ用 10.200.1.0/24, VIP .10)   ├─ site2 (クラスタ用 10.200.2.0/24, VIP .10)
      │   ├── site1-node1 (10.100.0.11) CP ┐ k8s  │   ├── site2-node1 (10.100.0.21) CP ┐ k8s
      │   └── site1-node2 (10.100.0.12) wk ┘      │   └── site2-node2 (10.100.0.22) wk ┘
      │      (kubeadm + Cilium + ArgoCD)          │      (kubeadm + Cilium + ArgoCD)
```

- 各ノードの**外向き通信は Linode 経由**(フルトンネル)。外部からは Linode の固定IPに見える
- **クラスタ内通信(etcd / API / Pod の VXLAN)は各拠点の LAN 内で直接通信**し、トンネルを通らない。
  拠点の LAN は DHCP のまま(アパートのルーターは触れない)で、Ansible が**ルーターと無関係な第 2 サブネット
  (`10.200.<site>.0/24`)を LAN NIC に重ね**、kubelet / kubeadm / kube-vip はそのアドレスだけを使う。
  DHCP で貰う LAN IP はどこにも焼き込まない
  → 詳細は [docs/content/docs/architecture/wireguard.mdx](docs/content/docs/architecture/wireguard.mdx)
- 拠点間はクラスタレベルで**接続しない**(→ [docs/content/docs/architecture/multi-site.mdx](docs/content/docs/architecture/multi-site.mdx))
- HTTP/HTTPS の公開は Linode 上の **Caddy** がホスト名ごとに対象拠点のノードへ転送(TLS 終端・ノード障害時の自動切替)。
  Minecraft など L4 のサービスは **HAProxy** が対象拠点の NodePort へ転送(前段の Velocity がプレイヤー IP を渡す)
- 各拠点の control-plane は 1台(etcd 1メンバー)なので **HA ではない**。etcd バックアップが前提

## ディレクトリ構成

```
moripa-infra/
├── Makefile                    # 主要操作の入口(make help)
├── .sops.yaml                  # sops + age の暗号化ルール(age 鍵 3種)
├── terraform/                  # Linode のプロビジョニング
│   ├── modules/
│   │   └── linode-gateway/     # Nanode + Firewall + cloud-init
│   └── envs/
│       └── prod/               # 実環境の tfvars(state はローカル + gitignore)
├── ansible/
│   ├── inventory/hosts.yml     # gateway / site1(_control_plane) / site2(_control_plane)
│   ├── group_vars/
│   │   ├── all/network.yml     # ★ 共通ネットワーク値の唯一の正
│   │   └── site1.yml, site2.yml  # 拠点別(クラスタ用サブネット / VIP / グループ名)
│   ├── host_vars/<host>/       # wg 公開鍵(平文) + 秘密鍵(sops 暗号化)
│   ├── roles/
│   │   ├── base/               # ユーザー, sshd, sysctl, unattended-upgrades
│   │   ├── wireguard/          # hub/spoke 両対応 + nftables (masquerade / 公開ポート / MSS clamp)
│   │   ├── cluster_lan/        # クラスタ用の第 2 サブネットを LAN NIC に追加(netplan)
│   │   ├── wg_dns/             # Linode 上の dnsmasq(<host>.wg.morino.party → wg アドレス)
│   │   ├── reverse_proxy/      # Linode 上の Caddy(proxy_routes → 拠点ノード :80)
│   │   ├── tcp_proxy/          # Linode 上の HAProxy(tcp_routes → 拠点ノードの NodePort)
│   │   ├── k8s_prereq/         # containerd (config v3), kubeadm/kubelet
│   │   └── k8s_bootstrap/      # kube-vip, kubeadm init/join 冪等化, Cilium Helm
│   └── playbooks/              # site.yml = gateway.yml + cluster.yml
├── kubernetes/                 # 各拠点の ArgoCD が watch する領域
│   ├── common/                 # 両拠点共通のベース
│   │   ├── argocd/             # 公式 manifest + ksops パッチ (kustomize)
│   │   ├── cilium/values.yaml  # ★ Cilium 共通設定(site 側が VIP を上書き)
│   │   ├── gateway-api-crds/   # Cilium より先に同期(wave -3)
│   │   └── cert-manager/
│   └── sites/
│       ├── site1/
│       │   ├── bootstrap/
│       │   │   ├── argocd/         # common/argocd の overlay
│       │   │   ├── secrets/        # out-of-band 投入する 2 Secret(両拠点で共有鍵)
│       │   │   ├── applications/   # site1 の app-of-apps(sync wave で順序制御)
│       │   │   └── root-app.yaml
│       │   ├── infrastructure/
│       │   │   ├── cilium/values.yaml  # k8sServiceHost = site1 の VIP
│       │   │   ├── ingress/            # Cilium Gateway API(hostNetwork :80、TLS は Caddy 側)
│       │   │   └── monitoring/
│       │   └── apps/
│       │       └── minecraft/          # NodePort(HAProxy 経由、Velocity 配下)
│       └── site2/              # site1 と同構造(apps は空の雛形)
├── scripts/                    # check_consistency.py / check_secrets.sh
├── docs/                       # fumadocs ドキュメントサイト(Workers へ自動デプロイ)
└── .github/workflows/ci.yml    # make lint 相当の CI
```

## ブートストラップ順序

ArgoCD は CNI のないクラスタでは動けないため、順序が重要:

1. **Terraform**: Linode Nanode 作成 (`terraform/envs/prod`)
2. **Ansible `gateway.yml`**: Linode に WireGuard ハブ + nftables + dnsmasq + Caddy + HAProxy を設定
3. **Ansible `cluster.yml`**(両拠点を順に処理):
   1. `base` + `wireguard`: 全ノードを spoke として接続
   2. `cluster_lan`: 第 2 サブネットの固定アドレスを LAN NIC に追加(ルーター設定不要)
   3. `k8s_prereq`: containerd / kubeadm 導入
   4. `k8s_bootstrap`: 拠点ごとに node1 で `kubeadm init --skip-phases=addon/kube-proxy` → node2 を worker として join
   5. Cilium を Helm で投入 (kube-proxy replacement 有効、common + site values)
4. **ArgoCD 導入**(拠点ごと): `make bootstrap-argocd SITE=site1` / `SITE=site2`
5. 以降は各拠点の ArgoCD が `kubernetes/common/` + `kubernetes/sites/<site>/` を同期。
   Cilium の Helm リリースも ArgoCD が引き取る(同じ values を使うこと)

## 前提・未確定事項

実際の値が確定したら `ansible/group_vars/` と本ドキュメントを更新すること。

ネットワーク値の**唯一の正は `ansible/group_vars/all/network.yml`**。
本テーブルは概要であり、変更は group_vars 側で行うこと。

| 項目 | 値 | 備考 |
|---|---|---|
| ノードの OS | Ubuntu 26.04.1 LTS server | 確定 |
| 拠点構成 | 2拠点 × 2台、拠点ごとに独立クラスタ | node1 = control-plane(stacked etcd・schedulable)、node2 = worker。API VIP は kube-vip(固定アドレス目的。CP 1台なので HA ではない) |
| ノードの LAN | DHCP のまま(ルーター設定不要) | ルーターは触れない前提。Ansible が第 2 サブネットの固定アドレス(`lan_address`)を LAN NIC に追加する |
| クラスタ用サブネット | site1 `10.200.1.0/24` / site2 `10.200.2.0/24` | `cluster_lan_cidr`。node1 `.11`、node2 `.12`、VIP `.10`。実際の LAN と被ったら変更 |
| ノードの管理経路 | WireGuard(10.100.0.x) | inventory の ansible_host = wg アドレス。管理者の kubectl も wg アドレス経由(VIP は wg から届かない) |
| WireGuard CIDR | 10.100.0.0/24 | site1 は .11–.12、site2 は .21–.22。LAN / Pod / Service と重複しないこと |
| Pod / Service CIDR | 10.244.0.0/16 / 10.96.0.0/12 | **両拠点で同一値**(クラスタ同士を接続しない前提 → [docs/content/docs/architecture/multi-site.mdx](docs/content/docs/architecture/multi-site.mdx)) |
| 外部公開ポート | Minecraft 25565、HTTP/HTTPS 80/443 | 25565 は HAProxy(`tcp_routes`、Velocity 配下)、80/443 は Caddy(`proxy_routes` でホスト名 → 拠点)。SSH は公開せず wg 経由のみ |
| 秘密情報の管理 | sops + age | Ansible vars と k8s Secret の両方で使える。cluster 鍵は両拠点共有(repo は public のため deploy key 不要) |

## 注意: Nanode の転送量上限

Nanode は **1TB/月** の転送量制限と共有1vCPU。フルトンネル構成では4台分の
外向き通信(イメージ pull, OS 更新, 公開サービスのトラフィック)と
Caddy / HAProxy の中継分がここを通る(クラスタ内通信は LAN 直通なので通らない)。
超過しそうな場合は、egress を直接出す split-tunnel(`AllowedIPs = 10.100.0.0/24`)
への切り替えが可能。公開経路は Caddy / HAProxy がハブ発で接続するため
split-tunnel でも壊れない(ノードの外向き IP が自宅回線になる点だけ変わる)。

## 次のステップ

- [x] `git init` してリモート(GitHub 等)に push — **ArgoCD が参照できるリポジトリであることが前提条件**
- [x] 前提テーブルの値を確定(LAN CIDR のみ提案値。実測後 group_vars を更新)
- [x] terraform / ansible / kubernetes の各実装
- [ ] 実鍵の生成(age 鍵 3種、wg 鍵)→ 管理者向けドキュメント(docs/content/docs/admin/)
- [ ] 実機適用(管理者向けドキュメント(docs/content/docs/admin/) の手順に従う)
- [ ] etcd の定期バックアップ(control-plane が 1台のため必須。未実装)
- [ ] 公開ホスト名の DNS を Linode に向け、`proxy_routes` に登録
