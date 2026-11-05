/** ログインに使える provider（Caddy の /oauth2/<name>/* と対応する） */
export type Provider = "mineauth" | "github";

/**
 * Caddy がリダイレクト時に付けた移動先（?rd=<元の URL>）を読み取る。
 * 許可ドメインの検査は oauth2-proxy が行うので、ここでは検証しない
 *
 * @param search location.search の値
 */
export const readDestination = (search: string): string | null => new URLSearchParams(search).get("rd") || null;

/**
 * provider のログイン開始 URL を返す。ログイン後に元の URL へ戻れるよう rd を引き継ぐ
 *
 * @param provider ログインに使う provider
 * @param destination 移動先。無ければ rd を付けない
 */
export const startUrl = (provider: Provider, destination: string | null): string => {
  const path = `/oauth2/${provider}/start`;
  return destination ? `${path}?rd=${encodeURIComponent(destination)}` : path;
};
