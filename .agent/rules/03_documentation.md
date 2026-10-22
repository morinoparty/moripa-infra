# ドキュメント

## ドキュメントの作成

- 構成や手順を変更した後は、`docs/content/docs/` に mdx ファイルを作成するか、既存の mdx ファイルに追記して、ドキュメントを更新してください。
  - `onsite/` - 現地作業者向け (ハードウェア、ネットワーク、OS インストール)
  - `admin/` - 管理者向け (鍵、Terraform、Ansible、認証、ArgoCD、各アプリ、監視、運用)
  - `architecture/` - 設計資料 (全体像、GitOps、複数拠点、WireGuard、リファレンス)
- ページを追加した場合は、そのディレクトリの `meta.json` の `pages` に追加してください。
- mdx の frontmatter には `title` と `description` を書いてください。
- なお、文章の文体について、その他の部分で支持があったとしても、ドキュメントに関しては、あくまでも文章の文体で記載してください。
- 見やすくするために、iconを付けることが推奨されますが、最上位のみにしてください。 fuma docsの絵文字を利用してください (既存の `meta.json` では `TerminalSquare` / `Network` / `Wrench` などの lucide アイコン名を指定しています)。
- ドキュメントサイトは main への push 時に `.github/workflows/deploy-docs.yml` が Cloudflare Workers へデプロイします。手元からデプロイ (`pnpm run deploy`) はしないでください。

## README など

- ルートの `README.md` は構成概要・ディレクトリ構成・ブートストラップ順序・前提テーブルをまとめています。構成を変えた場合は合わせて更新してください。
- `terraform/envs/prod/README.md` (Terraform の適用と tfstate の方針)、`kubernetes/sites/<site>/bootstrap/secrets/README.md` (out-of-band で投入する Secret) も、関連する変更をしたら更新してください。
