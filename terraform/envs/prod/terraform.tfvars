# 非秘密の値のみ(トークンは LINODE_TOKEN 環境変数)
admin_ssh_keys = [
  # "ssh-ed25519 AAAA... yahiro@morino.party",  # 実鍵に置き換えること
]

# 初回ブートストラップ時に管理者の現IPを入れる(例: "203.0.113.5/32")。
# wg 確立後は [] に戻して再 apply し、公開 SSH を閉じる
bootstrap_ssh_cidrs = []
