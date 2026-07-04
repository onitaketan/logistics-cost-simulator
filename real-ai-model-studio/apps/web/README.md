# @rams/web — Real AI Model Studio frontend

Next.js (App Router) + TypeScript. The UI holds **no compliance logic** — it
renders whatever the backend engine returns and disables actions the API would
reject anyway (defense in depth, never the enforcement point).

## Screens (docs/02_figma_wireframe_instructions.md)

| Route | Screen | Status |
|---|---|---|
| `/login` | Login | ✅ wired to `/auth/login` |
| `/` | Dashboard | 🟡 layout only |
| `/models` | Model List | ✅ wired to `/models` |
| `/compliance` | Compliance Check（3カラム判定） | ✅ wired to compliance-check |
| `/generation` | Generation Studio（生成ボタンは判定通過時のみ活性） | ✅ wired |
| `/projects` `/review` `/delivery` `/audit` `/settings` | — | 🟡 placeholder |

## Dev

```bash
pnpm install   # or npm install
pnpm dev       # http://localhost:3000  (expects API at NEXT_PUBLIC_API_BASE_URL)
```
