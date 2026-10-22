# 推奨される書き方

## 設定値
- 同じ値を複数の場所に書く必要がある場合は、`ansible/group_vars/` を唯一の正とし、他の場所は `scripts/check_consistency.py` で整合を検査できるようにすることが推奨されます。新しく値を写す場所を増やしたら、`check_consistency.py` に検査を追加してください。
- バージョンは `ansible/group_vars/all/versions.yml` に固定し、確認した日付や出典をコメントで残すことが推奨されます。
- コンテナイメージは既存のアプリと同様に、タグではなくダイジェストなどで固定することが推奨されます。

## Ansible
- タスクは冪等に書いてください (`command` / `shell` を使う場合は `creates` / `changed_when` などで変更判定を明示する)。
- 秘密の変数は `*.sops.yml` に置き、`community.sops` の vars plugin による自動復号に任せてください。

## Kubernetes / ArgoCD
- Secret は ksops の generator 経由で GitOps 管理してください。`kubectl create secret` などの手作業は前提にしないでください。
- Application の順序は sync wave で制御しています (例: Gateway API CRDs は Cilium より先に同期)。新しい Application を追加するときは既存の wave を確認してください。
- Helm chart の values を変更したら `make lint-helm`、kustomize を変更したら `make lint-kustomize` で検証してください。

## Terraform
- `.terraform.lock.hcl` はコミット対象です。tfstate はコミットしないでください。
- プロバイダのトークンは環境変数 (`LINODE_TOKEN`) から渡し、ファイルに書かないでください。

## Test
- 検証の追加は、CI と `make lint` の両方に入れることが推奨されます (`Makefile` と `.github/workflows/ci.yml` は同じ方針で保ってください)。
