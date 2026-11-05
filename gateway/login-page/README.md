# Login Page

The login chooser page served at `auth.dev.morino.party`. It is built with React and `@morinoparty/chlorophyll-react`.

## Building

```bash
pnpm install
pnpm run build
```

The build writes a single self-contained `../caddy/www/index.html`. The hub only syncs `gateway/caddy/www` from git and does not run the build, so commit the generated file together with the source.

`pnpm dev` previews the page. Add `?rd=https://example.site1.private.dev.morino.party/` to the URL to display a destination.

## Cover Images

The page reads `gateway/caddy/www/cover/covers.json` and displays one image at random on screens at least 1024px wide. When the file or the image cannot be loaded, the page displays a gradient instead. The format is the same as the MineAuth authorization page template.
