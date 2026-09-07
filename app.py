#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import gzip
import hashlib
import html
import http.client
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from PIL import Image
except Exception:
    Image = None


PORT = int(os.environ.get("PORT", "10000"))
BASE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("DATA_DIR", str(BASE / "data"))).expanduser()
STATIC_ROOT = BASE / "static"
SEED_LIBRARY_FILE = BASE / "data" / "creator_online_library.json"
SEED_MANUAL_LIBRARY_FILE = BASE / "data" / "manual_creator_scripts.json"
LIBRARY_FILE = DATA_ROOT / "creator_online_library.json"
MANUAL_LIBRARY_FILE = DATA_ROOT / "manual_creator_scripts.json"
SUBMISSIONS_FILE = DATA_ROOT / "creator_submissions.json"
INTAKE_FILE = DATA_ROOT / "creator_intake_submissions.json"
ACCESS_APPLICATIONS_FILE = DATA_ROOT / "creator_access_applications.json"
CREATORS_FILE = DATA_ROOT / "creator_profiles.json"
ACCOUNTS_FILE = DATA_ROOT / "creator_accounts.json"
ANALYTICS_FILE = DATA_ROOT / "creator_analytics_events.json"
THUMB_CACHE_FILE = DATA_ROOT / "creator_thumbnail_cache.json"
VIDEO_SOURCE_CACHE_FILE = DATA_ROOT / "creator_video_source_cache.json"
SCRIPT_HTML_CACHE_DIR = DATA_ROOT / "creator_script_html_cache"
THUMB_IMAGE_CACHE_DIR = DATA_ROOT / "creator_thumbnail_images"
MANUAL_SCRIPT_ASSET_DIR = DATA_ROOT / "manual_scripts"
SYNC_META_FILE = DATA_ROOT / "creator_sync_meta.json"
OVERRIDES_FILE = DATA_ROOT / "creator_script_overrides.json"
SOURCE_URL = os.environ.get("CREATOR_LIBRARY_SOURCE_URL", "https://koko-kwai-coach.onrender.com/api/library")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://koko-fpml.onrender.com").rstrip("/")
SYNC_INTERVAL_SEC = int(os.environ.get("CREATOR_LIBRARY_SYNC_INTERVAL_SEC", "86400"))
ADMIN_PASSWORD = os.environ.get("KOKO_CREATOR_ADMIN_PASSWORD", "kokokwai@2026")
ADMIN_COOKIE = "koko_creator_admin"
CREATOR_AUTH_COOKIE = "koko_creator_auth"
VISITOR_COOKIE = "koko_creator_visitor"
DEFAULT_ALLOWED_ACCOUNTS = [
    "88996177106",
    "13996855249",
    "85987869447",
    "95991319838",
    "99991605452",
    "88981741082",
    "88998113027",
    "86998490156",
    "88999263655",
    "88988853941",
    "61982331597",
    "88997515250",
    "88988061712",
    "88998411165",
    "666",
]

DEFAULT_CONTENT_TYPE = "朋友整蛊"
CANONICAL_CONTENT_TYPES = ["夫妻整蛊/冲突", "夫妻暧昧", "家庭整蛊", "朋友整蛊"]
UNKNOWN_CONTENT_TYPES = {"待分类", "A classificar", "Sem categoria", "未分类", "", "Popular", "热门", "还没想好，给我热门"}

ENTRY_SNAPSHOT_LOCK = threading.RLock()
ENTRY_SNAPSHOT: dict[str, Any] = {
    "signature": None,
    "raw": [],
    "entries": [],
    "effective": [],
    "by_id": {},
}
SYNC_CHECK_LOCK = threading.Lock()
LAST_SYNC_CHECK_MONOTONIC = 0.0
SYNC_IN_PROGRESS = False
THUMB_WARM_LOCK = threading.Lock()
THUMB_WARM_SEMAPHORE = threading.Semaphore(2)
THUMB_WARMING: set[str] = set()


QUESTIONS = [
    {
        "id": "people",
        "pt": "Com quem você costuma gravar?",
        "zh": "你通常跟谁一起拍？",
        "options": [
            {"id": "couple", "pt": "Casal / namorados", "zh": "夫妻/情侣", "types": ["夫妻整蛊/冲突", "夫妻暧昧"], "keywords": ["夫妻", "妻子", "丈夫", "老公", "老婆", "情侣", "marido", "esposa", "casal", "namorado", "namorada"]},
            {"id": "family", "pt": "Família", "zh": "家庭", "types": ["家庭整蛊"], "keywords": ["妈妈", "爸爸", "儿子", "女儿", "家庭", "亲戚", "mãe", "pai", "filho", "filha", "família"]},
            {"id": "friends", "pt": "Amigos / colegas", "zh": "朋友/同事", "types": ["朋友整蛊"], "keywords": ["朋友", "同事", "路人", "街头", "公共场景", "世界杯", "偷手机", "便利店", "amigo", "colega", "rua", "público", "cliente", "loja"]},
        ],
    },
    {
        "id": "subtype",
        "pt": "Que tipo de roteiro de casal você quer?",
        "zh": "你想拍哪种夫妻/情侣剧情？",
        "options": [
            {"id": "couple_prank", "pt": "Pegadinha / briga / virada", "zh": "夫妻整蛊/冲突", "people": ["couple"], "types": ["夫妻整蛊/冲突"], "keywords": ["吵架", "整蛊", "欺骗", "算计", "反转", "briga", "pegadinha", "conflito", "reviravolta"]},
            {"id": "couple_flirt", "pt": "Ciúmes / traição / clima íntimo", "zh": "夫妻暧昧", "people": ["couple"], "types": ["夫妻暧昧"], "keywords": ["暧昧", "出轨", "好色", "吃醋", "撬墙角", "traição", "infiel", "amante", "ciúme", "seduz"]},
        ],
    },
    {
        "id": "duration",
        "multiple": True,
        "pt": "Quanto tempo você costuma gravar?",
        "zh": "你一般能拍多长？",
        "options": [
            {"id": "dur_1_20", "pt": "1-20 s", "zh": "1-20 秒", "keywords": []},
            {"id": "dur_20_60", "pt": "20 s-1 min", "zh": "20 秒-1 分钟", "keywords": []},
            {"id": "dur_60_120", "pt": "1-2 min", "zh": "1-2 分钟", "keywords": []},
            {"id": "dur_120_plus", "pt": "Mais de 2 min", "zh": "2 分钟以上", "keywords": []},
        ],
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(path)


def client_ip(headers: Any) -> str:
    forwarded = str(headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
    return forwarded or str(headers.get("X-Real-IP") or headers.get("CF-Connecting-IP") or "").strip()


def load_overrides() -> dict[str, dict[str, Any]]:
    data = read_json_file(OVERRIDES_FILE, {})
    if not isinstance(data, dict):
        return {}
    clean: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        entry_id = str(key or "").strip()
        if re.fullmatch(r"[0-9a-f]{32}", entry_id) and isinstance(value, dict):
            clean[entry_id] = dict(value)
    return clean


def save_overrides(overrides: dict[str, dict[str, Any]]) -> None:
    write_json_atomic(OVERRIDES_FILE, overrides)


def apply_entry_override(entry: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    item = dict(entry)
    if not isinstance(override, dict):
        item.setdefault("creator_published", True)
        return item
    for key in [
        "title",
        "whole_video_summary",
        "content_type",
        "video_url",
        "preview_image_url",
        "storyboard_image_url",
        "thumbnail_url",
        "html_url",
        "zh_html_url",
        "pt_html_url",
        "duration_seconds",
        "duration_bucket",
        "duration_label_pt",
        "duration_label_zh",
        "reference_video_enabled",
        "library_date",
        "created_at",
        "saved_at",
        "relationship_tags",
        "format_tags",
        "location_tags",
        "content_tags",
        "relationship_tag_labels_zh",
        "relationship_tag_labels_pt",
        "format_tag_labels_zh",
        "format_tag_labels_pt",
        "location_tag_labels_zh",
        "location_tag_labels_pt",
        "content_tag_labels_zh",
        "content_tag_labels_pt",
        "taxonomy_version",
        "taxonomy_source",
        "taxonomy_confidence",
        "taxonomy_reasoning",
        "taxonomy_updated_at",
    ]:
        if key in override:
            item[key] = override.get(key)
    item["creator_published"] = not bool(override.get("hidden") or override.get("deleted"))
    item["creator_override"] = True
    item["creator_override_updated_at"] = override.get("updated_at") or ""
    return item


def content_type_labels() -> list[str]:
    return list(CANONICAL_CONTENT_TYPES)


def compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def collapse_repeated_text(value: object) -> str:
    text = compact_text(value)
    if not text:
        return ""
    for parts in range(2, 5):
        if len(text) % parts == 0:
            size = len(text) // parts
            chunks = [text[i * size:(i + 1) * size].strip() for i in range(parts)]
            if chunks[0] and all(chunk == chunks[0] for chunk in chunks):
                return chunks[0]
        words = text.split()
        if len(words) % parts == 0:
            size = len(words) // parts
            chunks = [" ".join(words[i * size:(i + 1) * size]).strip() for i in range(parts)]
            if chunks[0] and all(chunk == chunks[0] for chunk in chunks):
                return chunks[0]
    return text


def first_repeated_url(value: object) -> str:
    text = collapse_repeated_text(value)
    urls = re.findall(r"https?://\S+", text)
    return urls[0] if urls else text


def normalize_submission_video_url(value: object) -> str:
    url = first_repeated_url(value).strip()
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return url.rstrip("/").lower()
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/").lower()
    path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


class DuplicateSubmissionError(ValueError):
    pass


def has_family_signal(text: str) -> bool:
    chinese_terms = ["妈妈", "爸爸", "母亲", "父亲", "儿子", "女儿", "孩子", "小孩", "宝宝", "亲戚", "婆婆", "岳母", "兄弟", "姐妹"]
    if any(term in text for term in chinese_terms):
        return True
    word_terms = [
        "mãe", "mae", "pai", "filho", "filha", "criança", "crianca", "crianças", "criancas",
        "bebê", "bebe", "sogra", "sogro", "irmão", "irmao", "irmã", "irma",
    ]
    return any(re.search(rf"(?<![\wÀ-ÿ]){re.escape(term)}(?![\wÀ-ÿ])", text, flags=re.I) for term in word_terms)


def has_any_signal(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def canonical_content_type(entry: dict[str, Any] | str) -> str:
    if isinstance(entry, str):
        current = entry.strip()
        text = current.lower()
    else:
        current = str(entry.get("content_type") or "").strip()
        values: list[str] = []
        for key in [
            "title",
            "whole_video_summary",
            "summary",
            "video_url",
            "html_url",
            "pt_html_url",
            "zh_html_url",
        ]:
            values.append(str(entry.get(key) or ""))
        text = " ".join(values).lower()

    legacy_flirt = {
        "夫妻暧昧",
        "夫妻出轨",
        "夫妻好色",
        "夫妻黄段子",
        "撬墙角",
        "Relacionamento de casal",
    }
    legacy_couple = {
        "夫妻整蛊/冲突",
        "夫妻吵架",
        "夫妻欺骗",
        "夫妻算计",
        "妻管严",
        "夫妻整蛊",
        "夫妻关系",
        "夫妻/情侣",
        "夫妻情感",
        "Conflito por dinheiro",
    }
    legacy_family = {"家庭/亲子"}
    legacy_friends = {
        "朋友整蛊",
        "整蛊",
        "整蛊恶搞",
        "骗局反转",
        "赖账",
        "赖账/金钱冲突",
        "骗子",
        "偷奸耍滑",
        "偷吃东西",
        "偷吃/偷懒/耍小聪明",
        "Popular",
        "Golpe e reviravolta",
        "Pegadinha",
        "Esperteza cotidiana",
        "待分类",
        "热门",
    }
    flirt_terms = [
        "出轨", "暧昧", "好色", "黄段子", "撬墙角", "偷看", "吃醋",
        "trai", "infiel", "amante", "ciúme", "ciume", "seduz", "paquera",
        "mulher bonita", "namorada", "namorado", "beijo", "íntim", "intim",
    ]
    couple_terms = [
        "夫妻", "妻子", "丈夫", "老公", "老婆", "情侣",
        "marido", "esposa", "casal",
    ]
    has_family = current in legacy_family or has_family_signal(text)
    has_flirt = current in legacy_flirt or has_any_signal(text, flirt_terms)
    has_couple = current in legacy_couple or has_any_signal(text, couple_terms)

    if has_family:
        return "家庭整蛊"
    if has_flirt:
        return "夫妻暧昧"
    if has_couple:
        return "夫妻整蛊/冲突"
    if current in CANONICAL_CONTENT_TYPES and current != "家庭整蛊":
        return current
    if current in legacy_friends or current in UNKNOWN_CONTENT_TYPES:
        return "朋友整蛊"
    return "朋友整蛊"


def inferred_content_type(entry: dict[str, Any]) -> str:
    return canonical_content_type(entry)


def parse_timecode_seconds(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    nums = [int(part) for part in re.findall(r"\d+", text)]
    if len(nums) >= 3:
        return float(nums[-3] * 3600 + nums[-2] * 60 + nums[-1])
    if len(nums) >= 2:
        return float(nums[-2] * 60 + nums[-1])
    if nums:
        return float(nums[-1])
    return 0.0


def duration_bucket_from_seconds(seconds: float) -> str:
    if seconds <= 0:
        return ""
    if seconds <= 20:
        return "dur_1_20"
    if seconds <= 60:
        return "dur_20_60"
    if seconds <= 120:
        return "dur_60_120"
    return "dur_120_plus"


def extract_duration_seconds_from_text(value: object) -> float:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    if not text:
        return 0.0
    candidates: list[float] = []
    for match in re.finditer(r"(?:\d{1,2}:)?\d{1,2}:\d{2}\s*[-–—]\s*((?:\d{1,2}:)?\d{1,2}:\d{2})", text):
        candidates.append(parse_timecode_seconds(match.group(1)))
    if candidates:
        return max(candidates)
    for match in re.finditer(r"(?:\d{1,2}:)?\d{1,2}:\d{2}", text):
        candidates.append(parse_timecode_seconds(match.group(0)))
    return max(candidates) if candidates else 0.0


def extract_duration_seconds_from_script_json(script_json: dict[str, Any]) -> float:
    rows = script_json.get("segments") or script_json.get("rows") or script_json.get("script_table") or []
    if not isinstance(rows, list):
        return 0.0
    values: list[float] = []
    for row in rows:
        if isinstance(row, dict):
            values.append(parse_timecode_seconds(row.get("time") or row.get("tempo") or row.get("Tempo") or ""))
    return max(values) if values else 0.0


def entry_duration_seconds(entry: dict[str, Any]) -> float:
    for key in ["duration_seconds", "script_duration_seconds"]:
        try:
            value = float(entry.get(key) or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return extract_duration_seconds_from_text(" ".join(str(entry.get(key) or "") for key in ["script_html", "script_table_html", "html"]))


def duration_bucket_for_entry(entry: dict[str, Any]) -> str:
    bucket = str(entry.get("duration_bucket") or entry.get("script_duration_bucket") or "").strip()
    if bucket in DURATION_OPTIONS:
        return bucket
    return duration_bucket_from_seconds(entry_duration_seconds(entry))


def normalized_entry(entry: dict[str, Any]) -> dict[str, Any]:
    item = dict(entry)
    item["title"] = collapse_repeated_text(item.get("title") or "")
    item["whole_video_summary"] = collapse_repeated_text(
        item.get("whole_video_summary") or item.get("summary") or ""
    )
    item["video_url"] = first_repeated_url(item.get("video_url") or "")
    item["content_type"] = inferred_content_type(item)
    seconds = entry_duration_seconds(item)
    if seconds > 0:
        item["duration_seconds"] = round(seconds, 2)
        item["duration_bucket"] = duration_bucket_from_seconds(seconds)
    for dimension in ["relationship", "format", "location", "content"]:
        field = f"{dimension}_tags"
        values = item.get(field)
        item[field] = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip())) if isinstance(values, list) else []
    return item


def fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")
    except http.client.IncompleteRead as exc:
        partial = bytes(exc.partial or b"").decode("utf-8", errors="ignore")
        if partial.strip().endswith(("}", "]")):
            return partial
        curl = shutil.which("curl")
        if not curl:
            raise
        completed = subprocess.run(
            [curl, "-fsSL", "--max-time", str(max(5, timeout)), "-A", "Mozilla/5.0", url],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.stdout.decode("utf-8", errors="ignore")


def reclaim_rebuildable_cache_space(min_free_bytes: int = 64 * 1024 * 1024) -> int:
    """Remove oldest generated caches when the persistent disk is nearly full."""
    try:
        if shutil.disk_usage(DATA_ROOT).free >= min_free_bytes:
            return 0
    except OSError:
        return 0
    candidates: list[Path] = []
    for root in (THUMB_IMAGE_CACHE_DIR, SCRIPT_HTML_CACHE_DIR):
        if root.exists():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    candidates.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0)
    removed = 0
    for path in candidates:
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
        try:
            if shutil.disk_usage(DATA_ROOT).free >= min_free_bytes:
                break
        except OSError:
            break
    return removed


def sync_library(force: bool = False) -> dict[str, Any]:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    meta = read_json_file(SYNC_META_FILE, {})
    if not isinstance(meta, dict):
        meta = {}
    if not force and LIBRARY_FILE.exists():
        try:
            last = datetime.fromisoformat(str(meta.get("last_synced_at", "")).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - last < timedelta(seconds=SYNC_INTERVAL_SEC):
                return {"ok": True, "status": "fresh", **meta}
        except Exception:
            pass
    try:
        payload = json.loads(fetch_text(SOURCE_URL, timeout=20))
        entries = payload.get("entries") if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            raise ValueError("source did not return a list")
        clean = [entry for entry in entries if isinstance(entry, dict)]
        reclaim_rebuildable_cache_space()
        write_json_atomic(LIBRARY_FILE, clean)
        meta = {"ok": True, "status": "synced", "source_url": SOURCE_URL, "entries_count": len(clean), "last_synced_at": now_iso()}
        write_json_atomic(SYNC_META_FILE, meta)
        return meta
    except Exception as exc:
        if not LIBRARY_FILE.exists() and SEED_LIBRARY_FILE.exists():
            LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
            LIBRARY_FILE.write_text(SEED_LIBRARY_FILE.read_text("utf-8"), "utf-8")
        meta = {**meta, "ok": False, "status": "failed", "source_url": SOURCE_URL, "error": str(exc), "failed_at": now_iso()}
        write_json_atomic(SYNC_META_FILE, meta)
        return meta


def sync_library_entry(entry_id: str) -> dict[str, Any]:
    entry_id = str(entry_id or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        raise ValueError("invalid entry_id")
    payload = json.loads(fetch_text(f"{SOURCE_URL.rstrip('/')}/{entry_id}", timeout=20))
    entry = payload.get("entry") if isinstance(payload, dict) else None
    if not isinstance(entry, dict) or str(entry.get("entry_id") or "") != entry_id:
        raise ValueError("source entry was not found")
    entries = read_json_file(LIBRARY_FILE, [])
    entries = [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []
    replaced = False
    for index, item in enumerate(entries):
        if str(item.get("entry_id") or "") == entry_id:
            entries[index] = entry
            replaced = True
            break
    if not replaced:
        entries.insert(0, entry)
    reclaim_rebuildable_cache_space()
    write_json_atomic(LIBRARY_FILE, entries[:500])
    invalidate_library_snapshot()
    return {"ok": True, "status": "updated" if replaced else "inserted", "entry_id": entry_id}
def maybe_sync_library() -> None:
    """Refresh in the background so a creator never waits for the source service."""
    global LAST_SYNC_CHECK_MONOTONIC, SYNC_IN_PROGRESS
    now = time.monotonic()
    if now - LAST_SYNC_CHECK_MONOTONIC < 60:
        return
    with SYNC_CHECK_LOCK:
        now = time.monotonic()
        if now - LAST_SYNC_CHECK_MONOTONIC < 60:
            return
        LAST_SYNC_CHECK_MONOTONIC = now
        if SYNC_IN_PROGRESS:
            return
        SYNC_IN_PROGRESS = True

    def run() -> None:
        global SYNC_IN_PROGRESS
        try:
            sync_library(False)
            invalidate_library_snapshot()
        finally:
            with SYNC_CHECK_LOCK:
                SYNC_IN_PROGRESS = False

    threading.Thread(target=run, name="creator-library-sync", daemon=True).start()


def entry_files_signature() -> tuple[tuple[str, int, int], ...]:
    files = [
        LIBRARY_FILE,
        MANUAL_LIBRARY_FILE,
        SEED_LIBRARY_FILE,
        SEED_MANUAL_LIBRARY_FILE,
        OVERRIDES_FILE,
    ]
    signature: list[tuple[str, int, int]] = []
    for path in files:
        try:
            stat = path.stat()
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature.append((str(path), 0, 0))
    return tuple(signature)


def invalidate_library_snapshot() -> None:
    with ENTRY_SNAPSHOT_LOCK:
        ENTRY_SNAPSHOT["signature"] = None


def upsert_manual_entry(entry: dict[str, Any]) -> None:
    entries = read_json_file(MANUAL_LIBRARY_FILE, [])
    if not isinstance(entries, list):
        entries = []
    entry_id = str(entry.get("entry_id") or "").strip()
    entries = [item for item in entries if isinstance(item, dict) and str(item.get("entry_id") or "") != entry_id]
    entries.insert(0, entry)
    write_json_atomic(MANUAL_LIBRARY_FILE, entries[:500])


def save_direct_import(payload: dict[str, Any]) -> dict[str, Any]:
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    entry_id = str(entry.get("entry_id") or payload.get("entry_id") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        raise ValueError("Invalid script id.")
    html_content = str(payload.get("html_content") or "").strip()
    if not html_content:
        raise ValueError("Missing script HTML content.")
    script_json = payload.get("script_json") if isinstance(payload.get("script_json"), dict) else {}
    static_dir = MANUAL_SCRIPT_ASSET_DIR / entry_id
    static_dir.mkdir(parents=True, exist_ok=True)
    html_path = static_dir / "script_table_pt.html"
    html_path.write_text(html_content, "utf-8")
    if script_json:
        write_json_atomic(static_dir / "script_table_pt.json", script_json)
    preview_url = ""
    cover_b64 = str(payload.get("cover_b64") or "").strip()
    if not cover_b64:
        raise ValueError("Missing storyboard cover image.")
    if cover_b64:
        if "," in cover_b64 and cover_b64.startswith("data:"):
            cover_b64 = cover_b64.split(",", 1)[1]
        cover_mime = str(payload.get("cover_mime") or "image/png")
        suffix = ".jpg" if "jpeg" in cover_mime or "jpg" in cover_mime else ".png"
        cover_path = static_dir / ("storyboard_cover" + suffix)
        cover_path.write_bytes(base64.b64decode(cover_b64))
        preview_url = f"{PUBLIC_BASE_URL}/manual_scripts/{entry_id}/{cover_path.name}"
    storyboard_url = str(entry.get("storyboard_image_url") or payload.get("storyboard_image_url") or "").strip()
    storyboard_b64 = str(payload.get("storyboard_b64") or "").strip()
    if storyboard_b64:
        if "," in storyboard_b64 and storyboard_b64.startswith("data:"):
            storyboard_b64 = storyboard_b64.split(",", 1)[1]
        storyboard_mime = str(payload.get("storyboard_mime") or "image/png")
        storyboard_suffix = ".jpg" if "jpeg" in storyboard_mime or "jpg" in storyboard_mime else ".png"
        storyboard_path = static_dir / ("storyboard_reference" + storyboard_suffix)
        storyboard_path.write_bytes(base64.b64decode(storyboard_b64))
        storyboard_url = f"{PUBLIC_BASE_URL}/manual_scripts/{entry_id}/{storyboard_path.name}"
    if not storyboard_url:
        storyboard_url = preview_url
    content_type = str(entry.get("content_type") or DEFAULT_CONTENT_TYPE)
    content_type = {
        "A classificar": DEFAULT_CONTENT_TYPE,
        "Sem categoria": DEFAULT_CONTENT_TYPE,
    }.get(content_type, content_type)
    duration_seconds = extract_duration_seconds_from_script_json(script_json) or extract_duration_seconds_from_text(html_content)
    duration_bucket = duration_bucket_from_seconds(duration_seconds)
    imported = {
        "entry_id": entry_id,
        "parent_job_id": str(entry.get("parent_job_id") or f"creator_import_{entry_id}"),
        "created_at": str(entry.get("created_at") or now_iso()),
        "saved_at": str(entry.get("saved_at") or now_iso()),
        "video_url": first_repeated_url(entry.get("video_url") or payload.get("video_url") or ""),
        "title": collapse_repeated_text(entry.get("title") or script_json.get("title") or "Roteiro importado"),
        "content_type": content_type,
        "content_type_source": str(entry.get("content_type_source") or "manual"),
        "content_type_reasoning": str(entry.get("content_type_reasoning") or "Imported from Creator admin Excel."),
        "content_type_confidence": str(entry.get("content_type_confidence") or "high"),
        "duration_seconds": round(duration_seconds, 2) if duration_seconds > 0 else 0,
        "duration_bucket": duration_bucket,
        "whole_video_summary": collapse_repeated_text(
            entry.get("whole_video_summary") or script_json.get("whole_video_summary") or ""
        ),
        "html_url": f"{PUBLIC_BASE_URL}/manual_scripts/{entry_id}/script_table_pt.html",
        "pt_html_url": f"{PUBLIC_BASE_URL}/manual_scripts/{entry_id}/script_table_pt.html",
        "zh_html_url": f"{PUBLIC_BASE_URL}/manual_scripts/{entry_id}/script_table_pt.html",
        "preview_image_url": preview_url,
        "storyboard_image_url": storyboard_url,
        "reference_video_enabled": entry.get("reference_video_enabled") is not False,
        "library_date": str(entry.get("library_date") or entry.get("saved_at") or entry.get("created_at") or "")[:10],
        "source": "creator_direct_import",
    }
    for dimension in ["relationship", "format", "location", "content"]:
        field = f"{dimension}_tags"
        labels_zh = f"{dimension}_tag_labels_zh"
        labels_pt = f"{dimension}_tag_labels_pt"
        imported[field] = list(entry.get(field) or [])
        imported[labels_zh] = list(entry.get(labels_zh) or [])
        imported[labels_pt] = list(entry.get(labels_pt) or [])
    for field in ["taxonomy_version", "taxonomy_source", "taxonomy_confidence", "taxonomy_reasoning", "taxonomy_updated_at"]:
        if field in entry:
            imported[field] = entry.get(field)
    imported = normalized_entry(imported)
    upsert_manual_entry(imported)
    invalidate_entry_cache(entry_id)
    return {"ok": True, "entry": public_admin_entry(imported), "share_url": f"/script/{entry_id}"}


def load_entries_raw_files() -> list[dict[str, Any]]:
    manual = read_json_file(MANUAL_LIBRARY_FILE, [])
    manual_entries = [entry for entry in manual if isinstance(entry, dict)] if isinstance(manual, list) else []
    seed_manual = read_json_file(SEED_MANUAL_LIBRARY_FILE, [])
    if isinstance(seed_manual, list):
        manual_entries.extend(entry for entry in seed_manual if isinstance(entry, dict))
    data = read_json_file(LIBRARY_FILE, [])
    if not data and SEED_LIBRARY_FILE.exists():
        data = read_json_file(SEED_LIBRARY_FILE, [])
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for entry in [*manual_entries, *[item for item in data if isinstance(item, dict)]]:
        entry_id = str(entry.get("entry_id") or "").strip()
        if entry_id and entry_id in seen:
            continue
        if entry_id:
            seen.add(entry_id)
        entries.append(entry)
    return entries


def refresh_entry_snapshot() -> dict[str, Any]:
    maybe_sync_library()
    signature = entry_files_signature()
    with ENTRY_SNAPSHOT_LOCK:
        if ENTRY_SNAPSHOT.get("signature") == signature:
            return ENTRY_SNAPSHOT
        raw = load_entries_raw_files()
        overrides = load_overrides()
        entries: list[dict[str, Any]] = []
        by_id: dict[str, dict[str, Any]] = {}
        for raw_entry in raw:
            entry_id = str(raw_entry.get("entry_id") or "").strip()
            override = overrides.get(entry_id)
            if isinstance(override, dict) and override.get("deleted"):
                continue
            if isinstance(override, dict) and override.get("hidden"):
                continue
            normalized = normalized_entry(apply_entry_override(raw_entry, override))
            entries.append(normalized)
            if entry_id:
                by_id[entry_id] = normalized
        effective = sorted(
            [entry for entry in entries if entry_is_effective(entry)],
            key=admin_entry_sort_key,
            reverse=True,
        )
        ENTRY_SNAPSHOT.update({
            "signature": signature,
            "raw": raw,
            "entries": entries,
            "effective": effective,
            "by_id": by_id,
        })
        return ENTRY_SNAPSHOT


def load_entries_raw() -> list[dict[str, Any]]:
    return list(refresh_entry_snapshot()["raw"])


def load_entries() -> list[dict[str, Any]]:
    return list(refresh_entry_snapshot()["entries"])


def entry_is_effective(entry: dict[str, Any]) -> bool:
    return bool(
        str(entry.get("title") or "").strip()
        and entry_summary(entry)
        and entry_script_url(entry)
    )


def admin_entry_scope(entry: dict[str, Any]) -> str:
    if not bool(entry.get("creator_published", True)):
        return "hidden"
    if not entry_is_effective(entry):
        return "incomplete"
    return "portal_visible"


def entry_publication_timestamp(entry: dict[str, Any]) -> float:
    manual_tags = entry.get("manual_tags") if isinstance(entry.get("manual_tags"), dict) else {}
    candidates = [
        manual_tags.get("publish_datetime"),
        entry.get("publish_datetime"),
        entry.get("library_date"),
        entry.get("created_at"),
        entry.get("saved_at"),
    ]
    for value in candidates:
        text = str(value or "").strip().replace("/", "-")
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            continue
    return 0.0


def admin_entry_sort_key(entry: dict[str, Any]) -> tuple[float, str, str]:
    return (
        entry_publication_timestamp(entry),
        str(entry.get("actual_saved_at") or entry.get("saved_at") or entry.get("created_at") or ""),
        str(entry.get("entry_id") or ""),
    )


def load_admin_entries(scope: str = "portal_visible") -> list[dict[str, Any]]:
    if scope not in {"portal_visible", "hidden", "incomplete", "all"}:
        scope = "portal_visible"
    overrides = load_overrides()
    entries: list[dict[str, Any]] = []
    for entry in load_entries_raw():
        entry_id = str(entry.get("entry_id") or "").strip()
        override = overrides.get(entry_id)
        if isinstance(override, dict) and override.get("deleted"):
            continue
        normalized = normalized_entry(apply_entry_override(entry, override))
        if scope != "all" and admin_entry_scope(normalized) != scope:
            continue
        entries.append(normalized)
    return sorted(entries, key=admin_entry_sort_key, reverse=True)


def effective_entries() -> list[dict[str, Any]]:
    return list(refresh_entry_snapshot()["effective"])


def entry_summary(entry: dict[str, Any]) -> str:
    for key in ["whole_video_summary", "summary", "content_summary", "description", "title"]:
        text = str(entry.get(key) or "").strip()
        if text:
            return collapse_repeated_text(text)
    return ""


def entry_script_url(entry: dict[str, Any]) -> str:
    for key in ["pt_html_url", "html_url", "zh_html_url", "video_url"]:
        text = str(entry.get(key) or "").strip()
        if text:
            return text
    return ""


def option_lookup() -> dict[str, dict[str, Any]]:
    return {str(option["id"]): option for question in QUESTIONS for option in question.get("options", [])}


PEOPLE_OPTIONS = {"couple", "family", "friends"}
SUBTYPE_OPTIONS = {"couple_prank", "couple_flirt"}
DURATION_OPTIONS = {"dur_1_20", "dur_20_60", "dur_60_120", "dur_120_plus"}
DURATION_LABELS = {
    "dur_1_20": {"pt": "1-20 s", "zh": "1-20 秒"},
    "dur_20_60": {"pt": "20 s-1 min", "zh": "20 秒-1 分钟"},
    "dur_60_120": {"pt": "1-2 min", "zh": "1-2 分钟"},
    "dur_120_plus": {"pt": "Mais de 2 min", "zh": "2 分钟以上"},
}
COUPLE_TYPES = {"夫妻整蛊/冲突", "夫妻暧昧"}
FAMILY_TYPES = {"家庭整蛊"}
FRIEND_TYPES = {"朋友整蛊"}
MONEY_TYPES = set()
SNEAKY_TYPES = set()
PRANK_TYPES = {"夫妻整蛊/冲突", "家庭整蛊", "朋友整蛊"}
COUPLE_TERMS = [
    "夫妻", "妻子", "丈夫", "老公", "老婆", "情侣", "男友", "女友", "出轨", "吃醋",
    "marido", "esposa", "casal", "namorado", "namorada", "noivo", "noiva", "ciume", "ciúme", "traicao", "traição", "infiel", "amante",
]
FAMILY_TERMS = ["妈妈", "爸爸", "儿子", "女儿", "家庭", "亲戚", "mãe", "mae", "pai", "filho", "filha", "familia", "família"]
FRIEND_TERMS = ["朋友", "同事", "兄弟", "闺蜜", "amigo", "amiga", "colega", "irmão", "irmao", "irmã", "irma"]
GROUP_TERMS = ["多人", "围观", "群体", "路人", "儿童", "孩子", "pessoas", "grupo", "plateia", "publico", "público", "multidao", "multidão", "rua", "criança", "crianca", "crianças", "criancas"]
SERVICE_TERMS = ["老板", "员工", "顾客", "服务", "客户", "chefe", "cliente", "funcionario", "funcionário", "atendimento", "entregador", "delivery"]
MONEY_TERMS = ["付款", "欠钱", "逃单", "工资", "dinheiro", "pagar", "pagamento", "salario", "salário", "reais", "conta", "cobrar"]
PRANK_TERMS = ["整蛊", "恶作剧", "捉弄", "pegadinha", "brincadeira", "susto", "troll", "zoeira"]
ROLE_TERMS = ["homem", "mulher", "jovem", "rapaz", "moça", "moca", "senhor", "senhora", "menino", "menina"]
MULTI_PERSON_TERMS = [
    "两个人", "两位", "二人", "男人和女人", "男孩和男人", "女孩和女人", "duas pessoas", "dois homens", "duas mulheres",
    "homem e mulher", "homem e uma mulher", "mulher e um homem", "menino e homem", "menino e um homem", "menina e mulher", "casal de amigos",
    "homem se aproxima", "um homem se aproxima", "mulher se aproxima", "uma mulher se aproxima", "homem se aproxima dela", "mulher se aproxima dele",
]


def entry_match_text(entry: dict[str, Any]) -> str:
    item = normalized_entry(entry)
    return " ".join(
        str(item.get(key) or "")
        for key in ["content_type", "title", "whole_video_summary", "summary", "content_type_reasoning", "video_url"]
    ).lower()


def has_any(text: str, terms: list[str] | set[str]) -> bool:
    return any(str(term).lower() in text for term in terms if term)


def selected_axis(selected: list[str], options: set[str]) -> str:
    return next((value for value in selected if value in options), "")


def selected_durations(selected: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for value in selected:
        if value in DURATION_OPTIONS and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def has_multiple_role_terms(text: str) -> bool:
    found = {term for term in ROLE_TERMS if re.search(rf"\b{re.escape(term)}\b", text)}
    return len(found) >= 2


def entry_signals(entry: dict[str, Any]) -> dict[str, bool]:
    item = normalized_entry(entry)
    text = entry_match_text(item)
    content_type = canonical_content_type(item)
    couple = content_type in COUPLE_TYPES or has_any(text, COUPLE_TERMS)
    family = has_any(text, FAMILY_TERMS)
    friend = has_any(text, FRIEND_TERMS)
    group = has_any(text, GROUP_TERMS)
    multi = has_any(text, MULTI_PERSON_TERMS) or has_multiple_role_terms(text)
    service = has_any(text, SERVICE_TERMS)
    money = content_type in MONEY_TYPES or has_any(text, MONEY_TERMS)
    prank = content_type in PRANK_TYPES or has_any(text, PRANK_TERMS)
    sneaky = content_type in SNEAKY_TYPES
    return {
        "couple": couple,
        "family": family,
        "friend": friend,
        "group": group,
        "multi": multi,
        "service": service,
        "money": money,
        "prank": prank,
        "sneaky": sneaky,
    }


def entry_matches_hard_selection(entry: dict[str, Any], selected: list[str]) -> bool:
    people = selected_axis(selected, PEOPLE_OPTIONS)
    subtype = selected_axis(selected, SUBTYPE_OPTIONS)
    durations = selected_durations(selected)
    content_type = canonical_content_type(entry)
    if people == "couple" and content_type not in COUPLE_TYPES:
        return False
    if people == "family" and content_type != "家庭整蛊":
        return False
    if people == "friends" and content_type != "朋友整蛊":
        return False
    if subtype == "couple_prank" and content_type != "夫妻整蛊/冲突":
        return False
    if subtype == "couple_flirt" and content_type != "夫妻暧昧":
        return False
    if durations and duration_bucket_for_entry(entry) not in set(durations):
        return False
    return True


def filtered_entries_for_selection(entries: list[dict[str, Any]], selected: list[str]) -> list[dict[str, Any]]:
    if not selected:
        return entries
    strict_matches = [entry for entry in entries if entry_matches_hard_selection(entry, selected)]
    if strict_matches:
        return strict_matches
    # Duration data is not equally reliable across imported scripts. Keep the
    # creator's content-type tags as the hard filter, but do not let a missing
    # duration bucket force unrelated scripts into the daily feed.
    if selected_durations(selected):
        topic_only = [value for value in selected if value not in DURATION_OPTIONS]
        if topic_only:
            topic_matches = [entry for entry in entries if entry_matches_hard_selection(entry, topic_only)]
            if topic_matches:
                return topic_matches
    return []


def entry_matches_topic_selection(entry: dict[str, Any], selected: list[str]) -> bool:
    topic_only = [value for value in selected if value not in DURATION_OPTIONS]
    return bool(topic_only) and entry_matches_hard_selection(entry, topic_only)


def entry_matches_relaxed_selection(entry: dict[str, Any], selected: list[str]) -> bool:
    values = set(selected)
    content_type = canonical_content_type(entry)
    if {"couple", "couple_prank", "couple_flirt"} & values:
        return content_type in COUPLE_TYPES
    if "family" in values:
        return content_type == "家庭整蛊"
    if "friends" in values:
        return content_type == "朋友整蛊"
    return False


def recommendation_sequence(entries: list[dict[str, Any]], selected: list[str]) -> list[dict[str, Any]]:
    ordered_entries = sorted(entries, key=entry_time_sort_key, reverse=True)
    if not selected:
        return ordered_entries
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(candidates: list[dict[str, Any]]) -> None:
        for entry in sorted(candidates, key=entry_time_sort_key, reverse=True):
            entry_id = str(entry.get("entry_id") or "")
            if entry_id and entry_id not in seen:
                seen.add(entry_id)
                picked.append(entry)

    add([entry for entry in ordered_entries if entry_matches_hard_selection(entry, selected)])
    add([entry for entry in ordered_entries if entry_matches_topic_selection(entry, selected)])
    add([entry for entry in ordered_entries if entry_matches_relaxed_selection(entry, selected)])
    add(ordered_entries)
    return picked


def score_entry(entry: dict[str, Any], selected: list[str], index: int) -> int:
    lookup = option_lookup()
    text = " ".join([
        str(entry.get("content_type") or ""),
        str(entry.get("title") or ""),
        entry_summary(entry),
        str(entry.get("content_type_reasoning") or ""),
    ])
    content_type = canonical_content_type(entry)
    score = 0
    for option_id in selected:
        option = lookup.get(option_id) or {}
        if content_type in set(option.get("types") or []):
            score += 42
        hits = sum(1 for keyword in option.get("keywords") or [] if keyword and str(keyword) in text)
        score += min(24, hits * 6)
    score += 10 if content_type != DEFAULT_CONTENT_TYPE else 0
    score += 8 if entry_script_url(entry) else 0
    score += 4 if entry.get("video_url") else 0
    score += 1000 if entry.get("creator_featured") else 0
    score += max(0, 10 - min(index, 10))
    return score


def entry_time_sort_key(entry: dict[str, Any]) -> str:
    item = normalized_entry(entry)
    return str(item.get("saved_at") or item.get("created_at") or "")


def abs_url(url: object, base_url: str = "https://koko-kwai-coach.onrender.com") -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("/"):
        return base_url.rstrip("/") + text
    return text


def public_entry(entry: dict[str, Any], score: int) -> dict[str, Any]:
    entry = normalized_entry(entry)
    entry_id = str(entry.get("entry_id") or "").strip()
    script_date = str(entry.get("saved_at") or entry.get("created_at") or "").strip()
    duration_bucket = duration_bucket_for_entry(entry)
    duration_seconds = entry_duration_seconds(entry)
    result = {
        "entry_id": entry_id,
        "title": entry.get("title") or "Roteiro",
        "summary": entry_summary(entry),
        "content_type": entry.get("content_type") or DEFAULT_CONTENT_TYPE,
        "video_url": abs_url(entry.get("video_url"), ""),
        "reference_video_enabled": entry.get("reference_video_enabled") is not False,
        "html_url": abs_url(entry.get("pt_html_url") or entry.get("html_url") or entry.get("zh_html_url")),
        "preview_image_url": abs_url(entry.get("preview_image_url") or entry.get("thumbnail_url") or ""),
        "storyboard_image_url": abs_url(entry.get("storyboard_image_url") or entry.get("preview_image_url") or entry.get("thumbnail_url") or ""),
        "cover_url": abs_url(entry.get("preview_image_url") or entry.get("thumbnail_url") or ""),
        "thumbnail_url": f"/api/creator/thumbnail/{entry_id}.webp" if entry_id else "",
        "script_date": script_date,
        "duration_bucket": duration_bucket,
        "duration_seconds": round(duration_seconds, 2) if duration_seconds > 0 else 0,
        "duration_label_pt": DURATION_LABELS.get(duration_bucket, {}).get("pt", ""),
        "duration_label_zh": DURATION_LABELS.get(duration_bucket, {}).get("zh", ""),
        "score": score,
    }
    for dimension in ["relationship", "format", "location", "content"]:
        result[f"{dimension}_tags"] = list(entry.get(f"{dimension}_tags") or [])
        result[f"{dimension}_tag_labels_zh"] = list(entry.get(f"{dimension}_tag_labels_zh") or [])
        result[f"{dimension}_tag_labels_pt"] = list(entry.get(f"{dimension}_tag_labels_pt") or [])
    result["taxonomy_version"] = str(entry.get("taxonomy_version") or "")
    return result


def rewrite_relative_urls(html_text: str, base_url: str) -> str:
    def repl(match: re.Match[str]) -> str:
        attr, quote, value = match.group(1), match.group(2), html.unescape(match.group(3).strip())
        if not value or value.startswith(("http://", "https://", "data:", "mailto:", "#")):
            return match.group(0)
        return f'{attr}={quote}{urllib.parse.urljoin(base_url, value)}{quote}'
    return re.sub(r'\b(src|href)=([\'"])(.*?)\2', repl, html_text, flags=re.I | re.S)


def sanitize_script_html(raw_html: str, base_url: str) -> str:
    text = re.sub(r"<!--.*?-->", "", raw_html, flags=re.S)
    body = re.search(r"<body[^>]*>(.*?)</body>", text, flags=re.I | re.S)
    text = body.group(1) if body else text
    text = re.sub(r"<script\b[^>]*>.*?</script>", "", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.I | re.S)
    text = re.sub(r"<link\b[^>]*>", "", text, flags=re.I)
    text = re.sub(r"\s(on\w+)=([\"']).*?\2", "", text, flags=re.I | re.S)
    text = re.sub(r"\sstyle=([\"']).*?\1", "", text, flags=re.I | re.S)
    return rewrite_relative_urls(text.strip(), base_url)


def local_static_file_from_url(url: str) -> Path | None:
    text = str(url or "").strip()
    if not text:
        return None
    parsed = urllib.parse.urlparse(text)
    path = parsed.path if parsed.scheme else text
    if path.startswith("/manual_scripts/"):
        candidate = (MANUAL_SCRIPT_ASSET_DIR / urllib.parse.unquote(path.removeprefix("/manual_scripts/"))).resolve()
        try:
            if MANUAL_SCRIPT_ASSET_DIR.resolve() in candidate.parents and candidate.is_file():
                return candidate
        except Exception:
            return None
        return None
    if not path.startswith("/static/"):
        return None
    candidate = (STATIC_ROOT / urllib.parse.unquote(path.removeprefix("/static/"))).resolve()
    try:
        if STATIC_ROOT.resolve() in candidate.parents and candidate.is_file():
            return candidate
    except Exception:
        return None
    return None


def script_html_for_entry(entry: dict[str, Any]) -> str:
    entry_id = str(entry.get("entry_id") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        return ""
    cache_file = SCRIPT_HTML_CACHE_DIR / f"{entry_id}.html"
    if cache_file.exists():
        return cache_file.read_text("utf-8", errors="ignore")
    url = abs_url(entry.get("pt_html_url") or entry.get("html_url") or entry.get("zh_html_url"))
    if not url:
        return ""
    local_static = local_static_file_from_url(url)
    if local_static:
        clean = sanitize_script_html(local_static.read_text("utf-8", errors="ignore"), url)
        SCRIPT_HTML_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(clean, "utf-8")
        return clean
    raw = fetch_text(url, timeout=25)
    clean = sanitize_script_html(raw, url)
    SCRIPT_HTML_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(clean, "utf-8")
    return clean


def public_script_detail(entry: dict[str, Any], *, include_html: bool = True) -> dict[str, Any]:
    item = public_entry(entry, 100)
    item["script_html"] = script_html_for_entry(entry) if include_html else ""
    return item


def recommendation_payload(selected: list[str], limit: int = 80) -> dict[str, Any]:
    selected = [value for value in selected if value in option_lookup()]
    entries = effective_entries()
    candidates = recommendation_sequence(entries, selected)
    scored = [
        (score_entry(entry, selected, idx), entry)
        for idx, entry in enumerate(candidates)
    ]
    return {"questions": QUESTIONS, "selected": selected, "total": len(scored), "entries": [public_entry(entry, score) for score, entry in scored[:limit]]}


def entry_by_id(entry_id: str) -> dict[str, Any] | None:
    entry = refresh_entry_snapshot()["by_id"].get(entry_id)
    return entry if isinstance(entry, dict) else None


def admin_entry_by_id(entry_id: str) -> dict[str, Any] | None:
    for entry in load_admin_entries("all"):
        if str(entry.get("entry_id") or "") == entry_id:
            return entry
    return None


def meta_image(html_text: str) -> str:
    match = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
    return html.unescape(match.group(1).strip()) if match else ""


def meta_video_source(html_text: str) -> str:
    match = re.search(r'"contentUrl"\s*:\s*"([^"]+?\.mp4[^"]*)"', html_text, re.I)
    if not match:
        match = re.search(r'contentUrl\s*:\s*"([^"]+?\.mp4[^"]*)"', html_text, re.I)
    if not match:
        return ""
    return html.unescape(match.group(1).replace("\\u002F", "/").strip())


def official_video_embed_url(source_url: str) -> tuple[str, str]:
    """Return a platform-owned embed URL for supported public post URLs."""
    try:
        parsed = urllib.parse.urlparse(source_url)
    except ValueError:
        return "", ""
    host = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        match = re.search(r"/video/(\d+)", parsed.path)
        if not match:
            return "tiktok", ""
        query = urllib.parse.urlencode({
            "autoplay": "0",
            "controls": "1",
            "loop": "0",
            "music_info": "0",
            "description": "0",
            "rel": "0",
            "native_context_menu": "0",
        })
        return "tiktok", f"https://www.tiktok.com/player/v1/{match.group(1)}?{query}"

    if host == "instagram.com" or host.endswith(".instagram.com"):
        if len(path_parts) < 2 or path_parts[0].lower() not in {"p", "reel", "reels", "tv"}:
            return "instagram", ""
        content_type = "reel" if path_parts[0].lower() in {"reel", "reels"} else path_parts[0].lower()
        shortcode = re.sub(r"[^A-Za-z0-9_-]", "", path_parts[1])
        if not shortcode:
            return "instagram", ""
        return "instagram", f"https://www.instagram.com/{content_type}/{shortcode}/embed/"

    if host == "kwai.com" or host.endswith(".kwai.com"):
        return "kwai", ""
    return "other", ""


def video_source_url(entry: dict[str, Any]) -> str:
    entry_id = str(entry.get("entry_id") or "")
    cache = read_json_file(VIDEO_SOURCE_CACHE_FILE, {})
    if isinstance(cache, dict) and entry_id in cache and cache[entry_id].get("video_source_url"):
        return str(cache[entry_id]["video_source_url"])
    source_page = str(entry.get("video_url") or "")
    source = ""
    if source_page:
        try:
            source = meta_video_source(fetch_text(source_page, timeout=12))
        except Exception:
            source = ""
    if not isinstance(cache, dict):
        cache = {}
    cache[entry_id] = {"video_source_url": source, "checked_at": now_iso()}
    write_json_atomic(VIDEO_SOURCE_CACHE_FILE, cache)
    return source


def video_playback(entry: dict[str, Any]) -> dict[str, Any]:
    if entry.get("reference_video_enabled") is False:
        return {
            "platform": "",
            "playback_type": "disabled",
            "video_source_url": "",
            "embed_url": "",
            "video_url": "",
            "reference_video_enabled": False,
            "error_code": "reference_video_disabled",
            "error": "原视频访问失败，请稍后再试",
        }
    source_page = str(entry.get("video_url") or "").strip()
    platform, embed_url = official_video_embed_url(source_page)
    direct_source = video_source_url(entry) if platform == "kwai" else ""
    return {
        "platform": platform,
        "playback_type": "direct_mp4" if direct_source else ("official_embed" if embed_url else "external_link"),
        "video_source_url": direct_source,
        "embed_url": embed_url,
        "video_url": source_page,
        "reference_video_enabled": True,
    }


def thumbnail_url(entry: dict[str, Any]) -> str:
    entry_id = str(entry.get("entry_id") or "")
    manual_thumb = str(entry.get("preview_image_url") or entry.get("thumbnail_url") or "").strip()
    if manual_thumb:
        return abs_url(manual_thumb)
    cache = read_json_file(THUMB_CACHE_FILE, {})
    if isinstance(cache, dict) and entry_id in cache and cache[entry_id].get("thumbnail_url"):
        return str(cache[entry_id]["thumbnail_url"])
    url = str(entry.get("video_url") or "")
    thumb = ""
    if url:
        try:
            thumb = meta_image(fetch_text(url, timeout=10))
        except Exception:
            thumb = ""
    if not isinstance(cache, dict):
        cache = {}
    cache[entry_id] = {"thumbnail_url": thumb, "checked_at": now_iso()}
    write_json_atomic(THUMB_CACHE_FILE, cache)
    return thumb


def fetch_image_bytes(url: str, timeout: int = 15) -> tuple[bytes, str]:
    local = local_static_file_from_url(url)
    if local:
        return local.read_bytes(), mimetypes.guess_type(str(local))[0] or "image/jpeg"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers.get("Content-Type") or "image/jpeg"


def thumbnail_cache_file(entry: dict[str, Any], source_url: str) -> Path:
    entry_id = str(entry.get("entry_id") or "").strip()
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12]
    return THUMB_IMAGE_CACHE_DIR / f"{entry_id}-{digest}.webp"


def cached_optimized_thumbnail(entry: dict[str, Any], source_url: str) -> bytes | None:
    cache_file = thumbnail_cache_file(entry, source_url)
    try:
        return cache_file.read_bytes() if cache_file.exists() else None
    except OSError:
        return None


def warm_thumbnail_async(entry: dict[str, Any]) -> None:
    entry_id = str(entry.get("entry_id") or "").strip()
    if not entry_id:
        return
    with THUMB_WARM_LOCK:
        if entry_id in THUMB_WARMING:
            return
        THUMB_WARMING.add(entry_id)

    def run() -> None:
        try:
            # Let the creator's direct image request win; warm the smaller WebP after it.
            time.sleep(1.5)
            with THUMB_WARM_SEMAPHORE:
                optimized_thumbnail(entry)
        except Exception:
            pass
        finally:
            with THUMB_WARM_LOCK:
                THUMB_WARMING.discard(entry_id)

    threading.Thread(target=run, name=f"thumb-{entry_id[:8]}", daemon=True).start()


def optimized_thumbnail(entry: dict[str, Any]) -> tuple[bytes, str]:
    entry_id = str(entry.get("entry_id") or "").strip()
    source_url = thumbnail_url(entry)
    if not entry_id or not source_url:
        return placeholder_svg(entry), "image/svg+xml; charset=utf-8"
    cache_file = thumbnail_cache_file(entry, source_url)
    if cache_file.exists():
        return cache_file.read_bytes(), "image/webp"
    raw, content_type = fetch_image_bytes(source_url)
    if Image is None:
        return raw, content_type
    try:
        image = Image.open(BytesIO(raw))
        image.thumbnail((720, 720), Image.Resampling.LANCZOS)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        THUMB_IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        out = BytesIO()
        image.save(out, format="WEBP", quality=76, method=5)
        data = out.getvalue()
        cache_file.write_bytes(data)
        return data, "image/webp"
    except Exception:
        return raw, content_type


def placeholder_svg(entry: dict[str, Any] | None) -> bytes:
    title = html.escape(str((entry or {}).get("title") or "Koko")[:54])
    kind = html.escape(str((entry or {}).get("content_type") or "Roteiro"))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="324" height="576" viewBox="0 0 324 576"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#ffb357"/><stop offset=".55" stop-color="#ff6500"/><stop offset="1" stop-color="#2a1d16"/></linearGradient></defs><rect width="324" height="576" fill="url(#g)"/><circle cx="250" cy="92" r="74" fill="#fff" opacity=".18"/><text x="26" y="70" fill="#fff" font-family="Arial" font-size="26" font-weight="700">Koko</text><text x="26" y="430" fill="#fff" font-family="Arial" font-size="18" font-weight="700">{kind}</text><foreignObject x="26" y="448" width="270" height="100"><div xmlns="http://www.w3.org/1999/xhtml" style="color:white;font-family:Arial;font-size:26px;font-weight:800;line-height:1.12;">{title}</div></foreignObject></svg>""".encode()


def link_metadata(url: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read(450_000)
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return meta
    for key, patterns in {
        "title": [
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']+)["\']',
            r"<title[^>]*>(.*?)</title>",
        ],
        "image": [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ],
    }.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.I | re.S)
            if match:
                value = html.unescape(re.sub(r"\s+", " ", match.group(1)).strip())
                if value:
                    meta[key] = urllib.parse.urljoin(url, value)
                    break
    return meta


def match_submission_creator_by_account(
    account: dict[str, Any],
    profiles: list[dict[str, Any]] | None = None,
    account_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    profiles = profiles if profiles is not None else load_creator_profiles()
    account_lookup = account_lookup if account_lookup is not None else account_alias_lookup()
    account_keys = account_aliases(account)
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        account_key = str(profile.get("account_id") or profile.get("phone") or profile.get("kwai_id") or profile.get("uid") or "")
        linked_account = find_account_from_lookup(account_key, account_lookup)
        creator_keys = {
            normalize_account_key(profile.get("profile_id") or ""),
            normalize_account_key(profile.get("account_id") or ""),
            normalize_account_key(profile.get("phone") or ""),
            normalize_account_key(profile.get("uid") or ""),
            normalize_kwai_id(profile.get("kwai_id") or ""),
        }
        creator_keys.update(account_aliases(linked_account) if linked_account else set())
        creator_keys = {item for item in creator_keys if item}
        if account_keys.intersection(creator_keys):
            return {
                "profile_id": str(profile.get("profile_id") or ""),
                "name": str(profile.get("name") or profile.get("kwai_id") or "Kwai creator"),
                "kwai_id": str(profile.get("kwai_id") or ""),
            }
    return None


def match_submission_creator_by_kwai_id(
    kwai_id: str,
    profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    normalized = normalize_kwai_id(kwai_id).lower()
    if not normalized:
        return None
    profiles = profiles if profiles is not None else load_creator_profiles()
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        if normalize_kwai_id(profile.get("kwai_id") or "").lower() == normalized:
            return {
                "profile_id": str(profile.get("profile_id") or ""),
                "name": str(profile.get("name") or profile.get("kwai_id") or "Kwai creator"),
                "kwai_id": str(profile.get("kwai_id") or ""),
            }
    return None


def save_submission(payload: dict[str, Any], *, account: dict[str, Any] | None = None) -> dict[str, Any]:
    entry_id = str(payload.get("entry_id") or "").strip()
    video_url = str(payload.get("video_url") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        raise ValueError("Invalid script id.")
    if not video_url.startswith(("http://", "https://")):
        raise ValueError("Please submit a public video link.")
    entry = entry_by_id(entry_id)
    if not entry:
        raise ValueError("Script not found.")
    normalized_video_url = normalize_submission_video_url(video_url)
    meta = link_metadata(video_url)
    fallback_thumb = f"/api/creator/thumbnail/{entry_id}.webp"
    creator_id = canonical_account_key(str((account or {}).get("account_id") or payload.get("creator_id") or "local_creator"))
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    for existing in submissions:
        if not isinstance(existing, dict):
            continue
        same_creator = canonical_account_key(str(existing.get("creator_id") or "local_creator")) == (creator_id or "local_creator")
        same_video = normalize_submission_video_url(existing.get("video_url") or "") == normalized_video_url
        if same_creator and same_video:
            raise DuplicateSubmissionError("作品已上传，无需重复上传")
    detected_kwai_id = resolve_kwai_id_from_video_link(video_url, timeout=10)
    submission = {
        "submission_id": uuid4().hex,
        "entry_id": entry_id,
        "script_title": str(entry.get("title") or ""),
        "script_content_type": str(entry.get("content_type") or DEFAULT_CONTENT_TYPE),
        "submitted_title": meta.get("title") or str(entry.get("title") or ""),
        "thumbnail_url": meta.get("image") or fallback_thumb,
        "creator_id": creator_id or "local_creator",
        "detected_kwai_id": detected_kwai_id,
        "video_url": video_url,
        "status": "pending_review",
        "created_at": now_iso(),
    }
    # A video author's public Kwai ID is more specific than a login alias. Some
    # legacy accounts share aliases, so account-only matching can select the
    # wrong creator profile even when the video URL identifies its owner.
    matched_creator = match_submission_creator_by_kwai_id(detected_kwai_id)
    if not matched_creator and account:
        matched_creator = match_submission_creator_by_account(account)
    if matched_creator:
        submission.update({
            "creator_profile_id": matched_creator.get("profile_id", ""),
            "creator_profile_name": matched_creator.get("name", ""),
            "creator_profile_kwai_id": matched_creator.get("kwai_id", ""),
        })
    submissions.insert(0, submission)
    write_json_atomic(SUBMISSIONS_FILE, submissions[:1000])
    return submission


def delete_submissions_by_ids(submission_ids: list[str]) -> dict[str, Any]:
    ids = {str(item or "").strip() for item in submission_ids if str(item or "").strip()}
    if not ids:
        return {"ok": True, "deleted": 0, "missing_ids": [], "total_before": 0, "total_after": 0}
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    total_before = len(submissions)
    kept: list[dict[str, Any]] = []
    deleted_ids: list[str] = []
    for item in submissions:
        if isinstance(item, dict) and str(item.get("submission_id") or "") in ids:
            deleted_ids.append(str(item.get("submission_id") or ""))
            continue
        kept.append(item)
    if len(kept) != total_before:
        write_json_atomic(SUBMISSIONS_FILE, kept[:1000])
    missing_ids = sorted(ids - set(deleted_ids))
    return {
        "ok": True,
        "deleted": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "missing_ids": missing_ids,
        "total_before": total_before,
        "total_after": len(kept),
    }


def save_access_application(payload: dict[str, Any], headers: Any) -> dict[str, Any]:
    phone_raw = str(payload.get("phone") or payload.get("account_id") or "").strip()
    phone = normalize_account_key(phone_raw)
    kwai_id = str(payload.get("kwai_id") or payload.get("kwai") or "").strip().lstrip("@")
    reason = re.sub(r"\s+", " ", str(payload.get("reason") or payload.get("application_reason") or "").strip())
    if not phone:
        raise ValueError("Digite seu telefone.")
    if not kwai_id:
        raise ValueError("Informe seu ID do Kwai.")
    if not reason:
        raise ValueError("Informe o motivo da solicitação.")
    applications = read_json_file(ACCESS_APPLICATIONS_FILE, [])
    if not isinstance(applications, list):
        applications = []
    application = {
        "application_id": uuid4().hex,
        "phone": phone,
        "phone_raw": phone_raw,
        "kwai_id": kwai_id,
        "reason": reason[:600],
        "status": "pending",
        "created_at": now_iso(),
        "ip": client_ip(headers),
        "user_agent": str(headers.get("User-Agent") or "")[:240],
    }
    applications.insert(0, application)
    write_json_atomic(ACCESS_APPLICATIONS_FILE, applications[:1000])
    return application


def backfill_submission_creators(limit: int = 200) -> dict[str, Any]:
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    checked = 0
    updated = 0
    results: list[dict[str, Any]] = []
    for idx, item in enumerate(submissions):
        if checked >= limit:
            break
        if not isinstance(item, dict):
            continue
        if normalize_kwai_id(item.get("detected_kwai_id") or ""):
            continue
        video_url = str(item.get("video_url") or "").strip()
        if not video_url:
            continue
        checked += 1
        detected = resolve_kwai_id_from_video_link(video_url, timeout=12)
        result = {
            "submission_id": item.get("submission_id"),
            "video_url": video_url,
            "detected_kwai_id": detected,
            "updated": False,
        }
        if detected:
            item["detected_kwai_id"] = detected
            item["matched_at"] = now_iso()
            submissions[idx] = item
            updated += 1
            result["updated"] = True
        results.append(result)
    if updated:
        write_json_atomic(SUBMISSIONS_FILE, submissions[:1000])
    return {"ok": True, "checked": checked, "updated": updated, "total": len(submissions), "results": results}



def public_questions_with_other() -> list[dict[str, Any]]:
    source_by_id = {str(question.get("id") or ""): question for question in QUESTIONS}
    skip_options = {"hot"}
    questions: list[dict[str, Any]] = []
    for question_id in ["people", "scene", "humor"]:
        source = source_by_id.get(question_id) or {}
        item = {key: value for key, value in source.items() if key != "options"}
        item["options"] = [
            dict(option)
            for option in source.get("options") or []
            if str(option.get("id") or "") not in skip_options
        ]
        item["options"].append({"id": "other", "pt": "Outro", "zh": "其他", "types": [], "keywords": []})
        questions.append(item)
    questions.extend([
        {
            "id": "duration",
            "pt": "Quanto tempo costuma ter o vídeo que você grava?",
            "zh": "你们通常拍的视频时长大概是多少？",
            "options": [
                {"id": "d_1_20s", "pt": "1-20s", "zh": "1-20 秒"},
                {"id": "d_20s_1m", "pt": "20s-1min", "zh": "20 秒-1 分钟"},
                {"id": "d_1_2m", "pt": "1-2min", "zh": "1-2 分钟"},
                {"id": "d_2m_plus", "pt": "Mais de 2min", "zh": "2 分钟以上"},
                {"id": "other", "pt": "Outro", "zh": "其他"},
            ],
        },
        {
            "id": "shoot_location",
            "pt": "Onde vocês costumam gravar?",
            "zh": "你们通常在哪里拍摄？",
            "options": [
                {"id": "home", "pt": "Em casa", "zh": "家里"},
                {"id": "outdoor", "pt": "Ao ar livre / campo / fábrica / estrada", "zh": "室外（包括田野、工厂、道路）"},
                {"id": "other", "pt": "Outro", "zh": "其他"},
            ],
        },
    ])
    return questions


def save_intake(payload: dict[str, Any]) -> dict[str, Any]:
    kwai_name = str(payload.get("kwai_name") or "").strip()
    if not kwai_name:
        raise ValueError("Kwai name is required.")
    answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
    questions = public_questions_with_other()
    valid_questions = {str(question.get("id") or ""): question for question in questions}
    clean_answers: dict[str, dict[str, Any]] = {}
    for question_id, question in valid_questions.items():
        value = answers.get(question_id)
        if not isinstance(value, dict):
            continue
        raw_selections = value.get("selections")
        if isinstance(raw_selections, list):
            selections = [item for item in raw_selections if isinstance(item, dict)]
        else:
            selections = []
            option_id = str(value.get("option_id") or "").strip()
            if option_id:
                selections.append({
                    "option_id": option_id,
                    "label_pt": str(value.get("label_pt") or "").strip(),
                    "label_zh": str(value.get("label_zh") or "").strip(),
                })
        option_ids = {str(option.get("id") or "") for option in question.get("options") or []}
        clean_selections = []
        for selection in selections:
            option_id = str(selection.get("option_id") or "").strip()[:80]
            if option_id not in option_ids or option_id == "other":
                continue
            clean_selections.append({
                "option_id": option_id,
                "label_pt": str(selection.get("label_pt") or "").strip()[:160],
                "label_zh": str(selection.get("label_zh") or "").strip()[:160],
            })
        other_text = str(value.get("other_text") or "").strip()[:500]
        if other_text:
            clean_selections.append({"option_id": "other", "label_pt": "Outro", "label_zh": "其他"})
        if clean_selections or other_text:
            clean_answers[question_id] = {
                "question_pt": str(question.get("pt") or "")[:200],
                "question_zh": str(question.get("zh") or "")[:200],
                "selections": clean_selections,
                "other_text": other_text,
            }
    if len(clean_answers) < len(valid_questions):
        raise ValueError("Please answer all questions.")
    intake = {
        "intake_id": uuid4().hex,
        "kwai_name": kwai_name[:160],
        "kwai_url": "",
        "whatsapp": "",
        "answers": clean_answers,
        "notes": str(payload.get("notes") or "").strip()[:1200],
        "source": str(payload.get("source") or "creator-survey").strip()[:80],
        "created_at": now_iso(),
    }
    intakes = read_json_file(INTAKE_FILE, [])
    if not isinstance(intakes, list):
        intakes = []
    intakes.insert(0, intake)
    write_json_atomic(INTAKE_FILE, intakes[:3000])
    return intake


def survey_html() -> str:
    questions_json = json.dumps(public_questions_with_other(), ensure_ascii=False)
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>Koko Creator Survey</title>{FAVICON_LINKS}<style>
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#fffaf5,#fff0df 52%,#fff8f2);color:#1f1f1f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif}}.phone{{width:min(100%,520px);margin:0 auto;min-height:100vh;padding:18px 18px 34px}}.top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}}.brand{{font-size:30px;font-weight:950;letter-spacing:-.03em}}.brand span{{color:#ff5f00;font-size:17px;margin-left:6px}}.lang{{display:flex;gap:8px}}button{{font:inherit;cursor:pointer}}.lang button{{border:1px solid rgba(255,95,0,.26);border-radius:999px;background:white;color:#ff5f00;font-weight:850;min-height:36px;padding:0 12px}}.hero{{overflow:hidden;border-radius:28px;background:linear-gradient(135deg,#fff,#ffe0ca);border:1px solid rgba(255,95,0,.16);padding:24px 20px;margin-bottom:16px;box-shadow:0 20px 48px rgba(85,45,10,.12)}}.kicker{{display:inline-flex;border:1px solid rgba(255,95,0,.26);border-radius:999px;padding:7px 11px;color:#ff5f00;font-size:12px;font-weight:900;background:#fffaf5}}h1{{margin:15px 0 10px;font-size:38px;line-height:1.03;letter-spacing:-.04em}}.accent{{color:#ff5f00}}p{{color:#656b73;line-height:1.55;margin:0}}.card{{border:1px solid rgba(255,95,0,.16);border-radius:24px;background:rgba(255,255,255,.86);padding:16px;margin:12px 0;box-shadow:0 14px 34px rgba(85,45,10,.08)}}label{{display:block;color:#1f1f1f;font-weight:900;margin:0 0 8px}}input,textarea{{width:100%;border:1px solid rgba(255,95,0,.22);border-radius:16px;background:#fffaf7;min-height:50px;padding:12px 14px;font:inherit;outline:none}}textarea{{min-height:92px;resize:vertical}}input:focus,textarea:focus{{border-color:#ff5f00;box-shadow:0 0 0 4px rgba(255,95,0,.10)}}.question h2{{margin:0 0 5px;font-size:22px}}.hint{{font-size:12px;color:#858b92;margin-top:4px}}.options{{display:grid;gap:10px;margin-top:14px}}.option{{border:1px solid rgba(255,95,0,.22);border-radius:18px;background:white;min-height:58px;padding:12px 14px;text-align:left;color:#1f1f1f;font-weight:850}}.option.active{{border-color:#ff5f00;background:#fff0e6;box-shadow:0 10px 24px rgba(255,95,0,.13)}}.other-input{{display:block;margin-top:12px}}.primary{{width:100%;min-height:56px;border:0;border-radius:999px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;font-size:18px;font-weight:950;box-shadow:0 16px 34px rgba(255,95,0,.32)}}.status{{min-height:24px;margin-top:12px;text-align:center;font-weight:850;color:#ff5f00}}.done{{display:none;text-align:center;padding:28px 18px}}.done.active{{display:block}}.form.hidden{{display:none}}.small{{font-size:12px;color:#858b92;margin-top:6px}}</style></head><body><main class='phone'><header class='top'><div class='brand'>koko <span>Creator</span></div></header><section class='hero'><span class='kicker' data-i='kicker'>Pesquisa Koko Creator</span><h1 data-i='title'>Conte para a Koko <span class='accent'>como você grava</span></h1><p data-i='lead'>Responda em menos de 1 minuto. Você pode escolher mais de uma opção.</p></section><form class='form' id='survey-form'><section class='card'><label data-i='kwaiName'>Nome no Kwai</label><input name='kwai_name' placeholder='@seu_nome_no_kwai' required><div class='small' data-i='kwaiHint'>Use o nome que aparece no seu perfil.</div></section><div id='questions'></div><section class='card'><label data-i='notes'>Algo mais que precisamos saber? (opcional)</label><textarea name='notes' placeholder='Ex.: gravamos em casal, temos pouco tempo, preferimos histórias rápidas...'></textarea></section><button class='primary' type='submit' data-i='submit'>Enviar respostas</button><div class='status' id='status'></div></form><section class='done' id='done'><h1 data-i='doneTitle'>Recebemos suas respostas.</h1><p data-i='doneText'>Obrigado! A equipe Koko vai usar essas informações para entender seu perfil de criação.</p></section></main><script>
const questions={questions_json};let lang='pt';const answers={{}};const text={{pt:{{kicker:'Pesquisa Koko Creator',title:'Conte para a Koko <span class="accent">como você grava</span>',lead:'Responda em menos de 1 minuto. Você pode escolher mais de uma opção.',kwaiName:'Nome no Kwai',kwaiHint:'Use o nome que aparece no seu perfil.',notes:'Algo mais que precisamos saber? (opcional)',submit:'Enviar respostas',sending:'Enviando...',ok:'Enviado com sucesso.',err:'Confira as respostas e tente de novo.',otherPh:'Outra resposta',doneTitle:'Recebemos suas respostas.',doneText:'Obrigado! A equipe Koko vai usar essas informações para entender seu perfil de criação.',multi:'Escolha uma ou mais opções'}},zh:{{kicker:'Koko Creator 作者问卷',title:'告诉 Koko <span class="accent">你通常怎么拍</span>',lead:'1 分钟内完成。每题可以多选。',kwaiName:'Kwai 作者名称',kwaiHint:'填写主页里展示的名字或 @ID。',notes:'还有什么想补充？（选填）',submit:'提交问卷',sending:'提交中...',ok:'提交成功。',err:'请检查答案后重试。',otherPh:'其他答案',doneTitle:'我们收到你的信息了。',doneText:'谢谢！Koko 团队会用这些信息理解你的创作类型。',multi:'可多选'}}}};function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}function t(k){{return text[lang][k]||text.pt[k]||k}}function ensure(qid){{answers[qid]=answers[qid]||{{selections:[],other_text:''}};return answers[qid]}}function toggleOption(q,o){{const a=ensure(q.id);const idx=a.selections.findIndex(x=>x.option_id===o.id);if(idx>=0)a.selections.splice(idx,1);else a.selections.push({{option_id:o.id,label_pt:o.pt,label_zh:o.zh}})}}function applyLang(){{document.documentElement.lang='pt-BR';document.querySelectorAll('[data-i]').forEach(el=>{{const key=el.dataset.i;if(text[lang][key])el.innerHTML=text[lang][key]}});renderQuestions()}}function renderQuestions(){{const box=document.querySelector('#questions');box.innerHTML=questions.map((q,idx)=>{{const a=ensure(q.id);const normal=(q.options||[]).filter(o=>o.id!=='other');return `<section class="card question"><h2>${{idx+1}}. ${{esc(q[lang]||q.pt)}}</h2><div class="hint">${{t('multi')}}</div><div class="options">${{normal.map(o=>`<button class="option ${{a.selections.some(x=>x.option_id===o.id)?'active':''}}" type="button" data-q="${{esc(q.id)}}" data-opt="${{esc(o.id)}}">${{esc(o[lang]||o.pt)}}</button>`).join('')}}</div><div class="other-input"><label>${{lang==='zh'?'其他':'Outro'}}</label><input data-other="${{esc(q.id)}}" value="${{esc(a.other_text||'')}}" placeholder="${{t('otherPh')}}"></div></section>`}}).join('')}}document.addEventListener('click',e=>{{const opt=e.target.closest('[data-opt]');if(opt){{const q=questions.find(item=>item.id===opt.dataset.q);const o=q?.options?.find(item=>item.id===opt.dataset.opt);if(q&&o){{toggleOption(q,o);renderQuestions()}}}}}});document.addEventListener('input',e=>{{const input=e.target.closest('[data-other]');if(input)ensure(input.dataset.other).other_text=input.value}});document.querySelector('#survey-form').addEventListener('submit',async e=>{{e.preventDefault();const status=document.querySelector('#status');const fd=new FormData(e.target);status.textContent=t('sending');try{{const payload=Object.fromEntries(fd.entries());payload.answers=answers;payload.source='creator-survey';const r=await fetch('/api/creator/intake',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});if(!r.ok)throw new Error();status.textContent=t('ok');document.querySelector('#survey-form').classList.add('hidden');document.querySelector('#done').classList.add('active')}}catch(err){{status.textContent=t('err')}}}});applyLang();</script></body></html>"""


def cookie_value(headers: Any, name: str) -> str:
    raw = str(headers.get("Cookie") or "")
    for part in raw.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return urllib.parse.unquote(value)
    return ""


def is_admin_authed(headers: Any) -> bool:
    token = cookie_value(headers, ADMIN_COOKIE)
    return bool(token) and secrets.compare_digest(token, ADMIN_PASSWORD)


def normalize_account_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_@.-]+", "", str(value or "").strip())[:80]


def normalize_phone(value: str) -> str:
    return re.sub(r"\D+", "", str(value or ""))[:40]


def normalize_kwai_id(value: str) -> str:
    text = str(value or "").strip()
    text = text[1:] if text.startswith("@") else text
    return re.sub(r"[^0-9A-Za-z_.-]+", "", text)[:120]


ACCOUNT_ID_REPLACEMENTS = {
    "88992150187": "88993217658",
}


def canonical_account_key(value: str) -> str:
    clean = normalize_account_key(value)
    return ACCOUNT_ID_REPLACEMENTS.get(clean, clean)


def legacy_aliases_for_account(account_id: str) -> set[str]:
    clean = normalize_account_key(account_id)
    return {old for old, new in ACCOUNT_ID_REPLACEMENTS.items() if new == clean}


def account_aliases(account: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for key in ["account_id", "phone", "kwai_id", "uid"]:
        raw = str(account.get(key) or "").strip()
        for value in [raw, normalize_phone(raw), normalize_kwai_id(raw)]:
            clean = normalize_account_key(value)
            if clean:
                aliases.add(clean)
                aliases.add(canonical_account_key(clean))
    for raw in account.get("login_aliases") or []:
        for value in [str(raw or ""), normalize_phone(str(raw or "")), normalize_kwai_id(str(raw or ""))]:
            clean = normalize_account_key(value)
            if clean:
                aliases.add(clean)
                aliases.add(canonical_account_key(clean))
    aliases.update(legacy_aliases_for_account(str(account.get("account_id") or "")))
    aliases.update(legacy_aliases_for_account(str(account.get("phone") or "")))
    return aliases


def account_alias_lookup(accounts: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for account in accounts if accounts is not None else load_accounts():
        if not isinstance(account, dict):
            continue
        for alias in account_aliases(account):
            if alias:
                lookup.setdefault(alias, account)
    return lookup


def find_account_from_lookup(account_id: str, lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    targets = {
        canonical_account_key(account_id),
        canonical_account_key(normalize_phone(account_id)),
        normalize_kwai_id(account_id),
    }
    for target in targets:
        if target and target in lookup:
            return lookup[target]
    return None


def merge_account_dict(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in ["display_name", "kwai_id", "uid", "status", "source", "registration_status", "created_at", "provisioned_at", "registered_at", "last_registered_at", "updated_at", "last_login_at", "first_seen_at"]:
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming.get(key)
    if incoming.get("registration_status") == "registered":
        merged["registration_status"] = "registered"
    for key in ["registered_at", "first_seen_at", "created_at", "provisioned_at"]:
        values = [str(merged.get(key) or ""), str(incoming.get(key) or "")]
        values = [item for item in values if item]
        if values:
            merged[key] = min(values)
    for key in ["last_registered_at", "updated_at", "last_login_at"]:
        values = [str(merged.get(key) or ""), str(incoming.get(key) or "")]
        values = [item for item in values if item]
        if values:
            merged[key] = max(values)
    state = merged.get("state") if isinstance(merged.get("state"), dict) else {}
    incoming_state = incoming.get("state") if isinstance(incoming.get("state"), dict) else {}
    merged["state"] = {**incoming_state, **state}
    aliases = account_aliases(base).union(account_aliases(incoming))
    merged["login_aliases"] = sorted(alias for alias in aliases if alias)
    return merged


def migrate_account_replacements(accounts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    migrated: dict[str, dict[str, Any]] = {}
    changed = False
    ordered: list[str] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        row = dict(account)
        raw_id = normalize_account_key(row.get("account_id") or row.get("phone") or "")
        raw_phone = normalize_phone(row.get("phone") or raw_id)
        canonical_id = canonical_account_key(raw_id)
        canonical_phone = canonical_account_key(raw_phone) if raw_phone else canonical_id
        target_id = canonical_phone if raw_phone in ACCOUNT_ID_REPLACEMENTS or raw_phone in ACCOUNT_ID_REPLACEMENTS.values() else canonical_id
        if raw_id != target_id:
            row["account_id"] = target_id
            changed = True
        if raw_phone and raw_phone != target_id and (raw_phone in ACCOUNT_ID_REPLACEMENTS or target_id in ACCOUNT_ID_REPLACEMENTS.values()):
            row["phone"] = target_id
            changed = True
        row_aliases = set(row.get("login_aliases") or [])
        row_aliases.update(alias for alias in [raw_id, raw_phone, canonical_id, canonical_phone] if alias)
        row_aliases.update(legacy_aliases_for_account(target_id))
        if sorted(row_aliases) != sorted(row.get("login_aliases") or []):
            row["login_aliases"] = sorted(row_aliases)
            changed = True
        key = str(row.get("account_id") or target_id)
        if key in migrated:
            migrated[key] = merge_account_dict(migrated[key], row)
            changed = True
        else:
            migrated[key] = row
            ordered.append(key)
    return [migrated[key] for key in ordered if key in migrated], changed


def submission_kwai_id(submission: dict[str, Any]) -> str:
    return normalize_kwai_id(submission.get("detected_kwai_id") or kwai_handle_from_url(str(submission.get("video_url") or "")))


def match_submission_creator(
    submission: dict[str, Any],
    profiles: list[dict[str, Any]] | None = None,
    account_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    profiles = profiles if profiles is not None else load_creator_profiles()
    account_lookup = account_lookup if account_lookup is not None else account_alias_lookup()
    submission_creator = normalize_account_key(submission.get("creator_id") or "")
    submission_kwai = submission_kwai_id(submission)
    exact_kwai_match = match_submission_creator_by_kwai_id(submission_kwai, profiles)
    if exact_kwai_match:
        return exact_kwai_match
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        account_key = str(profile.get("account_id") or profile.get("phone") or profile.get("kwai_id") or profile.get("uid") or "")
        account = find_account_from_lookup(account_key, account_lookup)
        creator_keys = {
            normalize_account_key(profile.get("profile_id") or ""),
            normalize_account_key(profile.get("account_id") or ""),
            normalize_account_key(profile.get("phone") or ""),
            normalize_account_key(profile.get("uid") or ""),
            normalize_kwai_id(profile.get("kwai_id") or ""),
        }
        creator_keys.update(account_aliases(account) if account else set())
        creator_keys = {item for item in creator_keys if item}
        if submission_creator and submission_creator in creator_keys:
            return {
                "profile_id": str(profile.get("profile_id") or ""),
                "name": str(profile.get("name") or profile.get("kwai_id") or "Kwai creator"),
                "kwai_id": str(profile.get("kwai_id") or ""),
            }
    return None


def enrich_submission_records(submissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = load_creator_profiles()
    account_lookup = account_alias_lookup()
    enriched: list[dict[str, Any]] = []
    for item in submissions:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        matched = match_submission_creator(row, profiles, account_lookup)
        if matched:
            row["creator_profile_id"] = matched.get("profile_id", "")
            row["creator_profile_name"] = matched.get("name", "")
            row["creator_profile_kwai_id"] = matched.get("kwai_id", "")
            row["creator_unmatched"] = False
        else:
            row["creator_unmatched"] = True
            row["unmatched_reason"] = "未匹配到创作者账号、Kwai ID、UID 或手机号"
        enriched.append(row)
    return enriched


def resolve_kwai_id_from_video_link(url: str, timeout: int = 12) -> str:
    direct = normalize_kwai_id(kwai_handle_from_url(url))
    if direct:
        return direct
    try:
        req = urllib.request.Request(str(url or ""), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            final_url = response.geturl()
            raw = response.read(120_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    for source in [final_url, raw]:
        match = re.search(r"/@([^/?#]+)/video/", source) or re.search(r"authorKwaiId=([^&#\"']+)", source)
        if match:
            return normalize_kwai_id(urllib.parse.unquote(match.group(1)))
    return ""


def account_signature(account_id: str) -> str:
    secret = (ADMIN_PASSWORD or "kokokwai@2026").encode("utf-8")
    return hmac.new(secret, account_id.encode("utf-8"), hashlib.sha256).hexdigest()


def make_account_token(account_id: str) -> str:
    return f"{account_id}.{account_signature(account_id)[:24]}"


def account_id_from_token(token: str) -> str:
    account_id, dot, signature = str(token or "").partition(".")
    if not dot or not account_id or not signature:
        return ""
    expected = account_signature(account_id)[:24]
    return account_id if hmac.compare_digest(signature, expected) else ""


def load_accounts() -> list[dict[str, Any]]:
    accounts = read_json_file(ACCOUNTS_FILE, [])
    if not isinstance(accounts, list):
        accounts = []
    accounts, changed = migrate_account_replacements(accounts)
    seen = {str(item.get("account_id") or "") for item in accounts if isinstance(item, dict)}
    now = now_iso()
    for account in accounts:
        if not isinstance(account, dict):
            continue
        source = str(account.get("source") or "")
        if not account.get("registration_status"):
            account["registration_status"] = "registered" if source == "self_signup" or account.get("registered_at") else "unregistered"
            changed = True
        if account.get("registration_status") == "registered" and not account.get("registered_at"):
            account["registered_at"] = str(account.get("created_at") or now)
            changed = True
        if account.get("registration_status") == "unregistered" and not account.get("provisioned_at"):
            account["provisioned_at"] = str(account.get("created_at") or now)
            changed = True
    for key in DEFAULT_ALLOWED_ACCOUNTS:
        account_id = normalize_account_key(key)
        if account_id and account_id not in seen:
            accounts.append({
                "account_id": account_id,
                "phone": account_id,
                "display_name": account_id,
                "status": "active",
                "created_at": now,
                "provisioned_at": now,
                "registration_status": "unregistered",
                "source": "seed",
                "state": {},
            })
            seen.add(account_id)
            changed = True
    if changed:
        write_json_atomic(ACCOUNTS_FILE, accounts[:5000])
    return [item for item in accounts if isinstance(item, dict)]


def save_accounts(accounts: list[dict[str, Any]]) -> None:
    write_json_atomic(ACCOUNTS_FILE, accounts[:5000])


def public_account(account: dict[str, Any], *, include_state: bool = False) -> dict[str, Any]:
    account_id = str(account.get("account_id") or "").strip()
    submissions = [
        item for item in read_json_file(SUBMISSIONS_FILE, [])
        if isinstance(item, dict) and submission_matches_account(item, account)
    ]
    state = account.get("state") if isinstance(account.get("state"), dict) else {}
    workspace = state.get("workspace") if isinstance(state, dict) and isinstance(state.get("workspace"), dict) else {}
    payload = {
        "account_id": account_id,
        "phone": str(account.get("phone") or account_id),
        "kwai_id": str(account.get("kwai_id") or ""),
        "uid": str(account.get("uid") or ""),
        "login_aliases": sorted(account_aliases(account)),
        "display_name": str(account.get("display_name") or account_id),
        "status": str(account.get("status") or "active"),
        "source": str(account.get("source") or ""),
        "registration_status": str(account.get("registration_status") or "unregistered"),
        "created_at": str(account.get("created_at") or ""),
        "provisioned_at": str(account.get("provisioned_at") or ""),
        "registered_at": str(account.get("registered_at") or ""),
        "last_registered_at": str(account.get("last_registered_at") or ""),
        "updated_at": str(account.get("updated_at") or ""),
        "last_login_at": str(account.get("last_login_at") or ""),
        "saved_count": len(workspace.get("saved") or []),
        "scheduled_count": sum(len(v) for v in (workspace.get("schedule") or {}).values() if isinstance(v, list)) if isinstance(workspace.get("schedule"), dict) else 0,
        "submission_count": len(submissions),
        "submissions": submissions[:50],
    }
    if include_state:
        payload["state"] = state
    return payload


def public_accounts_compact() -> list[dict[str, Any]]:
    """Return the identity fields needed by Creator Ops without workspace blobs."""
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    submission_counts: dict[str, int] = {}
    for item in submissions:
        if not isinstance(item, dict):
            continue
        key = normalize_account_key(str(item.get("creator_id") or ""))
        if key:
            submission_counts[key] = submission_counts.get(key, 0) + 1

    rows: list[dict[str, Any]] = []
    for account in load_accounts():
        account_id = str(account.get("account_id") or "").strip()
        state = account.get("state") if isinstance(account.get("state"), dict) else {}
        workspace = state.get("workspace") if isinstance(state.get("workspace"), dict) else {}
        schedule = workspace.get("schedule") if isinstance(workspace.get("schedule"), dict) else {}
        aliases = sorted(account_aliases(account))
        rows.append({
            "account_id": account_id,
            "phone": str(account.get("phone") or account_id),
            "kwai_id": str(account.get("kwai_id") or ""),
            "uid": str(account.get("uid") or ""),
            "login_aliases": aliases,
            "display_name": str(account.get("display_name") or account_id),
            "status": str(account.get("status") or "active"),
            "source": str(account.get("source") or ""),
            "registration_status": str(account.get("registration_status") or "unregistered"),
            "created_at": str(account.get("created_at") or ""),
            "provisioned_at": str(account.get("provisioned_at") or ""),
            "registered_at": str(account.get("registered_at") or ""),
            "last_registered_at": str(account.get("last_registered_at") or ""),
            "updated_at": str(account.get("updated_at") or ""),
            "last_login_at": str(account.get("last_login_at") or ""),
            "saved_count": len(workspace.get("saved") or []),
            "scheduled_count": sum(len(value) for value in schedule.values() if isinstance(value, list)),
            "submission_count": sum(submission_counts.get(alias, 0) for alias in aliases),
            "submissions": [],
        })
    return rows


def find_account(account_id: str) -> dict[str, Any] | None:
    target = canonical_account_key(account_id)
    phone_target = canonical_account_key(normalize_phone(account_id))
    kwai_target = normalize_kwai_id(account_id)
    for account in load_accounts():
        aliases = account_aliases(account)
        if target in aliases or (phone_target and phone_target in aliases) or (kwai_target and kwai_target in aliases):
            return account
    return None


def creator_password_candidates(account: dict[str, Any], login_id: str) -> set[str]:
    raw_values = [
        login_id,
        account.get("account_id"),
        account.get("phone"),
        *(account.get("login_aliases") or []),
    ]
    candidates: set[str] = set()
    for raw in raw_values:
        digits = re.sub(r"\D+", "", str(raw or ""))
        if digits:
            candidates.add(digits[-4:])
    return candidates


def valid_creator_login_password(account: dict[str, Any], login_id: str, password: str) -> bool:
    supplied = str(password or "").strip()
    if not supplied:
        return False
    return any(secrets.compare_digest(supplied, allowed) for allowed in creator_password_candidates(account, login_id))


def upsert_account(
    account_id: str,
    *,
    source: str = "admin",
    display_name: str = "",
    phone: str = "",
    kwai_id: str = "",
    uid: str = "",
) -> dict[str, Any]:
    clean = canonical_account_key(account_id or phone or kwai_id or uid)
    if not clean:
        raise ValueError("账号只能包含数字、字母、下划线、@、点或短横线。")
    phone_clean = canonical_account_key(normalize_phone(phone or account_id))
    kwai_clean = normalize_kwai_id(kwai_id)
    uid_clean = normalize_account_key(uid)
    login_aliases = sorted({item for item in [clean, phone_clean, kwai_clean, uid_clean] if item})
    accounts = load_accounts()
    now = now_iso()
    for idx, account in enumerate(accounts):
        if clean in account_aliases(account) or any(alias in account_aliases(account) for alias in login_aliases):
            account["status"] = str(account.get("status") or "active")
            account["display_name"] = display_name or str(account.get("display_name") or clean)
            if phone_clean:
                account["phone"] = phone_clean
            if kwai_clean:
                account["kwai_id"] = kwai_clean
            if uid_clean:
                account["uid"] = uid_clean
            account["login_aliases"] = sorted(account_aliases(account).union(login_aliases))
            if source == "self_signup":
                account["registration_status"] = "registered"
                account["registered_at"] = str(account.get("registered_at") or now)
                account["last_registered_at"] = now
            elif not account.get("registration_status"):
                account["registration_status"] = "unregistered"
            account["updated_at"] = now
            accounts[idx] = account
            save_accounts(accounts)
            return public_account(account, include_state=True)
    account = {
        "account_id": clean,
        "phone": phone_clean or clean,
        "kwai_id": kwai_clean,
        "uid": uid_clean,
        "login_aliases": login_aliases,
        "display_name": display_name or clean,
        "status": "active",
        "created_at": now,
        "provisioned_at": "" if source == "self_signup" else now,
        "registration_status": "registered" if source == "self_signup" else "unregistered",
        "registered_at": now if source == "self_signup" else "",
        "last_registered_at": now if source == "self_signup" else "",
        "updated_at": now,
        "source": source,
        "state": {},
    }
    accounts.insert(0, account)
    save_accounts(accounts)
    return public_account(account, include_state=True)


def current_account(headers: Any) -> dict[str, Any] | None:
    account_id = account_id_from_token(cookie_value(headers, CREATOR_AUTH_COOKIE))
    if not account_id:
        return None
    account = find_account(account_id)
    if not account or str(account.get("status") or "active") != "active":
        return None
    return account


def mark_account_registered(account_id: str, *, action: str = "login") -> dict[str, Any] | None:
    target = canonical_account_key(account_id)
    accounts = load_accounts()
    now = now_iso()
    for idx, account in enumerate(accounts):
        if target in account_aliases(account):
            account["registration_status"] = "registered"
            account["registered_at"] = str(account.get("registered_at") or now)
            account["first_seen_at"] = str(account.get("first_seen_at") or now)
            if action == "login":
                account["last_login_at"] = now
            elif action == "register":
                account["last_registered_at"] = now
            account["updated_at"] = now
            accounts[idx] = account
            save_accounts(accounts)
            return account
    return None


def load_analytics_events() -> list[dict[str, Any]]:
    events = read_json_file(ANALYTICS_FILE, [])
    if not isinstance(events, list):
        return []
    return [item for item in events if isinstance(item, dict)]


def save_analytics_events(events: list[dict[str, Any]]) -> None:
    write_json_atomic(ANALYTICS_FILE, events)


def analytics_visitor_id(headers: Any) -> str:
    visitor = normalize_account_key(cookie_value(headers, VISITOR_COOKIE))
    return visitor or uuid4().hex


def analytics_ip_hash(headers: Any) -> str:
    raw = str(headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip() or str(headers.get("X-Real-IP") or "")
    if not raw:
        return ""
    return hashlib.sha256((raw + ADMIN_PASSWORD).encode("utf-8")).hexdigest()[:16]


def append_analytics_event(
    payload: dict[str, Any],
    headers: Any,
    *,
    account: dict[str, Any] | None = None,
    visitor_id: str = "",
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    account = account or current_account(headers)
    event_name = re.sub(r"[^0-9A-Za-z_.:-]+", "", str(payload.get("event") or "event"))[:80] or "event"
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    script_id = normalize_account_key(str(payload.get("script_id") or meta.get("script_id") or ""))
    if script_id and not re.fullmatch(r"[0-9a-f]{32}", script_id):
        script_id = ""
    try:
        duration_ms = max(0, min(12 * 60 * 60 * 1000, int(float(payload.get("duration_ms") or 0))))
    except Exception:
        duration_ms = 0
    event = {
        "event_id": uuid4().hex,
        "event": event_name,
        "created_at": now_iso(),
        "account_id": str(account.get("account_id") or "") if account else "",
        "display_name": str(account.get("display_name") or "") if account else "",
        "visitor_id": visitor_id or analytics_visitor_id(headers),
        "path": str(payload.get("path") or "")[:260],
        "page_type": str(payload.get("page_type") or "")[:80],
        "script_id": script_id,
        "duration_ms": duration_ms,
        "meta": {str(k)[:60]: str(v)[:240] for k, v in meta.items()},
        "referer": str(headers.get("Referer") or "")[:300],
        "user_agent": str(headers.get("User-Agent") or "")[:260],
        "ip_hash": analytics_ip_hash(headers),
    }
    events = load_analytics_events()
    events.append(event)
    save_analytics_events(events)
    return event


def script_id_from_url(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        parsed = urllib.parse.urlparse(text)
        match = re.fullmatch(r"/script/([0-9a-f]{32})", parsed.path or "")
        if match:
            return match.group(1)
        query = urllib.parse.parse_qs(parsed.query or "")
        candidate = str((query.get("script") or [""])[0] or "")
        if re.fullmatch(r"[0-9a-f]{32}", candidate):
            return candidate
    except Exception:
        pass
    return ""


def visitor_cookie_header(visitor_id: str) -> tuple[str, str]:
    return ("Set-Cookie", f"{VISITOR_COOKIE}={urllib.parse.quote(visitor_id)}; Path=/; Max-Age=31536000; SameSite=Lax")


def record_site_open(headers: Any, path: str, *, account: dict[str, Any] | None = None, script_id: str = "", source: str = "server") -> str:
    visitor_id = analytics_visitor_id(headers)
    page_type = "script" if script_id else "portal"
    try:
        append_analytics_event(
            {"event": "site_open", "page_type": page_type, "script_id": script_id, "path": path, "meta": {"source": source}},
            headers,
            account=account,
            visitor_id=visitor_id,
        )
        if script_id:
            append_analytics_event(
                {"event": "script_open", "page_type": "script", "script_id": script_id, "path": path, "meta": {"source": source}},
                headers,
                account=account,
                visitor_id=visitor_id,
            )
    except Exception as exc:
        print(f"analytics_record_failed path={path!r} error={exc}", flush=True)
    return visitor_id


def record_login_referer_open(headers: Any, account: dict[str, Any]) -> None:
    referer = str(headers.get("Referer") or "")
    if not referer:
        return
    script_id = script_id_from_url(referer)
    try:
        parsed = urllib.parse.urlparse(referer)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
    except Exception:
        path = referer[:260]
    record_site_open(headers, path, account=account, script_id=script_id, source="after_login")


def parse_iso_time(value: object) -> datetime | None:
    try:
        text = str(value or "")
        if not text:
            return None
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def event_in_days(event: dict[str, Any], days: int) -> bool:
    created = parse_iso_time(event.get("created_at"))
    if not created:
        return True
    return created >= datetime.now(timezone.utc) - timedelta(days=days)


def analytics_hour_bucket(value: object) -> str:
    created = parse_iso_time(value)
    if not created:
        return ""
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    created = created.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return created.isoformat()


CLICK_EVENT_LABELS = {
    "feature_next": "查看下一个脚本",
    "detail_open": "展开脚本",
    "save_click": "收藏",
    "share_click": "复制分享链接",
    "submit_click": "点击回传入口",
    "submission_created": "完成回传",
    "all_scripts_open": "查看全部推荐脚本",
    "profile_open": "进入个人中心",
    "login": "登录",
    "register": "注册",
}


def submission_matches_account(submission: dict[str, Any], account: dict[str, Any]) -> bool:
    aliases = account_aliases(account)
    creator_id = normalize_account_key(str(submission.get("creator_id") or ""))
    detected_kwai = normalize_kwai_id(str(submission.get("detected_kwai_id") or ""))
    video_kwai = normalize_kwai_id(kwai_handle_from_url(str(submission.get("video_url") or "")))
    return bool(
        (creator_id and creator_id in aliases)
        or (detected_kwai and detected_kwai in aliases)
        or (video_kwai and video_kwai in aliases)
    )


def script_title_for_id(entry_id: str) -> str:
    entry = entry_by_id(entry_id)
    return str(entry.get("title") or "") if entry else ""


def creator_analytics_summary_payload(days: int = 180) -> dict[str, Any]:
    """Return compact dashboard counters and daily account usage aggregates."""
    days = max(1, min(180, int(days or 180)))
    accounts = [item for item in load_accounts() if isinstance(item, dict)]
    alias_lookup = account_alias_lookup(accounts)
    account_alias_sets = {id(account): account_aliases(account) for account in accounts}
    test_accounts = {id(account) for account in accounts if "666" in account_alias_sets[id(account)]}
    events = [event for event in load_analytics_events() if event_in_days(event, days)]
    submissions_raw = read_json_file(SUBMISSIONS_FILE, [])
    submissions = [item for item in (submissions_raw if isinstance(submissions_raw, list) else []) if isinstance(item, dict)]

    visitor_accounts: dict[str, dict[str, Any]] = {}
    for event in events:
        visitor_id = str(event.get("visitor_id") or "").strip()
        account = find_account_from_lookup(str(event.get("account_id") or ""), alias_lookup)
        if visitor_id and account:
            visitor_accounts[visitor_id] = account

    script_opens = 0
    raw_script_opens = 0
    active_account_ids: set[int] = set()
    unique_script_ids: set[str] = set()
    daily_people: dict[str, dict[int, dict[str, str]]] = {}
    daily_script_opens: dict[str, int] = {}
    daily_scripts: dict[str, set[str]] = {}
    for event in events:
        if str(event.get("event") or "") not in {"script_open", "detail_open"}:
            continue
        script_id = str(event.get("script_id") or "").strip()
        if not script_id:
            continue
        raw_script_opens += 1
        account = find_account_from_lookup(str(event.get("account_id") or ""), alias_lookup)
        if not account:
            account = visitor_accounts.get(str(event.get("visitor_id") or "").strip())
        if account and id(account) not in test_accounts:
            script_opens += 1
            active_account_ids.add(id(account))
            unique_script_ids.add(script_id)
            created = parse_iso_time(event.get("created_at"))
            day = created.date().isoformat() if created else str(event.get("created_at") or "")[:10]
            if day:
                account_id = str(account.get("account_id") or account.get("phone") or "").strip()
                daily_people.setdefault(day, {})[id(account)] = {
                    "account_id": account_id,
                    "display_name": str(account.get("display_name") or account_id or "创作者"),
                    "phone": str(account.get("phone") or ""),
                    "kwai_id": str(account.get("kwai_id") or ""),
                }
                daily_script_opens[day] = daily_script_opens.get(day, 0) + 1
                daily_scripts.setdefault(day, set()).add(script_id)

    matched_submission_accounts: set[int] = set()
    submission_count = 0
    for submission in submissions:
        candidates = [
            canonical_account_key(str(submission.get("creator_id") or "")),
            normalize_account_key(normalize_kwai_id(str(submission.get("detected_kwai_id") or ""))),
            normalize_account_key(normalize_kwai_id(kwai_handle_from_url(str(submission.get("video_url") or "")))),
        ]
        account = next((alias_lookup[value] for value in candidates if value and value in alias_lookup), None)
        if account and id(account) not in test_accounts:
            submission_count += 1
            matched_submission_accounts.add(id(account))

    registered_users = sum(
        1
        for account in accounts
        if id(account) not in test_accounts
        and (
            str(account.get("registration_status") or "") == "registered"
            or id(account) in matched_submission_accounts
        )
    )
    return {
        "ok": True,
        "days": days,
        "generated_at": now_iso(),
        "summary": {
            "registered_users": registered_users,
            "script_opens": script_opens,
            "raw_script_opens": raw_script_opens,
            "active_users": len(active_account_ids),
            "unique_scripts_opened": len(unique_script_ids),
            "submissions": submission_count,
        },
        "daily_usage": [
            {
                "day": day,
                "active_users": len(daily_people.get(day, {})),
                "script_opens": daily_script_opens.get(day, 0),
                "unique_scripts_opened": len(daily_scripts.get(day, set())),
                "people": list(daily_people.get(day, {}).values()),
            }
            for day in sorted(daily_people, reverse=True)
        ],
    }


def creator_analytics_payload(days: int = 30, *, include_inactive: bool = False) -> dict[str, Any]:
    days = max(1, min(180, int(days or 30)))
    accounts = load_accounts()
    account_by_id: dict[str, dict[str, Any]] = {}
    for account in accounts:
        if not isinstance(account, dict):
            continue
        for alias in account_aliases(account):
            account_by_id[alias] = account
    events = [event for event in load_analytics_events() if event_in_days(event, days)]
    submissions_raw = read_json_file(SUBMISSIONS_FILE, [])
    submissions = [item for item in (submissions_raw if isinstance(submissions_raw, list) else []) if isinstance(item, dict)]
    title_cache: dict[str, str] = {}
    timeline: dict[str, dict[str, Any]] = {}
    detail_limit = 120

    def cached_script_title(entry_id: str) -> str:
        if entry_id not in title_cache:
            title_cache[entry_id] = script_title_for_id(entry_id)
        return title_cache[entry_id]

    def timeline_row(bucket: str) -> dict[str, Any]:
        row = timeline.setdefault(bucket, {
            "hour": bucket,
            "registered_users": 0,
            "platform_opens": 0,
            "share_link_opens": 0,
            "script_opens": 0,
            "script_duration_seconds": 0,
            "registered_details": [],
            "platform_open_details": [],
            "script_open_details": [],
            "duration_details": [],
            "_platform_people": {},
            "_script_people": {},
            "_duration_people": {},
        })
        return row

    def person_from_account(account: dict[str, Any] | None, fallback_id: str = "") -> dict[str, str]:
        account = account or {}
        account_id = str(account.get("account_id") or fallback_id or "")
        return {
            "account_id": account_id,
            "display_name": str(account.get("display_name") or account_id or "匿名访客"),
            "phone": str(account.get("phone") or ""),
            "kwai_id": str(account.get("kwai_id") or ""),
            "uid": str(account.get("uid") or ""),
        }

    def person_from_event(event: dict[str, Any]) -> dict[str, str]:
        account_id = canonical_account_key(str(event.get("account_id") or ""))
        person = person_from_account(account_by_id.get(account_id), account_id or str(event.get("visitor_id") or ""))
        if not person.get("display_name") or person.get("display_name") == "匿名访客":
            person["display_name"] = str(event.get("display_name") or person.get("account_id") or "匿名访客")
        person["visitor_id"] = str(event.get("visitor_id") or "")
        return person

    def append_timeline_detail(row: dict[str, Any], key: str, detail: dict[str, Any]) -> None:
        details = row.setdefault(key, [])
        if isinstance(details, list) and len(details) < detail_limit:
            details.append(detail)

    def time_value_in_days(value: object) -> bool:
        created = parse_iso_time(value)
        if not created:
            return False
        return created >= datetime.now(timezone.utc) - timedelta(days=days)

    for event in events:
        bucket = analytics_hour_bucket(event.get("created_at"))
        if not bucket:
            continue
        row = timeline_row(bucket)
        name = str(event.get("event") or "")
        page_type = str(event.get("page_type") or "")
        script_id = str(event.get("script_id") or "")
        is_script = page_type == "script" or bool(script_id)
        person = person_from_event(event)
        actor_key = person.get("account_id") or person.get("visitor_id") or str(event.get("event_id") or "")
        if name == "site_open":
            detail = {
                **person,
                "time": str(event.get("created_at") or ""),
                "path": str(event.get("path") or ""),
                "referer": str(event.get("referer") or ""),
                "source": "分享链接" if is_script else "直接打开",
                "script_id": script_id,
                "script_title": cached_script_title(script_id) if script_id else "",
            }
            row["platform_opens"] = int(row.get("platform_opens") or 0) + 1
            row["_platform_people"][actor_key] = person
            append_timeline_detail(row, "platform_open_details", detail)
        if name in {"script_open", "detail_open"} and script_id:
            detail = {
                **person,
                "time": str(event.get("created_at") or ""),
                "path": str(event.get("path") or ""),
                "referer": str(event.get("referer") or ""),
                "source": "分享链接" if name == "script_open" else "站内点开",
                "script_id": script_id,
                "script_title": cached_script_title(script_id),
            }
            row["script_opens"] = int(row.get("script_opens") or 0) + 1
            row["share_link_opens"] = int(row.get("share_link_opens") or 0) + 1
            row["_script_people"][actor_key] = person
            append_timeline_detail(row, "script_open_details", detail)
        if name == "page_duration":
            duration_seconds = round(int(event.get("duration_ms") or 0) / 1000)
            if is_script:
                row["script_duration_seconds"] = int(row.get("script_duration_seconds") or 0) + duration_seconds
            row["_duration_people"][actor_key] = person
            append_timeline_detail(row, "duration_details", {
                **person,
                "time": str(event.get("created_at") or ""),
                "duration_seconds": duration_seconds,
                "page_type": page_type or ("script" if is_script else "platform"),
                "path": str(event.get("path") or ""),
                "referer": str(event.get("referer") or ""),
                "script_id": script_id,
                "script_title": cached_script_title(script_id) if script_id else "",
            })

    events_by_account: dict[str, list[dict[str, Any]]] = {}
    events_by_visitor: dict[str, list[dict[str, Any]]] = {}
    visitor_ids_by_account: dict[str, set[str]] = {}
    for event in events:
        event_account_id = canonical_account_key(str(event.get("account_id") or ""))
        visitor_id = str(event.get("visitor_id") or "")
        events_by_account.setdefault(event_account_id, []).append(event)
        if visitor_id:
            events_by_visitor.setdefault(visitor_id, []).append(event)
        if event_account_id and visitor_id:
            visitor_ids_by_account.setdefault(event_account_id, set()).add(visitor_id)

    users: list[dict[str, Any]] = []
    inactive_users: list[dict[str, Any]] = []
    for account in accounts:
        account_id = str(account.get("account_id") or "")
        seen_event_ids: set[str] = set()
        user_events: list[dict[str, Any]] = []
        for event in events_by_account.get(account_id, []):
            event_id = str(event.get("event_id") or "")
            if event_id and event_id in seen_event_ids:
                continue
            if event_id:
                seen_event_ids.add(event_id)
            user_events.append(event)
        for visitor_id in visitor_ids_by_account.get(account_id, set()):
            for event in events_by_visitor.get(visitor_id, []):
                event_id = str(event.get("event_id") or "")
                if event_id and event_id in seen_event_ids:
                    continue
                if event_id:
                    seen_event_ids.add(event_id)
                user_events.append(event)
        user_submissions = [item for item in submissions if submission_matches_account(item, account)]
        registered_bucket = analytics_hour_bucket(account.get("registered_at") or account.get("last_registered_at"))
        if not registered_bucket and user_submissions:
            first_submission = min((str(item.get("created_at") or "") for item in user_submissions if item.get("created_at")), default="")
            registered_bucket = analytics_hour_bucket(first_submission)
        if registered_bucket and time_value_in_days(registered_bucket):
            row = timeline_row(registered_bucket)
            row["registered_users"] = int(row.get("registered_users") or 0) + 1
            append_timeline_detail(row, "registered_details", {
                **person_from_account(account),
                "time": str(account.get("last_registered_at") or account.get("registered_at") or (user_submissions[0].get("created_at") if user_submissions else "")),
                "source": "注册/首次回传",
            })
        clicks: dict[str, int] = {}
        script_stats: dict[str, dict[str, Any]] = {}
        platform_open_count = 0
        script_open_count = 0
        platform_duration_ms = 0
        script_duration_ms = 0
        for event in user_events:
            name = str(event.get("event") or "")
            page_type = str(event.get("page_type") or "")
            script_id = str(event.get("script_id") or "")
            if name == "site_open":
                platform_open_count += 1
            if name in {"script_open", "detail_open"} and script_id:
                script_open_count += 1
            if name == "page_duration":
                duration_ms = int(event.get("duration_ms") or 0)
                if page_type == "script" or script_id:
                    script_duration_ms += duration_ms
                    if script_id:
                        row = script_stats.setdefault(script_id, {"script_id": script_id, "title": cached_script_title(script_id), "views": 0, "duration_ms": 0})
                        row["duration_ms"] = int(row.get("duration_ms") or 0) + duration_ms
                else:
                    platform_duration_ms += duration_ms
            if name in CLICK_EVENT_LABELS:
                clicks[name] = clicks.get(name, 0) + 1
            if script_id and name in {"script_open", "detail_open"}:
                row = script_stats.setdefault(script_id, {"script_id": script_id, "title": cached_script_title(script_id), "views": 0, "duration_ms": 0})
                row["views"] = int(row.get("views") or 0) + 1
        has_behavior = bool(
            user_events
            or user_submissions
            or str(account.get("registration_status") or "") == "registered"
            or account.get("registered_at")
            or account.get("last_login_at")
        )
        if not has_behavior:
            inactive_users.append({
                "account_id": account_id,
                "phone": str(account.get("phone") or account_id),
                "display_name": str(account.get("display_name") or account_id),
                "registration_status": str(account.get("registration_status") or "unregistered"),
                "created_at": str(account.get("created_at") or ""),
                "provisioned_at": str(account.get("provisioned_at") or ""),
            })
            continue
        state = account.get("state") if isinstance(account.get("state"), dict) else {}
        workspace = state.get("workspace") if isinstance(state, dict) and isinstance(state.get("workspace"), dict) else {}
        users.append({
            "account_id": account_id,
            "phone": str(account.get("phone") or account_id),
            "kwai_id": str(account.get("kwai_id") or ""),
            "uid": str(account.get("uid") or ""),
            "login_aliases": sorted(account_aliases(account)),
            "display_name": str(account.get("display_name") or account_id),
            "status": str(account.get("status") or "active"),
            "source": str(account.get("source") or ""),
            "registration_status": str(account.get("registration_status") or "unregistered"),
            "created_at": str(account.get("created_at") or ""),
            "provisioned_at": str(account.get("provisioned_at") or ""),
            "registered_at": str(account.get("registered_at") or ""),
            "last_registered_at": str(account.get("last_registered_at") or ""),
            "updated_at": str(account.get("updated_at") or ""),
            "last_login_at": str(account.get("last_login_at") or ""),
            "saved_count": len(workspace.get("saved") or []),
            "scheduled_count": sum(len(v) for v in (workspace.get("schedule") or {}).values() if isinstance(v, list)) if isinstance(workspace.get("schedule"), dict) else 0,
            "platform_open_count": platform_open_count,
            "script_share_open_count": script_open_count,
            "platform_duration_seconds": round(platform_duration_ms / 1000),
            "script_duration_seconds": round(script_duration_ms / 1000),
            "click_counts": clicks,
            "click_labels": CLICK_EVENT_LABELS,
            "script_views": sorted(script_stats.values(), key=lambda item: (int(item.get("views") or 0), int(item.get("duration_ms") or 0)), reverse=True)[:20],
            "submission_count": len(user_submissions),
            "submissions": user_submissions[:30],
            "last_event_at": max([str(event.get("created_at") or "") for event in user_events] or [""]),
            "recent_events": sorted(user_events, key=lambda item: str(item.get("created_at") or ""), reverse=True)[:30],
        })
    users.sort(key=lambda item: (item.get("registration_status") == "registered", str(item.get("last_event_at") or ""), int(item.get("platform_open_count") or 0) + int(item.get("script_share_open_count") or 0)), reverse=True)
    inactive_users.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    timeline_rows = []
    for row in sorted(timeline.values(), key=lambda item: str(item.get("hour") or ""), reverse=True):
        script_opens_for_hour = int(row.get("script_opens") or 0)
        duration_for_hour = int(row.get("script_duration_seconds") or 0)
        row["koko_opens"] = int(row.get("platform_opens") or 0) + int(row.get("share_link_opens") or 0)
        row["platform_people_count"] = len(row.get("_platform_people") or {})
        row["script_people_count"] = len(row.get("_script_people") or {})
        row["duration_people_count"] = len(row.get("_duration_people") or {})
        row.pop("_platform_people", None)
        row.pop("_script_people", None)
        row.pop("_duration_people", None)
        row["avg_script_duration_seconds"] = round(duration_for_hour / script_opens_for_hour) if script_opens_for_hour else 0
        timeline_rows.append(row)
    return {
        "ok": True,
        "days": days,
        "timeline": {"hourly": timeline_rows},
        "summary": {
            "accounts": len(accounts),
            "active_accounts": len(users),
            "inactive_accounts": len(inactive_users),
            "registered": sum(1 for item in users if item.get("registration_status") == "registered"),
            "unregistered": sum(1 for item in accounts if str(item.get("registration_status") or "unregistered") != "registered"),
            "events": len(events),
            "submissions": len(submissions),
            "platform_opens": sum(int(item.get("platform_open_count") or 0) for item in users),
            "script_opens": sum(int(item.get("script_share_open_count") or 0) for item in users),
        },
        "users": users,
        "inactive_users": inactive_users if include_inactive else [],
        "inactive_loaded": bool(include_inactive),
    }

def update_account_state(account_id: str, state_patch: dict[str, Any]) -> dict[str, Any]:
    clean = canonical_account_key(account_id)
    accounts = load_accounts()
    for idx, account in enumerate(accounts):
        if clean in account_aliases(account):
            state = account.get("state") if isinstance(account.get("state"), dict) else {}
            for key in ["preferences", "workspace", "profile_ui", "language"]:
                if key in state_patch:
                    state[key] = state_patch[key]
            account["state"] = state
            account["updated_at"] = now_iso()
            accounts[idx] = account
            save_accounts(accounts)
            return public_account(account, include_state=True)
    raise ValueError("Account not found.")


def update_account_profile(account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    account = find_account(account_id)
    if not account:
        raise ValueError("Account not found.")
    phone = str(account.get("phone") or account_id or "").strip()
    kwai_id = str(payload.get("kwai_id") or "").strip()
    display_name = str(payload.get("display_name") or payload.get("name") or "").strip()
    if not kwai_id:
        raise ValueError("Kwai ID is required.")
    return upsert_account(
        str(account.get("account_id") or account_id or phone or kwai_id),
        source=str(account.get("source") or "self_signup"),
        display_name=display_name or kwai_id,
        phone=phone,
        kwai_id=kwai_id,
        uid=str(account.get("uid") or ""),
    )


def delete_account(account_id: str) -> bool:
    aliases = account_aliases({"account_id": account_id, "phone": account_id})
    aliases.add(canonical_account_key(account_id))
    aliases.add(canonical_account_key(normalize_phone(account_id)))
    aliases.add(normalize_kwai_id(account_id))
    aliases = {item for item in aliases if item}
    if not aliases:
        return False
    accounts = load_accounts()
    next_accounts = [
        account for account in accounts
        if not (account_aliases(account) & aliases)
    ]
    if len(next_accounts) == len(accounts):
        return False
    save_accounts(next_accounts)
    return True


def public_admin_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entry = normalized_entry(entry)
    entry_id = str(entry.get("entry_id") or "").strip()
    manual_tags = entry.get("manual_tags") if isinstance(entry.get("manual_tags"), dict) else {}
    duration_bucket = duration_bucket_for_entry(entry)
    duration_seconds = entry_duration_seconds(entry)
    result = {
        "entry_id": entry_id,
        "title": str(entry.get("title") or ""),
        "summary": entry_summary(entry),
        "content_type": str(entry.get("content_type") or DEFAULT_CONTENT_TYPE),
        "video_url": abs_url(entry.get("video_url"), ""),
        "reference_video_enabled": entry.get("reference_video_enabled") is not False,
        "publish_datetime": str(manual_tags.get("publish_datetime") or entry.get("publish_datetime") or ""),
        "library_date": str(entry.get("library_date") or entry.get("saved_at") or entry.get("created_at") or "")[:10],
        "cover_url": abs_url(entry.get("preview_image_url") or entry.get("thumbnail_url") or ""),
        "storyboard_image_url": abs_url(entry.get("storyboard_image_url") or entry.get("preview_image_url") or entry.get("thumbnail_url") or ""),
        "thumbnail_url": f"/api/creator/thumbnail/{entry_id}.webp" if entry_id else "",
        "html_url": abs_url(entry.get("pt_html_url") or entry.get("html_url") or entry.get("zh_html_url")),
        "zh_html_url": abs_url(entry.get("zh_html_url") or entry.get("html_url") or entry.get("pt_html_url")),
        "created_at": str(entry.get("created_at") or entry.get("saved_at") or ""),
        "duration_bucket": duration_bucket,
        "duration_seconds": round(duration_seconds, 2) if duration_seconds > 0 else 0,
        "duration_label_pt": DURATION_LABELS.get(duration_bucket, {}).get("pt", ""),
        "duration_label_zh": DURATION_LABELS.get(duration_bucket, {}).get("zh", ""),
        "published": bool(entry.get("creator_published", True)),
        "overridden": bool(entry.get("creator_override")),
    }
    for dimension in ["relationship", "format", "location", "content"]:
        result[f"{dimension}_tags"] = list(entry.get(f"{dimension}_tags") or [])
        result[f"{dimension}_tag_labels_zh"] = list(entry.get(f"{dimension}_tag_labels_zh") or [])
        result[f"{dimension}_tag_labels_pt"] = list(entry.get(f"{dimension}_tag_labels_pt") or [])
    result["taxonomy_version"] = str(entry.get("taxonomy_version") or "")
    result["taxonomy_source"] = str(entry.get("taxonomy_source") or "")
    result["taxonomy_confidence"] = str(entry.get("taxonomy_confidence") or "")
    return result


def normalize_kwai_url(url: str) -> str:
    text = str(url or "").strip()
    if text and not text.startswith(("http://", "https://")):
        text = "https://" + text
    return text


def kwai_handle_from_url(url: str) -> str:
    path = urllib.parse.urlparse(normalize_kwai_url(url)).path
    match = re.search(r"/@([^/?#]+)", path)
    return match.group(1).strip() if match else ""


def meta_content(html_text: str, key: str) -> str:
    pattern = rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']'
    match = re.search(pattern, html_text, re.I)
    return html.unescape(match.group(1).strip()) if match else ""


def fetch_kwai_profile(url: str) -> dict[str, Any]:
    profile_url = normalize_kwai_url(url)
    if "kwai.com/" not in profile_url:
        raise ValueError("请输入 Kwai 作者主页链接。")
    html_text = fetch_text(profile_url, timeout=24)
    title = meta_content(html_text, "og:title") or meta_content(html_text, "twitter:title")
    if not title:
        match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.I | re.S)
        title = html.unescape(re.sub(r"\s+", " ", match.group(1)).strip()) if match else ""
    handle = kwai_handle_from_url(profile_url)
    name = ""
    title_match = re.search(r"^(.*?)\s*\(@([^)]+)\)\s+on\s+Kwai", title)
    if title_match:
        name = title_match.group(1).strip()
        handle = handle or title_match.group(2).strip()
    else:
        name = re.sub(r"\s*\(@.*?\)\s+on\s+Kwai.*$", "", title).strip()
    avatar = meta_content(html_text, "og:image") or meta_content(html_text, "twitter:image")
    description = meta_content(html_text, "og:description") or meta_content(html_text, "twitter:description")
    follower_count = ""
    for pattern in [
        r'"(?:followerCount|followers|fanCount|fans)"\s*:\s*"?([\d,.万wkKmM]+)"?',
        r'([\d,.]+[KkMm]?)\s*(?:followers|fans)',
        r'([\d,.]+)\s*(?:Seguidores|seguidores)',
    ]:
        match = re.search(pattern, html_text, re.I)
        if match:
            follower_count = match.group(1).strip()
            break
    return {
        "kwai_url": profile_url,
        "kwai_id": handle,
        "name": name or handle or "Kwai creator",
        "avatar_url": avatar,
        "followers": follower_count,
        "bio": description,
        "fetched_at": now_iso(),
    }


def load_creator_profiles() -> list[dict[str, Any]]:
    data = read_json_file(CREATORS_FILE, [])
    profiles = [item for item in data if isinstance(item, dict)]
    changed = False
    for profile in profiles:
        account_id = str(profile.get("account_id") or "")
        phone = str(profile.get("phone") or "")
        next_account_id = canonical_account_key(account_id)
        next_phone = canonical_account_key(normalize_phone(phone)) if phone else ""
        if account_id and next_account_id != account_id:
            profile["account_id"] = next_account_id
            changed = True
        if phone and next_phone and next_phone != phone:
            profile["phone"] = next_phone
            changed = True
    if changed:
        save_creator_profiles(profiles)
    return profiles


def save_creator_profiles(profiles: list[dict[str, Any]]) -> None:
    write_json_atomic(CREATORS_FILE, profiles[:2000])


def list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in re.split(r"[、,，/]", text) if item.strip()]


def category_tokens(categories: list[str], creator_type: dict[str, Any] | None = None) -> set[str]:
    tokens: set[str] = set()
    mapping = {
        "夫妻关系": ["夫妻", "妻子", "丈夫", "情侣", "夫妻吵架", "夫妻欺骗", "夫妻算计", "妻管严"],
        "整蛊恶搞": ["整蛊", "恶作剧", "夫妻整蛊"],
        "骗局反转": ["骗子", "反转", "隐瞒", "秘密", "发现"],
        "赖账/金钱冲突": ["赖账", "欠钱", "付款", "金钱", "逃单"],
        "偷吃/偷懒/耍小聪明": ["偷吃", "偷懒", "偷奸耍滑", "装病", "耍小聪明"],
        "热门": [],
    }
    for category in categories:
        text = str(category or "").strip()
        if text:
            tokens.add(text)
        tokens.update(mapping.get(text, []))
    type_mapping = {
        "夫妻": ["夫妻", "妻子", "丈夫", "老婆", "老公", "casal", "esposa", "marido"],
        "情侣": ["情侣", "女友", "男友", "namorado", "namorada", "casal"],
        "家庭": ["家庭", "家人", "妈妈", "爸爸", "孩子", "família", "mãe", "pai", "filho"],
        "朋友": ["朋友", "闺蜜", "兄弟", "amigo", "amiga", "colega"],
        "家里": ["家里", "家庭", "卧室", "客厅", "厨房", "casa", "quarto", "cozinha"],
        "乡村": ["乡村", "农村", "田野", "工厂", "roça", "rural", "campo", "fazenda"],
        "城市": ["城市", "街道", "公司", "办公室", "rua", "cidade", "empresa", "escritório"],
    }
    if isinstance(creator_type, dict):
        for field in ("identity", "location"):
            for label in list_field(creator_type.get(field)):
                tokens.add(label)
                tokens.update(type_mapping.get(label, []))
    return {token for token in tokens if token}


def ranked_scripts_for_creator(
    categories: list[str],
    limit: int = 80,
    entries: list[dict[str, Any]] | None = None,
    creator_type: dict[str, Any] | None = None,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    tokens = category_tokens(categories, creator_type)
    if not tokens:
        return 0, []
    scored: list[tuple[int, int, dict[str, Any]]] = []
    source_entries = entries if entries is not None else load_entries()
    for idx, entry in enumerate(source_entries):
        text = " ".join([
            str(entry.get("content_type") or ""),
            str(entry.get("title") or ""),
            entry_summary(entry),
            str(entry.get("content_type_reasoning") or ""),
        ])
        score = 0
        for token in tokens:
            if token and token in text:
                score += 18 if token == str(entry.get("content_type") or "") else 8
        score += max(0, 12 - min(idx, 12))
        if score > 0:
            scored.append((score, idx, entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    public_scripts: list[dict[str, Any]] = []
    start = max(0, offset)
    end = start + max(0, limit)
    for score, _, entry in scored[start:end]:
        public = public_entry(entry, 0)
        public["match_score"] = score
        public["share_url"] = f"/script/{public['entry_id']}"
        public_scripts.append(public)
    return len(scored), public_scripts


def scripts_for_creator(categories: list[str], limit: int = 80, entries: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return ranked_scripts_for_creator(categories, limit, entries=entries)[1]


def public_creator_profile(
    profile: dict[str, Any],
    include_scripts: bool = True,
    *,
    entries: list[dict[str, Any]] | None = None,
    submissions: list[dict[str, Any]] | None = None,
    script_preview_limit: int | None = None,
    account_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    categories = [str(item or "").strip() for item in profile.get("categories") or [] if str(item or "").strip()]
    script_limit = 80 if script_preview_limit is None else max(0, script_preview_limit)
    creator_type = profile.get("creator_type") if isinstance(profile.get("creator_type"), dict) else {}
    script_total, scripts = ranked_scripts_for_creator(categories, script_limit, entries=entries, creator_type=creator_type) if include_scripts else (0, [])
    submissions = submissions if submissions is not None else read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    account_key = str(profile.get("account_id") or profile.get("phone") or profile.get("kwai_id") or profile.get("uid") or "")
    account = find_account_from_lookup(account_key, account_lookup) if account_lookup is not None else find_account(account_key)
    account_public: dict[str, Any] = {}
    if account:
        state = account.get("state") if isinstance(account.get("state"), dict) else {}
        workspace = state.get("workspace") if isinstance(state.get("workspace"), dict) else {}
        schedule = workspace.get("schedule") if isinstance(workspace.get("schedule"), dict) else {}
        account_public = {
            "account_id": str(account.get("account_id") or ""),
            "phone": str(account.get("phone") or account.get("account_id") or ""),
            "kwai_id": str(account.get("kwai_id") or ""),
            "uid": str(account.get("uid") or ""),
            "display_name": str(account.get("display_name") or account.get("account_id") or ""),
            "status": str(account.get("status") or "active"),
            "last_login_at": str(account.get("last_login_at") or ""),
            "saved_count": len(workspace.get("saved") or []),
            "scheduled_count": sum(len(v) for v in schedule.values() if isinstance(v, list)),
            "submission_count": 0,
        }
    creator_keys = {
        normalize_account_key(profile.get("profile_id") or ""),
        normalize_account_key(profile.get("account_id") or ""),
        normalize_account_key(profile.get("phone") or ""),
        normalize_account_key(profile.get("uid") or ""),
        normalize_kwai_id(profile.get("kwai_id") or ""),
    }

    creator_keys.update(account_aliases(account) if account else set())
    creator_keys = {item for item in creator_keys if item}
    creator_kwai = normalize_kwai_id(profile.get("kwai_id") or "")
    matched_submissions = [
        item for item in submissions
        if isinstance(item, dict)
        and (
            normalize_account_key(item.get("creator_id") or "") in creator_keys
            or (creator_kwai and submission_kwai_id(item) == creator_kwai)
        )
    ]
    if account_public:
        account_public["submission_count"] = len(matched_submissions)
    submission_by_script: dict[str, list[dict[str, Any]]] = {}
    for item in matched_submissions:
        submission_by_script.setdefault(str(item.get("entry_id") or ""), []).append(item)
    for script in scripts:
        script["submission_count"] = len(submission_by_script.get(str(script.get("entry_id") or ""), []))
        script["submissions"] = submission_by_script.get(str(script.get("entry_id") or ""), [])[:20]
    fake_submissions = []
    if not matched_submissions and scripts:
        fake_submissions = [{
            "submission_id": f"fake-{profile.get('profile_id')}",
            "entry_id": scripts[0].get("entry_id"),
            "script_title": scripts[0].get("title"),
            "submitted_title": "待回传：作者完成拍摄后会出现在这里",
            "thumbnail_url": scripts[0].get("thumbnail_url"),
            "video_url": "",
            "status": "placeholder",
            "created_at": "",
        }]
    visible_scripts = scripts if script_preview_limit is None else scripts[:max(0, script_preview_limit)]
    priority_limit = 6 if script_preview_limit is None else min(2, len(visible_scripts))
    return {
        **profile,
        "categories": categories,
        "account": account_public,
        "account_id": str(profile.get("account_id") or account_public.get("account_id") or ""),
        "phone": str(profile.get("phone") or account_public.get("phone") or ""),
        "uid": str(profile.get("uid") or account_public.get("uid") or ""),
        "creator_type": creator_type,
        "cooperation_level": str(profile.get("cooperation_level") or "待标注"),
        "creator_description": str(profile.get("creator_description") or profile.get("notes") or ""),
        "fed_script_count": script_total,
        "returned_script_count": len({str(item.get("entry_id") or "") for item in matched_submissions if isinstance(item, dict)}),
        "submission_count": len(matched_submissions),
        "matched_scripts": visible_scripts,
        "priority_scripts": visible_scripts[:priority_limit],
        "folded_count": max(0, script_total - priority_limit),
        "submissions": matched_submissions or fake_submissions,
    }


def public_creator_profiles() -> list[dict[str, Any]]:
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    account_lookup = account_alias_lookup()
    profiles = [
        public_creator_profile(item, include_scripts=False, submissions=submissions, script_preview_limit=0, account_lookup=account_lookup)
        for item in load_creator_profiles()
    ]
    profiles.sort(key=lambda item: (int(item.get("submission_count") or 0), int(item.get("returned_script_count") or 0), str(item.get("updated_at") or "")), reverse=True)
    return profiles


def creator_recommendations_for_profile(profile_id: str, limit: int = 5, offset: int = 0) -> dict[str, Any] | None:
    profile = next((item for item in load_creator_profiles() if str(item.get("profile_id") or "") == profile_id), None)
    if not profile:
        return None
    categories = [str(item or "").strip() for item in profile.get("categories") or [] if str(item or "").strip()]
    creator_type = profile.get("creator_type") if isinstance(profile.get("creator_type"), dict) else {}
    total, scripts = ranked_scripts_for_creator(categories, max(1, min(50, limit)), creator_type=creator_type, offset=max(0, offset))
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    creator_kwai = normalize_kwai_id(profile.get("kwai_id") or "")
    creator_keys = {
        normalize_account_key(profile.get("profile_id") or ""),
        normalize_account_key(profile.get("account_id") or ""),
        normalize_account_key(profile.get("phone") or ""),
        normalize_account_key(profile.get("uid") or ""),
        creator_kwai,
    }
    creator_keys = {item for item in creator_keys if item}
    matched_submissions = [
        item for item in submissions
        if isinstance(item, dict)
        and (
            normalize_account_key(item.get("creator_id") or "") in creator_keys
            or (creator_kwai and submission_kwai_id(item) == creator_kwai)
        )
    ]
    submission_by_script: dict[str, list[dict[str, Any]]] = {}
    for item in matched_submissions:
        submission_by_script.setdefault(str(item.get("entry_id") or ""), []).append(item)
    for script in scripts:
        script["submission_count"] = len(submission_by_script.get(str(script.get("entry_id") or ""), []))
        script["submissions"] = submission_by_script.get(str(script.get("entry_id") or ""), [])[:20]
    return {
        "profile_id": profile_id,
        "categories": categories,
        "creator_type": creator_type,
        "total": total,
        "limit": max(1, min(50, limit)),
        "offset": max(0, offset),
        "scripts": scripts,
    }


def create_or_update_creator_profile(payload: dict[str, Any], profile_id: str | None = None) -> dict[str, Any]:
    categories = payload.get("categories")
    if not isinstance(categories, list):
        categories = [item.strip() for item in str(payload.get("category") or "").split(",") if item.strip()]
    categories = [str(item or "").strip() for item in categories if str(item or "").strip()]
    kwai_url = normalize_kwai_url(str(payload.get("kwai_url") or payload.get("url") or "").strip())
    if not kwai_url:
        raise ValueError("请输入 Kwai 作者主页链接。")
    fetched: dict[str, Any] = {}
    if not payload.get("skip_fetch"):
        try:
            fetched = fetch_kwai_profile(kwai_url)
        except Exception:
            fetched = {}
    provided_kwai_id = normalize_kwai_id(payload.get("kwai_id") or fetched.get("kwai_id") or kwai_handle_from_url(kwai_url))
    provided_phone = normalize_phone(payload.get("phone") or "")
    provided_uid = normalize_account_key(str(payload.get("uid") or ""))
    display_name = str(payload.get("display_name") or payload.get("name") or fetched.get("name") or provided_kwai_id or provided_phone or provided_uid or "Kwai creator").strip()
    account_public = upsert_account(
        str(payload.get("account_id") or provided_phone or provided_kwai_id or provided_uid or ""),
        source="creator_profile",
        display_name=display_name,
        phone=provided_phone,
        kwai_id=provided_kwai_id,
        uid=provided_uid,
    )
    profiles = load_creator_profiles()
    existing_index = -1
    for idx, item in enumerate(profiles):
        if profile_id and str(item.get("profile_id") or "") == profile_id:
            existing_index = idx
            break
        if not profile_id and (
            str(item.get("kwai_url") or "") == kwai_url
            or (provided_uid and str(item.get("uid") or "") == provided_uid)
            or (provided_kwai_id and normalize_kwai_id(item.get("kwai_id") or "") == provided_kwai_id)
        ):
            existing_index = idx
            break
    base = profiles[existing_index] if existing_index >= 0 else {}
    creator_type = base.get("creator_type") if isinstance(base.get("creator_type"), dict) else {}
    incoming_creator_type = payload.get("creator_type") if isinstance(payload.get("creator_type"), dict) else {}
    creator_type = {**creator_type, **incoming_creator_type}
    for field in ["identity", "location"]:
        if field in payload or f"creator_{field}" in payload:
            values = list_field(payload.get(field) if field in payload else payload.get(f"creator_{field}"))
            creator_type[field] = values
        elif field in incoming_creator_type:
            creator_type[field] = list_field(incoming_creator_type.get(field))
    profile = {
        **base,
        **fetched,
        "profile_id": str(base.get("profile_id") or profile_id or uuid4().hex),
        "account_id": str(account_public.get("account_id") or ""),
        "phone": provided_phone or str(base.get("phone") or account_public.get("phone") or ""),
        "uid": provided_uid or str(base.get("uid") or account_public.get("uid") or ""),
        "kwai_id": provided_kwai_id or str(base.get("kwai_id") or ""),
        "name": display_name,
        "avatar_url": str(payload.get("avatar_url") or fetched.get("avatar_url") or base.get("avatar_url") or ""),
        "followers": str(payload.get("followers") or fetched.get("followers") or base.get("followers") or ""),
        "likes": str(payload.get("likes") or payload.get("likes_count") or base.get("likes") or ""),
        "favorites": str(payload.get("favorites") or payload.get("favorites_count") or base.get("favorites") or ""),
        "poc": str(payload.get("poc") or payload.get("owner") or base.get("poc") or "").strip(),
        "categories": categories,
        "creator_type": creator_type,
        "cooperation_level": str(payload.get("cooperation_level") or base.get("cooperation_level") or "待标注").strip(),
        "creator_description": str(payload.get("creator_description") or payload.get("description") or base.get("creator_description") or "").strip(),
        "notes": str(payload.get("notes") or base.get("notes") or "").strip(),
        "updated_at": now_iso(),
        "created_at": str(base.get("created_at") or now_iso()),
    }
    if existing_index >= 0:
        profiles[existing_index] = profile
    else:
        profiles.insert(0, profile)
    save_creator_profiles(profiles)
    return public_creator_profile(profile, include_scripts=False, script_preview_limit=0)


def delete_creator_profile(profile_id: str) -> bool:
    profiles = load_creator_profiles()
    next_profiles = [item for item in profiles if str(item.get("profile_id") or "") != profile_id]
    if len(next_profiles) == len(profiles):
        return False
    save_creator_profiles(next_profiles)
    return True


def import_creator_profiles(payload: dict[str, Any]) -> dict[str, Any]:
    raw_creators = payload.get("creators")
    if not isinstance(raw_creators, list):
        raise ValueError("creators must be a list.")
    results: list[dict[str, Any]] = []
    imported = 0
    failed = 0
    for idx, item in enumerate(raw_creators, start=1):
        if not isinstance(item, dict):
            failed += 1
            results.append({"row": idx, "status": "failed", "error": "Invalid creator row."})
            continue
        try:
            creator = create_or_update_creator_profile({**item, "skip_fetch": bool(payload.get("skip_fetch", True))})
            imported += 1
            results.append({
                "row": idx,
                "status": "imported",
                "profile_id": creator.get("profile_id"),
                "account_id": creator.get("account_id"),
                "kwai_id": creator.get("kwai_id"),
                "name": creator.get("name"),
                "submission_count": creator.get("submission_count", 0),
            })
        except Exception as exc:
            failed += 1
            results.append({
                "row": idx,
                "status": "failed",
                "kwai_url": item.get("kwai_url") or item.get("url") or "",
                "error": str(exc),
            })
    return {"ok": failed == 0, "imported": imported, "failed": failed, "total": len(raw_creators), "results": results}


def invalidate_entry_cache(entry_id: str) -> None:
    invalidate_library_snapshot()
    cache = read_json_file(THUMB_CACHE_FILE, {})
    if isinstance(cache, dict) and entry_id in cache:
        cache.pop(entry_id, None)
        write_json_atomic(THUMB_CACHE_FILE, cache)
    html_cache = SCRIPT_HTML_CACHE_DIR / f"{entry_id}.html"
    if html_cache.exists():
        try:
            html_cache.unlink()
        except OSError:
            pass


def update_admin_entry(entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        raise ValueError("Invalid script id.")
    if not admin_entry_by_id(entry_id):
        raise ValueError("Script not found.")
    overrides = load_overrides()
    override = dict(overrides.get(entry_id) or {})
    field_map = {
        "title": "title",
        "summary": "whole_video_summary",
        "content_type": "content_type",
        "video_url": "video_url",
        "cover_url": "preview_image_url",
        "storyboard_image_url": "storyboard_image_url",
        "html_url": "html_url",
        "zh_html_url": "zh_html_url",
        "pt_html_url": "pt_html_url",
        "duration_bucket": "duration_bucket",
        "duration_seconds": "duration_seconds",
    }
    for incoming, target in field_map.items():
        if incoming in payload:
            override[target] = str(payload.get(incoming) or "").strip()
    if "published" in payload:
        override["hidden"] = not bool(payload.get("published"))
    override.pop("deleted", None)
    override["updated_at"] = now_iso()
    overrides[entry_id] = override
    save_overrides(overrides)
    invalidate_entry_cache(entry_id)
    updated = admin_entry_by_id(entry_id)
    if not updated:
        raise ValueError("Script not found.")
    return public_admin_entry(updated)


def delete_admin_entries(entry_ids: list[str]) -> dict[str, Any]:
    overrides = load_overrides()
    existing = {str(entry.get("entry_id") or "") for entry in load_entries_raw()}
    deleted: list[str] = []
    missing: list[str] = []
    for raw_id in entry_ids:
        entry_id = str(raw_id or "").strip()
        if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
            continue
        if entry_id not in existing:
            missing.append(entry_id)
            continue
        override = dict(overrides.get(entry_id) or {})
        override["deleted"] = True
        override["hidden"] = True
        override["updated_at"] = now_iso()
        overrides[entry_id] = override
        invalidate_entry_cache(entry_id)
        deleted.append(entry_id)
    save_overrides(overrides)
    return {"deleted": deleted, "missing": missing}


def admin_html() -> str:
    labels_json = json.dumps(content_type_labels(), ensure_ascii=False)
    template = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Koko Creator Admin</title>__FAVICON_LINKS__<style>
*{{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}body{{margin:0;background:#fff6ee;color:#1f1f1f}}button,input,textarea,select{{font:inherit}}.wrap{{width:min(1180px,100%);margin:0 auto;padding:24px}}.top{{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:18px}}h1{{margin:0;font-size:36px;line-height:1.05}}.muted{{color:#707782;font-weight:650}}.toolbar{{display:grid;grid-template-columns:1fr auto auto;gap:10px;margin:18px 0}}input,textarea,select{{width:100%;border:1px solid #ff5f002e;border-radius:16px;background:white;padding:12px 14px;outline:none}}textarea{{min-height:96px;resize:vertical}}button{{border:1px solid #ff5f0030;border-radius:999px;background:white;color:#ff5f00;font-weight:900;padding:11px 16px;cursor:pointer}}button.primary{{border-color:#ff5f00;background:#ff5f00;color:white}}button.danger{{color:#d64520}}button:disabled{{opacity:.5;cursor:not-allowed}}.grid{{display:grid;gap:12px}}.card{{display:grid;grid-template-columns:32px 92px 1fr auto;gap:12px;align-items:center;border:1px solid #ff5f001f;border-radius:22px;background:white;padding:12px;box-shadow:0 10px 24px #552d0a0e}}.card img{{width:92px;aspect-ratio:9/16;border-radius:14px;object-fit:cover;background:#2a1d16}}.card h3{{margin:0 0 7px;font-size:17px;line-height:1.25}}.card p{{margin:0;color:#707782;font-size:13px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.meta{{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}}.pill{{border:1px solid #ff5f0026;border-radius:999px;padding:5px 9px;color:#ff5f00;background:#fff7f0;font-size:12px;font-weight:800}}.pill.off{{color:#777;background:#f4f4f4;border-color:#ddd}}.actions{{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}}.login{{min-height:100vh;display:grid;place-items:center;padding:22px}}.login form,.modal-card{{width:min(520px,100%);border:1px solid #ff5f0024;border-radius:28px;background:white;padding:24px;box-shadow:0 22px 54px #552d0a18}}.login h1{{text-align:center;margin-bottom:18px}}.status{{min-height:24px;color:#707782;font-weight:800}}.modal{{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:#20130b55;padding:14px;z-index:20}}.modal.open{{display:flex}}.modal-card{{max-height:92vh;overflow:auto}}.modal-card h2{{margin:0 0 14px}}.fields{{display:grid;gap:10px}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.modal-actions{{display:flex;justify-content:flex-end;gap:10px;margin-top:16px;flex-wrap:wrap}}.empty{{padding:28px;border:1px dashed #ff5f0040;border-radius:20px;text-align:center;color:#707782;background:white}}@media(max-width:760px){{.toolbar{{grid-template-columns:1fr}}.card{{grid-template-columns:28px 76px 1fr}}.card img{{width:76px}}.actions{{grid-column:2/4;justify-content:flex-start}}.row{{grid-template-columns:1fr}}}}
</style></head><body><main id="app"></main><div class="modal" id="edit-modal"><form class="modal-card" id="edit-form"><h2>编辑脚本</h2><div class="fields"><input name="title" placeholder="标题"><textarea name="summary" placeholder="摘要"></textarea><div class="row"><select name="content_type"></select><label><input name="published" type="checkbox" style="width:auto;margin-right:8px">上架显示</label></div><input name="video_url" placeholder="视频链接"><input name="cover_url" placeholder="封面链接"><input name="html_url" placeholder="HTML 链接"><input name="zh_html_url" placeholder="中文 HTML 链接"></div><div class="modal-actions"><button type="button" id="edit-cancel">取消</button><button class="primary" type="submit">保存</button></div></form></div><script>
const labels=__LABELS_JSON__;let entries=[];let editing=null;const app=document.querySelector("#app");const modal=document.querySelector("#edit-modal");const form=document.querySelector("#edit-form");
function esc(s){{return String(s??"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[c]))}}
async function api(url,opts={{}}){{const r=await fetch(url,{{headers:{{"Content-Type":"application/json"}},...opts}});const d=await r.json().catch(()=>({{}}));if(!r.ok)throw new Error(d.error||"请求失败");return d}}
function loginView(msg=""){{app.innerHTML=`<section class="login"><form id="login-form"><h1>Koko Creator 后台</h1><p class="muted">输入后台密码后可以管理创作者中心脚本。</p><input name="password" type="password" placeholder="后台密码" autofocus><button class="primary" style="width:100%;margin-top:12px" type="submit">进入后台</button><p class="status">${{esc(msg)}}</p></form></section>`}}
function adminView(){{app.innerHTML=`<section class="wrap"><div class="top"><div><h1>Koko Creator 后台</h1><p class="muted">管理 Creator 侧展示：搜索、批量删除、修改标题/摘要/分类/视频/封面/HTML、上下架。</p></div><div><a href="/creator-portal" target="_blank"><button type="button">打开前台</button></a><button class="primary" id="sync-now" type="button">立刻同步</button></div></div><div class="toolbar"><input id="search" placeholder="搜索脚本标题、摘要、分类"><button id="delete-selected" class="danger" type="button">批量删除</button><button id="refresh" type="button">刷新</button></div><p id="status" class="status"></p><div id="list" class="grid"></div></section>`;document.querySelector("#search").addEventListener("input",renderList);document.querySelector("#refresh").addEventListener("click",loadEntries);document.querySelector("#delete-selected").addEventListener("click",bulkDelete);document.querySelector("#sync-now").addEventListener("click",syncNow);renderList()}}
function filteredEntries(){{const q=String(document.querySelector("#search")?.value||"").trim().toLowerCase();if(!q)return entries;return entries.filter(e=>[e.title,e.summary,e.content_type,e.video_url].join(" ").toLowerCase().includes(q))}}
function renderList(){{const list=document.querySelector("#list");if(!list)return;const rows=filteredEntries();if(!rows.length){{list.innerHTML=`<div class="empty">没有匹配脚本</div>`;return}}list.innerHTML=rows.map(e=>`<article class="card"><input type="checkbox" data-pick="${{esc(e.entry_id)}}"><img src="${{esc(e.cover_url||e.thumbnail_url)}}" loading="lazy" alt=""><div><h3>${{esc(e.title||"Untitled")}}</h3><p>${{esc(e.summary||"")}}</p><div class="meta"><span class="pill">${{esc(e.content_type||"待分类")}}</span><span class="pill ${{e.published?"":"off"}}">${{e.published?"已上架":"已下架"}}</span>${{e.overridden?`<span class="pill">已修改</span>`:""}}</div></div><div class="actions"><button type="button" data-edit="${{esc(e.entry_id)}}">编辑</button><button type="button" data-toggle="${{esc(e.entry_id)}}">${{e.published?"下架":"上架"}}</button></div></article>`).join("")}}
async function loadEntries(){{try{{document.querySelector("#status")&&(document.querySelector("#status").textContent="加载中...");const d=await api("/api/admin/scripts");entries=d.entries||[];adminView();document.querySelector("#status").textContent=`共 ${{entries.length}} 条脚本`}}catch(e){{loginView(e.message)}}}}
function openEdit(id){{editing=entries.find(e=>e.entry_id===id);if(!editing)return;form.title.value=editing.title||"";form.summary.value=editing.summary||"";form.content_type.innerHTML=labels.map(x=>`<option value="${{esc(x)}}">${{esc(x)}}</option>`).join("");form.content_type.value=editing.content_type||"待分类";form.published.checked=!!editing.published;form.video_url.value=editing.video_url||"";form.cover_url.value=editing.cover_url||"";form.html_url.value=editing.html_url||"";form.zh_html_url.value=editing.zh_html_url||"";modal.classList.add("open")}}
async function saveEdit(ev){{ev.preventDefault();if(!editing)return;const payload=Object.fromEntries(new FormData(form).entries());payload.published=form.published.checked;await api(`/api/admin/scripts/${{editing.entry_id}}`,{{method:"POST",body:JSON.stringify(payload)}});modal.classList.remove("open");await loadEntries()}}
async function togglePublish(id){{const e=entries.find(x=>x.entry_id===id);if(!e)return;await api(`/api/admin/scripts/${{id}}`,{{method:"POST",body:JSON.stringify({{published:!e.published}})}});await loadEntries()}}
async function bulkDelete(){{const ids=[...document.querySelectorAll("[data-pick]:checked")].map(x=>x.dataset.pick);if(!ids.length)return alert("请先选择脚本");if(!confirm(`确定删除 Creator 后台里的 ${{ids.length}} 条脚本吗？`))return;await api("/api/admin/scripts/bulk-delete",{{method:"POST",body:JSON.stringify({{entry_ids:ids}})}});await loadEntries()}}
async function syncNow(){{const s=document.querySelector("#status");s.textContent="同步中...";await api("/api/creator/sync-library",{{method:"POST",body:"{}"}});await loadEntries()}}
document.addEventListener("submit",async e=>{{if(e.target.id==="login-form"){{e.preventDefault();try{{await api("/api/admin/login",{{method:"POST",body:JSON.stringify({{password:new FormData(e.target).get("password")}})}});await loadEntries()}}catch(err){{loginView(err.message)}}}}}});
document.addEventListener("click",e=>{{const edit=e.target.closest("[data-edit]");if(edit)openEdit(edit.dataset.edit);const toggle=e.target.closest("[data-toggle]");if(toggle)togglePublish(toggle.dataset.toggle)}});document.querySelector("#edit-cancel").addEventListener("click",()=>modal.classList.remove("open"));form.addEventListener("submit",saveEdit);loadEntries();
</script></body></html>"""
    return template.replace("{{", "{").replace("}}", "}").replace("__LABELS_JSON__", labels_json).replace("__FAVICON_LINKS__", FAVICON_LINKS)


FAVICON_LINKS = """<link rel="icon" type="image/svg+xml" href="/favicon.svg?v=kwai1"><link rel="shortcut icon" href="/favicon.ico?v=kwai1">"""


@lru_cache(maxsize=1)
def page_html() -> str:
    questions_json = json.dumps(QUESTIONS, ensure_ascii=False)
    profile_override_css = """.profile-hero{min-height:0;margin:-22px -22px 14px;padding:12px 14px 16px;background:linear-gradient(135deg,#32180b,#ff5f00 64%,#ffb36f);overflow:visible}.profile-cover{inset:0;height:132px;border-radius:0;background:radial-gradient(circle at 72% 16%,#ff8a1c,#8a3205 50%,#2a160d);filter:none}.profile-cover:after{background:linear-gradient(180deg,#00000018,#00000042)}.profile-tools{position:relative;top:auto;right:auto;justify-content:flex-end;margin-bottom:44px}.profile-upload{min-height:30px;padding:0 11px;border-color:#ffffff70;background:#ffffff24;font-size:11px;white-space:nowrap}.profile-info{position:relative;margin-top:-12px;padding:14px;border-radius:24px;background:#fffffff2;color:#1f1f1f;box-shadow:0 18px 38px #552d0a24}.profile-row{align-items:center;gap:12px}.profile-avatar{width:78px;height:78px;flex:0 0 78px;border:4px solid #fff;box-shadow:0 10px 24px #552d0a22}.profile-name{margin:0 0 6px;color:#1f1f1f;font-size:25px;text-shadow:none}.profile-bio{color:#69707a;font-size:13px;line-height:1.42}.profile-stats{margin-top:14px;padding:11px 8px;border-radius:18px;background:#fff7f0;border:1px solid #ff5f0018;text-align:center}.profile-stats b{color:#1f1f1f;font-size:19px}.profile-stats span{color:#69707a;font-size:12px;font-weight:800}.profile-prefs{margin-top:12px;gap:7px}.profile-prefs .chip{padding:7px 10px;background:#fff;color:#ff5f00;border-color:#ff5f0045;box-shadow:none;font-size:11px}.profile-card-strip{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0 12px}.profile-mini{min-height:58px;border-radius:18px;background:#fff;border:1px solid #ff5f0016;box-shadow:0 8px 18px #552d0a10;font-size:11px}.profile-mini b{font-size:17px;margin-bottom:2px}.profile-tabs{top:64px;margin:0 -22px 10px;padding:8px 18px}.profile-tabs .tabs button{padding:8px 12px;font-size:12px}#saved-feed .state{margin:0;border-radius:24px;padding:26px 20px}@media(max-width:380px){.profile-upload{padding:0 8px;font-size:10px}.profile-avatar{width:68px;height:68px;flex-basis:68px}.profile-name{font-size:22px}.profile-info{padding:12px}.profile-tabs .tabs button{padding:8px 10px}}"""
    profile_override_css += """.profile-hero{min-height:0!important;margin:-22px -22px 14px!important;padding:12px 14px 16px!important;overflow:visible!important}.profile-tools{position:relative!important;top:auto!important;right:auto!important;margin-bottom:44px!important}.profile-logout{border-color:#ff5f0038!important;background:#fff!important;color:#ff5f00!important}.profile-info{position:relative!important;margin-top:-12px!important;padding:14px!important;border-radius:24px!important;background:#fffffff2!important;color:#1f1f1f!important}.profile-row{align-items:center!important}.profile-avatar{width:78px!important;height:78px!important;flex:0 0 78px!important}.profile-name{color:#1f1f1f!important;font-size:25px!important;text-shadow:none!important}.profile-bio{color:#69707a!important;font-size:13px!important;line-height:1.42!important}.profile-stats{grid-template-columns:repeat(2,1fr)!important;margin-top:14px!important;padding:11px 8px!important;border-radius:18px!important;background:#fff7f0!important;text-align:center!important}.profile-stats b{color:#1f1f1f!important}.profile-stats span{color:#69707a!important}.profile-prefs .chip{background:#fff!important;color:#ff5f00!important;border-color:#ff5f0045!important}.profile-card-strip{grid-template-columns:repeat(3,minmax(0,1fr))!important}.profile-mini{min-height:58px!important}.profile-tabs{padding:8px 18px!important}.submission-feed{display:grid;gap:12px}.submission-card{display:grid;grid-template-columns:112px 1fr;gap:12px;align-items:center;padding:10px;border:1px solid #ff5f0022;border-radius:18px;background:#fff;box-shadow:0 10px 22px #552d0a10;color:#1f1f1f;text-decoration:none}.submission-cover{width:112px;aspect-ratio:9/16;border-radius:14px;object-fit:cover;background:#2a1d16}.submission-title{margin:0;font-size:15px;line-height:1.35;font-weight:900}.submission-time{margin-top:8px;color:#69707a;font-size:12px;font-weight:800}.submission-url{margin-top:7px;color:#ff5f00;font-size:11px;line-height:1.35;word-break:break-all}"""
    profile_override_css += """.profile-hero{margin:-22px -22px 8px!important;padding:8px 12px 10px!important}.profile-cover{height:78px!important}.profile-tools{margin-bottom:10px!important;gap:6px!important}.profile-upload{min-height:28px!important;padding:0 9px!important;font-size:10px!important}.profile-info{margin-top:0!important;padding:10px 12px!important;border-radius:20px!important}.profile-row{gap:10px!important}.profile-avatar{width:50px!important;height:50px!important;flex:0 0 50px!important;border-width:3px!important}.profile-name{font-size:22px!important;margin-bottom:2px!important;line-height:1!important}.profile-bio{font-size:11px!important;line-height:1.25!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}.profile-stats{margin-top:8px!important;padding:7px 8px!important;border-radius:14px!important}.profile-stats b{font-size:16px!important;line-height:1!important}.profile-stats span{font-size:10px!important;line-height:1.1!important}.profile-prefs{display:flex!important}.profile-card-strip{margin:8px 0 10px!important;gap:8px!important}.profile-mini{min-height:50px!important;border-radius:16px!important}.profile-mini b{font-size:15px!important;margin-bottom:1px!important}.profile-mini span{font-size:11px!important;line-height:1.1!important}.profile-tabs{display:none!important}#saved-feed{margin-top:0!important}@media(max-width:380px){.profile-tools{margin-bottom:8px!important}.profile-info{padding:9px 10px!important}.profile-avatar{width:46px!important;height:46px!important;flex-basis:46px!important}.profile-name{font-size:20px!important}.profile-card-strip{gap:6px!important}.profile-mini{min-height:48px!important}}"""
    profile_override_css += """.profile-stats{grid-template-columns:1fr!important;max-width:170px!important;margin-left:62px!important;padding:8px 12px!important}.profile-stats>div:nth-child(n+2){display:none!important}.profile-data-panel{margin:16px 0 12px!important}.profile-data-panel h2{margin:0 0 10px!important;font-size:28px!important;line-height:1.05!important;color:#1f1f1f!important;font-weight:950!important}.profile-data-grid{display:grid!important;grid-template-columns:1fr!important;gap:10px!important}.profile-data-item{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;min-height:68px!important;padding:14px 16px!important;border:1px solid #ff5f0024!important;border-radius:22px!important;background:#fff!important;box-shadow:0 12px 26px #552d0a0d!important}.profile-data-item b{display:block!important;color:#ff5f00!important;font-size:34px!important;line-height:1!important;font-weight:950!important}.profile-data-item span{display:block!important;color:#69707a!important;font-size:14px!important;line-height:1.25!important;font-weight:900!important;text-align:right!important}@media(max-width:380px){.profile-stats{margin-left:56px!important;max-width:150px!important}.profile-data-panel h2{font-size:25px!important}.profile-data-item b{font-size:30px!important}.profile-data-item span{font-size:13px!important}}"""
    profile_override_css += """.featured-shell{display:grid;gap:14px}.featured-card{overflow:hidden;border-radius:30px;background:#fff;border:1px solid #ff5f0026;box-shadow:0 22px 48px #552d0a18}.featured-media{position:relative;min-height:350px;background:#2a1d16;overflow:hidden}.featured-media img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.featured-media:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000018,#00000000 48%,#0000003f)}.featured-badge{position:absolute;left:14px;top:14px;z-index:1;border-radius:999px;padding:8px 12px;background:#fffffff0;color:#ff5f00;font-size:12px;font-weight:950;box-shadow:0 8px 22px #00000022}.featured-score{position:absolute;right:14px;top:14px;z-index:1;border-radius:999px;padding:8px 10px;background:#ff5f00;color:white;font-size:12px;font-weight:950}.featured-body{padding:16px 14px 16px}.featured-title{margin:0 0 10px;font-size:23px;line-height:1.2;font-weight:950;letter-spacing:0}.featured-summary{margin:0 0 13px;color:#69707a;font-size:14px;line-height:1.55;font-weight:750}.featured-tags{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px}.featured-actions{display:grid;grid-template-columns:1fr;gap:10px}.featured-actions .primary,.featured-actions .secondary,.featured-actions .featured-icon{width:100%;min-height:50px}.featured-icon{border:1px solid #ff5f0028;border-radius:999px;background:#fff7f0;color:#ff5f00;font-size:15px;font-weight:950}.featured-next{width:100%;min-height:46px;margin-top:10px;border:0;border-radius:999px;background:#fff7f0;color:#69707a;font-size:13px;font-weight:900}.view-all-card{width:100%;margin-top:14px;padding:15px 16px;border:1px solid #ff5f0028;border-radius:22px;background:#ffffffd8;color:#1f1f1f;text-align:left;box-shadow:0 12px 30px #552d0a10}.view-all-card b{display:block;margin-bottom:4px;color:#ff5f00;font-size:15px}.view-all-card span{color:#69707a;font-size:13px;font-weight:750}.all-title-row{display:flex;align-items:center;gap:10px;margin-bottom:12px}.all-title-row h1{margin:0;font-size:30px;line-height:1.1;flex:1}.back-pill{border:1px solid #ff5f0038;border-radius:999px;min-height:38px;padding:0 12px;background:#fff7f0;color:#ff5f00;font-size:12px;font-weight:900}.all-scripts-load{display:grid;justify-items:center;gap:10px;padding:24px 12px 10px;color:#6f7078;font-size:13px;font-weight:800}.all-scripts-load .primary{width:min(100%,360px);min-height:46px}.all-scripts-load .primary:disabled{opacity:.65}@media(max-width:380px){.featured-media{min-height:312px}.featured-title{font-size:21px}}"""
    profile_override_css += """.schedule-overlay{position:fixed;inset:0;z-index:90;display:none;align-items:flex-end;background:#1f1f1f66;padding:16px 12px 0}.schedule-overlay.active{display:flex}.schedule-sheet{width:min(100%,480px);max-height:88vh;margin:0 auto;overflow:auto;border-radius:28px 28px 0 0;background:#fffaf5;padding:18px;box-shadow:0 -18px 44px #00000024}.schedule-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.schedule-head h2{margin:0;font-size:23px;line-height:1.15}.schedule-close{border:0;width:38px;height:38px;border-radius:50%;background:#fff0e8;color:#ff5f00;font-weight:950}.calendar-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin:12px 0}.calendar-day{min-height:48px;border:1px solid #ff5f0018;border-radius:14px;background:white;color:#1f1f1f;font-weight:900}.calendar-day.muted{color:#b8b8b8;background:#fffaf7}.calendar-day.selected{background:#ff5f00;color:white;border-color:#ff5f00;box-shadow:0 8px 18px #ff5f0030}.calendar-weekday{display:grid;place-items:center;color:#69707a;font-size:11px;font-weight:900}.schedule-note{margin:0;color:#69707a;font-size:13px;line-height:1.45;font-weight:750}.schedule-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.schedule-actions button{min-height:48px}.schedule-list{display:grid;gap:12px}.schedule-day-card{padding:12px;border:1px solid #ff5f0020;border-radius:20px;background:white;box-shadow:0 10px 22px #552d0a0d}.schedule-day-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;color:#ff5f00;font-size:14px;font-weight:950}.schedule-item{display:grid;grid-template-columns:64px 1fr;gap:10px;align-items:center;padding:8px 0;border-top:1px solid #ff5f0014}.schedule-item:first-of-type{border-top:0}.schedule-item img{width:64px;aspect-ratio:1/1;border-radius:14px;object-fit:cover;background:#2a1d16}.schedule-item h3{margin:0;font-size:14px;line-height:1.3}.schedule-item p{margin:5px 0 0;color:#69707a;font-size:12px;line-height:1.35}.schedule-empty{padding:22px;border-radius:22px;background:white;border:1px solid #ff5f0018}.schedule-empty h3{margin:0 0 8px;font-size:20px}.schedule-empty p{margin:0;color:#69707a;line-height:1.5;font-weight:750}"""
    profile_override_css += """.shoot-calendar{display:grid;gap:14px}.shoot-calendar-panel{border-radius:28px;background:#fff;border:1px solid #ff5f0020;box-shadow:0 16px 34px #552d0a10;padding:14px}.shoot-calendar-head{display:grid;grid-template-columns:42px 1fr 42px;align-items:center;gap:8px;margin-bottom:10px}.shoot-month-btn{width:42px;height:42px;border:0;border-radius:50%;background:#fff0e8;color:#ff5f00;font-size:20px;font-weight:950}.shoot-month-title{text-align:center}.shoot-month-title b{display:block;font-size:20px;line-height:1.15}.shoot-month-title span{display:block;margin-top:3px;color:#69707a;font-size:12px;font-weight:800}.shoot-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}.shoot-weekday{display:grid;place-items:center;height:24px;color:#9a9a9a;font-size:11px;font-weight:900}.shoot-day{position:relative;min-height:54px;border:1px solid transparent;border-radius:16px;background:#fff8f3;color:#1f1f1f;font-size:14px;font-weight:900}.shoot-day.outside{color:#c8c8c8;background:#fffaf8}.shoot-day.active{background:#ff5f00;color:white;border-color:#ff5f00;box-shadow:0 10px 20px #ff5f0030}.shoot-day.has-items{border-color:#ff5f0042;background:#fff3eb}.shoot-day.active.has-items{background:#ff5f00}.shoot-dot{position:absolute;left:50%;bottom:7px;transform:translateX(-50%);min-width:16px;height:16px;border-radius:999px;display:grid;place-items:center;background:#ff5f00;color:white;font-size:9px;line-height:1;font-weight:950}.shoot-day.active .shoot-dot{background:white;color:#ff5f00}.shoot-agenda{display:grid;gap:10px}.shoot-agenda-title{display:flex;align-items:center;justify-content:space-between;padding:0 4px;color:#1f1f1f;font-size:15px;font-weight:950}.shoot-agenda-title span{color:#69707a;font-size:12px;font-weight:850}.shoot-empty{padding:20px;border-radius:22px;background:white;border:1px solid #ff5f0018;color:#69707a;line-height:1.5;font-weight:750}.shoot-empty b{display:block;margin-bottom:7px;color:#1f1f1f;font-size:19px}.schedule-item{border:1px solid #ff5f0018;border-radius:20px;background:white;padding:10px;box-shadow:0 10px 22px #552d0a0d}.schedule-item:first-of-type{border-top:1px solid #ff5f0018}@media(max-width:380px){.shoot-day{min-height:48px;border-radius:14px}.shoot-calendar-panel{padding:12px;border-radius:24px}}"""
    profile_override_css += """.title-row{align-items:flex-start}.title-row h1{min-width:0}.reselect-title{flex:0 0 auto;max-width:152px;min-height:44px;padding:0 14px;white-space:normal;line-height:1.12;text-align:center}.featured-actions .primary,.featured-actions .featured-icon,.featured-next{display:inline-flex;align-items:center;justify-content:center;gap:8px}.btn-ico{display:inline-grid;place-items:center;width:20px;height:20px;flex:0 0 20px;font-size:16px;line-height:1}.featured-next .btn-ico{font-size:15px}@media(max-width:380px){.reselect-title{max-width:134px;font-size:11px;padding:0 10px}.title-row{gap:8px}}"""
    profile_override_css += """.title-row{display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;align-items:center!important;gap:6px!important;margin:0 0 8px!important}.title-row h1{min-width:0!important;font-size:22px!important;line-height:1!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;display:block!important;letter-spacing:-.01em!important}.reselect-title{align-self:center!important;min-height:24px!important;height:24px!important;max-width:82px!important;padding:0 6px!important;border-width:1px!important;border-color:#ff5f0048!important;background:#fffaf5!important;box-shadow:none!important;font-size:8px!important;line-height:1!important;white-space:nowrap!important}.profile-hero{padding-top:8px!important}.profile-info .profile-tools{position:static!important;display:flex!important;justify-content:flex-end!important;gap:5px!important;margin:0 0 8px!important}.profile-info .profile-upload{min-height:25px!important;padding:0 8px!important;border-color:#ff5f0030!important;background:#fff7f0!important;color:#ff5f00!important;font-size:9px!important;line-height:1!important;box-shadow:none!important}.profile-info .profile-logout{background:#fff!important}.profile-info{padding-top:8px!important}@media(max-width:380px){.title-row h1{font-size:20px!important}.reselect-title{max-width:76px!important;font-size:7.5px!important;padding:0 5px!important}.profile-info .profile-upload{padding:0 7px!important}}"""

    profile_override_css += """.bottom{grid-template-columns:repeat(3,1fr)!important}.mission-view{display:grid!important;gap:14px}.mission-hero{position:relative;overflow:hidden;border:1px solid #ff5f0024;border-radius:28px;background:linear-gradient(135deg,#fffaf5,#fff0e7 58%,#ffe0c7);padding:18px 16px;box-shadow:0 18px 42px #552d0a14}.mission-hero:after{content:"";position:absolute;right:-34px;top:-42px;width:132px;height:132px;border-radius:50%;background:radial-gradient(circle,#ff7a0030,#ff7a0000 66%)}.mission-kicker{display:inline-flex;align-items:center;gap:6px;border:1px solid #ff5f0036;border-radius:999px;padding:6px 10px;background:#fff;color:#ff5f00;font-size:11px;font-weight:950}.mission-title{margin:10px 0 6px;font-size:28px;line-height:1.05;font-weight:950;letter-spacing:-.02em}.mission-lead{margin:0;color:#69707a;font-size:13px;line-height:1.45;font-weight:760}.mission-progress{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}.mission-stat{border:1px solid #ff5f001e;border-radius:18px;background:#fff;padding:10px 8px;text-align:center}.mission-stat b{display:block;color:#1f1f1f;font-size:19px;line-height:1}.mission-stat span{display:block;margin-top:4px;color:#69707a;font-size:10px;font-weight:850}.mission-bar{height:9px;margin-top:13px;border-radius:999px;background:#fff;border:1px solid #ff5f001a;overflow:hidden}.mission-bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#ff7a00,#ff4d00);border-radius:999px;transition:width .25s ease}.mission-section{border:1px solid #ff5f001d;border-radius:24px;background:#ffffffd8;padding:14px;box-shadow:0 14px 30px #552d0a0d}.mission-section-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.mission-section h2{margin:0;font-size:18px;line-height:1.15}.mission-section p{margin:4px 0 0;color:#69707a;font-size:12px;font-weight:760}.mission-chip{border:1px solid #ff5f0030;border-radius:999px;background:#fff7f0;color:#ff5f00;padding:6px 10px;font-size:11px;font-weight:950;white-space:nowrap}.mission-list{display:grid;gap:10px}.mission-task{display:grid;grid-template-columns:72px 1fr;gap:10px;align-items:center;border:1px solid #ff5f001f;border-radius:18px;background:#fff;padding:8px;color:#1f1f1f;text-align:left}.mission-task.selected{border-color:#ff5f00;box-shadow:0 10px 24px #ff5f0016}.mission-task.done{border-color:#2dbb6a55;background:#f5fff8}.mission-task img{width:72px;aspect-ratio:1/1;border-radius:14px;object-fit:cover;background:#f8f0e9}.mission-task h3{margin:0 0 6px;font-size:14px;line-height:1.22;font-weight:950;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.mission-task small{display:block;color:#69707a;font-size:11px;font-weight:800}.mission-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px}.mission-actions button{min-height:28px;border-radius:999px;border:1px solid #ff5f0028;background:#fff7f0;color:#ff5f00;padding:0 9px;font-size:10px;font-weight:950}.mission-actions .solid{border-color:#ff5f00;background:#ff5f00;color:#fff}.mission-empty{padding:18px;border:1px dashed #ff5f0030;border-radius:18px;background:#fffaf5;color:#69707a;font-size:13px;font-weight:760;text-align:center}.leaderboard{display:grid;gap:8px}.leader-row{display:grid;grid-template-columns:28px 1fr auto;align-items:center;gap:9px;border:1px solid #ff5f0018;border-radius:16px;background:#fff;padding:9px 10px}.leader-rank{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#fff0e8;color:#ff5f00;font-size:12px;font-weight:950}.leader-name{font-size:13px;font-weight:950}.leader-score{color:#69707a;font-size:11px;font-weight:900}@media(max-width:380px){.mission-title{font-size:25px}.mission-task{grid-template-columns:66px 1fr}.mission-task img{width:66px}.mission-progress{gap:6px}.mission-stat b{font-size:17px}}"""
    profile_override_css += """.mission-topline{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.mission-topline h1{margin:0;font-size:24px;line-height:1.05}.mission-topline p{margin:3px 0 0;color:#69707a;font-size:12px;font-weight:780}.mission-mini-actions{display:flex;gap:7px}.mission-mini-actions button{min-height:30px;border:1px solid #ff5f0030;border-radius:999px;background:#fff7f0;color:#ff5f00;padding:0 10px;font-size:10px;font-weight:950}.mission-candidates{margin-top:0}.mission-plan{background:linear-gradient(180deg,#fff,#fff8f2)}.mission-task.plan{grid-template-columns:82px 1fr}.mission-task.plan img{width:82px}.mission-step{display:inline-flex;align-items:center;gap:5px;border-radius:999px;background:#fff0e8;color:#ff5f00;padding:4px 8px;font-size:10px;font-weight:950;margin-bottom:6px}.mission-data-grid{display:grid;grid-template-columns:1fr;gap:12px}.mission-calendar{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-top:10px}.mission-day{min-height:48px;border:1px solid #ff5f001e;border-radius:14px;background:#fff;text-align:center;padding:7px 2px}.mission-day b{display:block;color:#1f1f1f;font-size:13px;line-height:1}.mission-day span{display:block;margin-top:4px;color:#69707a;font-size:9px;font-weight:850}.mission-day.done{background:#f1fff5;border-color:#35bf704d}.mission-day.partial{background:#fff7ee;border-color:#ff5f0042}.mission-day.empty{opacity:.78}.mission-day.done b,.mission-day.done span{color:#15904d}.mission-popup{position:fixed;inset:0;z-index:95;display:none;align-items:flex-end;background:#1f1f1f66;padding:16px 12px 0}.mission-popup.active{display:flex}.mission-sheet{width:min(100%,480px);max-height:86vh;overflow:auto;margin:0 auto;border-radius:28px 28px 0 0;background:#fffaf5;padding:18px;box-shadow:0 -18px 44px #00000024}.mission-sheet h2{margin:0 0 8px;font-size:24px;line-height:1.08}.mission-sheet p{margin:0 0 12px;color:#69707a;font-size:13px;line-height:1.5;font-weight:760}.mission-prize{border:1px solid #ff5f0026;border-radius:22px;background:linear-gradient(135deg,#fff,#fff0e5);padding:14px;margin:12px 0}.mission-prize b{display:block;color:#ff5f00;font-size:28px;line-height:1}.mission-checks{display:grid;gap:10px;margin:12px 0}.mission-checks label{display:flex;align-items:center;gap:9px;border:1px solid #ff5f001e;border-radius:16px;background:#fff;padding:10px;color:#1f1f1f;font-size:13px;font-weight:850}.mission-checks input{width:18px;height:18px}.mission-popup-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.mission-popup-actions button{min-height:46px;border-radius:999px;border:1px solid #ff5f0030;background:#fff;color:#ff5f00;font-weight:950}.mission-popup-actions .primary{border:0;background:linear-gradient(90deg,#ff6a00,#ff5200);color:#fff}.mission-popup-actions .primary:disabled{opacity:.45}.mission-board-highlight{display:grid;gap:8px;margin-top:10px}@media(max-width:380px){.mission-topline h1{font-size:22px}.mission-task.plan{grid-template-columns:72px 1fr}.mission-task.plan img{width:72px}.mission-popup-actions{grid-template-columns:1fr}}"""
    profile_override_css += """.mission-popup{align-items:center!important;padding:18px!important}.mission-sheet{border-radius:28px!important;max-height:min(82vh,620px)!important;box-shadow:0 24px 70px #0000002b!important}.mission-candidates .mission-topline{margin-bottom:12px!important}.mission-candidates .mission-topline h1{font-size:25px!important}.mission-candidates .mission-topline p{display:none!important}.mission-candidate-grid{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important}.mission-candidate-grid .mission-task{display:block!important;min-width:0!important;padding:6px!important;border-radius:16px!important}.mission-candidate-grid .mission-task img{width:100%!important;aspect-ratio:1/1!important;border-radius:12px!important;display:block!important}.mission-candidate-grid .mission-task h3{margin:7px 0 5px!important;font-size:10px!important;line-height:1.18!important;-webkit-line-clamp:3!important}.mission-candidate-grid .mission-task small{display:none!important}.mission-candidate-grid .mission-actions{display:grid!important;grid-template-columns:1fr!important;gap:5px!important;margin-top:6px!important}.mission-candidate-grid .mission-actions button{min-height:25px!important;padding:0 5px!important;font-size:8.5px!important}.mission-candidate-grid .mission-actions button[data-detail]{display:none!important}@media(max-width:380px){.mission-candidate-grid{gap:6px!important}.mission-candidate-grid .mission-task{padding:5px!important;border-radius:14px!important}.mission-candidate-grid .mission-task h3{font-size:9px!important}.mission-candidate-grid .mission-actions button{font-size:8px!important}}"""
    profile_override_css += """.mission-mini-actions{display:none!important}.mission-candidates .mission-topline{display:block!important}.mission-candidates .mission-topline h1{margin-bottom:0!important}"""
    profile_override_css += """.mission-duo-head{position:relative;margin:-22px -22px 14px;padding:18px 20px 20px;background:linear-gradient(180deg,#9a4b08,#7e3c05);color:#fff}.mission-duo-tabs{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;text-align:center;font-size:13px;font-weight:950;letter-spacing:.08em}.mission-duo-tabs span{opacity:.42}.mission-duo-tabs .active{opacity:1}.mission-goal-card{position:relative;overflow:hidden;border-radius:22px;background:#fff;color:#1f1f1f;padding:16px 14px;box-shadow:0 18px 42px #3b1b061f}.mission-goal-card h1{margin:0 0 12px;font-size:23px;line-height:1.08}.mission-goal-row{display:grid;grid-template-columns:1fr 58px;align-items:center;gap:10px}.mission-goal-bar{height:28px;border-radius:999px;background:#e8e3dd;overflow:hidden;position:relative}.mission-goal-bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#a85a10,#ffae25)}.mission-goal-bar span{position:absolute;inset:0;display:grid;place-items:center;color:#9b938c;font-size:14px;font-weight:950}.mission-coin{width:58px;height:58px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#ffbf38,#bf690b);color:#7d3d06;border:6px solid #d98a17;font-size:24px;box-shadow:0 8px 18px #8a4b1028}.mission-reward-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.mission-reward-row button{min-height:42px;border:2px solid #e5e0da;border-radius:16px;background:#fff;color:#5f5b56;font-size:13px;font-weight:950}.mission-duo-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:18px 0 10px}.mission-duo-title h2{margin:0;color:#4c4a48;font-size:24px;line-height:1.05}.mission-duo-title span{display:inline-flex;align-items:center;gap:4px;color:#ff9d00;font-size:12px;font-weight:950;white-space:nowrap}.daily-quest-card{overflow:hidden;border:2px solid #e8e3dd;border-radius:22px;background:#fff}.daily-quest{display:grid;grid-template-columns:58px 1fr;gap:12px;padding:14px;border-top:1px solid #eee8e2}.daily-quest:first-child{border-top:0}.daily-quest-icon{width:48px;height:48px;border-radius:18px;display:grid;place-items:center;background:#fff0cc;color:#ffb000;font-size:24px;font-weight:950}.daily-quest.done .daily-quest-icon{background:#e7fbe8;color:#32b943}.daily-quest h3{margin:0 0 6px;font-size:17px;line-height:1.18;color:#3c3a38}.daily-quest p{margin:0 0 9px;color:#707782;font-size:12px;line-height:1.35;font-weight:750;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.daily-quest-progress{height:18px;border-radius:999px;background:#ffe27a;overflow:hidden;position:relative}.daily-quest-progress i{display:block;height:100%;width:0;background:#ffb800}.daily-quest-progress span{position:absolute;inset:0;display:grid;place-items:center;color:#b67800;font-size:11px;font-weight:950}.daily-quest-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:9px}.daily-quest-actions button{min-height:31px;border-radius:999px;border:1px solid #ff5f0028;background:#fff7f0;color:#ff5f00;font-size:10px;font-weight:950}.daily-quest-actions .primary{border:0;background:#ff5f00;color:#fff}.mission-pick-pool{margin-top:14px}.mission-pick-pool .mission-section-head{margin-bottom:8px}.mission-pick-pool.collapsed .mission-candidate-grid{display:none!important}.mission-pick-pool-toggle{width:100%;min-height:42px;border-radius:999px;border:1px solid #ff5f0028;background:#fff7f0;color:#ff5f00;font-size:13px;font-weight:950;margin-top:10px}@media(max-width:380px){.mission-duo-head{padding:16px 18px 18px}.mission-goal-card h1{font-size:21px}.daily-quest{grid-template-columns:52px 1fr;padding:12px}.daily-quest-icon{width:44px;height:44px}.daily-quest h3{font-size:15px}}"""
    profile_override_css += """.mission-goal-card h1{font-size:22px!important}.mission-goal-row{grid-template-columns:1fr!important}.mission-goal-track{position:relative;height:44px;margin-top:3px}.mission-goal-track:before{content:"";position:absolute;left:12px;right:12px;top:18px;height:12px;border-radius:999px;background:#e8e3dd}.mission-goal-track i{position:absolute;left:12px;top:18px;height:12px;border-radius:999px;background:linear-gradient(90deg,#a85a10,#ffae25);width:0}.mission-coin-line{position:absolute;inset:0;display:grid;grid-template-columns:repeat(5,1fr);align-items:center}.mission-coin-node{justify-self:center;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#d7d0c8;color:#8a8179;border:5px solid #ede7df;font-size:16px;font-weight:950;box-shadow:0 6px 14px #3b1b0615}.mission-coin-node.active{background:linear-gradient(135deg,#ffbf38,#bf690b);color:#7d3d06;border-color:#d98a17}.mission-week-count{margin-top:6px;text-align:center;color:#9b938c;font-size:13px;font-weight:950}.mission-candidate-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:10px!important}.mission-candidate-grid .mission-task{padding:8px!important;border-radius:18px!important}.mission-candidate-grid .mission-task img{border-radius:14px!important}.mission-candidate-grid .mission-task h3{font-size:13px!important;line-height:1.22!important;-webkit-line-clamp:unset!important;display:block!important;overflow:visible!important;min-height:0!important}.mission-candidate-grid .mission-actions button{min-height:30px!important;font-size:10px!important}.mission-pick-pool.collapsed .mission-candidate-grid{display:grid!important}.mission-pick-pool-toggle{display:none!important}.daily-quest-card{margin-bottom:12px!important}@media(max-width:380px){.mission-candidate-grid{gap:8px!important}.mission-candidate-grid .mission-task h3{font-size:12px!important}.mission-coin-node{width:34px;height:34px;border-width:4px}}"""
    profile_override_css += """.daily-quest p{display:block!important;-webkit-line-clamp:unset!important;overflow:visible!important}.daily-quest h3{display:block!important;-webkit-line-clamp:unset!important;overflow:visible!important}.mission-pick-pool{margin-top:0!important;margin-bottom:16px!important}.mission-pick-pool .mission-section-head h2{font-size:24px!important;line-height:1.05!important}.mission-candidate-grid .mission-task small{display:block!important;font-size:9px!important;line-height:1.2!important}.mission-candidate-grid .mission-actions{margin-top:7px!important}"""
    profile_override_css += """.title-row{display:block!important;margin:0 0 12px!important}.title-row h1{width:100%!important;max-width:none!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;font-size:28px!important;line-height:1.05!important}.pref-card{margin-top:12px!important;margin-bottom:-2px!important;background:#fff7f0!important;border-color:#ff5f0038!important}.pref-card b{font-size:14px!important}.pref-card span{font-size:12px!important}@media(max-width:380px){.title-row h1{font-size:25px!important}}"""
    profile_override_css += """.profile-pref-row{display:grid!important;grid-template-columns:1fr auto!important;gap:8px!important;align-items:center!important;margin-top:9px!important}.profile-prefs{min-width:0!important;margin:0!important;gap:6px!important;overflow:hidden!important;display:flex!important;flex-wrap:nowrap!important}.profile-prefs .chip{flex:0 0 auto!important;max-width:132px!important;overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important;padding:6px 8px!important;font-size:10px!important;background:#fff!important;color:#ff5f00!important;border-color:#ff5f0040!important}.profile-pref-action{min-height:32px!important;border:1px solid #ff5f0040!important;border-radius:999px!important;background:#fff7f0!important;color:#ff5f00!important;padding:0 10px!important;font-size:10px!important;font-weight:950!important;white-space:nowrap!important}.profile-stats{margin-left:60px!important;max-width:132px!important}.profile-stats>div:nth-child(n+2){display:none!important}@media(max-width:380px){.profile-pref-action{padding:0 8px!important;font-size:9px!important}.profile-prefs .chip{max-width:104px!important}.profile-stats{margin-left:56px!important;max-width:120px!important}}"""
    profile_override_css += """.featured-badge,.featured-score{display:none!important}.featured-video-shell{position:absolute;inset:0;z-index:2;background:#111;display:none}.featured-media.playing .featured-video-shell{display:block}.featured-video-shell video,.featured-video-shell iframe{width:100%;height:100%;border:0;display:block;background:#050505;object-fit:contain}.featured-play{position:absolute;inset:0;z-index:3;border:0;background:linear-gradient(180deg,#00000005,#00000018);color:white;display:grid;place-items:center}.featured-play span{width:58px;height:58px;border-radius:50%;display:grid;place-items:center;background:#ff5f00;color:#fff;font-size:24px;font-weight:950;box-shadow:0 16px 34px #00000038}.featured-media.playing .featured-play{display:none}.featured-video-loading{position:absolute;inset:0;z-index:5;display:grid;place-items:center;background:linear-gradient(180deg,#00000030,#00000058);color:#fff;font-size:13px;font-weight:950;text-align:center}.featured-video-loading:before{content:"";width:34px;height:34px;border-radius:50%;border:4px solid #ffffff66;border-top-color:#ff5f00;animation:kokoSpin .82s linear infinite;margin-bottom:52px}.featured-video-loading:after{content:attr(data-label);position:absolute;left:50%;top:calc(50% + 16px);transform:translateX(-50%);min-width:150px;border-radius:999px;padding:8px 12px;background:#fffffff0;color:#ff5f00;box-shadow:0 10px 24px #00000020}@keyframes kokoSpin{to{transform:rotate(360deg)}}.featured-video-error{position:absolute;inset:auto 12px 12px;z-index:4;border-radius:16px;padding:10px 12px;background:#fffffff2;color:#1f1f1f;font-size:12px;font-weight:850;line-height:1.35;box-shadow:0 10px 24px #00000020}.featured-video-error a{color:#ff5f00;font-weight:950}.featured-media.playing img{opacity:0}.featured-media.loading .featured-play span{animation:kokoPlayPulse 1.1s ease-in-out infinite}@keyframes kokoPlayPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}"""
    profile_override_css += """.bottom{grid-template-columns:repeat(2,1fr)!important}.mission-integrated{display:grid;gap:14px}.reward-card{border:1px solid #ff5f0026;border-radius:28px;background:linear-gradient(180deg,#fff,#fff7ef);padding:16px 14px;box-shadow:0 18px 42px #552d0a12;text-align:center}.reward-card h2{margin:0 0 6px;font-size:22px;line-height:1.08;color:#e94c00}.reward-card p{margin:0;color:#69707a;font-size:12px;line-height:1.35;font-weight:800}.reward-track{position:relative;height:48px;margin:12px 0 4px}.reward-track:before{content:"";position:absolute;left:22px;right:22px;top:21px;height:8px;border-radius:999px;background:#ffe2cf}.reward-track i{position:absolute;left:22px;top:21px;height:8px;border-radius:999px;background:linear-gradient(90deg,#ff5f00,#26b765);width:0;transition:width .25s ease}.reward-coins{position:absolute;inset:0;display:grid;grid-template-columns:repeat(5,1fr);align-items:center}.reward-coin{justify-self:center;width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#fff;border:3px solid #ffb58b;color:#ff5f00;font-size:15px;font-weight:950;box-shadow:0 8px 18px #552d0a12}.reward-coin.done{background:linear-gradient(135deg,#ffd35c,#ff9b16);border-color:#ff8a00;color:#7c3b00}.reward-count{color:#ff5f00;font-size:12px;font-weight:950}.featured-shell{position:relative}.featured-card{transform-origin:center!important}.featured-card.slide-left{animation:kokoPickLeft .34s ease both}.featured-card.slide-right{animation:kokoPickRight .34s ease both}@keyframes kokoPickLeft{0%{transform:translateX(0) scale(1)}100%{transform:translateX(-24px) scale(.96);opacity:.2}}@keyframes kokoPickRight{0%{transform:translateX(0) scale(1)}100%{transform:translateX(24px) scale(.96);opacity:.2}}.featured-card-wrap{position:relative}.featured-card-wrap:before,.featured-card-wrap:after{content:"";position:absolute;left:18px;right:18px;bottom:-10px;height:34px;border:1px solid #ff5f0022;border-radius:0 0 26px 26px;background:#fff7f0;z-index:-1}.featured-card-wrap:after{left:30px;right:30px;bottom:-18px;opacity:.72}.feature-context{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.feature-context b{color:#ff5f00;font-size:17px}.feature-context span{border:1px solid #ff5f0038;border-radius:999px;padding:5px 11px;color:#ff5f00;background:#fff7f0;font-size:12px;font-weight:950}.featured-actions.pick-actions{grid-template-columns:1fr 1fr!important;margin-top:14px}.featured-actions.pick-actions .pick-skip,.featured-actions.pick-actions .pick-plan{min-height:58px!important;border-radius:22px!important;border:0!important;color:white!important;font-size:16px!important;font-weight:950!important;box-shadow:0 14px 28px #552d0a20!important}.pick-skip{background:linear-gradient(90deg,#ff4d4d,#ff1f1f)!important}.pick-plan{background:linear-gradient(90deg,#23c466,#0c9f4c)!important;animation:greenPulse 1.55s ease-in-out infinite}.pick-plan.is-picked{animation:none!important;background:linear-gradient(90deg,#1f9c55,#12783f)!important}@keyframes greenPulse{0%,100%{box-shadow:0 12px 24px #21b76130}50%{box-shadow:0 18px 34px #21b76155;transform:translateY(-1px)}}.scroll-cue{width:44px;height:34px;margin:8px auto 0;border:0;background:transparent;color:#ff5f00;font-size:24px;display:grid;place-items:center;animation:cueFloat 1.2s ease-in-out infinite}@keyframes cueFloat{0%,100%{transform:translateY(0);opacity:.55}50%{transform:translateY(5px);opacity:1}}.inline-script-section{border:1px solid #ff5f001e;border-radius:24px;background:#ffffffd8;padding:12px;box-shadow:0 14px 30px #552d0a0d;scroll-margin-top:12px}.inline-script-section h2,.today-plan h2{margin:0 0 10px;font-size:20px;color:#1f1f1f}.today-plan{border:1px solid #ff5f0024;border-radius:28px;background:#fffaf5;padding:14px;box-shadow:0 16px 34px #552d0a10}.today-plan-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}.today-plan-head h2{margin:0}.today-plan-progress{display:inline-flex;border:1px solid #ff5f0038;border-radius:999px;background:white;color:#ff5f00;padding:6px 12px;font-size:13px;font-weight:950}.plan-list{display:grid;gap:10px}.plan-card{display:grid;grid-template-columns:88px 1fr;gap:10px;border:1px solid #ff5f0022;border-radius:20px;background:white;padding:9px;box-shadow:0 8px 18px #552d0a0d}.plan-card.done{border-color:#23b76555;background:#f7fff9}.plan-card img{width:88px;aspect-ratio:1/1;border-radius:14px;object-fit:cover;background:#f8f0e9}.plan-card h3{margin:0 0 5px;font-size:14px;line-height:1.25}.plan-card p{margin:0 0 8px;color:#69707a;font-size:11px;line-height:1.35;font-weight:760}.plan-card input{min-height:34px;border-radius:12px;font-size:11px}.plan-card button{min-height:34px;margin-top:6px;border-radius:12px;font-size:11px}.plan-status{margin-top:5px;color:#23a65a;font-size:11px;font-weight:900}.plan-empty{padding:18px;border:1px dashed #ff5f0030;border-radius:20px;background:white;text-align:center;color:#69707a;font-size:13px;font-weight:800}.masonry-actions{display:grid;grid-template-columns:1fr;gap:7px;padding:0 9px 10px}.masonry-plan{border:0;border-radius:999px;min-height:34px;background:linear-gradient(90deg,#23c466,#0c9f4c);color:#fff;font-size:12px;font-weight:950}.masonry-open{border:1px solid #ff5f002c;border-radius:999px;min-height:32px;background:#fff7f0;color:#ff5f00;font-size:12px;font-weight:950}.masonry-card{border-radius:16px!important}.masonry-card.is-article{cursor:default;text-align:left}.masonry-card.is-article img,.masonry-card.is-article .masonry-title{cursor:pointer}@media(max-width:380px){.reward-card h2{font-size:20px}.featured-actions.pick-actions .pick-skip,.featured-actions.pick-actions .pick-plan{font-size:14px!important}.plan-card{grid-template-columns:78px 1fr}.plan-card img{width:78px}}"""
    profile_override_css += """.featured-card .inline-script-section{margin-top:12px;max-height:340px;overflow:auto;border-radius:22px;background:linear-gradient(180deg,#fffffff2,#fff8f1ee);box-shadow:inset 0 16px 26px #ffffffd9,inset 0 -18px 28px #fff1e5;border-color:#ff5f002b;padding:12px 10px;scroll-margin-top:84px;-webkit-mask-image:linear-gradient(180deg,transparent 0,#000 24px,#000 calc(100% - 26px),transparent 100%);mask-image:linear-gradient(180deg,transparent 0,#000 24px,#000 calc(100% - 26px),transparent 100%)}.featured-card .inline-script-section h2{position:sticky;top:-12px;z-index:2;margin:0 0 10px;padding:10px 4px 8px;background:linear-gradient(180deg,#fffaf5,#fffaf5ee);font-size:18px;color:#ff5f00}.featured-card .inline-script-section .script-html{margin:0!important}.featured-card .inline-script-section .clean-script{gap:10px!important}.featured-card .inline-script-section .brief-card,.featured-card .inline-script-section .script-shot-card,.featured-card .inline-script-section .script-table-card{border-radius:16px!important;padding:10px!important}.featured-card .inline-script-section .script-shot-table{font-size:11px!important}.mission-integrated>.inline-script-section{display:none!important}.plan-card{grid-template-columns:72px 1fr!important;align-items:start!important}.plan-card img{width:72px!important;border-radius:12px!important}.plan-card h3{font-size:13px!important;line-height:1.22!important;margin-bottom:4px!important}.plan-card p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:7px!important}.plan-card .masonry-open{min-height:30px!important;margin:0!important;padding:0 10px!important}.plan-submit{grid-column:1/-1;margin-top:8px;border-top:1px solid #ff5f0018;padding-top:8px}.plan-submit summary{cursor:pointer;list-style:none;display:flex;align-items:center;justify-content:center;min-height:36px;border-radius:999px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;font-size:12px;font-weight:950}.plan-submit summary::-webkit-details-marker{display:none}.plan-submit[open] summary{margin-bottom:8px}.plan-submit-row{display:grid;grid-template-columns:1fr auto;gap:7px}.plan-submit-row input{min-width:0!important;min-height:38px!important}.plan-submit-row button{margin:0!important;min-height:38px!important;border-radius:13px!important;padding:0 12px!important}.plan-status{grid-column:1/-1}.plan-card.done .plan-submit summary{background:linear-gradient(90deg,#26b765,#15984d)}@media(max-width:380px){.featured-card .inline-script-section{max-height:300px}.plan-card{grid-template-columns:64px 1fr!important}.plan-card img{width:64px!important}.plan-submit-row{grid-template-columns:1fr}.plan-submit-row button{width:100%}}"""
    profile_override_css += """.featured-card{display:flex!important;flex-direction:column!important;overflow:visible!important}.featured-scroll-area{max-height:none!important;overflow:visible!important;overscroll-behavior:auto!important;border-radius:24px 24px 18px 18px;background:#fff}.featured-scroll-area .featured-body{padding-bottom:0!important}.featured-card .inline-script-section{max-height:0!important;overflow:hidden!important;opacity:0!important;pointer-events:none!important;-webkit-mask-image:none!important;mask-image:none!important;margin:0!important;padding-top:0!important;padding-bottom:0!important;border-width:0!important;transform:translateY(-8px);transition:max-height .36s ease,opacity .22s ease,margin .22s ease,padding .22s ease,transform .22s ease}.featured-card.detail-open .inline-script-section{max-height:760px!important;overflow:auto!important;opacity:1!important;pointer-events:auto!important;margin:12px 0 0!important;padding:12px 10px!important;border-width:1px!important;background:linear-gradient(180deg,#fffffff6,#fff8f1f2)!important;transform:translateY(0);scrollbar-width:thin;scrollbar-color:#ff9d66 #fff0e8}.featured-card.detail-open .inline-script-section::-webkit-scrollbar{width:4px}.featured-card.detail-open .inline-script-section::-webkit-scrollbar-thumb{background:#ff9d66;border-radius:999px}.featured-card.detail-open .inline-script-section::-webkit-scrollbar-track{background:#fff0e8}.featured-card .inline-script-section h2{top:0!important}.scroll-cue{margin-left:auto!important;margin-right:0!important;width:40px!important;height:32px!important;border:1px solid #ff5f002a!important;border-radius:999px!important;background:#fff7f0!important}.featured-card.detail-open .scroll-cue{transform:rotate(180deg)}.featured-actions.pick-actions{flex:0 0 auto!important;margin:12px 16px 16px!important}.today-plan-head{display:block!important}.plan-progress-row{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:12px;margin:10px 0 14px;padding:10px 12px;border:1px solid #ff5f0030;border-radius:18px;background:white}.today-plan-progress{display:block!important;border:0!important;background:transparent!important;padding:0!important;font-size:18px!important;line-height:1!important}.plan-progress-track{height:14px;border-radius:999px;background:#fff0e8;overflow:hidden;border:1px solid #ff5f0028}.plan-progress-track i{display:block;height:100%;width:0;background:linear-gradient(90deg,#ff6a00,#27b866);border-radius:999px;transition:width .25s ease}.plan-submit{grid-column:1/-1;margin-top:8px;border-top:1px solid #ff5f0018;padding-top:8px}.plan-submit-label{display:flex;align-items:center;justify-content:center;min-height:34px;border-radius:999px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;font-size:12px;font-weight:950;margin-bottom:8px}.plan-card.done .plan-submit-label{background:linear-gradient(90deg,#26b765,#15984d)}@media(max-width:430px){.featured-actions.pick-actions{margin:10px 12px 14px!important}.plan-progress-row{grid-template-columns:1fr;gap:8px}.today-plan-progress{font-size:16px!important}.featured-card.detail-open .inline-script-section{max-height:680px!important}}"""

    profile_override_css += """.auth-card textarea{width:100%;min-height:92px;margin-bottom:12px;border:1px solid #ff5f0028;border-radius:16px;padding:14px 16px;font-size:15px;line-height:1.45;background:#fffaf7;color:#1f1f1f;outline:none;resize:vertical}.auth-card textarea:focus{border-color:#ff5f00;box-shadow:0 0 0 4px #ff5f0012}.auth-guide input[hidden],.auth-guide textarea[hidden]{display:none!important}"""

    profile_override_css += """.view[data-view="dashboard"]{padding-top:10px!important}.reward-card{position:relative!important;overflow:hidden!important;text-align:left!important;border:1px solid #ff7a0038!important;border-radius:24px!important;background:linear-gradient(135deg,#fffdf9 0%,#fff4e7 46%,#ffe0c2 100%)!important;padding:12px 12px 10px!important;margin:0 8px!important;box-shadow:0 18px 42px #ff5f0018,0 1px 0 #ffffff inset!important;isolation:isolate!important}.reward-card:before{content:"";position:absolute;inset:0;border-radius:24px;padding:1.5px;background:linear-gradient(115deg,#ff5f0000 0%,#ff8a00 45%,#ffe0a0 54%,#ff5f0000 72%);background-size:250% 250%;-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none;animation:rewardSweep 5.5s ease-in-out infinite;opacity:.65}.reward-glow{position:absolute;right:-42px;top:-58px;width:136px;height:136px;border-radius:50%;background:radial-gradient(circle,#ff9a2342,#ff9a2300 68%);animation:rewardPulse 2.7s ease-in-out infinite}.reward-copy{position:relative;z-index:2;max-width:74%;padding-right:24px}.reward-card h2{margin:0 0 4px!important;color:#f05a00!important;font-size:18px!important;line-height:1.08!important;letter-spacing:-.01em!important}.reward-card p{margin:0!important;color:#7a5940!important;font-size:10px!important;line-height:1.32!important;font-weight:850!important}.reward-mascot{position:absolute;right:-8px;top:15px;width:78px;height:78px;object-fit:contain;filter:drop-shadow(0 12px 18px #ff5f0034);animation:rewardMascot 2.6s ease-in-out infinite;z-index:2}.reward-track{position:relative!important;height:62px!important;margin:12px 0 0!important;z-index:2}.reward-track:before{left:20px!important;right:20px!important;top:36px!important;height:6px!important;background:#ffd8ba!important}.reward-track i{left:20px!important;top:36px!important;height:6px!important;background:linear-gradient(90deg,#ff6a00,#ffc247,#31c26b)!important}.reward-steps{position:absolute;inset:0;display:grid;grid-template-columns:repeat(5,1fr);align-items:end}.reward-step{position:relative;display:grid;justify-items:center;gap:3px;min-width:0}.reward-amount{color:#f05a00;font-size:9px;font-weight:950;line-height:1;white-space:nowrap}.reward-coin{width:31px!important;height:31px!important;border:0!important;border-radius:50%;background:url('/static/reward-coin.svg') center/contain no-repeat!important;box-shadow:0 10px 18px #a34a001f;filter:saturate(.95);font-size:0!important}.reward-step.done .reward-coin{filter:saturate(1.15) drop-shadow(0 0 8px #ffc24780);transform:scale(1.06)}.reward-step em,.reward-count{display:none!important}.reward-gift{position:absolute;right:-15px;top:25px;width:24px;height:24px;border-radius:8px;background:url('/static/reward-gift.svg') center/contain no-repeat;filter:drop-shadow(0 7px 12px #9b3c0028);animation:giftBounce 1.9s ease-in-out infinite;z-index:3}.reward-step:nth-child(4) .reward-gift{right:-13px}.mission-integrated{gap:12px!important}@keyframes giftBounce{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-4px) rotate(4deg)}}@keyframes rewardSweep{0%{background-position:160% 0}55%{background-position:-60% 100%}100%{background-position:160% 0}}@keyframes rewardPulse{0%,100%{transform:scale(.96);opacity:.68}50%{transform:scale(1.05);opacity:1}}@keyframes rewardMascot{0%,100%{transform:translateY(0) rotate(-2deg)}50%{transform:translateY(-5px) rotate(2deg)}}.featured-tags{align-items:center!important;position:relative!important}.featured-tags .scroll-cue{margin-left:auto!important;width:34px!important;height:28px!important;border:1px solid #ff5f0030!important;border-radius:999px!important;background:#fff7f0!important;color:#ff5f00!important;font-size:18px!important;box-shadow:0 8px 18px #ff5f0018!important;animation:cueFloat 1.15s ease-in-out infinite!important;display:inline-grid!important;place-items:center!important;flex:0 0 auto!important}.featured-actions.pick-actions{gap:12px!important;margin:14px 14px 16px!important}.featured-actions.pick-actions .pick-skip,.featured-actions.pick-actions .pick-plan{min-height:66px!important;border-radius:24px!important;font-size:17px!important;letter-spacing:.01em!important;position:relative!important;overflow:hidden!important}.featured-actions.pick-actions .pick-skip:after,.featured-actions.pick-actions .pick-plan:after{content:"";position:absolute;inset:-40% -85%;background:linear-gradient(90deg,#fff0,#ffffff48,#fff0);transform:rotate(12deg) translateX(-45%);animation:buttonShine 2.6s ease-in-out infinite}.pick-skip{animation:redPulse 1.8s ease-in-out infinite!important}.pick-plan{animation:greenPulseBig 1.45s ease-in-out infinite!important}.pick-plan.is-picked{animation:none!important}@keyframes redPulse{0%,100%{box-shadow:0 13px 26px #ff2b2b24!important;transform:translateY(0)}50%{box-shadow:0 18px 34px #ff2b2b42!important;transform:translateY(-1px)}}@keyframes greenPulseBig{0%,100%{box-shadow:0 13px 26px #21b76130!important;transform:translateY(0)}50%{box-shadow:0 19px 38px #21b76158!important;transform:translateY(-2px) scale(1.01)}}@keyframes buttonShine{0%,55%{transform:rotate(12deg) translateX(-46%);opacity:0}72%{opacity:.88}100%{transform:rotate(12deg) translateX(46%);opacity:0}}@media(max-width:380px){.reward-card{padding:11px 10px 9px!important;margin:0 6px!important}.reward-copy{max-width:74%}.reward-card h2{font-size:17px!important}.reward-card p{font-size:9px!important}.reward-mascot{width:70px;height:70px;top:18px}.reward-amount{font-size:8px}.reward-coin{width:29px!important;height:29px!important}.reward-gift{width:21px;height:21px;right:-13px;top:27px}.featured-actions.pick-actions .pick-skip,.featured-actions.pick-actions .pick-plan{min-height:60px!important;font-size:15px!important}}"""

    profile_override_css += """#mission-guide.mission-popup{align-items:center!important;justify-content:center!important;padding:18px!important;background:radial-gradient(circle at 50% 24%,#ff7a0030,#1f1f1f78 48%,#11111188)!important;backdrop-filter:blur(8px)}#mission-guide .mission-guide-card{position:relative!important;width:min(100%,430px)!important;max-height:min(86vh,680px)!important;overflow:auto!important;border-radius:30px!important;padding:0!important;background:linear-gradient(180deg,#fffdf8 0%,#fff4e7 58%,#fffaf5 100%)!important;border:1px solid #ff8a0045!important;box-shadow:0 30px 80px #1f10072e,0 0 0 1px #ffffffd8 inset!important;isolation:isolate!important}#mission-guide .mission-guide-card:before{content:"";position:absolute;inset:0;border-radius:30px;padding:2px;background:linear-gradient(120deg,#ff5f0000 0%,#ff7a00 38%,#ffe1a6 50%,#ff5f0000 70%);background-size:260% 260%;-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none;animation:rewardSweep 4.8s ease-in-out infinite;opacity:.78}#mission-guide .mission-guide-hero{position:relative;min-height:186px;padding:22px 20px 18px;overflow:hidden;background:radial-gradient(circle at 86% 8%,#ffd279 0,#ff9b1d 28%,#ff5f00 62%,#c84600 100%);color:white}#mission-guide .mission-guide-hero:before{content:"";position:absolute;left:-38px;bottom:-58px;width:150px;height:150px;border-radius:50%;background:#ffffff24}#mission-guide .mission-guide-hero:after{content:"✦";position:absolute;left:18px;top:122px;color:#fff0c8;font-size:22px;text-shadow:70px -76px 0 #fff6,220px -28px 0 #fff8;animation:rewardPulse 2.5s ease-in-out infinite}#mission-guide .mission-guide-kicker{position:relative;z-index:2;display:inline-flex;align-items:center;border-radius:999px;background:#ffffffed;color:#ff5f00;padding:6px 10px;font-size:11px;font-weight:950;box-shadow:0 10px 22px #9b3c0018}#mission-guide .mission-guide-hero h2{position:relative;z-index:2;width:68%;margin:14px 0 7px!important;color:white!important;font-size:28px!important;line-height:1.02!important;letter-spacing:-.02em!important;text-shadow:0 4px 18px #8c310040}#mission-guide .mission-guide-hero p{position:relative;z-index:2;width:72%;margin:0!important;color:#fff8ef!important;font-size:12px!important;line-height:1.38!important;font-weight:850!important}#mission-guide .mission-guide-mascot{position:absolute;right:-12px;bottom:-6px;width:150px;height:150px;object-fit:contain;filter:drop-shadow(0 18px 24px #5a1f002f);animation:rewardMascot 2.6s ease-in-out infinite;z-index:1}#mission-guide .mission-prize{position:relative;margin:-20px 18px 12px!important;padding:13px!important;border-radius:22px!important;background:#fffffff2!important;border:1px solid #ff5f002b!important;box-shadow:0 16px 36px #552d0a18!important;z-index:3}#mission-guide .mission-prize-main{display:grid;grid-template-columns:56px 1fr;gap:10px;align-items:center}#mission-guide .mission-prize-coin{width:54px;height:54px;border-radius:50%;background:url('/static/reward-coin.svg') center/contain no-repeat;filter:drop-shadow(0 10px 14px #a34a0024);animation:coinPop 1.8s ease-in-out infinite}#mission-guide .mission-prize b{display:block!important;color:#ff5f00!important;font-size:30px!important;line-height:1!important}#mission-guide .mission-prize span{display:block;margin-top:3px;color:#5e4532;font-size:12px;line-height:1.35;font-weight:900}.mission-rule-grid{display:grid;gap:9px;padding:0 18px 12px}.mission-rule{position:relative;padding:11px 12px 11px 44px;border:1px solid #ff5f0020;border-radius:18px;background:#fff;box-shadow:0 8px 18px #552d0a0b}.mission-rule:before{content:"$";position:absolute;left:12px;top:12px;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#ffe17d,#ff9d17);color:#994300;font-size:13px;font-weight:950}.mission-rule:nth-child(2):before{content:"↗";background:linear-gradient(135deg,#ffe7d3,#ff5f00);color:white}.mission-rule.gift:before{content:"🎁";background:#fff0e8;font-size:14px}.mission-rule strong{display:block;color:#1f1f1f;font-size:13px;line-height:1.18;font-weight:950}.mission-rule span{display:block;margin-top:4px;color:#69707a;font-size:11px;line-height:1.35;font-weight:800}.mission-read-card{display:flex!important;align-items:center;gap:10px;margin:0 18px 10px!important;padding:12px!important;border:1px solid #ff5f0036!important;border-radius:18px!important;background:#fff8f1!important;color:#1f1f1f!important;font-size:13px!important;font-weight:950!important}.mission-read-card input{width:22px!important;height:22px!important;accent-color:#ff5f00}.mission-hide-card{display:flex!important;align-items:center;gap:8px;margin:0 18px 12px!important;padding:8px 10px!important;border:1px solid #d8d8d8!important;border-radius:16px!important;background:#f4f4f4!important;color:#858b92!important;font-size:11px!important;font-weight:850!important}.mission-hide-card input{width:16px!important;height:16px!important;accent-color:#9aa0a6}.mission-guide-card .mission-popup-actions{display:block!important;margin:0!important;padding:0 18px 18px!important}.mission-guide-card .mission-popup-actions .primary{width:100%!important;min-height:50px!important;border-radius:999px!important;background:linear-gradient(90deg,#ff6a00,#ff5200)!important;color:white!important;font-size:15px!important;font-weight:950!important;box-shadow:0 14px 28px #ff5f0036!important}.mission-guide-card .mission-popup-actions .primary:disabled{filter:grayscale(.2);opacity:.48!important;box-shadow:none!important}@keyframes coinPop{0%,100%{transform:scale(1) rotate(-5deg)}50%{transform:scale(1.08) rotate(5deg)}}@media(max-width:380px){#mission-guide .mission-guide-hero{min-height:174px;padding:20px 18px 16px}#mission-guide .mission-guide-hero h2{font-size:24px!important;width:70%}#mission-guide .mission-guide-hero p{font-size:11px!important;width:72%}#mission-guide .mission-guide-mascot{width:130px;height:130px}.mission-rule{padding-left:40px}.mission-rule span{font-size:10px}}"""
    profile_override_css += """
.reward-card{min-height:0!important;padding:8px 10px 7px!important;margin:0 8px!important;border-radius:18px!important;display:grid!important;grid-template-columns:34px 1fr!important;column-gap:8px!important;align-items:center!important}
.reward-glow{display:none!important}.reward-copy{max-width:none!important;padding-right:0!important}.reward-card h2{font-size:14px!important;line-height:1.05!important;margin:0 0 2px!important}.reward-card p{font-size:8px!important;line-height:1.22!important;display:-webkit-box!important;-webkit-line-clamp:2!important;-webkit-box-orient:vertical!important;overflow:hidden!important}
.reward-mascot{display:none!important}.reward-logo{position:relative;z-index:3;width:30px;height:30px;border-radius:10px;background:#fff;box-shadow:0 8px 18px #ff5f001a;padding:5px;object-fit:contain}
.reward-track{grid-column:1/-1!important;height:42px!important;margin:4px 5px 0!important;padding:0 34px 0 2px!important;position:relative!important}
.reward-track:before{left:8px!important;right:36px!important;top:24px!important;height:3px!important;background:#ffe0c8!important}.reward-track i{left:8px!important;top:24px!important;height:3px!important;max-width:calc(100% - 44px)!important;background:linear-gradient(90deg,#ff5f00,#ffb13d)!important}
.reward-ticks{position:absolute;left:8px;right:36px;top:18px;height:16px;display:grid;grid-template-columns:repeat(15,1fr);z-index:2}.reward-tick{justify-self:center;width:1px;height:13px;border-radius:99px;background:#ffc7a6}.reward-tick.done{background:#ff5f00}
.reward-steps{position:absolute!important;left:8px!important;right:36px!important;top:0!important;bottom:auto!important;display:block!important;z-index:4}.reward-step{position:absolute!important;top:0!important;display:grid!important;justify-items:center!important;gap:0!important;transform:translateX(-50%)!important;padding:0!important}
.reward-amount{font-size:7px!important;line-height:1!important;margin-bottom:1px!important;transform:none!important;color:#ff5f00!important}.reward-coin{width:12px!important;height:12px!important;box-shadow:0 2px 6px #f59b1624!important}.reward-gift{width:12px!important;height:12px!important;top:12px!important;right:-13px!important}
.reward-progress-tail{right:0!important;top:14px!important;min-width:30px!important;height:19px!important;font-size:8px!important}
.feature-context{display:grid!important;grid-template-columns:1fr auto 1fr!important;align-items:center!important;margin:2px 0 8px!important}.feature-context b{grid-column:2!important;text-align:center!important;font-family:Impact,Arial Black,system-ui,sans-serif!important;color:#ff5f00!important;font-size:19px!important;line-height:1!important;letter-spacing:.01em!important}.feature-context span{grid-column:3!important;justify-self:end!important}
.today-plan-head h2,.inline-script-section h2{font-family:Impact,Arial Black,system-ui,sans-serif!important;color:#ff5f00!important;text-align:center!important;letter-spacing:.01em!important}.today-plan-head h2{font-size:21px!important}.inline-script-section h2{font-size:20px!important}
@media(max-width:380px){.reward-card{grid-template-columns:30px 1fr!important;padding:7px 9px 6px!important}.reward-logo{width:27px;height:27px}.reward-card h2{font-size:13px!important}.reward-card p{font-size:7.5px!important}.feature-context b{font-size:17px!important}}
"""
    profile_override_css += """
.reward-card{padding:9px 10px 8px!important;border-radius:18px!important;background:linear-gradient(135deg,#fffdf9 0%,#fff3e5 58%,#ffe4c5 100%)!important}
.reward-logo{width:28px!important;height:28px!important;padding:4px!important}.reward-card h2{font-size:14px!important}.reward-card p{font-size:8px!important;line-height:1.2!important}
.reward-track{grid-column:1/-1!important;height:48px!important;margin:4px 4px 0!important;padding:0 38px 0 0!important;position:relative!important;overflow:visible!important}
.reward-track:before{content:""!important;position:absolute!important;left:4px!important;right:40px!important;top:22px!important;height:14px!important;border-radius:999px!important;background:linear-gradient(180deg,#fff7eb,#ffd8bd 48%,#ffb98f)!important;box-shadow:inset 0 2px 4px #ffffff, inset 0 -3px 7px #d9793030, 0 7px 16px #ff7a001c!important;border:1px solid #ffb07a55!important}
.reward-track i{position:absolute!important;left:5px!important;top:23px!important;height:12px!important;border-radius:999px!important;background:linear-gradient(90deg,#ff5f00 0%,#ffb13d 48%,#24bd63 100%)!important;box-shadow:0 0 10px #ff8a0060,0 0 18px #24bd6340!important;overflow:hidden!important;transition:width .32s ease!important;max-width:calc(100% - 45px)!important}
.reward-track i:after{content:"";position:absolute;inset:-8px -24px;background:linear-gradient(100deg,#fff0 0%,#ffffffaa 42%,#fff0 70%);transform:translateX(-80%);animation:rewardTubeFlow 1.8s ease-in-out infinite}
.reward-ticks{display:none!important}.reward-step{top:0!important}.reward-amount{font-size:7px!important;font-weight:950!important;color:#ff5f00!important;text-shadow:0 1px 0 white!important}.reward-coin{width:13px!important;height:13px!important;filter:drop-shadow(0 3px 5px #9b3c0024)!important}.reward-step.done .reward-coin{filter:saturate(1.2) drop-shadow(0 0 7px #ffc24790)!important;transform:scale(1.08)!important}.reward-gift{width:13px!important;height:13px!important;top:12px!important;right:-14px!important}
.reward-progress-tail{top:19px!important;right:0!important;height:24px!important;min-width:34px!important;border-color:#ffb17b!important;background:#fffaf5!important;font-size:8px!important;box-shadow:0 6px 14px #552d0a12!important}
@keyframes rewardTubeFlow{0%{transform:translateX(-90%);opacity:0}38%{opacity:.85}100%{transform:translateX(90%);opacity:0}}
#mission-guide.mission-popup{z-index:180!important}
#mission-guide .mission-guide-card{width:min(94vw,408px)!important;max-height:min(90vh,720px)!important;border-radius:28px!important;box-sizing:border-box!important;overflow:auto!important;background:linear-gradient(180deg,#fffaf2 0%,#fff4e8 54%,#fffdf8 100%)!important}
#mission-guide .mission-guide-card:before{inset:0!important;border-radius:inherit!important;padding:2px!important;background:linear-gradient(125deg,#ff5f0000 0%,#ff7a00 34%,#fff0b8 50%,#ff7a00 64%,#ff5f0000 82%)!important;background-size:260% 260%!important;animation:rewardSweep 4.2s ease-in-out infinite!important;opacity:.9!important}
#mission-guide .mission-guide-hero{display:grid!important;justify-items:center!important;text-align:center!important;min-height:0!important;padding:22px 18px 18px!important;background:radial-gradient(circle at 50% 0%,#ffc84d 0,#ff8a00 34%,#ff5f00 72%,#e34d00 100%)!important;color:white!important}
#mission-guide .mission-guide-hero:before{left:-45px!important;bottom:-70px!important;width:150px!important;height:150px!important;background:#ffffff22!important}
#mission-guide .mission-guide-hero:after{left:42px!important;top:72px!important;text-shadow:150px 8px 0 #fff8,246px -42px 0 #fff7!important}
#mission-guide .mission-guide-kicker{font-size:11px!important;padding:6px 13px!important;background:#fff!important;color:#ff5f00!important}
#mission-guide .mission-guide-mascot{position:static!important;order:-1!important;width:58px!important;height:58px!important;border-radius:18px!important;background:#fff!important;padding:9px!important;margin:0 0 9px!important;filter:drop-shadow(0 12px 18px #7a290030)!important;animation:none!important}
#mission-guide .mission-guide-hero h2{width:100%!important;margin:4px 0 8px!important;text-align:center!important;font-family:Impact,'Arial Black',system-ui,sans-serif!important;font-size:34px!important;line-height:.98!important;letter-spacing:0!important;color:#fff!important;text-shadow:0 5px 18px #7a290045!important}
#mission-guide .mission-guide-hero p{width:100%!important;margin:0!important;text-align:center!important;color:#fff8ec!important;font-size:15px!important;line-height:1.3!important;font-weight:900!important}.mission-highlight{display:inline-block;color:#fff2a6!important;font-size:1.22em!important;font-weight:1000!important;text-shadow:0 2px 12px #9b3c0040!important}.mission-prize{display:none!important}.mission-rules-title{position:relative;z-index:3;display:grid;grid-template-columns:44px 1fr;gap:10px;align-items:center;margin:12px 16px 10px!important;padding:12px!important;border-radius:18px!important;background:linear-gradient(135deg,#fff,#fff7ee)!important;border:1px solid #ff5f0032!important;box-shadow:0 12px 26px #552d0a10!important}.mission-rules-title .mission-prize-coin{width:42px!important;height:42px!important}.mission-rules-title b{display:block;color:#ff5f00;font-size:17px;line-height:1.1;font-weight:1000}.mission-rules-title span{display:block;margin-top:4px;color:#5e4532;font-size:11px;line-height:1.38;font-weight:850}.reward-rule-grid{padding:0 16px 12px!important;gap:9px!important}.reward-rule-grid .mission-rule{padding:12px 12px 12px 44px!important;border-radius:18px!important;background:#fff!important;border:1px solid #ff5f0024!important;box-shadow:0 9px 20px #552d0a0d!important}.reward-rule-grid .mission-rule:before{left:12px!important;top:12px!important;width:24px!important;height:24px!important}.reward-rule-grid .mission-rule.cash:before{content:'$'!important;background:linear-gradient(135deg,#ffe88a,#ff9d17)!important;color:#8c3d00!important}.reward-rule-grid .mission-rule.views:before{content:'↗'!important;background:linear-gradient(135deg,#ffd7bd,#ff5f00)!important;color:#fff!important}.reward-rule-grid .mission-rule.gift:before{content:''!important;background:url('/static/reward-gift.svg') center/contain no-repeat!important}.reward-rule-grid .mission-rule strong{font-size:14px!important;line-height:1.16!important;color:#ff5f00!important}.reward-rule-grid .mission-rule span{font-size:11px!important;line-height:1.38!important;color:#555!important}.reward-views-list{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px}.reward-views-list span{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:7px;padding:7px 8px;border-radius:12px;background:#fff7ef;border:1px solid #ff5f001e}.reward-views-list em{font-style:normal;color:#6b7280;font-size:10px;font-weight:900}.reward-views-list b{color:#ff5f00;font-size:12px;font-weight:1000}.reward-views-note{display:block;margin-top:6px;color:#8b623f;font-size:10px;line-height:1.25;font-weight:850}.mission-read-card{margin:0 16px 9px!important;padding:11px!important;border-radius:17px!important}.mission-hide-card{margin:0 16px 12px!important;padding:9px 10px!important;border-radius:16px!important}.mission-guide-card .mission-popup-actions{padding:0 16px 16px!important}.mission-guide-card .mission-popup-actions .primary{min-height:48px!important}
@media(max-width:380px){#mission-guide .mission-guide-card{width:95vw!important;border-radius:24px!important}#mission-guide .mission-guide-hero{padding:18px 15px 15px!important}#mission-guide .mission-guide-mascot{width:50px!important;height:50px!important;border-radius:15px!important}#mission-guide .mission-guide-hero h2{font-size:28px!important}#mission-guide .mission-guide-hero p{font-size:13px!important}.mission-rules-title{margin:10px 12px 9px!important;padding:10px!important}.reward-rule-grid{padding:0 12px 10px!important}.reward-views-list{grid-template-columns:1fr}.reward-rule-grid .mission-rule strong{font-size:13px!important}}
"""
    profile_override_css += """#mission-guide .mission-guide-hero{padding:20px 18px 16px!important}#mission-guide .mission-guide-hero h2 span{display:inline-block;color:#fff0a6!important;text-shadow:0 3px 16px #7a290050!important;transform:rotate(-2deg);font-size:1.08em}#mission-guide .mission-guide-hero p{margin-bottom:12px!important}.mission-highlight{padding:2px 8px;border-radius:999px;background:#ffffff22;color:#fff3a8!important;box-shadow:0 0 0 1px #ffffff2e inset,0 8px 20px #7a290020}.mission-rules-title{margin:0!important;width:100%!important;grid-template-columns:34px 1fr!important;text-align:left!important;background:#fffaf4f2!important;border-color:#ffffff78!important;box-shadow:0 14px 30px #7a290028!important;backdrop-filter:blur(8px)!important}.mission-rules-title .mission-prize-coin{width:32px!important;height:32px!important;animation:coinPop 1.8s ease-in-out infinite!important}.mission-rules-title b{font-size:14px!important;color:#bf3e00!important;letter-spacing:.01em!important}.mission-rules-title span{font-size:10.5px!important;color:#5a3b24!important;line-height:1.45!important}.mission-rules-title span strong{color:#ff5f00;font-weight:1000}.mission-rules-title span em{display:inline-block;margin:3px 3px 0 0;padding:3px 6px;border-radius:999px;background:#ff5f00;color:#fff;font-style:normal;font-size:10px;font-weight:950;box-shadow:0 5px 12px #ff5f002c}.reward-rule-grid{padding-top:12px!important}.reward-rule-grid .mission-rule{position:relative!important;overflow:hidden!important;background:linear-gradient(135deg,#fff 0%,#fff9f3 100%)!important}.reward-rule-grid .mission-rule:after{content:"";position:absolute;right:-34px;top:-42px;width:92px;height:92px;border-radius:50%;background:radial-gradient(circle,#ff8a0016,#ff8a0000 68%);pointer-events:none}.reward-rule-grid .mission-rule:before{z-index:2;box-shadow:0 8px 16px #552d0a18;animation:rewardIconFloat 2.2s ease-in-out infinite}.reward-rule-grid .mission-rule.cash:before{animation:rewardCoinSpin 2.6s ease-in-out infinite}.reward-rule-grid .mission-rule.views:before{animation:rewardArrowFly 1.8s ease-in-out infinite}.reward-rule-grid .mission-rule.gift:before{animation:giftBounce 1.65s ease-in-out infinite}.reward-rule-grid .mission-rule strong{position:relative;z-index:1;font-size:14.5px!important;color:#1f1f1f!important}.reward-rule-grid .mission-rule strong:after{content:"";display:block;width:34px;height:3px;margin-top:6px;border-radius:999px;background:linear-gradient(90deg,#ff5f00,#ffc36e)}.reward-rule-grid .mission-rule span{position:relative;z-index:1;display:block!important;margin-top:7px!important;color:#5f6670!important}.reward-rule-grid .mission-rule span b{display:block;margin-bottom:5px;color:#ff5f00;font-size:13px;line-height:1.25;font-weight:1000}.reward-rule-grid .mission-rule span small{display:block;color:#606873;font-size:11px;line-height:1.4;font-weight:850}.reward-rule-grid .mission-rule span small em{font-style:normal;color:#159a51;font-weight:1000}.reward-views-list span{background:linear-gradient(135deg,#fff8ef,#fff)!important}.reward-views-list span:nth-child(2n){background:linear-gradient(135deg,#fff,#fff1e6)!important}.reward-views-list em{color:#555!important}.reward-views-list b{font-size:13px!important;color:#ff5f00!important}.reward-views-note{padding:6px 8px;border-radius:10px;background:#fff4e8;color:#8a4a19!important}.mission-read-card span{color:#1f1f1f!important}.mission-hide-card span{color:#7f8790!important}@keyframes rewardIconFloat{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-3px) scale(1.06)}}@keyframes rewardCoinSpin{0%,100%{transform:translateY(0) rotate(-8deg) scale(1)}50%{transform:translateY(-4px) rotate(10deg) scale(1.08)}}@keyframes rewardArrowFly{0%,100%{transform:translate(0,0) rotate(0)}50%{transform:translate(2px,-3px) rotate(8deg)}}@media(max-width:380px){#mission-guide .mission-guide-hero h2 span{font-size:1.04em}.mission-rules-title{grid-template-columns:30px 1fr!important;padding:9px!important}.mission-rules-title .mission-prize-coin{width:29px!important;height:29px!important}.mission-rules-title span{font-size:10px!important}.reward-rule-grid .mission-rule span b{font-size:12px!important}.reward-rule-grid .mission-rule span small{font-size:10.5px!important}}"""
    profile_override_css += """.reward-views-note{display:block!important;margin-top:7px!important;padding:0!important;border-radius:0!important;background:transparent!important;border:0!important;box-shadow:none!important;color:#8a4a19!important;font-size:10px!important;line-height:1.25!important;font-weight:850!important}"""
    profile_override_css += """.onboarding-overlay{position:fixed;inset:0;z-index:220;display:none;pointer-events:none}.onboarding-overlay.active{display:block;pointer-events:auto}.onboarding-spot{position:absolute;left:18px;top:120px;width:120px;height:80px;border-radius:24px;box-shadow:0 0 0 9999px rgba(24,14,8,.62),0 0 0 3px #ff6a00,0 18px 46px #ff5f0050;transition:all .24s ease;pointer-events:none;background:rgba(255,255,255,.04);animation:onboardingGlow 1.8s ease-in-out infinite}.onboarding-card{position:absolute;left:16px;right:16px;max-width:420px;margin:0 auto;border:1px solid #ff5f0040;border-radius:24px;background:linear-gradient(180deg,#fffdf9,#fff5eb);padding:15px;box-shadow:0 24px 70px #1f10073a;transition:top .24s ease;pointer-events:auto}.onboarding-card:before{content:"";position:absolute;inset:0;border-radius:24px;padding:1.5px;background:linear-gradient(120deg,#ff5f0000,#ff6a00,#ffd6a8,#ff5f0000);background-size:220% 220%;-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none;animation:onboardingSweep 3.4s ease-in-out infinite}.onboarding-step{display:inline-flex;align-items:center;border-radius:999px;background:#ff5f00;color:white;padding:5px 9px;font-size:11px;font-weight:950;box-shadow:0 8px 18px #ff5f0030}.onboarding-card h3{margin:9px 0 5px;color:#1f1f1f;font-size:20px;line-height:1.08;font-weight:1000}.onboarding-card p{margin:0;color:#68707b;font-size:13px;line-height:1.42;font-weight:820}.onboarding-actions{display:grid;grid-template-columns:auto 1fr auto;gap:8px;margin-top:13px}.onboarding-actions button{min-height:38px;border-radius:999px;border:1px solid #ff5f002c;background:#fff;color:#ff5f00;padding:0 12px;font-size:12px;font-weight:950}.onboarding-actions .primary{border:0;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;box-shadow:0 10px 22px #ff5f002e}.onboarding-actions [data-onboarding-back]{color:#6b7280;border-color:#e4d8ce}.onboarding-actions [data-onboarding-skip]{background:#fff7f0}.onboarding-nudge{animation:onboardingTargetPulse 1.25s ease-in-out 2}@keyframes onboardingGlow{0%,100%{box-shadow:0 0 0 9999px rgba(24,14,8,.62),0 0 0 3px #ff6a00,0 18px 46px #ff5f0040}50%{box-shadow:0 0 0 9999px rgba(24,14,8,.58),0 0 0 4px #ffb070,0 22px 58px #ff5f0060}}@keyframes onboardingSweep{0%{background-position:180% 0}55%{background-position:-40% 100%}100%{background-position:180% 0}}@keyframes onboardingTargetPulse{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}@media(max-width:380px){.onboarding-card{left:12px;right:12px;border-radius:22px;padding:13px}.onboarding-card h3{font-size:18px}.onboarding-card p{font-size:12px}.onboarding-actions{grid-template-columns:1fr 1fr}.onboarding-actions [data-onboarding-back]{display:none}.onboarding-actions .primary{grid-column:auto}.onboarding-actions button{padding:0 9px;font-size:11px}}"""
    profile_override_css += """.script-expand-cue{display:flex!important;align-items:center!important;justify-content:center!important;gap:8px!important;margin:6px 0 12px!important}.script-expand-cue .scroll-cue{margin:0!important;width:40px!important;height:34px!important;border:0!important;border-radius:999px!important;background:linear-gradient(135deg,#ff7a18,#ff5200)!important;color:#fff!important;font-size:22px!important;box-shadow:0 10px 24px #ff5f0030!important;animation:cueFloat 1.1s ease-in-out infinite!important}.script-expand-cue span{color:#858b94!important;font-size:11px!important;line-height:1.25!important;font-weight:850!important}.featured-card.detail-open .script-expand-cue .scroll-cue{transform:rotate(180deg)!important}.featured-actions.pick-actions .pick-skip,.featured-actions.pick-actions .pick-plan{display:flex!important;align-items:center!important;justify-content:center!important;gap:9px!important}.pick-mark{display:inline-grid!important;place-items:center!important;width:24px!important;height:24px!important;border-radius:50%!important;background:#ffffff30!important;color:#fff!important;font-size:15px!important;font-weight:1000!important;line-height:1!important}.plan-card.plan-card-compact{display:block!important;grid-template-columns:none!important;border:1px solid #ff5f0028!important;border-radius:24px!important;background:#fff!important;padding:12px!important;box-shadow:0 12px 28px #552d0a12!important}.plan-card.plan-card-compact .plan-card-top{display:grid!important;grid-template-columns:82px 1fr!important;gap:12px!important;align-items:start!important}.plan-card.plan-card-compact .plan-card-top img{width:82px!important;height:82px!important;aspect-ratio:1/1!important;border-radius:16px!important;object-fit:cover!important;background:#fff7f0!important;border:1px solid #ff5f0022!important}.plan-card.plan-card-compact h3{margin:2px 0 0!important;color:#1f1f1f!important;font-size:16px!important;line-height:1.24!important;font-weight:950!important;display:-webkit-box!important;-webkit-line-clamp:4!important;-webkit-box-orient:vertical!important;overflow:hidden!important}.plan-detail-button{display:flex!important;align-items:center!important;justify-content:center!important;width:100%!important;min-height:46px!important;margin:13px 0 10px!important;border:1px solid #ff5f0042!important;border-radius:18px!important;background:#fff7f0!important;color:#ff5f00!important;font-size:15px!important;font-weight:950!important;box-shadow:0 8px 18px #ff5f0014!important}.plan-submit-row.plan-submit-row-compact{display:grid!important;grid-template-columns:minmax(0,1fr) 88px!important;gap:8px!important;align-items:center!important;margin-top:0!important}.plan-submit-row.plan-submit-row-compact input{width:100%!important;min-width:0!important;min-height:43px!important;border:1px solid #ff5f0042!important;border-radius:16px!important;background:#fffdf9!important;padding:0 11px!important;color:#1f1f1f!important;font-size:12px!important;font-weight:750!important}.plan-submit-row.plan-submit-row-compact button{width:100%!important;min-height:43px!important;margin:0!important;border-radius:16px!important;background:linear-gradient(90deg,#ff6a00,#ff5200)!important;color:#fff!important;font-size:13px!important;font-weight:950!important}.plan-card.plan-card-compact .plan-status{margin-top:9px!important;color:#ff5f00!important;font-size:11px!important;font-weight:900!important}.plan-card.plan-card-compact.done{border-color:#ff5f0045!important;background:#fffaf5!important}.plan-card.plan-card-compact.done .plan-status{color:#159a51!important}@media(max-width:380px){.script-expand-cue{gap:6px!important}.script-expand-cue span{font-size:10px!important}.plan-card.plan-card-compact{padding:10px!important;border-radius:22px!important}.plan-card.plan-card-compact .plan-card-top{grid-template-columns:72px 1fr!important;gap:10px!important}.plan-card.plan-card-compact .plan-card-top img{width:72px!important;height:72px!important}.plan-card.plan-card-compact h3{font-size:14px!important}.plan-submit-row.plan-submit-row-compact{grid-template-columns:minmax(0,1fr) 78px!important}.plan-submit-row.plan-submit-row-compact button{font-size:12px!important}}"""
    profile_override_css += """.preference-strip{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:10px!important;margin:0 8px 10px!important;padding:9px 10px!important;border:1px solid #ff5f002c!important;border-radius:18px!important;background:#fffaf5d8!important;box-shadow:0 10px 24px #552d0a0d!important}.preference-strip b{display:block!important;margin:0 0 5px!important;color:#1f1f1f!important;font-size:12px!important;line-height:1!important}.preference-strip-chips{display:flex!important;gap:5px!important;flex-wrap:wrap!important;max-height:30px!important;overflow:hidden!important}.preference-strip .chip{padding:5px 8px!important;font-size:10px!important;line-height:1!important;background:#fff!important}.preference-strip button{flex:0 0 auto!important;min-height:32px!important;border:1px solid #ff5f0048!important;border-radius:999px!important;background:#fff7f0!important;color:#ff5f00!important;padding:0 10px!important;font-size:11px!important;font-weight:950!important;white-space:nowrap!important}@media(max-width:380px){.preference-strip{margin-left:6px!important;margin-right:6px!important;padding:8px!important}.preference-strip button{font-size:10px!important;padding:0 8px!important}.preference-strip-chips{max-height:27px!important}.preference-strip .chip{font-size:9px!important;padding:5px 7px!important}}"""
    profile_override_css += """.featured-card .preference-strip{display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;align-items:center!important;margin:0 14px 14px!important;padding:10px 12px!important;border-radius:18px!important}.featured-card .preference-strip>div{min-width:0!important}.featured-card .preference-strip b{font-size:11px!important;margin-bottom:6px!important}.featured-card .preference-strip-chips{max-height:none!important;overflow:visible!important;row-gap:6px!important}.featured-card .preference-strip button{max-width:116px!important;min-height:34px!important;padding:0 10px!important;white-space:normal!important;line-height:1.12!important}.featured-tags{display:flex!important;flex-wrap:wrap!important;gap:7px!important;overflow:visible!important;max-height:none!important}.featured-tags .tag,.preference-strip .chip,.chip{height:auto!important;min-height:26px!important;max-width:100%!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;word-break:break-word!important;line-height:1.16!important}.featured-tags .tag{padding:6px 9px!important;font-size:11px!important}.preference-strip .chip{padding:5px 8px!important}@media(max-width:380px){.featured-card .preference-strip{grid-template-columns:1fr!important;gap:8px!important;margin:0 10px 12px!important}.featured-card .preference-strip button{justify-self:start!important;max-width:none!important}.featured-tags .tag{font-size:10px!important;padding:5px 7px!important}}"""
    profile_override_css += """#mission-guide.mission-popup{padding:12px!important;overflow:hidden!important}#mission-guide .mission-guide-card{width:min(94vw,390px)!important;max-height:none!important;overflow:visible!important;transform:none!important;border-radius:24px!important}#mission-guide .mission-guide-card:before{border-radius:24px!important}.mission-guide-close{position:absolute!important;right:10px!important;top:10px!important;z-index:9!important;width:34px!important;height:34px!important;border:1px solid #ffffff9c!important;border-radius:50%!important;background:#fffffff2!important;color:#ff5f00!important;font-size:23px!important;line-height:1!important;font-weight:950!important;box-shadow:0 10px 22px #7a29002e!important}#mission-guide .mission-guide-hero{padding:14px 14px 10px!important;border-radius:24px 24px 0 0!important}#mission-guide .mission-guide-kicker{font-size:10px!important;padding:5px 10px!important}#mission-guide .mission-guide-mascot{width:42px!important;height:42px!important;border-radius:14px!important;padding:7px!important;margin:0 0 6px!important}#mission-guide .mission-guide-hero h2{font-size:26px!important;line-height:.98!important;margin:2px 0 6px!important}#mission-guide .mission-guide-hero p{font-size:12px!important;line-height:1.18!important;margin-bottom:7px!important}.mission-highlight{font-size:1.14em!important;padding:1px 6px!important}.mission-rules-title{grid-template-columns:28px 1fr!important;margin:0!important;padding:8px!important;border-radius:14px!important}.mission-rules-title .mission-prize-coin{width:27px!important;height:27px!important}.mission-rules-title b{font-size:12px!important}.mission-rules-title span{font-size:9.3px!important;line-height:1.24!important}.mission-rules-title span em{padding:2px 5px!important;font-size:8.6px!important;margin-top:2px!important}.mission-guide-scroll-cue{display:none!important}.reward-rule-grid{padding:8px 12px 7px!important;gap:6px!important}.reward-rule-grid .mission-rule{padding:8px 9px 8px 36px!important;border-radius:14px!important}.reward-rule-grid .mission-rule:before{left:9px!important;top:9px!important;width:21px!important;height:21px!important;font-size:11px!important}.reward-rule-grid .mission-rule strong{font-size:12.5px!important;line-height:1.05!important}.reward-rule-grid .mission-rule strong:after{width:28px!important;height:2px!important;margin-top:4px!important}.reward-rule-grid .mission-rule span{margin-top:4px!important;font-size:9.6px!important;line-height:1.22!important}.reward-rule-grid .mission-rule span b{margin-bottom:3px!important;font-size:11px!important}.reward-rule-grid .mission-rule span small{font-size:9.5px!important;line-height:1.24!important}.reward-views-list{grid-template-columns:1fr 1fr!important;gap:4px!important;margin-top:4px!important}.reward-views-list span{padding:5px 6px!important;border-radius:9px!important}.reward-views-list em{font-size:8.7px!important}.reward-views-list b{font-size:10.5px!important}.reward-views-note{display:none!important}.mission-read-card{margin:0 12px 6px!important;padding:8px 9px!important;border-radius:13px!important;font-size:11px!important;gap:7px!important}.mission-read-card input{width:17px!important;height:17px!important}.mission-hide-card{margin:0 12px 7px!important;padding:6px 8px!important;border-radius:12px!important;font-size:10px!important;gap:6px!important}.mission-hide-card input{width:14px!important;height:14px!important}.mission-guide-card .mission-popup-actions{padding:0 12px 12px!important}.mission-guide-card .mission-popup-actions .primary{min-height:40px!important;font-size:13px!important}@media(max-height:700px){#mission-guide .mission-guide-card{transform:scale(.9)!important;transform-origin:center center!important}}@media(max-height:620px){#mission-guide .mission-guide-card{transform:scale(.82)!important}}@media(max-width:380px){#mission-guide.mission-popup{padding:8px!important}#mission-guide .mission-guide-card{width:95vw!important}#mission-guide .mission-guide-hero{padding:12px 12px 9px!important}#mission-guide .mission-guide-hero h2{font-size:22px!important}.reward-rule-grid{padding:7px 10px 6px!important;gap:5px!important}.reward-rule-grid .mission-rule{padding:7px 8px 7px 34px!important}.reward-rule-grid .mission-rule strong{font-size:11.5px!important}.reward-rule-grid .mission-rule span b{font-size:10.5px!important}.reward-rule-grid .mission-rule span small{font-size:9px!important}.mission-rules-title span{font-size:8.8px!important}}"""
    profile_override_css += """.ui-toast{position:fixed;left:50%;bottom:max(86px,calc(env(safe-area-inset-bottom) + 72px));z-index:220;display:flex;align-items:center;gap:9px;width:max-content;max-width:calc(100vw - 28px);min-height:46px;padding:11px 15px;border:1px solid #ff5f0042;border-radius:14px;background:#fffffff5;color:#9b430a;font-size:13px;font-weight:900;line-height:1.35;box-shadow:0 18px 44px #32170830;opacity:0;pointer-events:none;transform:translate(-50%,12px);transition:opacity .18s ease,transform .18s ease}.ui-toast.show{opacity:1;transform:translate(-50%,0)}.ui-toast.success{border-color:#20a45a50;color:#158548}.ui-toast.error{border-color:#d94b3655;color:#c53d29}.ui-toast.loading:before,.ui-busy:before{content:"";width:14px;height:14px;flex:0 0 14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:uiSpin .7s linear infinite}.ui-busy{cursor:wait!important;opacity:.72!important}.ui-pressed{transform:scale(.97)!important;filter:brightness(.97)}button,a,.option,.calendar-day{transition:transform .12s ease,filter .12s ease,opacity .12s ease,background-color .16s ease,border-color .16s ease}.auth-status{min-height:20px;margin:10px 2px 0;color:#69707a;font-size:12px;font-weight:850;line-height:1.4;text-align:center}.auth-status.success{color:#158548}.auth-status.error{color:#c53d29}.auth-status.loading{color:#9b430a}.submit-status.success{color:#158548}.submit-status.error{color:#c53d29}@keyframes uiSpin{to{transform:rotate(360deg)}}"""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Koko</title>{FAVICON_LINKS}<style>{profile_override_css}
*{{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}body{{margin:0;background:#fff4ea;color:#1f1f1f}}button,a{{font:inherit}}.phone{{width:min(100%,480px);min-height:100vh;margin:0 auto;padding-bottom:96px;overflow-x:hidden;background:linear-gradient(180deg,#fffaf5,#fff0df 42%,#fff8f2)}}.top{{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;padding:18px 22px 12px;background:rgba(255,252,248,.9);backdrop-filter:blur(16px)}}.brand{{font-size:34px;font-weight:900}}.brand span{{color:#ff5f00;font-size:17px;margin-left:8px}}.lang{{position:fixed;right:max(14px,calc((100vw - 480px)/2 + 14px));bottom:92px;z-index:20;display:flex;gap:4px;padding:5px;border-radius:999px;background:white;box-shadow:0 12px 28px #ff820022}}.lang button{{border:0;border-radius:999px;padding:7px 10px;background:transparent;font-size:12px;font-weight:850;color:#777}}.lang .active{{background:#ff5f00;color:white}}.view{{display:none;padding:22px}}.view.active{{display:block}}.chip,.tag{{display:inline-flex;align-items:center;border:1px solid #ff5f0070;border-radius:999px;padding:8px 12px;color:#ff5f00;background:#ffffff90;font-size:12px;font-weight:850}}.step-label{{display:block;margin:2px 0 0;color:#ff5f00;font-size:13px;font-weight:850}}button.chip{{cursor:pointer;min-height:38px}}button.chip:active{{transform:scale(.98);background:#fff0e8}}.title-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:2px 0 12px}}.title-row h1{{margin:0;font-size:clamp(30px,8vw,46px);flex:1}}.reselect-title{{border:1px solid #ff5f0060;border-radius:999px;min-height:38px;padding:0 12px;background:#fff7f0;color:#ff5f00;font-size:12px;font-weight:900;white-space:nowrap;box-shadow:0 8px 18px #ff5f0018}}h1{{margin:10px 0 12px;font-size:clamp(38px,10vw,56px);line-height:1.08;font-weight:900}}.lead{{margin:0;color:#69707a;font-size:16px;line-height:1.55}}.primary,.open{{border:0;border-radius:999px;min-height:48px;padding:0 16px;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;text-decoration:none;font-weight:900;box-shadow:0 14px 30px #ff5f0040}}.secondary{{border:0;border-radius:999px;min-height:44px;padding:0 16px;background:white;color:#1f1f1f;font-weight:850;box-shadow:0 10px 24px #00000010}}.step-actions{{display:grid;grid-template-columns:1fr;gap:10px;margin-top:18px}}.step-actions button{{min-height:54px}}.cta{{display:grid;gap:12px;margin:18px 0}}.card{{border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a14}}.hero{{min-height:150px;margin:20px -22px 0;position:relative;overflow:hidden}}.mascot{{position:absolute;right:26px;bottom:8px;width:116px;height:116px;border-radius:52% 48% 44% 56%;background:radial-gradient(circle at 35% 22%,#ffbe55,#ff8e24 64%,#f97808)}}.quick{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}}.quick button{{min-height:78px;border:0;border-radius:18px;background:white;font-weight:850}}.quick b{{display:block;color:#ff5f00;font-size:22px}}.stepper{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 24px}}.step{{min-height:58px;border:0;border-radius:18px;background:white;display:grid;place-items:center;color:#777;font-weight:900;cursor:pointer}}.step:active{{transform:scale(.98)}}.step.active{{background:#ff5f00;color:white}}.options,.feed{{display:grid;gap:14px;margin-top:16px}}.option{{min-height:72px;border:1px solid #ff820026;border-radius:18px;background:white;text-align:left;padding:14px;font-weight:850}}.option.selected{{border-color:#ff5f00;color:#ff5f00}}.question-submit{{width:100%;min-height:72px;margin-top:14px;border-radius:18px;font-size:22px;justify-content:center;text-align:center}}.date-group{{margin-top:16px}}.date-divider{{display:flex;align-items:center;justify-content:center;min-height:34px;border:1px solid rgba(255,95,0,.36);border-radius:999px;background:#fffdf9;color:#1f1f1f;font-size:15px;font-weight:900;box-shadow:0 8px 20px #552d0a0a}}.masonry{{columns:2 150px;column-gap:10px;margin-top:10px}}.masonry-card{{break-inside:avoid;display:block;width:100%;margin:0 0 10px;border:1px solid rgba(255,95,0,.26);border-radius:12px;overflow:hidden;background:white;color:#1f1f1f;text-align:left;box-shadow:0 6px 18px #552d0a10;cursor:pointer}}.masonry-card:active{{transform:scale(.99)}}.masonry-card img{{display:block;width:100%;height:auto;aspect-ratio:3/4;object-fit:cover;background:#2a1d16}}.masonry-card:nth-child(3n+2) img{{aspect-ratio:1/1}}.masonry-card:nth-child(4n+3) img{{aspect-ratio:4/5}}.masonry-title{{display:block;padding:9px 10px 11px;font-size:14px;line-height:1.34;font-weight:850;white-space:normal;overflow:visible;word-break:break-word}}.script{{display:grid;grid-template-columns:116px 1fr;gap:13px;padding:14px;min-height:168px}}.thumb{{position:relative;overflow:hidden;border-radius:16px;min-height:142px;background:#2a1d16;color:white;padding:10px;font-size:12px;font-weight:900}}.thumb img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.thumb:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000010,#000000aa)}}.thumb span{{position:relative;z-index:1;background:#9e490ce0;border-radius:9px;padding:6px 8px}}.body{{min-width:0;display:flex;flex-direction:column;gap:8px}}.body h3{{margin:0;font-size:18px;line-height:1.22;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.body p{{margin:0;color:#69707a;font-size:13px;line-height:1.42;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}.tags{{display:flex;gap:6px;flex-wrap:wrap}}.tag{{padding:5px 8px;background:#fff0e8;font-size:11px}}.actions{{display:grid;grid-template-columns:1fr 38px 38px;gap:8px;margin-top:auto}}.icon{{border:0;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#fff0e8;color:#ff5f00;font-weight:900}}.tabs{{display:flex;gap:8px;overflow:auto;padding:4px 0 12px}}.tabs button{{border:1px solid #ff5f0038;border-radius:999px;padding:9px 13px;background:white;color:#777;font-size:12px;font-weight:850}}.tabs .active{{background:#ff5f00;color:white}}.bottom{{position:fixed;left:50%;bottom:0;transform:translateX(-50%);z-index:18;width:min(100%,480px);display:grid;grid-template-columns:repeat(2,1fr);gap:2px;padding:10px 14px;background:#fffffff0;border-radius:24px 24px 0 0;box-shadow:0 -14px 34px #00000014}}.bottom button{{border:0;background:transparent;min-height:54px;color:#777;font-size:12px;font-weight:750}}.bottom .active{{color:#ff5f00}}.modal{{position:fixed;inset:0;z-index:50;display:none;align-items:flex-end;background:#1f1f1f55;padding:18px 18px 0}}.modal.active{{display:flex}}.sheet{{width:min(100%,480px);max-height:88vh;overflow:auto;margin:0 auto;border-radius:28px 28px 0 0;background:#fffaf5;padding:18px}}.sheet-img{{height:220px;border-radius:20px;overflow:hidden;background:#2a1d16}}.sheet-img img{{width:100%;height:100%;object-fit:cover}}.submit{{display:grid;gap:10px;margin:14px 0;padding:14px;border-radius:18px;background:#fff0e8}}.submit input{{min-height:46px;border:1px solid #ff5f0038;border-radius:14px;padding:0 12px}}.state{{padding:18px}}@media(max-width:380px){{.view{{padding:18px}}h1{{font-size:36px}}.script{{grid-template-columns:104px 1fr}}}}
.modal{{padding:10px 10px 0}}.sheet{{height:96vh;max-height:96vh;border-radius:24px 24px 0 0;padding:12px 12px 24px}}.detail-top{{position:sticky;top:0;z-index:2;display:flex;justify-content:flex-end;padding:2px 0 8px;background:#fffaf5cc;backdrop-filter:blur(12px)}}.detail-cover{{position:relative;width:100%;aspect-ratio:4/5;border-radius:22px;overflow:hidden;background:#2a1d16;margin:0 0 14px;box-shadow:0 18px 38px #552d0a1c}}.detail-cover img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.detail-cover:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000008,#00000000 48%,#0000003f)}}.video-section{{margin:16px 0 14px}}.video-section-title{{display:flex;align-items:center;justify-content:space-between;margin:0 0 8px;color:#1f1f1f;font-size:15px;font-weight:950}}.video-section-title span{{color:#ff5f00;font-size:12px}}.video-box{{position:relative;width:100%;height:min(78vh,760px);aspect-ratio:9/16;border-radius:18px;overflow:hidden;background:#111;margin-bottom:14px}}.video-box iframe,.video-box img,.video-box video{{position:absolute;inset:0;width:100%;height:100%;border:0;object-fit:contain;background:#111}}.video-fallback{{position:absolute;inset:auto 12px 12px;z-index:1;border-radius:14px;padding:10px;background:#00000099;color:white;font-size:12px;line-height:1.4}}.detail-title{{margin:8px 0 10px;font-size:25px;line-height:1.18;font-weight:900}}.social-actions{{display:flex;gap:10px;margin:14px 0 10px;padding:10px 0;border-top:1px solid rgba(255,95,0,.12);border-bottom:1px solid rgba(255,95,0,.12)}}.social-btn{{border:1px solid rgba(255,95,0,.26);border-radius:999px;min-width:48px;height:48px;padding:0 15px;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:white;color:#ff5f00;font-size:22px;font-weight:900;box-shadow:0 8px 20px #552d0a10}}.social-btn span{{font-size:13px;color:#1f1f1f}}.share-box{{display:none;margin:0 0 12px;padding:12px;border:1px solid rgba(255,95,0,.22);border-radius:16px;background:#fff7f0;color:#69707a;font-size:12px;line-height:1.45}}.share-box.active{{display:block}}.share-box b{{display:block;margin-bottom:6px;color:#1f1f1f;font-size:13px}}.share-box a{{display:block;color:#ff5f00;font-weight:850;word-break:break-all}}.script-html{{margin-top:12px;padding:0;border-radius:18px;background:transparent;border:0;overflow:visible}}.clean-script{{display:grid;gap:12px}}.storyboard{{aspect-ratio:1/1;border-radius:20px;background:#fbfaf7;border:1px solid rgba(255,95,0,.18);overflow:hidden;box-shadow:0 10px 24px rgba(85,45,10,.08)}}.storyboard-img{{display:block;width:100%;height:100%;object-fit:cover}}.brief-card,.insight-section{{border:1px solid rgba(255,95,0,.18);border-radius:18px;background:white;padding:15px;box-shadow:0 10px 24px rgba(85,45,10,.08)}}.brief-card b{{display:block;margin-bottom:9px;color:#ff5f00;font-size:16px;line-height:1.2;font-weight:950;letter-spacing:.01em}}.brief-card p{{margin:0;color:#1f1f1f;font-size:15px;line-height:1.62;word-break:break-word}}.brief-list{{display:grid;gap:10px}}.insight-section h3{{margin:0 0 12px!important;color:#1f1f1f!important;font-size:22px!important;line-height:1.15!important;font-weight:950!important}}.insight-cards{{display:grid;gap:10px}}.insight-cards article{{border:1px solid rgba(255,95,0,.14);border-radius:14px;background:#fffdf9;padding:12px}}.insight-cards b{{display:block;margin:0 0 6px;color:#1f1f1f;font-size:15px;line-height:1.25;font-weight:950}}.insight-cards p{{margin:0;color:#4f5661;font-size:13px;line-height:1.55}}.script-table-card{{border:1px solid rgba(255,95,0,.22);border-radius:18px;background:white;overflow:hidden;box-shadow:0 10px 24px rgba(85,45,10,.08);width:100%;max-width:100%;margin:0}}.script-table-title{{padding:14px 14px 12px;font-size:22px;line-height:1.15;font-weight:950;color:#1f1f1f;border-bottom:1px solid #ffd8c0}}.script-table{{width:100%;table-layout:fixed;border-collapse:collapse}}.script-table th,.script-table td{{border-right:1px solid #ffd8c0;border-bottom:1px solid #ffd8c0;padding:8px 3px;vertical-align:top;color:#1f1f1f;word-break:break-word;overflow-wrap:anywhere}}.script-table th:last-child,.script-table td:last-child{{border-right:0}}.script-table tr:last-child td{{border-bottom:0}}.script-table th{{background:#fff8f2;font-size:12px;line-height:1.2;font-weight:950;text-align:center}}.script-table td{{font-size:11px;line-height:1.48}}.script-table .col-time{{width:10.5%}}.script-table .col-image{{width:30.5%}}.script-table .col-action{{width:27%}}.script-table .col-dialogue{{width:32%}}.script-table .time-cell{{font-weight:900;color:#ff5f00;text-align:center;white-space:normal;font-size:9px;line-height:1.18;letter-spacing:0}}.shot-cell{{display:grid;gap:6px}}.shot-thumb{{position:relative;width:100%;aspect-ratio:1/1;border-radius:8px;overflow:hidden;background:#fbfaf7;border:1px solid rgba(0,0,0,.16)}}.shot-thumb img{{position:absolute;width:calc(var(--cols)*100%);height:calc(var(--rows)*100%);max-width:none!important;object-fit:cover;left:calc(var(--sx)*-100%);top:calc(var(--sy)*-100%)}}.shot-text{{font-size:10.5px;line-height:1.35;color:#1f1f1f}}.script-shot-list{{display:grid;gap:14px;padding:12px;background:#fffaf6}}.script-shot-card{{display:grid;gap:10px;border:1px solid rgba(255,95,0,.22);border-radius:18px;background:#fff;padding:10px;box-shadow:0 10px 22px rgba(85,45,10,.08)}}.script-shot-time{{border:1px solid rgba(255,95,0,.24);border-radius:14px;background:#fffdf9;padding:10px 13px;color:#ff5f00;font-size:14px;font-weight:950;line-height:1.2}}.script-shot-body{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:10px;align-items:stretch}}.script-shot-visual,.script-shot-info{{min-width:0}}.script-shot-visual{{display:grid;gap:8px;align-content:start}}.script-shot-image{{position:relative;width:100%;aspect-ratio:1/1;border-radius:16px;overflow:hidden;background:#fbfaf7;border:1px solid rgba(0,0,0,.18)}}.script-shot-image img{{position:absolute;width:calc(var(--cols)*100%);height:calc(var(--rows)*100%);max-width:none!important;border-radius:0!important;object-fit:cover!important;left:calc(var(--sx)*-100%);top:calc(var(--sy)*-100%)}}.script-shot-caption{{margin:0;color:#4f5661;font-size:11px;line-height:1.38;font-weight:750}}.script-shot-info{{display:grid;grid-template-rows:1fr 1fr;gap:10px}}.script-shot-box{{min-height:104px;border:1px solid rgba(255,95,0,.20);border-radius:16px;background:#fffdf9;padding:12px;overflow:hidden}}.script-shot-box b{{display:block;margin:0 0 7px;color:#ff5f00;font-size:13px;line-height:1.2;font-weight:950}}.script-shot-box p{{margin:0;color:#1f1f1f;font-size:12.5px;line-height:1.48;font-weight:700;word-break:break-word;overflow-wrap:anywhere}}@media(max-width:380px){{.script-shot-list{{padding:10px;gap:12px}}.script-shot-card{{padding:9px}}.script-shot-body{{gap:8px;grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr)}}.script-shot-box{{min-height:96px;padding:10px}}.script-shot-box p{{font-size:11.5px;line-height:1.42}}.script-shot-caption{{font-size:10.5px}}}}.raw-script-source{{display:none}}.script-loading{{margin-top:12px;padding:18px;border-radius:18px;background:white;border:1px solid rgba(255,95,0,.14);color:#69707a}}.script-loading b{{display:block;margin-bottom:8px;color:#1f1f1f;font-size:16px}}.script-progress{{position:relative;height:6px;margin-top:12px;overflow:hidden;border-radius:999px;background:#ffe4d2}}.script-progress:after{{content:"";position:absolute;inset:0 auto 0 0;width:42%;border-radius:999px;background:linear-gradient(90deg,#ff7a18,#ff5200);animation:scriptLoad 1.1s ease-in-out infinite}}@keyframes scriptLoad{{0%{{transform:translateX(-105%)}}100%{{transform:translateX(245%)}}}}.script-html *{{max-width:100%}}.script-html h1{{font-size:24px;line-height:1.18;margin:0 0 10px}}.script-html h2{{font-size:19px;line-height:1.25;margin:18px 0 10px}}.script-html h3{{font-size:16px;line-height:1.3;margin:14px 0 8px}}.script-html p,.script-html li,.script-html td,.script-html th{{font-size:14px;line-height:1.7;word-break:break-word}}.script-html img,.script-html video{{height:auto;border-radius:12px}}.script-html .shot-thumb img{{position:absolute!important;width:calc(var(--cols)*100%)!important;height:calc(var(--rows)*100%)!important;max-width:none!important;border-radius:0!important;object-fit:cover!important;left:calc(var(--sx)*-100%)!important;top:calc(var(--sy)*-100%)!important}}.script-html table{{display:block;width:100%;overflow-x:auto;border-collapse:collapse;white-space:normal}}.script-html th,.script-html td{{min-width:120px;border:1px solid #ffe0cc;padding:8px;vertical-align:top}}.script-html .wrap,.script-html .card{{max-width:100%;padding:0;box-shadow:none;background:transparent}}.script-html .script-table th,.script-html .script-table td{{min-width:0!important}}

.landing{{padding:22px;background:linear-gradient(180deg,#fffaf5,#fff0df 42%,#fff8f2)}}.landing .hero{{min-height:238px;margin:18px -22px 0;position:relative;overflow:hidden}}.landing .cta{{grid-template-columns:1fr;gap:10px;margin:20px 0 10px}}.landing-register{{border:0;border-radius:999px;min-height:50px;padding:0 16px;background:white;color:#1f1f1f;font-weight:900;box-shadow:0 10px 24px #00000010}}.landing-section{{margin-top:28px}}.landing-section h2{{font-size:25px;line-height:1.15;margin:0 0 14px;font-weight:950}}.preview-strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0;padding:12px;border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a14}}.preview-card{{min-height:162px;border-radius:16px;background:linear-gradient(180deg,#4b2b19,#17110e);position:relative;overflow:hidden;color:white;padding:10px;display:flex;align-items:flex-end;font-weight:900;font-size:13px;line-height:1.25;background-size:cover;background-position:center}}.preview-card:before{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000008,#000000c0)}}.preview-card span{{position:relative;z-index:1;text-shadow:0 2px 8px #00000070}}.preview-card:nth-child(1){{background-image:url('/static/landing-storyboard-1.jpg')}}.preview-card:nth-child(2){{background-image:url('/static/landing-storyboard-2.jpg')}}.preview-card:nth-child(3){{background-image:url('/static/landing-storyboard-3.jpg')}}.info-panel{{min-height:104px;border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a10;display:grid;place-items:center;padding:20px;text-align:center;color:#69707a;font-size:15px;line-height:1.55;font-weight:750}}.feature-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 24px}}.feature{{min-height:94px;border-radius:18px;background:white;border:1px solid #ff82001a;display:grid;place-items:center;text-align:center;padding:10px;font-size:13px;font-weight:850;color:#1f1f1f}}.feature b{{display:block;color:#ff5f00;font-size:24px;margin-bottom:5px}}.author-cloud{{position:relative;height:250px;margin:14px 0;overflow:hidden;border-radius:28px;background:radial-gradient(circle at 50% 50%,#fff7ee 0,#ffe8d8 44%,#fff4ea 100%)}}.author-dot{{position:absolute;border-radius:50%;background-color:#ffd9bf;background-position:center;background-size:cover;background-repeat:no-repeat;box-shadow:0 18px 34px #ff5f0028;border:6px solid #fffaf5;animation:floatAvatar 12s ease-in-out infinite alternate;will-change:transform}}.author-dot:nth-child(1){{width:96px;height:96px;left:36%;top:8px;background-image:url('/static/landing-avatar-real-01.jpg');animation-duration:13s}}.author-dot:nth-child(2){{width:70px;height:70px;left:8%;top:82px;background-image:url('/static/landing-avatar-real-02.jpg');animation-duration:11s;animation-delay:-3s}}.author-dot:nth-child(3){{width:106px;height:106px;right:8%;top:86px;background-image:url('/static/landing-avatar-real-03.jpg');animation-duration:15s;animation-delay:-6s}}.author-dot:nth-child(4){{width:116px;height:116px;left:30%;bottom:10px;background-image:url('/static/landing-avatar-real-04.jpg');animation-duration:14s;animation-delay:-2s}}.author-dot:nth-child(5){{width:58px;height:58px;left:68%;top:22px;background-image:url('/static/landing-avatar-real-05.jpg');animation-delay:-5s}}.author-dot:nth-child(6){{width:66px;height:66px;left:2%;bottom:26px;background-image:url('/static/landing-avatar-real-06.jpg');animation-duration:10s;animation-delay:-7s}}.author-dot:nth-child(7){{width:74px;height:74px;right:0;bottom:12px;background-image:url('/static/landing-avatar-real-07.jpg');animation-duration:12s;animation-delay:-4s}}.author-dot:nth-child(8){{width:52px;height:52px;left:20%;top:18px;background-image:url('/static/landing-avatar-real-08.jpg');animation-duration:9s;animation-delay:-8s}}.author-dot:nth-child(9){{width:62px;height:62px;right:30%;bottom:4px;background-image:url('/static/landing-avatar-real-09.jpg');animation-duration:13s;animation-delay:-1s}}.author-dot:nth-child(10){{width:50px;height:50px;right:16%;top:6px;background-image:url('/static/landing-avatar-real-10.jpg');animation-duration:10s;animation-delay:-9s}}.author-dot:nth-child(11){{width:64px;height:64px;left:48%;top:92px;background-image:url('/static/landing-avatar-real-11.jpg');animation-duration:12s;animation-delay:-10s}}.author-dot:nth-child(12){{width:60px;height:60px;right:42%;bottom:62px;background-image:url('/static/landing-avatar-real-12.jpg');animation-duration:11s;animation-delay:-6s}}@keyframes floatAvatar{{0%{{transform:translate3d(-10px,8px,0) scale(.98)}}50%{{transform:translate3d(14px,-12px,0) scale(1.04)}}100%{{transform:translate3d(-4px,16px,0) scale(1)}}}}.ending-card{{min-height:238px;border-radius:28px;border:1px solid #ff5f0024;background:linear-gradient(135deg,#fff,#ffe3cf);display:grid;place-items:center;text-align:center;font-size:30px;font-weight:950;box-shadow:0 18px 42px #552d0a14;padding:26px}}.ending-card small{{display:block;margin-top:8px;color:#69707a;font-size:15px;font-weight:750;line-height:1.5}}.auth-overlay{{position:fixed;inset:0;z-index:140;display:none;place-items:center;background:linear-gradient(180deg,#fffaf5,#fff0df 60%,#fff7f0);padding:22px}}.auth-overlay.active{{display:grid}}.auth-card{{width:min(100%,390px);min-height:420px;border:1px solid #ff5f0026;border-radius:28px;background:#fffffff2;padding:34px 24px;box-shadow:0 26px 60px #552d0a18}}.auth-card h2{{text-align:center;font-size:34px;margin:0 0 24px;color:#1f1f1f}}.auth-card input{{width:100%;min-height:52px;margin-bottom:12px;border:1px solid #ff5f0028;border-radius:16px;padding:0 16px;font-size:15px;background:#fffaf7;color:#1f1f1f;outline:none}}.auth-card input:focus{{border-color:#ff5f00;box-shadow:0 0 0 4px #ff5f0012}}.auth-login-hint{{margin:-2px 0 14px;color:#69707a;font-size:13px;line-height:1.45;font-weight:800}}.auth-meta{{display:flex;align-items:center;justify-content:space-between;margin:8px 0 22px;color:#69707a;font-size:14px}}.auth-submit{{width:100%;min-height:52px;border:0;border-radius:999px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;font-weight:950;box-shadow:0 14px 30px #ff5f0036}}.auth-guide{{display:none;margin:4px 0 12px}}.auth-guide.active{{display:block}}.auth-guide p{{margin:0 0 10px;color:#69707a;font-size:13px;line-height:1.45;font-weight:750}}.auth-switch{{margin-top:18px;text-align:center;color:#62666d;font-weight:750}}.auth-switch.hidden{{display:none}}.auth-switch button,.link-btn{{border:0;background:transparent;color:#ff5f00;font-weight:900}}.auth-close{{position:absolute;top:18px;right:18px;background:white}}.profile-hero{{margin:-22px -22px 16px;position:relative;min-height:290px;overflow:hidden;background:linear-gradient(135deg,#2b211d,#ff6a00);color:white}}.profile-cover{{position:absolute;inset:0;background:linear-gradient(145deg,#2a1d16,#ff6a00 58%,#ffd6ad);background-size:cover;background-position:center;filter:saturate(1.05)}}.profile-cover:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000020,#00000088)}}.profile-tools{{position:absolute;top:14px;right:14px;z-index:2;display:flex;gap:8px}}.profile-upload{{border:1px solid #ffffff60;border-radius:999px;min-height:34px;padding:0 10px;background:#ffffff28;color:white;font-size:12px;font-weight:850;backdrop-filter:blur(10px)}}.profile-info{{position:relative;z-index:1;padding:78px 18px 18px}}.profile-row{{display:flex;gap:14px;align-items:end}}.profile-avatar{{position:relative;width:92px;height:92px;border-radius:50%;border:4px solid white;background:white center/cover no-repeat;box-shadow:0 14px 28px #00000030;overflow:hidden}}.profile-avatar:before{{content:"";position:absolute;inset:0;background:radial-gradient(circle at 35% 25%,#ffc46b,#ff8e24 64%,#f97808)}}.profile-avatar.has-image:before{{display:none}}.profile-name{{margin:0 0 7px;font-size:28px;line-height:1.05;font-weight:950;text-shadow:0 2px 12px #00000035}}.profile-bio{{margin:0;color:#ffffffd8;font-size:13px;font-weight:750}}.profile-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:18px}}.profile-stats b{{display:block;font-size:19px;color:white}}.profile-stats span{{color:#ffffffc8;font-size:12px}}.profile-prefs{{margin-top:16px;display:flex;gap:8px;flex-wrap:wrap}}.profile-prefs .chip{{background:#ffffff22;color:white;border-color:#ffffff55;backdrop-filter:blur(8px)}}.profile-card-strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0 16px}}.profile-mini{{border:0;border-radius:16px;min-height:66px;background:#ffffffcc;color:#1f1f1f;font-size:12px;font-weight:850;box-shadow:0 10px 24px #552d0a10}}.profile-mini b{{display:block;color:#ff5f00;font-size:18px;margin-bottom:3px}}.profile-tabs{{position:sticky;top:62px;z-index:4;margin:0 -22px;padding:8px 22px;background:#fffaf5e8;backdrop-filter:blur(14px);border-bottom:1px solid #ff5f0012}}.profile-tabs .tabs{{padding:0}}.hidden-input{{display:none}}.modal{{align-items:stretch;padding:0;background:#fff;z-index:80}}.modal.active{{display:block}}.sheet{{width:min(100%,480px);height:100vh;max-height:100vh;margin:0 auto;border-radius:0;background:#fff;padding:0;overflow:auto}}.detail-top{{position:sticky;top:0;z-index:5;justify-content:flex-start;padding:10px;background:#ffffffd8}}.video-box{{height:auto;aspect-ratio:4/5;border-radius:0;margin:0;background:#050505}}.video-box iframe,.video-box img,.video-box video{{object-fit:contain}}.detail-content{{padding:12px 14px 90px;background:white}}.detail-title{{font-size:20px;margin:12px 0 8px}}.social-actions{{position:sticky;bottom:0;z-index:6;margin:0 -14px;padding:9px 12px;background:#fffffff2;border-top:1px solid #00000010;border-bottom:0;justify-content:space-around}}.social-btn{{border:0;box-shadow:none;background:white;color:#1f1f1f;font-size:26px;flex-direction:row}}.social-btn span{{font-size:14px;color:#1f1f1f}}.comment-pill{{min-height:42px;border-radius:999px;background:#f4f4f4;padding:0 14px;color:#777;display:flex;align-items:center;min-width:130px}}.bottom{{grid-template-columns:repeat(2,1fr)}}.landing .mascot{{position:absolute;right:-18px;bottom:-22px;width:250px;height:250px;border-radius:0;background:transparent;object-fit:contain;filter:drop-shadow(0 24px 30px #ff5f0036)}}.landing .hero:before{{content:"";position:absolute;right:-64px;bottom:-30px;width:286px;height:146px;border-radius:999px;background:linear-gradient(135deg,#ffd9bf,#ffb98c);opacity:.72}}.landing .hero:after{{content:"✦";position:absolute;right:204px;top:34px;color:#ff9f24;font-size:28px;text-shadow:70px 42px 0 #fff,22px 112px 0 #fff}}.title-row{{display:grid!important;grid-template-columns:1fr!important;align-items:start!important;gap:12px!important;margin-bottom:18px!important}}.title-row h1{{min-width:0!important;width:100%!important}}.reselect-title{{justify-self:start!important;max-width:none!important;min-width:0!important;min-height:42px!important;padding:0 16px!important;white-space:nowrap!important;line-height:1!important;text-align:center!important}}.featured-actions .primary,.featured-actions .featured-icon,.featured-next{{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:8px!important}}.btn-ico{{display:inline-grid;place-items:center;width:20px;height:20px;flex:0 0 20px;font-size:16px;line-height:1}}@media(max-width:380px){{.reselect-title{{font-size:11px!important;padding:0 12px!important}}.title-row{{gap:10px!important}}}}.top{{display:none!important}}.view[data-view="dashboard"]{{padding-top:14px!important}}.title-row{{display:flex!important;grid-template-columns:none!important;align-items:center!important;gap:10px!important;margin:0 0 12px!important}}.title-row h1{{min-width:0!important;width:auto!important;flex:1 1 auto!important;font-size:26px!important;line-height:1.05!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:clip!important;letter-spacing:-.02em!important}}.reselect-title{{flex:0 0 auto!important;justify-self:auto!important;max-width:none!important;min-width:0!important;min-height:34px!important;padding:0 11px!important;white-space:nowrap!important;line-height:1!important;text-align:center!important;font-size:11px!important;box-shadow:none!important}}.featured-card{{position:relative!important;isolation:isolate!important;overflow:hidden!important;border:1px solid #ff5f002a!important;box-shadow:0 18px 38px #552d0a12,0 1px 0 #ffffffd0 inset!important;transition:transform .24s ease,box-shadow .24s ease,border-color .24s ease!important;will-change:transform}}.featured-card:before{{content:""!important;position:absolute!important;inset:0!important;border-radius:30px!important;padding:1.5px!important;background:linear-gradient(115deg,#ff5f0000 0%,#ff5f0000 32%,#ff5f00 47%,#ffb16b 53%,#ff5f0000 68%,#ff5f0000 100%)!important;background-size:260% 260%!important;-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0)!important;-webkit-mask-composite:xor!important;mask-composite:exclude!important;pointer-events:none!important;z-index:4!important;opacity:.28!important;animation:kokoBorderSweep 6.5s ease-in-out infinite!important}}.featured-card:after{{content:""!important;position:absolute!important;inset:8px!important;border-radius:24px!important;background:radial-gradient(circle at 50% 0%,#ff7a0018,#ff7a0000 46%)!important;pointer-events:none!important;z-index:-1!important;opacity:.65!important;transition:opacity .24s ease!important}}.featured-card:hover,.featured-card:focus-within,.featured-card:active{{transform:translateY(-3px) scale(1.006)!important;border-color:#ff5f0078!important;box-shadow:0 26px 58px #552d0a20,0 0 0 1px #ff5f0020!important}}.featured-card:hover:before,.featured-card:focus-within:before,.featured-card:active:before{{opacity:.88!important;animation-duration:3.8s!important}}.featured-card:hover:after,.featured-card:focus-within:after,.featured-card:active:after{{opacity:1!important}}@keyframes kokoBorderSweep{{0%{{background-position:160% 0%}}52%{{background-position:-60% 100%}}100%{{background-position:160% 0%}}}}.featured-media{{aspect-ratio:1/1!important;min-height:0!important;background:#f8f0e9!important;display:block!important}}.featured-media img{{object-fit:contain!important;background:#f8f0e9!important}}.featured-media:after{{display:none!important}}.featured-body{{padding:12px 18px 15px!important}}.featured-title{{font-size:21px!important;margin-bottom:9px!important}}.featured-summary{{display:none!important}}.featured-tags{{margin-bottom:11px!important;gap:6px!important}}.featured-tags .tag{{font-size:10px!important;padding:5px 8px!important}}.featured-actions{{display:grid!important;grid-template-columns:18% 39% 39%!important;gap:9px!important;align-items:center!important;justify-content:center!important}}.featured-actions .primary,.featured-actions .featured-next,.featured-save{{width:100%!important;min-width:0!important;min-height:44px!important;margin:0!important;border-radius:999px!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:7px!important;white-space:nowrap!important}}.featured-save{{border:1px solid #ff5f0028!important;background:#fff7f0!important;color:#ff5f00!important;font-size:20px!important;font-weight:950!important;padding:0!important}}.featured-actions .primary,.featured-next{{border:0!important;background:linear-gradient(90deg,#ff6a00,#ff4d00)!important;color:#fff!important;font-size:13px!important;font-weight:950!important;padding:0 8px!important;box-shadow:0 10px 20px #ff5f0030!important}}.featured-next .btn-ico,.featured-next span{{color:#fff!important}}.featured-actions .btn-ico{{width:16px!important;height:16px!important;flex:0 0 16px!important;font-size:14px!important;line-height:1!important}}.featured-next .btn-ico{{transform:translateX(-1px)!important}}@media(max-width:380px){{.title-row h1{{font-size:23px!important}}.reselect-title{{font-size:10px!important;padding:0 9px!important}}.featured-body{{padding-left:16px!important;padding-right:16px!important}}.featured-actions{{grid-template-columns:18% 39% 39%!important;gap:7px!important}}.featured-actions .primary,.featured-actions .featured-next,.featured-save{{min-height:42px!important;font-size:12px!important}}}}
</style></head><body><main class="phone"><header class="top"><div class="brand">kwai <span>Koko</span></div></header>

<section class="view landing" data-view="home"><h1>Encontre roteiros que você consegue gravar</h1><p class="lead">Receba recomendações com base no seu perfil de criação, formatos que combinam com você e roteiros prontos para gravar.</p><div class="hero"><img class="mascot" src="/static/koko-creator-mascot-cutout.png" alt="Koko Creator"></div><div class="cta"><button class="primary" type="button" data-auth-open="login">Entrar com telefone</button><button class="landing-register" type="button" data-auth-open="register">Solicitar acesso</button></div><section class="landing-section"><h2>Veja antes de escolher</h2><div class="preview-strip"><div class="preview-card"><span>Preview do roteiro</span></div><div class="preview-card"><span>Referência em vídeo</span></div><div class="preview-card"><span>Estrutura de gravação</span></div></div></section><section class="landing-section"><div class="feature-row"><div class="feature"><b>1</b>Escolha seu perfil</div><div class="feature"><b>2</b>Veja recomendações</div><div class="feature"><b>3</b>Grave e envie</div></div></section><section class="landing-section"><h2>Criadores parceiros</h2><div class="author-cloud"><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span></div><div class="info-panel">Já trabalhamos com muitos grandes criadores da plataforma Kwai. Vídeos gravados a partir dos roteiros da Koko tiveram desempenho acima da média de visualizações dos próprios criadores, e em alguns casos ajudaram a aumentar a renda em até 200%.</div></section><section class="landing-section ending-card"><div>Pronto para começar a gravar com a Koko?<small>Entre com seu telefone, escolha suas preferências uma vez e volte todos os dias para ver novos roteiros.</small><br><button class="primary" type="button" data-auth-open="login">Entrar agora</button></div></section></section>
<section class="view" data-view="dashboard"><div id="dashboard-feed"></div></section>
<section class="view" data-view="missions"><div id="mission-feed"></div></section>
<section class="view" data-view="all-scripts"><div class="all-title-row"><button class="back-pill" type="button" data-go="dashboard">←</button><h1 id="all-title">Todos os roteiros</h1></div><div id="all-feed"></div></section>
<section class="view" data-view="choose"><span class="step-label" id="step-label">Etapa 1 de 3</span><div class="stepper" id="stepper"></div><div id="question"></div><div class="step-actions"><button class="secondary" id="prev-step" type="button"><span data-t="prev">Etapa anterior</span></button></div></section>

<section class="view" data-view="saved"><section class="profile-hero"><div class="profile-cover" id="profile-cover"></div><div class="profile-info"><div class="profile-tools"><button class="profile-upload" type="button" data-upload-trigger="cover" data-t="editCover">Capa</button><button class="profile-upload" type="button" data-upload-trigger="avatar" data-t="editAvatar">Avatar</button><button class="profile-upload profile-logout" type="button" data-logout data-t="logout">Sair</button></div><div class="profile-row"><div class="profile-avatar" id="profile-avatar"></div><div><h1 class="profile-name" id="creator-name">Koko Creator</h1><p class="profile-bio" data-t="profileBio">Biblioteca pessoal de roteiros e gravações.</p></div></div><div class="profile-stats"><div><b id="profile-count-finished">0</b><span data-t="statusFinished">Gravados</span></div></div><div class="profile-pref-row"><div class="profile-prefs" id="profile-filters"></div><button class="profile-pref-action" type="button" data-reselect>Mudar preferências</button></div></div></section><input class="hidden-input" id="profile-avatar-input" type="file" accept="image/*"><input class="hidden-input" id="profile-cover-input" type="file" accept="image/*"><section class="profile-card-strip"><button class="profile-mini" type="button" data-tab-jump="finished"><b>✓</b><span data-t="statusFinished">Gravados</span></button><button class="profile-mini" type="button" data-tab-jump="saved"><b>♡</b><span data-t="statusSaved">Salvos</span></button><button class="profile-mini" type="button" data-tab-jump="schedule"><b>▦</b><span id="schedule-mini-label">Calendário de gravação</span></button></section><div class="profile-tabs"><div class="tabs" id="saved-tabs"></div></div><div id="saved-feed"></div></section></main>

<nav class="bottom"><button data-go="dashboard">⌂<br><span data-t="navHome">Roteiros</span></button><button data-go="saved">☻<br><span data-t="navSaved">Eu</span></button></nav>
<div class="modal" id="modal"><section class="sheet"><div id="detail"></div></section></div>
<div class="auth-overlay" id="auth-modal"><button class="icon auth-close" type="button" data-auth-close>×</button><section class="auth-card"><h2 id="auth-title">Entrar</h2><form id="auth-form"><input name="phone" id="auth-phone" inputmode="text" autocomplete="username" placeholder="Telefone ou ID do Kwai"><p class="auth-login-hint" id="auth-login-hint">Use o telefone cadastrado no Kwai ou seu ID do Kwai para entrar.</p><div class="auth-guide" id="auth-guide"><p id="auth-guide-copy">Para liberar sua biblioteca, informe seu ID do Kwai.</p><input name="kwai_id" id="auth-kwai" autocomplete="username" placeholder="@seu_id_no_kwai"><input name="display_name" id="auth-display-name" autocomplete="name" placeholder="Nome do criador"><textarea name="reason" id="auth-reason" placeholder="Por que você quer acessar a Koko?"></textarea></div><button class="auth-submit" type="submit" id="auth-submit">Entrar</button><p class="auth-status" id="auth-status" role="status" aria-live="polite"></p><div class="auth-switch"><span id="auth-switch-copy">Ainda não tem conta?</span> <button type="button" data-auth-toggle id="auth-toggle">Solicitar acesso</button></div></form></section></div>
<div class="schedule-overlay" id="schedule-modal"><section class="schedule-sheet"><div class="schedule-head"><h2 id="schedule-title">Adicionar ao calendário de gravação</h2><button class="schedule-close" type="button" data-schedule-close>×</button></div><p class="schedule-note" id="schedule-note">Escolha o dia em que pretende gravar este roteiro.</p><div class="calendar-grid" id="calendar-grid"></div><div class="schedule-actions"><button class="secondary" type="button" data-schedule-close>Mais tarde</button><button class="primary" type="button" data-schedule-confirm>Adicionar</button></div></section></div>
<div class="mission-popup" id="mission-guide"><section class="mission-sheet mission-guide-card"><button class="mission-guide-close" type="button" data-mission-guide-x aria-label="Fechar">×</button><div class="mission-guide-hero"><span class="mission-guide-kicker" id="mission-guide-kicker">Campanha Koko</span><img class="mission-guide-mascot" src="/static/kwai-favicon.svg" alt="Kwai"><h2 id="mission-guide-title">Regrave vídeos da <span>Koko</span> e ganhe dinheiro</h2><p id="mission-guide-copy">até <strong class="mission-highlight">US$56 por semana</strong></p><div class="mission-rules-title"><span class="mission-prize-coin" aria-hidden="true"></span><div><b id="mission-rule-kicker">Regras do desafio diário</b><span id="mission-guide-prize">Escolha roteiros na <strong>Koko</strong>, grave e envie o link dentro da <strong>Koko</strong>. Ao publicar, use também: <em>#SeRirJáEra</em> <em>#EscolaComédia</em>.</span></div></div></div><div class="mission-rule-grid reward-rule-grid"><div class="mission-rule cash"><strong id="mission-rule-one-title">Regravou, ganhou em dinheiro</strong><span id="mission-rule-one-copy"><b>3 vídeos válidos por dia = US$3</b><small>A partir do 4º vídeo, cada extra vale <em>+US$1</em>. Bônus diário extra de até <em>US$5</em>.</small></span></div><div class="mission-rule views"><strong id="mission-rule-two-title">Quanto mais views, maior o prêmio</strong><span id="mission-rule-two-copy"><div class="reward-views-list"><span><em>30 mil views</em><b>US$1,5</b></span><span><em>100 mil views</em><b>US$3</b></span><span><em>500 mil views</em><b>US$10</b></span><span><em>1 milhão views</em><b>US$20</b></span></div><small class="reward-views-note">Cada vídeo recebe o maior nível alcançado.</small></span></div><div class="mission-rule gift"><strong id="mission-rule-three-title">Apoio de tráfego</strong><span id="mission-rule-three-copy"><b>Todo vídeo válido pode receber tráfego.</b><small>Bons conteúdos podem chegar a <em>milhões de exposições</em>.</small></span></div></div><label class="mission-read-card"><input id="mission-read" type="checkbox"> <span id="mission-read-label">Li e entendi as regras da campanha.</span></label><label class="mission-hide-card"><input id="mission-hide" type="checkbox"> <span id="mission-hide-label">Não mostrar novamente.</span></label><div class="mission-popup-actions"><button class="primary" type="button" id="mission-start" data-mission-guide-close disabled>Confirmar e começar</button></div></section></div>
<div class="mission-popup" id="mission-ranking"><section class="mission-sheet"><h2 id="mission-ranking-title">Ranking da semana</h2><p id="mission-ranking-copy">Quem completa mais missões aparece no topo.</p><div class="leaderboard mission-board-highlight" id="mission-ranking-list"></div><div class="mission-popup-actions"><button type="button" data-mission-ranking-close>Fechar</button><button class="primary" type="button" data-mission-ranking-close>Continuar gravando</button></div></section></div>
<div class="onboarding-overlay" id="creator-onboarding" aria-hidden="true"><div class="onboarding-spot" id="onboarding-spot"></div><section class="onboarding-card" id="onboarding-card"><span class="onboarding-step" id="onboarding-step">1/8</span><h3 id="onboarding-title">Como usar a Koko</h3><p id="onboarding-copy">Siga os passos para escolher e enviar seus vídeos.</p><div class="onboarding-actions"><button type="button" data-onboarding-back>Voltar</button><button type="button" data-onboarding-skip>Pular</button><button class="primary" type="button" data-onboarding-next>Próximo</button></div></section></div>
<div class="ui-toast" id="ui-toast" role="status" aria-live="polite"></div>
<script>
const questions={questions_json}; const profileKey="koko_profile_v1"; const workspaceKey="koko_workspace_v1"; const authKey="koko_creator_user_v1"; const profileUiKey="koko_creator_profile_ui_v1";
let lang="pt"; let step=0; let savedTab="finished"; let featuredOffset=0; let featuredKey=""; let entries=[]; let submissions=[];
let answers=JSON.parse(localStorage.getItem(profileKey)||"null")||{{people:"couple",subtype:"couple_prank",duration:["dur_120_plus"]}};
let workspace=JSON.parse(localStorage.getItem(workspaceKey)||"null")||{{saved:[],planned:[],finished:[],rejected:[],schedule:{{}}}};
if(!workspace.schedule||Array.isArray(workspace.schedule))workspace.schedule={{}};
let authMode="login"; let creatorUser=JSON.parse(localStorage.getItem(authKey)||"null"); let profileGateActive=false;
let profileUi=JSON.parse(localStorage.getItem(profileUiKey)||"null")||{{avatar:"",cover:""}};
let scheduleDraftId=""; let scheduleSelectedDate=""; let scheduleViewDate=todayKey();
const initialScriptId=(()=>{{const path=location.pathname.match(/^\\/script\\/([0-9a-f]{{32}})$/);if(path)return path[1];return new URLSearchParams(location.search).get("script")||""}})();
const forceLanding=new URLSearchParams(location.search).get("landing")==="1";
let analyticsCurrentScriptId=initialScriptId||"";
const analyticsSessionId=(window.crypto&&crypto.randomUUID)?crypto.randomUUID():String(Date.now())+"-"+String(Math.random()).slice(2);
let analyticsLastDurationAt=Date.now();
function analyticsPageType(){{return analyticsCurrentScriptId?"script":(document.querySelector(".view.active")?.dataset.view||"portal")}}
function track(event,meta){{try{{const payload={{event:event,path:location.pathname+location.search,page_type:analyticsPageType(),script_id:analyticsCurrentScriptId,duration_ms:0,meta:Object.assign({{session_id:analyticsSessionId}},meta||{{}})}};fetch("/api/analytics/events",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(payload),keepalive:true}}).catch(()=>null)}}catch(e){{}}}}
function trackDuration(finalSend){{try{{const now=Date.now();const duration=Math.max(0,now-analyticsLastDurationAt);if(duration<1500&&!finalSend)return;analyticsLastDurationAt=now;const payload={{event:"page_duration",path:location.pathname+location.search,page_type:analyticsPageType(),script_id:analyticsCurrentScriptId,duration_ms:duration,meta:{{session_id:analyticsSessionId,final:finalSend?"1":"0"}}}};const raw=JSON.stringify(payload);if(finalSend&&navigator.sendBeacon){{navigator.sendBeacon("/api/analytics/events",new Blob([raw],{{type:"application/json"}}));return}}fetch("/api/analytics/events",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:raw,keepalive:true}}).catch(()=>null)}}catch(e){{}}}}
window.addEventListener("beforeunload",()=>trackDuration(true));setInterval(()=>trackDuration(false),30000);
const I={{pt:{{homePill:"Biblioteca de roteiros",homeTitle:"Encontre roteiros que você consegue gravar",homeLead:"Responda 3 perguntas e veja roteiros para o seu estilo.",start:"Começar agora",seePopular:"Ver populares",todayPill:"Recomendação de roteiros",todayTitle:"Recomendação de roteiros",todayLead:"Abra e escolha um roteiro para ver os detalhes.",quickNew:"roteiros",quickSaved:"salvos",quickPlan:"para gravar",next:"Próxima etapa",prev:"Etapa anterior",finish:"Ver recomendações",libraryPill:"Biblioteca",libraryTitle:"Sua biblioteca recomendada",savedPill:"Meus roteiros",savedTitle:"Sua lista de gravação",navHome:"Roteiros",navMission:"Missões",navLibrary:"Biblioteca",navSaved:"Eu",navPrefs:"Perfil",changePrefs:"Mudar preferências",editCover:"Editar capa",editAvatar:"Editar avatar",logout:"Sair",profileBio:"Biblioteca pessoal de roteiros e gravações.",profileHome:"Início",open:"Abrir",save:"Salvar",plan:"Vou gravar",done:"Gravado",reject:"Não serve",original:"Referencia",details:"Detalhes",submitTitle:"Enviar vídeo gravado",submitHint:"Envie o link do vídeo gravado seguindo este roteiro. Vamos revisar e, se aprovado, ajudar com impulsionamento.",submitPlaceholder:"Cole aqui o link do seu vídeo",submitButton:"Enviar para revisão",submitOk:"Recebido. Vamos revisar seu vídeo.",submitError:"Não foi possível enviar. Confira o link.",empty:"Nada aqui ainda",emptyText:"Salve um roteiro da recomendação para montar sua lista.",statusSaved:"Salvos",statusPlanned:"Vou gravar",statusFinished:"Gravados",statusRejected:"Não servem",step:"Etapa"}},zh:{{homePill:"脚本推荐",homeTitle:"找到你真的能拍的脚本",homeLead:"回答 3 个问题，进入你的推荐脚本页面。",start:"开始选择",seePopular:"先看热门",todayPill:"脚本推荐",todayTitle:"脚本推荐",todayLead:"点开卡片，查看完整脚本和拍摄说明。",quickNew:"推荐脚本",quickSaved:"已收藏",quickPlan:"准备拍",next:"下一步",prev:"上一步",finish:"查看推荐",libraryPill:"脚本库",libraryTitle:"你的推荐脚本库",savedPill:"我的脚本",savedTitle:"你的拍摄清单",navHome:"脚本推荐",navMission:"每日任务",navLibrary:"脚本库",navSaved:"我",navPrefs:"偏好",changePrefs:"重新选择偏好",editCover:"编辑封面",editAvatar:"编辑头像",logout:"退出登录",profileBio:"你的脚本收藏和视频回传记录。",profileHome:"主页",open:"打开",save:"收藏",plan:"准备拍",done:"已拍",reject:"不适合",original:"参考视频",details:"完整脚本",submitTitle:"回传拍摄视频",submitHint:"上传按照脚本拍摄的视频，我们会审核后给您投流。",submitPlaceholder:"把你发布后的视频链接粘贴在这里",submitButton:"提交审核",submitOk:"已收到，我们会审核这个视频。",submitError:"提交失败，请检查链接。",empty:"这里还没有脚本",emptyText:"先从脚本推荐里收藏一个脚本。",statusSaved:"收藏",statusPlanned:"准备拍",statusFinished:"已拍",statusRejected:"不适合",step:"第"}}}};
	    const t=k=>(I.pt&&I.pt[k])||k; const label=x=>x.pt||x.zh||""; const esc=v=>String(v||"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
let uiToastTimer=null;
function uiCopy(pt,zh){{return lang==="zh"?zh:pt}}
function uiMessage(message,kind="",timeout=2400){{const toast=document.querySelector("#ui-toast");if(!toast)return;if(uiToastTimer)clearTimeout(uiToastTimer);toast.textContent=message;toast.className=`ui-toast show ${{kind}}`.trim();if(timeout>0)uiToastTimer=setTimeout(()=>toast.classList.remove("show"),timeout)}}
function setAuthStatus(message,kind=""){{const status=document.querySelector("#auth-status");if(!status)return;status.textContent=message||"";status.className=`auth-status ${{kind}}`.trim()}}
function setButtonBusy(button,busy,label=""){{if(!button)return;if(busy){{if(!button.dataset.idleText)button.dataset.idleText=button.textContent||"";button.disabled=true;button.classList.add("ui-busy");button.setAttribute("aria-busy","true");if(label)button.textContent=label}}else{{button.disabled=false;button.classList.remove("ui-busy");button.removeAttribute("aria-busy");if(button.dataset.idleText)button.textContent=button.dataset.idleText;delete button.dataset.idleText}}}}
function pulseControl(control){{if(!control||control.disabled)return;control.classList.add("ui-pressed");setTimeout(()=>control.classList.remove("ui-pressed"),150)}}
function answerValues(qid){{const v=answers[qid];return Array.isArray(v)?v:(v?[v]:[])}}
function isMultipleQuestion(q){{return !!q?.multiple}}
function optionAllowed(opt){{if(!opt)return false;if(Array.isArray(opt.people)&&opt.people.length&&!opt.people.includes(answers.people))return false;if(Array.isArray(opt.scenes)&&opt.scenes.length&&!opt.scenes.includes(answers.scene))return false;return true}}
function optionsFor(q){{return(q.options||[]).filter(optionAllowed)}}
function stepAvailable(i){{const q=questions[i];return !!q&&optionsFor(q).length>0}}
function stepCountLabel(){{return questions.filter((_,i)=>stepAvailable(i)).length||questions.length}}
function currentStepPosition(){{let n=0;for(let i=0;i<=step;i++)if(stepAvailable(i))n++;return Math.max(1,n)}}
function goStep(delta){{let i=step+delta;while(i>=0&&i<questions.length&&!stepAvailable(i))i+=delta;if(i>=0&&i<questions.length){{step=i;renderQuestion();return true}}return false}}
function nextAvailableAfter(i){{let n=i+1;while(n<questions.length&&!stepAvailable(n))n++;return n<questions.length?n:-1}}
function normalizeAnswers(){{let changed=false;questions.forEach(q=>{{const opts=optionsFor(q);if(!opts.length)return;const ids=opts.map(o=>o.id);if(isMultipleQuestion(q)){{let values=answerValues(q.id).filter(v=>ids.includes(v));if(!values.length)values=[ids[0]];if(JSON.stringify(values)!==JSON.stringify(answerValues(q.id))){{answers[q.id]=values;changed=true}}}}else if(!ids.includes(answers[q.id])){{answers[q.id]=ids[0];changed=true}}}});if(changed)saveProfile();return changed}}
function selectedAnswerValues(){{normalizeAnswers();return questions.filter((q,i)=>stepAvailable(i)).flatMap(q=>isMultipleQuestion(q)?answerValues(q.id):[answers[q.id]]).filter(Boolean)}}
function hasMultiDurationSelection(){{return answerValues("duration").filter(v=>/^dur_/.test(v)).length>1}}
function hasProfile(){{return !!localStorage.getItem(profileKey)}} function saveProfile(){{localStorage.setItem(profileKey,JSON.stringify(answers));persistAccountState()}} function saveWorkspace(){{localStorage.setItem(workspaceKey,JSON.stringify(workspace)); counts();persistAccountState()}} function saveProfileUi(){{localStorage.setItem(profileUiKey,JSON.stringify(profileUi));persistAccountState()}}
function updateCreatorName(){{const node=document.querySelector("#creator-name");if(node)node.textContent=creatorUser?.display_name||creatorUser?.account_id||creatorUser?.phone||creatorUser?.name||"Koko Creator"}}
function updateProfileImages(){{const avatar=document.querySelector("#profile-avatar");const cover=document.querySelector("#profile-cover");if(avatar){{avatar.classList.toggle("has-image",!!profileUi.avatar);avatar.style.backgroundImage=profileUi.avatar?`url("${{profileUi.avatar}}")`:""}}if(cover&&profileUi.cover)cover.style.backgroundImage=`url("${{profileUi.cover}}")`}}
function updateProfileHeader(){{updateCreatorName();updateProfileImages();const filters=document.querySelector("#profile-filters");if(filters){{const selected=chips();filters.innerHTML=selected||`<span class="chip">${{lang==="zh"?"未选择标签":"Sem preferências"}}</span>`}}const prefBtn=document.querySelector(".profile-pref-action");if(prefBtn)prefBtn.textContent=lang==="zh"?"重新选择标签":"Mudar preferências";const saved=document.querySelector("#profile-count-saved");if(saved)saved.textContent=String((workspace.saved||[]).length);const planned=document.querySelector("#profile-count-planned");if(planned)planned.textContent=String((workspace.planned||[]).length);const finished=document.querySelector("#profile-count-finished");if(finished)finished.textContent=String(submissions.length||0);const week=document.querySelector("#profile-count-week");if(week)week.textContent=String(missionWeeklyDone())}}
function authCopy(){{const zh=lang==="zh";return {{login:zh?"登录":"Entrar",register:zh?"申请":"Solicitar acesso",phone:zh?"手机号或 Kwai ID":"Telefone ou ID do Kwai",loginHint:zh?"使用注册 Kwai 的手机号或者 Kwai ID 登录。":"Use o telefone cadastrado no Kwai ou seu ID do Kwai para entrar.",loginSubmit:zh?"登录":"Entrar",registerSubmit:zh?"提交申请":"Enviar solicitação",profileSubmit:zh?"开始使用":"Comecar a usar",loginLoading:zh?"正在登录...":"Entrando...",registerLoading:zh?"正在提交...":"Enviando...",profileLoading:zh?"正在保存...":"Salvando...",loginOk:zh?"登录成功，正在进入...":"Login concluído. Abrindo sua conta...",profileOk:zh?"资料已保存。":"Perfil salvo.",missing:zh?"请输入手机号或 Kwai ID":"Digite seu telefone ou ID do Kwai",notFound:zh?"没有找到账号，请先申请开通。":"Conta não encontrada. Solicite acesso primeiro.",registerFailed:zh?"申请提交失败，请重试":"Nao foi possivel enviar a solicitacao",registered:zh?"申请已提交，我们会审核后开通账号。":"Solicitação recebida. Vamos revisar e liberar o acesso.",switchToRegister:zh?"如果没有账号，点击申请":"Ainda não tem acesso? Solicite aqui",switchToLogin:zh?"已有账号？点击登录":"Ja tem conta? Clique para entrar",profileTitle:zh?"完善 Kwai 信息":"Complete seu perfil Kwai",profileCopy:zh?"请输入你的 Kwai ID 和创作者名称，之后系统会把回传自动归到你的账号。":"Informe seu ID do Kwai e o nome do criador. Assim a Koko consegue organizar seus envios automaticamente.",applicationCopy:zh?"提交 Kwai ID、手机号和申请原因，运营审核后会为你开通登录权限。":"Envie seu ID do Kwai, telefone e motivo. A equipe vai revisar antes de liberar o acesso.",kwaiMissing:zh?"请输入 Kwai ID":"Informe seu ID do Kwai",reasonMissing:zh?"请输入申请原因":"Informe o motivo da solicitacao"}}}}
function accountNeedsProfile(account){{return !!account&&!String(account?.kwai_id||"").trim()}}
function authPasswordCopy(){{const zh=lang==="zh";return {{placeholder:zh?"登录密码（手机号后四位）":"Senha (4 últimos dígitos)",missing:zh?"请输入登录密码":"Digite a senha de acesso",hint:zh?"输入手机号/Kwai ID，以及手机号后四位登录。":"Use o telefone ou ID do Kwai e os 4 últimos dígitos do telefone."}}}}
function syncAuthPasswordInput(){{const phoneInput=document.querySelector("#auth-phone");if(!phoneInput)return null;let password=document.querySelector("#auth-password");if(!password){{phoneInput.insertAdjacentHTML("afterend",'<input name="password" id="auth-password" type="password" inputmode="numeric" autocomplete="current-password" placeholder="Senha (4 últimos dígitos)">');password=document.querySelector("#auth-password")}}const copy=authPasswordCopy();password.placeholder=copy.placeholder;password.hidden=authMode!=="login";password.required=authMode==="login";password.disabled=authMode!=="login";const hint=document.querySelector("#auth-login-hint");if(hint&&authMode==="login")hint.textContent=copy.hint;return password}}
function setAuthStep(nextStep){{authMode=nextStep==="profile"?"profile":nextStep==="register"?"register":"login";const c=authCopy();const guide=document.querySelector("#auth-guide");const switchCopy=document.querySelector("#auth-switch-copy");const toggle=document.querySelector("#auth-toggle");const reason=document.querySelector("#auth-reason");const display=document.querySelector("#auth-display-name");const phoneInput=document.querySelector("#auth-phone");const kwaiInput=document.querySelector("#auth-kwai");const loginHint=document.querySelector("#auth-login-hint");setAuthStatus("");document.querySelector("#auth-title").textContent=authMode==="profile"?c.profileTitle:authMode==="register"?c.register:c.login;document.querySelector("#auth-submit").textContent=authMode==="profile"?c.profileSubmit:authMode==="register"?c.registerSubmit:c.loginSubmit;if(phoneInput){{phoneInput.placeholder=c.phone;phoneInput.disabled=authMode==="profile";if(authMode==="profile")phoneInput.value=creatorUser?.phone||creatorUser?.account_id||phoneInput.value||""}}if(authMode==="profile"){{if(display)display.value=creatorUser?.display_name||creatorUser?.name||"";if(kwaiInput)kwaiInput.value=creatorUser?.kwai_id||""}}if(loginHint){{loginHint.textContent=c.loginHint;loginHint.hidden=authMode!=="login"}}document.querySelector("#auth-guide-copy").textContent=authMode==="register"?c.applicationCopy:c.profileCopy;guide?.classList.toggle("active",authMode==="profile"||authMode==="register");if(reason)reason.hidden=authMode!=="register";if(display)display.hidden=authMode==="register";if(switchCopy)switchCopy.textContent=authMode==="register"?c.switchToLogin:c.switchToRegister;if(toggle){{toggle.textContent=authMode==="register"?c.login:c.register;toggle.dataset.authToggle=authMode==="register"?"login":"register";toggle.closest(".auth-switch")?.classList.toggle("hidden",authMode==="profile")}}}}
function setAuthMode(mode){{setAuthStep(mode==="profile"?"profile":mode==="register"?"register":"login");syncAuthPasswordInput()}}
function openAuth(mode="login"){{setAuthStep(mode==="profile"?"profile":mode==="register"?"register":"login");syncAuthPasswordInput();document.querySelector("#auth-modal").classList.add("active")}}
function closeAuth(force=false){{if(profileGateActive&&!force)return;document.querySelector("#auth-modal").classList.remove("active")}}
function requireKwaiProfile(source="auto"){{if(!accountNeedsProfile(creatorUser)){{profileGateActive=false;return false}}profileGateActive=true;openAuth("profile");track("profile_required",{{source}});return true}}
async function loadAccountState(){{if(!creatorUser)return null;try{{const r=await fetch(`/api/me/state?_=${{Date.now()}}`);const d=await r.json();if(r.status===401){{creatorUser=null;localStorage.removeItem(authKey);return null}}if(!r.ok)throw new Error(d.error||"state failed");creatorUser=d.account||creatorUser;localStorage.setItem(authKey,JSON.stringify(creatorUser));const state=d.state||{{}};if(state.preferences){{answers=state.preferences;localStorage.setItem(profileKey,JSON.stringify(answers))}}if(state.workspace){{workspace=state.workspace;if(!workspace.schedule||Array.isArray(workspace.schedule))workspace.schedule={{}};localStorage.setItem(workspaceKey,JSON.stringify(workspace))}}if(state.profile_ui){{profileUi=state.profile_ui;localStorage.setItem(profileUiKey,JSON.stringify(profileUi))}}submissions=Array.isArray(d.submissions)?d.submissions:submissions;return d}}catch(err){{return null}}}}
let persistTimer=null;let persistErrorShownAt=0;function persistAccountState(){{if(!creatorUser)return;if(persistTimer)clearTimeout(persistTimer);persistTimer=setTimeout(async()=>{{try{{const response=await fetch("/api/me/state",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{preferences:answers,workspace,profile_ui:profileUi,language:lang}})}});if(!response.ok)throw new Error(`HTTP ${{response.status}}`)}}catch(err){{const now=Date.now();if(now-persistErrorShownAt>30000){{persistErrorShownAt=now;uiMessage(uiCopy("Nao foi possivel sincronizar suas alteracoes. Tente novamente em instantes.","暂时无法同步修改，请稍后重试。"),"error",5000)}}}}}},260)}}
async function handleAuthSubmit(e){{e.preventDefault();const button=document.querySelector("#auth-submit");if(button?.disabled)return;const form=new FormData(e.currentTarget);const phone=String(form.get("phone")||"").replace(/\\s+/g,"").trim();const c=authCopy();const loading=authMode==="profile"?c.profileLoading:authMode==="register"?c.registerLoading:c.loginLoading;setButtonBusy(button,true,loading);setAuthStatus(loading,"loading");try{{if(authMode==="register"){{if(!phone)throw new Error(c.missing);const kwai_id=String(form.get("kwai_id")||"").trim();const reason=String(form.get("reason")||"").trim();if(!kwai_id)throw new Error(c.kwaiMissing);if(!reason)throw new Error(c.reasonMissing);const r=await fetch("/api/auth/register",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{phone,kwai_id,reason}})}});const d=await r.json().catch(()=>({{}}));if(!r.ok)throw new Error(d.error||c.registerFailed);setAuthStatus(c.registered,"success");uiMessage(c.registered,"success",3200);setTimeout(()=>{{setAuthStep("login");document.querySelector("#auth-phone").value=phone}},900);return}}if(authMode==="profile"){{const kwai_id=String(form.get("kwai_id")||"").trim();const display_name=String(form.get("display_name")||"").trim();if(!kwai_id)throw new Error(c.kwaiMissing);const r=await fetch("/api/me/profile",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{kwai_id,display_name}})}});const d=await r.json().catch(()=>({{}}));if(!r.ok)throw new Error(d.error||c.notFound);creatorUser=d.account;localStorage.setItem(authKey,JSON.stringify(creatorUser));await loadAccountState();updateCreatorName();setAuthStatus(c.profileOk,"success");uiMessage(c.profileOk,"success");profileGateActive=false;closeAuth(true);track("page_view",{{source:"after_profile"}});if(!hasProfile())show("choose");else show("dashboard");return}}if(!phone)throw new Error(c.missing);const password=String(form.get("password")||"").trim();if(!password)throw new Error(authPasswordCopy().missing);const r=await fetch("/api/auth/login",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{phone,password}})}});const d=await r.json().catch(()=>({{}}));if(!r.ok)throw new Error(d.error||c.notFound);creatorUser=d.account;localStorage.setItem(authKey,JSON.stringify(creatorUser));setAuthStatus(c.loginOk,"success");uiMessage(c.loginOk,"success");await loadAccountState();updateCreatorName();if(requireKwaiProfile("after_login"))return;closeAuth();track("page_view",{{source:"after_login"}});if(!hasProfile())show("choose");else show("dashboard")}}catch(err){{const message=err.message||c.notFound;setAuthStatus(message,"error");uiMessage(message,"error",3200)}}finally{{setButtonBusy(button,false)}}}}
async function logout(button){{if(button?.disabled)return;setButtonBusy(button,true,uiCopy("Saindo...","退出中..."));uiMessage(uiCopy("Saindo da conta...","正在退出账号..."),"loading",0);try{{await fetch("/api/auth/logout",{{method:"POST",body:"{{}}"}});creatorUser=null;localStorage.removeItem(authKey);closeDetail();closeAuth();show("home");uiMessage(uiCopy("Você saiu da conta.","已退出账号。"),"success")}}catch(err){{uiMessage(uiCopy("Não foi possível sair. Tente novamente.","退出失败，请重试。"),"error")}}finally{{setButtonBusy(button,false)}}}}
function ids(k){{return new Set(workspace[k]||[])}} function statusOf(id){{return ids("planned").has(id)?"planned":ids("finished").has(id)?"finished":ids("rejected").has(id)?"rejected":ids("saved").has(id)?"saved":""}} function entry(id){{return entries.find(e=>e.entry_id===id)}}
function setStatus(id,status){{["saved","planned","finished","rejected"].forEach(k=>workspace[k]=(workspace[k]||[]).filter(x=>x!==id)); if(status) workspace[status]=[...(workspace[status]||[]),id]; saveWorkspace(); renderCurrent()}}
function counts(){{const n=document.querySelector("#count-new");if(n)n.textContent=String(entries.length);const s=document.querySelector("#count-saved");if(s)s.textContent=String((workspace.saved||[]).length);const p=document.querySelector("#count-planned");if(p)p.textContent=String((workspace.planned||[]).length);updateProfileHeader()}}
function applyLang(){{document.documentElement.lang="pt-BR";document.querySelectorAll("[data-t]").forEach(n=>n.textContent=t(n.dataset.t));document.querySelectorAll("[data-html]").forEach(n=>n.innerHTML=t(n.dataset.html));renderQuestion();renderCurrent();counts();setAuthMode(authMode)}}

function show(v){{if(v==="library")v="dashboard";if(["dashboard","missions","saved","all-scripts","choose"].includes(v)&&requireKwaiProfile(`show_${{v}}`))return;if(["dashboard","missions","saved","all-scripts"].includes(v)&&(!creatorUser||!hasProfile()))v="home";if(v==="choose"&&!creatorUser)v="home";if(v==="choose")step=0;if(v!=="detail"&&!initialScriptId)analyticsCurrentScriptId="";document.querySelectorAll("[data-view]").forEach(x=>x.classList.toggle("active",x.dataset.view===v));if(v==="choose")renderQuestion();if(v==="dashboard")renderDashboard();if(v==="all-scripts")renderAllScripts();if(v==="missions")renderMissions();if(v==="saved")renderSaved();document.querySelectorAll(".bottom button").forEach(b=>b.classList.toggle("active",b.dataset.go===v||v==="all-scripts"&&b.dataset.go==="dashboard"));scrollTo({{top:0,behavior:"smooth"}})}}

function renderQuestion(){{normalizeAnswers();if(!stepAvailable(step)){{const first=questions.findIndex((_,i)=>stepAvailable(i));step=first>=0?first:0}}const q=questions[step];const opts=optionsFor(q);const total=stepCountLabel();const pos=currentStepPosition();const multi=isMultipleQuestion(q);document.querySelector("#step-label").textContent=lang==="zh"?`${{t("step")}} ${{pos}} / ${{total}}`:`${{t("step")}} ${{pos}} de ${{total}}`;document.querySelector("#stepper").innerHTML=questions.map((_,i)=>stepAvailable(i)?`<button class="step ${{i===step?"active":""}}" type="button" data-step="${{i}}">${{questions.slice(0,i+1).filter((_,j)=>stepAvailable(j)).length}}</button>`:"").join("");document.querySelector("#question").innerHTML=`<h1>${{esc(label(q))}}</h1>${{multi?`<p class="lead">${{lang==="zh"?"可以多选，Koko 会把这些时长的脚本合并推荐。":"Pode escolher mais de uma duração. A Koko mistura esses roteiros na recomendação."}}</p>`:""}}<div class="options">${{opts.map(o=>`<button class="option ${{answerValues(q.id).includes(o.id)?"selected":""}}" data-answer="${{q.id}}" data-value="${{o.id}}">${{esc(label(o))}}</button>`).join("")}}</div>${{multi?`<button class="primary question-submit" type="button" id="next-step"><span>${{t("finish")}}</span></button>`:""}}`;const next=document.querySelector("#next-step span");if(next)next.textContent=nextAvailableAfter(step)<0?t("finish"):t("next");const prev=document.querySelector("#prev-step");if(prev){{prev.style.visibility=questions.slice(0,step).some((_,i)=>stepAvailable(i))?"visible":"hidden";prev.disabled=prev.style.visibility==="hidden"}}}}
function entryTimestamp(e){{const raw=e.script_date||e.created_at||e.saved_at||"";const n=Date.parse(raw);return Number.isNaN(n)?0:n}}
let entriesLoadedLimit=0;let entriesLoadedKey="";let entriesTotal=0;
function recommendationKey(){{return selectedAnswerValues().join("|")}}
async function loadEntries(limit=48,opts={{}}){{const key=recommendationKey();const force=!!opts.force;if(!force&&entries.length&&entriesLoadedKey===key&&entriesLoadedLimit>=limit){{counts();return entries}}const cacheKey=`koko_reco_cache_v4_paged_${{key}}_${{limit}}`;if(!force){{try{{const cached=JSON.parse(sessionStorage.getItem(cacheKey)||"null");if(cached&&Date.now()-cached.ts<10*60*1000&&Array.isArray(cached.entries)){{entries=cached.entries;entriesTotal=Number(cached.total)||cached.entries.length;entriesLoadedKey=key;entriesLoadedLimit=limit;counts();return entries}}}}catch(err){{}}}}const p=new URLSearchParams({{limit:String(limit)}});selectedAnswerValues().forEach(v=>p.append("selected",v));const r=await fetch(`/api/creator/recommendations?${{p.toString()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"load failed");let loaded=(d.entries||[]).slice();entriesTotal=Number(d.total)||loaded.length;if(!loaded.length&&forceLocalOnboarding&&selectedAnswerValues().length){{const fallbackParams=new URLSearchParams({{limit:String(limit)}});const fallback=await fetch(`/api/creator/recommendations?${{fallbackParams.toString()}}`);const fallbackData=await fallback.json();if(fallback.ok){{loaded=(fallbackData.entries||[]).slice();entriesTotal=Number(fallbackData.total)||loaded.length}}}}entries=loaded;entries.sort((a,b)=>entryTimestamp(b)-entryTimestamp(a));entriesLoadedKey=key;entriesLoadedLimit=limit;try{{sessionStorage.setItem(cacheKey,JSON.stringify({{ts:Date.now(),entries,total:entriesTotal}}))}}catch(err){{}}counts();return entries}}
function chips(){{const lookup=Object.fromEntries(questions.flatMap(q=>q.options.map(o=>[o.id,o])));return selectedAnswerValues().map(id=>lookup[id]).filter(Boolean).map(o=>`<span class="chip">${{esc(label(o))}} ✓</span>`).join("")}}
function dayKey(d){{const y=d.getFullYear();const m=String(d.getMonth()+1).padStart(2,"0");const day=String(d.getDate()).padStart(2,"0");return `${{y}}-${{m}}-${{day}}`}}
function todayKey(){{return dayKey(new Date())}}
function scheduleLabel(key){{const d=new Date(`${{key}}T00:00:00`);if(Number.isNaN(d.getTime()))return key;return lang==="zh"?`${{d.getMonth()+1}}月${{d.getDate()}}日`:`${{String(d.getDate()).padStart(2,"0")}}/${{String(d.getMonth()+1).padStart(2,"0")}}`}}
function scheduleCount(){{return Object.values(workspace.schedule||{{}}).reduce((n,arr)=>n+(Array.isArray(arr)?arr.length:0),0)}}
function saveScheduleItem(id,date){{workspace.schedule=workspace.schedule||{{}};const key=date||todayKey();Object.keys(workspace.schedule).forEach(k=>workspace.schedule[k]=(workspace.schedule[k]||[]).filter(x=>x!==id));workspace.schedule[key]=[...(workspace.schedule[key]||[]),id];scheduleViewDate=key;saveWorkspace()}}
function openScheduleModal(id){{scheduleDraftId=id;scheduleSelectedDate=todayKey();renderCalendar();document.querySelector("#schedule-title").textContent=lang==="zh"?"加入拍摄日历":"Adicionar ao calendário de gravação";document.querySelector("#schedule-note").textContent=lang==="zh"?"选择你准备拍摄这个脚本的日期。":"Escolha o dia em que pretende gravar este roteiro.";document.querySelector(".schedule-actions [data-schedule-close]").textContent=lang==="zh"?"稍后再说":"Mais tarde";document.querySelector("[data-schedule-confirm]").textContent=lang==="zh"?"加入拍摄日历":"Adicionar";document.querySelector("#schedule-modal").classList.add("active")}}
function closeScheduleModal(){{document.querySelector("#schedule-modal").classList.remove("active");scheduleDraftId=""}}
function renderCalendar(){{const root=document.querySelector("#calendar-grid");if(!root)return;const base=scheduleSelectedDate?new Date(`${{scheduleSelectedDate}}T00:00:00`):new Date();const first=new Date(base.getFullYear(),base.getMonth(),1);const start=new Date(first);start.setDate(first.getDate()-first.getDay());const weekdays=lang==="zh"?["日","一","二","三","四","五","六"]:["D","S","T","Q","Q","S","S"];let html=weekdays.map(w=>`<div class="calendar-weekday">${{w}}</div>`).join("");for(let i=0;i<35;i++){{const d=new Date(start);d.setDate(start.getDate()+i);const key=dayKey(d);const muted=d.getMonth()!==base.getMonth();const selected=key===scheduleSelectedDate;html+=`<button class="calendar-day ${{muted?"muted":""}} ${{selected?"selected":""}}" type="button" data-schedule-date="${{key}}">${{d.getDate()}}</button>`}}root.innerHTML=html}}
function thumbImage(e){{return e?.entry_id?`/api/creator/thumbnail/${{e.entry_id}}.webp`:""}}
function scriptImage(e){{return String(thumbImage(e)||e.thumbnail_url||e.preview_image_url||e.cover_url||storyboardDemoUrl||"").trim()}}
function scheduleItem(e,date){{return `<button class="schedule-item" type="button" data-detail="${{esc(e.entry_id)}}"><img src="${{esc(scriptImage(e))}}" loading="lazy" alt=""><div><h3>${{esc(ptTitle(e))}}</h3><p>${{esc(ptTag(e.content_type||""))}} · ${{esc(scheduleLabel(date))}}</p></div></button>`}}
function monthTitle(date){{return lang==="zh"?`${{date.getFullYear()}}年${{date.getMonth()+1}}月`:date.toLocaleDateString("pt-BR",{{month:"long",year:"numeric"}})}}
function shiftScheduleMonth(delta){{const base=new Date(`${{scheduleViewDate||todayKey()}}T00:00:00`);base.setMonth(base.getMonth()+delta);scheduleViewDate=dayKey(base);renderScheduleFeed()}}
function renderShootCalendar(schedule){{const base=scheduleViewDate?new Date(`${{scheduleViewDate}}T00:00:00`):new Date();const first=new Date(base.getFullYear(),base.getMonth(),1);const start=new Date(first);start.setDate(first.getDate()-first.getDay());const weekdays=lang==="zh"?["日","一","二","三","四","五","六"]:["D","S","T","Q","Q","S","S"];let cells=weekdays.map(w=>`<div class="shoot-weekday">${{w}}</div>`).join("");for(let i=0;i<42;i++){{const d=new Date(start);d.setDate(start.getDate()+i);const key=dayKey(d);const count=(schedule[key]||[]).length;const outside=d.getMonth()!==base.getMonth();const active=key===scheduleViewDate;cells+=`<button class="shoot-day ${{outside?"outside":""}} ${{active?"active":""}} ${{count?"has-items":""}}" type="button" data-shoot-date="${{key}}"><span>${{d.getDate()}}</span>${{count?`<i class="shoot-dot">${{count}}</i>`:""}}</button>`}}return `<section class="shoot-calendar-panel"><div class="shoot-calendar-head"><button class="shoot-month-btn" type="button" data-shoot-month="-1">‹</button><div class="shoot-month-title"><b>${{esc(monthTitle(base))}}</b><span>${{lang==="zh"?"选择日期查看待拍脚本":"Toque em um dia para ver tarefas"}}</span></div><button class="shoot-month-btn" type="button" data-shoot-month="1">›</button></div><div class="shoot-grid">${{cells}}</div></section>`}}
function renderScheduleFeed(){{const root=document.querySelector("#saved-feed");const schedule=workspace.schedule||{{}};const selected=scheduleViewDate||todayKey();const planned=(schedule[selected]||[]).map(entry).filter(Boolean);const count=scheduleCount();const agenda=planned.length?planned.map(e=>scheduleItem(e,selected)).join(""):`<section class="shoot-empty"><b>${{count?esc(scheduleLabel(selected)):(lang==="zh"?"还没有加入拍摄日历":"Calendario de gravacao vazio")}}</b>${{count?(lang==="zh"?"这一天还没有待拍脚本，点有橙色标记的日期看看。":"Este dia ainda nao tem roteiro. Toque em um dia marcado em laranja."):(lang==="zh"?"收藏脚本后，可以把它加入某一天的拍摄日历。":"Salve um roteiro e escolha um dia para gravar.")}}</section>`;root.innerHTML=`<section class="shoot-calendar">${{renderShootCalendar(schedule)}}<section class="shoot-agenda"><div class="shoot-agenda-title"><b>${{esc(scheduleLabel(selected))}}</b><span>${{planned.length}} ${{lang==="zh"?"个待拍脚本":"roteiro(s)"}}</span></div>${{agenda}}</section></section>`}}
function dateKey(e){{const raw=String(e.script_date||"");const m=raw.match(/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})/);return m?`${{m[1]}}-${{m[2]}}-${{m[3]}}`:"recent"}}
function dateLabel(key){{if(key==="recent")return lang==="zh"?"近期":"Recentes";const [y,m,d]=key.split("-");return `${{y}}.${{Number(m)}}.${{Number(d)}}`}}
function masonryCard(e,i){{const planned=missionState().picks.includes(e.entry_id)||ids("planned").has(e.entry_id);return `<article class="masonry-card is-article"><img src="${{esc(scriptImage(e))}}" loading="lazy" alt="" data-detail="${{esc(e.entry_id)}}"><span class="masonry-title" data-detail="${{esc(e.entry_id)}}">${{esc(ptTitle(e))}}</span><div class="masonry-actions"><button class="masonry-plan" type="button" data-plan-script="${{esc(e.entry_id)}}">${{planned?(lang==="zh"?"已加入拍摄计划":"No plano"):(lang==="zh"?"加入拍摄计划":"Adicionar ao plano")}}</button><button class="masonry-open" type="button" data-detail="${{esc(e.entry_id)}}">${{lang==="zh"?"查看脚本":"Ver roteiro"}}</button></div></article>`}}
function card(e,i){{const s=statusOf(e.entry_id);return `<article class="script card"><div class="thumb"><img src="${{esc(scriptImage(e))}}" loading="lazy" alt=""><span>${{Math.max(78,96-Math.min(i,18))}} match</span></div><div class="body"><h3>${{esc(ptTitle(e))}}</h3><p>${{esc(preferPortugueseText(e.summary))}}</p><div class="tags"><span class="tag">${{esc(ptTag(e.content_type))}}</span>${{durationLabel(e)?`<span class="tag">${{esc(durationLabel(e))}}</span>`:""}}${{s?`<span class="tag">${{esc(ptTag(s))}}</span>`:""}}</div><div class="actions"><button class="open" data-detail="${{esc(e.entry_id)}}">▷ ${{t("open")}}</button><button class="icon" data-status="${{s==="saved"?"":"saved"}}" data-entry="${{esc(e.entry_id)}}">${{s==="saved"?"✓":"♡"}}</button><button class="icon" data-status="planned" data-entry="${{esc(e.entry_id)}}">＋</button></div></div></article>`}}
function renderList(sel,list){{document.querySelector(sel).innerHTML=list.length?list.map(card).join(""):`<section class="state card"><h3>${{t("empty")}}</h3><p class="lead">${{t("emptyText")}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`}}
function masonryHtml(list){{if(!list.length)return `<section class="state card"><h3>${{t("empty")}}</h3><p class="lead">${{t("emptyText")}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`;const groups=new Map();list.forEach(e=>{{const key=dateKey(e);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e)}});const keys=[...groups.keys()].sort((a,b)=>b.localeCompare(a));return keys.map(key=>`<section class="date-group"><div class="date-divider">${{esc(dateLabel(key))}}</div><div class="masonry">${{groups.get(key).map(masonryCard).join("")}}</div></section>`).join("")}}
function renderMasonry(sel,list){{document.querySelector(sel).innerHTML=masonryHtml(list)}}
function renderAllScriptsFeed(){{const root=document.querySelector("#all-feed");if(!root)return;const more=entries.length<entriesTotal;root.innerHTML=masonryHtml(entries)+`<section class="all-scripts-load"><span>${{lang==="zh"?`已显示 ${{entries.length}} / ${{entriesTotal}} 条`:`${{entries.length}} de ${{entriesTotal}} roteiros`}}</span>${{more?`<button class="primary" type="button" data-all-load-more>${{lang==="zh"?"继续加载 50 条":"Carregar mais 50"}}</button>`:""}}</section>`}}
async function loadMoreAllScripts(){{const button=document.querySelector("[data-all-load-more]");if(button?.disabled)return;setButtonBusy(button,true,uiCopy("Carregando...","加载中..."));uiMessage(uiCopy("Carregando mais roteiros...","正在加载更多脚本..."),"loading",0);try{{await ensure(Math.min(entriesTotal||500,entries.length+50));renderAllScriptsFeed();uiMessage(uiCopy("Mais roteiros carregados.","更多脚本已加载。"),"success")}}catch(err){{uiMessage(uiCopy("Falha ao carregar. Toque para tentar novamente.","加载失败，请点击重试。"),"error",3200);setButtonBusy(button,false);if(button)button.textContent=uiCopy("Tentar novamente","重试")}}}}
function preloadImagesAround(index){{if(!entries.length)return;const warm=()=>{{const item=entries[(index+1)%entries.length];const url=scriptImage(item);if(url){{const img=new Image();img.decoding="async";img.src=url;}}}};if("requestIdleCallback" in window)requestIdleCallback(warm,{{timeout:1800}});else setTimeout(warm,900)}}

function featuredCard(e,i,total=10){{const tags=[ptTag(e.content_type),durationLabel(e)].filter(Boolean);const hasVideo=!!String(e.video_url||"").trim();const picked=missionState().picks.includes(e.entry_id);return `<section class="featured-shell"><div class="feature-context"><b>${{lang==="zh"?"今日脚本推荐":"Roteiro recomendado hoje"}}</b><span>${{i+1}}/${{total}}</span></div><div class="featured-card-wrap"><article class="featured-card" data-feature-card="${{esc(e.entry_id)}}"><div class="featured-scroll-area"><div class="featured-media" data-feature-media="${{esc(e.entry_id)}}" data-original-video="${{esc(e.video_url||"")}}"><img src="${{esc(scriptImage(e))}}" loading="eager" alt=""><div class="featured-video-shell" data-feature-video-shell></div>${{hasVideo?`<button class="featured-play" type="button" data-feature-play="${{esc(e.entry_id)}}" aria-label="${{lang==="zh"?"播放参考视频":"Reproduzir referencia"}}"><span>▶</span></button>`:""}}</div><div class="featured-body"><h2 class="featured-title">${{esc(ptTitle(e))}}</h2><div class="featured-tags">${{tags.map(x=>`<span class="tag">${{esc(x)}}</span>`).join("")}}</div><div class="script-expand-cue"><button class="scroll-cue" type="button" data-scroll-script="${{esc(e.entry_id)}}" aria-label="${{lang==="zh"?"点击展开查看脚本细节":"Toque para ver detalhes do roteiro"}}">⌄</button><span>${{lang==="zh"?"点击展开查看脚本细节":"Toque para ver detalhes do roteiro"}}</span></div>${{inlineScriptShell(e)}}</div></div>${{preferenceStripHtml()}}<div class="featured-actions pick-actions"><button class="pick-skip" type="button" data-feature-skip><span class="pick-mark">✕</span><span>${{lang==="zh"?"不想拍摄":"Não quero gravar"}}</span></button><button class="pick-plan ${{picked?"is-picked":""}}" type="button" data-plan-script="${{esc(e.entry_id)}}"><span class="pick-mark">✓</span><span>${{lang==="zh"?"我要拍摄":"Quero gravar"}}</span></button></div></article></div></section>`}}
function stopFeaturedVideo(){{document.querySelectorAll("[data-feature-media]").forEach(media=>{{media.classList.remove("playing","loading");media.querySelectorAll("video").forEach(v=>{{try{{v.pause();v.removeAttribute("src");v.load()}}catch(e){{}}}});const shell=media.querySelector("[data-feature-video-shell]");if(shell)shell.innerHTML="";media.querySelector(".featured-video-loading")?.remove();media.querySelector(".featured-video-error")?.remove();}})}}
async function playFeaturedVideo(id){{const media=document.querySelector(`[data-feature-media="${{CSS.escape(id)}}"]`);if(!media||media.classList.contains("loading"))return;stopFeaturedVideo();const loadingLabel=lang==="zh"?"视频加载中":"Carregando vídeo";media.classList.add("loading");media.insertAdjacentHTML("beforeend",`<div class="featured-video-loading" data-label="${{esc(loadingLabel)}}"></div>`);const shell=media.querySelector("[data-feature-video-shell]");const e=entry(id)||{{}};const finishLoading=()=>{{media.classList.remove("loading");media.querySelector(".featured-video-loading")?.remove()}};try{{const playback=await fetchVideoPlayback(id);const poster=esc(scriptImage(e));if(playback.video_source_url){{shell.innerHTML=`<video src="${{esc(playback.video_source_url)}}" poster="${{poster}}" controls playsinline preload="auto" autoplay></video>`;media.classList.add("playing");const video=shell.querySelector("video");let done=false;const ready=()=>{{if(done)return;done=true;finishLoading()}};video?.addEventListener("loadeddata",ready,{{once:true}});video?.addEventListener("canplay",ready,{{once:true}});video?.addEventListener("playing",ready,{{once:true}});setTimeout(ready,4500);try{{await video?.play?.()}}catch(err){{}}return}}if(playback.embed_url){{shell.innerHTML=`<iframe src="${{esc(playback.embed_url)}}" title="video preview" loading="eager" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin" sandbox="allow-scripts allow-same-origin allow-popups allow-presentation allow-forms"></iframe>`;media.classList.add("playing");const iframe=shell.querySelector("iframe");let done=false;const ready=()=>{{if(done)return;done=true;finishLoading()}};iframe?.addEventListener("load",ready,{{once:true}});setTimeout(ready,5000);return}}throw new Error("no playable source")}}catch(err){{finishLoading();const disabled=err?.code==="reference_video_disabled"||e.reference_video_enabled===false;const url=disabled?"":String(media.dataset.originalVideo||e.video_url||"");const message=disabled?(lang==="zh"?"原视频访问失败，请稍后再试":"Falha ao acessar o vídeo original. Tente novamente mais tarde."):(lang==="zh"?"站内预览暂时加载失败。":"A prévia não carregou agora.");media.insertAdjacentHTML("beforeend",`<div class="featured-video-error">${{esc(message)}} ${{url?`<a href="${{esc(url)}}" target="_blank" rel="noopener">${{lang==="zh"?"打开参考视频":"Abrir vídeo"}}</a>`:""}}</div>`)}}}}
async function ensure(limit=48){{if(!entries.length||entriesLoadedKey!==recommendationKey()||entriesLoadedLimit<limit)await loadEntries(limit)}} function missionDayKey(){{return todayKey()}}
function missionState(day){{workspace.missions=workspace.missions||{{}};const key=day||missionDayKey();workspace.missions[key]=workspace.missions[key]||{{picks:[]}};workspace.missions[key].picks=Array.isArray(workspace.missions[key].picks)?workspace.missions[key].picks:[];return workspace.missions[key]}}
function submissionFor(id){{return submissions.find(s=>s.entry_id===id||s.script_id===id)}}
function missionDone(id){{return !!submissionFor(id)}}
function recommendationDateSorted(list){{return list.slice().sort((a,b)=>dateKey(b).localeCompare(dateKey(a)))}}
function topicMatchesCurrentPreference(e){{const selected=selectedAnswerValues();const type=String(e.content_type||"");const people=selected.find(v=>["couple","family","friends"].includes(v))||"";const subtype=selected.find(v=>["couple_prank","couple_flirt"].includes(v))||"";if(people==="couple"&&!["夫妻整蛊/冲突","夫妻暧昧"].includes(type))return false;if(people==="family"&&type!=="家庭整蛊")return false;if(people==="friends"&&type!=="朋友整蛊")return false;if(subtype==="couple_prank"&&type!=="夫妻整蛊/冲突")return false;if(subtype==="couple_flirt"&&type!=="夫妻暧昧")return false;return true}}
function durationMatchesCurrentPreference(e){{const durations=selectedAnswerValues().filter(v=>/^dur_/.test(v));return !durations.length||!e.duration_bucket||durations.includes(e.duration_bucket)}}
function hardMatchesCurrentPreference(e){{return topicMatchesCurrentPreference(e)&&durationMatchesCurrentPreference(e)}}
function relaxedMatchesCurrentPreference(e){{const selected=selectedAnswerValues();const type=String(e.content_type||"");if(selected.some(v=>["couple","couple_prank","couple_flirt"].includes(v)))return ["夫妻整蛊/冲突","夫妻暧昧"].includes(type);if(selected.includes("family"))return type==="家庭整蛊";if(selected.includes("friends"))return type==="朋友整蛊";return false}}
function preferenceFirstCandidates(limit=Infinity){{const picked=[];const seen=new Set();const cap=Number.isFinite(limit)?limit:Infinity;const add=list=>recommendationDateSorted(list).forEach(e=>{{if(picked.length<cap&&!seen.has(e.entry_id)){{picked.push(e);seen.add(e.entry_id)}}}});add(entries.filter(hardMatchesCurrentPreference));add(entries.filter(topicMatchesCurrentPreference));add(entries.filter(relaxedMatchesCurrentPreference));add(entries);return picked}}
function missionCandidates(){{return preferenceFirstCandidates()}}
function missionPickedEntries(day){{return missionState(day).picks.map(entry).filter(Boolean)}}
function missionWeekKeys(){{const today=new Date(`${{missionDayKey()}}T00:00:00`);const start=new Date(today);start.setDate(today.getDate()-today.getDay());const keys=[];for(let i=0;i<7;i++){{const d=new Date(start);d.setDate(start.getDate()+i);keys.push(dayKey(d))}}return keys}}
function submissionDayKey(s){{const raw=String(s?.created_at||"");const d=raw?new Date(raw):null;if(d&&!Number.isNaN(d.getTime())){{return `${{d.getFullYear()}}-${{String(d.getMonth()+1).padStart(2,"0")}}-${{String(d.getDate()).padStart(2,"0")}}`}}return missionDayKey()}}
function missionWeeklyDone(){{const week=new Set(missionWeekKeys());const seen=new Set();(submissions||[]).forEach(s=>{{const id=String(s.entry_id||s.script_id||s.video_url||"");if(id&&week.has(submissionDayKey(s)))seen.add(id)}});return seen.size}}
function missionStatusText(id){{if(missionDone(id))return lang==="zh"?"已回传，等待审核/已完成":"Enviado para revisão";if(missionState().picks.includes(id))return lang==="zh"?"已加入今日任务":"Na missão de hoje";return lang==="zh"?"点击加入今日任务":"Toque para escolher"}}
function missionCard(e,selected,mode){{const done=missionDone(e.entry_id);return `<article class="mission-task ${{selected?"selected":""}} ${{done?"done":""}}"><img src="${{esc(scriptImage(e))}}" loading="lazy" alt=""><div><h3>${{esc(ptTitle(e))}}</h3><small>${{esc(missionStatusText(e.entry_id))}}</small><div class="mission-actions"><button class="${{selected?"":"solid"}}" type="button" data-mission-pick="${{esc(e.entry_id)}}">${{selected?(lang==="zh"?"移出":"Remover"):(lang==="zh"?"选择":"Escolher")}}</button><button type="button" data-detail="${{esc(e.entry_id)}}">${{lang==="zh"?"查看":"Ver"}}</button></div></div></article>`}}
function questSummary(e){{return preferPortugueseText(e.summary)||preferPortugueseText(e.title)||""}}
function dailyQuestCard(e,idx){{if(!e)return `<article class="daily-quest"><div class="daily-quest-icon">${{idx+1}}</div><div><h3>${{lang==="zh"?"选择一个今日脚本":"Escolha um roteiro"}}</h3><p>${{lang==="zh"?"从下方今日脚本推荐里加入任务。":"Adicione um roteiro da recomendação de hoje abaixo."}}</p><div class="daily-quest-progress"><i style="width:0%"></i><span>0 / 1</span></div></div></article>`;const done=missionDone(e.entry_id);return `<article class="daily-quest ${{done?"done":""}}"><div class="daily-quest-icon">${{done?"✓":idx+1}}</div><div><h3>${{esc(ptTitle(e))}}</h3><p>${{esc(questSummary(e))}}</p><div class="daily-quest-progress"><i style="width:${{done?100:35}}%"></i><span>${{done?"1 / 1":"0 / 1"}}</span></div><div class="daily-quest-actions"><button class="primary" type="button" data-detail="${{esc(e.entry_id)}}">${{lang==="zh"?"打开脚本":"Abrir roteiro"}}</button><button type="button" data-detail="${{esc(e.entry_id)}}" data-submit-scroll="${{esc(e.entry_id)}}">${{done?(lang==="zh"?"已回传":"Enviado"):(lang==="zh"?"回传视频":"Enviar link")}}</button></div></div></article>`}}
function missionCalendarHtml(){{const today=new Date(`${{missionDayKey()}}T00:00:00`);let html="";for(let i=6;i>=0;i--){{const d=new Date(today);d.setDate(today.getDate()-i);const key=dayKey(d);const picks=missionPickedEntries(key);const done=picks.filter(e=>missionDone(e.entry_id)).length;const cls=done>=3?"done":done>0?"partial":"empty";html+=`<div class="mission-day ${{cls}}"><b>${{d.getDate()}}</b><span>${{done}}/3</span></div>`}}return html}}
function missionLeaderboardHtml(done){{const name=esc(creatorUser?.display_name||creatorUser?.account_id||creatorUser?.phone||"666");return `<div class="leader-row"><span class="leader-rank">1</span><span class="leader-name">${{name}}</span><span class="leader-score">${{done}}/3 hoje</span></div><div class="leader-row"><span class="leader-rank">2</span><span class="leader-name">Koko Creator BR</span><span class="leader-score">2/3 hoje</span></div><div class="leader-row"><span class="leader-rank">3</span><span class="leader-name">Equipe teste</span><span class="leader-score">1/3 hoje</span></div>`}}
function openMissionGuide(){{if(initialScriptId)return;if(forceLocalOnboarding)return;if(workspace.rewardGuideHidden)return;const modal=document.querySelector("#mission-guide");if(!modal)return;const zh=lang==="zh";document.querySelector("#mission-guide-kicker").textContent=zh?"Koko 奖励活动":"Campanha Koko";document.querySelector("#mission-guide-title").innerHTML=zh?'翻拍 <span>Koko</span> 视频，赚取现金奖励':'Regrave vídeos da <span>Koko</span> e ganhe dinheiro';document.querySelector("#mission-guide-copy").innerHTML=zh?'最高 <strong class="mission-highlight">每周 US$56</strong>':'até <strong class="mission-highlight">US$56 por semana</strong>';document.querySelector("#mission-rule-kicker").textContent=zh?"每日挑战规则":"Regras do desafio diário";document.querySelector("#mission-guide-prize").innerHTML=zh?'在 <strong>Koko</strong> 选择脚本、拍摄并回传。发布时添加：<em>#SeRirJáEra</em> <em>#EscolaComédia</em>。':'Escolha roteiros na <strong>Koko</strong>, grave e envie o link dentro da <strong>Koko</strong>. Ao publicar, use também: <em>#SeRirJáEra</em> <em>#EscolaComédia</em>.';document.querySelector("#mission-rule-one-title").textContent=zh?"翻拍即可直接赚取现金":"Regravou, ganhou em dinheiro";document.querySelector("#mission-rule-one-copy").innerHTML=zh?'<b>每天 3 条有效视频 = US$3</b><small>第 4 条起每多 1 条加 <em>+US$1</em>，每日额外最高 <em>US$5</em>。</small>':'<b>3 vídeos válidos por dia = US$3</b><small>A partir do 4º vídeo, cada extra vale <em>+US$1</em>. Bônus diário extra de até <em>US$5</em>.</small>';document.querySelector("#mission-rule-two-title").textContent=zh?"视频播放越高，现金奖励越多":"Quanto mais views, maior o prêmio";document.querySelector("#mission-rule-two-copy").innerHTML=zh?'<div class="reward-views-list"><span><em>3 万播放</em><b>US$1.5</b></span><span><em>10 万播放</em><b>US$3</b></span><span><em>50 万播放</em><b>US$10</b></span><span><em>100 万播放</em><b>US$20</b></span></div><small class="reward-views-note">每条视频按达到的最高档位奖励。</small>':'<div class="reward-views-list"><span><em>30 mil views</em><b>US$1,5</b></span><span><em>100 mil views</em><b>US$3</b></span><span><em>500 mil views</em><b>US$10</b></span><span><em>1 milhão views</em><b>US$20</b></span></div><small class="reward-views-note">Cada vídeo recebe o maior nível alcançado.</small>';document.querySelector("#mission-rule-three-title").textContent=zh?"平台流量支持":"Apoio de tráfego";document.querySelector("#mission-rule-three-copy").innerHTML=zh?'<b>每条有效翻拍都可获得平台流量支持。</b><small>优质内容最高有机会获得<em>百万级曝光</em>。</small>':'<b>Todo vídeo válido pode receber tráfego.</b><small>Bons conteúdos podem chegar a <em>milhões de exposições</em>.</small>';document.querySelector("#mission-read-label").textContent=zh?"我已阅读并理解活动规则。":"Li e entendi as regras da campanha.";document.querySelector("#mission-hide-label").textContent=zh?"不再提示这个活动说明。":"Não mostrar novamente.";document.querySelector("#mission-start").textContent=zh?"确认并开始":"Confirmar e começar";document.querySelector("#mission-read").checked=false;document.querySelector("#mission-hide").checked=false;document.querySelector("#mission-start").disabled=true;modal.classList.add("active")}}
function closeMissionGuide(){{if(document.querySelector("#mission-hide")?.checked){{workspace.rewardGuideHidden=true;saveWorkspace()}}document.querySelector("#mission-guide")?.classList.remove("active");setTimeout(scheduleCreatorOnboarding,240)}}
function openMissionRanking(done){{const modal=document.querySelector("#mission-ranking");if(!modal)return;const zh=lang==="zh";document.querySelector("#mission-ranking-title").textContent=zh?"本周排行榜":"Ranking da semana";document.querySelector("#mission-ranking-copy").textContent=zh?"完成每日任务越多，排名越靠前。":"Quem completa mais missões aparece no topo.";document.querySelector("#mission-ranking-list").innerHTML=missionLeaderboardHtml(done||0);modal.classList.add("active")}}
function closeMissionRanking(){{document.querySelector("#mission-ranking")?.classList.remove("active")}}
let onboardingIndex=0;let onboardingTimer=0;let onboardingActive=false;const forceLocalOnboarding=["localhost","127.0.0.1"].includes(location.hostname);
function onboardingCopySet(){{const zh=lang==="zh";return [
{{id:"reward",selector:".reward-card",title:zh?"先看本周奖励进度":"Veja sua meta da semana",copy:zh?"这里显示本周 15 条任务进度。每通过 3 条审核，就解锁一个奖金节点。":"Aqui aparece a meta de 15 vídeos da semana. A cada 3 vídeos aprovados, um bônus é liberado."}},
{{id:"featured",selector:"#featured-slot .featured-card",title:zh?"先看今天推荐的脚本":"Comece pelo roteiro recomendado",copy:zh?"Koko 会按你的偏好优先推荐今天适合拍的脚本。":"A Koko mostra primeiro roteiros de hoje combinando com suas preferências."}},
{{id:"expand",selector:"#featured-slot .script-expand-cue",title:zh?"展开看脚本细节":"Abra os detalhes do roteiro",copy:zh?"点这个向下箭头，就能在卡片里直接看到完整脚本，不用跳走。":"Toque na seta para ver o roteiro completo dentro do card, sem sair da página."}},
{{id:"choose",selector:"#featured-slot .pick-actions",title:zh?"做出选择":"Escolha se vai gravar",copy:zh?"红色是不想拍，绿色是我要拍。选择绿色后，脚本会进入今天的拍摄计划。":"Vermelho é não gravar; verde é quero gravar. Ao escolher verde, o roteiro entra no plano de hoje."}},
{{id:"plan",selector:"#today-plan",title:zh?"今天要拍的脚本在这里":"Seu plano de gravação fica aqui",copy:zh?"被选中的脚本会列在这里，按卡片逐个打开、拍摄、回传。":"Os roteiros escolhidos aparecem aqui para abrir, gravar e enviar um por um."}},
{{id:"planDetail",selector:"#today-plan .plan-detail-button",title:zh?"拍之前再看一遍":"Revise antes de gravar",copy:zh?"点这里可以再次查看脚本内容，确认剧情、动作和对白。":"Toque aqui para revisar história, ações e falas antes de gravar."}},
{{id:"upload",selector:"#today-plan [data-submit-url]",title:zh?"拍完粘贴视频链接":"Envie o link depois de gravar",copy:zh?"视频发布后，把 Kwai 链接粘贴到这里，再点击确认上传。":"Depois de publicar, cole aqui o link do Kwai e confirme o envio."}},
{{id:"finish",selector:".reward-card",title:zh?"回传后进度会更新":"O progresso atualiza após o envio",copy:zh?"审核通过后，顶部进度条会同步更新。达到 3、6、9、12、15 条会解锁对应奖励。":"Após aprovação, a barra de cima atualiza. Em 3, 6, 9, 12 e 15 vídeos, você libera recompensas."}}
]}}
function shouldShowCreatorOnboarding(){{return !!creatorUser&&!initialScriptId&&hasProfile()&&(forceLocalOnboarding||!workspace.creatorOnboardingDone)}}
function currentFeaturedId(){{return document.querySelector("[data-feature-card]")?.dataset.featureCard||""}}
function ensureOnboardingPlan(){{if(missionPickedEntries().length)return;const id=currentFeaturedId();if(!id)return;addToTodayPlan(id);renderFeaturedAndPlan()}}
function scheduleCreatorOnboarding(){{if(!shouldShowCreatorOnboarding())return;clearTimeout(onboardingTimer);onboardingTimer=setTimeout(()=>{{if(document.querySelector("#mission-guide.active")||document.querySelector("#auth-modal.active")){{scheduleCreatorOnboarding();return}}startCreatorOnboarding()}},720)}}
function startCreatorOnboarding(){{if(onboardingActive||!shouldShowCreatorOnboarding())return;onboardingActive=true;onboardingIndex=0;renderOnboardingStep()}}
function finishCreatorOnboarding(){{onboardingActive=false;document.querySelector("#creator-onboarding")?.classList.remove("active");if(!forceLocalOnboarding){{workspace.creatorOnboardingDone=true;saveWorkspace()}}}}
function positionOnboarding(target){{const overlay=document.querySelector("#creator-onboarding");const spot=document.querySelector("#onboarding-spot");const card=document.querySelector("#onboarding-card");if(!overlay||!spot||!card||!target)return;const r=target.getBoundingClientRect();const pad=8;const viewportPad=10;const visibleLeft=Math.max(viewportPad,r.left-pad);const visibleTop=Math.max(viewportPad,r.top-pad);const visibleRight=Math.min(innerWidth-viewportPad,r.right+pad);const visibleBottom=Math.min(innerHeight-viewportPad,r.bottom+pad);const left=Math.min(visibleLeft,innerWidth-80);const top=Math.min(visibleTop,innerHeight-80);const width=Math.max(72,visibleRight-left);const height=Math.max(56,visibleBottom-top);spot.style.left=`${{left}}px`;spot.style.top=`${{top}}px`;spot.style.width=`${{width}}px`;spot.style.height=`${{height}}px`;spot.style.borderRadius=getComputedStyle(target).borderRadius||"24px";const cardHeight=Math.min(card.offsetHeight||180,240);const canShowBelow=top+height+16+cardHeight<innerHeight-12;const canShowAbove=top-cardHeight-16>12;let cardTop=canShowBelow?top+height+16:canShowAbove?top-cardHeight-16:Math.max(12,Math.min(innerHeight-cardHeight-12,top+Math.min(height+12,80)));card.style.top=`${{cardTop}}px`}}
function settleOnboardingPosition(target,frames=22){{let i=0;const tick=()=>{{if(!onboardingActive)return;positionOnboarding(target);if(++i<frames)requestAnimationFrame(tick)}};requestAnimationFrame(tick)}}
function renderOnboardingStep(){{const steps=onboardingCopySet();if(onboardingIndex>=steps.length){{finishCreatorOnboarding();return}}const stepData=steps[onboardingIndex];if(["plan","planDetail","upload"].includes(stepData.id))ensureOnboardingPlan();const overlay=document.querySelector("#creator-onboarding");if(!overlay)return;overlay.classList.add("active");overlay.setAttribute("aria-hidden","false");document.querySelector("#onboarding-step").textContent=`${{onboardingIndex+1}}/${{steps.length}}`;document.querySelector("#onboarding-title").textContent=stepData.title;document.querySelector("#onboarding-copy").textContent=stepData.copy;document.querySelector("[data-onboarding-back]").disabled=onboardingIndex===0;document.querySelector("[data-onboarding-next]").textContent=onboardingIndex===steps.length-1?(lang==="zh"?"完成":"Concluir"):(lang==="zh"?"下一步":"Próximo");document.querySelector("[data-onboarding-skip]").textContent=lang==="zh"?"跳过":"Pular";document.querySelector("[data-onboarding-back]").textContent=lang==="zh"?"上一步":"Voltar";setTimeout(()=>{{let target=document.querySelector(stepData.selector)||document.querySelector("#dashboard-feed")||document.body;target.scrollIntoView({{behavior:"smooth",block:"center",inline:"nearest"}});document.querySelectorAll(".onboarding-nudge").forEach(x=>x.classList.remove("onboarding-nudge"));target.classList.add("onboarding-nudge");settleOnboardingPosition(target)}},40)}}
function refreshOnboardingPosition(){{if(!onboardingActive)return;const stepData=onboardingCopySet()[onboardingIndex];const target=document.querySelector(stepData?.selector||"")||document.querySelector("#dashboard-feed");if(target)positionOnboarding(target)}}
function todayCandidates(){{return missionCandidates()}}
function currentFeaturedIndex(candidates){{return ((featuredOffset%candidates.length)+candidates.length)%candidates.length}}
function selectionRoundComplete(candidates){{return candidates.length&&featuredOffset>=candidates.length}}
function allScriptsPanel(){{return `<section class="selection-complete"><h2>${{lang==="zh"?"已看完所有可推荐脚本":"Você viu todos os roteiros disponíveis"}}</h2><p>${{lang==="zh"?"可以重新选择偏好，或者打开完整脚本库继续浏览。":"Você pode mudar suas preferências ou abrir a biblioteca completa."}}</p><button class="primary" type="button" data-reselect>${{lang==="zh"?"重新选择偏好":"Mudar preferências"}}</button><button class="secondary" type="button" data-go="all-scripts">${{lang==="zh"?"查看所有脚本":"Todos os roteiros"}}</button></section>`}}
function preferenceStripHtml(){{const summary=chips();const empty=`<span class="chip">${{lang==="zh"?"未选择标签":"Sem preferências"}}</span>`;return `<section class="preference-strip"><div><b>${{lang==="zh"?"你的推荐标签":"Suas preferências"}}</b><div class="preference-strip-chips">${{summary||empty}}</div></div><button type="button" data-reselect>${{lang==="zh"?"重新选择标签":"Mudar preferências"}}</button></section>`}}
function addToTodayPlan(id){{const state=missionState();if(!state.picks.includes(id)){{state.picks.push(id)}}if(!ids("planned").has(id)){{["saved","planned","finished","rejected"].forEach(k=>workspace[k]=(workspace[k]||[]).filter(x=>x!==id));workspace.planned=[...(workspace.planned||[]),id]}}saveWorkspace();return true}}
function rewardBanner(){{const weeklyDone=Math.min(15,missionWeeklyDone());const pct=Math.min(100,Math.round(weeklyDone/15*100));const complete=weeklyDone>=15;const rewards=[3,6,9,12,15];const giftLabel=lang==="zh"?"神秘礼物":"presente";const ticks=Array.from({{length:15}},(_,i)=>`<span class="reward-tick ${{weeklyDone>=i+1?"done":""}}"></span>`).join("");const coins=rewards.map(n=>`<div class="reward-step ${{weeklyDone>=n?"done":""}}" style="left:${{Math.round(n/15*100)}}%"><span class="reward-amount">${{n}} USD</span><span class="reward-coin" aria-hidden="true"></span>${{n===6||n===12?`<span class="reward-gift" title="${{giftLabel}}" aria-label="${{giftLabel}}"></span>`:""}}</div>`).join("");return `<section class="reward-card ${{complete?"complete":""}}"><div class="reward-glow"></div><img class="reward-logo" src="/static/kwai-favicon.svg" alt="Kwai"><div class="reward-copy"><h2>${{complete?(lang==="zh"?"本周任务已完成":"Meta semanal concluída"):(lang==="zh"?"完成翻拍赚取现金奖励":"Ganhe bônus gravando roteiros")}}</h2><p>${{complete?(lang==="zh"?"想解锁下一周任务，可以点击申请联系我们。":"Para liberar a próxima semana, toque para solicitar contato."):(lang==="zh"?"每完成 3 条审核通过的视频，就解锁一个奖金节点，还有神秘礼物。":"A cada 3 vídeos aprovados, você libera bônus em dinheiro e presentes surpresa.")}}</p></div><div class="reward-track"><i style="width:${{pct}}%"></i><div class="reward-ticks">${{ticks}}</div><div class="reward-steps">${{coins}}</div><span class="reward-progress-tail">${{weeklyDone}}/15</span></div>${{complete?`<button class="reward-apply" type="button" data-week-apply>${{lang==="zh"?"申请解锁下一周任务":"Solicitar próxima semana"}}</button>`:""}}</section>`}}
function refreshRewardBanner(){{const old=document.querySelector(".reward-card");if(old)old.outerHTML=rewardBanner()}}
function renderFeaturedAndPlan(){{const key=recommendationKey();if(featuredKey!==key){{featuredKey=key;featuredOffset=0}}const candidates=todayCandidates();const slot=document.querySelector("#featured-slot");const plan=document.querySelector("#today-plan-slot");if(!slot||!plan)return;if(!candidates.length){{slot.innerHTML="";plan.innerHTML=todayPlanHtml();return}}if(selectionRoundComplete(candidates)){{slot.innerHTML=allScriptsPanel();plan.innerHTML=todayPlanHtml();return}}const idx=currentFeaturedIndex(candidates);const item=candidates[idx];slot.innerHTML=featuredCard(item,idx,candidates.length);plan.innerHTML=todayPlanHtml();preloadImagesAround(idx)}}
function inlineScriptShell(e){{return `<section class="inline-script-section" id="inline-script-${{esc(e.entry_id)}}"><h2>${{lang==="zh"?"具体脚本":"Roteiro detalhado"}}</h2><div id="inline-script-slot-${{esc(e.entry_id)}}">${{scriptLoading()}}</div></section>`}}
async function loadInlineScript(e){{const slot=document.querySelector(`#inline-script-slot-${{CSS.escape(e.entry_id)}}`);if(!slot)return;try{{const html=e.script_html||await fetchScriptHtml(e.entry_id);slot.innerHTML=renderScriptSlot(html,e)}}catch(err){{slot.innerHTML=renderScriptSlot("",{{...e,summary:e.summary||err.message}})}}}}
document.addEventListener("click",event=>{{const trigger=event.target.closest("[data-scroll-script]");if(!trigger||!trigger.closest("[data-feature-card]"))return;const item=entry(trigger.dataset.scrollScript);if(item)loadInlineScript(item)}},true)
function planCard(e){{const done=missionDone(e.entry_id);const sub=submissionFor(e.entry_id);return `<article class="plan-card plan-card-compact ${{done?"done":""}}"><div class="plan-card-top"><img src="${{esc(scriptImage(e))}}" loading="lazy" alt=""><h3>${{esc(ptTitle(e))}}</h3></div><button class="plan-detail-button" type="button" data-scroll-script="${{esc(e.entry_id)}}">${{lang==="zh"?"点击查看脚本详情":"Ver detalhes do roteiro"}}</button><div class="plan-submit-row plan-submit-row-compact"><input type="url" data-submit-url="${{esc(e.entry_id)}}" placeholder="${{lang==="zh"?"在这里粘贴拍摄好的视频链接":"Cole aqui o link do vídeo gravado"}}"><button class="primary" type="button" data-submit="${{esc(e.entry_id)}}">${{lang==="zh"?"确认上传":"Confirmar"}}</button></div><div class="plan-status" id="submit-status-${{esc(e.entry_id)}}">${{done?(lang==="zh"?"✅ 脚本已上传，等待审核":"✅ Vídeo enviado, aguardando revisão"):(sub?esc(submissionTime(sub)):"")}}</div></article>`}}
function todayPlanHtml(){{const picks=missionPickedEntries();const done=picks.filter(e=>missionDone(e.entry_id)).length;const total=Math.max(1,picks.length);const pct=picks.length?Math.min(100,Math.round(done/total*100)):0;const progressText=picks.length?`${{done}}/${{picks.length}}`:"0/0";const list=picks.length?picks.map(planCard).join(""):`<section class="plan-empty"><b>${{lang==="zh"?"先选择今天要拍的脚本":"Escolha os roteiros de hoje"}}</b><span>${{lang==="zh"?"从上方推荐卡片里选择脚本，加入后这里会变成你的拍摄计划和回传入口。":"Toque em Adicionar ao plano nos cards acima. Eles aparecem aqui com o campo para enviar o vídeo."}}</span></section>`;return `<section class="today-plan" id="today-plan"><div class="today-plan-head"><h2>${{lang==="zh"?"今日拍摄计划":"Plano de gravação de hoje"}}</h2><div class="plan-progress-row"><span class="today-plan-progress">${{lang==="zh"?"已完成":"Concluído"}}: ${{progressText}}</span><div class="plan-progress-track"><i style="width:${{pct}}%"></i></div></div></div><div class="plan-list">${{list}}</div></section>`}}

async function renderMissions(){{const root=document.querySelector("#mission-feed");if(!root)return;root.innerHTML=`<section class="state card"><h3>Loading...</h3></section>`;try{{await ensure(48);await ensureEntryIds(missionState().picks);await loadSubmissions();const state=missionState();const picks=missionPickedEntries();const done=picks.filter(e=>missionDone(e.entry_id)).length;const selected=picks.length;const weeklyDone=Math.min(15,missionWeeklyDone());const weeklyPct=Math.min(100,Math.round(weeklyDone/15*100));const coins=[3,6,9,12,15].map(n=>`<span class="mission-coin-node ${{weeklyDone>=n?"active":""}}">🪙</span>`).join("");const candidates=missionCandidates();const pickedIds=new Set(state.picks);const available=candidates.map(e=>missionCard(e,pickedIds.has(e.entry_id),"pick")).join("");const quests=[0,1,2].map(i=>dailyQuestCard(picks[i],i)).join("");root.innerHTML=`<section class="mission-view"><section class="mission-duo-head"><div class="mission-duo-tabs"><b class="active">GOALS</b><span>BADGES</span></div><div class="mission-goal-card"><h1>${{lang==="zh"?"本周完成 15 个脚本任务":"Complete 15 roteiros na semana"}}</h1><div class="mission-goal-row"><div><div class="mission-goal-track"><i style="width:${{weeklyPct}}%"></i><div class="mission-coin-line">${{coins}}</div></div><div class="mission-week-count">${{weeklyDone}} / 15</div></div></div><div class="mission-reward-row"><button type="button" data-mission-guide-open>👋 $3</button><button type="button" data-mission-ranking-open>🎁 Ranking</button></div></div></section><section class="mission-section mission-pick-pool"><div class="mission-section-head"><div><h2>${{lang==="zh"?"今日脚本推荐":"Roteiros de hoje"}}</h2></div><span class="mission-chip">${{selected}}/3</span></div><div class="mission-list mission-candidate-grid">${{available}}</div></section><div class="mission-duo-title"><h2>${{lang==="zh"?"Daily Quests 今日需求":"Daily Quests"}}</h2><span>⏱ ${{lang==="zh"?"今日有效":"Hoje"}}</span></div><section class="daily-quest-card">${{quests}}</section><section class="mission-section"><div class="mission-section-head"><div><h2>${{lang==="zh"?"任务日历":"Calendário de missões"}}</h2><p>${{lang==="zh"?"完成 3 条的日期会变成绿色，部分完成是浅橙色。":"Dias completos ficam verdes; parciais ficam laranja."}}</p></div><button class="mission-chip" type="button" data-mission-reset>${{lang==="zh"?"重选今日":"Reiniciar"}}</button></div><div class="mission-calendar">${{missionCalendarHtml()}}</div></section></section>`;setTimeout(openMissionGuide,180);}}catch(e){{root.innerHTML=`<section class="state card"><h3>Erro</h3></section>`}}}}
async function renderDashboard(){{const root=document.querySelector("#dashboard-feed");root.innerHTML=`<section class="state card"><h3>Loading...</h3></section>`;try{{await ensure(48);await ensureEntryIds(missionState().picks);await loadSubmissions();const candidates=todayCandidates();if(!candidates.length){{root.innerHTML=`<section class="mission-integrated"><section class="state card"><h3>${{lang==="zh"?"没有可推荐脚本":"Nenhum roteiro disponível"}}</h3><p class="lead">${{lang==="zh"?"当前脚本库暂时没有可推荐内容，请稍后再试或重新选择标签。":"Não encontramos roteiros disponíveis agora. Tente novamente mais tarde ou ajuste suas preferências."}}</p><button class="primary" type="button" data-reselect>${{lang==="zh"?"重新选择标签":"Mudar preferências"}}</button></section></section>`;return}}root.innerHTML=`<section class="mission-integrated">${{rewardBanner()}}<div id="featured-slot" class="featured-slot"></div><div id="today-plan-slot"></div></section>`;renderFeaturedAndPlan();setTimeout(openMissionGuide,260);setTimeout(scheduleCreatorOnboarding,900)}}catch(e){{root.innerHTML=`<section class="state card"><h3>Erro</h3></section>`}}}}

async function renderAllScripts(){{document.querySelector("#all-title").textContent=lang==="zh"?"全部推荐脚本":"Todos os roteiros";const root=document.querySelector("#all-feed");if(!entries.length)root.innerHTML=`<section class="state card"><h3>Loading...</h3></section>`;try{{await ensure(48);renderAllScriptsFeed()}}catch(e){{root.innerHTML=`<section class="state card"><h3>Erro</h3></section>`}}}}
async function loadSubmissions(){{try{{const r=await fetch(`/api/creator/submissions?_=${{Date.now()}}`);const d=await r.json();submissions=Array.isArray(d.submissions)?d.submissions:[]}}catch(e){{submissions=[]}}return submissions}}
function submissionTime(s){{const raw=String(s.created_at||"");const d=new Date(raw);if(Number.isNaN(d.getTime()))return raw;return lang==="zh"?`回传时间：${{d.toLocaleString("zh-CN",{{hour12:false}})}}`:`Enviado em ${{d.toLocaleString("pt-BR",{{hour12:false}})}}`}}
function submissionCard(s){{const img=esc(s.thumbnail_url||`/api/creator/thumbnail/${{s.entry_id}}.webp`);const title=esc(s.submitted_title||s.script_title||"Video enviado");const url=esc(s.video_url||"#");return `<a class="submission-card" href="${{url}}" target="_blank" rel="noopener"><img class="submission-cover" src="${{img}}" loading="lazy" alt=""><div><h3 class="submission-title">${{title}}</h3><div class="submission-time">${{esc(submissionTime(s))}}</div><div class="submission-url">${{url}}</div></div></a>`}}
function profileDataPanel(){{const returned=submissions.length||0;return `<section class="profile-data-panel"><h2>${{lang==="zh"?"数据统计":"Dados"}}</h2><div class="profile-data-grid"><div class="profile-data-item"><b>${{returned}}</b><span>${{lang==="zh"?"累计回传视频":"Vídeos enviados"}}</span></div></div></section>`}}
function renderSubmissionFeed(){{const root=document.querySelector("#saved-feed");if(!submissions.length){{root.innerHTML=profileDataPanel()+`<section class="state card"><h3>${{lang==="zh"?"这里还没有回传视频":"Nenhum video enviado ainda"}}</h3><p class="lead">${{lang==="zh"?"拍完脚本后，在脚本详情页粘贴视频外链提交。":"Depois de gravar, cole o link do video na pagina do roteiro."}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`;return}}root.innerHTML=profileDataPanel()+`<section class="submission-feed">${{submissions.map(submissionCard).join("")}}</section>`}}
function savedList(k){{return (workspace[k]||[]).map(entry).filter(Boolean)}} function savedTabsHtml(){{return [["finished",t("statusFinished"),submissions.length],["saved",t("statusSaved"),(workspace.saved||[]).length],["schedule",lang==="zh"?"拍摄日历":"Calendario de gravacao",scheduleCount()]].map(([id,txt,count])=>`<button class="${{savedTab===id?"active":""}}" data-tab="${{id}}">${{txt}} ${{count}}</button>`).join("")}} async function renderSaved(){{const feed=document.querySelector("#saved-feed");document.querySelector("#schedule-mini-label").textContent=lang==="zh"?"拍摄日历":"Calendario de gravacao";document.querySelector("#saved-tabs").innerHTML=savedTabsHtml();feed.innerHTML=`<section class="empty"><h3>${{uiCopy("Carregando sua biblioteca...","正在加载个人库...")}}</h3></section>`;try{{await Promise.all([ensure(),loadSubmissions()]);const savedIds=savedTab==="schedule"?Object.values(workspace.schedule||{{}}).flat():workspace.saved||[];await ensureEntryIds(savedIds);updateProfileHeader();document.querySelector("#saved-tabs").innerHTML=savedTabsHtml();if(savedTab==="finished"){{renderSubmissionFeed();return}}if(savedTab==="schedule"){{renderScheduleFeed();return}}renderMasonry("#saved-feed",savedList("saved"))}}catch(err){{feed.innerHTML=`<section class="empty"><h3>${{uiCopy("Nao foi possivel carregar sua biblioteca.","个人库加载失败。")}}</h3><button class="cta secondary" data-tab="saved">${{uiCopy("Tentar novamente","重试")}}</button></section>`;uiMessage(uiCopy("Falha ao carregar sua biblioteca. Tente novamente.","个人库加载失败，请重试。"),"error",5000)}}}}
function renderCurrent(){{const v=document.querySelector(".view.active")?.dataset.view;if(v==="dashboard")renderDashboard();if(v==="all-scripts")renderAllScripts();if(v==="missions")renderMissions();if(v==="saved")renderSaved()}}
async function fetchScript(id){{let e=entry(id);if(e)return e;const r=await fetch(`/api/creator/scripts/${{encodeURIComponent(id)}}?html=0&_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"load failed");e=d.entry;if(!entries.some(x=>x.entry_id===e.entry_id))entries.unshift(e);else entries=entries.map(x=>x.entry_id===e.entry_id?{{...x,...e}}:x);return e}}
async function ensureEntryIds(values){{const missing=[...new Set((values||[]).map(String).filter(Boolean))].filter(id=>!entry(id));if(!missing.length)return;await Promise.allSettled(missing.map(fetchScript))}}
async function fetchScriptHtml(id){{const r=await fetch(`/api/creator/script-html/${{encodeURIComponent(id)}}?_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"html failed");entries=entries.map(x=>x.entry_id===id?{{...x,script_html:d.script_html||""}}:x);return d.script_html||""}}
function shareUrl(id){{return `${{location.origin}}/script/${{id}}`}}
async function copyText(text){{try{{if(navigator.clipboard){{await navigator.clipboard.writeText(text);return true}}}}catch(err){{}}try{{const ta=document.createElement("textarea");ta.value=text;ta.setAttribute("readonly","");ta.style.position="fixed";ta.style.top="0";ta.style.left="-9999px";document.body.appendChild(ta);ta.focus();ta.select();ta.setSelectionRange(0,ta.value.length);const ok=document.execCommand("copy");ta.remove();return ok}}catch(err){{return false}}}}
function showShareLink(id,copied){{const url=shareUrl(id);const box=document.querySelector("#share-output");if(box){{box.classList.add("active");box.innerHTML=`<b>${{copied?(lang==="zh"?"已复制分享链接":"Link copiado"):(lang==="zh"?"分享链接":"Link de compartilhamento")}}</b><a href="${{esc(url)}}" target="_blank" rel="noopener">${{esc(url)}}</a>`;if(!copied){{const link=box.querySelector("a");const range=document.createRange();range.selectNodeContents(link);const sel=window.getSelection();sel.removeAllRanges();sel.addRange(range)}}}}}}
function coverImage(e){{return String(e.preview_image_url||e.cover_url||e.storyboard_image_url||scriptImage(e)||"").trim()}}
function storyboardImage(e){{return String(e.storyboard_image_url||e.storyboard_url||scriptImage(e)||"").trim()}}
function detailCover(e){{const hasVideo=!!String(e.video_url||"").trim();return `<section class="detail-preview-section"><div class="detail-cover detail-video-cover" data-detail-video="${{esc(e.entry_id)}}" data-original-video="${{esc(e.video_url||"")}}"><img src="${{esc(coverImage(e))}}" loading="eager" alt="Prévia do roteiro"><div class="detail-video-shell" data-detail-video-shell></div>${{hasVideo?`<button class="detail-video-play" type="button" data-detail-video-play="${{esc(e.entry_id)}}" aria-label="${{lang==="zh"?"播放预览视频":"Reproduzir vídeo de referência"}}"><span>▶</span></button>`:""}}</div><p class="detail-preview-hint">${{lang==="zh"?"点击看看别的创作者是如何拍摄这个脚本的":"Toque para ver como outros criadores gravaram este roteiro."}}</p></section>`}}
async function fetchVideoPlayback(id){{const r=await fetch(`/api/creator/video-source/${{encodeURIComponent(id)}}?_=${{Date.now()}}`);const d=await r.json();if(!r.ok||d.error_code){{const error=new Error(d.error||"video failed");error.code=d.error_code||"video_failed";throw error}}return d}}
function originalVideoLink(url){{if(!url)return "";const label=lang==="zh"?"打开原视频":"Abrir vídeo original";return `<a href="${{esc(url)}}" target="_blank" rel="noopener noreferrer" style="display:flex;align-items:center;justify-content:center;min-height:42px;margin:0 0 14px;border:1px solid #ff5f0033;border-radius:999px;background:#fff7f0;color:#ff5f00;font-size:13px;font-weight:900;text-decoration:none">${{label}} ↗</a>`}}
function stopDetailVideo(){{document.querySelectorAll("[data-detail-video]").forEach(media=>{{media.classList.remove("playing","loading");media.querySelectorAll("video").forEach(v=>{{try{{v.pause();v.removeAttribute("src");v.load()}}catch(e){{}}}});const shell=media.querySelector("[data-detail-video-shell]");if(shell)shell.innerHTML="";media.querySelector(".detail-video-loading")?.remove();media.querySelector(".detail-video-error")?.remove()}})}}
async function playDetailVideo(id){{const media=document.querySelector(`[data-detail-video="${{CSS.escape(id)}}"]`);if(!media||media.classList.contains("loading")||media.classList.contains("playing"))return;media.classList.add("loading");media.insertAdjacentHTML("beforeend",`<div class="detail-video-loading"><i></i><span>${{lang==="zh"?"视频加载中，请稍候":"Carregando vídeo, aguarde"}}</span></div>`);const shell=media.querySelector("[data-detail-video-shell]");const e=entry(id)||{{}};const finish=()=>{{media.classList.remove("loading");media.querySelector(".detail-video-loading")?.remove()}};try{{const playback=await fetchVideoPlayback(id);if(playback.video_source_url){{shell.innerHTML=`<video src="${{esc(playback.video_source_url)}}" poster="${{esc(coverImage(e))}}" controls playsinline preload="auto" autoplay></video>`;media.classList.add("playing");const video=shell.querySelector("video");let done=false;const ready=()=>{{if(done)return;done=true;finish()}};video?.addEventListener("loadeddata",ready,{{once:true}});video?.addEventListener("canplay",ready,{{once:true}});video?.addEventListener("playing",ready,{{once:true}});setTimeout(ready,5000);try{{await video?.play?.()}}catch(err){{}}return}}if(playback.embed_url){{shell.innerHTML=`<iframe src="${{esc(playback.embed_url)}}" title="video preview" loading="eager" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin" sandbox="allow-scripts allow-same-origin allow-popups allow-presentation allow-forms"></iframe>`;media.classList.add("playing");const iframe=shell.querySelector("iframe");let done=false;const ready=()=>{{if(done)return;done=true;finish()}};iframe?.addEventListener("load",ready,{{once:true}});setTimeout(ready,5500);return}}throw new Error("no playable source")}}catch(err){{finish();const disabled=err?.code==="reference_video_disabled"||e.reference_video_enabled===false;const url=disabled?"":String(media.dataset.originalVideo||e.video_url||"");const message=disabled?(lang==="zh"?"原视频访问失败，请稍后再试":"Falha ao acessar o vídeo original. Tente novamente mais tarde."):(lang==="zh"?"视频暂时无法加载":"Não foi possível carregar o vídeo agora");media.insertAdjacentHTML("beforeend",`<div class="detail-video-error">${{esc(message)}}${{url?` · <a href="${{esc(url)}}" target="_blank" rel="noopener">${{lang==="zh"?"打开视频":"Abrir vídeo"}}</a>`:""}}</div>`)}}}}
function scriptLoading(){{return `<section class="script-loading"><b>${{lang==="zh"?"脚本加载中请耐心等待":"Roteiro carregando, aguarde um momento"}}</b><span>${{lang==="zh"?"正在整理完整脚本内容，加载完成后会自动显示。":"Estamos preparando o roteiro completo. Ele aparecerá automaticamente."}}</span><div class="script-progress" aria-hidden="true"></div></section>`}}
function normalizeLabel(s){{return String(s||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[：:]/g,"").trim()}}
function compactText(s){{return String(s||"").replace(/\s+/g," ").trim()}}
function durationLabel(e){{if(lang==="zh")return e.duration_label_zh||{{dur_1_20:"1-20 秒",dur_20_60:"20 秒-1 分钟",dur_60_120:"1-2 分钟",dur_120_plus:"2 分钟以上"}}[e.duration_bucket]||"";return e.duration_label_pt||{{dur_1_20:"1-20 s",dur_20_60:"20 s-1 min",dur_60_120:"1-2 min",dur_120_plus:"Mais de 2 min"}}[e.duration_bucket]||""}}
function ptTag(value){{const raw=String(value||"").trim();const key=raw.toLowerCase();const map={{"夫妻整蛊/冲突":"Pegadinha/conflito de casal","夫妻暧昧":"Ciúmes/traição de casal","家庭整蛊":"Pegadinha em família","朋友整蛊":"Pegadinha com amigos/colegas","待分类":"Pegadinha com amigos/colegas","热门":"Pegadinha com amigos/colegas","还没想好，给我热门":"Pegadinha com amigos/colegas","夫妻关系":"Pegadinha/conflito de casal","夫妻欺骗":"Pegadinha/conflito de casal","夫妻/情侣":"Pegadinha/conflito de casal","夫妻情感":"Pegadinha/conflito de casal","夫妻吵架":"Pegadinha/conflito de casal","夫妻出轨":"Ciúmes/traição de casal","夫妻好色":"Ciúmes/traição de casal","夫妻黄段子":"Ciúmes/traição de casal","夫妻算计":"Pegadinha/conflito de casal","妻管严":"Pegadinha/conflito de casal","夫妻整蛊":"Pegadinha/conflito de casal","隐瞒反转":"Pegadinha com amigos/colegas","骗局反转":"Pegadinha com amigos/colegas","整蛊恶搞":"Pegadinha com amigos/colegas","整蛊":"Pegadinha com amigos/colegas","赖账/金钱冲突":"Pegadinha com amigos/colegas","赖账":"Pegadinha com amigos/colegas","偷吃/偷懒/耍小聪明":"Pegadinha com amigos/colegas","偷奸耍滑":"Pegadinha com amigos/colegas","骗子":"Pegadinha com amigos/colegas","撬墙角":"Ciúmes/traição de casal","偷吃东西":"Pegadinha com amigos/colegas","Relacionamento de casal":"Pegadinha/conflito de casal","Conflito por dinheiro":"Pegadinha com amigos/colegas","Pegadinha":"Pegadinha com amigos/colegas","Golpe e reviravolta":"Pegadinha com amigos/colegas","Esperteza cotidiana":"Pegadinha com amigos/colegas","Popular":"Pegadinha com amigos/colegas",saved:"Salvo",planned:"Planejado",finished:"Gravado"}};return map[raw]||map[key]||raw.replace(/_/g," ")}}
const storyboardDemoUrl="/static/storyboard_sick_wife_demo.png";
function hasChinese(s){{return /[\u4e00-\u9fff]/.test(String(s||""))}}
function collapseRepeatedText(s){{let text=compactText(s);if(!text)return "";for(let parts=2;parts<=4;parts++){{if(text.length%parts)continue;const size=text.length/parts;const chunk=text.slice(0,size).trim();if(chunk&&Array.from({{length:parts}},(_,i)=>text.slice(i*size,(i+1)*size).trim()).every(x=>x===chunk))return chunk}}const words=text.split(/\s+/);for(let parts=2;parts<=4;parts++){{if(words.length%parts)continue;const size=words.length/parts;const chunk=words.slice(0,size).join(" ");let ok=true;for(let i=1;i<parts;i++){{if(words.slice(i*size,(i+1)*size).join(" ")!==chunk){{ok=false;break}}}}if(ok)return chunk}}return text}}
function uniqueCellValues(cells){{const out=[];const seen=new Set();cells.map(preferPortugueseText).map(collapseRepeatedText).forEach(v=>{{const key=normalizeLabel(v);if(!v||seen.has(key))return;seen.add(key);out.push(v)}});return out}}
function uniqueCards(cards){{const out=[];const seen=new Set();(cards||[]).forEach(c=>{{const title=collapseRepeatedText(preferPortugueseText(c.title||""));const body=collapseRepeatedText(preferPortugueseText(c.body||""));const key=normalizeLabel(`${{title}} ${{body}}`);if(!body||seen.has(key))return;seen.add(key);out.push({{title:title||"Ponto-chave",body}})}});return out.slice(0,6)}}
function preferPortugueseText(s){{let text=compactText(s);if(!text)return "";if(hasChinese(text)&&/[A-Za-zÀ-ÿ]/.test(text))text=text.split(/[\u4e00-\u9fff]/)[0].trim();text=text.replace(/[，。；、：！？][^A-Za-zÀ-ÿ]*$/,"").trim();return collapseRepeatedText(text)}}
function ptTitle(e){{return preferPortugueseText(e.title)||String(e.title||"Roteiro")}}
function sketchSvg(i){{const variants=[`<path d="M18 82 H92 M22 82 Q42 60 62 82 M50 24 q18 4 19 22 q-3 24-20 28 q-17-7-18-28 q2-18 19-22Z"/><path d="M48 75 v34 M30 100 q18-18 38 0 M70 38 h30 v82"/>`,`<path d="M16 88 h96 M54 26 q18 4 18 23 q-2 22-20 26 q-19-6-20-26 q3-18 22-23Z"/><path d="M50 74 q-6 26-2 48 M26 98 q24-14 50 0 M78 34 h28 v92 M36 50 l-18 22"/>`,`<path d="M18 88 h94 M58 30 q17 3 18 23 q-3 22-20 26 q-18-6-19-26 q2-19 21-23Z"/><path d="M54 77 q-10 26-1 48 M28 98 q22-12 49 2 M82 36 h24 v88"/>`,`<path d="M18 28 v100 M18 96 h110 M42 76 l38-28 M43 82 l38-28 M76 43 q18 10 32 28"/><path d="M70 74 q16 10 32 22"/>`,`<path d="M14 92 h114 M50 24 q18 3 20 22 q-2 24-20 28 q-18-6-20-28 q2-18 20-22Z"/><path d="M48 74 q-6 30 0 52 M24 102 q24-16 53 0 M86 52 q10 6 20 20 M92 82 q10 7 25 6"/>`,`<path d="M22 68 h78 M22 102 h80 M50 68 l-14 34 M82 68 l-14 34"/><path d="M86 64 q26 5 30 28 q-8 16-26 12 M94 86 l30-16"/>`,`<path d="M64 24 q18 6 20 24 q-4 24-23 28 q-18-8-17-29 q4-19 20-23Z"/><path d="M60 78 v48 M36 110 q25-14 51 0 M22 34 h28 M24 34 v88"/>`,`<path d="M16 92 h112 M54 24 q18 4 20 23 q-2 23-21 27 q-18-6-19-27 q3-19 20-23Z"/><path d="M52 76 q-4 27 2 50 M28 102 q24-14 52 1 M92 50 q12 7 24 24 M98 84 q11 7 26 5"/>`,`<path d="M68 28 q20 6 21 25 q-4 24-23 28 q-19-7-19-29 q3-20 21-24Z"/><path d="M48 88 q20 18 44 0 M45 102 q26 22 54 0 M44 118 h58"/>`];return `<svg viewBox="0 0 132 132" aria-hidden="true"><rect width="132" height="132" fill="#fbfaf7"/><path d="M0 0h132v132H0z" fill="none" stroke="#222" stroke-width="1.2"/>${{variants[i%variants.length]}}</svg>`}}
function collectReferenceImages(doc,e){{const imgs=[...doc.querySelectorAll("img")].map(img=>img.getAttribute("src")||"").filter(Boolean);if(e.thumbnail_url)imgs.unshift(e.thumbnail_url);return imgs.filter((x,i,a)=>x&&a.indexOf(x)===i).slice(0,4)}}
function portugueseDemoScript(e){{return {{original:"https://www.kwai.com/@Suelen_michelini/video/5209970453127473266",main:"O vídeo começa com a esposa ficando doente; ela parece fraca e sem forças, e, com um ar carinhoso, pede atenção e cuidados ao marido. Embora o marido pareça um pouco resignado, ele cuida dela com carinho, lavando e estendendo suas roupas.",points:["Interação carinhosa entre os cônjuges"],adaptable:["O enredo da doença"],images:e.thumbnail_url?[e.thumbnail_url]:[],segments:[{{time:"00:00-00:05",image:"À porta do quarto; esposa vestida com pijama, com aspecto frágil.",action:"A esposa está encostada na porta, com uma expressão de fraqueza e desânimo.",dialogue:"Legenda: Quando eu fico doente"}},{{time:"00:05-00:10",image:"Quarto; esposa deitada na cama, coberta com o cobertor.",action:"A esposa está deitada na cama, parecendo exausta; o marido a observa.",dialogue:"Esposa: Ai, meu Deus, eu tô horrível. Eu acho que eu não passo."}},{{time:"00:10-00:15",image:"Quarto; esposa deitada na cama, marido ao lado da cama.",action:"A esposa olha para o marido com um tom de voz carinhoso e aponta para as roupas.",dialogue:"Esposa: Lava a roupa pra mim."}},{{time:"00:15-00:20",image:"Lavanderia; marido segurando roupas; máquina de lavar e roupas ao fundo.",action:"O marido segura uma pilha de roupas, com uma expressão um pouco hesitante.",dialogue:""}},{{time:"00:20-00:25",image:"Quarto; esposa deitada na cama, pegando o celular.",action:"A esposa pega o celular e parece estar fazendo algo nele.",dialogue:""}},{{time:"00:25-00:30",image:"Quarto; esposa olhando para o celular, marido ao lado.",action:"Enquanto olha para o celular, a esposa fala com o marido em tom de reclamação.",dialogue:"Esposa: Que você não tá me dando atenção. Eu tô aqui morrendo, você nem tá vendo."}},{{time:"00:30-00:33",image:"Quarto; esposa segurando a chaleira, marido ao lado.",action:"A esposa chama o marido com o sino do celular, e ele se aproxima segurando uma chaleira.",dialogue:""}}]}}}}
function readInsightCards(doc,titlePattern){{const cards=[];const headings=[...doc.querySelectorAll("h2,h3")];const h=headings.find(x=>titlePattern.test(normalizeLabel(x.textContent)));if(!h)return cards;let node=h.nextElementSibling;while(node&&!/^H2$/i.test(node.tagName)){{node.querySelectorAll(".insight").forEach(card=>{{const parts=[...card.children].map(x=>preferPortugueseText(x.textContent)).filter(Boolean);if(parts.length)cards.push({{title:parts[0],body:parts.slice(1).join(" ")}})}});node=node.nextElementSibling}}return uniqueCards(cards)}}
function extractScriptData(raw,e){{const doc=new DOMParser().parseFromString(String(raw||""),"text/html");const data={{original:collapseRepeatedText(preferPortugueseText(e.video_url||"")),main:collapseRepeatedText(preferPortugueseText(e.summary)||""),points:[],adaptable:[],pointCards:readInsightCards(doc,/pontos-chave|pontos principais/),adaptableCards:readInsightCards(doc,/planos de substituicao|partes.*adapt/),segments:[],images:collectReferenceImages(doc,e)}};doc.querySelectorAll("tr").forEach(tr=>{{const cells=[...tr.children].map(td=>preferPortugueseText(td.textContent));if(cells.length<2)return;const key=normalizeLabel(cells[0]);const val=uniqueCellValues(cells.slice(1)).join(" ").trim();if(/video original|original/.test(key))data.original=val||data.original;if(/conteudo principal|resumo geral|resumo do video|contenido principal|内容|整体/.test(key))data.main=val||data.main;if(/pontos principais|points?|ponto principal|看点|爆点|重点/.test(key))data.points.push(val);if(/partes.*adapt|adaptadas|adaptavel|适配|替换/.test(key))data.adaptable.push(val);}});doc.querySelectorAll("table").forEach(table=>{{const rows=[...table.querySelectorAll("tr")].map(tr=>[...tr.children].map(td=>preferPortugueseText(td.textContent))).filter(r=>r.length);const headIndex=rows.findIndex(r=>r.some(c=>/tempo|时间/i.test(c))&&(r.some(c=>/imagem|conteudo visual|visual|画面|image/i.test(c))||r.length>=4));if(headIndex<0)return;const heads=rows[headIndex].map(normalizeLabel);const idx=n=>heads.findIndex(h=>n.some(x=>h.includes(x)));let ti=idx(["tempo","时间"]), im=idx(["imagem","conteudo visual","visual","画面","image"]), ac=idx(["acoes","acao","动作","action"]), di=idx(["dialogos","dialogo","台词","对白","dialogue"]);if(ti<0&&heads.length>=4){{ti=0;im=1;ac=2;di=3}}rows.slice(headIndex+1).forEach(r=>{{if(ti<0||!r[ti])return;data.segments.push({{time:r[ti]||"",image:im>=0?r[im]||"":"",action:ac>=0?r[ac]||"":"",dialogue:di>=0?r[di]||"":""}})}})}});data.points=splitBrief(data.points).filter(x=>x&&x!==data.main);data.adaptable=splitBrief(data.adaptable);return data}}
function splitBrief(list){{const out=[];const seen=new Set();list.flatMap(x=>String(x||"").split(/(?:\\n|；|;|\d+[.、])/).map(preferPortugueseText).map(collapseRepeatedText).filter(Boolean)).forEach(v=>{{const key=normalizeLabel(v);if(!seen.has(key)){{seen.add(key);out.push(v)}}}});return out.slice(0,6)}}
function storyFrameHtml(f,img,i){{return `<div class="story-frame">${{sketchSvg(i)}}<span>${{esc(f.time||`00:${{String(i*5).padStart(2,"0")}}`)}}</span></div>`}}
function timeCellText(t){{const parts=String(t||"").split("-");return parts.map(x=>esc(x)).join("<br>")}}
function storyboardGrid(segs){{return {{cols:3,rows:3}}}}
function readableSentences(text){{const clean=compactText(text);if(!clean)return [];const parts=clean.match(/[^.!?]+(?:[.!?]+|$)/g)||[clean];return parts.map(x=>x.trim()).filter(Boolean)}}
function mainContentCard(value){{const parts=readableSentences(value);return `<div class="brief-card main-content-card"><b>Conteúdo principal</b><div class="content-flow">${{parts.map((part,i)=>`<div class="content-beat"><i>${{i+1}}</i><p>${{esc(part)}}</p></div>`).join("")}}</div></div>`}}
function dialogueHtml(text){{let clean=compactText(text);if(emptyDialogueText(clean))return "";clean=clean.replace(/([.!?\"])(?=(?:Homem|Mulher|Esposa|Marido|Amigo|Amiga|Narrador|Legenda)\s*[A-Z]?\s*:)/gi,"$1\\n");const turns=clean.split(/\\n+/).map(x=>x.trim()).filter(Boolean);return `<div class="script-shot-box dialogue-box"><b>Diálogos</b><div class="dialogue-turns">${{turns.map(turn=>{{const m=turn.match(/^([^:]+):\s*(.*)$/);return m?`<div class="dialogue-turn"><strong>${{esc(m[1])}}</strong><span>${{esc(m[2])}}</span></div>`:`<div class="dialogue-turn"><span>${{esc(turn)}}</span></div>`}}).join("")}}</div></div>`}}
function scriptTableRows(segs,storyboard){{const grid=storyboardGrid(segs);return segs.map((s,i)=>{{const sx=i%grid.cols,sy=Math.floor(i/grid.cols);const frame=storyboard?`<img src="${{esc(storyboard)}}" alt="Storyboard frame ${{i+1}}">`:"";const dialogue=dialogueHtml(s.dialogue);return `<article class="script-shot-card" data-shot-index="${{i}}"><div class="script-shot-visual"><div class="script-shot-image" style="--cols:${{grid.cols}};--rows:${{grid.rows}};--sx:${{sx}};--sy:${{sy}}">${{frame}}<span class="script-shot-time">${{esc(s.time||"")}}</span></div></div><div class="script-shot-info ${{dialogue?"has-dialogue":"no-dialogue"}}"><div class="script-shot-box action-box"><b>Ações</b><p>${{esc(s.action||"")}}</p></div>${{dialogue}}</div></article>`}}).join("")}}
function insightSection(title,cards){{cards=uniqueCards(cards);if(!cards.length)return "";const dots=cards.map((_,i)=>`<i class="${{i===0?"active":""}}" data-insight-dot="${{i}}"></i>`).join("");return `<section class="insight-section insight-carousel-card"><div class="insight-title"><h3>${{esc(title)}}</h3><b data-insight-counter>1 / ${{cards.length}}</b></div><div class="insight-cards" data-insight-carousel>${{cards.map((c,i)=>`<article data-insight-index="${{i}}"><b>${{esc(c.title)}}</b><p>${{esc(c.body)}}</p></article>`).join("")}}</div><div class="insight-carousel-footer"><button type="button" data-insight-nav="prev" aria-label="Item anterior">‹</button><div class="insight-dots">${{dots}}</div><button type="button" data-insight-nav="next" aria-label="Próximo item">›</button></div></section>`}}
function cleanScriptHtml(raw,e){{const d=extractScriptData(raw,e);const fallbackPointCards=d.points.map((x,i)=>({{title:i===0?"Ponto-chave":"Ponto-chave "+(i+1),body:x}}));const fallbackAdaptCards=d.adaptable.map((x,i)=>({{title:i===0?"Plano de substituição":"Plano "+(i+1),body:x}}));const brief=[d.original?`<div class="brief-card source-card"><b>Vídeo original</b><p>${{esc(d.original)}}</p></div>`:"",d.main?mainContentCard(d.main):""].join("");const segs=d.segments.slice(0,9);const storyboard=storyboardImage(e);const dots=segs.map((_,i)=>`<i class="${{i===0?"active":""}}" data-shot-dot="${{i}}"></i>`).join("");return `<article class="script-html"><div class="clean-script"><section class="brief-list">${{brief}}</section>${{insightSection("Pontos-chave",d.pointCards.length?d.pointCards:fallbackPointCards)}}${{insightSection("Planos de substituição",d.adaptableCards.length?d.adaptableCards:fallbackAdaptCards)}}${{segs.length?`<section class="script-table-card"><div class="script-table-title"><span>Tabela do roteiro</span><b data-shot-counter>1 / ${{segs.length}}</b></div><div class="script-shot-list" data-shot-carousel data-shot-total="${{segs.length}}">${{scriptTableRows(segs,storyboard)}}</div><div class="shot-carousel-footer"><button type="button" data-shot-nav="prev" aria-label="Cena anterior">‹</button><div class="shot-dots">${{dots}}</div><button type="button" data-shot-nav="next" aria-label="Próxima cena">›</button></div><p class="shot-swipe-hint">Deslize para ver a próxima cena</p></section>`:""}}</div></article>`}}
function renderScriptSlot(html,e){{return html?cleanScriptHtml(html,e):`<article class="script-html"><div class="clean-script"><div class="brief-card"><b>Conteúdo principal</b><p>${{esc(preferPortugueseText(e.summary)||"")}}</p></div></div></article>`}}
function renderDetail(e){{const s=statusOf(e.entry_id);const liked=ids("saved").has(e.entry_id);document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><div class="detail-content">${{detailCover(e)}}<h2 class="detail-title">${{esc(ptTitle(e))}}</h2><div class="tags"><span class="tag">${{esc(ptTag(e.content_type))}}</span>${{durationLabel(e)?`<span class="tag">${{esc(durationLabel(e))}}</span>`:""}}${{s?`<span class="tag">${{esc(ptTag(s))}}</span>`:""}}</div><div class="share-box" id="share-output"></div><div id="script-html-slot">${{e.script_html?renderScriptSlot(e.script_html,e):scriptLoading()}}</div><section class="submit"><b>${{t("submitTitle")}}</b><p class="lead">${{t("submitHint")}}</p><input type="url" data-submit-url="${{esc(e.entry_id)}}" placeholder="${{t("submitPlaceholder")}}"><button class="primary" data-submit="${{esc(e.entry_id)}}">${{t("submitButton")}}</button><div id="submit-status-${{esc(e.entry_id)}}"></div></section><div class="social-actions"><button class="social-btn" type="button" data-status="${{liked?"":"saved"}}" data-entry="${{esc(e.entry_id)}}" aria-label="${{t("save")}}">♡<span>${{liked?(lang==="zh"?"已收藏":"Salvo"):(lang==="zh"?"收藏":"Salvar")}}</span></button><button class="social-btn" type="button" data-copy-share="${{esc(e.entry_id)}}" aria-label="${{lang==="zh"?"复制分享链接":"Copiar link"}}">↗<span>${{lang==="zh"?"分享":"Compartilhar"}}</span></button></div></div>`}}
function loadDetailHtml(e){{if(e.script_html)return;setTimeout(async()=>{{try{{const html=await fetchScriptHtml(e.entry_id);const slot=document.querySelector("#script-html-slot");if(slot)slot.innerHTML=renderScriptSlot(html,e)}}catch(err){{const slot=document.querySelector("#script-html-slot");if(slot)slot.innerHTML=renderScriptSlot("",{{...e,summary:e.summary||err.message}})}}}},300)}}
async function openDetail(id){{analyticsCurrentScriptId=id||"";const modal=document.querySelector("#modal");modal.classList.add("active");const local=entry(id);if(local){{renderDetail(local);loadDetailHtml(local);return}}document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><section class="state card"><h3>${{lang==="zh"?"正在加载脚本..." :"Carregando roteiro..."}}</h3></section>`;try{{const e=await fetchScript(id);renderDetail(e);loadDetailHtml(e)}}catch(err){{document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><section class="state card"><h3>${{lang==="zh"?"脚本加载失败":"Falha ao carregar"}}</h3><p>${{esc(err.message)}}</p></section>`}}}}
async function submitVideo(id,button){{const input=document.querySelector(`[data-submit-url="${{id}}"]`);const status=document.querySelector(`#submit-status-${{id}}`);const video_url=String(input?.value||"").trim();const duplicateText=uiCopy("Este vídeo já foi enviado.","作品已上传，无需重复上传");if(!creatorUser){{if(status){{status.textContent=uiCopy("Entre com seu telefone primeiro.","请先用手机号登录。");status.className="submit-status error"}}openAuth("login");return}}if(!video_url){{if(status){{status.textContent=t("submitError");status.className="submit-status error"}}uiMessage(t("submitError"),"error");input?.focus();return}}if(button?.disabled)return;setButtonBusy(button,true,uiCopy("Enviando...","提交中..."));if(status){{status.textContent=uiCopy("Enviando vídeo...","正在提交视频...");status.className="submit-status"}}uiMessage(uiCopy("Enviando vídeo para revisão...","正在回传视频..."),"loading",0);try{{const r=await fetch("/api/creator/submissions",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{entry_id:id,video_url,creator_id:creatorUser?.account_id||creatorUser?.phone||"creator"}})}});const d=await r.json().catch(()=>({{}}));if(r.status===409||d.code==="duplicate_submission"){{if(status){{status.textContent=duplicateText;status.className="submit-status error"}}uiMessage(duplicateText,"error",3200);return}}if(!r.ok)throw new Error(d.error||"submit failed");const success=uiCopy("Vídeo enviado, aguardando revisão.","视频已上传，等待审核。");if(status){{status.textContent=`✅ ${{success}}`;status.className="submit-status success"}}uiMessage(success,"success",3200);await loadSubmissions();["saved","planned","finished","rejected"].forEach(k=>workspace[k]=(workspace[k]||[]).filter(x=>x!==id));workspace.finished=[...(workspace.finished||[]),id];saveWorkspace();refreshRewardBanner();renderFeaturedAndPlan();savedTab="finished"}}catch(e){{const message=uiCopy("Não foi possível enviar. Confira o link e tente novamente.","提交失败，请检查链接后重试。");if(status){{status.textContent=message;status.className="submit-status error"}}uiMessage(message,"error",3200)}}finally{{setButtonBusy(button,false)}}}}
function closeDetail(){{trackDuration(true);analyticsCurrentScriptId="";stopDetailVideo();document.querySelectorAll("#modal video").forEach(v=>{{try{{v.pause();v.removeAttribute("src");v.load()}}catch(e){{}}}});document.querySelector("#modal").classList.remove("active");document.querySelector("#detail").innerHTML=""}}
function handleProfileImage(kind,file){{if(!file)return;if(!file.type.startsWith("image/")){{uiMessage(uiCopy("Escolha uma imagem válida.","请选择有效的图片。"),"error");return}}uiMessage(uiCopy("Processando imagem...","正在处理图片..."),"loading",0);const reader=new FileReader();reader.onload=()=>{{profileUi[kind]=String(reader.result||"");saveProfileUi();updateProfileImages();uiMessage(uiCopy("Imagem atualizada.","图片已更新。"),"success")}};reader.onerror=()=>uiMessage(uiCopy("Não foi possível abrir a imagem.","图片读取失败。"),"error");reader.readAsDataURL(file)}}
function ensureDetailEnhancementStyles(){{if(document.querySelector("#detail-enhancement-style"))return;const style=document.createElement("style");style.id="detail-enhancement-style";style.textContent=`.detail-top{{display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:10px!important}}.reference-jump{{border:0;border-radius:999px;min-height:42px;width:min(340px,calc(100vw - 92px));padding:0 16px;background:#ff5f00;color:white;font-size:13px;font-weight:950;box-shadow:0 10px 22px rgba(255,95,0,.30);animation:jumpPulse 1.25s ease-in-out infinite;white-space:normal;line-height:1.12;text-align:center}}@keyframes jumpPulse{{0%,100%{{transform:scale(1);box-shadow:0 10px 22px rgba(255,95,0,.28)}}50%{{transform:scale(1.025);box-shadow:0 14px 30px rgba(255,95,0,.40)}}}}.submit{{scroll-margin-top:76px}}.detail-preview-section{{margin:0 0 14px}}.detail-video-cover{{margin-bottom:0!important;background:#111!important}}.detail-video-cover:after{{pointer-events:none}}.detail-video-shell{{position:absolute;inset:0;z-index:2;display:none;background:#050505}}.detail-video-cover.playing .detail-video-shell{{display:block}}.detail-video-shell video,.detail-video-shell iframe{{width:100%;height:100%;display:block;border:0;background:#050505;object-fit:contain}}.detail-video-play{{position:absolute;inset:0;z-index:4;display:grid;place-items:center;border:0;background:linear-gradient(180deg,#00000004,#00000026);color:#fff}}.detail-video-play span{{width:62px;height:62px;display:grid;place-items:center;border-radius:50%;padding-left:4px;background:#ff5f00;color:#fff;font-size:25px;font-weight:950;box-shadow:0 14px 32px #00000042}}.detail-video-cover.playing .detail-video-play{{display:none}}.detail-video-cover.playing>img{{opacity:0}}.detail-preview-hint{{margin:8px 4px 0;color:#8a8f98;font-size:11px;line-height:1.35;text-align:center;font-weight:700}}.detail-video-loading{{position:absolute;inset:0;z-index:6;display:grid;place-content:center;justify-items:center;gap:10px;background:#00000066;color:#fff;font-size:12px;font-weight:900}}.detail-video-loading i{{width:34px;height:34px;border:4px solid #ffffff66;border-top-color:#ff5f00;border-radius:50%;animation:kokoSpin .82s linear infinite}}.detail-video-error{{position:absolute;z-index:7;left:12px;right:12px;bottom:12px;border-radius:14px;padding:10px 12px;background:#fffffff2;color:#333;font-size:11px;font-weight:800;text-align:center}}.detail-video-error a{{color:#ff5f00}}.script-shot-info.no-dialogue{{grid-template-rows:1fr!important}}`;document.head.appendChild(style)}}
function ensureShotCarouselStyles(){{if(document.querySelector("#shot-carousel-style"))return;const style=document.createElement("style");style.id="shot-carousel-style";style.textContent=`.script-html,.clean-script{{min-width:0!important;max-width:100%!important;overflow:hidden!important}}.script-table-card{{box-sizing:border-box!important;width:100%!important;min-width:0!important;max-width:100%!important;overflow:hidden!important;border-radius:22px!important}}.script-table-title{{box-sizing:border-box!important;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:10px!important;width:100%!important;min-width:0!important;padding:14px 14px 12px!important}}.script-table-title span{{min-width:0!important;font-size:20px!important;font-weight:950!important}}.script-table-title b{{flex:0 0 auto;border-radius:999px;padding:6px 10px;background:#fff0e8;color:#ff5f00;font-size:12px;font-weight:950}}.script-shot-list{{box-sizing:border-box!important;display:flex!important;grid-template-columns:none!important;gap:12px!important;width:100%!important;min-width:0!important;max-width:100%!important;overflow-x:auto!important;overflow-y:hidden!important;scroll-snap-type:x mandatory!important;scroll-padding-left:12px!important;padding:12px 26px 12px 12px!important;background:#fffaf6!important;overscroll-behavior-x:contain!important;-webkit-overflow-scrolling:touch!important;scrollbar-width:none!important}}.script-shot-list::-webkit-scrollbar{{display:none!important}}.script-shot-card{{box-sizing:border-box!important;display:block!important;flex:0 0 calc(100% - 28px)!important;min-width:0!important;max-width:none!important;scroll-snap-align:start!important;scroll-snap-stop:always!important;padding:10px!important;border-radius:20px!important;background:#fff!important;box-shadow:0 12px 26px #552d0a0d!important}}.script-shot-visual{{display:block!important;min-width:0!important}}.script-shot-image{{position:relative!important;width:100%!important;aspect-ratio:1/1!important;border-radius:16px!important;overflow:hidden!important;background:#f6f3ef!important}}.script-shot-time{{position:absolute!important;left:9px!important;bottom:9px!important;z-index:3!important;width:auto!important;max-width:calc(100% - 18px)!important;padding:6px 9px!important;border:1px solid #ffffffb8!important;border-radius:999px!important;background:#ff5f00e8!important;color:#fff!important;font-size:11px!important;line-height:1!important;font-weight:950!important;white-space:nowrap!important;box-shadow:0 7px 16px #2b12062b!important;backdrop-filter:blur(8px)!important}}.script-shot-info{{display:grid!important;grid-template-columns:1fr!important;grid-template-rows:auto!important;gap:9px!important;min-width:0!important;margin-top:10px!important}}.script-shot-info.no-dialogue{{grid-template-rows:auto!important}}.script-shot-box{{box-sizing:border-box!important;min-width:0!important;min-height:0!important;padding:12px 13px!important;border-radius:15px!important;background:#fffaf6!important;overflow:visible!important}}.script-shot-box b{{margin-bottom:6px!important;font-size:13px!important}}.script-shot-box p{{font-size:13.5px!important;line-height:1.55!important;font-weight:720!important;word-break:normal!important;overflow-wrap:break-word!important;hyphens:auto!important}}.dialogue-box{{background:#fff!important;border-style:dashed!important}}.shot-carousel-footer{{box-sizing:border-box!important;display:grid!important;grid-template-columns:34px minmax(0,1fr) 34px!important;align-items:center!important;gap:8px!important;width:100%!important;padding:4px 12px 0!important}}.shot-carousel-footer button{{width:34px!important;height:34px!important;border:1px solid #ff5f0030!important;border-radius:50%!important;background:#fff7f0!important;color:#ff5f00!important;font-size:24px!important;font-weight:900!important;line-height:1!important}}.shot-carousel-footer button:disabled{{opacity:.3!important}}.shot-dots{{display:flex!important;align-items:center!important;justify-content:center!important;gap:5px!important;min-width:0!important}}.shot-dots i{{display:block!important;width:6px!important;height:6px!important;border-radius:50%!important;background:#ffd6bf!important;transition:width .2s ease,background .2s ease!important}}.shot-dots i.active{{width:18px!important;border-radius:999px!important;background:#ff5f00!important}}.shot-swipe-hint{{margin:5px 0 12px!important;color:#9398a0!important;font-size:10px!important;line-height:1.2!important;font-weight:750!important;text-align:center!important}}@media(max-width:380px){{.script-shot-card{{flex-basis:calc(100% - 22px)!important}}.script-shot-list{{padding-right:22px!important;gap:10px!important}}.script-shot-box p{{font-size:13px!important}}}}`;document.head.appendChild(style)}}
function ensureReadableScriptStyles(){{if(document.querySelector("#readable-script-style"))return;const style=document.createElement("style");style.id="readable-script-style";style.textContent=`.source-card p{{font-size:12px!important;color:#7d838c!important;word-break:break-all!important}}.main-content-card{{padding:16px!important}}.main-content-card>b{{font-size:20px!important;margin-bottom:14px!important}}.content-flow{{position:relative;display:grid;gap:0}}.content-beat{{position:relative;display:grid;grid-template-columns:28px minmax(0,1fr);gap:10px;padding:0 0 14px}}.content-beat:last-child{{padding-bottom:0}}.content-beat:not(:last-child):before{{content:"";position:absolute;left:13px;top:25px;bottom:1px;width:2px;background:linear-gradient(#ff5f0066,#ff5f0014)}}.content-beat i{{position:relative;z-index:1;width:28px;height:28px;display:grid;place-items:center;border-radius:50%;background:#ff5f00;color:#fff;font-size:11px;font-style:normal;font-weight:950;box-shadow:0 6px 14px #ff5f0030}}.content-beat p{{padding-top:2px!important;font-size:14px!important;line-height:1.58!important;font-weight:720!important;word-break:normal!important;overflow-wrap:break-word!important}}.insight-carousel-card{{box-sizing:border-box!important;width:100%!important;min-width:0!important;max-width:100%!important;overflow:hidden!important;padding:0!important}}.insight-title{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 14px 10px}}.insight-title h3{{margin:0!important;font-size:20px!important}}.insight-title>b{{flex:0 0 auto;border-radius:999px;padding:6px 10px;background:#fff0e8;color:#ff5f00;font-size:12px;font-weight:950}}.insight-cards{{box-sizing:border-box!important;display:flex!important;gap:10px!important;width:100%!important;min-width:0!important;max-width:100%!important;overflow-x:auto!important;scroll-snap-type:x mandatory!important;scroll-padding-left:12px!important;padding:2px 26px 12px 12px!important;scrollbar-width:none!important;-webkit-overflow-scrolling:touch!important;overscroll-behavior-x:contain!important}}.insight-cards::-webkit-scrollbar{{display:none!important}}.insight-cards article{{box-sizing:border-box!important;display:block!important;flex:0 0 calc(100% - 28px)!important;min-width:0!important;max-width:none!important;scroll-snap-align:start!important;scroll-snap-stop:always!important;padding:15px!important;border-radius:17px!important;background:linear-gradient(145deg,#fff,#fff8f2)!important;box-shadow:0 9px 22px #552d0a0b!important}}.insight-cards article>b{{font-size:16px!important;line-height:1.3!important;color:#ff5f00!important}}.insight-cards article>p{{margin-top:8px!important;font-size:13.5px!important;line-height:1.58!important;color:#343941!important;word-break:normal!important;overflow-wrap:break-word!important}}.insight-carousel-footer{{display:grid;grid-template-columns:32px minmax(0,1fr) 32px;align-items:center;gap:8px;padding:0 12px 12px}}.insight-carousel-footer button{{width:32px;height:32px;border:1px solid #ff5f0030;border-radius:50%;background:#fff7f0;color:#ff5f00;font-size:21px;font-weight:900;line-height:1}}.insight-carousel-footer button:disabled{{opacity:.3}}.insight-dots{{display:flex;align-items:center;justify-content:center;gap:5px;min-width:0}}.insight-dots i{{display:block;width:6px;height:6px;border-radius:50%;background:#ffd6bf;transition:width .2s ease,background .2s ease}}.insight-dots i.active{{width:18px;border-radius:999px;background:#ff5f00}}.dialogue-box{{border-style:solid!important;background:#fff8f2!important}}.dialogue-box>b:before{{content:"“";margin-right:4px;font-size:17px}}.dialogue-turns{{display:grid;gap:8px}}.dialogue-turn{{display:grid;gap:3px;padding:9px 10px;border-radius:12px;background:#fff;border:1px solid #ff5f0018}}.dialogue-turn strong{{color:#ff5f00;font-size:11px;line-height:1.25;font-weight:950}}.dialogue-turn span{{color:#26292e;font-size:13.5px;line-height:1.52;font-weight:720;word-break:normal;overflow-wrap:break-word}}.script-shot-info.has-dialogue .action-box{{background:#fffdf9!important}}@media(max-width:380px){{.content-beat{{grid-template-columns:26px minmax(0,1fr);gap:8px}}.content-beat i{{width:26px;height:26px}}.content-beat:not(:last-child):before{{left:12px}}.insight-cards article{{flex-basis:calc(100% - 22px)!important}}}}`;document.head.appendChild(style)}}
function emptyDialogueText(text){{const normalized=String(text||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/\s+/g," ").trim();return !normalized||["-","—","sem conteudo","sem dialogo","n/a","na","nao ha dialogo","sem fala","sem falas"].includes(normalized)}}
function shotCarouselIndex(carousel){{const cards=[...carousel.querySelectorAll("[data-shot-index]")];if(!cards.length)return 0;const left=carousel.scrollLeft;let best=0,delta=Infinity;cards.forEach((card,i)=>{{const d=Math.abs(card.offsetLeft-carousel.offsetLeft-left);if(d<delta){{delta=d;best=i}}}});return best}}
function updateShotCarousel(carousel){{const table=carousel.closest(".script-table-card");const cards=[...carousel.querySelectorAll("[data-shot-index]")];const index=shotCarouselIndex(carousel);carousel.dataset.activeShot=String(index);const counter=table?.querySelector("[data-shot-counter]");if(counter)counter.textContent=`${{index+1}} / ${{cards.length}}`;table?.querySelectorAll("[data-shot-dot]").forEach((dot,i)=>dot.classList.toggle("active",i===index));const prev=table?.querySelector('[data-shot-nav="prev"]');const next=table?.querySelector('[data-shot-nav="next"]');if(prev)prev.disabled=index<=0;if(next)next.disabled=index>=cards.length-1}}
function setupShotCarousels(){{ensureShotCarouselStyles();document.querySelectorAll("[data-shot-carousel]").forEach(carousel=>{{if(carousel.dataset.carouselReady)return;carousel.dataset.carouselReady="1";let frame=0;carousel.addEventListener("scroll",()=>{{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>updateShotCarousel(carousel))}},{{passive:true}});updateShotCarousel(carousel)}})}}
function insightCarouselIndex(carousel){{const cards=[...carousel.querySelectorAll("[data-insight-index]")];if(!cards.length)return 0;let best=0,delta=Infinity;cards.forEach((card,i)=>{{const d=Math.abs(card.offsetLeft-carousel.offsetLeft-carousel.scrollLeft);if(d<delta){{delta=d;best=i}}}});return best}}
function updateInsightCarousel(carousel){{const section=carousel.closest(".insight-carousel-card");const cards=[...carousel.querySelectorAll("[data-insight-index]")];const index=insightCarouselIndex(carousel);const counter=section?.querySelector("[data-insight-counter]");if(counter)counter.textContent=`${{index+1}} / ${{cards.length}}`;section?.querySelectorAll("[data-insight-dot]").forEach((dot,i)=>dot.classList.toggle("active",i===index));const prev=section?.querySelector('[data-insight-nav="prev"]');const next=section?.querySelector('[data-insight-nav="next"]');if(prev)prev.disabled=index<=0;if(next)next.disabled=index>=cards.length-1}}
function setupInsightCarousels(){{ensureReadableScriptStyles();document.querySelectorAll("[data-insight-carousel]").forEach(carousel=>{{if(carousel.dataset.insightReady)return;carousel.dataset.insightReady="1";let frame=0;carousel.addEventListener("scroll",()=>{{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>updateInsightCarousel(carousel))}},{{passive:true}});updateInsightCarousel(carousel)}})}}
function ensureReferenceJumpButton(){{const top=document.querySelector("#detail .detail-top");if(!top||top.querySelector(".reference-jump"))return;const submit=document.querySelector("#detail .submit");if(!submit)return;const button=document.createElement("button");button.type="button";button.className="reference-jump";button.dataset.submitScroll=analyticsCurrentScriptId||"";button.textContent=lang==="zh"?"拍摄完毕？点击上传拍摄好的视频":"Terminou de gravar? Toque para enviar o vídeo gravado";top.appendChild(button)}}
function pruneEmptyDialogueCards(){{document.querySelectorAll("#detail .script-shot-info").forEach(info=>{{[...info.querySelectorAll(".script-shot-box")].forEach(box=>{{const title=normalizeLabel(box.querySelector("b")?.textContent||"");if(!title.includes("dialogos")&&!title.includes("dialogo"))return;const body=box.querySelector(".dialogue-turns")?.textContent||box.querySelector("p")?.textContent||"";if(emptyDialogueText(body)){{box.remove();info.classList.add("no-dialogue");info.classList.remove("has-dialogue")}}}})}})}}
function refreshDetailEnhancements(){{ensureDetailEnhancementStyles();ensureReadableScriptStyles();ensureReferenceJumpButton();pruneEmptyDialogueCards();setupShotCarousels();setupInsightCarousels()}}
new MutationObserver(()=>setTimeout(refreshDetailEnhancements,0)).observe(document.querySelector("#detail"),{{childList:true,subtree:true}})
document.addEventListener("click",e=>{{const play=e.target.closest("[data-detail-video-play]");if(!play)return;track("detail_video_play",{{script_id:play.dataset.detailVideoPlay||""}});playDetailVideo(play.dataset.detailVideoPlay)}})
document.addEventListener("click",e=>{{if(e.target.closest("[data-all-load-more]"))loadMoreAllScripts()}})
document.addEventListener("click",e=>{{const nav=e.target.closest("[data-shot-nav]");if(!nav)return;const table=nav.closest(".script-table-card");const carousel=table?.querySelector("[data-shot-carousel]");const cards=[...(carousel?.querySelectorAll("[data-shot-index]")||[])];if(!carousel||!cards.length)return;const current=shotCarouselIndex(carousel);const target=Math.max(0,Math.min(cards.length-1,current+(nav.dataset.shotNav==="next"?1:-1)));carousel.scrollTo({{left:cards[target].offsetLeft-carousel.offsetLeft-12,behavior:"smooth"}})}})
document.addEventListener("click",e=>{{const nav=e.target.closest("[data-insight-nav]");if(!nav)return;const section=nav.closest(".insight-carousel-card");const carousel=section?.querySelector("[data-insight-carousel]");const cards=[...(carousel?.querySelectorAll("[data-insight-index]")||[])];if(!carousel||!cards.length)return;const current=insightCarouselIndex(carousel);const target=Math.max(0,Math.min(cards.length-1,current+(nav.dataset.insightNav==="next"?1:-1)));carousel.scrollTo({{left:cards[target].offsetLeft-carousel.offsetLeft-12,behavior:"smooth"}})}})
document.addEventListener("click",async e=>{{const logoutButton=e.target.closest("[data-logout]");if(logoutButton){{logout(logoutButton);return}}if(e.target.closest("[data-feature-restart]")){{featuredOffset=0;renderFeaturedAndPlan();return}}if(e.target.closest("[data-week-apply]")){{alert((lang==="zh"?"请联系 WhatsApp 申请下一周任务：":"Fale no WhatsApp para liberar a próxima semana: ")+"+86 13726250870");return}}const featurePlay=e.target.closest("[data-feature-play]");if(featurePlay){{track("feature_video_play",{{script_id:featurePlay.dataset.featurePlay||""}});playFeaturedVideo(featurePlay.dataset.featurePlay);return}}if(e.target.closest("[data-feature-next]")){{stopFeaturedVideo();track("feature_next");const card=document.querySelector("[data-feature-card]");if(card)card.classList.add("slide-left");setTimeout(()=>{{featuredOffset++;renderFeaturedAndPlan()}},440);return}}const planBtn=e.target.closest("[data-plan-script]");if(planBtn){{const id=planBtn.dataset.planScript;const ok=addToTodayPlan(id);if(!ok)return;uiMessage(uiCopy("Roteiro adicionado ao plano de hoje.","脚本已加入今日计划。"),"success");const featureCard=planBtn.closest("[data-feature-card]");if(featureCard){{track("daily_plan_add",{{script_id:id}});featureCard.classList.add("slide-right");setTimeout(()=>{{featuredOffset++;renderFeaturedAndPlan()}},440)}}else{{renderCurrent()}}return}}const skipBtn=e.target.closest("[data-feature-skip]");if(skipBtn){{const featureCard=skipBtn.closest("[data-feature-card]");if(featureCard){{featureCard.classList.add("slide-left")}}track("daily_script_skip");setTimeout(()=>{{featuredOffset++;renderFeaturedAndPlan()}},440);return}}const scrollScript=e.target.closest("[data-scroll-script]");if(scrollScript){{const card=scrollScript.closest("[data-feature-card]");if(card){{card.classList.toggle("detail-open");if(card.classList.contains("detail-open")){{setTimeout(()=>card.querySelector(".inline-script-section")?.scrollIntoView({{behavior:"smooth",block:"nearest"}}),80)}}}}else{{openDetail(scrollScript.dataset.scrollScript)}}return}}const missionPick=e.target.closest("[data-mission-pick]");if(missionPick){{const id=missionPick.dataset.missionPick;const state=missionState();if(state.picks.includes(id)){{state.picks=state.picks.filter(x=>x!==id)}}else if(state.picks.length<3){{state.picks.push(id)}}else{{uiMessage(uiCopy("Escolha no máximo 3 roteiros por dia.","今天最多选择 3 个脚本。"),"error");return}}saveWorkspace();renderMissions();setTimeout(()=>document.querySelector("#mission-plan")?.scrollIntoView({{behavior:"smooth",block:"start"}}),120);return}}if(e.target.closest("[data-mission-guide-open]")){{sessionStorage.removeItem(`koko_mission_guide_${{missionDayKey()}}`);openMissionGuide();return}}if(e.target.closest("[data-mission-guide-x]")){{closeMissionGuide();return}}if(e.target.closest("[data-mission-guide-close]")){{if(!document.querySelector("#mission-read")?.checked){{uiMessage(uiCopy("Marque que leu a regra primeiro.","请先勾选已读。"),"error");return}}closeMissionGuide();return}}if(e.target.closest("[data-mission-ranking-open]")){{const done=missionPickedEntries().filter(e=>missionDone(e.entry_id)).length;openMissionRanking(done);return}}if(e.target.closest("[data-mission-ranking-close]")){{closeMissionRanking();return}}if(e.target.closest("[data-mission-reset]")){{missionState().picks=[];saveWorkspace();renderMissions();uiMessage(uiCopy("Seleção de hoje redefinida.","今日选择已重置。"),"success");return}}if(e.target.closest("[data-mission-pool-toggle]")){{document.querySelector(".mission-pick-pool")?.classList.remove("collapsed");return}}const upload=e.target.closest("[data-upload-trigger]");if(upload){{document.querySelector(`#profile-${{upload.dataset.uploadTrigger}}-input`)?.click();return}}const jump=e.target.closest("[data-tab-jump]");if(jump){{stopFeaturedVideo();savedTab=jump.dataset.tabJump;show("saved");return}}const authOpen=e.target.closest("[data-auth-open]");if(authOpen){{openAuth(authOpen.dataset.authOpen||"login");return}}if(e.target.closest("[data-auth-close]")){{closeAuth();return}}const authToggle=e.target.closest("[data-auth-toggle]");if(authToggle){{setAuthMode(authMode==="register"?"login":"register");return}}const reselect=e.target.closest("[data-reselect]");if(reselect){{stopFeaturedVideo();show("choose");return}}const stepNav=e.target.closest("[data-step]");if(stepNav){{step=Number(stepNav.dataset.step)||0;renderQuestion();return}}if(e.target.closest("#prev-step")){{goStep(-1);return}}const tab=e.target.closest("[data-tab]");if(tab){{savedTab=tab.dataset.tab;renderSaved();return}}const shootMonth=e.target.closest("[data-shoot-month]");if(shootMonth){{shiftScheduleMonth(Number(shootMonth.dataset.shootMonth)||0);return}}const shootDate=e.target.closest("[data-shoot-date]");if(shootDate){{scheduleViewDate=shootDate.dataset.shootDate;renderScheduleFeed();return}}const d=e.target.closest("[data-detail]");if(d){{stopFeaturedVideo();track("detail_open",{{script_id:d.dataset.detail||""}});openDetail(d.dataset.detail);return}}if(e.target.closest("[data-close]")||e.target.id==="modal"){{closeDetail();return}}const copy=e.target.closest("[data-copy-share]");if(copy){{const id=copy.dataset.copyShare;track("share_click",{{script_id:id}});const ok=await copyText(shareUrl(id));showShareLink(id,ok);const label=copy.querySelector("span");if(label)label.textContent=ok?(lang==="zh"?"已复制":"Copiado"):(lang==="zh"?"复制失败，请手动复制":"Copie manualmente");uiMessage(ok?uiCopy("Link copiado.","链接已复制。"):uiCopy("Copie o link manualmente.","复制失败，请手动复制。"),ok?"success":"error");return}}const scrollSubmit=e.target.closest("[data-submit-scroll]");if(scrollSubmit){{track("submit_click",{{script_id:scrollSubmit.dataset.submitScroll||""}});document.querySelector(`[data-submit-url="${{scrollSubmit.dataset.submitScroll}}"]`)?.scrollIntoView({{behavior:"smooth",block:"center"}});return}}const sub=e.target.closest("[data-submit]");if(sub){{track("submit_click",{{script_id:sub.dataset.submit||""}});submitVideo(sub.dataset.submit,sub);return}}const st=e.target.closest("[data-status]");if(st){{if(st.dataset.status==="saved")track("save_click",{{script_id:st.dataset.entry||""}});const inDetail=!!st.closest("#detail");setStatus(st.dataset.entry,st.dataset.status);uiMessage(st.dataset.status==="saved"?uiCopy("Roteiro salvo.","脚本已收藏。"):st.dataset.status==="planned"?uiCopy("Marcado para gravar.","已标记为准备拍摄。"):uiCopy("Status atualizado.","状态已更新。"),"success");if(inDetail){{const fresh=entry(st.dataset.entry);if(fresh)renderDetail(fresh)}}else{{const label=st.querySelector("span");if(label)label.textContent=t(st.dataset.status==="saved"?"saved":st.dataset.status==="planned"?"plan":"save")}}return}}const go=e.target.closest("[data-go]");if(go){{stopFeaturedVideo();if(go.dataset.go==="all-scripts")track("all_scripts_open");if(go.dataset.go==="saved")track("profile_open");if(go.dataset.savedTab)savedTab=go.dataset.savedTab;show(go.dataset.go);return}}const ans=e.target.closest("[data-answer]");if(ans){{const q=questions.find(item=>item.id===ans.dataset.answer);if(isMultipleQuestion(q)){{const values=answerValues(q.id);answers[q.id]=values.includes(ans.dataset.value)?values.filter(v=>v!==ans.dataset.value):[...values,ans.dataset.value];normalizeAnswers();saveProfile();renderQuestion();}}else{{answers[ans.dataset.answer]=ans.dataset.value;normalizeAnswers();saveProfile();if(!goStep(1))show("dashboard");}}return}}if(e.target.closest("#next-step")){{normalizeAnswers();saveProfile();if(!goStep(1))show("dashboard")}}}});
document.addEventListener("click",e=>{{const dateBtn=e.target.closest("[data-schedule-date]");if(dateBtn){{scheduleSelectedDate=dateBtn.dataset.scheduleDate;renderCalendar();return}}if(e.target.closest("[data-schedule-close]")){{closeScheduleModal();return}}if(e.target.closest("[data-schedule-confirm]")){{if(scheduleDraftId){{saveScheduleItem(scheduleDraftId,scheduleSelectedDate||todayKey());savedTab="schedule";closeScheduleModal();show("saved");uiMessage(uiCopy("Roteiro adicionado ao calendário.","脚本已加入拍摄日历。"),"success")}}return}}}});document.addEventListener("click",e=>{{const st=e.target.closest("[data-status]");if(st&&st.dataset.status==="saved"){{const id=st.dataset.entry;setTimeout(()=>openScheduleModal(id),80)}}}});
document.addEventListener("pointerdown",e=>{{const control=e.target.closest("button,a,.option,.calendar-day");if(control)pulseControl(control)}},true);
document.addEventListener("click",e=>{{const link=e.target.closest('a[target="_blank"]');if(link)uiMessage(uiCopy("Abrindo em uma nova página...","正在打开新页面..."),"loading",900)}},true);
document.querySelector("#mission-read")?.addEventListener("change",e=>{{const btn=document.querySelector("#mission-start");if(btn)btn.disabled=!e.target.checked}});
document.addEventListener("click",e=>{{if(e.target.closest("[data-onboarding-next]")){{if(onboardingIndex===3)ensureOnboardingPlan();onboardingIndex++;renderOnboardingStep();return}}if(e.target.closest("[data-onboarding-back]")){{onboardingIndex=Math.max(0,onboardingIndex-1);renderOnboardingStep();return}}if(e.target.closest("[data-onboarding-skip]")){{finishCreatorOnboarding();return}}}});
window.addEventListener("resize",()=>refreshOnboardingPosition());
window.addEventListener("scroll",()=>{{if(onboardingActive)requestAnimationFrame(refreshOnboardingPosition)}},{{passive:true}});
document.querySelector("#auth-form").addEventListener("submit",handleAuthSubmit);
document.querySelector("#profile-avatar-input")?.addEventListener("change",e=>handleProfileImage("avatar",e.target.files?.[0]));
document.querySelector("#profile-cover-input")?.addEventListener("change",e=>handleProfileImage("cover",e.target.files?.[0]));
async function bootstrap(){{if(creatorUser)await loadAccountState();applyLang();setAuthMode("login");show(forceLanding?"home":initialScriptId?"dashboard":creatorUser&&hasProfile()?"dashboard":"home");track("page_view",{{source:initialScriptId?"share_script":"portal"}});if(initialScriptId){{openDetail(initialScriptId);if(!creatorUser)setTimeout(()=>openAuth("login"),260)}}if(creatorUser)setTimeout(()=>requireKwaiProfile(initialScriptId?"share_script_open":"portal_open"),180)}}bootstrap();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "KokoCreator/1.0"

    def compressed_response(self, raw: bytes) -> tuple[bytes, bool]:
        accepts_gzip = "gzip" in str(self.headers.get("Accept-Encoding") or "").lower()
        if not accepts_gzip or len(raw) < 1024:
            return raw, False
        return gzip.compress(raw, compresslevel=5), True

    def send_json(self, payload: Any, status: int = 200, headers: list[tuple[str, str]] | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode()
        raw, compressed = self.compressed_response(raw)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Accept-Encoding")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def send_html(self, body: str, headers: list[tuple[str, str]] | None = None) -> None:
        raw = body.encode()
        raw, compressed = self.compressed_response(raw)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Vary", "Accept-Encoding")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def send_favicon(self, head_only: bool = False) -> None:
        path = (STATIC_ROOT / "kwai-favicon.svg").resolve()
        if not path.is_file():
            self.send_error(404)
            return
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not head_only:
            self.wfile.write(raw)

    def require_admin(self) -> bool:
        if is_admin_authed(self.headers):
            return True
        self.send_json({"error": "请先登录后台。"}, status=401)
        return False

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode() if length else "{}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/favicon.svg", "/favicon.ico", "/brand/kwai-favicon.svg"}:
            self.send_favicon()
            return
        if parsed.path.startswith("/static/"):
            name = urllib.parse.unquote(parsed.path.removeprefix("/static/"))
            path = (STATIC_ROOT / name).resolve()
            if STATIC_ROOT.resolve() not in path.parents or not path.is_file():
                self.send_error(404)
                return
            raw = path.read_bytes()
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path.startswith("/manual_scripts/"):
            name = urllib.parse.unquote(parsed.path.removeprefix("/manual_scripts/"))
            path = (MANUAL_SCRIPT_ASSET_DIR / name).resolve()
            if MANUAL_SCRIPT_ASSET_DIR.resolve() not in path.parents or not path.is_file():
                self.send_error(404)
                return
            raw = path.read_bytes()
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path in {"/", "/creator-portal"}:
            visitor_id = record_site_open(self.headers, self.path, account=current_account(self.headers), source="document")
            self.send_html(page_html(), headers=[visitor_cookie_header(visitor_id)])
            return
        if parsed.path in {"/creator-survey", "/creator-intake"}:
            self.send_html(survey_html())
            return
        if parsed.path in {"/admin", "/admin/scripts"}:
            self.send_html(admin_html())
            return
        if parsed.path == "/healthz":
            self.send_json({"ok": True})
            return
        if parsed.path == "/api/admin/scripts":
            if not self.require_admin():
                return
            q = urllib.parse.parse_qs(parsed.query)
            try:
                limit = max(1, min(500, int((q.get("limit") or ["500"])[0] or "500")))
            except Exception:
                limit = 500
            try:
                offset = max(0, int((q.get("offset") or ["0"])[0] or "0"))
            except Exception:
                offset = 0
            scope = str((q.get("scope") or ["portal_visible"])[0] or "portal_visible").strip()
            if scope not in {"portal_visible", "hidden", "incomplete", "all"}:
                scope = "portal_visible"
            search = str((q.get("search") or [""])[0] or "").strip().lower()
            all_entries = load_admin_entries("all")
            counts = {
                "portal_visible": 0,
                "hidden": 0,
                "incomplete": 0,
                "all": len(all_entries),
            }
            for entry in all_entries:
                counts[admin_entry_scope(entry)] = counts.get(admin_entry_scope(entry), 0) + 1
            entries = [public_admin_entry(entry) for entry in load_admin_entries(scope)]
            if search:
                entries = [
                    entry for entry in entries
                    if search in " ".join(str(entry.get(key) or "") for key in ["title", "summary", "content_type", "video_url"]).lower()
                ]
            total = len(entries)
            self.send_json({
                "entries": entries[offset:offset + limit],
                "total": total,
                "limit": limit,
                "offset": offset,
                "scope": scope,
                "scope_counts": counts,
            })
            return
        if parsed.path == "/api/admin/creators":
            if not self.require_admin():
                return
            profiles = public_creator_profiles()
            self.send_json({"creators": profiles, "total": len(profiles), "categories": content_type_labels()})
            return
        creator_reco_match = re.fullmatch(r"/api/admin/creators/([0-9a-f]{32})/recommendations", parsed.path)
        if creator_reco_match:
            if not self.require_admin():
                return
            q = urllib.parse.parse_qs(parsed.query)
            try:
                limit = max(1, min(50, int((q.get("limit") or ["5"])[0] or "5")))
            except Exception:
                limit = 5
            try:
                offset = max(0, int((q.get("offset") or ["0"])[0] or "0"))
            except Exception:
                offset = 0
            payload = creator_recommendations_for_profile(creator_reco_match.group(1), limit=limit, offset=offset)
            if payload is None:
                self.send_json({"error": "Creator not found."}, status=404)
                return
            self.send_json(payload)
            return
        creator_match = re.fullmatch(r"/api/admin/creators/([0-9a-f]{32})", parsed.path)
        if creator_match:
            if not self.require_admin():
                return
            profile_id = creator_match.group(1)
            for profile in load_creator_profiles():
                if str(profile.get("profile_id") or "") == profile_id:
                    self.send_json({"creator": public_creator_profile(profile, include_scripts=False, script_preview_limit=0)})
                    return
            self.send_json({"error": "Creator not found."}, status=404)
            return
        if parsed.path == "/api/creator/recommendations":
            q = urllib.parse.parse_qs(parsed.query)
            selected = [str(v) for v in q.get("selected", [])]
            limit = max(1, min(500, int((q.get("limit") or ["500"])[0] or "500")))
            self.send_json(recommendation_payload(selected, limit))
            return
        if parsed.path.startswith("/script/"):
            script_match = re.fullmatch(r"/script/([0-9a-f]{32})", parsed.path)
            script_id = script_match.group(1) if script_match else ""
            visitor_id = record_site_open(self.headers, self.path, account=current_account(self.headers), script_id=script_id, source="script_link")
            self.send_html(page_html(), headers=[visitor_cookie_header(visitor_id)])
            return
        if parsed.path.startswith("/api/creator/scripts/"):
            entry_id = parsed.path.rsplit("/", 1)[-1]
            entry = entry_by_id(entry_id)
            if not entry:
                self.send_json({"error": "Script not found."}, status=404)
                return
            try:
                include_html = (urllib.parse.parse_qs(parsed.query).get("html") or ["1"])[0] != "0"
                self.send_json({"entry": public_script_detail(entry, include_html=include_html)})
            except Exception as exc:
                fallback = public_entry(entry, 100)
                fallback["script_html"] = ""
                self.send_json({"entry": fallback, "html_error": str(exc)})
            return
        if parsed.path.startswith("/api/creator/script-html/"):
            entry_id = parsed.path.rsplit("/", 1)[-1]
            entry = entry_by_id(entry_id)
            if not entry:
                self.send_json({"error": "Script not found."}, status=404)
                return
            try:
                self.send_json({"entry_id": entry_id, "script_html": script_html_for_entry(entry)})
            except Exception as exc:
                self.send_json({"entry_id": entry_id, "script_html": "", "error": str(exc)}, status=500)
            return
        if parsed.path.startswith("/api/creator/video-source/"):
            entry_id = parsed.path.rsplit("/", 1)[-1]
            entry = entry_by_id(entry_id)
            if not entry:
                self.send_json({"error": "Script not found."}, status=404)
                return
            self.send_json({"entry_id": entry_id, **video_playback(entry)})
            return
        if parsed.path == "/api/admin/submissions":
            if not self.require_admin():
                return
            q = urllib.parse.parse_qs(parsed.query)
            try:
                limit = max(1, min(300, int((q.get("limit") or ["80"])[0] or "80")))
            except Exception:
                limit = 80
            try:
                offset = max(0, int((q.get("offset") or ["0"])[0] or "0"))
            except Exception:
                offset = 0
            submissions = read_json_file(SUBMISSIONS_FILE, [])
            if not isinstance(submissions, list):
                submissions = []
            total = len(submissions)
            page = submissions[offset:offset + limit]
            enriched = enrich_submission_records(page)
            unmatched_count = sum(1 for item in enriched if item.get("creator_unmatched"))
            self.send_json({
                "ok": True,
                "submissions": enriched,
                "applications": read_json_file(ACCESS_APPLICATIONS_FILE, []) if isinstance(read_json_file(ACCESS_APPLICATIONS_FILE, []), list) else [],
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
                "unmatched_count": unmatched_count,
            })
            return
        if parsed.path == "/api/admin/analytics":
            if not self.require_admin():
                return
            q = urllib.parse.parse_qs(parsed.query)
            try:
                days = max(1, min(180, int((q.get("days") or ["30"])[0] or "30")))
            except Exception:
                days = 30
            include_inactive = (q.get("include_inactive") or ["0"])[0] == "1"
            self.send_json(creator_analytics_payload(days, include_inactive=include_inactive))
            return
        if parsed.path == "/api/admin/analytics-summary":
            if not self.require_admin():
                return
            q = urllib.parse.parse_qs(parsed.query)
            try:
                days = max(1, min(180, int((q.get("days") or ["180"])[0] or "180")))
            except Exception:
                days = 180
            self.send_json(creator_analytics_summary_payload(days))
            return
        if parsed.path == "/api/admin/intakes":
            if not self.require_admin():
                return
            intakes = read_json_file(INTAKE_FILE, [])
            if not isinstance(intakes, list):
                intakes = []
            self.send_json({"ok": True, "intakes": intakes, "total": len(intakes)})
            return
        if parsed.path == "/api/admin/accounts":
            if not self.require_admin():
                return
            q = urllib.parse.parse_qs(parsed.query)
            compact = (q.get("compact") or ["0"])[0] == "1"
            accounts = public_accounts_compact() if compact else [public_account(item, include_state=True) for item in load_accounts()]
            self.send_json({"ok": True, "accounts": accounts, "total": len(accounts)})
            return
        if parsed.path == "/api/me/state":
            account = current_account(self.headers)
            if not account:
                self.send_json({"error": "Not logged in."}, status=401)
                return
            public = public_account(account, include_state=True)
            self.send_json({
                "ok": True,
                "account": {k: v for k, v in public.items() if k != "state"},
                "state": public.get("state") or {},
                "submissions": public.get("submissions") or [],
            })
            return
        if parsed.path == "/api/creator/submissions":
            account = current_account(self.headers)
            if not account:
                self.send_json({"error": "Login required."}, status=401)
                return
            submissions = read_json_file(SUBMISSIONS_FILE, [])
            if not isinstance(submissions, list):
                submissions = []
            submissions = [
                item for item in submissions
                if isinstance(item, dict) and submission_matches_account(item, account)
            ]
            self.send_json({"submissions": submissions})
            return
        if parsed.path == "/api/creator/sync-status":
            meta = read_json_file(SYNC_META_FILE, {})
            count = len(read_json_file(LIBRARY_FILE, [])) if LIBRARY_FILE.exists() else 0
            self.send_json({"cache_exists": LIBRARY_FILE.exists(), "entries_count": count, **(meta if isinstance(meta, dict) else {})})
            return
        if parsed.path.startswith("/api/creator/thumbnail/"):
            entry_id = parsed.path.rsplit("/", 1)[-1].split(".", 1)[0]
            entry = entry_by_id(entry_id)
            if not entry:
                self.send_error(404)
                return
            source_url = thumbnail_url(entry)
            cached = cached_optimized_thumbnail(entry, source_url) if source_url else None
            if cached is None and source_url:
                warm_thumbnail_async(entry)
                self.send_response(302)
                self.send_header("Location", source_url)
                self.send_header("Cache-Control", "public, max-age=300")
                self.end_headers()
                return
            raw = cached if cached is not None else placeholder_svg(entry)
            content_type = "image/webp" if cached is not None else "image/svg+xml; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "public, max-age=604800, immutable" if cached is not None else "public, max-age=300")
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/admin/login":
            try:
                payload = self.read_body()
            except Exception:
                payload = {}
            password = str(payload.get("password") or "")
            if not secrets.compare_digest(password, ADMIN_PASSWORD):
                self.send_json({"error": "后台密码不正确。"}, status=401)
                return
            raw = json.dumps({"ok": True}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Set-Cookie", f"{ADMIN_COOKIE}={urllib.parse.quote(ADMIN_PASSWORD)}; Path=/; Max-Age=604800; HttpOnly; SameSite=Lax")
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path == "/api/analytics/events":
            try:
                payload = self.read_body()
            except Exception:
                payload = {}
            visitor_id = analytics_visitor_id(self.headers)
            event = append_analytics_event(payload, self.headers, visitor_id=visitor_id)
            self.send_json(
                {"ok": True, "event_id": event.get("event_id")},
                status=201,
                headers=[("Set-Cookie", f"{VISITOR_COOKIE}={urllib.parse.quote(visitor_id)}; Path=/; Max-Age=31536000; SameSite=Lax")],
            )
            return
        if parsed.path == "/api/auth/login":
            try:
                payload = self.read_body()
            except Exception:
                payload = {}
            raw_phone = str(payload.get("phone") or payload.get("account_id") or "").strip()
            password = str(payload.get("password") or payload.get("access_key") or payload.get("login_password") or "").strip()
            account_id = normalize_account_key(raw_phone)
            login_error = "Telefone/ID ou senha incorretos."
            if not account_id or not password:
                self.send_json({"error": login_error}, status=401)
                return
            account = find_account(account_id)
            if not account:
                self.send_json({"error": login_error}, status=401)
                return
            if not valid_creator_login_password(account, account_id, password):
                self.send_json({"error": login_error}, status=401)
                return
            if not account or str(account.get("status") or "active") != "active":
                self.send_json({"error": "Conta desativada"}, status=403)
                return
            account = mark_account_registered(account_id, action="login") or account
            append_analytics_event({"event": "login", "page_type": "auth", "path": parsed.path}, self.headers, account=account)
            record_login_referer_open(self.headers, account)
            public = public_account(account, include_state=True)
            raw = json.dumps({
                "ok": True,
                "account": {k: v for k, v in public.items() if k != "state"},
                "state": public.get("state") or {},
                "submissions": public.get("submissions") or [],
            }, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            canonical_login_id = str(account.get("account_id") or canonical_account_key(account_id))
            self.send_header("Set-Cookie", f"{CREATOR_AUTH_COOKIE}={urllib.parse.quote(make_account_token(canonical_login_id))}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax")
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path == "/api/auth/register":
            try:
                payload = self.read_body()
            except Exception:
                payload = {}
            try:
                application = save_access_application(payload, self.headers)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
                return
            append_analytics_event(
                {
                    "event": "access_application_created",
                    "page_type": "auth",
                    "path": parsed.path,
                    "meta": {"phone": application.get("phone"), "kwai_id": application.get("kwai_id")},
                },
                self.headers,
            )
            self.send_json({"ok": True, "application": application}, status=201)
            return
        if parsed.path == "/api/auth/logout":
            self.send_json({"ok": True}, headers=[("Set-Cookie", f"{CREATOR_AUTH_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")])
            return
        if parsed.path == "/api/me/profile":
            account = current_account(self.headers)
            if not account:
                self.send_json({"error": "Not logged in."}, status=401)
                return
            try:
                public = update_account_profile(str(account.get("account_id") or ""), self.read_body())
                raw = json.dumps({
                    "ok": True,
                    "account": {k: v for k, v in public.items() if k != "state"},
                    "state": public.get("state") or {},
                    "submissions": public.get("submissions") or [],
                }, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Set-Cookie", f"{CREATOR_AUTH_COOKIE}={urllib.parse.quote(make_account_token(str(public.get('account_id') or '')))}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(raw)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/me/state":
            account = current_account(self.headers)
            if not account:
                self.send_json({"error": "Not logged in."}, status=401)
                return
            try:
                public = update_account_state(str(account.get("account_id") or ""), self.read_body())
                self.send_json({"ok": True, "account": {k: v for k, v in public.items() if k != "state"}, "state": public.get("state") or {}})
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/admin/scripts/bulk-delete":
            if not self.require_admin():
                return
            try:
                payload = self.read_body()
                raw_ids = payload.get("entry_ids")
                if not isinstance(raw_ids, list):
                    raise ValueError("entry_ids must be a list.")
                self.send_json({"ok": True, **delete_admin_entries([str(item or "") for item in raw_ids])})
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/admin/scripts/import":
            if not self.require_admin():
                return
            try:
                self.send_json(save_direct_import(self.read_body()), status=201)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/admin/creators":
            if not self.require_admin():
                return
            try:
                self.send_json({"ok": True, "creator": create_or_update_creator_profile(self.read_body())}, status=201)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/admin/creators/import":
            if not self.require_admin():
                return
            try:
                result = import_creator_profiles(self.read_body())
                self.send_json(result, status=201 if result.get("imported") else 400)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/admin/accounts":
            if not self.require_admin():
                return
            try:
                payload = self.read_body()
                account = upsert_account(
                    str(payload.get("account") or payload.get("phone") or payload.get("account_id") or ""),
                    display_name=str(payload.get("display_name") or ""),
                    phone=str(payload.get("phone") or ""),
                    kwai_id=str(payload.get("kwai_id") or ""),
                    uid=str(payload.get("uid") or ""),
                )
                self.send_json({"ok": True, "account": account}, status=201)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/admin/submissions/backfill-creators":
            if not self.require_admin():
                return
            try:
                payload = self.read_body()
                limit = max(1, min(1000, int(payload.get("limit") or 200)))
                self.send_json(backfill_submission_creators(limit), status=200)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/admin/submissions/delete":
            if not self.require_admin():
                return
            try:
                payload = self.read_body()
                submission_ids = payload.get("submission_ids") or payload.get("ids") or []
                if not isinstance(submission_ids, list):
                    raise ValueError("submission_ids must be a list.")
                self.send_json(delete_submissions_by_ids(submission_ids), status=200)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        creator_update_match = re.fullmatch(r"/api/admin/creators/([0-9a-f]{32})", parsed.path)
        if creator_update_match:
            if not self.require_admin():
                return
            try:
                self.send_json({"ok": True, "creator": create_or_update_creator_profile(self.read_body(), creator_update_match.group(1))})
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        admin_update_match = re.fullmatch(r"/api/admin/scripts/([0-9a-f]{32})", parsed.path)
        if admin_update_match:
            if not self.require_admin():
                return
            try:
                self.send_json({"ok": True, "entry": update_admin_entry(admin_update_match.group(1), self.read_body())})
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/creator/intake":
            try:
                self.send_json({"ok": True, "intake": save_intake(self.read_body())}, status=201)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/creator/submissions":
            try:
                payload = self.read_body()
                account = current_account(self.headers)
                if not account:
                    self.send_json({"error": "Login required."}, status=401)
                    return
                payload["creator_id"] = str(account.get("account_id") or "")
                submission = save_submission(payload, account=account)
                append_analytics_event(
                    {"event": "submission_created", "page_type": "script", "script_id": submission.get("entry_id"), "path": parsed.path},
                    self.headers,
                    account=account,
                )
                self.send_json({"ok": True, "submission": submission}, status=201)
            except DuplicateSubmissionError as exc:
                self.send_json({"error": str(exc), "code": "duplicate_submission"}, status=409)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/creator/sync-library":
            self.send_json(sync_library(True))
            return
        if parsed.path == "/api/creator/sync-entry":
            try:
                payload = self.read_body()
                self.send_json(sync_library_entry(str(payload.get("entry_id") or "")))
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        self.send_error(404)

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/creator-portal"} or re.fullmatch(r"/script/[0-9a-f]{32}", parsed.path or ""):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path in {"/favicon.svg", "/favicon.ico", "/brand/kwai-favicon.svg"}:
            self.send_favicon(head_only=True)
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        account_match = re.fullmatch(r"/api/admin/accounts/([^/]+)", parsed.path)
        if account_match:
            if not self.require_admin():
                return
            account_id = urllib.parse.unquote(account_match.group(1))
            if not delete_account(account_id):
                self.send_json({"error": "Account not found."}, status=404)
                return
            self.send_json({"ok": True, "account_id": account_id})
            return
        creator_match = re.fullmatch(r"/api/admin/creators/([0-9a-f]{32})", parsed.path)
        if creator_match:
            if not self.require_admin():
                return
            if not delete_creator_profile(creator_match.group(1)):
                self.send_json({"error": "Creator not found."}, status=404)
                return
            self.send_json({"ok": True, "profile_id": creator_match.group(1)})
            return
        self.send_error(404)


def main() -> int:
    try:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"data_root_init_failed path={DATA_ROOT!s} error={exc}", flush=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(json.dumps({"port": PORT, "data_root": str(DATA_ROOT)}, ensure_ascii=False), flush=True)
    try:
        maybe_sync_library()
    except Exception as exc:
        print(f"startup_sync_schedule_failed error={exc}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
