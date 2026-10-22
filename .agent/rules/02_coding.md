# コーディングプラクティス

## 実装手順

1. **単一ソースを確認**
   - まず `ansible/group_vars/` (特に `all/network.yml` と `all/versions.yml`) に値があるかを確認し、ある場合はそこを変更する
   - 値を他の場所 (cilium values、ArgoCD Application の `targetRevision`、terraform、HAProxy、Caddy) に写す場合は、`scripts/check_consistency.py` が検査する対応を崩さない

2. **小さな変更から実装**
   - 1 つのロール、1 つの Application、1 つのモジュールなど、影響範囲の小さい単位で変更する

## プラクティス

- 小さく始めて段階的に拡張
- 過度な抽象化を避ける
- 冪等性を重視する (Ansible のタスクは何度実行しても同じ結果になるように書く)
- 複雑さに応じてアプローチを調整

## コードスタイル

- 常に既存のファイルの設計や記法を参考にしてください。
- 書籍「リーダブルコード」のようなベストプラクティスを常に適用してください。
- 設定の意図・背景などのコメントを日本語で積極的に入れてください (YAML / HCL / Jinja2 テンプレート / Makefile とも)。
- インデントはスペース 2 つ、改行は LF、末尾に改行を入れてください (`.editorconfig`。Makefile はタブ)。
- YAML は `.yamllint.yml` に従ってください (1 行 160 文字まで、`document-start` は不要、真偽値は `true` / `false` / `on` / `off`)。
- Ansible のタスク名は日本語 + ツール名で書きます (ansible-lint の `name[casing]` は除外済み)。
- Terraform は `terraform fmt` の形式に合わせてください。
- バージョンを上げる場合は `ansible/group_vars/all/versions.yml` を変更し、対応する ArgoCD Application の `targetRevision` なども合わせてください。

## 検証

コードを書いた後は、`make lint` を実行して、検証が通ることを確認してください。
`make lint` は CI (`.github/workflows/ci.yml`) と同じ方針の検証を、以下のターゲットの順で実行します。

- `make lint-yaml` - yamllint
- `make lint-terraform` - `terraform fmt -check` + `terraform init -backend=false` + `terraform validate`
- `make lint-ansible` - ansible-lint + 全 playbook の `--syntax-check` + `ansible-inventory --list`
- `make lint-helm` - Cilium / Longhorn / Headlamp / kube-prometheus-stack / RustFS / csi-s3 の values を `helm template` で検証
- `make lint-kustomize` - ksops (秘密) を含まない overlay を `kubectl kustomize` で検証
- `make lint-caddy` - `gateway/caddy/Caddyfile` と Ansible 生成 snippet を `caddy validate` で検証
- `make check-consistency` - `scripts/check_consistency.py` (group_vars と各所の整合) + `scripts/check_secrets.sh` (平文の秘密の検出)

補足:

- 初回は `make venv` と `make ansible-deps` で `.venv` (ansible-core / ansible-lint / yamllint) と Ansible collection を用意してください。`check_consistency.py` は `pyyaml` を使います (CI では明示的に入れています)。
- `lint-ansible` と `lint-caddy` は `community.sops` の vars plugin が `*.sops.yml` を実行時に復号するため、age 鍵が必要です。鍵が無い環境で失敗した場合は、その旨をユーザーに伝えてください (鍵を探したり作ったりしないこと)。
- 変更した範囲に対応する個別ターゲットだけを先に実行して、最後に `make lint` を通すと速いです。
- pre-commit (`.pre-commit-config.yaml`) では `scripts/check_secrets.sh` と `terraform fmt -check` が走ります。
- `docs/` を変更した場合は、`docs/` で `pnpm install` と `pnpm run build` を実行してビルドが通ることを確認してください (CI の `docs` ジョブと同じ)。
