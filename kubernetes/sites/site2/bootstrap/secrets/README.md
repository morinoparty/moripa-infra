# bootstrap secrets

ArgoCD が repo を読めるようになる**前**に必要な2つの Secret。
構造的に GitOps 経路に乗せられないため、`make bootstrap-argocd SITE=<site>` が
`sops -d | kubectl apply` で out-of-band 投入する。**これ以外の Secret は
すべて ksops 経由(GitOps)で管理すること。**

鍵は**両拠点で共有**する(単一管理者の運用ではサイト別鍵の分離メリットより
運用の単純さを優先):

- cluster 用 age 鍵: 1つを両クラスタの repo-server に投入
- GitHub deploy key: 1つを両クラスタの repo Secret に使用(GitHub 側の登録も1回)

したがって site2/site2 の secrets の中身は同一でよい(ファイルは各サイトに置く)。

## 作成手順

```sh
# 1. example をコピーして実値を記入
cp sops-age.sops.yaml.example sops-age.sops.yaml
cp repo-moripa-infra.sops.yaml.example repo-moripa-infra.sops.yaml
#    - sops-age: age-cluster.agekey の秘密部(AGE-SECRET-KEY-...)
#    - repo-moripa-infra: GitHub read-only deploy key の秘密鍵

# 2. その場で暗号化(平文のまま commit しないこと!)
sops -e -i sops-age.sops.yaml
sops -e -i repo-moripa-infra.sops.yaml
```

`.sops.yaml`(リポジトリルート)の `encrypted_regex` により
data/stringData のみ暗号化され、kind/metadata は diff 可能なまま残る。
pre-commit フックが平文の `AGE-SECRET-KEY` / `PRIVATE KEY` を検出する。
