# 非秘密の値のみ(トークンは LINODE_TOKEN 環境変数)
admin_ssh_keys = [
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPU9TKqjEA+vskebF8GVZiLc4V9s3BGbA07B9E15WdKX nikomaru@linode-dev", # 管理者マシン(秘密鍵 ~/.ssh/id_ed25519_linode)
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICS6zP54bvSBtyML1Ap87RSkahT4CfG5ye7Wn16Xlyjw",                     # 管理者の Windows 機
]

# 初回ブートストラップ時に管理者の現IPを入れる(例: "203.0.113.5/32")。
# wg 確立後は [] に戻して再 apply し、公開 SSH を閉じる
bootstrap_ssh_cidrs = [] # 定常。wg 経由の SSH を確認済みなので公開 22 は閉じる
