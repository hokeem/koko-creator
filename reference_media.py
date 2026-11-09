import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

_lock = threading.Lock()


def reference_path(root, entry_id):
    if not re.fullmatch(r'[0-9a-f]{32}', entry_id):
        raise ValueError('Invalid entry id')
    return Path(root) / 'reference_videos' / (entry_id + '.mp4')


def prepare_reference(root, entry_id, url):
    if not re.fullmatch(r'https://(?:www\.)?tiktok\.com/@[^/]+/video/\d+', url):
        return False
    dest = reference_path(root, entry_id)
    with _lock:
        if dest.is_file() and dest.stat().st_size > 32:
            return True
        dest.parent.mkdir(parents=True, exist_ok=True)
        files = sorted(dest.parent.glob('*.mp4'), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        for old in files:
            if total < 192 * 1024 * 1024:
                break
            total -= old.stat().st_size
            old.unlink()
        if shutil.disk_usage(dest.parent).free < 100 * 1024 * 1024:
            return False
        temp = dest.with_suffix('.download.mp4')
        try:
            proc = subprocess.run([sys.executable, '-m', 'yt_dlp', '--no-playlist', '--no-progress', '--retries', '1', '--socket-timeout', '15', '--max-filesize', '50M', '-f', 'best[ext=mp4]/best', '-o', str(temp), url], capture_output=True, timeout=90)
            if proc.returncode or not temp.is_file() or temp.stat().st_size > 50 * 1024 * 1024:
                return False
            with temp.open('rb') as handle:
                if b'ftyp' not in handle.read(32):
                    return False
            os.replace(temp, dest)
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False
        finally:
            for partial in temp.parent.glob(temp.name + '*'):
                partial.unlink(missing_ok=True)


def serve_reference(handler, path):
    size = path.stat().st_size
    start, end = 0, size - 1
    value = handler.headers.get('Range', '')
    if value:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
        if not match or not any(match.groups()):
            handler.send_error(416)
            return
        a, b = match.groups()
        start = int(a) if a else max(0, size - int(b))
        end = min(int(b), size - 1) if a and b else size - 1
        if start >= size or start > end:
            handler.send_response(416)
            handler.send_header('Content-Range', f'bytes */{size}')
            handler.end_headers()
            return
    handler.send_response(206 if value else 200)
    handler.send_header('Content-Type', 'video/mp4')
    handler.send_header('Accept-Ranges', 'bytes')
    handler.send_header('Content-Length', str(end - start + 1))
    handler.send_header('Cache-Control', 'private, max-age=3600')
    if value:
        handler.send_header('Content-Range', f'bytes {start}-{end}/{size}')
    handler.end_headers()
    with path.open('rb') as stream:
        stream.seek(start)
        left = end - start + 1
        while left:
            chunk = stream.read(min(left, 65536))
            if not chunk:
                break
            handler.wfile.write(chunk)
            left -= len(chunk)
