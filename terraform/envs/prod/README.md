# prod 環境

## 適用

```sh
export LINODE_TOKEN=...
make tf-init tf-plan tf-apply   # リポジトリルートから
make tf-output                  # public_ip を ansible/group_vars/all/network.yml へ転記
```

`image = "linode/ubuntu26.04"` は apply 前に `linode-cli images list` で存在確認すること。

## tfstate の方針

**ローカル state + gitignore**(コミット禁止)。管理者1人・リソースは
Nanode 1台 + Firewall 1個のみで、リモート state は現状過剰なため。
state に秘密は入らない(トークンは env、WireGuard 鍵は Terraform 非管理)。

複数人運用になったら移行する。候補:

- Linode Object Storage(S3 互換 backend。`skip_credentials_validation = true`
  等のフラグ指定が必要)
- HCP Terraform (free tier)

`.terraform.lock.hcl` はコミット対象(プロバイダのバージョン固定)。
