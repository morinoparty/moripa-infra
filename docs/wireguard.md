# WireGuard 設計

## 目的

1. 6台のノードの**外向き通信を Linode の固定IPから出す**(自宅回線のIPを晒さない)
2. 外部からのアクセスを Linode で受けて **DNAT でノードへ転送**(サービス公開)
3. 管理用の踏み台経路(ssh over wg)

これは **Cilium のノード間 WireGuard 暗号化(`encryption.type=wireguard`)とは別物**。
あちらはクラスタ内 Pod 通信の暗号化で、このトンネルは南北(external)トラフィック用。
混同しないこと(併用は可能)。

## トポロジ: hub-and-spoke

| ホスト | wg アドレス | 役割 |
|---|---|---|
| linode-gw | 10.100.0.1/24 | ハブ。ListenPort 51820。IP forward + masquerade |
| node1–6 | 10.100.0.11–16/32 | spoke。NAT 裏なので `PersistentKeepalive = 25` |

ノード同士は wg 経由で通信**しない**(同一LANで直接通信)。ハブ側の
AllowedIPs は各 peer の /32 のみ。

## 最重要の設計制約: k8s トラフィックをトンネルに乗せない

ノード側を安易に `AllowedIPs = 0.0.0.0/0` にすると、etcd・kubelet・Pod間通信まで
$5 VPS 経由になりクラスタが実用にならない。ただし **wg-quick のフルトンネル機構は
これを自然に回避できる**:

- wg-quick は `0.0.0.0/0` 指定時、default route の差し替えではなく
  **fwmark + ポリシールーティング**(table 51820 + `suppress_prefixlength 0` ルール)を使う
- `suppress_prefixlength 0` により、**main テーブルにより具体的な経路があれば
  そちらが勝つ**。つまり:
  - LAN 内ノード間通信 → connected route (`192.168.1.0/24 dev eth0`) が勝つ → 直接通信
  - Pod CIDR → Cilium が main テーブルに入れる経路(native routing)、または
    VXLAN 外側パケットがノードIP宛(= LAN 経路)になる → 直接通信
  - それ以外の外向き → table 51820 の default → wg0 経由

依存関係として明示しておく: **「ノード間トラフィックが LAN に留まる」ことが
Pod MTU に影響が出ない条件**。もしノードが別セグメントに分散したら MTU と
経路設計を見直すこと。

安全側に倒すため、spoke 設定には LAN / Pod / Service CIDR の除外経路を
PostUp で明示的にも入れておく(冪等なので二重でも害はない)。

## MTU

- `wg0` は **MTU 1420** (1500 − 80: WireGuard オーバーヘッド + 余裕)
- クラスタ内(Cilium)の MTU はトンネルを通らないため影響なし(上記の依存関係参照)

## 設定サンプル

### ハブ (Linode) — `/etc/wireguard/wg0.conf`

```ini
[Interface]
Address    = 10.100.0.1/24
ListenPort = 51820
PrivateKey = <sops で管理>
MTU        = 1420

[Peer]  # node1
PublicKey  = <node1 pubkey>
AllowedIPs = 10.100.0.11/32

# ... node2–6 同様 (Ansible テンプレートで生成)
```

nftables (抜粋、Ansible の `wireguard` ロールで管理):

```nft
table inet nat {
  chain postrouting {
    type nat hook postrouting priority srcnat;
    oifname "eth0" ip saddr 10.100.0.0/24 masquerade
  }
  chain prerouting {
    type nat hook prerouting priority dstnat;
    # 例: Minecraft を node1 へ公開
    iifname "eth0" tcp dport 25565 dnat ip to 10.100.0.11:25565
  }
}
```

`sysctl net.ipv4.ip_forward=1` を忘れない。

### spoke (各ノード) — `/etc/wireguard/wg0.conf`

```ini
[Interface]
Address    = 10.100.0.11/32
PrivateKey = <sops で管理>
MTU        = 1420
# フルトンネル時に wg-quick が fwmark + policy routing を設定する
# 念のため k8s / LAN 向けを main テーブル経由に明示固定
PostUp   = ip rule add to 192.168.1.0/24 lookup main priority 100
PostUp   = ip rule add to 10.244.0.0/16  lookup main priority 100
PostUp   = ip rule add to 10.96.0.0/12   lookup main priority 100
PostDown = ip rule del to 192.168.1.0/24 lookup main priority 100
PostDown = ip rule del to 10.244.0.0/16  lookup main priority 100
PostDown = ip rule del to 10.96.0.0/12   lookup main priority 100

[Peer]  # linode-gw
PublicKey           = <gw pubkey>
Endpoint            = <linode public ip>:51820
AllowedIPs          = 0.0.0.0/0
PersistentKeepalive = 25
```

## 鍵の管理

- 秘密鍵は **sops + age** で暗号化して `ansible/group_vars/` に格納
  (`wg genkey` で生成、公開鍵は平文でよい)
- age の受信者鍵は管理者の鍵 + CI 用の鍵。k8s 側の Secret にも同じ sops 運用を
  使えるので、ArgoCD 導入後も方式を統一できる

## 運用メモ

- spoke は NAT 裏のため keepalive 必須。ハブ再起動後も spoke 側から再接続される
- 疎通確認: `wg show` で latest handshake、`ping 10.100.0.1`、
  `curl ifconfig.me` が Linode の IP を返すこと
- **クラスタ健全性の確認**: `ip route get <他ノードのLAN IP>` が `dev eth0`
  (LAN 直通)を返すことをセットアップ後に必ず確認する
