# moripa-infra

自宅サーバー6台 + Linode Nanode(踏み台/出口ゲートウェイ) のインフラ管理モノレポ。

- **Terraform**: Linode リソース(Nanode, Firewall)のプロビジョニング
- **Ansible**: 6台のサーバーの構成管理(WireGuard, k8s ブートストラップ)
- **kubernetes/**: ArgoCD が監視する GitOps マニフェスト群

## 構成概要

```
[インターネット]
      │
[Linode Nanode]  ← WireGuard ハブ / 出口 (10.100.0.1)
      │ wg0 (hub-and-spoke)
      ├── node1 (10.100.0.11) ┐
      ├── node2 (10.100.0.12) │
      ├── node3 (10.100.0.13) │  自宅LAN上の k8s クラスタ
      ├── node4 (10.100.0.14) │  (kubeadm + Cilium + ArgoCD)
      ├── node5 (10.100.0.15) │
      └── node6 (10.100.0.16) ┘
```

- 各ノードの**外向き通信は Linode 経由**(フルトンネル)。外部からは Linode の固定IPに見える
- **ノード間通信(etcd / Pod / Service)は自宅LAN内で直接通信**し、トンネルを通らない
  → 詳細は [docs/wireguard.md](docs/wireguard.md)
- 外部公開はLinode 側の DNAT でトンネル越しにノードへ転送

## ディレクトリ構成

```
moripa-infra/
├── terraform/                  # Linode のプロビジョニング
│   ├── modules/
│   │   └── linode-gateway/     # Nanode + Firewall + cloud-init
│   └── envs/
│       └── prod/               # 実環境の tfvars / backend 設定
├── ansible/
│   ├── inventory/
│   │   └── hosts.yml           # gateway / k8s_control_plane / k8s_workers
│   ├── group_vars/             # WireGuard 鍵(sops暗号化), CIDR 定義など
│   ├── roles/
│   │   ├── base/               # 共通設定(ユーザー, sshd, sysctl, unattended-upgrades)
│   │   ├── wireguard/          # wg 設定配布(hub / spoke 両対応)
│   │   ├── k8s-prereq/         # containerd, kubeadm/kubelet, カーネルモジュール
│   │   └── k8s-bootstrap/      # kubeadm init/join (kube-proxy なし), Cilium Helm 投入
│   └── playbooks/
│       ├── site.yml
│       ├── gateway.yml         # Linode 側の設定
│       └── cluster.yml         # 6台のセットアップ
├── kubernetes/                 # ArgoCD が watch する領域
│   ├── bootstrap/              # ArgoCD 本体 + app-of-apps のルート Application
│   ├── infrastructure/         # クラスタ基盤 (ArgoCD 管理)
│   │   ├── cilium/             # ブートストラップ後に ArgoCD が引き取る
│   │   ├── cert-manager/
│   │   ├── ingress/
│   │   └── monitoring/
│   └── apps/                   # 各種アプリケーション
└── docs/
    └── wireguard.md            # WireGuard 設計の詳細
```

## ブートストラップ順序

ArgoCD は CNI のないクラスタでは動けないため、順序が重要:

1. **Terraform**: Linode Nanode 作成 (`terraform/envs/prod`)
2. **Ansible `gateway.yml`**: Linode に WireGuard ハブ + nftables (masquerade / DNAT) を設定
3. **Ansible `cluster.yml`**:
   1. `base` + `wireguard`: 各ノードを spoke として接続
   2. `k8s-prereq`: containerd / kubeadm 導入
   3. `k8s-bootstrap`: `kubeadm init --skip-phases=addon/kube-proxy` → 各ノード join
   4. Cilium を Helm で投入 (kube-proxy replacement 有効)
4. **ArgoCD 導入**: `kubernetes/bootstrap/` を適用し、app-of-apps を起動
5. 以降は ArgoCD が `kubernetes/infrastructure/` と `kubernetes/apps/` を同期。
   Cilium の Helm リリースも ArgoCD が引き取る(同じ values を使うこと)

## 前提・未確定事項

実際の値が確定したら `ansible/group_vars/` と本ドキュメントを更新すること。

| 項目 | 仮の値 | 備考 |
|---|---|---|
| ノードの OS | Ubuntu 24.04 LTS | 要確認 |
| 自宅 LAN CIDR | 192.168.1.0/24 | 6台が同一LANにいる前提。**この前提が崩れると WireGuard 設計の見直しが必要** |
| WireGuard CIDR | 10.100.0.0/24 | LAN / Pod / Service と重複しないこと |
| Pod CIDR | 10.244.0.0/16 | Cilium cluster-pool |
| Service CIDR | 10.96.0.0/12 | kubeadm デフォルト |
| 外部公開ポート | Minecraft (25565/tcp 等) | Linode 側 DNAT で定義 |
| 秘密情報の管理 | sops + age | Ansible vars と k8s Secret の両方で使える |

## 注意: Nanode の転送量上限

Nanode は **1TB/月** の転送量制限と共有1vCPU。フルトンネル構成では6台分の
外向き通信(イメージ pull, OS 更新, 公開サービスのトラフィック)がすべてここを通る。
超過しそうな場合は、egress は直接出す split-tunnel への切り替えを検討する
(inbound DNAT だけなら AllowedIPs を 10.100.0.0/24 に絞るだけで済む)。

## 次のステップ

- [ ] `git init` してリモート(GitHub 等)に push — **ArgoCD が参照できるリポジトリであることが前提条件**
- [ ] 前提テーブルの値を実際の値で確定
- [ ] terraform / ansible / kubernetes の各実装
