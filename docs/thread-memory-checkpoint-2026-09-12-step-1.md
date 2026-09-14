# Flowset step-one checkpoint — 2026-09-12

## Resume and authorization

The user said to start step one and explain in language a non-coder can understand. This authorizes the baseline/source/runtime, CI, and keepalive work described in the reassessment. Step two (matching correctness changes) has not begun. Preserve unrelated local changes and datasets. The earlier reassessment's pending-approval statement is historical.

## Changes and evidence

- Created `codex/flowset-baseline`. Merge commit `db8e9da` combines `main` and `codex/publish-code-no-datasets` histories. Eight conflicts resolved by retaining the newer current app; the additional legacy API file from main was retained. No matching or frontend behavior was rewritten.
- Updated `start-flowset.ps1` and the app launcher to use the Vercel JavaScript runtime instead of the old Python server and automatic SQLite rebuild. Node 24 matches hosting. Pinned Vercel CLI 59.16.0 as a development dependency; lockfile records dependency resolution. `-UseSupabase` is removed; default port remains 3001.
- Added npm syntax/test commands and a GitHub `Flowset checks` workflow. All 24 existing Node tests pass locally. Workflow installs production dependencies only and needs no database secrets.
- Added bounded timeouts/retries to the scheduled stats check. Existing GitHub workflow 306328065 was disabled by inactivity; re-enabled through the authenticated GitHub API and dispatched on main. [Successful keepalive run](https://github.com/robrhapsody/melodex-site/actions/runs/34741126047).
- Added environment-file ignore rules. No credentials were committed. Existing Vercel cron configuration and unrelated local artifacts were preserved.
- Refreshed expired Vercel CLI login with user participation. Root launcher started successfully on `http://127.0.0.1:3001`.
- Browser verification: Flowset page and controls render, worship catalog reports 8,520 songs, progression `4 5 6m` returns 15 results including Holy Forever; browser error list was empty. Screenshot stored locally under the active app's ignored `.vercel/flowset-baseline-check.png`.
- Known missing-tempo display still shows 0 BPM; this is recorded in the reassessment and intentionally remains for step two. Search smoke success does not validate recommendation quality.

## Production baseline

Project `prj_UfWg96QJWEB4F6LsKnChcvytRxp6`, team `team_U6r3r0KnKPkVrxbBB53Os7qY`; alias `worship-progressions-app-experiment.vercel.app`.

Production deployment `dpl_9RR2Vr9KifsyrpwJzXfQm6diQTfQ`, URL `worship-progressions-app-experimental-r9289b3qz.vercel.app`, READY. Metadata names commit `d50f219e1d5a30b68cc2c4934ffbfbadd78c2925`, branch `codex/publish-code-no-datasets`, **gitDirty=1**, redeployed from `dpl_GsH3Lc3t4JrPFjndUxXpD8vXTP65`. This is not proof of an exact clean source revision.

Project settings: Node24.x, framework/devCommand/buildCommand/outputDirectory/rootDirectory all null, Git link null. Deployment working directory is the app directory. Git pushes therefore do not automatically deploy. No production deployment was made during this work.

Live `index.html`, `app.js`, `styles.css` each returned HTTP200 and match local files after CRLF normalization. SHA256 respectively:

- `1e55643d81579d2488cbd38b3f23cb93d73cdfcbd265055b33ae660030aa67fa`
- `95883e4580a8dd702a3ac677bfed0acc510a7fc5ed747b69ce2f3c06765022df`
- `9c885e32068b7acd4f2219972fc5c7bcb459592315084746921c5c3d8807d379`

Backend source bytes have not been compared with deployment source. A future clean, reviewed deployment should establish an exact commit-to-production link. Local browser search exercised the current JavaScript API against the existing Supabase database.

## Completion update — resumed September 13, 2026

Step-one baseline work is complete. [PR #1](https://github.com/robrhapsody/melodex-site/pull/1) merged into `main` as `3f642a840fe9b72756acd0abf6927823fe0a29e0`. The local checkout is now on main and includes that merge. The former integration branch remains available as history.

- [Main-branch Flowset checks passed](https://github.com/robrhapsody/melodex-site/actions/runs/34741402055), following the successful branch checks. All 24 existing tests passed locally and in CI.
- [A subsequent scheduled keepalive passed](https://github.com/robrhapsody/melodex-site/actions/runs/34775660613), in addition to the manual reactivation test. GitHub's existing Pages workflow also ran successfully; that legacy site is separate from the Vercel Flowset app.
- Local and live `/api/stats` returned identical JSON. Local and live `/api/search?catalog=worship_strict&progression=4%205%206m&limit=3` also returned identical JSON; all four requests returned HTTP200. This is sample behavior parity, not exhaustive backend identity verification.
- The main Flowset website was not redeployed. Its historical uncommitted-source limitation remains documented above; use a clean revision for the next intended production release.
- Final results are recorded in the companion Notion checkpoint, and the two step-one tasks are completed. The usage interruption occurred after the merge; recovery finished status/documentation updates without repeating implementation or browser tests.

Next is step two: correct minor-key representation and missing-metadata handling, then retrieval/input edge cases, and evaluate real musician-reviewed song examples. Step two has not started. See the [full reassessment](thread-memory-checkpoint-2026-09-12-flowset-reassessment.md) for the feature reconstruction, discrepancies, risks, and detailed next steps.
