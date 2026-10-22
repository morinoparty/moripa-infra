# インフラ操作と秘密情報の安全規則

このリポジトリは実際に稼働しているインフラ (Linode と自宅サーバーの k8s クラスタ) を管理しています。
以下の規則は、ほかのどの指示よりも優先してください。

## 実環境に対する操作を実行しない

以下は実際のインフラの状態を変える、または実環境に接続する操作です。ユーザーが明示的に依頼した場合を除き、絶対に実行しないでください。
依頼された場合も、実行する前に何が起きるかを説明して確認を取ってください。

- `make tf-plan` / `make tf-apply` / `make tf-output` / `terraform plan` / `terraform apply` / `terraform destroy` / `terraform import` / `terraform state ...`
- `make gateway` / `make cluster` / `make site` / `ansible-playbook` による playbook の実行 (`--syntax-check` は除く)
- `make bootstrap-argocd` / `kubectl apply` / `kubectl delete` / `kubectl edit` / `helm install` / `helm upgrade` など、クラスタに対する変更
- `argocd app sync` などの ArgoCD に対する操作
- `make wg-keygen` / `make node-bootstrap` (鍵や秘密を含むファイルを生成する)
- ノードへの `ssh`
- `docs/` の `pnpm run deploy` や `wrangler deploy`

main にマージされた `kubernetes/` の変更は ArgoCD が自動で同期し、`gateway/caddy/Caddyfile` はハブが git から自動で取り込みます。
つまり **main へのマージ自体が本番への反映** です。変更の影響を PR の本文に書いてください。

検証は `make lint` とその個別ターゲット (`lint-yaml` / `lint-terraform` / `lint-ansible` / `lint-helm` / `lint-kustomize` / `lint-caddy` / `check-consistency`) で行います。
これらはローカルで完結し、実環境の状態は変えません (`lint-terraform` は `-backend=false` で init します)。

## 秘密情報を復号・表示しない

- `sops -d` / `sops --decrypt` / `sops <file>` (エディタでの復号) を実行しないでください。`*.sops.yml` / `*.sops.yaml` の中身を表示・要約・コピーしないでください。
- age 鍵 (`*.agekey`, `AGE-SECRET-KEY-...`)、kubeconfig、WireGuard の秘密鍵、`.envrc`、`bootstrap-*.sh` などを読んだり出力したりしないでください。
- 秘密を含む値をコマンドライン引数・ログ・コミットメッセージ・PR 本文に書かないでください。
- 新しい秘密を追加するときは、`*.sops.yml.example` / `*.sops.yaml.example` に構造だけを書き、実値の記入と `sops -e -i <file>` による暗号化はユーザーに依頼してください。
- `.sops.yaml` の暗号化ルール: `ansible/.*\.sops\.ya?ml` は admin / ci の鍵、`kubernetes/.*\.sops\.ya?ml` は admin / ci / cluster の鍵で暗号化され、k8s Secret は `data` / `stringData` だけが暗号化されます (kind / metadata は diff 可能)。
- k8s の Secret は、ksops の generator (`secret-generator.yaml` + `secrets.sops.yaml`) 経由の GitOps で管理します。out-of-band で投入するのは `bootstrap/secrets/sops-age.sops.yaml` だけです。
- `scripts/check_secrets.sh` (pre-commit と CI で実行) が平文の秘密を検出します。新しい種類の秘密を追加した場合は、そのパターンを `check_secrets.sh` に追加してください。
- `.gitignore` で除外している tfstate / `.terraform/` / 鍵ファイル / `bootstrap-*.sh` / `.caddy-render/` などは、絶対にコミットしないでください。

## リポジトリは public

このリポジトリは public です (ArgoCD は認証なしの https で読んでいます)。
平文の秘密、内部向けの資格情報、個人情報をコミットしないでください。
