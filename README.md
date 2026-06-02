# Koko Creator Portal

Standalone creator-facing script recommendation portal for Brazilian creators.

## Local run

```bash
python3 app.py
```

Open:

```text
http://localhost:10000
```

## Render

Create a new Render Web Service from this repository. The included `render.yaml`
creates a service named `koko` with a persistent disk mounted at `/var/data`.

Important: this is a standalone service and should not be connected to the
existing Koko production Render service.

## Data

- Script library cache: `DATA_DIR/creator_online_library.json`
- Creator submissions: `DATA_DIR/creator_submissions.json`
- Thumbnail cache: `DATA_DIR/creator_thumbnail_cache.json`

The service syncs the script library from `CREATOR_LIBRARY_SOURCE_URL` every
24 hours by default. A seed cache is included under `data/` so the portal can
start even if the source is temporarily unavailable.
