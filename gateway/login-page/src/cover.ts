/** カバー画像 1 枚の情報（cover/covers.json の images の要素） */
export interface CoverImage {
  /** cover/ からの相対パス、または絶対 URL */
  src: string;
  /** 読み込み中に表示するプレースホルダ */
  blurhash: string;
  width: number;
  height: number;
  /** CSS の object-position。省略時は中央 */
  position?: string;
}

/** cover/covers.json の形式 */
export interface CoverManifest {
  images: CoverImage[];
}

// ログイン選択画面はサイトのルートで配信され、カバー画像は gateway/caddy/www/cover/ から同じサーバーで配信される
const COVER_BASE_URL = new URL("cover/", window.location.href).href;
const MANIFEST_URL = new URL("covers.json", COVER_BASE_URL).href;

const isCoverImage = (value: unknown): value is CoverImage => {
  if (typeof value !== "object" || value === null) return false;
  const image = value as Record<string, unknown>;
  return (
    typeof image.src === "string" &&
    typeof image.blurhash === "string" &&
    typeof image.width === "number" &&
    typeof image.height === "number" &&
    (image.position === undefined || typeof image.position === "string")
  );
};

const isCoverManifest = (value: unknown): value is CoverManifest => {
  if (typeof value !== "object" || value === null) return false;
  const manifest = value as Record<string, unknown>;
  return Array.isArray(manifest.images) && manifest.images.every(isCoverImage);
};

/**
 * マニフェストから 1 枚選ぶ。画像が無ければ null を返す
 *
 * @param manifest カバー画像の一覧
 * @param random 0 以上 1 未満の乱数
 */
export const pickCover = (manifest: CoverManifest, random: number): CoverImage | null =>
  manifest.images[Math.floor(random * manifest.images.length)] ?? null;

/** カバー画像の URL を返す */
export const coverUrl = (image: CoverImage): string => new URL(image.src, COVER_BASE_URL).href;

/**
 * カバー画像をランダムに 1 枚読み込む。
 * カバーは装飾なので、マニフェストが無い・壊れている場合は null を返し、グラデーションだけを表示する
 */
export const loadCover = async (): Promise<CoverImage | null> => {
  try {
    const response = await fetch(MANIFEST_URL);
    if (!response.ok) return null;
    const manifest: unknown = await response.json();
    return isCoverManifest(manifest) ? pickCover(manifest, Math.random()) : null;
  } catch {
    return null;
  }
};
