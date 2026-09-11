import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import app


class CacheReclamationTests(unittest.TestCase):
    def test_oldest_rebuildable_cache_is_removed_when_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            thumbs = root / "thumbs"
            html = root / "html"
            thumbs.mkdir()
            html.mkdir()
            old = thumbs / "old.webp"
            new = html / "new.html"
            old.write_bytes(b"a" * 8)
            new.write_bytes(b"b" * 8)
            old_stat = old.stat()
            os.utime(old, (old_stat.st_atime - 10, old_stat.st_mtime - 10))

            with (
                patch.object(app, "DATA_ROOT", root),
                patch.object(app, "THUMB_IMAGE_CACHE_DIR", thumbs),
                patch.object(app, "SCRIPT_HTML_CACHE_DIR", html),
            ):
                removed = app.reclaim_rebuildable_cache_space(
                    min_free_bytes=0,
                    max_cache_bytes=8,
                )

            self.assertEqual(removed, 1)
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())

    def test_script_open_is_queued_without_sync_file_write(self) -> None:
        headers = {"User-Agent": "test"}
        script_id = "a" * 32
        with patch.object(app, "enqueue_analytics_events") as enqueue:
            visitor_id = app.record_site_open(headers, f"/script/{script_id}", script_id=script_id)

        self.assertTrue(visitor_id)
        events = enqueue.call_args.args[0]
        self.assertEqual([event["event"] for event in events], ["site_open", "script_open"])

    def test_force_cleanup_removes_rebuildable_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            thumbs = root / "creator_thumbnail_images"
            html = root / "creator_script_html_cache"
            thumbs.mkdir()
            html.mkdir()
            (thumbs / "cached.webp").write_bytes(b"a" * 16)
            (html / "cached.html").write_text("<p>cached</p>", "utf-8")
            (root / "creator_thumbnail_cache.json").write_text('{"bbbb": {"checked_at": "2026-01-01"}}', "utf-8")
            (root / "creator_video_source_cache.json").write_text('{"bbbb": {"checked_at": "2026-01-01"}}', "utf-8")
            entry_id = "a" * 32
            entries = [{"entry_id": entry_id, "title": "keep"}]

            with (
                patch.object(app, "DATA_ROOT", root),
                patch.object(app, "THUMB_IMAGE_CACHE_DIR", thumbs),
                patch.object(app, "SCRIPT_HTML_CACHE_DIR", html),
                patch.object(app, "THUMB_CACHE_FILE", root / "creator_thumbnail_cache.json"),
                patch.object(app, "VIDEO_SOURCE_CACHE_FILE", root / "creator_video_source_cache.json"),
                patch.object(app, "ANALYTICS_FILE", root / "creator_analytics_events.json"),
                patch.object(app, "load_entries_raw_files", return_value=entries),
            ):
                result = app.force_creator_storage_cleanup(aggressive=True)

            self.assertTrue(result["ok"])
            self.assertFalse((thumbs / "cached.webp").exists())
            self.assertFalse((html / "cached.html").exists())
            self.assertGreaterEqual(result["removed_cache_files"], 2)

    def test_prune_analytics_keeps_recent_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "creator_analytics_events.json"
            old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
            recent = datetime.now(timezone.utc).isoformat()
            path.write_text(
                app.json.dumps([
                    {"event_id": "old", "created_at": old},
                    {"event_id": "recent", "created_at": recent},
                ]),
                "utf-8",
            )

            with patch.object(app, "ANALYTICS_FILE", path):
                result = app.prune_analytics_events(retention_days=180, max_events=100)
                kept = app.json.loads(path.read_text("utf-8"))

            self.assertEqual(result["removed"], 1)
            self.assertEqual([event["event_id"] for event in kept], ["recent"])

    def test_manual_asset_optimizer_rewrites_library_urls(self) -> None:
        if app.Image is None:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            assets = root / "manual_scripts"
            entry_id = "a" * 32
            entry_dir = assets / entry_id
            entry_dir.mkdir(parents=True)
            image_path = entry_dir / "storyboard_cover.png"
            app.Image.new("RGB", (1200, 1200), (255, 190, 80)).save(image_path, "PNG")
            library_path = root / "manual_creator_scripts.json"
            library_path.write_text(
                app.json.dumps([{
                    "entry_id": entry_id,
                    "preview_image_url": f"https://kokocomedy.com/manual_scripts/{entry_id}/storyboard_cover.png",
                }]),
                "utf-8",
            )

            with (
                patch.object(app, "MANUAL_SCRIPT_ASSET_DIR", assets),
                patch.object(app, "MANUAL_LIBRARY_FILE", library_path),
                patch.object(app, "LIBRARY_FILE", root / "creator_online_library.json"),
                patch.object(app, "PUBLIC_BASE_URL", "https://kokocomedy.com"),
                patch.object(app, "invalidate_library_snapshot"),
            ):
                result = app.optimize_manual_script_assets(min_size_bytes=1, max_dimension=300, quality=60)
                updated = app.json.loads(library_path.read_text("utf-8"))

            self.assertEqual(result["optimized"], 1)
            self.assertFalse(image_path.exists())
            self.assertTrue((entry_dir / "storyboard_cover.webp").exists())
            self.assertTrue(updated[0]["preview_image_url"].endswith("storyboard_cover.webp"))


if __name__ == "__main__":
    unittest.main()
