import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

/** この設定ファイルからの相対パスを絶対パスにする（@types/node を入れずに済むよう URL で解決する） */
const fromHere = (path: string) => decodeURIComponent(new URL(path, import.meta.url).pathname);

// ビルド結果は JS / CSS をすべてインライン化した 1 枚の index.html にする。
// ハブの caddy-gitops はビルドせず gateway/caddy/www を同期するだけなので、生成物もコミットする
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  resolve: {
    alias: {
      // Chlorophyll のコンポーネントは "styled-system/css" などを素の指定子で import する。
      // panda codegen が生成したこのプロジェクトの styled-system に向ける
      "styled-system": fromHere("./styled-system"),
      // Chlorophyll のコンポーネントを1つずつ読むための別名（理由は src/chlorophyll.ts）
      "chlorophyll-components": fromHere("./node_modules/@morinoparty/chlorophyll-react/src/components"),
    },
  },
  build: {
    outDir: "../caddy/www",
    // www/cover のカバー画像を消さない
    emptyOutDir: false,
  },
});
