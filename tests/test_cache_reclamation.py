import os
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
