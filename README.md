# Flowset

Flowset helps worship leaders find songs with similar chord movement as a starting point for planning transitions and mashups. Search by song, artist, or chord progression; compare matching song sections across keys. Saved setlists and a complete transition-planning workflow are still planned.

## Open the current app locally

Use Node.js **24** and run this from the project folder in PowerShell:

```powershell
.\start-flowset.ps1
```

Open `http://localhost:3001` and leave the terminal open. Press Ctrl+C to stop. Use `-Port 3002` if the default port is occupied. The shortcut installs the locked development dependencies if needed and starts Vercel's local runtime, which runs the same JavaScript API files used on the website. It does not rebuild the song database.

The first setup needs a Vercel login with access to the existing Flowset project. If the login expires, run these commands, approve the browser sign-in, and retry the shortcut:

```powershell
cd apps/worship-progressions-app-experimental
node node_modules/vercel/dist/vc.js login
```

For a fresh checkout, first run `npm.cmd ci --ignore-scripts` in that app folder. Link that folder to the existing `worship-progressions-app-experimental` project in `robrhapsodys-projects` with `node node_modules/vercel/dist/vc.js link`. The project requires development environment variables `SUPABASE_URL` and `SUPABASE_ANON_KEY`. Use the public anon key, not a service-role key. Local `.env*` files and Vercel settings are ignored by Git; never commit credentials. The old `-UseSupabase` launcher flag has been removed because the current app always uses this API path.

## Source and hosting

- Current app: `apps/worship-progressions-app-experimental/` (the folder name is historical).
- UI: `index.html`, `app.js`, `styles.css`; server functions: `api/`.
- Repository: [robrhapsody/melodex-site](https://github.com/robrhapsody/melodex-site).
- Website: [Flowset](https://worship-progressions-app-experiment.vercel.app).
- Current source branch: `main`. [PR #1](https://github.com/robrhapsody/melodex-site/pull/1) merged `codex/flowset-baseline`, combining the previous histories without discarding either.
- Hosting uses Node 24, no framework/build command, and no Git integration as checked September 12. Deployments have been made from the app folder, not the repository root. Pushing a branch does not currently deploy the site.

The September live deployment was created from a working tree with uncommitted changes, so its commit label alone cannot reproduce it. The local HTML, app JavaScript, and stylesheet were compared with live files and match after normalizing line endings. See the checkpoint for the exact deployment identifier and remaining backend provenance limitation.

`server.py`, `server.js`, the other app folders, and Antigravity snapshots are historical references. They are not the supported route for opening the current app. Data-processing scripts remain separate from running Flowset.

## Checks

From the current app folder:

```powershell
npm.cmd run check
npm.cmd test
```

These check JavaScript syntax and run all 24 existing matching/input tests without database credentials. The `Flowset checks` GitHub workflow runs them on pushes and pull requests. They are basic regression checks, not proof that recommendations are musically correct.

The `Supabase Keepalive` workflow checks the public database-backed stats endpoint twice daily. It was re-enabled and successfully run on September 12. GitHub may disable scheduled workflows after repository inactivity; check Actions when resuming after a long break. The separate Vercel daily keepalive configuration is retained.

## Resume safely

Read the [step-one checkpoint](docs/thread-memory-checkpoint-2026-09-12-step-1.md) first, then the [full reassessment](docs/thread-memory-checkpoint-2026-09-12-flowset-reassessment.md) for product intent, implemented features, unfinished work, and known correctness defects.
