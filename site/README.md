# Archeon marketing site

A self-contained static landing page for Archeon. No build step, no dependencies —
just three files:

| File | Purpose |
|------|---------|
| `index.html` | Page content and structure |
| `styles.css` | Design-token system (spacing, type, one accent) + all components |
| `main.js`   | Theme toggle, sticky-nav border, scroll reveals |

## Preview locally

Open `index.html` directly in a browser, or serve the folder:

```powershell
python -m http.server 8080 --directory site
# then open http://localhost:8080
```

## Deploy

Because it's plain static files, it works on any static host:

- **GitHub Pages** — Settings → Pages → deploy from `/site` (or copy to `/docs`).
- **Netlify / Vercel / Cloudflare Pages** — set the publish directory to `site`, no build command.

## Customizing

- **Rebrand the color** — change `--accent-h` (one hue) near the top of `styles.css`.
- **Dark mode** — automatic from the OS preference; the toggle in the nav overrides and
  remembers the choice in `localStorage`.
- **Content** — all copy lives in `index.html`; update the GitHub URLs if the repo moves.
