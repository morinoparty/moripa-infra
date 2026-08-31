# 2拠点アーキテクチャ

本リポジトリは **2拠点・拠点ごとに独立した k8s クラスタ**を実装している。
このドキュメントはその設計判断と、拠点の追加・変更時の指針を記す。

## なぜ「1つのクラスタを2拠点に跨がせる」のではなく「独立クラスタ×2」なのか

- **etcd クォーラム**: 2拠点では過半数を持つ側が落ちるとクラスタ全体が停止する。
  タイブレーカーになる第3拠点がなく、対称な冗長化が原理的に不可能
  (Nanode は非力すぎて etcd メンバーには不適)
- **拠点間リンクへの依存**: 跨がせると etcd / API / Pod 通信が拠点間トンネルの
  品質に常時依存する。独立クラスタなら拠点間リンク断でも両拠点とも無傷
- **障害ドメインの分離**: ArgoCD も拠点ごとに持つ。片拠点が全損しても
  もう片方の GitOps は動き続ける

## 構成の要点

| 項目 | site1 | site2 |
|---|---|---|
| LAN CIDR | 192.168.10.0/24 | 192.168.20.0/24 |
| kube-vip VIP | 192.168.10.10 | 192.168.20.10 |
| wg アドレス | 10.100.0.11–13 | 10.100.0.21–23 |
| ノード | site1-node1〜3(全部CP) | site2-node1〜3(全部CP) |

- WireGuard は従来どおり **Linode をハブとする hub-and-spoke**。両拠点の全ノードが
  spoke であり、拠点間に直接トンネルは張らない(クラスタ間通信が無いため不要)
- ArgoCD は各クラスタが自分の分を self-host し、
  `kubernetes/common/`(共通ベース)+ `kubernetes/sites/<site>/`(サイト固有)を同期する
- 管理者は wg 経由で両拠点のノード・APIへ到達できる
  (kubeadm の certSANs に各ノードの wg アドレスを含めている)

## 重要な制約: Pod / Service CIDR は両拠点で同一値

10.244.0.0/16 / 10.96.0.0/12 を両クラスタで使い回している。
**クラスタ同士を接続しない前提でのみ成立する**。将来 Cilium Cluster Mesh や
クラスタ間の Pod 直接通信をやりたくなったら、これは設定変更ではなく
**片方のクラスタの再IP設計(実質作り直し)**になる。その予定が少しでもあるなら
先に site2 の CIDR をずらしておくこと(例: pod 10.245.0.0/16)。

## 公開サービスと拠点

Linode の `dnat_rules`(ansible/group_vars/all/network.yml)の `target` を
どの拠点のノードの wg アドレスにするかでサービスの提供拠点が決まる。
現状はすべて site1。site2 で公開するサービスは target を 10.100.0.2x にして
追加する。Minecraft のような eTP Local + node ピン構成では、
Pod の nodeSelector と dnat target の対応を check-consistency が検査する。

## 拠点を追加する場合(site3)

1. `ansible/inventory/hosts.yml` に site3 グループを追加(wg は 10.100.0.31– を採番)
2. `ansible/group_vars/site3.yml` を作成(lan_cidr / kube_vip_address / グループ名 / values パス)
3. `kubernetes/sites/site3/` を site2 からコピーして site 名を置換
4. `playbooks/cluster.yml` に site3 の CP play を追加
5. Makefile の KUSTOMIZE_DIRS、CI の kustomize リスト、
   `scripts/check_consistency.py` の SITES に site3 を追加
6. wg 鍵生成 → `make gateway`(hub の peer が増える)→ `make cluster`
   → `make bootstrap-argocd SITE=site3`

## 既存拠点のクラスタに worker を足す場合

inventory の `siteN_workers` にホストを追加して wg 鍵を生成し、
`make cluster` を再実行するだけ(join は冪等)。
