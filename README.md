# moripa-infra

自宅サーバー6台 + Linode Nanode(踏み台/出口ゲートウェイ) のインフラ管理モノレポ。

- **Terraform**: Linode リソース(Nanode, Firewall)のプロビジョニング
- **Ansible**: 6台のサーバーの構成管理(WireGuard, k8s ブートストラップ)
- **kubernetes/**: ArgoCD が監視する GitOps マニフェスト群

## 構成概要

**2拠点構成**。各拠点が独立した k8s クラスタ(3台全部 control-plane・schedulable)
と独立した ArgoCD を持つ。障害ドメインは完全に分離され、拠点間にクラスタの依存はない。

```
[インターネット]
      │
[Linode Nanode]  ← WireGuard ハブ / 出口 (10.100.0.1)
      │ wg0 (hub-and-spoke)
      │
      ├─ site1 (LAN 192.168.10.0/24, VIP .10)     ├─ site2 (LAN 192.168.20.0/24, VIP .10)
      │   ├── site1-node1 (10.100.0.11) ┐         │   ├── site2-node1 (10.100.0.21) ┐
      │   ├── site1-node2 (10.100.0.12) │ k8s     │   ├── site2-node2 (10.100.0.22) │ k8s
      │   └── site1-node3 (10.100.0.13) ┘ cluster │   └── site2-node3 (10.100.0.23) ┘ cluster
      │      (kubeadm + Cilium + ArgoCD)          │      (kubeadm + Cilium + ArgoCD)
```

- 各ノードの**外向き通信は Linode 経由**(フルトンネル)。外部からは Linode の固定IPに見える
- **クラスタ内通信(etcd / Pod / Service)は各拠点の LAN 内で直接通信**し、トンネルを通らない
  → 詳細は [docs/content/docs/architecture/wireguard.mdx](docs/content/docs/architecture/wireguard.mdx)
- 拠点間はクラスタレベルで**接続しない**(→ [docs/content/docs/architecture/multi-site.mdx](docs/content/docs/architecture/multi-site.mdx))
- 外部公開は Linode 側の DNAT でトンネル越しに対象拠点のノードへ転送

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
│   │   └── site1.yml, site2.yml  # 拠点別(LAN CIDR / VIP / グループ名)
│   ├── host_vars/<host>/       # wg 公開鍵(平文) + 秘密鍵(sops 暗号化)
│   ├── roles/
│   │   ├── base/               # ユーザー, sshd, sysctl, unattended-upgrades
│   │   ├── wireguard/          # hub/spoke 両対応 + nftables (DNAT / MSS clamp)
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
│       │   │   ├── ingress/            # Cilium Gateway API(hostNetwork :80/:443)
│       │   │   └── monitoring/
│       │   └── apps/
│       │       └── minecraft/          # eTP Local + DNAT 先ノードにピン
│       └── site2/              # site1 と同構造(apps は空の雛形)
├── scripts/                    # check_consistency.py / check_secrets.sh
├── docs/                       # fumadocs ドキュメントサイト(Workers へ自動デプロイ)
└── .github/workflows/ci.yml    # make lint 相当の CI
```

## ブートストラップ順序

ArgoCD は CNI のないクラスタでは動けないため、順序が重要:

1. **Terraform**: Linode Nanode 作成 (`terraform/envs/prod`)
2. **Ansible `gateway.yml`**: Linode に WireGuard ハブ + nftables (masquerade / DNAT) を設定
3. **Ansible `cluster.yml`**(両拠点を順に処理):
   1. `base` + `wireguard`: 全ノードを spoke として接続
   2. `k8s_prereq`: containerd / kubeadm 導入
   3. `k8s_bootstrap`: 拠点ごとに `kubeadm init --skip-phases=addon/kube-proxy` → join
   4. Cilium を Helm で投入 (kube-proxy replacement 有効、common + site values)
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
| 拠点構成 | 2拠点 × 3台、拠点ごとに独立クラスタ | 各拠点 3台全部 control-plane(stacked etcd・schedulable)、API VIP は kube-vip |
| site1 LAN CIDR | 192.168.10.0/24(提案値) | ノード .11–.13、kube-vip VIP .10 |
| site2 LAN CIDR | 192.168.20.0/24(提案値) | ノード .11–.13、kube-vip VIP .10 |
| WireGuard CIDR | 10.100.0.0/24 | site1 は .11–.13、site2 は .21–.23。LAN / Pod / Service と重複しないこと |
| Pod / Service CIDR | 10.244.0.0/16 / 10.96.0.0/12 | **両拠点で同一値**(クラスタ同士を接続しない前提 → [docs/content/docs/architecture/multi-site.mdx](docs/content/docs/architecture/multi-site.mdx)) |
| 外部公開ポート | Minecraft 25565、HTTP/HTTPS 80/443 | Linode 側 DNAT(現状すべて site1 向け)。SSH は公開せず wg 経由のみ |
| 秘密情報の管理 | sops + age | Ansible vars と k8s Secret の両方で使える。cluster 鍵と deploy key は両拠点共有 |

## 注意: Nanode の転送量上限

Nanode は **1TB/月** の転送量制限と共有1vCPU。フルトンネル構成では6台分の
外向き通信(イメージ pull, OS 更新, 公開サービスのトラフィック)がすべてここを通る。
超過しそうな場合は、egress は直接出す split-tunnel への切り替えを検討する。
ただし **AllowedIPs を 10.100.0.0/24 に絞るだけでは DNAT が壊れる**ので注意
(DNAT された inbound パケットは送信元がクライアントの公開IPのままトンネルを
通るため、cryptokey routing で破棄され、戻り経路も非対称になる)。
split-tunnel にする場合の選択肢:
- `AllowedIPs = 0.0.0.0/0` は維持しつつ `Table = off` + 独自ルーティングルールで
  egress だけ直接出す(クライアントの実IPは保持される)
- ハブ側で wg0 向けに SNAT する(簡単だがノードから見た接続元がすべて
  ハブになるため、IP でのBAN等ができなくなる)

## 次のステップ

- [x] `git init` してリモート(GitHub 等)に push — **ArgoCD が参照できるリポジトリであることが前提条件**
- [x] 前提テーブルの値を確定(LAN CIDR のみ提案値。実測後 group_vars を更新)
- [x] terraform / ansible / kubernetes の各実装
- [ ] 実鍵の生成(age 鍵 3種、wg 鍵、GitHub deploy key)→ 管理者向けドキュメント(docs/content/docs/admin/)
- [ ] 実機適用(管理者向けドキュメント(docs/content/docs/admin/) の手順に従う)
