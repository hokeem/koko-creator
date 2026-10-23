# Agent handoff: Koko Creator

Read `README.md`, `render.yaml`, and relevant functions/tests before modifying code. The public portal is this repository; the internal content center is [hokeem/koko-kwai-coach](https://github.com/hokeem/koko-kwai-coach). Do not assume an old PRD or a local seed cache reflects production.

## Boundaries and invariants

- `app.py` contains the HTTP server, HTML/JS UI, auth, script sync, analytics, and submission logic. `page_html()` generates much of the mobile experience. A backend change and its browser behavior often need to be changed together.
- That browser JavaScript is embedded in Python f-strings. Preserve doubled braces and interpolation; render `page_html()` and syntax-check the extracted scripts after an edit, not just `python3 -m py_compile`.
- Content center `/api/library` is the upstream script source. Creator keeps a disk cache at `DATA_DIR/creator_online_library.json` and has manual entries/overrides. Check upstream publication, Telekwai, reference-video setting, cache/sync, and recommendation filtering in order.
- Creator owns accounts, profiles, analytics, submissions, and their review state under `DATA_DIR`. The content center's `/api/creator-admin/...` is a proxy to this service's `/api/admin/...`, not a separate source of truth. Avoid writing only to a content-center cache to "fix" author data.
- Every new return is `pending_review`. Approval is an explicit admin action; rejection must retain a visible reason. Only `approved` submissions count for the top reward progress and wallet. Never auto-approve a backlog or treat a submitted URL as proof of a remake.
- Authentication, creator cookies, admin cookies, and campaign attribution are distinct. A page visit is not a registered creator. Aggregate visits and account-linked events separately; do not fabricate identity for unidentified visits.
- The `888` account deliberately replays onboarding on login. Keep test-account behavior isolated from real creators and do not use production data mutations for smoke tests.

## Working safely

1. Check `git status` and use a clean clone/worktree if the current checkout contains user changes. Do not reset or overwrite unrelated work.
2. For code edits run `python3 -m unittest discover -s tests`. For `page_html()` changes, render the returned HTML, syntax-check the extracted JavaScript, and test the actual mobile browser flow. Check portal, a script detail, account state, and any changed reward/submission behavior.
3. Test against isolated `DATA_DIR`; never copy or mutate production `/var/data` for development. Validate existing records and migrations before changing JSON shapes. The Render disk is not in Git; back it up before data migration.
4. Coordinate cross-service releases. If a new content-center proxy needs a new Creator API, deploy and verify Creator first. Confirm the Render deployment finished; check `/healthz`, `/creator-portal`, a changed script or account view, and the relevant read-only API on the live domain. A successful Git push is not enough. Do not create/approve/reject real submissions only to prove a deployment.
5. Report changed files, tests, production verification, and unresolved risks. If a live service returns 502, distinguish platform availability, upstream failures, disk pressure, and frontend render errors with evidence.

Do not include credentials or personal creator data in prompts, docs, tests, logs, or commits. Use secret env vars and least-privilege access. Existing fallback admin-secret values in code are security debt, not a template for new work.
