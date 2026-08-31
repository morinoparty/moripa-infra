# bootstrap secrets

ArgoCD が repo を読めるようになる**前**に必要な Secret(現在は1つ)。
構造的に GitOps 経路に乗せられないため、`make bootstrap-argocd SITE=<site>` が
`sops -d | kubectl apply` で out-of-band 投入する。**これ以外の Secret は
すべて ksops 経由(GitOps)で管理すること。**

- `sops-age`: cluster 用 age 鍵(ksops の復号用)。**両拠点で共有**する
  (単一管理者の運用ではサイト別鍵の分離メリットより運用の単純さを優先)。
  したがって site1/site2 の secrets の中身は同一でよい(ファイルは各サイトに置く)

リポジトリは public のため、repo アクセスは認証なしの https
(`https://github.com/morinoparty/moripa-infra.git`)で行い、deploy key は
使わない。**リポジトリを private に戻す場合は、read-only deploy key を作成し
`argocd.argoproj.io/secret-type: repository` の Secret(sshPrivateKey +
`git@github.com:...` URL)を復活させ、全 Application の repoURL を SSH 形式に
戻すこと。**

## 作成手順

```sh
# 1. example をコピーして実値を記入
cp sops-age.sops.yaml.example sops-age.sops.yaml
#    - sops-age: age-cluster.agekey の秘密部(AGE-SECRET-KEY-...)

# 2. その場で暗号化(平文のまま commit しないこと!)
sops -e -i sops-age.sops.yaml
```

`.sops.yaml`(リポジトリルート)の `encrypted_regex` により
data/stringData のみ暗号化され、kind/metadata は diff 可能なまま残る。
pre-commit フックが平文の `AGE-SECRET-KEY` / `PRIVATE KEY` を検出する。
