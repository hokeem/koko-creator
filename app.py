#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
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
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4


PORT = int(os.environ.get("PORT", "10000"))
BASE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("DATA_DIR", str(BASE / "data"))).expanduser()
STATIC_ROOT = BASE / "static"
SEED_LIBRARY_FILE = BASE / "data" / "creator_online_library.json"
SEED_MANUAL_LIBRARY_FILE = BASE / "data" / "manual_creator_scripts.json"
LIBRARY_FILE = DATA_ROOT / "creator_online_library.json"
MANUAL_LIBRARY_FILE = DATA_ROOT / "manual_creator_scripts.json"
SUBMISSIONS_FILE = DATA_ROOT / "creator_submissions.json"
CREATOR_EVENTS_FILE = DATA_ROOT / "creator_events.json"
INTAKE_FILE = DATA_ROOT / "creator_intake_submissions.json"
CREATORS_FILE = DATA_ROOT / "creator_profiles.json"
ACCOUNTS_FILE = DATA_ROOT / "creator_accounts.json"
THUMB_CACHE_FILE = DATA_ROOT / "creator_thumbnail_cache.json"
VIDEO_SOURCE_CACHE_FILE = DATA_ROOT / "creator_video_source_cache.json"
SCRIPT_HTML_CACHE_DIR = DATA_ROOT / "creator_script_html_cache"
MANUAL_SCRIPT_ASSET_DIR = DATA_ROOT / "manual_scripts"
SYNC_META_FILE = DATA_ROOT / "creator_sync_meta.json"
OVERRIDES_FILE = DATA_ROOT / "creator_script_overrides.json"
SOURCE_URL = os.environ.get("CREATOR_LIBRARY_SOURCE_URL", "https://koko-kwai-coach.onrender.com/api/library")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://koko-fpml.onrender.com").rstrip("/")
SYNC_INTERVAL_SEC = int(os.environ.get("CREATOR_LIBRARY_SYNC_INTERVAL_SEC", "86400"))
ADMIN_PASSWORD = os.environ.get("KOKO_CREATOR_ADMIN_PASSWORD", "koko")
ADMIN_COOKIE = "koko_creator_admin"
CREATOR_AUTH_COOKIE = "koko_creator_auth"
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
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(path)


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
        "source": "creator_direct_import",
    }
    imported = normalized_entry(imported)
    upsert_manual_entry(imported)
    invalidate_entry_cache(entry_id)
    return {"ok": True, "entry": public_admin_entry(imported), "share_url": f"/script/{entry_id}"}


def load_entries_raw() -> list[dict[str, Any]]:
    sync_library(False)
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


def load_entries() -> list[dict[str, Any]]:
    overrides = load_overrides()
    entries: list[dict[str, Any]] = []
    for entry in load_entries_raw():
        entry_id = str(entry.get("entry_id") or "").strip()
        override = overrides.get(entry_id)
        if isinstance(override, dict) and override.get("deleted"):
            continue
        if isinstance(override, dict) and override.get("hidden"):
            continue
        entries.append(normalized_entry(apply_entry_override(entry, override)))
    return entries


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
    return sorted(entries, key=lambda item: str(item.get("saved_at") or item.get("created_at") or ""), reverse=True)


def effective_entries() -> list[dict[str, Any]]:
    entries = [
        entry for entry in load_entries()
        if entry_is_effective(entry)
    ]
    return sorted(entries, key=lambda item: str(item.get("saved_at") or item.get("created_at") or ""), reverse=True)


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
    return [entry for entry in entries if entry_matches_hard_selection(entry, selected)]


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
    return {
        "entry_id": entry_id,
        "title": entry.get("title") or "Roteiro",
        "summary": entry_summary(entry),
        "content_type": entry.get("content_type") or DEFAULT_CONTENT_TYPE,
        "video_url": abs_url(entry.get("video_url"), ""),
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
    if not selected:
        return {
            "questions": QUESTIONS,
            "selected": selected,
            "total": len(entries),
            "entries": [public_entry(entry, score_entry(entry, selected, idx)) for idx, entry in enumerate(entries[:limit])],
        }
    candidates = filtered_entries_for_selection(entries, selected)
    scored = sorted(((score_entry(entry, selected, idx), entry) for idx, entry in enumerate(candidates)), key=lambda pair: pair[0], reverse=True)
    if len(selected_durations(selected)) > 1:
        salt = "|".join(sorted(selected))
        scored = sorted(scored, key=lambda pair: hashlib.sha1(f"{salt}:{pair[1].get('entry_id') or pair[1].get('video_url') or pair[0]}".encode("utf-8")).hexdigest())
    return {"questions": QUESTIONS, "selected": selected, "total": len(scored), "entries": [public_entry(entry, score) for score, entry in scored[:limit]]}


def entry_by_id(entry_id: str) -> dict[str, Any] | None:
    for entry in load_entries():
        if str(entry.get("entry_id") or "") == entry_id:
            return entry
    return None


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


def save_submission(payload: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(payload.get("entry_id") or "").strip()
    video_url = str(payload.get("video_url") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        raise ValueError("Invalid script id.")
    if not video_url.startswith(("http://", "https://")):
        raise ValueError("Please submit a public video link.")
    entry = entry_by_id(entry_id)
    if not entry:
        raise ValueError("Script not found.")
    meta = link_metadata(video_url)
    fallback_thumb = f"/api/creator/thumbnail/{entry_id}.webp"
    creator_id = normalize_account_key(str(payload.get("creator_id") or "local_creator"))
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
    matched_creator = match_submission_creator(submission)
    if matched_creator:
        submission.update({
            "creator_profile_id": matched_creator.get("profile_id", ""),
            "creator_profile_name": matched_creator.get("name", ""),
            "creator_profile_kwai_id": matched_creator.get("kwai_id", ""),
        })
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    submissions.insert(0, submission)
    write_json_atomic(SUBMISSIONS_FILE, submissions[:1000])
    return submission




def client_ip_from_headers(headers: Any, client_address: Any = None) -> str:
    for key in ["CF-Connecting-IP", "X-Real-IP", "X-Forwarded-For"]:
        raw = str(headers.get(key) or "").strip()
        if raw:
            return raw.split(",", 1)[0].strip()
    if isinstance(client_address, tuple) and client_address:
        return str(client_address[0] or "")
    return ""


def anonymize_ip(ip: str) -> dict[str, str]:
    text = str(ip or "").strip()
    digest = hmac.new((ADMIN_PASSWORD or "koko").encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()[:16] if text else ""
    masked = ""
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", text):
        parts = text.split(".")
        masked = ".".join(parts[:2] + ["x", "x"])
    elif ":" in text:
        masked = ":".join(text.split(":")[:3] + ["..."])
    return {"ip_hash": digest, "ip_masked": masked}


def clean_event_meta(value: Any, depth: int = 0) -> Any:
    if depth > 2:
        return ""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:30]:
            clean_key = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(key or "")).strip("_")[:80]
            if clean_key:
                out[clean_key] = clean_event_meta(item, depth + 1)
        return out
    if isinstance(value, list):
        return [clean_event_meta(item, depth + 1) for item in value[:40]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value or "").strip()[:500]


def load_creator_events() -> list[dict[str, Any]]:
    events = read_json_file(CREATOR_EVENTS_FILE, [])
    return events if isinstance(events, list) else []


def event_account_from_payload(payload: dict[str, Any], headers: Any) -> dict[str, Any] | None:
    account = current_account(headers)
    if account:
        return account
    raw = str(payload.get("creator_id") or payload.get("account_id") or "").strip()
    return find_account(raw) if raw else None


def save_creator_event(payload: dict[str, Any], headers: Any, client_address: Any = None) -> dict[str, Any]:
    event_name = re.sub(r"[^0-9a-zA-Z_.:-]+", "_", str(payload.get("event") or "").strip())[:80]
    if not event_name:
        raise ValueError("Event name required.")
    meta = clean_event_meta(payload.get("meta") if isinstance(payload.get("meta"), dict) else {})
    account = event_account_from_payload(payload, headers)
    raw_ip = client_ip_from_headers(headers, client_address)
    ip_info = anonymize_ip(raw_ip)
    entry_id = str(payload.get("script_id") or payload.get("entry_id") or meta.get("script_id") or meta.get("entry_id") or "").strip()
    if entry_id and not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        entry_id = ""
    account_id = str((account or {}).get("account_id") or payload.get("creator_id") or "").strip()[:120]
    event = {
        "event_id": uuid4().hex,
        "event": event_name,
        "created_at": now_iso(),
        "creator_id": normalize_account_key(account_id),
        "creator_name": str((account or {}).get("display_name") or "")[:120],
        "script_id": entry_id,
        "path": str(payload.get("path") or "")[:240],
        "referrer": str(payload.get("referrer") or headers.get("Referer") or "")[:500],
        "language": str(payload.get("language") or "")[:16],
        "session_id": str(payload.get("session_id") or "")[:120],
        "visitor_id": str(payload.get("visitor_id") or "")[:120],
        "user_agent": str(headers.get("User-Agent") or "")[:500],
        "ip_hash": ip_info.get("ip_hash") or "",
        "ip_masked": ip_info.get("ip_masked") or "",
        "meta": meta,
    }
    events = load_creator_events()
    events.insert(0, event)
    write_json_atomic(CREATOR_EVENTS_FILE, events[:20000])
    return event


def parse_event_dt(value: Any) -> datetime | None:
    try:
        text = str(value or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def creator_event_day(value: Any, tz: timezone = timezone(timedelta(hours=-3))) -> str:
    dt = parse_event_dt(value) or datetime.now(timezone.utc)
    return dt.astimezone(tz).strftime("%Y-%m-%d")


def creator_script_title(entry_id: str) -> str:
    entry = entry_by_id(entry_id)
    return str((entry or {}).get("title") or entry_id or "")


def build_creator_analytics(days: int = 14) -> dict[str, Any]:
    days = max(1, min(90, int(days or 14)))
    tz = timezone(timedelta(hours=-3))
    now_dt = datetime.now(timezone.utc)
    today = now_dt.astimezone(tz).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    events = load_creator_events()
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    submissions = submissions if isinstance(submissions, list) else []
    accounts = {str(a.get("account_id") or ""): public_account(a) for a in load_accounts()}
    day_map: dict[str, dict[str, Any]] = {}
    creator_map: dict[str, dict[str, Any]] = {}
    script_map: dict[str, dict[str, Any]] = {}
    event_names: dict[str, int] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        dt = parse_event_dt(event.get("created_at"))
        if not dt:
            continue
        if now_dt - dt > timedelta(days=days):
            continue
        day = creator_event_day(event.get("created_at"), tz)
        bucket = day_map.setdefault(day, {"date": day, "events": 0, "creators": set(), "visitors": set(), "scripts": set(), "submissions": 0})
        bucket["events"] += 1
        if event.get("creator_id"):
            bucket["creators"].add(str(event.get("creator_id")))
        if event.get("visitor_id") or event.get("ip_hash"):
            bucket["visitors"].add(str(event.get("visitor_id") or event.get("ip_hash")))
        if event.get("script_id"):
            bucket["scripts"].add(str(event.get("script_id")))
        name = str(event.get("event") or "")
        event_names[name] = event_names.get(name, 0) + 1
        creator_id = str(event.get("creator_id") or event.get("visitor_id") or event.get("ip_hash") or "unknown")
        c = creator_map.setdefault(creator_id, {"creator_id": creator_id, "creator_name": str(event.get("creator_name") or accounts.get(creator_id, {}).get("display_name") or creator_id), "events": 0, "detail_views": 0, "favorites": 0, "calendar_adds": 0, "shares": 0, "submissions": 0, "last_seen": "", "scripts": set()})
        c["events"] += 1
        c["last_seen"] = max(str(c.get("last_seen") or ""), str(event.get("created_at") or ""))
        if event.get("script_id"):
            c["scripts"].add(str(event.get("script_id")))
        if name == "script_detail_view":
            c["detail_views"] += 1
        if name == "favorite_add":
            c["favorites"] += 1
        if name == "calendar_add":
            c["calendar_adds"] += 1
        if name == "share_copy":
            c["shares"] += 1
        script_id = str(event.get("script_id") or "")
        if script_id:
            s = script_map.setdefault(script_id, {"script_id": script_id, "title": creator_script_title(script_id), "events": 0, "impressions": 0, "detail_views": 0, "favorites": 0, "calendar_adds": 0, "shares": 0, "submissions": 0, "creators": set()})
            s["events"] += 1
            if creator_id:
                s["creators"].add(creator_id)
            if name == "script_impression":
                s["impressions"] += 1
            if name == "script_detail_view":
                s["detail_views"] += 1
            if name == "favorite_add":
                s["favorites"] += 1
            if name == "calendar_add":
                s["calendar_adds"] += 1
            if name == "share_copy":
                s["shares"] += 1
    for sub in submissions:
        if not isinstance(sub, dict):
            continue
        day = creator_event_day(sub.get("created_at"), tz)
        if day in day_map:
            day_map[day]["submissions"] += 1
        creator_id = str(sub.get("creator_id") or "")
        if creator_id:
            c = creator_map.setdefault(creator_id, {"creator_id": creator_id, "creator_name": accounts.get(creator_id, {}).get("display_name") or creator_id, "events": 0, "detail_views": 0, "favorites": 0, "calendar_adds": 0, "shares": 0, "submissions": 0, "last_seen": "", "scripts": set()})
            c["submissions"] += 1
        script_id = str(sub.get("entry_id") or "")
        if script_id:
            s = script_map.setdefault(script_id, {"script_id": script_id, "title": creator_script_title(script_id), "events": 0, "impressions": 0, "detail_views": 0, "favorites": 0, "calendar_adds": 0, "shares": 0, "submissions": 0, "creators": set()})
            s["submissions"] += 1
    daily = []
    for i in range(days):
        day = (today - timedelta(days=i)).isoformat()
        raw = day_map.get(day, {"date": day, "events": 0, "creators": set(), "visitors": set(), "scripts": set(), "submissions": 0})
        daily.append({"date": day, "events": raw["events"], "active_creators": len(raw["creators"]), "unique_visitors": len(raw["visitors"]), "scripts": len(raw["scripts"]), "submissions": raw["submissions"]})
    yesterday_row = next((row for row in daily if row["date"] == yesterday), {"events": 0, "active_creators": 0, "unique_visitors": 0, "scripts": 0, "submissions": 0})
    def clean_sets(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for key in ["scripts", "creators"]:
            if isinstance(out.get(key), set):
                out[key] = len(out[key])
        return out
    creators = sorted((clean_sets(v) for v in creator_map.values()), key=lambda x: (x.get("submissions", 0), x.get("detail_views", 0), x.get("events", 0)), reverse=True)[:80]
    scripts = sorted((clean_sets(v) for v in script_map.values()), key=lambda x: (x.get("submissions", 0), x.get("detail_views", 0), x.get("favorites", 0)), reverse=True)[:80]
    recent = events[:80]
    return {
        "ok": True,
        "generated_at": now_iso(),
        "timezone": "America/Sao_Paulo",
        "summary": {
            "yesterday_active_creators": yesterday_row.get("active_creators", 0),
            "yesterday_unique_visitors": yesterday_row.get("unique_visitors", 0),
            "yesterday_events": yesterday_row.get("events", 0),
            "yesterday_submissions": yesterday_row.get("submissions", 0),
            "total_events": len(events),
            "total_submissions": len(submissions),
        },
        "daily": daily,
        "event_counts": sorted(({"event": k, "count": v} for k, v in event_names.items()), key=lambda x: x["count"], reverse=True),
        "creators": creators,
        "scripts": scripts,
        "recent_events": recent,
    }

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


def account_aliases(account: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for key in ["account_id", "phone", "kwai_id", "uid"]:
        raw = str(account.get(key) or "").strip()
        for value in [raw, normalize_phone(raw), normalize_kwai_id(raw)]:
            clean = normalize_account_key(value)
            if clean:
                aliases.add(clean)
    for raw in account.get("login_aliases") or []:
        for value in [str(raw or ""), normalize_phone(str(raw or "")), normalize_kwai_id(str(raw or ""))]:
            clean = normalize_account_key(value)
            if clean:
                aliases.add(clean)
    return aliases


def submission_kwai_id(submission: dict[str, Any]) -> str:
    return normalize_kwai_id(submission.get("detected_kwai_id") or kwai_handle_from_url(str(submission.get("video_url") or "")))


def match_submission_creator(submission: dict[str, Any], profiles: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    profiles = profiles if profiles is not None else load_creator_profiles()
    submission_creator = normalize_account_key(submission.get("creator_id") or "")
    submission_kwai = submission_kwai_id(submission)
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        account = find_account(str(profile.get("account_id") or profile.get("phone") or profile.get("kwai_id") or profile.get("uid") or ""))
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
        if (submission_creator and submission_creator in creator_keys) or (submission_kwai and creator_kwai and submission_kwai == creator_kwai):
            return {
                "profile_id": str(profile.get("profile_id") or ""),
                "name": str(profile.get("name") or profile.get("kwai_id") or "Kwai creator"),
                "kwai_id": str(profile.get("kwai_id") or ""),
            }
    return None


def enrich_submission_records(submissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = load_creator_profiles()
    enriched: list[dict[str, Any]] = []
    for item in submissions:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        matched = match_submission_creator(row, profiles)
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
    secret = (ADMIN_PASSWORD or "koko").encode("utf-8")
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
    seen = {str(item.get("account_id") or "") for item in accounts if isinstance(item, dict)}
    changed = False
    for key in DEFAULT_ALLOWED_ACCOUNTS:
        account_id = normalize_account_key(key)
        if account_id and account_id not in seen:
            accounts.append({
                "account_id": account_id,
                "phone": account_id,
                "display_name": account_id,
                "status": "active",
                "created_at": now_iso(),
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
        if isinstance(item, dict) and str(item.get("creator_id") or "") == account_id
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
        "created_at": str(account.get("created_at") or ""),
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


def find_account(account_id: str) -> dict[str, Any] | None:
    target = normalize_account_key(account_id)
    phone_target = normalize_phone(account_id)
    kwai_target = normalize_kwai_id(account_id)
    for account in load_accounts():
        aliases = account_aliases(account)
        if target in aliases or (phone_target and phone_target in aliases) or (kwai_target and kwai_target in aliases):
            return account
    return None


def upsert_account(
    account_id: str,
    *,
    source: str = "admin",
    display_name: str = "",
    phone: str = "",
    kwai_id: str = "",
    uid: str = "",
) -> dict[str, Any]:
    clean = normalize_account_key(account_id or phone or kwai_id or uid)
    if not clean:
        raise ValueError("账号只能包含数字、字母、下划线、@、点或短横线。")
    phone_clean = normalize_phone(phone or account_id)
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


def update_account_state(account_id: str, state_patch: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_account_key(account_id)
    accounts = load_accounts()
    for idx, account in enumerate(accounts):
        if str(account.get("account_id") or "") == clean:
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


def public_admin_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entry = normalized_entry(entry)
    entry_id = str(entry.get("entry_id") or "").strip()
    duration_bucket = duration_bucket_for_entry(entry)
    duration_seconds = entry_duration_seconds(entry)
    return {
        "entry_id": entry_id,
        "title": str(entry.get("title") or ""),
        "summary": entry_summary(entry),
        "content_type": str(entry.get("content_type") or DEFAULT_CONTENT_TYPE),
        "video_url": abs_url(entry.get("video_url"), ""),
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
    return [item for item in data if isinstance(item, dict)]


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
) -> dict[str, Any]:
    categories = [str(item or "").strip() for item in profile.get("categories") or [] if str(item or "").strip()]
    script_limit = 80 if script_preview_limit is None else max(0, script_preview_limit)
    creator_type = profile.get("creator_type") if isinstance(profile.get("creator_type"), dict) else {}
    script_total, scripts = ranked_scripts_for_creator(categories, script_limit, entries=entries, creator_type=creator_type) if include_scripts else (0, [])
    submissions = submissions if submissions is not None else read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    account = find_account(str(profile.get("account_id") or profile.get("phone") or profile.get("kwai_id") or profile.get("uid") or ""))
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
    profiles = [
        public_creator_profile(item, include_scripts=False, submissions=submissions, script_preview_limit=0)
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
function esc(s){{return String(s??"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;","\\\"":"&quot;","'":"&#39;"}}[c]))}}
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


def page_html() -> str:
    questions_json = json.dumps(QUESTIONS, ensure_ascii=False)
    profile_override_css = """.profile-hero{min-height:0;margin:-22px -22px 14px;padding:12px 14px 16px;background:linear-gradient(135deg,#32180b,#ff5f00 64%,#ffb36f);overflow:visible}.profile-cover{inset:0;height:132px;border-radius:0;background:radial-gradient(circle at 72% 16%,#ff8a1c,#8a3205 50%,#2a160d);filter:none}.profile-cover:after{background:linear-gradient(180deg,#00000018,#00000042)}.profile-tools{position:relative;top:auto;right:auto;justify-content:flex-end;margin-bottom:44px}.profile-upload{min-height:30px;padding:0 11px;border-color:#ffffff70;background:#ffffff24;font-size:11px;white-space:nowrap}.profile-info{position:relative;margin-top:-12px;padding:14px;border-radius:24px;background:#fffffff2;color:#1f1f1f;box-shadow:0 18px 38px #552d0a24}.profile-row{align-items:center;gap:12px}.profile-avatar{width:78px;height:78px;flex:0 0 78px;border:4px solid #fff;box-shadow:0 10px 24px #552d0a22}.profile-name{margin:0 0 6px;color:#1f1f1f;font-size:25px;text-shadow:none}.profile-bio{color:#69707a;font-size:13px;line-height:1.42}.profile-stats{margin-top:14px;padding:11px 8px;border-radius:18px;background:#fff7f0;border:1px solid #ff5f0018;text-align:center}.profile-stats b{color:#1f1f1f;font-size:19px}.profile-stats span{color:#69707a;font-size:12px;font-weight:800}.profile-prefs{margin-top:12px;gap:7px}.profile-prefs .chip{padding:7px 10px;background:#fff;color:#ff5f00;border-color:#ff5f0045;box-shadow:none;font-size:11px}.profile-card-strip{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0 12px}.profile-mini{min-height:58px;border-radius:18px;background:#fff;border:1px solid #ff5f0016;box-shadow:0 8px 18px #552d0a10;font-size:11px}.profile-mini b{font-size:17px;margin-bottom:2px}.profile-tabs{top:64px;margin:0 -22px 10px;padding:8px 18px}.profile-tabs .tabs button{padding:8px 12px;font-size:12px}#saved-feed .state{margin:0;border-radius:24px;padding:26px 20px}@media(max-width:380px){.profile-upload{padding:0 8px;font-size:10px}.profile-avatar{width:68px;height:68px;flex-basis:68px}.profile-name{font-size:22px}.profile-info{padding:12px}.profile-tabs .tabs button{padding:8px 10px}}"""
    profile_override_css += """.profile-hero{min-height:0!important;margin:-22px -22px 14px!important;padding:12px 14px 16px!important;overflow:visible!important}.profile-tools{position:relative!important;top:auto!important;right:auto!important;margin-bottom:44px!important}.profile-logout{border-color:#ff5f0038!important;background:#fff!important;color:#ff5f00!important}.profile-info{position:relative!important;margin-top:-12px!important;padding:14px!important;border-radius:24px!important;background:#fffffff2!important;color:#1f1f1f!important}.profile-row{align-items:center!important}.profile-avatar{width:78px!important;height:78px!important;flex:0 0 78px!important}.profile-name{color:#1f1f1f!important;font-size:25px!important;text-shadow:none!important}.profile-bio{color:#69707a!important;font-size:13px!important;line-height:1.42!important}.profile-stats{grid-template-columns:repeat(2,1fr)!important;margin-top:14px!important;padding:11px 8px!important;border-radius:18px!important;background:#fff7f0!important;text-align:center!important}.profile-stats b{color:#1f1f1f!important}.profile-stats span{color:#69707a!important}.profile-prefs .chip{background:#fff!important;color:#ff5f00!important;border-color:#ff5f0045!important}.profile-card-strip{grid-template-columns:repeat(3,minmax(0,1fr))!important}.profile-mini{min-height:58px!important}.profile-tabs{padding:8px 18px!important}.submission-feed{display:grid;gap:12px}.submission-card{display:grid;grid-template-columns:112px 1fr;gap:12px;align-items:center;padding:10px;border:1px solid #ff5f0022;border-radius:18px;background:#fff;box-shadow:0 10px 22px #552d0a10;color:#1f1f1f;text-decoration:none}.submission-cover{width:112px;aspect-ratio:9/16;border-radius:14px;object-fit:cover;background:#2a1d16}.submission-title{margin:0;font-size:15px;line-height:1.35;font-weight:900}.submission-time{margin-top:8px;color:#69707a;font-size:12px;font-weight:800}.submission-url{margin-top:7px;color:#ff5f00;font-size:11px;line-height:1.35;word-break:break-all}"""
    profile_override_css += """.featured-shell{display:grid;gap:14px}.featured-card{overflow:hidden;border-radius:30px;background:#fff;border:1px solid #ff5f0026;box-shadow:0 22px 48px #552d0a18}.featured-media{position:relative;min-height:350px;background:#2a1d16;overflow:hidden}.featured-media img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.featured-media:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000018,#00000000 48%,#0000003f)}.featured-badge{position:absolute;left:14px;top:14px;z-index:1;border-radius:999px;padding:8px 12px;background:#fffffff0;color:#ff5f00;font-size:12px;font-weight:950;box-shadow:0 8px 22px #00000022}.featured-score{position:absolute;right:14px;top:14px;z-index:1;border-radius:999px;padding:8px 10px;background:#ff5f00;color:white;font-size:12px;font-weight:950}.featured-body{padding:16px 14px 16px}.featured-title{margin:0 0 10px;font-size:23px;line-height:1.2;font-weight:950;letter-spacing:0}.featured-summary{margin:0 0 13px;color:#69707a;font-size:14px;line-height:1.55;font-weight:750}.featured-tags{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px}.featured-actions{display:grid;grid-template-columns:1fr;gap:10px}.featured-actions .primary,.featured-actions .secondary,.featured-actions .featured-icon{width:100%;min-height:50px}.featured-icon{border:1px solid #ff5f0028;border-radius:999px;background:#fff7f0;color:#ff5f00;font-size:15px;font-weight:950}.featured-next{width:100%;min-height:46px;margin-top:10px;border:0;border-radius:999px;background:#fff7f0;color:#69707a;font-size:13px;font-weight:900}.view-all-card{width:100%;margin-top:14px;padding:15px 16px;border:1px solid #ff5f0028;border-radius:22px;background:#ffffffd8;color:#1f1f1f;text-align:left;box-shadow:0 12px 30px #552d0a10}.view-all-card b{display:block;margin-bottom:4px;color:#ff5f00;font-size:15px}.view-all-card span{color:#69707a;font-size:13px;font-weight:750}.all-title-row{display:flex;align-items:center;gap:10px;margin-bottom:12px}.all-title-row h1{margin:0;font-size:30px;line-height:1.1;flex:1}.back-pill{border:1px solid #ff5f0038;border-radius:999px;min-height:38px;padding:0 12px;background:#fff7f0;color:#ff5f00;font-size:12px;font-weight:900}@media(max-width:380px){.featured-media{min-height:312px}.featured-title{font-size:21px}}"""
    profile_override_css += """.schedule-overlay{position:fixed;inset:0;z-index:90;display:none;align-items:flex-end;background:#1f1f1f66;padding:16px 12px 0}.schedule-overlay.active{display:flex}.schedule-sheet{width:min(100%,480px);max-height:88vh;margin:0 auto;overflow:auto;border-radius:28px 28px 0 0;background:#fffaf5;padding:18px;box-shadow:0 -18px 44px #00000024}.schedule-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.schedule-head h2{margin:0;font-size:23px;line-height:1.15}.schedule-close{border:0;width:38px;height:38px;border-radius:50%;background:#fff0e8;color:#ff5f00;font-weight:950}.calendar-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin:12px 0}.calendar-day{min-height:48px;border:1px solid #ff5f0018;border-radius:14px;background:white;color:#1f1f1f;font-weight:900}.calendar-day.muted{color:#b8b8b8;background:#fffaf7}.calendar-day.selected{background:#ff5f00;color:white;border-color:#ff5f00;box-shadow:0 8px 18px #ff5f0030}.calendar-weekday{display:grid;place-items:center;color:#69707a;font-size:11px;font-weight:900}.schedule-note{margin:0;color:#69707a;font-size:13px;line-height:1.45;font-weight:750}.schedule-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.schedule-actions button{min-height:48px}.schedule-list{display:grid;gap:12px}.schedule-day-card{padding:12px;border:1px solid #ff5f0020;border-radius:20px;background:white;box-shadow:0 10px 22px #552d0a0d}.schedule-day-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;color:#ff5f00;font-size:14px;font-weight:950}.schedule-item{display:grid;grid-template-columns:64px 1fr;gap:10px;align-items:center;padding:8px 0;border-top:1px solid #ff5f0014}.schedule-item:first-of-type{border-top:0}.schedule-item img{width:64px;aspect-ratio:1/1;border-radius:14px;object-fit:cover;background:#2a1d16}.schedule-item h3{margin:0;font-size:14px;line-height:1.3}.schedule-item p{margin:5px 0 0;color:#69707a;font-size:12px;line-height:1.35}.schedule-empty{padding:22px;border-radius:22px;background:white;border:1px solid #ff5f0018}.schedule-empty h3{margin:0 0 8px;font-size:20px}.schedule-empty p{margin:0;color:#69707a;line-height:1.5;font-weight:750}"""
    profile_override_css += """.shoot-calendar{display:grid;gap:14px}.shoot-calendar-panel{border-radius:28px;background:#fff;border:1px solid #ff5f0020;box-shadow:0 16px 34px #552d0a10;padding:14px}.shoot-calendar-head{display:grid;grid-template-columns:42px 1fr 42px;align-items:center;gap:8px;margin-bottom:10px}.shoot-month-btn{width:42px;height:42px;border:0;border-radius:50%;background:#fff0e8;color:#ff5f00;font-size:20px;font-weight:950}.shoot-month-title{text-align:center}.shoot-month-title b{display:block;font-size:20px;line-height:1.15}.shoot-month-title span{display:block;margin-top:3px;color:#69707a;font-size:12px;font-weight:800}.shoot-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}.shoot-weekday{display:grid;place-items:center;height:24px;color:#9a9a9a;font-size:11px;font-weight:900}.shoot-day{position:relative;min-height:54px;border:1px solid transparent;border-radius:16px;background:#fff8f3;color:#1f1f1f;font-size:14px;font-weight:900}.shoot-day.outside{color:#c8c8c8;background:#fffaf8}.shoot-day.active{background:#ff5f00;color:white;border-color:#ff5f00;box-shadow:0 10px 20px #ff5f0030}.shoot-day.has-items{border-color:#ff5f0042;background:#fff3eb}.shoot-day.active.has-items{background:#ff5f00}.shoot-dot{position:absolute;left:50%;bottom:7px;transform:translateX(-50%);min-width:16px;height:16px;border-radius:999px;display:grid;place-items:center;background:#ff5f00;color:white;font-size:9px;line-height:1;font-weight:950}.shoot-day.active .shoot-dot{background:white;color:#ff5f00}.shoot-agenda{display:grid;gap:10px}.shoot-agenda-title{display:flex;align-items:center;justify-content:space-between;padding:0 4px;color:#1f1f1f;font-size:15px;font-weight:950}.shoot-agenda-title span{color:#69707a;font-size:12px;font-weight:850}.shoot-empty{padding:20px;border-radius:22px;background:white;border:1px solid #ff5f0018;color:#69707a;line-height:1.5;font-weight:750}.shoot-empty b{display:block;margin-bottom:7px;color:#1f1f1f;font-size:19px}.schedule-item{border:1px solid #ff5f0018;border-radius:20px;background:white;padding:10px;box-shadow:0 10px 22px #552d0a0d}.schedule-item:first-of-type{border-top:1px solid #ff5f0018}@media(max-width:380px){.shoot-day{min-height:48px;border-radius:14px}.shoot-calendar-panel{padding:12px;border-radius:24px}}"""
    profile_override_css += """.title-row{align-items:flex-start}.title-row h1{min-width:0}.reselect-title{flex:0 0 auto;max-width:152px;min-height:44px;padding:0 14px;white-space:normal;line-height:1.12;text-align:center}.featured-actions .primary,.featured-actions .featured-icon,.featured-next{display:inline-flex;align-items:center;justify-content:center;gap:8px}.btn-ico{display:inline-grid;place-items:center;width:20px;height:20px;flex:0 0 20px;font-size:16px;line-height:1}.featured-next .btn-ico{font-size:15px}@media(max-width:380px){.reselect-title{max-width:134px;font-size:11px;padding:0 10px}.title-row{gap:8px}}"""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Koko</title>{FAVICON_LINKS}<style>{profile_override_css}
*{{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}body{{margin:0;background:#fff4ea;color:#1f1f1f}}button,a{{font:inherit}}.phone{{width:min(100%,480px);min-height:100vh;margin:0 auto;padding-bottom:96px;overflow-x:hidden;background:linear-gradient(180deg,#fffaf5,#fff0df 42%,#fff8f2)}}.top{{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;padding:18px 22px 12px;background:rgba(255,252,248,.9);backdrop-filter:blur(16px)}}.brand{{font-size:34px;font-weight:900}}.brand span{{color:#ff5f00;font-size:17px;margin-left:8px}}.lang{{position:fixed;right:max(14px,calc((100vw - 480px)/2 + 14px));bottom:92px;z-index:20;display:flex;gap:4px;padding:5px;border-radius:999px;background:white;box-shadow:0 12px 28px #ff820022}}.lang button{{border:0;border-radius:999px;padding:7px 10px;background:transparent;font-size:12px;font-weight:850;color:#777}}.lang .active{{background:#ff5f00;color:white}}.view{{display:none;padding:22px}}.view.active{{display:block}}.chip,.tag{{display:inline-flex;align-items:center;border:1px solid #ff5f0070;border-radius:999px;padding:8px 12px;color:#ff5f00;background:#ffffff90;font-size:12px;font-weight:850}}.step-label{{display:block;margin:2px 0 0;color:#ff5f00;font-size:13px;font-weight:850}}button.chip{{cursor:pointer;min-height:38px}}button.chip:active{{transform:scale(.98);background:#fff0e8}}.title-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:2px 0 12px}}.title-row h1{{margin:0;font-size:clamp(30px,8vw,46px);flex:1}}.reselect-title{{border:1px solid #ff5f0060;border-radius:999px;min-height:38px;padding:0 12px;background:#fff7f0;color:#ff5f00;font-size:12px;font-weight:900;white-space:nowrap;box-shadow:0 8px 18px #ff5f0018}}h1{{margin:10px 0 12px;font-size:clamp(38px,10vw,56px);line-height:1.08;font-weight:900}}.lead{{margin:0;color:#69707a;font-size:16px;line-height:1.55}}.primary,.open{{border:0;border-radius:999px;min-height:48px;padding:0 16px;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;text-decoration:none;font-weight:900;box-shadow:0 14px 30px #ff5f0040}}.secondary{{border:0;border-radius:999px;min-height:44px;padding:0 16px;background:white;color:#1f1f1f;font-weight:850;box-shadow:0 10px 24px #00000010}}.step-actions{{display:grid;grid-template-columns:1fr;gap:10px;margin-top:18px}}.step-actions button{{min-height:54px}}.cta{{display:grid;gap:12px;margin:18px 0}}.card{{border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a14}}.hero{{min-height:150px;margin:20px -22px 0;position:relative;overflow:hidden}}.mascot{{position:absolute;right:26px;bottom:8px;width:116px;height:116px;border-radius:52% 48% 44% 56%;background:radial-gradient(circle at 35% 22%,#ffbe55,#ff8e24 64%,#f97808)}}.quick{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}}.quick button{{min-height:78px;border:0;border-radius:18px;background:white;font-weight:850}}.quick b{{display:block;color:#ff5f00;font-size:22px}}.stepper{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 24px}}.step{{min-height:58px;border:0;border-radius:18px;background:white;display:grid;place-items:center;color:#777;font-weight:900;cursor:pointer}}.step:active{{transform:scale(.98)}}.step.active{{background:#ff5f00;color:white}}.options,.feed{{display:grid;gap:14px;margin-top:16px}}.option{{min-height:72px;border:1px solid #ff820026;border-radius:18px;background:white;text-align:left;padding:14px;font-weight:850}}.option.selected{{border-color:#ff5f00;color:#ff5f00}}.question-submit{{width:100%;min-height:72px;margin-top:14px;border-radius:18px;font-size:22px;justify-content:center;text-align:center}}.date-group{{margin-top:16px}}.date-divider{{display:flex;align-items:center;justify-content:center;min-height:34px;border:1px solid rgba(255,95,0,.36);border-radius:999px;background:#fffdf9;color:#1f1f1f;font-size:15px;font-weight:900;box-shadow:0 8px 20px #552d0a0a}}.masonry{{columns:2 150px;column-gap:10px;margin-top:10px}}.masonry-card{{break-inside:avoid;display:block;width:100%;margin:0 0 10px;border:1px solid rgba(255,95,0,.26);border-radius:12px;overflow:hidden;background:white;color:#1f1f1f;text-align:left;box-shadow:0 6px 18px #552d0a10;cursor:pointer}}.masonry-card:active{{transform:scale(.99)}}.masonry-card img{{display:block;width:100%;height:auto;aspect-ratio:3/4;object-fit:cover;background:#2a1d16}}.masonry-card:nth-child(3n+2) img{{aspect-ratio:1/1}}.masonry-card:nth-child(4n+3) img{{aspect-ratio:4/5}}.masonry-title{{display:block;padding:9px 10px 11px;font-size:14px;line-height:1.34;font-weight:850;white-space:normal;overflow:visible;word-break:break-word}}.script{{display:grid;grid-template-columns:116px 1fr;gap:13px;padding:14px;min-height:168px}}.thumb{{position:relative;overflow:hidden;border-radius:16px;min-height:142px;background:#2a1d16;color:white;padding:10px;font-size:12px;font-weight:900}}.thumb img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.thumb:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000010,#000000aa)}}.thumb span{{position:relative;z-index:1;background:#9e490ce0;border-radius:9px;padding:6px 8px}}.body{{min-width:0;display:flex;flex-direction:column;gap:8px}}.body h3{{margin:0;font-size:18px;line-height:1.22;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.body p{{margin:0;color:#69707a;font-size:13px;line-height:1.42;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}.tags{{display:flex;gap:6px;flex-wrap:wrap}}.tag{{padding:5px 8px;background:#fff0e8;font-size:11px}}.actions{{display:grid;grid-template-columns:1fr 38px 38px;gap:8px;margin-top:auto}}.icon{{border:0;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#fff0e8;color:#ff5f00;font-weight:900}}.tabs{{display:flex;gap:8px;overflow:auto;padding:4px 0 12px}}.tabs button{{border:1px solid #ff5f0038;border-radius:999px;padding:9px 13px;background:white;color:#777;font-size:12px;font-weight:850}}.tabs .active{{background:#ff5f00;color:white}}.bottom{{position:fixed;left:50%;bottom:0;transform:translateX(-50%);z-index:18;width:min(100%,480px);display:grid;grid-template-columns:repeat(2,1fr);gap:2px;padding:10px 14px;background:#fffffff0;border-radius:24px 24px 0 0;box-shadow:0 -14px 34px #00000014}}.bottom button{{border:0;background:transparent;min-height:54px;color:#777;font-size:12px;font-weight:750}}.bottom .active{{color:#ff5f00}}.modal{{position:fixed;inset:0;z-index:50;display:none;align-items:flex-end;background:#1f1f1f55;padding:18px 18px 0}}.modal.active{{display:flex}}.sheet{{width:min(100%,480px);max-height:88vh;overflow:auto;margin:0 auto;border-radius:28px 28px 0 0;background:#fffaf5;padding:18px}}.sheet-img{{height:220px;border-radius:20px;overflow:hidden;background:#2a1d16}}.sheet-img img{{width:100%;height:100%;object-fit:cover}}.submit{{display:grid;gap:10px;margin:14px 0;padding:14px;border-radius:18px;background:#fff0e8}}.submit input{{min-height:46px;border:1px solid #ff5f0038;border-radius:14px;padding:0 12px}}.state{{padding:18px}}@media(max-width:380px){{.view{{padding:18px}}h1{{font-size:36px}}.script{{grid-template-columns:104px 1fr}}}}
.modal{{padding:10px 10px 0}}.sheet{{height:96vh;max-height:96vh;border-radius:24px 24px 0 0;padding:12px 12px 24px}}.detail-top{{position:sticky;top:0;z-index:2;display:flex;justify-content:flex-end;padding:2px 0 8px;background:#fffaf5cc;backdrop-filter:blur(12px)}}.detail-cover{{position:relative;width:100%;aspect-ratio:4/5;border-radius:22px;overflow:hidden;background:#2a1d16;margin:0 0 14px;box-shadow:0 18px 38px #552d0a1c}}.detail-cover img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.detail-cover:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000008,#00000000 48%,#0000003f)}}.video-section{{margin:16px 0 14px}}.video-section-title{{display:flex;align-items:center;justify-content:space-between;margin:0 0 8px;color:#1f1f1f;font-size:15px;font-weight:950}}.video-section-title span{{color:#ff5f00;font-size:12px}}.video-box{{position:relative;width:100%;height:min(78vh,760px);aspect-ratio:9/16;border-radius:18px;overflow:hidden;background:#111;margin-bottom:14px}}.video-box iframe,.video-box img,.video-box video{{position:absolute;inset:0;width:100%;height:100%;border:0;object-fit:contain;background:#111}}.video-fallback{{position:absolute;inset:auto 12px 12px;z-index:1;border-radius:14px;padding:10px;background:#00000099;color:white;font-size:12px;line-height:1.4}}.detail-title{{margin:8px 0 10px;font-size:25px;line-height:1.18;font-weight:900}}.social-actions{{display:flex;gap:10px;margin:14px 0 10px;padding:10px 0;border-top:1px solid rgba(255,95,0,.12);border-bottom:1px solid rgba(255,95,0,.12)}}.social-btn{{border:1px solid rgba(255,95,0,.26);border-radius:999px;min-width:48px;height:48px;padding:0 15px;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:white;color:#ff5f00;font-size:22px;font-weight:900;box-shadow:0 8px 20px #552d0a10}}.social-btn span{{font-size:13px;color:#1f1f1f}}.share-box{{display:none;margin:0 0 12px;padding:12px;border:1px solid rgba(255,95,0,.22);border-radius:16px;background:#fff7f0;color:#69707a;font-size:12px;line-height:1.45}}.share-box.active{{display:block}}.share-box b{{display:block;margin-bottom:6px;color:#1f1f1f;font-size:13px}}.share-box a{{display:block;color:#ff5f00;font-weight:850;word-break:break-all}}.script-html{{margin-top:12px;padding:0;border-radius:18px;background:transparent;border:0;overflow:visible}}.clean-script{{display:grid;gap:12px}}.storyboard{{aspect-ratio:1/1;border-radius:20px;background:#fbfaf7;border:1px solid rgba(255,95,0,.18);overflow:hidden;box-shadow:0 10px 24px rgba(85,45,10,.08)}}.storyboard-img{{display:block;width:100%;height:100%;object-fit:cover}}.brief-card,.insight-section{{border:1px solid rgba(255,95,0,.18);border-radius:18px;background:white;padding:15px;box-shadow:0 10px 24px rgba(85,45,10,.08)}}.brief-card b{{display:block;margin-bottom:9px;color:#ff5f00;font-size:16px;line-height:1.2;font-weight:950;letter-spacing:.01em}}.brief-card p{{margin:0;color:#1f1f1f;font-size:15px;line-height:1.62;word-break:break-word}}.brief-list{{display:grid;gap:10px}}.insight-section h3{{margin:0 0 12px!important;color:#1f1f1f!important;font-size:22px!important;line-height:1.15!important;font-weight:950!important}}.insight-cards{{display:grid;gap:10px}}.insight-cards article{{border:1px solid rgba(255,95,0,.14);border-radius:14px;background:#fffdf9;padding:12px}}.insight-cards b{{display:block;margin:0 0 6px;color:#1f1f1f;font-size:15px;line-height:1.25;font-weight:950}}.insight-cards p{{margin:0;color:#4f5661;font-size:13px;line-height:1.55}}.script-table-card{{border:1px solid rgba(255,95,0,.22);border-radius:18px;background:white;overflow:hidden;box-shadow:0 10px 24px rgba(85,45,10,.08);width:100%;max-width:100%;margin:0}}.script-table-title{{padding:14px 14px 12px;font-size:22px;line-height:1.15;font-weight:950;color:#1f1f1f;border-bottom:1px solid #ffd8c0}}.script-table{{width:100%;table-layout:fixed;border-collapse:collapse}}.script-table th,.script-table td{{border-right:1px solid #ffd8c0;border-bottom:1px solid #ffd8c0;padding:8px 3px;vertical-align:top;color:#1f1f1f;word-break:break-word;overflow-wrap:anywhere}}.script-table th:last-child,.script-table td:last-child{{border-right:0}}.script-table tr:last-child td{{border-bottom:0}}.script-table th{{background:#fff8f2;font-size:12px;line-height:1.2;font-weight:950;text-align:center}}.script-table td{{font-size:11px;line-height:1.48}}.script-table .col-time{{width:10.5%}}.script-table .col-image{{width:30.5%}}.script-table .col-action{{width:27%}}.script-table .col-dialogue{{width:32%}}.script-table .time-cell{{font-weight:900;color:#ff5f00;text-align:center;white-space:normal;font-size:9px;line-height:1.18;letter-spacing:0}}.shot-cell{{display:grid;gap:6px}}.shot-thumb{{position:relative;width:100%;aspect-ratio:1/1;border-radius:8px;overflow:hidden;background:#fbfaf7;border:1px solid rgba(0,0,0,.16)}}.shot-thumb img{{position:absolute;width:calc(var(--cols)*100%);height:calc(var(--rows)*100%);max-width:none!important;object-fit:cover;left:calc(var(--sx)*-100%);top:calc(var(--sy)*-100%)}}.shot-text{{font-size:10.5px;line-height:1.35;color:#1f1f1f}}.script-shot-list{{display:grid;gap:14px;padding:12px;background:#fffaf6}}.script-shot-card{{display:grid;gap:10px;border:1px solid rgba(255,95,0,.22);border-radius:18px;background:#fff;padding:10px;box-shadow:0 10px 22px rgba(85,45,10,.08)}}.script-shot-time{{border:1px solid rgba(255,95,0,.24);border-radius:14px;background:#fffdf9;padding:10px 13px;color:#ff5f00;font-size:14px;font-weight:950;line-height:1.2}}.script-shot-body{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:10px;align-items:stretch}}.script-shot-visual,.script-shot-info{{min-width:0}}.script-shot-visual{{display:grid;gap:8px;align-content:start}}.script-shot-image{{position:relative;width:100%;aspect-ratio:1/1;border-radius:16px;overflow:hidden;background:#fbfaf7;border:1px solid rgba(0,0,0,.18)}}.script-shot-image img{{position:absolute;width:calc(var(--cols)*100%);height:calc(var(--rows)*100%);max-width:none!important;border-radius:0!important;object-fit:cover!important;left:calc(var(--sx)*-100%);top:calc(var(--sy)*-100%)}}.script-shot-caption{{margin:0;color:#4f5661;font-size:11px;line-height:1.38;font-weight:750}}.script-shot-info{{display:grid;grid-template-rows:1fr 1fr;gap:10px}}.script-shot-box{{min-height:104px;border:1px solid rgba(255,95,0,.20);border-radius:16px;background:#fffdf9;padding:12px;overflow:hidden}}.script-shot-box b{{display:block;margin:0 0 7px;color:#ff5f00;font-size:13px;line-height:1.2;font-weight:950}}.script-shot-box p{{margin:0;color:#1f1f1f;font-size:12.5px;line-height:1.48;font-weight:700;word-break:break-word;overflow-wrap:anywhere}}@media(max-width:380px){{.script-shot-list{{padding:10px;gap:12px}}.script-shot-card{{padding:9px}}.script-shot-body{{gap:8px;grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr)}}.script-shot-box{{min-height:96px;padding:10px}}.script-shot-box p{{font-size:11.5px;line-height:1.42}}.script-shot-caption{{font-size:10.5px}}}}.raw-script-source{{display:none}}.script-loading{{margin-top:12px;padding:18px;border-radius:18px;background:white;border:1px solid rgba(255,95,0,.14);color:#69707a}}.script-loading b{{display:block;margin-bottom:8px;color:#1f1f1f;font-size:16px}}.script-progress{{position:relative;height:6px;margin-top:12px;overflow:hidden;border-radius:999px;background:#ffe4d2}}.script-progress:after{{content:"";position:absolute;inset:0 auto 0 0;width:42%;border-radius:999px;background:linear-gradient(90deg,#ff7a18,#ff5200);animation:scriptLoad 1.1s ease-in-out infinite}}@keyframes scriptLoad{{0%{{transform:translateX(-105%)}}100%{{transform:translateX(245%)}}}}.script-html *{{max-width:100%}}.script-html h1{{font-size:24px;line-height:1.18;margin:0 0 10px}}.script-html h2{{font-size:19px;line-height:1.25;margin:18px 0 10px}}.script-html h3{{font-size:16px;line-height:1.3;margin:14px 0 8px}}.script-html p,.script-html li,.script-html td,.script-html th{{font-size:14px;line-height:1.7;word-break:break-word}}.script-html img,.script-html video{{height:auto;border-radius:12px}}.script-html .shot-thumb img{{position:absolute!important;width:calc(var(--cols)*100%)!important;height:calc(var(--rows)*100%)!important;max-width:none!important;border-radius:0!important;object-fit:cover!important;left:calc(var(--sx)*-100%)!important;top:calc(var(--sy)*-100%)!important}}.script-html table{{display:block;width:100%;overflow-x:auto;border-collapse:collapse;white-space:normal}}.script-html th,.script-html td{{min-width:120px;border:1px solid #ffe0cc;padding:8px;vertical-align:top}}.script-html .wrap,.script-html .card{{max-width:100%;padding:0;box-shadow:none;background:transparent}}.script-html .script-table th,.script-html .script-table td{{min-width:0!important}}
.landing{{padding:22px;background:linear-gradient(180deg,#fffaf5,#fff0df 42%,#fff8f2)}}.landing .hero{{min-height:238px;margin:18px -22px 0;position:relative;overflow:hidden}}.landing .cta{{grid-template-columns:1fr;gap:10px;margin:20px 0 10px}}.landing-register{{border:0;border-radius:999px;min-height:50px;padding:0 16px;background:white;color:#1f1f1f;font-weight:900;box-shadow:0 10px 24px #00000010}}.landing-section{{margin-top:28px}}.landing-section h2{{font-size:25px;line-height:1.15;margin:0 0 14px;font-weight:950}}.preview-strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0;padding:12px;border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a14}}.preview-card{{min-height:162px;border-radius:16px;background:linear-gradient(180deg,#4b2b19,#17110e);position:relative;overflow:hidden;color:white;padding:10px;display:flex;align-items:flex-end;font-weight:900;font-size:13px;line-height:1.25;background-size:cover;background-position:center}}.preview-card:before{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000008,#000000c0)}}.preview-card span{{position:relative;z-index:1;text-shadow:0 2px 8px #00000070}}.preview-card:nth-child(1){{background-image:url('/static/landing-storyboard-1.jpg')}}.preview-card:nth-child(2){{background-image:url('/static/landing-storyboard-2.jpg')}}.preview-card:nth-child(3){{background-image:url('/static/landing-storyboard-3.jpg')}}.info-panel{{min-height:104px;border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a10;display:grid;place-items:center;padding:20px;text-align:center;color:#69707a;font-size:15px;line-height:1.55;font-weight:750}}.feature-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 24px}}.feature{{min-height:94px;border-radius:18px;background:white;border:1px solid #ff82001a;display:grid;place-items:center;text-align:center;padding:10px;font-size:13px;font-weight:850;color:#1f1f1f}}.feature b{{display:block;color:#ff5f00;font-size:24px;margin-bottom:5px}}.author-cloud{{position:relative;height:250px;margin:14px 0;overflow:hidden;border-radius:28px;background:radial-gradient(circle at 50% 50%,#fff7ee 0,#ffe8d8 44%,#fff4ea 100%)}}.author-dot{{position:absolute;border-radius:50%;background-color:#ffd9bf;background-position:center;background-size:cover;background-repeat:no-repeat;box-shadow:0 18px 34px #ff5f0028;border:6px solid #fffaf5;animation:floatAvatar 12s ease-in-out infinite alternate;will-change:transform}}.author-dot:nth-child(1){{width:96px;height:96px;left:36%;top:8px;background-image:url('/static/landing-avatar-real-01.jpg');animation-duration:13s}}.author-dot:nth-child(2){{width:70px;height:70px;left:8%;top:82px;background-image:url('/static/landing-avatar-real-02.jpg');animation-duration:11s;animation-delay:-3s}}.author-dot:nth-child(3){{width:106px;height:106px;right:8%;top:86px;background-image:url('/static/landing-avatar-real-03.jpg');animation-duration:15s;animation-delay:-6s}}.author-dot:nth-child(4){{width:116px;height:116px;left:30%;bottom:10px;background-image:url('/static/landing-avatar-real-04.jpg');animation-duration:14s;animation-delay:-2s}}.author-dot:nth-child(5){{width:58px;height:58px;left:68%;top:22px;background-image:url('/static/landing-avatar-real-05.jpg');animation-delay:-5s}}.author-dot:nth-child(6){{width:66px;height:66px;left:2%;bottom:26px;background-image:url('/static/landing-avatar-real-06.jpg');animation-duration:10s;animation-delay:-7s}}.author-dot:nth-child(7){{width:74px;height:74px;right:0;bottom:12px;background-image:url('/static/landing-avatar-real-07.jpg');animation-duration:12s;animation-delay:-4s}}.author-dot:nth-child(8){{width:52px;height:52px;left:20%;top:18px;background-image:url('/static/landing-avatar-real-08.jpg');animation-duration:9s;animation-delay:-8s}}.author-dot:nth-child(9){{width:62px;height:62px;right:30%;bottom:4px;background-image:url('/static/landing-avatar-real-09.jpg');animation-duration:13s;animation-delay:-1s}}.author-dot:nth-child(10){{width:50px;height:50px;right:16%;top:6px;background-image:url('/static/landing-avatar-real-10.jpg');animation-duration:10s;animation-delay:-9s}}.author-dot:nth-child(11){{width:64px;height:64px;left:48%;top:92px;background-image:url('/static/landing-avatar-real-11.jpg');animation-duration:12s;animation-delay:-10s}}.author-dot:nth-child(12){{width:60px;height:60px;right:42%;bottom:62px;background-image:url('/static/landing-avatar-real-12.jpg');animation-duration:11s;animation-delay:-6s}}@keyframes floatAvatar{{0%{{transform:translate3d(-10px,8px,0) scale(.98)}}50%{{transform:translate3d(14px,-12px,0) scale(1.04)}}100%{{transform:translate3d(-4px,16px,0) scale(1)}}}}.ending-card{{min-height:238px;border-radius:28px;border:1px solid #ff5f0024;background:linear-gradient(135deg,#fff,#ffe3cf);display:grid;place-items:center;text-align:center;font-size:30px;font-weight:950;box-shadow:0 18px 42px #552d0a14;padding:26px}}.ending-card small{{display:block;margin-top:8px;color:#69707a;font-size:15px;font-weight:750;line-height:1.5}}.auth-overlay{{position:fixed;inset:0;z-index:70;display:none;place-items:center;background:linear-gradient(180deg,#fffaf5,#fff0df 60%,#fff7f0);padding:22px}}.auth-overlay.active{{display:grid}}.auth-card{{width:min(100%,390px);min-height:420px;border:1px solid #ff5f0026;border-radius:28px;background:#fffffff2;padding:34px 24px;box-shadow:0 26px 60px #552d0a18}}.auth-card h2{{text-align:center;font-size:34px;margin:0 0 24px;color:#1f1f1f}}.auth-card input{{width:100%;min-height:52px;margin-bottom:12px;border:1px solid #ff5f0028;border-radius:16px;padding:0 16px;font-size:15px;background:#fffaf7;color:#1f1f1f;outline:none}}.auth-card input:focus{{border-color:#ff5f00;box-shadow:0 0 0 4px #ff5f0012}}.auth-meta{{display:flex;align-items:center;justify-content:space-between;margin:8px 0 22px;color:#69707a;font-size:14px}}.auth-submit{{width:100%;min-height:52px;border:0;border-radius:999px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;font-weight:950;box-shadow:0 14px 30px #ff5f0036}}.auth-switch{{margin-top:18px;text-align:center;color:#62666d;font-weight:750}}.auth-switch button,.link-btn{{border:0;background:transparent;color:#ff5f00;font-weight:900}}.auth-close{{position:absolute;top:18px;right:18px;background:white}}.profile-hero{{margin:-22px -22px 16px;position:relative;min-height:290px;overflow:hidden;background:linear-gradient(135deg,#2b211d,#ff6a00);color:white}}.profile-cover{{position:absolute;inset:0;background:linear-gradient(145deg,#2a1d16,#ff6a00 58%,#ffd6ad);background-size:cover;background-position:center;filter:saturate(1.05)}}.profile-cover:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000020,#00000088)}}.profile-tools{{position:absolute;top:14px;right:14px;z-index:2;display:flex;gap:8px}}.profile-upload{{border:1px solid #ffffff60;border-radius:999px;min-height:34px;padding:0 10px;background:#ffffff28;color:white;font-size:12px;font-weight:850;backdrop-filter:blur(10px)}}.profile-info{{position:relative;z-index:1;padding:78px 18px 18px}}.profile-row{{display:flex;gap:14px;align-items:end}}.profile-avatar{{position:relative;width:92px;height:92px;border-radius:50%;border:4px solid white;background:white center/cover no-repeat;box-shadow:0 14px 28px #00000030;overflow:hidden}}.profile-avatar:before{{content:"";position:absolute;inset:0;background:radial-gradient(circle at 35% 25%,#ffc46b,#ff8e24 64%,#f97808)}}.profile-avatar.has-image:before{{display:none}}.profile-name{{margin:0 0 7px;font-size:28px;line-height:1.05;font-weight:950;text-shadow:0 2px 12px #00000035}}.profile-bio{{margin:0;color:#ffffffd8;font-size:13px;font-weight:750}}.profile-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:18px}}.profile-stats b{{display:block;font-size:19px;color:white}}.profile-stats span{{color:#ffffffc8;font-size:12px}}.profile-prefs{{margin-top:16px;display:flex;gap:8px;flex-wrap:wrap}}.profile-prefs .chip{{background:#ffffff22;color:white;border-color:#ffffff55;backdrop-filter:blur(8px)}}.profile-card-strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0 16px}}.profile-mini{{border:0;border-radius:16px;min-height:66px;background:#ffffffcc;color:#1f1f1f;font-size:12px;font-weight:850;box-shadow:0 10px 24px #552d0a10}}.profile-mini b{{display:block;color:#ff5f00;font-size:18px;margin-bottom:3px}}.profile-tabs{{position:sticky;top:62px;z-index:4;margin:0 -22px;padding:8px 22px;background:#fffaf5e8;backdrop-filter:blur(14px);border-bottom:1px solid #ff5f0012}}.profile-tabs .tabs{{padding:0}}.hidden-input{{display:none}}.modal{{align-items:stretch;padding:0;background:#fff;z-index:80}}.modal.active{{display:block}}.sheet{{width:min(100%,480px);height:100vh;max-height:100vh;margin:0 auto;border-radius:0;background:#fff;padding:0;overflow:auto}}.detail-top{{position:sticky;top:0;z-index:5;justify-content:flex-start;padding:10px;background:#ffffffd8}}.video-box{{height:auto;aspect-ratio:4/5;border-radius:0;margin:0;background:#050505}}.video-box iframe,.video-box img,.video-box video{{object-fit:contain}}.detail-content{{padding:12px 14px 90px;background:white}}.detail-title{{font-size:20px;margin:12px 0 8px}}.social-actions{{position:sticky;bottom:0;z-index:6;margin:0 -14px;padding:9px 12px;background:#fffffff2;border-top:1px solid #00000010;border-bottom:0;justify-content:space-around}}.social-btn{{border:0;box-shadow:none;background:white;color:#1f1f1f;font-size:26px;flex-direction:row}}.social-btn span{{font-size:14px;color:#1f1f1f}}.comment-pill{{min-height:42px;border-radius:999px;background:#f4f4f4;padding:0 14px;color:#777;display:flex;align-items:center;min-width:130px}}.bottom{{grid-template-columns:repeat(2,1fr)}}.landing .mascot{{position:absolute;right:-18px;bottom:-22px;width:250px;height:250px;border-radius:0;background:transparent;object-fit:contain;filter:drop-shadow(0 24px 30px #ff5f0036)}}.landing .hero:before{{content:"";position:absolute;right:-64px;bottom:-30px;width:286px;height:146px;border-radius:999px;background:linear-gradient(135deg,#ffd9bf,#ffb98c);opacity:.72}}.landing .hero:after{{content:"✦";position:absolute;right:204px;top:34px;color:#ff9f24;font-size:28px;text-shadow:70px 42px 0 #fff,22px 112px 0 #fff}}.title-row{{display:grid!important;grid-template-columns:1fr!important;align-items:start!important;gap:12px!important;margin-bottom:18px!important}}.title-row h1{{min-width:0!important;width:100%!important}}.reselect-title{{justify-self:start!important;max-width:none!important;min-width:0!important;min-height:42px!important;padding:0 16px!important;white-space:nowrap!important;line-height:1!important;text-align:center!important}}.featured-actions .primary,.featured-actions .featured-icon,.featured-next{{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:8px!important}}.btn-ico{{display:inline-grid;place-items:center;width:20px;height:20px;flex:0 0 20px;font-size:16px;line-height:1}}@media(max-width:380px){{.reselect-title{{font-size:11px!important;padding:0 12px!important}}.title-row{{gap:10px!important}}}}</style></head><body><main class="phone"><header class="top"><div class="brand">kwai <span>Koko</span></div></header>
<section class="view landing" data-view="home"><h1>Encontre roteiros que você consegue gravar</h1><p class="lead">Receba recomendações com base no seu perfil de criação, formatos que combinam com você e roteiros prontos para gravar.</p><div class="hero"><img class="mascot" src="/static/koko-creator-mascot-cutout.png" alt="Koko Creator"></div><div class="cta"><button class="primary" type="button" data-auth-open="login">Entrar com telefone</button><button class="landing-register" type="button" data-auth-open="login">Abrir login</button></div><section class="landing-section"><h2>Veja antes de escolher</h2><div class="preview-strip"><div class="preview-card"><span>Preview do roteiro</span></div><div class="preview-card"><span>Referência em vídeo</span></div><div class="preview-card"><span>Estrutura de gravação</span></div></div></section><section class="landing-section"><div class="feature-row"><div class="feature"><b>1</b>Escolha seu perfil</div><div class="feature"><b>2</b>Veja recomendações</div><div class="feature"><b>3</b>Grave e envie</div></div></section><section class="landing-section"><h2>Criadores parceiros</h2><div class="author-cloud"><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span></div><div class="info-panel">Já trabalhamos com muitos grandes criadores da plataforma Kwai. Vídeos gravados a partir dos roteiros da Koko tiveram desempenho acima da média de visualizações dos próprios criadores, e em alguns casos ajudaram a aumentar a renda em até 200%.</div></section><section class="landing-section ending-card"><div>Pronto para começar a gravar com a Koko?<small>Entre com seu telefone, escolha suas preferências uma vez e volte todos os dias para ver novos roteiros.</small><br><button class="primary" type="button" data-auth-open="login">Entrar agora</button></div></section></section>
<section class="view" data-view="dashboard"><div class="title-row"><h1 data-t="todayTitle">Recomendação de roteiros</h1><button class="reselect-title" type="button" data-reselect="true" data-t="changePrefs">Mudar preferências</button></div><div id="dashboard-feed"></div></section>
<section class="view" data-view="all-scripts"><div class="all-title-row"><button class="back-pill" type="button" data-go="dashboard">←</button><h1 id="all-title">Todos os roteiros</h1></div><div id="all-feed"></div></section>
<section class="view" data-view="choose"><span class="step-label" id="step-label">Etapa 1 de 3</span><div class="stepper" id="stepper"></div><div id="question"></div><div class="step-actions"><button class="secondary" id="prev-step" type="button"><span data-t="prev">Etapa anterior</span></button></div></section>
<section class="view" data-view="saved"><section class="profile-hero"><div class="profile-cover" id="profile-cover"></div><div class="profile-tools"><button class="profile-upload" type="button" data-upload-trigger="cover" data-t="editCover">Capa</button><button class="profile-upload" type="button" data-upload-trigger="avatar" data-t="editAvatar">Avatar</button><button class="profile-upload profile-logout" type="button" data-logout data-t="logout">Sair</button></div><div class="profile-info"><div class="profile-row"><div class="profile-avatar" id="profile-avatar"></div><div><h1 class="profile-name" id="creator-name">Koko Creator</h1><p class="profile-bio" data-t="profileBio">Biblioteca pessoal de roteiros e gravações.</p></div></div><div class="profile-stats"><div><b id="profile-count-finished">0</b><span data-t="statusFinished">Gravados</span></div><div><b id="profile-count-saved">0</b><span data-t="statusSaved">Salvos</span></div></div><div class="profile-prefs" id="profile-filters"></div></div></section><input class="hidden-input" id="profile-avatar-input" type="file" accept="image/*"><input class="hidden-input" id="profile-cover-input" type="file" accept="image/*"><section class="profile-card-strip"><button class="profile-mini" type="button" data-tab-jump="finished"><b>✓</b><span data-t="statusFinished">Gravados</span></button><button class="profile-mini" type="button" data-tab-jump="saved"><b>♡</b><span data-t="statusSaved">Salvos</span></button><button class="profile-mini" type="button" data-tab-jump="schedule"><b>▦</b><span id="schedule-mini-label">Calendário de gravação</span></button></section><div class="profile-tabs"><div class="tabs" id="saved-tabs"></div></div><div id="saved-feed"></div></section></main>
<nav class="bottom"><button data-go="dashboard">⌂<br><span data-t="navHome">Roteiros</span></button><button data-go="saved">☻<br><span data-t="navSaved">Eu</span></button></nav>
<div class="modal" id="modal"><section class="sheet"><div id="detail"></div></section></div>
<div class="auth-overlay" id="auth-modal"><button class="icon auth-close" type="button" data-auth-close>×</button><section class="auth-card"><h2 id="auth-title">Entrar com telefone</h2><form id="auth-form"><input name="phone" id="auth-phone" inputmode="numeric" autocomplete="tel" placeholder="Número de telefone"><button class="auth-submit" type="submit" id="auth-submit">Entrar</button></form></section></div>
<div class="schedule-overlay" id="schedule-modal"><section class="schedule-sheet"><div class="schedule-head"><h2 id="schedule-title">Adicionar ao calendário de gravação</h2><button class="schedule-close" type="button" data-schedule-close>×</button></div><p class="schedule-note" id="schedule-note">Escolha o dia em que pretende gravar este roteiro.</p><div class="calendar-grid" id="calendar-grid"></div><div class="schedule-actions"><button class="secondary" type="button" data-schedule-close>Mais tarde</button><button class="primary" type="button" data-schedule-confirm>Adicionar</button></div></section></div>
<script>
const questions={questions_json}; const profileKey="koko_profile_v1"; const workspaceKey="koko_workspace_v1"; const authKey="koko_creator_user_v1"; const profileUiKey="koko_creator_profile_ui_v1";
let lang="pt"; let step=0; let savedTab="finished"; let featuredOffset=0; let entries=[]; let submissions=[];
let answers=JSON.parse(localStorage.getItem(profileKey)||"null")||{{people:"couple",subtype:"couple_prank",duration:["dur_20_60"]}};
let workspace=JSON.parse(localStorage.getItem(workspaceKey)||"null")||{{saved:[],planned:[],finished:[],rejected:[],schedule:{{}}}};
if(!workspace.schedule||Array.isArray(workspace.schedule))workspace.schedule={{}};
let authMode="login"; let creatorUser=JSON.parse(localStorage.getItem(authKey)||"null");
let profileUi=JSON.parse(localStorage.getItem(profileUiKey)||"null")||{{avatar:"",cover:""}};
let scheduleDraftId=""; let scheduleSelectedDate=""; let scheduleViewDate=todayKey(); let pendingAuthAction=null;
const initialScriptId=(()=>{{const path=location.pathname.match(/^\\/script\\/([0-9a-f]{{32}})$/);if(path)return path[1];return new URLSearchParams(location.search).get("script")||""}})();
const forceLanding=new URLSearchParams(location.search).get("landing")==="1";
const I={{pt:{{homePill:"Biblioteca de roteiros",homeTitle:"Encontre roteiros que você consegue gravar",homeLead:"Responda 3 perguntas e veja roteiros para o seu estilo.",start:"Começar agora",seePopular:"Ver populares",todayPill:"Recomendação de roteiros",todayTitle:"Recomendação de roteiros",todayLead:"Abra e escolha um roteiro para ver os detalhes.",quickNew:"roteiros",quickSaved:"salvos",quickPlan:"para gravar",next:"Próxima etapa",prev:"Etapa anterior",finish:"Ver recomendações",libraryPill:"Biblioteca",libraryTitle:"Sua biblioteca recomendada",savedPill:"Meus roteiros",savedTitle:"Sua lista de gravação",navHome:"Roteiros",navLibrary:"Biblioteca",navSaved:"Eu",navPrefs:"Perfil",changePrefs:"Mudar preferências",editCover:"Editar capa",editAvatar:"Editar avatar",logout:"Sair",profileBio:"Biblioteca pessoal de roteiros e gravações.",profileHome:"Início",open:"Abrir",save:"Salvar",plan:"Vou gravar",done:"Gravado",reject:"Não serve",original:"Referencia",details:"Detalhes",submitTitle:"Enviar vídeo gravado",submitHint:"Envie o link do vídeo gravado seguindo este roteiro. Vamos revisar e, se aprovado, ajudar com impulsionamento.",submitPlaceholder:"Cole aqui o link do seu vídeo",submitButton:"Enviar para revisão",submitOk:"Recebido. Vamos revisar seu vídeo.",submitError:"Não foi possível enviar. Confira o link.",empty:"Nada aqui ainda",emptyText:"Salve um roteiro da recomendação para montar sua lista.",statusSaved:"Salvos",statusPlanned:"Vou gravar",statusFinished:"Gravados",statusRejected:"Não servem",step:"Etapa"}},zh:{{homePill:"脚本推荐",homeTitle:"找到你真的能拍的脚本",homeLead:"回答 3 个问题，进入你的推荐脚本页面。",start:"开始选择",seePopular:"先看热门",todayPill:"脚本推荐",todayTitle:"脚本推荐",todayLead:"点开卡片，查看完整脚本和拍摄说明。",quickNew:"推荐脚本",quickSaved:"已收藏",quickPlan:"准备拍",next:"下一步",prev:"上一步",finish:"查看推荐",libraryPill:"脚本库",libraryTitle:"你的推荐脚本库",savedPill:"我的脚本",savedTitle:"你的拍摄清单",navHome:"脚本推荐",navLibrary:"脚本库",navSaved:"我",navPrefs:"偏好",changePrefs:"重新选择偏好",editCover:"编辑封面",editAvatar:"编辑头像",logout:"退出登录",profileBio:"你的脚本收藏和视频回传记录。",profileHome:"主页",open:"打开",save:"收藏",plan:"准备拍",done:"已拍",reject:"不适合",original:"参考视频",details:"完整脚本",submitTitle:"回传拍摄视频",submitHint:"上传按照脚本拍摄的视频，我们会审核后给您投流。",submitPlaceholder:"把你发布后的视频链接粘贴在这里",submitButton:"提交审核",submitOk:"已收到，我们会审核这个视频。",submitError:"提交失败，请检查链接。",empty:"这里还没有脚本",emptyText:"先从脚本推荐里收藏一个脚本。",statusSaved:"收藏",statusPlanned:"准备拍",statusFinished:"已拍",statusRejected:"不适合",step:"第"}}}};
const t=k=>(I.pt&&I.pt[k])||k; const label=x=>x.pt||x.zh||""; const esc=v=>String(v||"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
const analyticsVisitorKey="koko_creator_visitor_v1"; const analyticsSessionKey="koko_creator_session_v1";
function analyticsId(store,key){{let v=store.getItem(key)||"";if(!v){{v=(crypto.randomUUID?crypto.randomUUID():`${{Date.now()}}-${{Math.random().toString(16).slice(2)}}`);store.setItem(key,v)}}return v}}
const analyticsVisitorId=analyticsId(localStorage,analyticsVisitorKey); const analyticsSessionId=analyticsId(sessionStorage,analyticsSessionKey);
function track(event,meta={{}}){{try{{const payload={{event,meta,path:location.pathname+location.search,referrer:document.referrer,language:lang,creator_id:creatorUser?.account_id||creatorUser?.phone||creatorUser?.kwai_id||"",session_id:analyticsSessionId,visitor_id:analyticsVisitorId}};const body=JSON.stringify(payload);if(navigator.sendBeacon){{const ok=navigator.sendBeacon("/api/creator/events",new Blob([body],{{type:"application/json"}}));if(ok)return}}fetch("/api/creator/events",{{method:"POST",headers:{{"Content-Type":"application/json"}},body,keepalive:true}}).catch(()=>{{}})}}catch(err){{}}}}
function trackScripts(event,list,extra={{}}){{(list||[]).slice(0,40).forEach((item,index)=>track(event,{{...extra,script_id:item.entry_id,index,title:item.title||""}}))}}
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
function updateProfileHeader(){{updateCreatorName();updateProfileImages();const filters=document.querySelector("#profile-filters");if(filters)filters.innerHTML=chips();const saved=document.querySelector("#profile-count-saved");if(saved)saved.textContent=String((workspace.saved||[]).length);const planned=document.querySelector("#profile-count-planned");if(planned)planned.textContent=String((workspace.planned||[]).length);const finished=document.querySelector("#profile-count-finished");if(finished)finished.textContent=String(submissions.length||0)}}
function authCopy(){{const zh=lang==="zh";return {{login:zh?"电话号码登录":"Entrar com telefone",phone:zh?"请输入电话号码":"Digite o numero de telefone",submit:zh?"登录":"Entrar",missing:zh?"请输入电话号码":"Digite o numero de telefone",notFound:zh?"找不到电话":"Telefone não encontrado"}}}}
function setAuthMode(mode){{authMode="login";const c=authCopy();document.querySelector("#auth-title").textContent=c.login;document.querySelector("#auth-submit").textContent=c.submit;document.querySelector("#auth-phone").placeholder=c.phone}}
function openAuth(mode="login"){{setAuthMode(mode);document.querySelector("#auth-modal").classList.add("active")}}
function closeAuth(){{document.querySelector("#auth-modal").classList.remove("active")}}
function requireCreatorAuth(action,meta={{}}){{if(creatorUser)return false;pendingAuthAction=typeof action==="function"?action:null;track("auth_required",meta);openAuth("login");return true}}
async function loadAccountState(){{if(!creatorUser)return null;try{{const r=await fetch(`/api/me/state?_=${{Date.now()}}`);const d=await r.json();if(r.status===401){{creatorUser=null;localStorage.removeItem(authKey);return null}}if(!r.ok)throw new Error(d.error||"state failed");creatorUser=d.account||creatorUser;localStorage.setItem(authKey,JSON.stringify(creatorUser));const state=d.state||{{}};if(state.preferences){{answers=state.preferences;localStorage.setItem(profileKey,JSON.stringify(answers))}}if(state.workspace){{workspace=state.workspace;if(!workspace.schedule||Array.isArray(workspace.schedule))workspace.schedule={{}};localStorage.setItem(workspaceKey,JSON.stringify(workspace))}}if(state.profile_ui){{profileUi=state.profile_ui;localStorage.setItem(profileUiKey,JSON.stringify(profileUi))}}submissions=Array.isArray(d.submissions)?d.submissions:submissions;return d}}catch(err){{return null}}}}
let persistTimer=null;function persistAccountState(){{if(!creatorUser)return;if(persistTimer)clearTimeout(persistTimer);persistTimer=setTimeout(async()=>{{try{{await fetch("/api/me/state",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{preferences:answers,workspace,profile_ui:profileUi,language:lang}})}})}}catch(err){{}}}},260)}}
async function handleAuthSubmit(e){{e.preventDefault();const form=new FormData(e.currentTarget);const phone=String(form.get("phone")||"").replace(/\\s+/g,"").trim();if(!phone){{alert(authCopy().missing);return}}try{{const r=await fetch("/api/auth/login",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{phone}})}});const d=await r.json();if(!r.ok)throw new Error(d.error||authCopy().notFound);creatorUser=d.account;localStorage.setItem(authKey,JSON.stringify(creatorUser));track("login",{{method:"phone"}});await loadAccountState();updateCreatorName();closeAuth();if(pendingAuthAction){{const action=pendingAuthAction;pendingAuthAction=null;await action();return}}if(!hasProfile())show("choose");else show("dashboard")}}catch(err){{alert(authCopy().notFound)}}}}
async function logout(){{track("logout",{{}});creatorUser=null;localStorage.removeItem(authKey);await fetch("/api/auth/logout",{{method:"POST",body:"{{}}"}}).catch(()=>null);closeDetail();closeAuth();show("home")}}
function ids(k){{return new Set(workspace[k]||[])}} function statusOf(id){{return ids("planned").has(id)?"planned":ids("finished").has(id)?"finished":ids("rejected").has(id)?"rejected":ids("saved").has(id)?"saved":""}} function entry(id){{return entries.find(e=>e.entry_id===id)}}
function setStatus(id,status){{const prev=statusOf(id);["saved","planned","finished","rejected"].forEach(k=>workspace[k]=(workspace[k]||[]).filter(x=>x!==id)); if(status) workspace[status]=[...(workspace[status]||[]),id]; if(status==="saved"&&prev!=="saved")track("favorite_add",{{script_id:id,previous_status:prev}}); if(!status&&prev==="saved")track("favorite_remove",{{script_id:id}}); if(status==="planned"&&prev!=="planned")track("plan_add",{{script_id:id,previous_status:prev}}); if(status==="finished"&&prev!=="finished")track("mark_finished",{{script_id:id,previous_status:prev}}); saveWorkspace(); renderCurrent()}}
function counts(){{const n=document.querySelector("#count-new");if(n)n.textContent=String(entries.length);const s=document.querySelector("#count-saved");if(s)s.textContent=String((workspace.saved||[]).length);const p=document.querySelector("#count-planned");if(p)p.textContent=String((workspace.planned||[]).length);updateProfileHeader()}}
function applyLang(){{document.documentElement.lang="pt-BR";document.querySelectorAll("[data-t]").forEach(n=>n.textContent=t(n.dataset.t));document.querySelectorAll("[data-html]").forEach(n=>n.innerHTML=t(n.dataset.html));renderQuestion();renderCurrent();counts();setAuthMode(authMode)}}
function show(v){{if(v==="library")v="dashboard";if(["dashboard","saved","all-scripts"].includes(v)&&(!creatorUser||!hasProfile()))v="home";if(v==="choose"&&!creatorUser)v="home";if(v==="choose")step=0;document.querySelectorAll("[data-view]").forEach(x=>x.classList.toggle("active",x.dataset.view===v));if(v==="choose")renderQuestion();if(v==="dashboard")renderDashboard();if(v==="all-scripts")renderAllScripts();if(v==="saved")renderSaved();document.querySelectorAll(".bottom button").forEach(b=>b.classList.toggle("active",b.dataset.go===v||v==="all-scripts"&&b.dataset.go==="dashboard"));track("page_view",{{view:v,has_profile:hasProfile()}});scrollTo({{top:0,behavior:"smooth"}})}}
function renderQuestion(){{normalizeAnswers();if(!stepAvailable(step)){{const first=questions.findIndex((_,i)=>stepAvailable(i));step=first>=0?first:0}}const q=questions[step];const opts=optionsFor(q);const total=stepCountLabel();const pos=currentStepPosition();const multi=isMultipleQuestion(q);document.querySelector("#step-label").textContent=lang==="zh"?`${{t("step")}} ${{pos}} / ${{total}}`:`${{t("step")}} ${{pos}} de ${{total}}`;document.querySelector("#stepper").innerHTML=questions.map((_,i)=>stepAvailable(i)?`<button class="step ${{i===step?"active":""}}" type="button" data-step="${{i}}">${{questions.slice(0,i+1).filter((_,j)=>stepAvailable(j)).length}}</button>`:"").join("");document.querySelector("#question").innerHTML=`<h1>${{esc(label(q))}}</h1>${{multi?`<p class="lead">${{lang==="zh"?"可以多选，Koko 会把这些时长的脚本合并推荐。":"Pode escolher mais de uma duração. A Koko mistura esses roteiros na recomendação."}}</p>`:""}}<div class="options">${{opts.map(o=>`<button class="option ${{answerValues(q.id).includes(o.id)?"selected":""}}" data-answer="${{q.id}}" data-value="${{o.id}}">${{esc(label(o))}}</button>`).join("")}}</div>${{multi?`<button class="primary question-submit" type="button" id="next-step"><span>${{t("finish")}}</span></button>`:""}}`;const next=document.querySelector("#next-step span");if(next)next.textContent=nextAvailableAfter(step)<0?t("finish"):t("next");const prev=document.querySelector("#prev-step");if(prev){{prev.style.visibility=questions.slice(0,step).some((_,i)=>stepAvailable(i))?"visible":"hidden";prev.disabled=prev.style.visibility==="hidden"}}}}
function entryTimestamp(e){{const raw=e.script_date||e.created_at||e.saved_at||"";const n=Date.parse(raw);return Number.isNaN(n)?0:n}}
let entriesLoadedLimit=0;let entriesLoadedKey="";
function recommendationKey(){{return selectedAnswerValues().join("|")}}
async function loadEntries(limit=48,opts={{}}){{const key=recommendationKey();const force=!!opts.force;if(!force&&entries.length&&entriesLoadedKey===key&&entriesLoadedLimit>=limit){{counts();track("recommendation_view",{{source:"memory",limit,selected:selectedAnswerValues(),count:entries.length}});trackScripts("script_impression",entries.slice(0,12),{{surface:"recommendation"}});return entries}}const cacheKey=`koko_reco_cache_v2_${{key}}_${{limit}}`;if(!force){{try{{const cached=JSON.parse(sessionStorage.getItem(cacheKey)||"null");if(cached&&Date.now()-cached.ts<10*60*1000&&Array.isArray(cached.entries)){{entries=cached.entries;entriesLoadedKey=key;entriesLoadedLimit=limit;counts();track("recommendation_view",{{source:"cache",limit,selected:selectedAnswerValues(),count:entries.length}});trackScripts("script_impression",entries.slice(0,12),{{surface:"recommendation"}});return entries}}}}catch(err){{}}}}const p=new URLSearchParams({{limit:String(limit)}});selectedAnswerValues().forEach(v=>p.append("selected",v));const r=await fetch(`/api/creator/recommendations?${{p.toString()}}&_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"load failed");entries=(d.entries||[]).slice();if(!hasMultiDurationSelection())entries.sort((a,b)=>entryTimestamp(b)-entryTimestamp(a));entriesLoadedKey=key;entriesLoadedLimit=limit;try{{sessionStorage.setItem(cacheKey,JSON.stringify({{ts:Date.now(),entries}}))}}catch(err){{}}counts();track("recommendation_view",{{source:"network",limit,selected:selectedAnswerValues(),count:entries.length}});trackScripts("script_impression",entries.slice(0,12),{{surface:"recommendation"}});return entries}}
function chips(){{const lookup=Object.fromEntries(questions.flatMap(q=>q.options.map(o=>[o.id,o])));return selectedAnswerValues().map(id=>lookup[id]).filter(Boolean).map(o=>`<span class="chip">${{esc(label(o))}} ✓</span>`).join("")}}
function dayKey(d){{const y=d.getFullYear();const m=String(d.getMonth()+1).padStart(2,"0");const day=String(d.getDate()).padStart(2,"0");return `${{y}}-${{m}}-${{day}}`}}
function todayKey(){{return dayKey(new Date())}}
function scheduleLabel(key){{const d=new Date(`${{key}}T00:00:00`);if(Number.isNaN(d.getTime()))return key;return lang==="zh"?`${{d.getMonth()+1}}月${{d.getDate()}}日`:`${{String(d.getDate()).padStart(2,"0")}}/${{String(d.getMonth()+1).padStart(2,"0")}}`}}
function scheduleCount(){{return Object.values(workspace.schedule||{{}}).reduce((n,arr)=>n+(Array.isArray(arr)?arr.length:0),0)}}
function saveScheduleItem(id,date){{workspace.schedule=workspace.schedule||{{}};const key=date||todayKey();Object.keys(workspace.schedule).forEach(k=>workspace.schedule[k]=(workspace.schedule[k]||[]).filter(x=>x!==id));workspace.schedule[key]=[...(workspace.schedule[key]||[]),id];scheduleViewDate=key;track("calendar_add",{{script_id:id,date:key}});saveWorkspace()}}
function openScheduleModal(id){{scheduleDraftId=id;scheduleSelectedDate=todayKey();renderCalendar();document.querySelector("#schedule-title").textContent=lang==="zh"?"加入拍摄日历":"Adicionar ao calendário de gravação";document.querySelector("#schedule-note").textContent=lang==="zh"?"选择你准备拍摄这个脚本的日期。":"Escolha o dia em que pretende gravar este roteiro.";document.querySelector(".schedule-actions [data-schedule-close]").textContent=lang==="zh"?"稍后再说":"Mais tarde";document.querySelector("[data-schedule-confirm]").textContent=lang==="zh"?"加入拍摄日历":"Adicionar";document.querySelector("#schedule-modal").classList.add("active")}}
function closeScheduleModal(){{document.querySelector("#schedule-modal").classList.remove("active");scheduleDraftId=""}}
function renderCalendar(){{const root=document.querySelector("#calendar-grid");if(!root)return;const base=scheduleSelectedDate?new Date(`${{scheduleSelectedDate}}T00:00:00`):new Date();const first=new Date(base.getFullYear(),base.getMonth(),1);const start=new Date(first);start.setDate(first.getDate()-first.getDay());const weekdays=lang==="zh"?["日","一","二","三","四","五","六"]:["D","S","T","Q","Q","S","S"];let html=weekdays.map(w=>`<div class="calendar-weekday">${{w}}</div>`).join("");for(let i=0;i<35;i++){{const d=new Date(start);d.setDate(start.getDate()+i);const key=dayKey(d);const muted=d.getMonth()!==base.getMonth();const selected=key===scheduleSelectedDate;html+=`<button class="calendar-day ${{muted?"muted":""}} ${{selected?"selected":""}}" type="button" data-schedule-date="${{key}}">${{d.getDate()}}</button>`}}root.innerHTML=html}}
function scriptImage(e){{return String(e.preview_image_url||e.cover_url||e.thumbnail_url||storyboardDemoUrl||"").trim()}}
function scheduleItem(e,date){{return `<button class="schedule-item" type="button" data-detail="${{esc(e.entry_id)}}"><img src="${{esc(scriptImage(e))}}" loading="lazy" alt=""><div><h3>${{esc(ptTitle(e))}}</h3><p>${{esc(ptTag(e.content_type||""))}} · ${{esc(scheduleLabel(date))}}</p></div></button>`}}
function monthTitle(date){{return lang==="zh"?`${{date.getFullYear()}}年${{date.getMonth()+1}}月`:date.toLocaleDateString("pt-BR",{{month:"long",year:"numeric"}})}}
function shiftScheduleMonth(delta){{const base=new Date(`${{scheduleViewDate||todayKey()}}T00:00:00`);base.setMonth(base.getMonth()+delta);scheduleViewDate=dayKey(base);renderScheduleFeed()}}
function renderShootCalendar(schedule){{const base=scheduleViewDate?new Date(`${{scheduleViewDate}}T00:00:00`):new Date();const first=new Date(base.getFullYear(),base.getMonth(),1);const start=new Date(first);start.setDate(first.getDate()-first.getDay());const weekdays=lang==="zh"?["日","一","二","三","四","五","六"]:["D","S","T","Q","Q","S","S"];let cells=weekdays.map(w=>`<div class="shoot-weekday">${{w}}</div>`).join("");for(let i=0;i<42;i++){{const d=new Date(start);d.setDate(start.getDate()+i);const key=dayKey(d);const count=(schedule[key]||[]).length;const outside=d.getMonth()!==base.getMonth();const active=key===scheduleViewDate;cells+=`<button class="shoot-day ${{outside?"outside":""}} ${{active?"active":""}} ${{count?"has-items":""}}" type="button" data-shoot-date="${{key}}"><span>${{d.getDate()}}</span>${{count?`<i class="shoot-dot">${{count}}</i>`:""}}</button>`}}return `<section class="shoot-calendar-panel"><div class="shoot-calendar-head"><button class="shoot-month-btn" type="button" data-shoot-month="-1">‹</button><div class="shoot-month-title"><b>${{esc(monthTitle(base))}}</b><span>${{lang==="zh"?"选择日期查看待拍脚本":"Toque em um dia para ver tarefas"}}</span></div><button class="shoot-month-btn" type="button" data-shoot-month="1">›</button></div><div class="shoot-grid">${{cells}}</div></section>`}}
function renderScheduleFeed(){{const root=document.querySelector("#saved-feed");const schedule=workspace.schedule||{{}};const selected=scheduleViewDate||todayKey();const planned=(schedule[selected]||[]).map(entry).filter(Boolean);const count=scheduleCount();const agenda=planned.length?planned.map(e=>scheduleItem(e,selected)).join(""):`<section class="shoot-empty"><b>${{count?esc(scheduleLabel(selected)):(lang==="zh"?"还没有加入拍摄日历":"Calendario de gravacao vazio")}}</b>${{count?(lang==="zh"?"这一天还没有待拍脚本，点有橙色标记的日期看看。":"Este dia ainda nao tem roteiro. Toque em um dia marcado em laranja."):(lang==="zh"?"收藏脚本后，可以把它加入某一天的拍摄日历。":"Salve um roteiro e escolha um dia para gravar.")}}</section>`;root.innerHTML=`<section class="shoot-calendar">${{renderShootCalendar(schedule)}}<section class="shoot-agenda"><div class="shoot-agenda-title"><b>${{esc(scheduleLabel(selected))}}</b><span>${{planned.length}} ${{lang==="zh"?"个待拍脚本":"roteiro(s)"}}</span></div>${{agenda}}</section></section>`}}
function dateKey(e){{const raw=String(e.script_date||"");const m=raw.match(/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})/);return m?`${{m[1]}}-${{m[2]}}-${{m[3]}}`:"recent"}}
function dateLabel(key){{if(key==="recent")return lang==="zh"?"近期":"Recentes";const [y,m,d]=key.split("-");return `${{y}}.${{Number(m)}}.${{Number(d)}}`}}
function masonryCard(e,i){{return `<button class="masonry-card" type="button" data-detail="${{esc(e.entry_id)}}"><img src="${{esc(scriptImage(e))}}" loading="lazy" alt=""><span class="masonry-title">${{esc(ptTitle(e))}}</span></button>`}}
function card(e,i){{const s=statusOf(e.entry_id);return `<article class="script card"><div class="thumb"><img src="${{esc(scriptImage(e))}}" loading="lazy" alt=""><span>${{Math.max(78,96-Math.min(i,18))}} match</span></div><div class="body"><h3>${{esc(ptTitle(e))}}</h3><p>${{esc(preferPortugueseText(e.summary))}}</p><div class="tags"><span class="tag">${{esc(ptTag(e.content_type))}}</span>${{durationLabel(e)?`<span class="tag">${{esc(durationLabel(e))}}</span>`:""}}${{s?`<span class="tag">${{esc(ptTag(s))}}</span>`:""}}</div><div class="actions"><button class="open" data-detail="${{esc(e.entry_id)}}">▷ ${{t("open")}}</button><button class="icon" data-status="${{s==="saved"?"":"saved"}}" data-entry="${{esc(e.entry_id)}}">${{s==="saved"?"✓":"♡"}}</button><button class="icon" data-status="planned" data-entry="${{esc(e.entry_id)}}">＋</button></div></div></article>`}}
function renderList(sel,list){{document.querySelector(sel).innerHTML=list.length?list.map(card).join(""):`<section class="state card"><h3>${{t("empty")}}</h3><p class="lead">${{t("emptyText")}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`}}
function masonryHtml(list){{if(!list.length)return `<section class="state card"><h3>${{t("empty")}}</h3><p class="lead">${{t("emptyText")}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`;const groups=new Map();list.forEach(e=>{{const key=dateKey(e);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e)}});const keys=[...groups.keys()].sort((a,b)=>b.localeCompare(a));return keys.map(key=>`<section class="date-group"><div class="date-divider">${{esc(dateLabel(key))}}</div><div class="masonry">${{groups.get(key).map(masonryCard).join("")}}</div></section>`).join("")}}
function renderMasonry(sel,list){{document.querySelector(sel).innerHTML=masonryHtml(list)}}
function featuredCard(e,i){{const s=statusOf(e.entry_id);const liked=ids("saved").has(e.entry_id);const tags=[ptTag(e.content_type),durationLabel(e),...(s?[ptTag(s)]:[])].filter(Boolean);const summary=preferPortugueseText(e.summary)||ptTag(e.content_type)||"";return `<section class="featured-shell"><article class="featured-card"><div class="featured-media"><img src="${{esc(scriptImage(e))}}" loading="eager" alt=""><span class="featured-badge">Recomendado agora</span><span class="featured-score">${{i+1}}/${{entries.length}}</span></div><div class="featured-body"><h2 class="featured-title">${{esc(ptTitle(e))}}</h2><p class="featured-summary">${{esc(summary)}}</p><div class="featured-tags">${{tags.map(x=>`<span class="tag">${{esc(x)}}</span>`).join("")}}</div><div class="featured-actions"><button class="featured-icon" type="button" data-status="${{liked?"":"saved"}}" data-entry="${{esc(e.entry_id)}}" aria-label="${{t("save")}}"><span class="btn-ico">${{liked?"✓":"♡"}}</span><span>${{liked?(lang==="zh"?"已收藏":"Salvo"):(lang==="zh"?"收藏":"Salvar")}}</span></button><button class="primary" type="button" data-detail="${{esc(e.entry_id)}}"><span class="btn-ico">⌕</span><span>${{lang==="zh"?"具体查看":"Ver detalhes"}}</span></button></div><button class="featured-next" type="button" data-feature-next><span class="btn-ico">→</span><span>${{lang==="zh"?"查看下一个脚本":"Ver proximo roteiro"}}</span></button></div></article><button class="view-all-card" type="button" data-go="all-scripts"><b>${{lang==="zh"?"查看全部推荐脚本":"Ver todos os roteiros recomendados"}}</b><span>${{lang==="zh"?"打开双列瀑布流，集中浏览全部脚本。":"Abrir a lista em duas colunas para explorar tudo."}}</span></button></section>`}}
async function ensure(limit=48){{if(!entries.length||entriesLoadedKey!==recommendationKey()||entriesLoadedLimit<limit)await loadEntries(limit)}} async function renderDashboard(){{document.querySelector("#dashboard-feed").innerHTML=`<section class="state card"><h3>Loading...</h3></section>`;try{{await ensure(48);if(!entries.length){{renderMasonry("#dashboard-feed",entries);return}}const featuredIndex=((featuredOffset%entries.length)+entries.length)%entries.length;document.querySelector("#dashboard-feed").innerHTML=featuredCard(entries[featuredIndex],featuredIndex);track("featured_script_view",{{script_id:entries[featuredIndex]?.entry_id,index:featuredIndex}})}}catch(e){{document.querySelector("#dashboard-feed").innerHTML=`<section class="state card"><h3>Erro</h3></section>`}}}}
async function renderAllScripts(){{document.querySelector("#all-title").textContent=lang==="zh"?"全部推荐脚本":"Todos os roteiros";document.querySelector("#all-feed").innerHTML=`<section class="state card"><h3>Loading...</h3></section>`;try{{await ensure(500);renderMasonry("#all-feed",entries);track("all_scripts_view",{{count:entries.length}});trackScripts("script_impression",entries.slice(0,40),{{surface:"all_scripts"}})}}catch(e){{document.querySelector("#all-feed").innerHTML=`<section class="state card"><h3>Erro</h3></section>`}}}}
async function loadSubmissions(){{try{{const r=await fetch(`/api/creator/submissions?_=${{Date.now()}}`);const d=await r.json();submissions=Array.isArray(d.submissions)?d.submissions:[]}}catch(e){{submissions=[]}}return submissions}}
function submissionTime(s){{const raw=String(s.created_at||"");const d=new Date(raw);if(Number.isNaN(d.getTime()))return raw;return lang==="zh"?`回传时间：${{d.toLocaleString("zh-CN",{{hour12:false}})}}`:`Enviado em ${{d.toLocaleString("pt-BR",{{hour12:false}})}}`}}
function submissionCard(s){{const img=esc(s.thumbnail_url||`/api/creator/thumbnail/${{s.entry_id}}.webp`);const title=esc(s.submitted_title||s.script_title||"Video enviado");const url=esc(s.video_url||"#");return `<a class="submission-card" href="${{url}}" target="_blank" rel="noopener"><img class="submission-cover" src="${{img}}" loading="lazy" alt=""><div><h3 class="submission-title">${{title}}</h3><div class="submission-time">${{esc(submissionTime(s))}}</div><div class="submission-url">${{url}}</div></div></a>`}}
function renderSubmissionFeed(){{const root=document.querySelector("#saved-feed");if(!submissions.length){{root.innerHTML=`<section class="state card"><h3>${{lang==="zh"?"这里还没有回传视频":"Nenhum video enviado ainda"}}</h3><p class="lead">${{lang==="zh"?"拍完脚本后，在脚本详情页粘贴视频外链提交。":"Depois de gravar, cole o link do video na pagina do roteiro."}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`;return}}root.innerHTML=`<section class="submission-feed">${{submissions.map(submissionCard).join("")}}</section>`}}
function savedList(k){{return (workspace[k]||[]).map(entry).filter(Boolean)}} function savedTabsHtml(){{return [["finished",t("statusFinished"),submissions.length],["saved",t("statusSaved"),(workspace.saved||[]).length],["schedule",lang==="zh"?"拍摄日历":"Calendario de gravacao",scheduleCount()]].map(([id,txt,count])=>`<button class="${{savedTab===id?"active":""}}" data-tab="${{id}}">${{txt}} ${{count}}</button>`).join("")}} async function renderSaved(){{document.querySelector("#schedule-mini-label").textContent=lang==="zh"?"拍摄日历":"Calendario de gravacao";document.querySelector("#saved-tabs").innerHTML=savedTabsHtml();await Promise.all([ensure(),loadSubmissions()]);updateProfileHeader();document.querySelector("#saved-tabs").innerHTML=savedTabsHtml();if(savedTab==="finished"){{renderSubmissionFeed();return}}if(savedTab==="schedule"){{renderScheduleFeed();return}}renderMasonry("#saved-feed",savedList("saved"))}}
function renderCurrent(){{const v=document.querySelector(".view.active")?.dataset.view;if(v==="dashboard")renderDashboard();if(v==="all-scripts")renderAllScripts();if(v==="saved")renderSaved()}}
async function fetchScript(id){{let e=entry(id);if(e)return e;const r=await fetch(`/api/creator/scripts/${{encodeURIComponent(id)}}?html=0&_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"load failed");e=d.entry;if(!entries.some(x=>x.entry_id===e.entry_id))entries.unshift(e);else entries=entries.map(x=>x.entry_id===e.entry_id?{{...x,...e}}:x);return e}}
async function fetchScriptHtml(id){{const r=await fetch(`/api/creator/script-html/${{encodeURIComponent(id)}}?_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"html failed");entries=entries.map(x=>x.entry_id===id?{{...x,script_html:d.script_html||""}}:x);return d.script_html||""}}
function shareUrl(id){{return `${{location.origin}}/script/${{id}}`}}
async function copyText(text){{try{{if(navigator.clipboard){{await navigator.clipboard.writeText(text);return true}}}}catch(err){{}}try{{const ta=document.createElement("textarea");ta.value=text;ta.setAttribute("readonly","");ta.style.position="fixed";ta.style.top="0";ta.style.left="-9999px";document.body.appendChild(ta);ta.focus();ta.select();ta.setSelectionRange(0,ta.value.length);const ok=document.execCommand("copy");ta.remove();return ok}}catch(err){{return false}}}}
function showShareLink(id,copied){{const url=shareUrl(id);const box=document.querySelector("#share-output");if(box){{box.classList.add("active");box.innerHTML=`<b>${{copied?(lang==="zh"?"已复制分享链接":"Link copiado"):(lang==="zh"?"分享链接":"Link de compartilhamento")}}</b><a href="${{esc(url)}}" target="_blank" rel="noopener">${{esc(url)}}</a>`;if(!copied){{const link=box.querySelector("a");const range=document.createRange();range.selectNodeContents(link);const sel=window.getSelection();sel.removeAllRanges();sel.addRange(range)}}}}}}
function coverImage(e){{return scriptImage(e)}}
function storyboardImage(e){{return String(e.storyboard_image_url||e.storyboard_url||scriptImage(e)||"").trim()}}
function detailCover(e){{return `<div class="detail-cover"><img src="${{esc(coverImage(e))}}" loading="eager" alt="Cover"></div>`}}
function videoPreview(e){{const url=esc(e.video_url);const img=esc(e.thumbnail_url);return `<section class="video-section"><h3 class="video-section-title">${{lang==="zh"?"看看其他人做的：":"Veja como outros criadores fizeram:"}}<span>${{lang==="zh"?"参考视频":"Referencia"}}</span></h3><div class="video-box" data-video-box="${{esc(e.entry_id)}}" data-video-src="${{url}}"><img src="${{img}}" alt="video preview"><div class="video-fallback">${{url ? (lang==="zh"?"视频预览加载中":"Carregando preview") : ""}}</div></div></section>`}}
async function fetchVideoSource(id){{const r=await fetch(`/api/creator/video-source/${{encodeURIComponent(id)}}?_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"video failed");return d.video_source_url||""}}
function hydrateVideo(e){{if(!e.video_url)return;setTimeout(async()=>{{const box=document.querySelector(`[data-video-box="${{e.entry_id}}"]`);if(!box||box.querySelector("video")||box.querySelector("iframe"))return;try{{const source=await fetchVideoSource(e.entry_id);if(source){{box.innerHTML=`<video src="${{esc(source)}}" poster="${{esc(e.thumbnail_url)}}" controls playsinline preload="metadata"></video>`;return}}}}catch(err){{}}box.innerHTML=`<iframe src="${{esc(e.video_url)}}" title="video preview" loading="lazy" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" sandbox="allow-scripts allow-same-origin allow-popups allow-presentation"></iframe><div class="video-fallback">${{lang==="zh"?"如果平台禁止内嵌播放，这里可能只显示空白。":"Se a plataforma bloquear embed, o preview pode aparecer em branco."}}</div>`}},350)}}
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
function scriptTableRows(segs,storyboard){{const grid=storyboardGrid(segs);return segs.map((s,i)=>{{const sx=i%grid.cols,sy=Math.floor(i/grid.cols);const frame=storyboard?`<img src="${{esc(storyboard)}}" alt="Storyboard frame">`:"";return `<article class="script-shot-card"><div class="script-shot-time">Tempo · ${{esc(s.time||"")}}</div><div class="script-shot-body"><div class="script-shot-visual"><div class="script-shot-image" style="--cols:${{grid.cols}};--rows:${{grid.rows}};--sx:${{sx}};--sy:${{sy}}">${{frame}}</div></div><div class="script-shot-info"><div class="script-shot-box"><b>Ações</b><p>${{esc(s.action||"")}}</p></div><div class="script-shot-box"><b>Diálogos</b><p>${{esc(s.dialogue||"")}}</p></div></div></div></article>`}}).join("")}}
function insightSection(title,cards){{cards=uniqueCards(cards);if(!cards.length)return "";return `<section class="insight-section"><h3>${{esc(title)}}</h3><div class="insight-cards">${{cards.map(c=>`<article><b>${{esc(c.title)}}</b><p>${{esc(c.body)}}</p></article>`).join("")}}</div></section>`}}
function cleanScriptHtml(raw,e){{const d=extractScriptData(raw,e);const fallbackPointCards=d.points.map((x,i)=>({{title:i===0?"Ponto-chave":"Ponto-chave "+(i+1),body:x}}));const fallbackAdaptCards=d.adaptable.map((x,i)=>({{title:i===0?"Plano de substituição":"Plano "+(i+1),body:x}}));const brief=[{{label:"Video original",value:d.original}},{{label:"Conteúdo principal",value:d.main}}].filter(x=>x.value);const segs=d.segments.slice(0,9);const storyboard=storyboardImage(e);return `<article class="script-html"><div class="clean-script"><section class="brief-list">${{brief.map(x=>`<div class="brief-card"><b>${{esc(x.label)}}</b><p>${{esc(x.value)}}</p></div>`).join("")}}</section>${{insightSection("Pontos-chave",d.pointCards.length?d.pointCards:fallbackPointCards)}}${{insightSection("Planos de substituição",d.adaptableCards.length?d.adaptableCards:fallbackAdaptCards)}}${{segs.length?`<section class="script-table-card"><div class="script-table-title">Tabela do roteiro</div><div class="script-shot-list">${{scriptTableRows(segs,storyboard)}}</div></section>`:""}}</div></article>`}}
function renderScriptSlot(html,e){{return html?cleanScriptHtml(html,e):`<article class="script-html"><div class="clean-script"><div class="brief-card"><b>Conteúdo principal</b><p>${{esc(preferPortugueseText(e.summary)||"")}}</p></div></div></article>`}}
function renderDetail(e){{const s=statusOf(e.entry_id);const liked=ids("saved").has(e.entry_id);document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><div class="detail-content">${{detailCover(e)}}<h2 class="detail-title">${{esc(ptTitle(e))}}</h2><div class="tags"><span class="tag">${{esc(ptTag(e.content_type))}}</span>${{durationLabel(e)?`<span class="tag">${{esc(durationLabel(e))}}</span>`:""}}${{s?`<span class="tag">${{esc(ptTag(s))}}</span>`:""}}</div><div class="share-box" id="share-output"></div><div id="script-html-slot">${{e.script_html?renderScriptSlot(e.script_html,e):scriptLoading()}}</div>${{videoPreview(e)}}<section class="submit"><b>${{t("submitTitle")}}</b><p class="lead">${{t("submitHint")}}</p><input type="url" data-submit-url="${{esc(e.entry_id)}}" placeholder="${{t("submitPlaceholder")}}"><button class="primary" data-submit="${{esc(e.entry_id)}}">${{t("submitButton")}}</button><div id="submit-status-${{esc(e.entry_id)}}"></div></section><div class="social-actions"><button class="social-btn" type="button" data-status="${{liked?"":"saved"}}" data-entry="${{esc(e.entry_id)}}" aria-label="${{t("save")}}">♡<span>${{liked?(lang==="zh"?"已收藏":"Salvo"):(lang==="zh"?"收藏":"Salvar")}}</span></button><button class="social-btn" type="button" data-copy-share="${{esc(e.entry_id)}}" aria-label="${{lang==="zh"?"复制分享链接":"Copiar link"}}">↗<span>${{lang==="zh"?"分享":"Compartilhar"}}</span></button></div></div>`}}
function loadDetailHtml(e){{if(e.script_html)return;setTimeout(async()=>{{try{{const html=await fetchScriptHtml(e.entry_id);track("script_html_loaded",{{script_id:e.entry_id,ok:true}});const slot=document.querySelector("#script-html-slot");if(slot)slot.innerHTML=renderScriptSlot(html,e)}}catch(err){{track("script_html_loaded",{{script_id:e.entry_id,ok:false,error:String(err.message||err)}});const slot=document.querySelector("#script-html-slot");if(slot)slot.innerHTML=renderScriptSlot("",{{...e,summary:e.summary||err.message}})}}}},300)}}
async function openDetail(id){{track("script_detail_view",{{script_id:id}});const modal=document.querySelector("#modal");modal.classList.add("active");const local=entry(id);if(local){{renderDetail(local);hydrateVideo(local);loadDetailHtml(local);return}}document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><section class="state card"><h3>${{lang==="zh"?"正在加载脚本..." :"Carregando roteiro..."}}</h3></section>`;try{{const e=await fetchScript(id);renderDetail(e);hydrateVideo(e);loadDetailHtml(e)}}catch(err){{document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><section class="state card"><h3>${{lang==="zh"?"脚本加载失败":"Falha ao carregar"}}</h3><p>${{esc(err.message)}}</p></section>`}}}}
async function submitVideo(id){{const input=document.querySelector(`[data-submit-url="${{id}}"]`);const status=document.querySelector(`#submit-status-${{id}}`);const video_url=String(input?.value||"").trim();if(!video_url){{status.textContent=t("submitError");return}}status.textContent=lang==="zh"?"提交中...":"Enviando...";try{{const r=await fetch("/api/creator/submissions",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{entry_id:id,video_url,creator_id:creatorUser?.account_id||creatorUser?.phone||"creator"}})}});const d=await r.json().catch(()=>({{}}));if(!r.ok)throw new Error();track("submission_create",{{script_id:id,video_url,submission_id:d.submission?.submission_id||""}});status.textContent=t("submitOk");await loadSubmissions();setStatus(id,"finished");savedTab="finished"}}catch(e){{status.textContent=t("submitError")}}}}
function closeDetail(){{document.querySelectorAll("#modal video").forEach(v=>{{try{{v.pause();v.removeAttribute("src");v.load()}}catch(e){{}}}});document.querySelector("#modal").classList.remove("active");document.querySelector("#detail").innerHTML="";if(/^\/script\/[0-9a-f]{{32}}$/.test(location.pathname)){{history.replaceState({{}},"","/creator-portal");show(creatorUser&&hasProfile()?"dashboard":"home")}}}}
function handleProfileImage(kind,file){{if(!file||!file.type.startsWith("image/"))return;const reader=new FileReader();reader.onload=()=>{{profileUi[kind]=String(reader.result||"");saveProfileUi();updateProfileImages()}};reader.readAsDataURL(file)}}
document.addEventListener("click",async e=>{{if(e.target.closest("[data-logout]")){{logout();return}}if(e.target.closest("[data-feature-next]")){{featuredOffset++;track("featured_next",{{offset:featuredOffset}});renderDashboard();return}}const upload=e.target.closest("[data-upload-trigger]");if(upload){{document.querySelector(`#profile-${{upload.dataset.uploadTrigger}}-input`)?.click();return}}const jump=e.target.closest("[data-tab-jump]");if(jump){{savedTab=jump.dataset.tabJump;show("saved");return}}const authOpen=e.target.closest("[data-auth-open]");if(authOpen){{openAuth(authOpen.dataset.authOpen||"login");return}}if(e.target.closest("[data-auth-close]")){{closeAuth();return}}const authToggle=e.target.closest("[data-auth-toggle]");if(authToggle){{setAuthMode(authMode==="register"?"login":"register");return}}const reselect=e.target.closest("[data-reselect]");if(reselect){{show("choose");return}}const stepNav=e.target.closest("[data-step]");if(stepNav){{step=Number(stepNav.dataset.step)||0;track("preference_step_jump",{{step}});renderQuestion();return}}if(e.target.closest("#prev-step")){{track("preference_step_prev",{{step}});goStep(-1);return}}const tab=e.target.closest("[data-tab]");if(tab){{savedTab=tab.dataset.tab;renderSaved();return}}const shootMonth=e.target.closest("[data-shoot-month]");if(shootMonth){{shiftScheduleMonth(Number(shootMonth.dataset.shootMonth)||0);return}}const shootDate=e.target.closest("[data-shoot-date]");if(shootDate){{scheduleViewDate=shootDate.dataset.shootDate;renderScheduleFeed();return}}const d=e.target.closest("[data-detail]");if(d){{openDetail(d.dataset.detail);return}}if(e.target.closest("[data-close]")||e.target.id==="modal"){{closeDetail();return}}const copy=e.target.closest("[data-copy-share]");if(copy){{const id=copy.dataset.copyShare;const ok=await copyText(shareUrl(id));track("share_copy",{{script_id:id,ok}});showShareLink(id,ok);const label=copy.querySelector("span");if(label)label.textContent=ok?(lang==="zh"?"已复制":"Copiado"):(lang==="zh"?"复制失败，请手动复制":"Copie manualmente");return}}const scrollSubmit=e.target.closest("[data-submit-scroll]");if(scrollSubmit){{document.querySelector(`[data-submit-url="${{scrollSubmit.dataset.submitScroll}}"]`)?.scrollIntoView({{behavior:"smooth",block:"center"}});return}}const sub=e.target.closest("[data-submit]");if(sub){{const id=sub.dataset.submit;if(requireCreatorAuth(()=>submitVideo(id),{{action:"submit_video",script_id:id}}))return;submitVideo(id);return}}const videoBox=e.target.closest("[data-video-box]");if(videoBox){{track("original_video_click",{{script_id:videoBox.dataset.videoBox,video_url:videoBox.dataset.videoSrc||""}});return}}const st=e.target.closest("[data-status]");if(st){{const inDetail=!!st.closest("#detail");const id=st.dataset.entry;const status=st.dataset.status;if(status&&requireCreatorAuth(()=>{{setStatus(id,status);if(status==="saved")setTimeout(()=>openScheduleModal(id),80)}},{{action:"set_status",script_id:id,status}}))return;setStatus(id,status);if(inDetail){{const fresh=entry(st.dataset.entry);if(fresh)renderDetail(fresh)}}else{{const label=st.querySelector("span");if(label)label.textContent=t(st.dataset.status==="saved"?"saved":st.dataset.status==="planned"?"plan":"save")}}return}}const go=e.target.closest("[data-go]");if(go){{if(go.dataset.savedTab)savedTab=go.dataset.savedTab;show(go.dataset.go);return}}const ans=e.target.closest("[data-answer]");if(ans){{const q=questions.find(item=>item.id===ans.dataset.answer);if(isMultipleQuestion(q)){{const values=answerValues(q.id);answers[q.id]=values.includes(ans.dataset.value)?values.filter(v=>v!==ans.dataset.value):[...values,ans.dataset.value];normalizeAnswers();saveProfile();track("preference_select",{{question:q.id,value:ans.dataset.value,multiple:true,answers}});renderQuestion();}}else{{answers[ans.dataset.answer]=ans.dataset.value;normalizeAnswers();saveProfile();track("preference_select",{{question:ans.dataset.answer,value:ans.dataset.value,multiple:false,answers}});if(!goStep(1))show("dashboard");}}return}}if(e.target.closest("#next-step")){{normalizeAnswers();saveProfile();track("preference_step_next",{{step,answers}});if(!goStep(1))show("dashboard")}}}});
document.addEventListener("click",e=>{{const dateBtn=e.target.closest("[data-schedule-date]");if(dateBtn){{scheduleSelectedDate=dateBtn.dataset.scheduleDate;renderCalendar();return}}if(e.target.closest("[data-schedule-close]")){{closeScheduleModal();return}}if(e.target.closest("[data-schedule-confirm]")){{if(scheduleDraftId){{saveScheduleItem(scheduleDraftId,scheduleSelectedDate||todayKey());savedTab="schedule";closeScheduleModal();show("saved")}}return}}}});document.addEventListener("click",e=>{{const st=e.target.closest("[data-status]");if(st&&st.dataset.status==="saved"&&creatorUser){{const id=st.dataset.entry;setTimeout(()=>openScheduleModal(id),80)}}}});
document.querySelector("#auth-form").addEventListener("submit",handleAuthSubmit);
document.querySelector("#profile-avatar-input")?.addEventListener("change",e=>handleProfileImage("avatar",e.target.files?.[0]));
document.querySelector("#profile-cover-input")?.addEventListener("change",e=>handleProfileImage("cover",e.target.files?.[0]));
async function bootstrap(){{if(creatorUser)await loadAccountState();applyLang();setAuthMode("login");show(forceLanding?"home":initialScriptId?"dashboard":creatorUser&&hasProfile()?"dashboard":"home");if(initialScriptId){{track("script_share_open",{{script_id:initialScriptId,source:"direct_link"}});openDetail(initialScriptId)}}}}bootstrap();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "KokoCreator/1.0"

    def send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_html(self, body: str) -> None:
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
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
            self.send_html(page_html())
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
            entry_id = parsed.path.rsplit("/", 1)[-1]
            if re.fullmatch(r"[0-9a-f]{32}", entry_id):
                try:
                    save_creator_event({"event": "script_share_request", "script_id": entry_id, "path": parsed.path}, self.headers, self.client_address)
                except Exception:
                    pass
            self.send_html(page_html())
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
            self.send_json({"entry_id": entry_id, "video_source_url": video_source_url(entry), "video_url": abs_url(entry.get("video_url"), "")})
            return
        if parsed.path == "/api/admin/analytics":
            if not self.require_admin():
                return
            q = urllib.parse.parse_qs(parsed.query)
            try:
                days = int((q.get("days") or ["14"])[0] or "14")
            except Exception:
                days = 14
            self.send_json(build_creator_analytics(days))
            return
        if parsed.path == "/api/admin/submissions":
            if not self.require_admin():
                return
            submissions = read_json_file(SUBMISSIONS_FILE, [])
            if not isinstance(submissions, list):
                submissions = []
            enriched = enrich_submission_records(submissions)
            unmatched_count = sum(1 for item in enriched if item.get("creator_unmatched"))
            self.send_json({"ok": True, "submissions": enriched, "total": len(enriched), "unmatched_count": unmatched_count})
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
            accounts = [public_account(item, include_state=True) for item in load_accounts()]
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
            submissions = read_json_file(SUBMISSIONS_FILE, [])
            if not isinstance(submissions, list):
                submissions = []
            if account:
                account_id = str(account.get("account_id") or "")
                submissions = [item for item in submissions if isinstance(item, dict) and str(item.get("creator_id") or "") == account_id]
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
            url = thumbnail_url(entry)
            if url:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=15) as response:
                        raw = response.read()
                        content_type = response.headers.get("Content-Type") or "image/webp"
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                except Exception:
                    pass
            raw = placeholder_svg(entry)
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
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
        if parsed.path == "/api/auth/login":
            try:
                payload = self.read_body()
            except Exception:
                payload = {}
            account_id = normalize_account_key(str(payload.get("phone") or payload.get("account_id") or ""))
            account = find_account(account_id)
            if not account or str(account.get("status") or "active") != "active":
                self.send_json({"error": "Telefone não encontrado"}, status=404)
                return
            accounts = load_accounts()
            for idx, item in enumerate(accounts):
                if str(item.get("account_id") or "") == account_id:
                    item["last_login_at"] = now_iso()
                    accounts[idx] = item
                    account = item
                    save_accounts(accounts)
                    break
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
            self.send_header("Set-Cookie", f"{CREATOR_AUTH_COOKIE}={urllib.parse.quote(make_account_token(account_id))}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax")
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path == "/api/auth/logout":
            self.send_json({"ok": True}, headers=[("Set-Cookie", f"{CREATOR_AUTH_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")])
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
        if parsed.path == "/api/creator/events":
            try:
                event = save_creator_event(self.read_body(), self.headers, self.client_address)
                self.send_json({"ok": True, "event_id": event.get("event_id")}, status=201)
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
                if account:
                    payload["creator_id"] = str(account.get("account_id") or "")
                submission = save_submission(payload)
                try:
                    save_creator_event({
                        "event": "submission_create",
                        "script_id": submission.get("entry_id") or payload.get("entry_id"),
                        "creator_id": submission.get("creator_id") or payload.get("creator_id"),
                        "meta": {"video_url": submission.get("video_url"), "submission_id": submission.get("submission_id")},
                    }, self.headers, self.client_address)
                except Exception:
                    pass
                self.send_json({"ok": True, "submission": submission}, status=201)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/creator/sync-library":
            self.send_json(sync_library(True))
            return
        self.send_error(404)

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/favicon.svg", "/favicon.ico", "/brand/kwai-favicon.svg"}:
            self.send_favicon(head_only=True)
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
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
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    sync_library(False)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(json.dumps({"port": PORT, "data_root": str(DATA_ROOT)}, ensure_ascii=False), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
