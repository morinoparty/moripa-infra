# 実機適用 runbook

ゼロから全環境を立ち上げる手順。各フェーズ末尾の ✅ 検証を通してから次へ進むこと。

## 0. 事前準備(鍵の生成)

```sh
make venv ansible-deps          # ローカルツール

# age 鍵 3種(admin / ci / cluster)を生成し、.sops.yaml のプレースホルダーを置換
age-keygen -o ~/keys/age-admin.agekey     # 公開鍵を .sops.yaml の &admin に
age-keygen -o ~/keys/age-ci.agekey        # 公開鍵を &ci に。秘密部は GitHub Actions Secrets (SOPS_AGE_KEY)
age-keygen -o ~/keys/age-cluster.agekey   # 公開鍵を &cluster に。秘密部は bootstrap 時に投入(§5)
export SOPS_AGE_KEY_FILE=~/keys/age-admin.agekey

# WireGuard 鍵(全7ホスト分)
for h in linode-gw site1-node{1..3} site2-node{1..3}; do make wg-keygen HOST=$h; done
# → 表示された公開鍵を ansible/host_vars/<host>/main.yml に記載(コミット対象)

# 管理者マシンの WireGuard peer 登録(重要: これを忘れると §6 で SSH を閉じた後
# ゲートウェイに入れなくなる。復旧は Linode の LISH コンソールのみ)
wg genkey | tee ~/keys/wg-admin.key | wg pubkey   # 公開鍵が表示される
# → 公開鍵を ansible/group_vars/all/network.yml の wg_extra_peers に登録
#    (allowed_ips: 10.100.0.100/32)。管理者マシン側の設定例:
#
#    # /etc/wireguard/wg0.conf(管理者マシン)
#    [Interface]
#    Address    = 10.100.0.100/32
#    PrivateKey = <~/keys/wg-admin.key の中身>
#    [Peer]
#    PublicKey           = <linode-gw の公開鍵>
#    Endpoint            = <linode public ip>:51820
#    AllowedIPs          = 10.100.0.0/24   # 管理経路のみ(フルトンネルにしない)
#    PersistentKeepalive = 25

# GitHub read-only deploy key(ArgoCD 用。両拠点で同じ鍵を共有 — 生成は1回)
ssh-keygen -t ed25519 -f /tmp/deploy_key -N "" -C argocd@moripa
# 公開鍵を GitHub repo Settings → Deploy keys に登録(read-only、1回)
# 秘密鍵を kubernetes/sites/site1/bootstrap/secrets/repo-moripa-infra.sops.yaml と
# site2 側の同名ファイルの sshPrivateKey に貼り、それぞれ `sops -e -i` で暗号化。
# cluster 用 age 鍵も同様に両サイトの sops-age.sops.yaml へ(共有方針は
# kubernetes/sites/site1/bootstrap/secrets/README.md 参照)。/tmp の鍵は shred で削除
```

`.sops.yaml` 更新後、既存の `*.sops.yml` があれば `sops updatekeys` で再暗号化。

## 1. Terraform(Linode)

```sh
export LINODE_TOKEN=...
# terraform/envs/prod/terraform.tfvars に ssh 公開鍵と bootstrap_ssh_cidrs(自分の現IP/32)を設定
make tf-init tf-plan tf-apply
make tf-output   # → gateway_public_ip を ansible/group_vars/all/network.yml へ転記
```

✅ `ssh moripa@<public_ip>` でログイン可、`cloud-init status` が done。

## 2. ゲートウェイ構成

```sh
make gateway
```

✅ Linode 上で `wg show`(peer 7台分)、`nft list ruleset`(masquerade / dnat / MSS clamp)。

## 3. ノード構成(WireGuard + k8s 前提)

前提: 各ノードに Ubuntu 26.04.1 を導入し、LAN 固定 IP
(site1: 192.168.10.11–13、site2: 192.168.20.11–13)と
ssh 公開鍵ログインを設定済みであること。

```sh
make cluster    # 両拠点を処理: base+wg → k8s_prereq → 拠点ごとに kubeadm init/join → cilium
```

wg 疎通(play の検証タスクでも自動確認):

- ✅ 各ノードで `curl ifconfig.me` = Linode の IP(フルトンネル)
- ✅ `ping 10.100.0.1` 成功、`wg show` の handshake が新しい
- ✅ `ip route get <同一拠点の他ノードIP>` が LAN NIC を返す(**クラスタ内は LAN 直通**)
- ✅ `ip rule` に priority 100 の除外(lan/pod/service)3本

k8s(**拠点ごとに確認**):

- ✅ `kubectl get nodes` で各クラスタ 3台 Ready(taint なし)
- ✅ VIP フェイルオーバー: 先頭ノードの kubelet を止めても VIP
  (site1: 192.168.10.10 / site2: 192.168.20.10)への ping と `kubectl` が継続
  (確認後 kubelet を戻す)
- ✅ `cilium status --wait` 全緑 / 任意で `cilium connectivity test`

## 4. 公開経路の確認

- ✅ 外部から `nc -vz <linode_ip> 25565`(Minecraft デプロイ後)
- ✅ `curl -v http://<linode_ip>`(Gateway 応答。ingress デプロイ後)
- ✅ アプリログでクライアントの**実IP**が見えること(SNAT されていない)
- ✅ Pod 内から大きな HTTPS レスポンスの取得(MSS clamp / MTU 検証)

## 5. ArgoCD bootstrap

**拠点ごとに実行する**(kubeconfig をその拠点のクラスタに向けてから):

```sh
# kubeconfig は各拠点の先頭CPの /etc/kubernetes/admin.conf を手元へ(server を VIP に)
KUBECONFIG=~/kube/site1 make bootstrap-argocd SITE=site1
KUBECONFIG=~/kube/site2 make bootstrap-argocd SITE=site2
```

内部で行われること(各拠点):
1. `kubectl apply -k kubernetes/sites/<site>/bootstrap/argocd`(ArgoCD 本体 + ksops パッチ)
2. age cluster 鍵 Secret(sops-age)を out-of-band 投入
3. repo 用 deploy key Secret を out-of-band 投入
4. root Application 適用 → app-of-apps がその拠点分を同期

- ✅ 各拠点で `kubectl -n argocd get applications` 全て Synced / Healthy
- ✅ **cilium Application の diff がゼロ**(Ansible が入れた Helm リリースを
  そのまま引き取れている)。diff が出る場合は values の乖離 → `make check-consistency`

## 6. 定常運用メモ

- SSH は wg 経由のみ: `ssh moripa@10.100.0.1`(gw)、`ssh moripa@10.100.0.11`(site1-node1)、
  `ssh moripa@10.100.0.21`(site2-node1)。
  **公開 SSH を閉じる前の必須確認**: §0 で管理者マシンを `wg_extra_peers` に登録し
  `make gateway` を再実行済みで、管理者マシンの wg0 から `ssh moripa@10.100.0.1`
  が通ること。確認後に Terraform の `bootstrap_ssh_cidrs` を空にして re-apply する
  (閉じた後に wg が壊れた場合の復旧は Linode の LISH コンソール)
- DNAT 先ノード(site1-node1)障害時: `network.yml` の `dnat_rules[].target` を
  別ノードの wg アドレスに変え `make gateway`。Minecraft は nodeSelector のピン先も
  同時に変更(対応関係は `make check-consistency` が検査する)
- VIP 全損時は Cilium agent の API 接続も落ちる(既存データプレーンは動き続ける)。
  復旧は control-plane の kubelet/kube-vip から
- wg 設定変更は syncconf で反映される。Interface 行の変更のみ計画 restart
- Nanode の転送量(1TB/月)を Linode ダッシュボードで月次確認
