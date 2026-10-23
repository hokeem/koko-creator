# Koko Creator / kokocomedy.com

This repository serves the public, Portuguese-language creator experience for Brazilian Kwai creators. It is separate from the internal [Koko content center](https://github.com/hokeem/koko-kwai-coach). The two services have separate code, Render deployments, and persistent data disks.

## Current product flow

1. A visitor enters via a direct or campaign link, binds a Kwai profile or signs in, and completes content preferences and the first-use guide. The `888` account is a repeatable onboarding test account; do not treat its activity as a normal creator case.
2. The portal recommends eligible Portuguese scripts from a cached copy of the content center's library. A script must be published, effective, not Telekwai, and not have `reference_video_enabled` set to false to be recommended. A share link and a recommendation card are different visibility paths.
3. Creators can open a complete script, save it, plan filming, and submit a link to their own adapted/remade video. The original reference-video link is hidden from the author-facing script page; an identical reference-video URL is rejected at submission.
4. Each new submission starts as `pending_review`. The content center's [video review UI](https://koko-kwai-coach.onrender.com/koko_admin_2026-kwai/reviews) calls this service's admin API to approve or reject it, with a required rejection reason. The author's submission history shows status and reason. **Only `approved` submissions advance cash-reward progress and wallet estimates.**

## Code map

| Need | Start here |
| --- | --- |
| Mobile portal, recommendations, onboarding, profile, wallet | `app.py`: `page_html()` and embedded JavaScript |
| Authentication and Kwai profile binding | `app.py`: `/api/auth/kwai-link`, `/api/auth/login`, `/api/auth/register`, account helpers |
| Library sync and visibility | `app.py`: `sync_library()`, `is_creator_recommended()`, `load_entries()`, `/api/creator/scripts/...` |
| Submission validation and review | `app.py`: `save_submission()`, `review_submission()`, `/api/creator/submissions`, `/api/admin/submissions/review` |
| Campaign/usage analytics | `app.py`: analytics event helpers, `creator_campaign_dashboard_payload()` |
| Static images and signup assets | `static/` |
| Regression tests | `tests/` |

The June 2026 [`docs/koko-creator-prd.md`](docs/koko-creator-prd.md) is a historical proposal, not a current implementation inventory. In particular, its "not yet complete" section is outdated.

## Run and test

From the repository root, install `requirements.txt` and run `python3 -m unittest discover -s tests`. For local development use an isolated data directory, for example `PORT=10000 DATA_DIR=/tmp/koko-creator-dev python3 app.py`, then open `http://127.0.0.1:10000/creator-portal`. The default script source is the live content center; for a fully local two-service test, set `CREATOR_LIBRARY_SOURCE_URL` to the local content center's `/api/library`.

The repository [`render.yaml`](render.yaml) declares a service with `/var/data` and `/healthz`. Key configuration names include `DATA_DIR`, `CREATOR_LIBRARY_SOURCE_URL`, `PUBLIC_BASE_URL`, `KOKO_CREATOR_ADMIN_PASSWORD`, and `KOKO_ATTRIBUTION_SECRET`. Verify the actual service, branch, disk, environment variables, and domain in Render before deployment. Core files such as `creator_accounts.json`, `creator_profiles.json`, `creator_submissions.json`, and `creator_analytics_events.json` live under `DATA_DIR`; a Git clone alone cannot reproduce production state.

See [`AGENTS.md`](AGENTS.md) for change/deploy rules and cross-service checks.
