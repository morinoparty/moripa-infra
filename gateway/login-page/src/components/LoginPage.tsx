import { Github, Pickaxe } from "lucide-react";
import { css } from "styled-system/css";
import logo from "../assets/logo.svg";
import { startUrl } from "../destination";
import { CoverPanel } from "./CoverPanel";
import { ProviderOption } from "./ProviderOption";

interface LoginPageProps {
  /** ログイン後に戻る URL */
  destination: string | null;
}

/**
 * *.private.dev.morino.party のログイン選択画面。
 * 左にログイン方法、右にカバー画像を並べる（狭い画面ではカバーを出さない）
 */
export const LoginPage = ({ destination }: LoginPageProps) => (
  <div
    className={css({
      display: "grid",
      gridTemplateColumns: { base: "1fr", lg: "minmax(0, 1fr) minmax(0, 1fr)" },
      minHeight: "100dvh",
      bg: "bg.panel",
    })}
  >
    <main className={css({ display: "flex", alignItems: "center", justifyContent: "center", px: { base: "6", md: "12" }, py: { base: "10", md: "12" } })}>
      <div className={css({ width: "full", maxWidth: "md", display: "flex", flexDirection: "column", gap: "8" })}>
        <header className={css({ display: "flex", alignItems: "center", gap: "2.5" })}>
          <img src={logo} alt="" className={css({ height: "9", width: "auto" })} />
          <span className={css({ textStyle: "lg", fontWeight: "bold", color: "colorPalette.fg" })}>morino.party</span>
        </header>

        <div className={css({ display: "flex", flexDirection: "column", gap: "3" })}>
          <h1 className={css({ textStyle: "3xl", fontWeight: "bold", color: "colorPalette.12" })}>ログイン</h1>
          <p className={css({ textStyle: "md", color: "fg.muted" })}>内部向けのページです。どちらか一方の条件を満たせば入れます。</p>
          {destination && (
            <p className={css({ textStyle: "sm", color: "fg.muted", overflowWrap: "anywhere" })}>
              移動先: <code className={css({ fontFamily: "mono", color: "colorPalette.fg" })}>{destination}</code>
            </p>
          )}
        </div>

        <div className={css({ display: "flex", flexDirection: "column", gap: "5" })}>
          <ProviderOption
            href={startUrl("mineauth", destination)}
            icon={<Pickaxe aria-hidden />}
            label="MineAuth でログイン"
            requirement="staff ロールを持つプレイヤー"
            intent="primary"
          />
          <ProviderOption
            href={startUrl("github", destination)}
            icon={<Github aria-hidden />}
            label="GitHub でログイン"
            requirement="morinoparty org のメンバー"
            intent="secondary"
          />
        </div>
      </div>
    </main>

    {/* カバーは装飾なので支援技術からは隠し、スクロールしても画面に留める */}
    <aside aria-hidden className={css({ display: { base: "none", lg: "block" }, position: "sticky", top: "0", height: "100dvh" })}>
      <CoverPanel />
    </aside>
  </div>
);
