# 2拠点目への拡張パス(設計メモ)

現状は単一拠点(6台が同一LAN)。将来2拠点目に worker を追加する場合の
判断材料と必要な変更をここに残す。**実装は行っていない。**

## 原則

- **control-plane(etcd)は主拠点に3台固定のまま動かさない**。
  2拠点では etcd クォーラムのタイブレーカーが存在せず、対称な冗長化は不可能。
  拠点間リンク断のとき「主拠点だけでクラスタ生存、第2拠点の worker は
  NotReady になるだけ」という縮退が最も安全
- 第2拠点の台数を増やしすぎない(過半数の Pod が NotReady 側に寄ると縮退の意味がない)

## 必要な変更

### 1. 拠点間トンネル(Linode を経由しない)

第2拠点のノード間通信(kubelet→API、VXLAN)を Nanode 経由にしてはいけない
(1TB/月・共有1vCPU がクラスタ内トラフィックで即死する)。

- 拠点間に **site-to-site WireGuard(wg1)** を張る。どちらかの拠点に
  固定IP or DDNS + ポート開放が必要
- 両拠点とも開放不可の場合のみ Linode 中継を検討するが、その場合は
  Nanode のプラン増強が前提

### 2. ルーティングと MTU

- 「ノード間トラフィックは LAN 直通」という前提が崩れる:
  - spoke の `ip rule ... lookup main` 除外に**リモート拠点の LAN CIDR を追加**
  - wg1 経由の経路を main テーブルに追加(static route)
- **MTU**: 第2拠点向け VXLAN は wg1(MTU 1420)の内側を通るため、
  クラスタ全体の MTU を **1370**(1420 − VXLAN 50)へ引き下げる必要がある
  (Cilium の `MTU` 設定。全ノード再起動を伴う変更なので計画的に)
- Cilium は VXLAN トンネルモードなので、L2 が分かれても Pod 通信自体は動く
  (この将来性が VXLAN を選んだ理由の一つ)

### 3. Ansible / inventory

- `k8s_workers_site2` グループを追加し、`lan_cidr` / `lan_interface` を
  拠点別の group_vars に分離
- wireguard ロールに wg1(site-to-site)のテンプレートを追加

### 4. 公開経路

- DNAT 先を第2拠点のノードにする場合、経路は
  Linode → wg0 → 主拠点ノード…ではなく Linode → 第2拠点ノードの wg0 spoke
  で直接届く(hub-and-spoke のまま)。戻りもフルトンネルで対称
- ただし Minecraft の eTP Local + nodeSelector ピンの配置先は要再検討

## 判断チェックリスト(拡張前に確認)

- [ ] 拠点間の RTT と帯域(iperf3 / ping)。RTT > 20ms なら Pod 配置を拠点内で完結させる設計に
- [ ] どちらの拠点でポート開放できるか
- [ ] MTU 1370 への引き下げの影響範囲(全ノード)
- [ ] 第2拠点の障害時に許容できるサービス縮退の範囲
