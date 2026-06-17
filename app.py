#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import http.client
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
LIBRARY_FILE = DATA_ROOT / "creator_online_library.json"
SUBMISSIONS_FILE = DATA_ROOT / "creator_submissions.json"
CREATORS_FILE = DATA_ROOT / "creator_profiles.json"
THUMB_CACHE_FILE = DATA_ROOT / "creator_thumbnail_cache.json"
VIDEO_SOURCE_CACHE_FILE = DATA_ROOT / "creator_video_source_cache.json"
SCRIPT_HTML_CACHE_DIR = DATA_ROOT / "creator_script_html_cache"
SYNC_META_FILE = DATA_ROOT / "creator_sync_meta.json"
OVERRIDES_FILE = DATA_ROOT / "creator_script_overrides.json"
SOURCE_URL = os.environ.get("CREATOR_LIBRARY_SOURCE_URL", "https://koko-kwai-coach.onrender.com/api/library")
SYNC_INTERVAL_SEC = int(os.environ.get("CREATOR_LIBRARY_SYNC_INTERVAL_SEC", "86400"))
ADMIN_PASSWORD = os.environ.get("KOKO_CREATOR_ADMIN_PASSWORD", "koko")
ADMIN_COOKIE = "koko_creator_admin"

DEFAULT_CONTENT_TYPE = "待分类"


QUESTIONS = [
    {
        "id": "people",
        "pt": "Quantas pessoas aparecem normalmente?",
        "zh": "你们通常几个人拍？",
        "options": [
            {"id": "solo", "pt": "Só eu", "zh": "我一个人拍", "types": ["骗子", "偷奸耍滑", "整蛊"], "keywords": ["假装", "反应", "秘密", "发现", "装病", "偷懒"]},
            {"id": "duo", "pt": "Duas pessoas", "zh": "两个人拍", "types": ["夫妻吵架", "夫妻欺骗", "夫妻算计", "妻管严", "整蛊", "骗子", "赖账"], "keywords": ["夫妻", "妻子", "丈夫", "老公", "老婆", "情侣", "朋友", "同事"]},
            {"id": "group", "pt": "Três ou mais", "zh": "三个人以上", "types": ["夫妻欺骗", "夫妻算计", "骗子", "整蛊", "撬墙角"], "keywords": ["妈妈", "爸爸", "儿子", "女儿", "家庭", "朋友", "多人", "误会"]},
            {"id": "flex", "pt": "Varia bastante", "zh": "不固定", "types": [], "keywords": ["热门", "低成本", "反转", "误会", "发现", "简单"]},
        ],
    },
    {
        "id": "scene",
        "pt": "Qual cena parece mais com seu conteúdo?",
        "zh": "你最常拍哪种关系/场景？",
        "options": [
            {"id": "couple", "pt": "Casal / namorados", "zh": "夫妻/情侣", "types": ["夫妻吵架", "夫妻欺骗", "夫妻算计", "妻管严", "夫妻出轨", "夫妻整蛊"], "keywords": ["夫妻", "妻子", "丈夫", "老公", "老婆", "情侣", "吃醋", "约会"]},
            {"id": "friends", "pt": "Amigos ou colegas", "zh": "朋友/同事", "types": ["整蛊", "骗子", "偷奸耍滑", "撬墙角"], "keywords": ["朋友", "同事", "兄弟", "闺蜜", "套路", "恶作剧"]},
            {"id": "family", "pt": "Família / filhos", "zh": "家庭/亲子", "types": ["夫妻欺骗", "夫妻算计"], "keywords": ["妈妈", "爸爸", "儿子", "女儿", "家庭", "亲戚"]},
            {"id": "service", "pt": "Cliente, chefe ou atendimento", "zh": "顾客/老板/服务", "types": ["赖账", "骗子", "偷奸耍滑", "整蛊"], "keywords": ["老板", "员工", "顾客", "服务", "付款", "结账"]},
            {"id": "unsure_scene", "pt": "Ainda não sei", "zh": "不确定", "types": [], "keywords": ["热门", "反转", "误会", "发现", "日常"]},
        ],
    },
    {
        "id": "humor",
        "pt": "Que tipo de graça você quer?",
        "zh": "你想要哪种笑点？",
        "options": [
            {"id": "banter", "pt": "Discussão e respostas rápidas", "zh": "拌嘴互怼", "types": ["夫妻吵架", "妻管严", "夫妻算计"], "keywords": ["吵架", "争执", "训斥", "反驳", "打脸"]},
            {"id": "twist", "pt": "Segredo e revelação", "zh": "隐瞒反转", "types": ["夫妻欺骗", "骗子", "夫妻算计"], "keywords": ["假装", "隐瞒", "谎称", "秘密", "真相", "发现"]},
            {"id": "prank", "pt": "Pegadinha ou susto", "zh": "整蛊恶搞", "types": ["整蛊", "夫妻整蛊"], "keywords": ["整蛊", "恶作剧", "捉弄", "陷阱", "反应"]},
            {"id": "money", "pt": "Dinheiro ou vantagem", "zh": "钱/占便宜", "types": ["赖账", "骗子", "夫妻算计"], "keywords": ["付款", "欠钱", "逃单", "结账", "便宜"]},
            {"id": "sneaky", "pt": "Preguiça ou esperteza", "zh": "偷懒/偷吃/耍小聪明", "types": ["偷吃东西", "偷奸耍滑"], "keywords": ["偷吃", "偷喝", "偷懒", "装病", "耍小聪明"]},
            {"id": "hot", "pt": "Mostre os populares", "zh": "先看热门", "types": [], "keywords": ["热门", "完整", "反转", "误会", "简单"]},
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
        "thumbnail_url",
        "html_url",
        "zh_html_url",
    ]:
        if key in override:
            item[key] = override.get(key)
    item["creator_published"] = not bool(override.get("hidden") or override.get("deleted"))
    item["creator_override"] = True
    item["creator_override_updated_at"] = override.get("updated_at") or ""
    return item


def content_type_labels() -> list[str]:
    labels = [DEFAULT_CONTENT_TYPE]
    for question in QUESTIONS:
        for option in question.get("options", []):
            for label in option.get("types") or []:
                if label not in labels:
                    labels.append(label)
    for label in [
        "夫妻关系",
        "整蛊恶搞",
        "骗局反转",
        "赖账/金钱冲突",
        "偷吃/偷懒/耍小聪明",
        "热门",
    ]:
        if label not in labels:
            labels.append(label)
    return labels


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


def load_entries_raw() -> list[dict[str, Any]]:
    sync_library(False)
    data = read_json_file(LIBRARY_FILE, [])
    if not data and SEED_LIBRARY_FILE.exists():
        data = read_json_file(SEED_LIBRARY_FILE, [])
    return [entry for entry in data if isinstance(entry, dict)]


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
        entries.append(apply_entry_override(entry, override))
    return entries


def load_admin_entries() -> list[dict[str, Any]]:
    overrides = load_overrides()
    entries: list[dict[str, Any]] = []
    for entry in load_entries_raw():
        entry_id = str(entry.get("entry_id") or "").strip()
        override = overrides.get(entry_id)
        if isinstance(override, dict) and override.get("deleted"):
            continue
        entries.append(apply_entry_override(entry, override))
    return sorted(entries, key=lambda item: str(item.get("saved_at") or item.get("created_at") or ""), reverse=True)


def effective_entries() -> list[dict[str, Any]]:
    entries = [
        entry for entry in load_entries()
        if str(entry.get("title") or "").strip()
        and str(entry.get("whole_video_summary") or "").strip()
        and (entry.get("html_url") or entry.get("zh_html_url") or entry.get("video_url"))
    ]
    return sorted(entries, key=lambda item: str(item.get("saved_at") or item.get("created_at") or ""), reverse=True)


def option_lookup() -> dict[str, dict[str, Any]]:
    return {str(option["id"]): option for question in QUESTIONS for option in question.get("options", [])}


def score_entry(entry: dict[str, Any], selected: list[str], index: int) -> int:
    lookup = option_lookup()
    text = " ".join(str(entry.get(key) or "") for key in ["content_type", "title", "whole_video_summary", "content_type_reasoning"])
    content_type = str(entry.get("content_type") or DEFAULT_CONTENT_TYPE)
    score = 0
    for option_id in selected:
        option = lookup.get(option_id) or {}
        if content_type in set(option.get("types") or []):
            score += 42
        hits = sum(1 for keyword in option.get("keywords") or [] if keyword and str(keyword) in text)
        score += min(24, hits * 6)
    score += 10 if content_type != DEFAULT_CONTENT_TYPE else 0
    score += 8 if entry.get("html_url") or entry.get("zh_html_url") else 0
    score += 4 if entry.get("video_url") else 0
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
    entry_id = str(entry.get("entry_id") or "").strip()
    script_date = str(entry.get("saved_at") or entry.get("created_at") or "").strip()
    return {
        "entry_id": entry_id,
        "title": entry.get("title") or "Roteiro",
        "summary": entry.get("whole_video_summary") or "",
        "content_type": entry.get("content_type") or DEFAULT_CONTENT_TYPE,
        "video_url": abs_url(entry.get("video_url"), ""),
        "html_url": abs_url(entry.get("zh_html_url") or entry.get("html_url")),
        "thumbnail_url": f"/api/creator/thumbnail/{entry_id}.webp" if entry_id else "",
        "script_date": script_date,
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


def script_html_for_entry(entry: dict[str, Any]) -> str:
    entry_id = str(entry.get("entry_id") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
        return ""
    cache_file = SCRIPT_HTML_CACHE_DIR / f"{entry_id}.html"
    if cache_file.exists():
        return cache_file.read_text("utf-8", errors="ignore")
    url = abs_url(entry.get("zh_html_url") or entry.get("html_url"))
    if not url:
        return ""
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
    scored = sorted(((score_entry(entry, selected, idx), entry) for idx, entry in enumerate(effective_entries())), key=lambda pair: pair[0], reverse=True)
    return {"questions": QUESTIONS, "selected": selected, "total": len(scored), "entries": [public_entry(entry, score) for score, entry in scored[:limit]]}


def entry_by_id(entry_id: str) -> dict[str, Any] | None:
    for entry in load_entries():
        if str(entry.get("entry_id") or "") == entry_id:
            return entry
    return None


def admin_entry_by_id(entry_id: str) -> dict[str, Any] | None:
    for entry in load_admin_entries():
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
    submission = {
        "submission_id": uuid4().hex,
        "entry_id": entry_id,
        "script_title": str(entry.get("title") or ""),
        "script_content_type": str(entry.get("content_type") or DEFAULT_CONTENT_TYPE),
        "submitted_title": meta.get("title") or str(entry.get("title") or ""),
        "thumbnail_url": meta.get("image") or fallback_thumb,
        "creator_id": str(payload.get("creator_id") or "local_creator").strip()[:120],
        "video_url": video_url,
        "status": "pending_review",
        "created_at": now_iso(),
    }
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    submissions.insert(0, submission)
    write_json_atomic(SUBMISSIONS_FILE, submissions[:1000])
    return submission


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


def public_admin_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(entry.get("entry_id") or "").strip()
    return {
        "entry_id": entry_id,
        "title": str(entry.get("title") or ""),
        "summary": str(entry.get("whole_video_summary") or ""),
        "content_type": str(entry.get("content_type") or DEFAULT_CONTENT_TYPE),
        "video_url": abs_url(entry.get("video_url"), ""),
        "cover_url": abs_url(entry.get("preview_image_url") or entry.get("thumbnail_url") or ""),
        "thumbnail_url": f"/api/creator/thumbnail/{entry_id}.webp" if entry_id else "",
        "html_url": abs_url(entry.get("html_url")),
        "zh_html_url": abs_url(entry.get("zh_html_url") or entry.get("html_url")),
        "created_at": str(entry.get("created_at") or entry.get("saved_at") or ""),
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


def category_tokens(categories: list[str]) -> set[str]:
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
    return {token for token in tokens if token}


def scripts_for_creator(categories: list[str], limit: int = 80) -> list[dict[str, Any]]:
    tokens = category_tokens(categories)
    scored: list[tuple[int, dict[str, Any]]] = []
    for idx, entry in enumerate(load_entries()):
        public = public_entry(entry, 0)
        text = " ".join(str(entry.get(key) or "") for key in ["content_type", "title", "whole_video_summary", "content_type_reasoning"])
        score = 0
        if not tokens:
            score += 20
        for token in tokens:
            if token and token in text:
                score += 18 if token == str(entry.get("content_type") or "") else 8
        score += max(0, 12 - min(idx, 12))
        if score > 0:
            public["match_score"] = score
            public["share_url"] = f"/script/{public['entry_id']}"
            scored.append((score, public))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


def public_creator_profile(profile: dict[str, Any], include_scripts: bool = True) -> dict[str, Any]:
    categories = [str(item or "").strip() for item in profile.get("categories") or [] if str(item or "").strip()]
    scripts = scripts_for_creator(categories, 80) if include_scripts else []
    submissions = read_json_file(SUBMISSIONS_FILE, [])
    if not isinstance(submissions, list):
        submissions = []
    creator_keys = {str(profile.get("profile_id") or ""), str(profile.get("kwai_id") or "")}
    matched_submissions = [
        item for item in submissions
        if isinstance(item, dict) and str(item.get("creator_id") or "") in creator_keys
    ]
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
    return {
        **profile,
        "categories": categories,
        "matched_scripts": scripts,
        "priority_scripts": scripts[:6],
        "folded_count": max(0, len(scripts) - 6),
        "submissions": matched_submissions or fake_submissions,
    }


def create_or_update_creator_profile(payload: dict[str, Any], profile_id: str | None = None) -> dict[str, Any]:
    categories = payload.get("categories")
    if not isinstance(categories, list):
        categories = [item.strip() for item in str(payload.get("category") or "").split(",") if item.strip()]
    categories = [str(item or "").strip() for item in categories if str(item or "").strip()]
    kwai_url = normalize_kwai_url(str(payload.get("kwai_url") or payload.get("url") or "").strip())
    if not kwai_url:
        raise ValueError("请输入 Kwai 作者主页链接。")
    fetched = fetch_kwai_profile(kwai_url)
    profiles = load_creator_profiles()
    existing_index = -1
    for idx, item in enumerate(profiles):
        if profile_id and str(item.get("profile_id") or "") == profile_id:
            existing_index = idx
            break
        if not profile_id and str(item.get("kwai_url") or "") == kwai_url:
            existing_index = idx
            break
    base = profiles[existing_index] if existing_index >= 0 else {}
    profile = {
        **base,
        **fetched,
        "profile_id": str(base.get("profile_id") or profile_id or uuid4().hex),
        "categories": categories,
        "notes": str(payload.get("notes") or base.get("notes") or "").strip(),
        "updated_at": now_iso(),
        "created_at": str(base.get("created_at") or now_iso()),
    }
    if existing_index >= 0:
        profiles[existing_index] = profile
    else:
        profiles.insert(0, profile)
    save_creator_profiles(profiles)
    return public_creator_profile(profile)


def delete_creator_profile(profile_id: str) -> bool:
    profiles = load_creator_profiles()
    next_profiles = [item for item in profiles if str(item.get("profile_id") or "") != profile_id]
    if len(next_profiles) == len(profiles):
        return False
    save_creator_profiles(next_profiles)
    return True


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
        "html_url": "html_url",
        "zh_html_url": "zh_html_url",
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
    template = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Koko Creator Admin</title><style>
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
    return template.replace("{{", "{").replace("}}", "}").replace("__LABELS_JSON__", labels_json)


def page_html() -> str:
    questions_json = json.dumps(QUESTIONS, ensure_ascii=False)
    profile_override_css = """.profile-hero{min-height:0;margin:-22px -22px 14px;padding:12px 14px 16px;background:linear-gradient(135deg,#32180b,#ff5f00 64%,#ffb36f);overflow:visible}.profile-cover{inset:0;height:132px;border-radius:0;background:radial-gradient(circle at 72% 16%,#ff8a1c,#8a3205 50%,#2a160d);filter:none}.profile-cover:after{background:linear-gradient(180deg,#00000018,#00000042)}.profile-tools{position:relative;top:auto;right:auto;justify-content:flex-end;margin-bottom:44px}.profile-upload{min-height:30px;padding:0 11px;border-color:#ffffff70;background:#ffffff24;font-size:11px;white-space:nowrap}.profile-info{position:relative;margin-top:-12px;padding:14px;border-radius:24px;background:#fffffff2;color:#1f1f1f;box-shadow:0 18px 38px #552d0a24}.profile-row{align-items:center;gap:12px}.profile-avatar{width:78px;height:78px;flex:0 0 78px;border:4px solid #fff;box-shadow:0 10px 24px #552d0a22}.profile-name{margin:0 0 6px;color:#1f1f1f;font-size:25px;text-shadow:none}.profile-bio{color:#69707a;font-size:13px;line-height:1.42}.profile-stats{margin-top:14px;padding:11px 8px;border-radius:18px;background:#fff7f0;border:1px solid #ff5f0018;text-align:center}.profile-stats b{color:#1f1f1f;font-size:19px}.profile-stats span{color:#69707a;font-size:12px;font-weight:800}.profile-prefs{margin-top:12px;gap:7px}.profile-prefs .chip{padding:7px 10px;background:#fff;color:#ff5f00;border-color:#ff5f0045;box-shadow:none;font-size:11px}.profile-card-strip{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0 12px}.profile-mini{min-height:58px;border-radius:18px;background:#fff;border:1px solid #ff5f0016;box-shadow:0 8px 18px #552d0a10;font-size:11px}.profile-mini b{font-size:17px;margin-bottom:2px}.profile-tabs{top:64px;margin:0 -22px 10px;padding:8px 18px}.profile-tabs .tabs button{padding:8px 12px;font-size:12px}#saved-feed .state{margin:0;border-radius:24px;padding:26px 20px}@media(max-width:380px){.profile-upload{padding:0 8px;font-size:10px}.profile-avatar{width:68px;height:68px;flex-basis:68px}.profile-name{font-size:22px}.profile-info{padding:12px}.profile-tabs .tabs button{padding:8px 10px}}"""
    profile_override_css += """.profile-hero{min-height:0!important;margin:-22px -22px 14px!important;padding:12px 14px 16px!important;overflow:visible!important}.profile-tools{position:relative!important;top:auto!important;right:auto!important;margin-bottom:44px!important}.profile-logout{border-color:#ff5f0038!important;background:#fff!important;color:#ff5f00!important}.profile-info{position:relative!important;margin-top:-12px!important;padding:14px!important;border-radius:24px!important;background:#fffffff2!important;color:#1f1f1f!important}.profile-row{align-items:center!important}.profile-avatar{width:78px!important;height:78px!important;flex:0 0 78px!important}.profile-name{color:#1f1f1f!important;font-size:25px!important;text-shadow:none!important}.profile-bio{color:#69707a!important;font-size:13px!important;line-height:1.42!important}.profile-stats{grid-template-columns:repeat(2,1fr)!important;margin-top:14px!important;padding:11px 8px!important;border-radius:18px!important;background:#fff7f0!important;text-align:center!important}.profile-stats b{color:#1f1f1f!important}.profile-stats span{color:#69707a!important}.profile-prefs .chip{background:#fff!important;color:#ff5f00!important;border-color:#ff5f0045!important}.profile-card-strip{grid-template-columns:repeat(3,minmax(0,1fr))!important}.profile-mini{min-height:58px!important}.profile-tabs{padding:8px 18px!important}.submission-feed{display:grid;gap:12px}.submission-card{display:grid;grid-template-columns:112px 1fr;gap:12px;align-items:center;padding:10px;border:1px solid #ff5f0022;border-radius:18px;background:#fff;box-shadow:0 10px 22px #552d0a10;color:#1f1f1f;text-decoration:none}.submission-cover{width:112px;aspect-ratio:9/16;border-radius:14px;object-fit:cover;background:#2a1d16}.submission-title{margin:0;font-size:15px;line-height:1.35;font-weight:900}.submission-time{margin-top:8px;color:#69707a;font-size:12px;font-weight:800}.submission-url{margin-top:7px;color:#ff5f00;font-size:11px;line-height:1.35;word-break:break-all}"""
    profile_override_css += """.featured-shell{display:grid;gap:14px}.featured-card{overflow:hidden;border-radius:30px;background:#fff;border:1px solid #ff5f0026;box-shadow:0 22px 48px #552d0a18}.featured-media{position:relative;min-height:350px;background:#2a1d16;overflow:hidden}.featured-media img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.featured-media:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000018,#00000000 48%,#0000003f)}.featured-badge{position:absolute;left:14px;top:14px;z-index:1;border-radius:999px;padding:8px 12px;background:#fffffff0;color:#ff5f00;font-size:12px;font-weight:950;box-shadow:0 8px 22px #00000022}.featured-score{position:absolute;right:14px;top:14px;z-index:1;border-radius:999px;padding:8px 10px;background:#ff5f00;color:white;font-size:12px;font-weight:950}.featured-body{padding:16px 14px 16px}.featured-title{margin:0 0 10px;font-size:23px;line-height:1.2;font-weight:950;letter-spacing:0}.featured-summary{margin:0 0 13px;color:#69707a;font-size:14px;line-height:1.55;font-weight:750}.featured-tags{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px}.featured-actions{display:grid;grid-template-columns:1fr;gap:10px}.featured-actions .primary,.featured-actions .secondary,.featured-actions .featured-icon{width:100%;min-height:50px}.featured-icon{border:1px solid #ff5f0028;border-radius:999px;background:#fff7f0;color:#ff5f00;font-size:15px;font-weight:950}.featured-next{width:100%;min-height:46px;margin-top:10px;border:0;border-radius:999px;background:#fff7f0;color:#69707a;font-size:13px;font-weight:900}.view-all-card{width:100%;margin-top:14px;padding:15px 16px;border:1px solid #ff5f0028;border-radius:22px;background:#ffffffd8;color:#1f1f1f;text-align:left;box-shadow:0 12px 30px #552d0a10}.view-all-card b{display:block;margin-bottom:4px;color:#ff5f00;font-size:15px}.view-all-card span{color:#69707a;font-size:13px;font-weight:750}.all-title-row{display:flex;align-items:center;gap:10px;margin-bottom:12px}.all-title-row h1{margin:0;font-size:30px;line-height:1.1;flex:1}.back-pill{border:1px solid #ff5f0038;border-radius:999px;min-height:38px;padding:0 12px;background:#fff7f0;color:#ff5f00;font-size:12px;font-weight:900}@media(max-width:380px){.featured-media{min-height:312px}.featured-title{font-size:21px}}"""
    profile_override_css += """.schedule-overlay{position:fixed;inset:0;z-index:90;display:none;align-items:flex-end;background:#1f1f1f66;padding:16px 12px 0}.schedule-overlay.active{display:flex}.schedule-sheet{width:min(100%,480px);max-height:88vh;margin:0 auto;overflow:auto;border-radius:28px 28px 0 0;background:#fffaf5;padding:18px;box-shadow:0 -18px 44px #00000024}.schedule-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.schedule-head h2{margin:0;font-size:23px;line-height:1.15}.schedule-close{border:0;width:38px;height:38px;border-radius:50%;background:#fff0e8;color:#ff5f00;font-weight:950}.calendar-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin:12px 0}.calendar-day{min-height:48px;border:1px solid #ff5f0018;border-radius:14px;background:white;color:#1f1f1f;font-weight:900}.calendar-day.muted{color:#b8b8b8;background:#fffaf7}.calendar-day.selected{background:#ff5f00;color:white;border-color:#ff5f00;box-shadow:0 8px 18px #ff5f0030}.calendar-weekday{display:grid;place-items:center;color:#69707a;font-size:11px;font-weight:900}.schedule-note{margin:0;color:#69707a;font-size:13px;line-height:1.45;font-weight:750}.schedule-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.schedule-actions button{min-height:48px}.schedule-list{display:grid;gap:12px}.schedule-day-card{padding:12px;border:1px solid #ff5f0020;border-radius:20px;background:white;box-shadow:0 10px 22px #552d0a0d}.schedule-day-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;color:#ff5f00;font-size:14px;font-weight:950}.schedule-item{display:grid;grid-template-columns:64px 1fr;gap:10px;align-items:center;padding:8px 0;border-top:1px solid #ff5f0014}.schedule-item:first-of-type{border-top:0}.schedule-item img{width:64px;aspect-ratio:1/1;border-radius:14px;object-fit:cover;background:#2a1d16}.schedule-item h3{margin:0;font-size:14px;line-height:1.3}.schedule-item p{margin:5px 0 0;color:#69707a;font-size:12px;line-height:1.35}.schedule-empty{padding:22px;border-radius:22px;background:white;border:1px solid #ff5f0018}.schedule-empty h3{margin:0 0 8px;font-size:20px}.schedule-empty p{margin:0;color:#69707a;line-height:1.5;font-weight:750}"""
    profile_override_css += """.shoot-calendar{display:grid;gap:14px}.shoot-calendar-panel{border-radius:28px;background:#fff;border:1px solid #ff5f0020;box-shadow:0 16px 34px #552d0a10;padding:14px}.shoot-calendar-head{display:grid;grid-template-columns:42px 1fr 42px;align-items:center;gap:8px;margin-bottom:10px}.shoot-month-btn{width:42px;height:42px;border:0;border-radius:50%;background:#fff0e8;color:#ff5f00;font-size:20px;font-weight:950}.shoot-month-title{text-align:center}.shoot-month-title b{display:block;font-size:20px;line-height:1.15}.shoot-month-title span{display:block;margin-top:3px;color:#69707a;font-size:12px;font-weight:800}.shoot-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}.shoot-weekday{display:grid;place-items:center;height:24px;color:#9a9a9a;font-size:11px;font-weight:900}.shoot-day{position:relative;min-height:54px;border:1px solid transparent;border-radius:16px;background:#fff8f3;color:#1f1f1f;font-size:14px;font-weight:900}.shoot-day.outside{color:#c8c8c8;background:#fffaf8}.shoot-day.active{background:#ff5f00;color:white;border-color:#ff5f00;box-shadow:0 10px 20px #ff5f0030}.shoot-day.has-items{border-color:#ff5f0042;background:#fff3eb}.shoot-day.active.has-items{background:#ff5f00}.shoot-dot{position:absolute;left:50%;bottom:7px;transform:translateX(-50%);min-width:16px;height:16px;border-radius:999px;display:grid;place-items:center;background:#ff5f00;color:white;font-size:9px;line-height:1;font-weight:950}.shoot-day.active .shoot-dot{background:white;color:#ff5f00}.shoot-agenda{display:grid;gap:10px}.shoot-agenda-title{display:flex;align-items:center;justify-content:space-between;padding:0 4px;color:#1f1f1f;font-size:15px;font-weight:950}.shoot-agenda-title span{color:#69707a;font-size:12px;font-weight:850}.shoot-empty{padding:20px;border-radius:22px;background:white;border:1px solid #ff5f0018;color:#69707a;line-height:1.5;font-weight:750}.shoot-empty b{display:block;margin-bottom:7px;color:#1f1f1f;font-size:19px}.schedule-item{border:1px solid #ff5f0018;border-radius:20px;background:white;padding:10px;box-shadow:0 10px 22px #552d0a0d}.schedule-item:first-of-type{border-top:1px solid #ff5f0018}@media(max-width:380px){.shoot-day{min-height:48px;border-radius:14px}.shoot-calendar-panel{padding:12px;border-radius:24px}}"""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Koko</title><style>{profile_override_css}
*{{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}body{{margin:0;background:#fff4ea;color:#1f1f1f}}button,a{{font:inherit}}.phone{{width:min(100%,480px);min-height:100vh;margin:0 auto;padding-bottom:96px;overflow-x:hidden;background:linear-gradient(180deg,#fffaf5,#fff0df 42%,#fff8f2)}}.top{{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;padding:18px 22px 12px;background:rgba(255,252,248,.9);backdrop-filter:blur(16px)}}.brand{{font-size:34px;font-weight:900}}.brand span{{color:#ff5f00;font-size:17px;margin-left:8px}}.lang{{position:fixed;right:max(14px,calc((100vw - 480px)/2 + 14px));bottom:92px;z-index:20;display:flex;gap:4px;padding:5px;border-radius:999px;background:white;box-shadow:0 12px 28px #ff820022}}.lang button{{border:0;border-radius:999px;padding:7px 10px;background:transparent;font-size:12px;font-weight:850;color:#777}}.lang .active{{background:#ff5f00;color:white}}.view{{display:none;padding:22px}}.view.active{{display:block}}.chip,.tag{{display:inline-flex;align-items:center;border:1px solid #ff5f0070;border-radius:999px;padding:8px 12px;color:#ff5f00;background:#ffffff90;font-size:12px;font-weight:850}}.step-label{{display:block;margin:2px 0 0;color:#ff5f00;font-size:13px;font-weight:850}}button.chip{{cursor:pointer;min-height:38px}}button.chip:active{{transform:scale(.98);background:#fff0e8}}.title-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:2px 0 12px}}.title-row h1{{margin:0;font-size:clamp(30px,8vw,46px);flex:1}}.reselect-title{{border:1px solid #ff5f0060;border-radius:999px;min-height:38px;padding:0 12px;background:#fff7f0;color:#ff5f00;font-size:12px;font-weight:900;white-space:nowrap;box-shadow:0 8px 18px #ff5f0018}}h1{{margin:10px 0 12px;font-size:clamp(38px,10vw,56px);line-height:1.08;font-weight:900}}.lead{{margin:0;color:#69707a;font-size:16px;line-height:1.55}}.primary,.open{{border:0;border-radius:999px;min-height:48px;padding:0 16px;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;text-decoration:none;font-weight:900;box-shadow:0 14px 30px #ff5f0040}}.secondary{{border:0;border-radius:999px;min-height:44px;padding:0 16px;background:white;color:#1f1f1f;font-weight:850;box-shadow:0 10px 24px #00000010}}.step-actions{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}}.step-actions button{{min-height:54px}}.cta{{display:grid;gap:12px;margin:18px 0}}.card{{border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a14}}.hero{{min-height:150px;margin:20px -22px 0;position:relative;overflow:hidden}}.mascot{{position:absolute;right:26px;bottom:8px;width:116px;height:116px;border-radius:52% 48% 44% 56%;background:radial-gradient(circle at 35% 22%,#ffbe55,#ff8e24 64%,#f97808)}}.quick{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}}.quick button{{min-height:78px;border:0;border-radius:18px;background:white;font-weight:850}}.quick b{{display:block;color:#ff5f00;font-size:22px}}.stepper{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 24px}}.step{{min-height:58px;border:0;border-radius:18px;background:white;display:grid;place-items:center;color:#777;font-weight:900;cursor:pointer}}.step:active{{transform:scale(.98)}}.step.active{{background:#ff5f00;color:white}}.options,.feed{{display:grid;gap:14px;margin-top:16px}}.option{{min-height:72px;border:1px solid #ff820026;border-radius:18px;background:white;text-align:left;padding:14px;font-weight:850}}.option.selected{{border-color:#ff5f00;color:#ff5f00}}.date-group{{margin-top:16px}}.date-divider{{display:flex;align-items:center;justify-content:center;min-height:34px;border:1px solid rgba(255,95,0,.36);border-radius:999px;background:#fffdf9;color:#1f1f1f;font-size:15px;font-weight:900;box-shadow:0 8px 20px #552d0a0a}}.masonry{{columns:2 150px;column-gap:10px;margin-top:10px}}.masonry-card{{break-inside:avoid;display:block;width:100%;margin:0 0 10px;border:1px solid rgba(255,95,0,.26);border-radius:12px;overflow:hidden;background:white;color:#1f1f1f;text-align:left;box-shadow:0 6px 18px #552d0a10;cursor:pointer}}.masonry-card:active{{transform:scale(.99)}}.masonry-card img{{display:block;width:100%;height:auto;aspect-ratio:3/4;object-fit:cover;background:#2a1d16}}.masonry-card:nth-child(3n+2) img{{aspect-ratio:1/1}}.masonry-card:nth-child(4n+3) img{{aspect-ratio:4/5}}.masonry-title{{display:block;padding:9px 10px 11px;font-size:14px;line-height:1.34;font-weight:850;white-space:normal;overflow:visible;word-break:break-word}}.script{{display:grid;grid-template-columns:116px 1fr;gap:13px;padding:14px;min-height:168px}}.thumb{{position:relative;overflow:hidden;border-radius:16px;min-height:142px;background:#2a1d16;color:white;padding:10px;font-size:12px;font-weight:900}}.thumb img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.thumb:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000010,#000000aa)}}.thumb span{{position:relative;z-index:1;background:#9e490ce0;border-radius:9px;padding:6px 8px}}.body{{min-width:0;display:flex;flex-direction:column;gap:8px}}.body h3{{margin:0;font-size:18px;line-height:1.22;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.body p{{margin:0;color:#69707a;font-size:13px;line-height:1.42;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}.tags{{display:flex;gap:6px;flex-wrap:wrap}}.tag{{padding:5px 8px;background:#fff0e8;font-size:11px}}.actions{{display:grid;grid-template-columns:1fr 38px 38px;gap:8px;margin-top:auto}}.icon{{border:0;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#fff0e8;color:#ff5f00;font-weight:900}}.tabs{{display:flex;gap:8px;overflow:auto;padding:4px 0 12px}}.tabs button{{border:1px solid #ff5f0038;border-radius:999px;padding:9px 13px;background:white;color:#777;font-size:12px;font-weight:850}}.tabs .active{{background:#ff5f00;color:white}}.bottom{{position:fixed;left:50%;bottom:0;transform:translateX(-50%);z-index:18;width:min(100%,480px);display:grid;grid-template-columns:repeat(2,1fr);gap:2px;padding:10px 14px;background:#fffffff0;border-radius:24px 24px 0 0;box-shadow:0 -14px 34px #00000014}}.bottom button{{border:0;background:transparent;min-height:54px;color:#777;font-size:12px;font-weight:750}}.bottom .active{{color:#ff5f00}}.modal{{position:fixed;inset:0;z-index:50;display:none;align-items:flex-end;background:#1f1f1f55;padding:18px 18px 0}}.modal.active{{display:flex}}.sheet{{width:min(100%,480px);max-height:88vh;overflow:auto;margin:0 auto;border-radius:28px 28px 0 0;background:#fffaf5;padding:18px}}.sheet-img{{height:220px;border-radius:20px;overflow:hidden;background:#2a1d16}}.sheet-img img{{width:100%;height:100%;object-fit:cover}}.submit{{display:grid;gap:10px;margin:14px 0;padding:14px;border-radius:18px;background:#fff0e8}}.submit input{{min-height:46px;border:1px solid #ff5f0038;border-radius:14px;padding:0 12px}}.state{{padding:18px}}@media(max-width:380px){{.view{{padding:18px}}h1{{font-size:36px}}.script{{grid-template-columns:104px 1fr}}}}
.modal{{padding:10px 10px 0}}.sheet{{height:96vh;max-height:96vh;border-radius:24px 24px 0 0;padding:12px 12px 24px}}.detail-top{{position:sticky;top:0;z-index:2;display:flex;justify-content:flex-end;padding:2px 0 8px;background:#fffaf5cc;backdrop-filter:blur(12px)}}.detail-cover{{position:relative;width:100%;aspect-ratio:4/5;border-radius:22px;overflow:hidden;background:#2a1d16;margin:0 0 14px;box-shadow:0 18px 38px #552d0a1c}}.detail-cover img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.detail-cover:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000008,#00000000 48%,#0000003f)}}.video-section{{margin:16px 0 14px}}.video-section-title{{display:flex;align-items:center;justify-content:space-between;margin:0 0 8px;color:#1f1f1f;font-size:15px;font-weight:950}}.video-section-title span{{color:#ff5f00;font-size:12px}}.video-box{{position:relative;width:100%;height:min(78vh,760px);aspect-ratio:9/16;border-radius:18px;overflow:hidden;background:#111;margin-bottom:14px}}.video-box iframe,.video-box img,.video-box video{{position:absolute;inset:0;width:100%;height:100%;border:0;object-fit:contain;background:#111}}.video-fallback{{position:absolute;inset:auto 12px 12px;z-index:1;border-radius:14px;padding:10px;background:#00000099;color:white;font-size:12px;line-height:1.4}}.detail-title{{margin:8px 0 10px;font-size:25px;line-height:1.18;font-weight:900}}.social-actions{{display:flex;gap:10px;margin:14px 0 10px;padding:10px 0;border-top:1px solid rgba(255,95,0,.12);border-bottom:1px solid rgba(255,95,0,.12)}}.social-btn{{border:1px solid rgba(255,95,0,.26);border-radius:999px;min-width:48px;height:48px;padding:0 15px;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:white;color:#ff5f00;font-size:22px;font-weight:900;box-shadow:0 8px 20px #552d0a10}}.social-btn span{{font-size:13px;color:#1f1f1f}}.share-box{{display:none;margin:0 0 12px;padding:12px;border:1px solid rgba(255,95,0,.22);border-radius:16px;background:#fff7f0;color:#69707a;font-size:12px;line-height:1.45}}.share-box.active{{display:block}}.share-box b{{display:block;margin-bottom:6px;color:#1f1f1f;font-size:13px}}.share-box a{{display:block;color:#ff5f00;font-weight:850;word-break:break-all}}.script-html{{margin-top:12px;padding:14px;border-radius:18px;background:white;border:1px solid rgba(255,95,0,.14);overflow:hidden}}.script-loading{{margin-top:12px;padding:18px;border-radius:18px;background:white;border:1px solid rgba(255,95,0,.14);color:#69707a}}.script-loading b{{display:block;margin-bottom:8px;color:#1f1f1f;font-size:16px}}.script-progress{{position:relative;height:6px;margin-top:12px;overflow:hidden;border-radius:999px;background:#ffe4d2}}.script-progress:after{{content:"";position:absolute;inset:0 auto 0 0;width:42%;border-radius:999px;background:linear-gradient(90deg,#ff7a18,#ff5200);animation:scriptLoad 1.1s ease-in-out infinite}}@keyframes scriptLoad{{0%{{transform:translateX(-105%)}}100%{{transform:translateX(245%)}}}}.script-html *{{max-width:100%}}.script-html h1{{font-size:24px;line-height:1.18;margin:0 0 10px}}.script-html h2{{font-size:19px;line-height:1.25;margin:18px 0 10px}}.script-html h3{{font-size:16px;line-height:1.3;margin:14px 0 8px}}.script-html p,.script-html li,.script-html td,.script-html th{{font-size:14px;line-height:1.7;word-break:break-word}}.script-html img,.script-html video{{height:auto;border-radius:12px}}.script-html table{{display:block;width:100%;overflow-x:auto;border-collapse:collapse;white-space:normal}}.script-html th,.script-html td{{min-width:120px;border:1px solid #ffe0cc;padding:8px;vertical-align:top}}.script-html .wrap,.script-html .card{{max-width:100%;padding:0;box-shadow:none;background:transparent}}
.landing{{padding:22px;background:linear-gradient(180deg,#fffaf5,#fff0df 42%,#fff8f2)}}.landing .hero{{min-height:238px;margin:18px -22px 0;position:relative;overflow:hidden}}.landing .cta{{grid-template-columns:1fr;gap:10px;margin:20px 0 10px}}.landing-register{{border:0;border-radius:999px;min-height:50px;padding:0 16px;background:white;color:#1f1f1f;font-weight:900;box-shadow:0 10px 24px #00000010}}.landing-section{{margin-top:28px}}.landing-section h2{{font-size:25px;line-height:1.15;margin:0 0 14px;font-weight:950}}.preview-strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0;padding:12px;border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a14}}.preview-card{{min-height:162px;border-radius:16px;background:linear-gradient(180deg,#4b2b19,#17110e);position:relative;overflow:hidden;color:white;padding:10px;display:flex;align-items:flex-end;font-weight:900;font-size:13px;line-height:1.25;background-size:cover;background-position:center}}.preview-card:before{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000008,#000000c0)}}.preview-card span{{position:relative;z-index:1;text-shadow:0 2px 8px #00000070}}.preview-card:nth-child(1){{background-image:url('/api/creator/thumbnail/bbab84126a3840eea25fe1a83f0c3012')}}.preview-card:nth-child(2){{background-image:url('/api/creator/thumbnail/08a75198fe5d4b2bb31817f09c2ea88f')}}.preview-card:nth-child(3){{background-image:url('/api/creator/thumbnail/d3efff85be124453b3a75c331ee6fb65')}}.info-panel{{min-height:104px;border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a10;display:grid;place-items:center;padding:20px;text-align:center;color:#69707a;font-size:15px;line-height:1.55;font-weight:750}}.feature-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 24px}}.feature{{min-height:94px;border-radius:18px;background:white;border:1px solid #ff82001a;display:grid;place-items:center;text-align:center;padding:10px;font-size:13px;font-weight:850;color:#1f1f1f}}.feature b{{display:block;color:#ff5f00;font-size:24px;margin-bottom:5px}}.author-cloud{{position:relative;height:250px;margin:14px 0;overflow:hidden;border-radius:28px;background:radial-gradient(circle at 50% 50%,#fff7ee 0,#ffe8d8 44%,#fff4ea 100%)}}.author-dot{{position:absolute;border-radius:50%;background:#fff center/cover no-repeat;box-shadow:0 18px 34px #ff5f0028;border:6px solid #fffaf5;animation:floatAvatar 12s ease-in-out infinite alternate;will-change:transform}}.author-dot:nth-child(1){{width:96px;height:96px;left:36%;top:8px;background-image:url('https://i.pravatar.cc/240?img=47');animation-duration:13s}}.author-dot:nth-child(2){{width:70px;height:70px;left:8%;top:82px;background-image:url('https://i.pravatar.cc/200?img=32');animation-duration:11s;animation-delay:-3s}}.author-dot:nth-child(3){{width:106px;height:106px;right:8%;top:86px;background-image:url('https://i.pravatar.cc/240?img=12');animation-duration:15s;animation-delay:-6s}}.author-dot:nth-child(4){{width:116px;height:116px;left:30%;bottom:10px;background-image:url('https://i.pravatar.cc/240?img=5');animation-duration:14s;animation-delay:-2s}}.author-dot:nth-child(5){{width:58px;height:58px;left:68%;top:22px;background-image:url('https://i.pravatar.cc/180?img=21');animation-delay:-5s}}.author-dot:nth-child(6){{width:66px;height:66px;left:2%;bottom:26px;background-image:url('https://i.pravatar.cc/180?img=56');animation-duration:10s;animation-delay:-7s}}.author-dot:nth-child(7){{width:74px;height:74px;right:0;bottom:12px;background-image:url('https://i.pravatar.cc/180?img=15');animation-duration:12s;animation-delay:-4s}}.author-dot:nth-child(8){{width:52px;height:52px;left:20%;top:18px;background-image:url('https://i.pravatar.cc/160?img=36');animation-duration:9s;animation-delay:-8s}}.author-dot:nth-child(9){{width:62px;height:62px;right:30%;bottom:4px;background-image:url('https://i.pravatar.cc/180?img=49');animation-duration:13s;animation-delay:-1s}}.author-dot:nth-child(10){{width:50px;height:50px;right:16%;top:6px;background-image:url('https://i.pravatar.cc/160?img=68');animation-duration:10s;animation-delay:-9s}}@keyframes floatAvatar{{0%{{transform:translate3d(-10px,8px,0) scale(.98)}}50%{{transform:translate3d(14px,-12px,0) scale(1.04)}}100%{{transform:translate3d(-4px,16px,0) scale(1)}}}}.ending-card{{min-height:238px;border-radius:28px;border:1px solid #ff5f0024;background:linear-gradient(135deg,#fff,#ffe3cf);display:grid;place-items:center;text-align:center;font-size:30px;font-weight:950;box-shadow:0 18px 42px #552d0a14;padding:26px}}.ending-card small{{display:block;margin-top:8px;color:#69707a;font-size:15px;font-weight:750;line-height:1.5}}.auth-overlay{{position:fixed;inset:0;z-index:70;display:none;place-items:center;background:linear-gradient(180deg,#fffaf5,#fff0df 60%,#fff7f0);padding:22px}}.auth-overlay.active{{display:grid}}.auth-card{{width:min(100%,390px);min-height:420px;border:1px solid #ff5f0026;border-radius:28px;background:#fffffff2;padding:34px 24px;box-shadow:0 26px 60px #552d0a18}}.auth-card h2{{text-align:center;font-size:34px;margin:0 0 24px;color:#1f1f1f}}.auth-card input{{width:100%;min-height:52px;margin-bottom:12px;border:1px solid #ff5f0028;border-radius:16px;padding:0 16px;font-size:15px;background:#fffaf7;color:#1f1f1f;outline:none}}.auth-card input:focus{{border-color:#ff5f00;box-shadow:0 0 0 4px #ff5f0012}}.auth-meta{{display:flex;align-items:center;justify-content:space-between;margin:8px 0 22px;color:#69707a;font-size:14px}}.auth-submit{{width:100%;min-height:52px;border:0;border-radius:999px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;font-weight:950;box-shadow:0 14px 30px #ff5f0036}}.auth-switch{{margin-top:18px;text-align:center;color:#62666d;font-weight:750}}.auth-switch button,.link-btn{{border:0;background:transparent;color:#ff5f00;font-weight:900}}.auth-close{{position:absolute;top:18px;right:18px;background:white}}.profile-hero{{margin:-22px -22px 16px;position:relative;min-height:290px;overflow:hidden;background:linear-gradient(135deg,#2b211d,#ff6a00);color:white}}.profile-cover{{position:absolute;inset:0;background:linear-gradient(145deg,#2a1d16,#ff6a00 58%,#ffd6ad);background-size:cover;background-position:center;filter:saturate(1.05)}}.profile-cover:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000020,#00000088)}}.profile-tools{{position:absolute;top:14px;right:14px;z-index:2;display:flex;gap:8px}}.profile-upload{{border:1px solid #ffffff60;border-radius:999px;min-height:34px;padding:0 10px;background:#ffffff28;color:white;font-size:12px;font-weight:850;backdrop-filter:blur(10px)}}.profile-info{{position:relative;z-index:1;padding:78px 18px 18px}}.profile-row{{display:flex;gap:14px;align-items:end}}.profile-avatar{{position:relative;width:92px;height:92px;border-radius:50%;border:4px solid white;background:white center/cover no-repeat;box-shadow:0 14px 28px #00000030;overflow:hidden}}.profile-avatar:before{{content:"";position:absolute;inset:0;background:radial-gradient(circle at 35% 25%,#ffc46b,#ff8e24 64%,#f97808)}}.profile-avatar.has-image:before{{display:none}}.profile-name{{margin:0 0 7px;font-size:28px;line-height:1.05;font-weight:950;text-shadow:0 2px 12px #00000035}}.profile-bio{{margin:0;color:#ffffffd8;font-size:13px;font-weight:750}}.profile-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:18px}}.profile-stats b{{display:block;font-size:19px;color:white}}.profile-stats span{{color:#ffffffc8;font-size:12px}}.profile-prefs{{margin-top:16px;display:flex;gap:8px;flex-wrap:wrap}}.profile-prefs .chip{{background:#ffffff22;color:white;border-color:#ffffff55;backdrop-filter:blur(8px)}}.profile-card-strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0 16px}}.profile-mini{{border:0;border-radius:16px;min-height:66px;background:#ffffffcc;color:#1f1f1f;font-size:12px;font-weight:850;box-shadow:0 10px 24px #552d0a10}}.profile-mini b{{display:block;color:#ff5f00;font-size:18px;margin-bottom:3px}}.profile-tabs{{position:sticky;top:62px;z-index:4;margin:0 -22px;padding:8px 22px;background:#fffaf5e8;backdrop-filter:blur(14px);border-bottom:1px solid #ff5f0012}}.profile-tabs .tabs{{padding:0}}.hidden-input{{display:none}}.modal{{align-items:stretch;padding:0;background:#fff;z-index:80}}.modal.active{{display:block}}.sheet{{width:min(100%,480px);height:100vh;max-height:100vh;margin:0 auto;border-radius:0;background:#fff;padding:0;overflow:auto}}.detail-top{{position:sticky;top:0;z-index:5;justify-content:flex-start;padding:10px;background:#ffffffd8}}.video-box{{height:auto;aspect-ratio:4/5;border-radius:0;margin:0;background:#050505}}.video-box iframe,.video-box img,.video-box video{{object-fit:contain}}.detail-content{{padding:12px 14px 90px;background:white}}.detail-title{{font-size:20px;margin:12px 0 8px}}.social-actions{{position:sticky;bottom:0;z-index:6;margin:0 -14px;padding:9px 12px;background:#fffffff2;border-top:1px solid #00000010;border-bottom:0;justify-content:space-around}}.social-btn{{border:0;box-shadow:none;background:white;color:#1f1f1f;font-size:26px;flex-direction:row}}.social-btn span{{font-size:14px;color:#1f1f1f}}.comment-pill{{min-height:42px;border-radius:999px;background:#f4f4f4;padding:0 14px;color:#777;display:flex;align-items:center;min-width:130px}}.bottom{{grid-template-columns:repeat(2,1fr)}}.landing .mascot{{position:absolute;right:-18px;bottom:-22px;width:250px;height:250px;border-radius:0;background:transparent;object-fit:contain;filter:drop-shadow(0 24px 30px #ff5f0036)}}.landing .hero:before{{content:"";position:absolute;right:-64px;bottom:-30px;width:286px;height:146px;border-radius:999px;background:linear-gradient(135deg,#ffd9bf,#ffb98c);opacity:.72}}.landing .hero:after{{content:"✦";position:absolute;right:204px;top:34px;color:#ff9f24;font-size:28px;text-shadow:70px 42px 0 #fff,22px 112px 0 #fff}}</style></head><body><main class="phone"><header class="top"><div class="brand">kwai <span>Koko</span></div><button class="icon" type="button">☰</button></header><div class="lang"><button data-lang="pt">PT</button><button data-lang="zh">中文</button></div>
<section class="view landing" data-view="home"><h1>Encontre roteiros que você consegue gravar</h1><p class="lead">Receba recomendações com base no seu perfil de criação, formatos que combinam com você e roteiros prontos para gravar.</p><div class="hero"><img class="mascot" src="/static/koko-creator-mascot-cutout.png" alt="Koko Creator"></div><div class="cta"><button class="primary" type="button" data-auth-open="register">Criar conta e começar</button><button class="landing-register" type="button" data-auth-open="login">Já tenho conta</button></div><section class="landing-section"><h2>Veja antes de escolher</h2><div class="preview-strip"><div class="preview-card"><span>Preview do roteiro</span></div><div class="preview-card"><span>Referência em vídeo</span></div><div class="preview-card"><span>Estrutura de gravação</span></div></div><div class="info-panel">Em breve este espaço recebe cards reais, regras de campanha, exemplos de criadores e materiais enviados pela equipe.</div></section><section class="landing-section"><div class="feature-row"><div class="feature"><b>1</b>Escolha seu perfil</div><div class="feature"><b>2</b>Veja recomendações</div><div class="feature"><b>3</b>Grave e envie</div></div></section><section class="landing-section"><h2>Criadores parceiros</h2><div class="author-cloud"><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span><span class="author-dot"></span></div><div class="info-panel">Aqui entram fotos, nomes e cases dos criadores parceiros. Por enquanto mantemos o espaço preparado para os materiais finais.</div></section><section class="landing-section ending-card"><div>Pronto para abrir sua biblioteca?<small>Crie sua conta, escolha suas preferências uma vez e volte todos os dias para ver novos roteiros.</small><br><button class="primary" type="button" data-auth-open="register">Registrar agora</button></div></section></section>
<section class="view" data-view="dashboard"><div class="title-row"><h1 data-t="todayTitle">Recomendação de roteiros</h1><button class="reselect-title" type="button" data-reselect="true" data-t="changePrefs">Mudar preferências</button></div><div id="dashboard-feed"></div></section>
<section class="view" data-view="all-scripts"><div class="all-title-row"><button class="back-pill" type="button" data-go="dashboard">←</button><h1 id="all-title">全部推荐脚本</h1></div><div id="all-feed"></div></section>
<section class="view" data-view="choose"><span class="step-label" id="step-label">Etapa 1 de 3</span><div class="stepper" id="stepper"></div><div id="question"></div><div class="step-actions"><button class="secondary" id="prev-step" type="button"><span data-t="prev">上一步</span></button><button class="primary" id="next-step" type="button"><span data-t="next">Próxima etapa</span> →</button></div></section>
<section class="view" data-view="saved"><section class="profile-hero"><div class="profile-cover" id="profile-cover"></div><div class="profile-tools"><button class="profile-upload" type="button" data-upload-trigger="cover" data-t="editCover">Capa</button><button class="profile-upload" type="button" data-upload-trigger="avatar" data-t="editAvatar">Avatar</button><button class="profile-upload profile-logout" type="button" data-logout data-t="logout">Sair</button></div><div class="profile-info"><div class="profile-row"><div class="profile-avatar" id="profile-avatar"></div><div><h1 class="profile-name" id="creator-name">Koko Creator</h1><p class="profile-bio" data-t="profileBio">Biblioteca pessoal de roteiros e gravações.</p></div></div><div class="profile-stats"><div><b id="profile-count-finished">0</b><span data-t="statusFinished">Gravados</span></div><div><b id="profile-count-saved">0</b><span data-t="statusSaved">Salvos</span></div></div><div class="profile-prefs" id="profile-filters"></div></div></section><input class="hidden-input" id="profile-avatar-input" type="file" accept="image/*"><input class="hidden-input" id="profile-cover-input" type="file" accept="image/*"><section class="profile-card-strip"><button class="profile-mini" type="button" data-tab-jump="finished"><b>✓</b><span data-t="statusFinished">Gravados</span></button><button class="profile-mini" type="button" data-tab-jump="saved"><b>♡</b><span data-t="statusSaved">Salvos</span></button><button class="profile-mini" type="button" data-tab-jump="schedule"><b>▦</b><span id="schedule-mini-label">拍摄日历</span></button></section><div class="profile-tabs"><div class="tabs" id="saved-tabs"></div></div><div id="saved-feed"></div></section></main>
<nav class="bottom"><button data-go="dashboard">⌂<br><span data-t="navHome">脚本推荐</span></button><button data-go="saved">☻<br><span data-t="navSaved">Eu</span></button></nav>
<div class="modal" id="modal"><section class="sheet"><div id="detail"></div></section></div>
<div class="auth-overlay" id="auth-modal"><button class="icon auth-close" type="button" data-auth-close>×</button><section class="auth-card"><h2 id="auth-title">Entrar</h2><form id="auth-form"><input name="name" id="auth-name" autocomplete="username" placeholder="Nome de usuário"><input name="password" id="auth-password" type="password" autocomplete="current-password" placeholder="Senha"><input name="invite" id="invite-input" placeholder="Código de convite (opcional)"><div class="auth-meta"><label><input type="checkbox" name="remember"> <span id="auth-remember">Lembrar-me</span></label><button class="link-btn" id="auth-forgot" type="button">Esqueci a senha</button></div><button class="auth-submit" type="submit" id="auth-submit">Entrar</button></form><div class="auth-switch"><span id="auth-switch-text">Ainda não tem conta?</span><button type="button" data-auth-toggle id="auth-toggle">Criar conta</button></div></section></div>
<div class="schedule-overlay" id="schedule-modal"><section class="schedule-sheet"><div class="schedule-head"><h2 id="schedule-title">加入拍摄日历</h2><button class="schedule-close" type="button" data-schedule-close>×</button></div><p class="schedule-note" id="schedule-note">选择你准备拍摄这个脚本的日期。</p><div class="calendar-grid" id="calendar-grid"></div><div class="schedule-actions"><button class="secondary" type="button" data-schedule-close>稍后再说</button><button class="primary" type="button" data-schedule-confirm>加入拍摄日历</button></div></section></div>
<script>
const questions={questions_json}; const profileKey="koko_profile_v1"; const workspaceKey="koko_workspace_v1"; const langKey="koko_lang"; const authKey="koko_creator_user_v1"; const profileUiKey="koko_creator_profile_ui_v1";
let lang=localStorage.getItem(langKey)||"pt"; let step=0; let savedTab="finished"; let featuredOffset=0; let entries=[]; let submissions=[];
let answers=JSON.parse(localStorage.getItem(profileKey)||"null")||{{people:"duo",scene:"couple",humor:"twist"}};
let workspace=JSON.parse(localStorage.getItem(workspaceKey)||"null")||{{saved:[],planned:[],finished:[],rejected:[],schedule:{{}}}};
if(!workspace.schedule||Array.isArray(workspace.schedule))workspace.schedule={{}};
let authMode="login"; let creatorUser=JSON.parse(localStorage.getItem(authKey)||"null");
let profileUi=JSON.parse(localStorage.getItem(profileUiKey)||"null")||{{avatar:"",cover:""}};
let scheduleDraftId=""; let scheduleSelectedDate=""; let scheduleViewDate=todayKey();
const initialScriptId=(()=>{{const path=location.pathname.match(/^\\/script\\/([0-9a-f]{{32}})$/);if(path)return path[1];return new URLSearchParams(location.search).get("script")||""}})();
const forceLanding=new URLSearchParams(location.search).get("landing")==="1";
const I={{pt:{{homePill:"Biblioteca de roteiros",homeTitle:"Encontre roteiros que você consegue gravar",homeLead:"Responda 3 perguntas e veja roteiros para o seu estilo.",start:"Começar agora",seePopular:"Ver populares",todayPill:"Recomendação de roteiros",todayTitle:"Recomendação de roteiros",todayLead:"Abra e escolha um roteiro para ver os detalhes.",quickNew:"roteiros",quickSaved:"salvos",quickPlan:"para gravar",next:"Próxima etapa",prev:"Etapa anterior",finish:"Ver recomendações",libraryPill:"Biblioteca",libraryTitle:"Sua biblioteca recomendada",savedPill:"Meus roteiros",savedTitle:"Sua lista de gravação",navHome:"Roteiros",navLibrary:"Biblioteca",navSaved:"Eu",navPrefs:"Perfil",changePrefs:"Mudar preferências",editCover:"Editar capa",editAvatar:"Editar avatar",logout:"Sair",profileBio:"Biblioteca pessoal de roteiros e gravações.",profileHome:"Início",open:"Abrir",save:"Salvar",plan:"Vou gravar",done:"Gravado",reject:"Não serve",original:"Referencia",details:"Detalhes",submitTitle:"Enviar vídeo gravado",submitHint:"Envie o link do vídeo gravado seguindo este roteiro. Vamos revisar e, se aprovado, ajudar com impulsionamento.",submitPlaceholder:"Cole aqui o link do seu vídeo",submitButton:"Enviar para revisão",submitOk:"Recebido. Vamos revisar seu vídeo.",submitError:"Não foi possível enviar. Confira o link.",empty:"Nada aqui ainda",emptyText:"Salve um roteiro da recomendação para montar sua lista.",statusSaved:"Salvos",statusPlanned:"Vou gravar",statusFinished:"Gravados",statusRejected:"Não servem",step:"Etapa"}},zh:{{homePill:"脚本推荐",homeTitle:"找到你真的能拍的脚本",homeLead:"回答 3 个问题，进入你的推荐脚本页面。",start:"开始选择",seePopular:"先看热门",todayPill:"脚本推荐",todayTitle:"脚本推荐",todayLead:"点开卡片，查看完整脚本和拍摄说明。",quickNew:"推荐脚本",quickSaved:"已收藏",quickPlan:"准备拍",next:"下一步",prev:"上一步",finish:"查看推荐",libraryPill:"脚本库",libraryTitle:"你的推荐脚本库",savedPill:"我的脚本",savedTitle:"你的拍摄清单",navHome:"脚本推荐",navLibrary:"脚本库",navSaved:"我",navPrefs:"偏好",changePrefs:"重新选择偏好",editCover:"编辑封面",editAvatar:"编辑头像",logout:"退出登录",profileBio:"你的脚本收藏和视频回传记录。",profileHome:"主页",open:"打开",save:"收藏",plan:"准备拍",done:"已拍",reject:"不适合",original:"参考视频",details:"完整脚本",submitTitle:"回传拍摄视频",submitHint:"上传按照脚本拍摄的视频，我们会审核后给您投流。",submitPlaceholder:"把你发布后的视频链接粘贴在这里",submitButton:"提交审核",submitOk:"已收到，我们会审核这个视频。",submitError:"提交失败，请检查链接。",empty:"这里还没有脚本",emptyText:"先从脚本推荐里收藏一个脚本。",statusSaved:"收藏",statusPlanned:"准备拍",statusFinished:"已拍",statusRejected:"不适合",step:"第"}}}};
const t=k=>(I[lang]&&I[lang][k])||k; const label=x=>lang==="zh"?x.zh:x.pt; const esc=v=>String(v||"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
function hasProfile(){{return !!localStorage.getItem(profileKey)}} function saveProfile(){{localStorage.setItem(profileKey,JSON.stringify(answers))}} function saveWorkspace(){{localStorage.setItem(workspaceKey,JSON.stringify(workspace)); counts()}} function saveProfileUi(){{localStorage.setItem(profileUiKey,JSON.stringify(profileUi))}}
function updateCreatorName(){{const node=document.querySelector("#creator-name");if(node)node.textContent=creatorUser?.name?creatorUser.name:"Koko Creator"}}
function updateProfileImages(){{const avatar=document.querySelector("#profile-avatar");const cover=document.querySelector("#profile-cover");if(avatar){{avatar.classList.toggle("has-image",!!profileUi.avatar);avatar.style.backgroundImage=profileUi.avatar?`url("${{profileUi.avatar}}")`:""}}if(cover&&profileUi.cover)cover.style.backgroundImage=`url("${{profileUi.cover}}")`}}
function updateProfileHeader(){{updateCreatorName();updateProfileImages();const filters=document.querySelector("#profile-filters");if(filters)filters.innerHTML=chips();const saved=document.querySelector("#profile-count-saved");if(saved)saved.textContent=String((workspace.saved||[]).length);const planned=document.querySelector("#profile-count-planned");if(planned)planned.textContent=String((workspace.planned||[]).length);const finished=document.querySelector("#profile-count-finished");if(finished)finished.textContent=String(submissions.length||0)}}
function authCopy(){{const zh=lang==="zh";return {{login:zh?"登录":"Entrar",register:zh?"注册":"Criar conta",name:zh?"请输入账号":"Nome de usuário",password:zh?"请输入密码":"Senha",invite:zh?"邀请码（选填）":"Código de convite (opcional)",remember:zh?"记住我":"Lembrar-me",forgot:zh?"忘记密码？":"Esqueci a senha",noAccount:zh?"还没有账号？":"Ainda não tem conta?",hasAccount:zh?"已有账号？":"Já tem conta?",missing:zh?"请输入账号和密码":"Preencha usuário e senha"}}}}
function setAuthMode(mode){{authMode=mode;const c=authCopy();const isRegister=mode==="register";document.querySelector("#auth-title").textContent=isRegister?c.register:c.login;document.querySelector("#auth-submit").textContent=isRegister?c.register:c.login;document.querySelector("#auth-switch-text").textContent=isRegister?c.hasAccount:c.noAccount;document.querySelector("#auth-toggle").textContent=isRegister?c.login:c.register;document.querySelector("#auth-name").placeholder=c.name;document.querySelector("#auth-password").placeholder=c.password;document.querySelector("#invite-input").placeholder=c.invite;document.querySelector("#auth-remember").textContent=c.remember;document.querySelector("#auth-forgot").textContent=c.forgot;document.querySelector("#invite-input").style.display=isRegister?"block":"none"}}
function openAuth(mode="login"){{setAuthMode(mode);document.querySelector("#auth-modal").classList.add("active")}}
function closeAuth(){{document.querySelector("#auth-modal").classList.remove("active")}}
function handleAuthSubmit(e){{e.preventDefault();const form=new FormData(e.currentTarget);const name=String(form.get("name")||"").trim();const password=String(form.get("password")||"").trim();if(!name||!password){{alert(authCopy().missing);return}}creatorUser={{name,created_at:new Date().toISOString()}};localStorage.setItem(authKey,JSON.stringify(creatorUser));updateCreatorName();closeAuth();if(!hasProfile())show("choose");else show("dashboard")}}
function logout(){{creatorUser=null;localStorage.removeItem(authKey);closeDetail();closeAuth();show("home")}}
function ids(k){{return new Set(workspace[k]||[])}} function statusOf(id){{return ids("planned").has(id)?"planned":ids("finished").has(id)?"finished":ids("rejected").has(id)?"rejected":ids("saved").has(id)?"saved":""}} function entry(id){{return entries.find(e=>e.entry_id===id)}}
function setStatus(id,status){{["saved","planned","finished","rejected"].forEach(k=>workspace[k]=(workspace[k]||[]).filter(x=>x!==id)); if(status) workspace[status]=[...(workspace[status]||[]),id]; saveWorkspace(); renderCurrent()}}
function counts(){{const n=document.querySelector("#count-new");if(n)n.textContent=String(entries.length);const s=document.querySelector("#count-saved");if(s)s.textContent=String((workspace.saved||[]).length);const p=document.querySelector("#count-planned");if(p)p.textContent=String((workspace.planned||[]).length);updateProfileHeader()}}
function applyLang(){{document.documentElement.lang=lang==="zh"?"zh-CN":"pt-BR";document.querySelectorAll("[data-lang]").forEach(b=>b.classList.toggle("active",b.dataset.lang===lang));document.querySelectorAll("[data-t]").forEach(n=>n.textContent=t(n.dataset.t));document.querySelectorAll("[data-html]").forEach(n=>n.innerHTML=t(n.dataset.html));renderQuestion();renderCurrent();counts();setAuthMode(authMode)}}
function show(v){{if(v==="library")v="dashboard";if(["dashboard","saved","all-scripts"].includes(v)&&(!creatorUser||!hasProfile()))v="home";if(v==="choose"&&!creatorUser)v="home";if(v==="choose")step=0;document.querySelectorAll("[data-view]").forEach(x=>x.classList.toggle("active",x.dataset.view===v));if(v==="choose")renderQuestion();if(v==="dashboard")renderDashboard();if(v==="all-scripts")renderAllScripts();if(v==="saved")renderSaved();document.querySelectorAll(".bottom button").forEach(b=>b.classList.toggle("active",b.dataset.go===v||v==="all-scripts"&&b.dataset.go==="dashboard"));scrollTo({{top:0,behavior:"smooth"}})}}
function renderQuestion(){{const q=questions[step];document.querySelector("#step-label").textContent=lang==="zh"?`${{t("step")}} ${{step+1}} / 3`:`${{t("step")}} ${{step+1}} de 3`;document.querySelector("#stepper").innerHTML=questions.map((_,i)=>`<button class="step ${{i===step?"active":""}}" type="button" data-step="${{i}}">${{i+1}}</button>`).join("");document.querySelector("#question").innerHTML=`<h1>${{esc(label(q))}}</h1><div class="options">${{q.options.map(o=>`<button class="option ${{answers[q.id]===o.id?"selected":""}}" data-answer="${{q.id}}" data-value="${{o.id}}">${{esc(label(o))}}</button>`).join("")}}</div>`;document.querySelector("#next-step span").textContent=step===questions.length-1?t("finish"):t("next");const prev=document.querySelector("#prev-step");if(prev){{prev.style.visibility=step===0?"hidden":"visible";prev.disabled=step===0}}}}
function entryTimestamp(e){{const raw=e.script_date||e.created_at||e.saved_at||"";const n=Date.parse(raw);return Number.isNaN(n)?0:n}}
async function loadEntries(){{const p=new URLSearchParams({{limit:80}});Object.values(answers).forEach(v=>p.append("selected",v));const r=await fetch(`/api/creator/recommendations?${{p.toString()}}&_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"load failed");entries=(d.entries||[]).slice().sort((a,b)=>entryTimestamp(b)-entryTimestamp(a));counts();return entries}}
function chips(){{const lookup=Object.fromEntries(questions.flatMap(q=>q.options.map(o=>[o.id,o])));return Object.values(answers).map(id=>lookup[id]).filter(Boolean).map(o=>`<span class="chip">${{esc(label(o))}} ✓</span>`).join("")}}
function dayKey(d){{const y=d.getFullYear();const m=String(d.getMonth()+1).padStart(2,"0");const day=String(d.getDate()).padStart(2,"0");return `${{y}}-${{m}}-${{day}}`}}
function todayKey(){{return dayKey(new Date())}}
function scheduleLabel(key){{const d=new Date(`${{key}}T00:00:00`);if(Number.isNaN(d.getTime()))return key;return lang==="zh"?`${{d.getMonth()+1}}月${{d.getDate()}}日`:`${{String(d.getDate()).padStart(2,"0")}}/${{String(d.getMonth()+1).padStart(2,"0")}}`}}
function scheduleCount(){{return Object.values(workspace.schedule||{{}}).reduce((n,arr)=>n+(Array.isArray(arr)?arr.length:0),0)}}
function saveScheduleItem(id,date){{workspace.schedule=workspace.schedule||{{}};const key=date||todayKey();Object.keys(workspace.schedule).forEach(k=>workspace.schedule[k]=(workspace.schedule[k]||[]).filter(x=>x!==id));workspace.schedule[key]=[...(workspace.schedule[key]||[]),id];scheduleViewDate=key;saveWorkspace()}}
function openScheduleModal(id){{scheduleDraftId=id;scheduleSelectedDate=todayKey();renderCalendar();document.querySelector("#schedule-title").textContent=lang==="zh"?"加入拍摄日历":"Adicionar ao calendario de gravacao";document.querySelector("#schedule-note").textContent=lang==="zh"?"选择你准备拍摄这个脚本的日期。":"Escolha o dia em que pretende gravar este roteiro.";document.querySelector("[data-schedule-confirm]").textContent=lang==="zh"?"加入拍摄日历":"Adicionar";document.querySelector("#schedule-modal").classList.add("active")}}
function closeScheduleModal(){{document.querySelector("#schedule-modal").classList.remove("active");scheduleDraftId=""}}
function renderCalendar(){{const root=document.querySelector("#calendar-grid");if(!root)return;const base=scheduleSelectedDate?new Date(`${{scheduleSelectedDate}}T00:00:00`):new Date();const first=new Date(base.getFullYear(),base.getMonth(),1);const start=new Date(first);start.setDate(first.getDate()-first.getDay());const weekdays=lang==="zh"?["日","一","二","三","四","五","六"]:["D","S","T","Q","Q","S","S"];let html=weekdays.map(w=>`<div class="calendar-weekday">${{w}}</div>`).join("");for(let i=0;i<35;i++){{const d=new Date(start);d.setDate(start.getDate()+i);const key=dayKey(d);const muted=d.getMonth()!==base.getMonth();const selected=key===scheduleSelectedDate;html+=`<button class="calendar-day ${{muted?"muted":""}} ${{selected?"selected":""}}" type="button" data-schedule-date="${{key}}">${{d.getDate()}}</button>`}}root.innerHTML=html}}
function scheduleItem(e,date){{return `<button class="schedule-item" type="button" data-detail="${{esc(e.entry_id)}}"><img src="${{esc(e.thumbnail_url)}}" loading="lazy" alt=""><div><h3>${{esc(e.title)}}</h3><p>${{esc(e.content_type||"")}} · ${{esc(scheduleLabel(date))}}</p></div></button>`}}
function monthTitle(date){{return lang==="zh"?`${{date.getFullYear()}}年${{date.getMonth()+1}}月`:date.toLocaleDateString("pt-BR",{{month:"long",year:"numeric"}})}}
function shiftScheduleMonth(delta){{const base=new Date(`${{scheduleViewDate||todayKey()}}T00:00:00`);base.setMonth(base.getMonth()+delta);scheduleViewDate=dayKey(base);renderScheduleFeed()}}
function renderShootCalendar(schedule){{const base=scheduleViewDate?new Date(`${{scheduleViewDate}}T00:00:00`):new Date();const first=new Date(base.getFullYear(),base.getMonth(),1);const start=new Date(first);start.setDate(first.getDate()-first.getDay());const weekdays=lang==="zh"?["日","一","二","三","四","五","六"]:["D","S","T","Q","Q","S","S"];let cells=weekdays.map(w=>`<div class="shoot-weekday">${{w}}</div>`).join("");for(let i=0;i<42;i++){{const d=new Date(start);d.setDate(start.getDate()+i);const key=dayKey(d);const count=(schedule[key]||[]).length;const outside=d.getMonth()!==base.getMonth();const active=key===scheduleViewDate;cells+=`<button class="shoot-day ${{outside?"outside":""}} ${{active?"active":""}} ${{count?"has-items":""}}" type="button" data-shoot-date="${{key}}"><span>${{d.getDate()}}</span>${{count?`<i class="shoot-dot">${{count}}</i>`:""}}</button>`}}return `<section class="shoot-calendar-panel"><div class="shoot-calendar-head"><button class="shoot-month-btn" type="button" data-shoot-month="-1">‹</button><div class="shoot-month-title"><b>${{esc(monthTitle(base))}}</b><span>${{lang==="zh"?"选择日期查看待拍脚本":"Toque em um dia para ver tarefas"}}</span></div><button class="shoot-month-btn" type="button" data-shoot-month="1">›</button></div><div class="shoot-grid">${{cells}}</div></section>`}}
function renderScheduleFeed(){{const root=document.querySelector("#saved-feed");const schedule=workspace.schedule||{{}};const selected=scheduleViewDate||todayKey();const planned=(schedule[selected]||[]).map(entry).filter(Boolean);const count=scheduleCount();const agenda=planned.length?planned.map(e=>scheduleItem(e,selected)).join(""):`<section class="shoot-empty"><b>${{count?esc(scheduleLabel(selected)):(lang==="zh"?"还没有加入拍摄日历":"Calendario de gravacao vazio")}}</b>${{count?(lang==="zh"?"这一天还没有待拍脚本，点有橙色标记的日期看看。":"Este dia ainda nao tem roteiro. Toque em um dia marcado em laranja."):(lang==="zh"?"收藏脚本后，可以把它加入某一天的拍摄日历。":"Salve um roteiro e escolha um dia para gravar.")}}</section>`;root.innerHTML=`<section class="shoot-calendar">${{renderShootCalendar(schedule)}}<section class="shoot-agenda"><div class="shoot-agenda-title"><b>${{esc(scheduleLabel(selected))}}</b><span>${{planned.length}} ${{lang==="zh"?"个待拍脚本":"roteiro(s)"}}</span></div>${{agenda}}</section></section>`}}
function dateKey(e){{const raw=String(e.script_date||"");const m=raw.match(/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})/);return m?`${{m[1]}}-${{m[2]}}-${{m[3]}}`:"recent"}}
function dateLabel(key){{if(key==="recent")return lang==="zh"?"近期":"Recentes";const [y,m,d]=key.split("-");return `${{y}}.${{Number(m)}}.${{Number(d)}}`}}
function masonryCard(e,i){{return `<button class="masonry-card" type="button" data-detail="${{esc(e.entry_id)}}"><img src="${{esc(e.thumbnail_url)}}" loading="lazy" alt=""><span class="masonry-title">${{esc(e.title)}}</span></button>`}}
function card(e,i){{const s=statusOf(e.entry_id);return `<article class="script card"><div class="thumb"><img src="${{esc(e.thumbnail_url)}}" loading="lazy" alt=""><span>${{Math.max(78,96-Math.min(i,18))}} match</span></div><div class="body"><h3>${{esc(e.title)}}</h3><p>${{esc(e.summary)}}</p><div class="tags"><span class="tag">${{esc(e.content_type)}}</span><span class="tag">1-3 min</span>${{s?`<span class="tag">${{s}}</span>`:""}}</div><div class="actions"><button class="open" data-detail="${{esc(e.entry_id)}}">▷ ${{t("open")}}</button><button class="icon" data-status="${{s==="saved"?"":"saved"}}" data-entry="${{esc(e.entry_id)}}">${{s==="saved"?"✓":"♡"}}</button><button class="icon" data-status="planned" data-entry="${{esc(e.entry_id)}}">＋</button></div></div></article>`}}
function renderList(sel,list){{document.querySelector(sel).innerHTML=list.length?list.map(card).join(""):`<section class="state card"><h3>${{t("empty")}}</h3><p class="lead">${{t("emptyText")}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`}}
function masonryHtml(list){{if(!list.length)return `<section class="state card"><h3>${{t("empty")}}</h3><p class="lead">${{t("emptyText")}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`;const groups=new Map();list.forEach(e=>{{const key=dateKey(e);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e)}});const keys=[...groups.keys()].sort((a,b)=>b.localeCompare(a));return keys.map(key=>`<section class="date-group"><div class="date-divider">${{esc(dateLabel(key))}}</div><div class="masonry">${{groups.get(key).map(masonryCard).join("")}}</div></section>`).join("")}}
function renderMasonry(sel,list){{document.querySelector(sel).innerHTML=masonryHtml(list)}}
function featuredCard(e,i){{const s=statusOf(e.entry_id);const liked=ids("saved").has(e.entry_id);const tags=[e.content_type,"1-3 min",...(s?[s]:[])].filter(Boolean);const summary=String(e.summary||"").trim();return `<section class="featured-shell"><article class="featured-card"><div class="featured-media"><img src="${{esc(e.thumbnail_url)}}" loading="eager" alt=""><span class="featured-badge">${{lang==="zh"?"按时间推荐":"Recomendado agora"}}</span><span class="featured-score">${{i+1}}/${{entries.length}}</span></div><div class="featured-body"><h2 class="featured-title">${{esc(e.title)}}</h2><p class="featured-summary">${{esc(summary||e.content_type||"")}}</p><div class="featured-tags">${{tags.map(x=>`<span class="tag">${{esc(x)}}</span>`).join("")}}</div><div class="featured-actions"><button class="featured-icon" type="button" data-status="${{liked?"":"saved"}}" data-entry="${{esc(e.entry_id)}}" aria-label="${{t("save")}}">${{liked?(lang==="zh"?"已收藏":"Salvo"):(lang==="zh"?"收藏":"Salvar")}}</button><button class="primary" type="button" data-detail="${{esc(e.entry_id)}}">${{lang==="zh"?"具体查看":"Ver detalhes"}}</button></div><button class="featured-next" type="button" data-feature-next>${{lang==="zh"?"查看下一个脚本":"Ver proximo roteiro"}}</button></div></article><button class="view-all-card" type="button" data-go="all-scripts"><b>${{lang==="zh"?"查看全部推荐脚本":"Ver todos os roteiros recomendados"}}</b><span>${{lang==="zh"?"打开双列瀑布流，集中浏览全部脚本。":"Abrir a lista em duas colunas para explorar tudo."}}</span></button></section>`}}
async function ensure(){{if(!entries.length)await loadEntries()}} async function renderDashboard(){{document.querySelector("#dashboard-feed").innerHTML=`<section class="state card"><h3>Loading...</h3></section>`;try{{await loadEntries();if(!entries.length){{renderMasonry("#dashboard-feed",entries);return}}const featuredIndex=((featuredOffset%entries.length)+entries.length)%entries.length;document.querySelector("#dashboard-feed").innerHTML=featuredCard(entries[featuredIndex],featuredIndex)}}catch(e){{document.querySelector("#dashboard-feed").innerHTML=`<section class="state card"><h3>Erro</h3></section>`}}}}
async function renderAllScripts(){{document.querySelector("#all-title").textContent=lang==="zh"?"全部推荐脚本":"Todos os roteiros";document.querySelector("#all-feed").innerHTML=`<section class="state card"><h3>Loading...</h3></section>`;try{{await ensure();renderMasonry("#all-feed",entries)}}catch(e){{document.querySelector("#all-feed").innerHTML=`<section class="state card"><h3>Erro</h3></section>`}}}}
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
function detailCover(e){{return `<div class="detail-cover"><img src="${{esc(e.thumbnail_url)}}" loading="eager" alt=""></div>`}}
function videoPreview(e){{const url=esc(e.video_url);const img=esc(e.thumbnail_url);return `<section class="video-section"><h3 class="video-section-title">${{lang==="zh"?"看看其他人做的：":"Veja como outros criadores fizeram:"}}<span>${{lang==="zh"?"参考视频":"Referencia"}}</span></h3><div class="video-box" data-video-box="${{esc(e.entry_id)}}" data-video-src="${{url}}"><img src="${{img}}" alt="video preview"><div class="video-fallback">${{url ? (lang==="zh"?"视频预览加载中":"Carregando preview") : ""}}</div></div></section>`}}
async function fetchVideoSource(id){{const r=await fetch(`/api/creator/video-source/${{encodeURIComponent(id)}}?_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"video failed");return d.video_source_url||""}}
function hydrateVideo(e){{if(!e.video_url)return;setTimeout(async()=>{{const box=document.querySelector(`[data-video-box="${{e.entry_id}}"]`);if(!box||box.querySelector("video")||box.querySelector("iframe"))return;try{{const source=await fetchVideoSource(e.entry_id);if(source){{box.innerHTML=`<video src="${{esc(source)}}" poster="${{esc(e.thumbnail_url)}}" controls playsinline preload="metadata"></video>`;return}}}}catch(err){{}}box.innerHTML=`<iframe src="${{esc(e.video_url)}}" title="video preview" loading="lazy" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" sandbox="allow-scripts allow-same-origin allow-popups allow-presentation"></iframe><div class="video-fallback">${{lang==="zh"?"如果平台禁止内嵌播放，这里可能只显示空白。":"Se a plataforma bloquear embed, o preview pode aparecer em branco."}}</div>`}},350)}}
function scriptLoading(){{return `<section class="script-loading"><b>${{lang==="zh"?"脚本加载中请耐心等待":"Roteiro carregando, aguarde um momento"}}</b><span>${{lang==="zh"?"正在整理完整脚本内容，加载完成后会自动显示。":"Estamos preparando o roteiro completo. Ele aparecerá automaticamente."}}</span><div class="script-progress" aria-hidden="true"></div></section>`}}
function renderDetail(e){{const s=statusOf(e.entry_id);const liked=ids("saved").has(e.entry_id);document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><div class="detail-content">${{detailCover(e)}}<h2 class="detail-title">${{esc(e.title)}}</h2><div class="tags"><span class="tag">${{esc(e.content_type)}}</span><span class="tag">1-3 min</span>${{s?`<span class="tag">${{s}}</span>`:""}}</div><div class="share-box" id="share-output"></div><div id="script-html-slot">${{e.script_html?`<article class="script-html">${{e.script_html}}</article>`:scriptLoading()}}</div>${{videoPreview(e)}}<section class="submit"><b>${{t("submitTitle")}}</b><p class="lead">${{t("submitHint")}}</p><input type="url" data-submit-url="${{esc(e.entry_id)}}" placeholder="${{t("submitPlaceholder")}}"><button class="primary" data-submit="${{esc(e.entry_id)}}">${{t("submitButton")}}</button><div id="submit-status-${{esc(e.entry_id)}}"></div></section><div class="social-actions"><button class="social-btn" type="button" data-status="${{liked?"":"saved"}}" data-entry="${{esc(e.entry_id)}}" aria-label="${{t("save")}}">♡<span>${{liked?(lang==="zh"?"已收藏":"Salvo"):(lang==="zh"?"收藏":"Salvar")}}</span></button></div></div>`}}
function loadDetailHtml(e){{if(e.script_html)return;setTimeout(async()=>{{try{{const html=await fetchScriptHtml(e.entry_id);const slot=document.querySelector("#script-html-slot");if(slot)slot.innerHTML=html?`<article class="script-html">${{html}}</article>`:`<article class="script-html"><p>${{esc(e.summary)}}</p></article>`}}catch(err){{const slot=document.querySelector("#script-html-slot");if(slot)slot.innerHTML=`<article class="script-html"><p>${{esc(e.summary||err.message)}}</p></article>`}}}},300)}}
async function openDetail(id){{const modal=document.querySelector("#modal");modal.classList.add("active");const local=entry(id);if(local){{renderDetail(local);hydrateVideo(local);loadDetailHtml(local);return}}document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><section class="state card"><h3>${{lang==="zh"?"正在加载脚本..." :"Carregando roteiro..."}}</h3></section>`;try{{const e=await fetchScript(id);renderDetail(e);hydrateVideo(e);loadDetailHtml(e)}}catch(err){{document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><section class="state card"><h3>${{lang==="zh"?"脚本加载失败":"Falha ao carregar"}}</h3><p>${{esc(err.message)}}</p></section>`}}}}
async function submitVideo(id){{const input=document.querySelector(`[data-submit-url="${{id}}"]`);const status=document.querySelector(`#submit-status-${{id}}`);const video_url=String(input?.value||"").trim();if(!video_url){{status.textContent=t("submitError");return}}status.textContent=lang==="zh"?"提交中...":"Enviando...";try{{const r=await fetch("/api/creator/submissions",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{entry_id:id,video_url,creator_id:"creator"}})}});if(!r.ok)throw new Error();status.textContent=t("submitOk");await loadSubmissions();setStatus(id,"finished");savedTab="finished"}}catch(e){{status.textContent=t("submitError")}}}}
function closeDetail(){{document.querySelectorAll("#modal video").forEach(v=>{{try{{v.pause();v.removeAttribute("src");v.load()}}catch(e){{}}}});document.querySelector("#modal").classList.remove("active");document.querySelector("#detail").innerHTML=""}}
function handleProfileImage(kind,file){{if(!file||!file.type.startsWith("image/"))return;const reader=new FileReader();reader.onload=()=>{{profileUi[kind]=String(reader.result||"");saveProfileUi();updateProfileImages()}};reader.readAsDataURL(file)}}
document.addEventListener("click",async e=>{{const l=e.target.closest("[data-lang]");if(l){{lang=l.dataset.lang;localStorage.setItem(langKey,lang);applyLang();return}}if(e.target.closest("[data-logout]")){{logout();return}}if(e.target.closest("[data-feature-next]")){{featuredOffset++;renderDashboard();return}}const upload=e.target.closest("[data-upload-trigger]");if(upload){{document.querySelector(`#profile-${{upload.dataset.uploadTrigger}}-input`)?.click();return}}const jump=e.target.closest("[data-tab-jump]");if(jump){{savedTab=jump.dataset.tabJump;show("saved");return}}const authOpen=e.target.closest("[data-auth-open]");if(authOpen){{openAuth(authOpen.dataset.authOpen||"login");return}}if(e.target.closest("[data-auth-close]")){{closeAuth();return}}const authToggle=e.target.closest("[data-auth-toggle]");if(authToggle){{setAuthMode(authMode==="register"?"login":"register");return}}const reselect=e.target.closest("[data-reselect]");if(reselect){{show("choose");return}}const stepNav=e.target.closest("[data-step]");if(stepNav){{step=Number(stepNav.dataset.step)||0;renderQuestion();return}}if(e.target.closest("#prev-step")){{if(step>0){{step--;renderQuestion()}}return}}const tab=e.target.closest("[data-tab]");if(tab){{savedTab=tab.dataset.tab;renderSaved();return}}const shootMonth=e.target.closest("[data-shoot-month]");if(shootMonth){{shiftScheduleMonth(Number(shootMonth.dataset.shootMonth)||0);return}}const shootDate=e.target.closest("[data-shoot-date]");if(shootDate){{scheduleViewDate=shootDate.dataset.shootDate;renderScheduleFeed();return}}const d=e.target.closest("[data-detail]");if(d){{openDetail(d.dataset.detail);return}}if(e.target.closest("[data-close]")||e.target.id==="modal"){{closeDetail();return}}const copy=e.target.closest("[data-copy-share]");if(copy){{const id=copy.dataset.copyShare;const ok=await copyText(shareUrl(id));showShareLink(id,ok);const label=copy.querySelector("span");if(label)label.textContent=ok?(lang==="zh"?"已复制":"Copiado"):(lang==="zh"?"复制失败，请手动复制":"Copie manualmente");return}}const scrollSubmit=e.target.closest("[data-submit-scroll]");if(scrollSubmit){{document.querySelector(`[data-submit-url="${{scrollSubmit.dataset.submitScroll}}"]`)?.scrollIntoView({{behavior:"smooth",block:"center"}});return}}const sub=e.target.closest("[data-submit]");if(sub){{submitVideo(sub.dataset.submit);return}}const st=e.target.closest("[data-status]");if(st){{const inDetail=!!st.closest("#detail");setStatus(st.dataset.entry,st.dataset.status);if(inDetail){{const fresh=entry(st.dataset.entry);if(fresh)renderDetail(fresh)}}else{{const label=st.querySelector("span");if(label)label.textContent=t(st.dataset.status==="saved"?"saved":st.dataset.status==="planned"?"plan":"save")}}return}}const go=e.target.closest("[data-go]");if(go){{if(go.dataset.savedTab)savedTab=go.dataset.savedTab;show(go.dataset.go);return}}const ans=e.target.closest("[data-answer]");if(ans){{answers[ans.dataset.answer]=ans.dataset.value;saveProfile();renderQuestion();return}}if(e.target.closest("#next-step")){{if(step<questions.length-1){{step++;renderQuestion()}}else{{saveProfile();show("dashboard")}}}}}});
document.addEventListener("click",e=>{{const dateBtn=e.target.closest("[data-schedule-date]");if(dateBtn){{scheduleSelectedDate=dateBtn.dataset.scheduleDate;renderCalendar();return}}if(e.target.closest("[data-schedule-close]")){{closeScheduleModal();return}}if(e.target.closest("[data-schedule-confirm]")){{if(scheduleDraftId){{saveScheduleItem(scheduleDraftId,scheduleSelectedDate||todayKey());savedTab="schedule";closeScheduleModal();show("saved")}}return}}}});document.addEventListener("click",e=>{{const st=e.target.closest("[data-status]");if(st&&st.dataset.status==="saved"){{const id=st.dataset.entry;setTimeout(()=>openScheduleModal(id),80)}}}});
document.querySelector("#auth-form").addEventListener("submit",handleAuthSubmit);
document.querySelector("#profile-avatar-input")?.addEventListener("change",e=>handleProfileImage("avatar",e.target.files?.[0]));
document.querySelector("#profile-cover-input")?.addEventListener("change",e=>handleProfileImage("cover",e.target.files?.[0]));
applyLang();setAuthMode("login");show(forceLanding?"home":initialScriptId?"dashboard":creatorUser&&hasProfile()?"dashboard":"home");if(initialScriptId)openDetail(initialScriptId);
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
        if parsed.path in {"/", "/creator-portal"}:
            self.send_html(page_html())
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
            search = str((q.get("search") or [""])[0] or "").strip().lower()
            entries = [public_admin_entry(entry) for entry in load_admin_entries()]
            if search:
                entries = [
                    entry for entry in entries
                    if search in " ".join(str(entry.get(key) or "") for key in ["title", "summary", "content_type", "video_url"]).lower()
                ]
            total = len(entries)
            self.send_json({"entries": entries[offset:offset + limit], "total": total, "limit": limit, "offset": offset})
            return
        if parsed.path == "/api/admin/creators":
            if not self.require_admin():
                return
            profiles = [public_creator_profile(item) for item in load_creator_profiles()]
            self.send_json({"creators": profiles, "total": len(profiles), "categories": content_type_labels()})
            return
        creator_match = re.fullmatch(r"/api/admin/creators/([0-9a-f]{32})", parsed.path)
        if creator_match:
            if not self.require_admin():
                return
            profile_id = creator_match.group(1)
            for profile in load_creator_profiles():
                if str(profile.get("profile_id") or "") == profile_id:
                    self.send_json({"creator": public_creator_profile(profile)})
                    return
            self.send_json({"error": "Creator not found."}, status=404)
            return
        if parsed.path == "/api/creator/recommendations":
            q = urllib.parse.parse_qs(parsed.query)
            selected = [str(v) for v in q.get("selected", [])]
            limit = max(1, min(200, int((q.get("limit") or ["80"])[0] or "80")))
            self.send_json(recommendation_payload(selected, limit))
            return
        if parsed.path.startswith("/script/"):
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
        if parsed.path == "/api/creator/submissions":
            self.send_json({"submissions": read_json_file(SUBMISSIONS_FILE, [])})
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
        if parsed.path == "/api/admin/creators":
            if not self.require_admin():
                return
            try:
                self.send_json({"ok": True, "creator": create_or_update_creator_profile(self.read_body())}, status=201)
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
        if parsed.path == "/api/creator/submissions":
            try:
                self.send_json({"ok": True, "submission": save_submission(self.read_body())}, status=201)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if parsed.path == "/api/creator/sync-library":
            self.send_json(sync_library(True))
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
