#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import os
import re
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
SEED_LIBRARY_FILE = BASE / "data" / "creator_online_library.json"
LIBRARY_FILE = DATA_ROOT / "creator_online_library.json"
SUBMISSIONS_FILE = DATA_ROOT / "creator_submissions.json"
THUMB_CACHE_FILE = DATA_ROOT / "creator_thumbnail_cache.json"
VIDEO_SOURCE_CACHE_FILE = DATA_ROOT / "creator_video_source_cache.json"
SCRIPT_HTML_CACHE_DIR = DATA_ROOT / "creator_script_html_cache"
SYNC_META_FILE = DATA_ROOT / "creator_sync_meta.json"
SOURCE_URL = os.environ.get("CREATOR_LIBRARY_SOURCE_URL", "https://koko-kwai-coach.onrender.com/api/library")
SYNC_INTERVAL_SEC = int(os.environ.get("CREATOR_LIBRARY_SYNC_INTERVAL_SEC", "86400"))

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


def fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


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


def load_entries() -> list[dict[str, Any]]:
    sync_library(False)
    data = read_json_file(LIBRARY_FILE, [])
    if not data and SEED_LIBRARY_FILE.exists():
        data = read_json_file(SEED_LIBRARY_FILE, [])
    return [entry for entry in data if isinstance(entry, dict)]


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
    submission = {
        "submission_id": uuid4().hex,
        "entry_id": entry_id,
        "script_title": str(entry.get("title") or ""),
        "script_content_type": str(entry.get("content_type") or DEFAULT_CONTENT_TYPE),
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


def page_html() -> str:
    questions_json = json.dumps(QUESTIONS, ensure_ascii=False)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Koko</title><style>
*{{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}body{{margin:0;background:#fff4ea;color:#1f1f1f}}button,a{{font:inherit}}.phone{{width:min(100%,480px);min-height:100vh;margin:0 auto;padding-bottom:96px;overflow-x:hidden;background:linear-gradient(180deg,#fffaf5,#fff0df 42%,#fff8f2)}}.top{{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;padding:18px 22px 12px;background:rgba(255,252,248,.9);backdrop-filter:blur(16px)}}.brand{{font-size:34px;font-weight:900}}.brand span{{color:#ff5f00;font-size:17px;margin-left:8px}}.lang{{position:fixed;right:max(14px,calc((100vw - 480px)/2 + 14px));bottom:92px;z-index:20;display:flex;gap:4px;padding:5px;border-radius:999px;background:white;box-shadow:0 12px 28px #ff820022}}.lang button{{border:0;border-radius:999px;padding:7px 10px;background:transparent;font-size:12px;font-weight:850;color:#777}}.lang .active{{background:#ff5f00;color:white}}.view{{display:none;padding:22px}}.view.active{{display:block}}.chip,.tag{{display:inline-flex;align-items:center;border:1px solid #ff5f0070;border-radius:999px;padding:8px 12px;color:#ff5f00;background:#ffffff90;font-size:12px;font-weight:850}}.step-label{{display:block;margin:2px 0 0;color:#ff5f00;font-size:13px;font-weight:850}}button.chip{{cursor:pointer;min-height:38px}}button.chip:active{{transform:scale(.98);background:#fff0e8}}.title-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:2px 0 12px}}.title-row h1{{margin:0;font-size:clamp(30px,8vw,46px);flex:1}}.reselect-title{{border:1px solid #ff5f0060;border-radius:999px;min-height:38px;padding:0 12px;background:#fff7f0;color:#ff5f00;font-size:12px;font-weight:900;white-space:nowrap;box-shadow:0 8px 18px #ff5f0018}}h1{{margin:10px 0 12px;font-size:clamp(38px,10vw,56px);line-height:1.08;font-weight:900}}.lead{{margin:0;color:#69707a;font-size:16px;line-height:1.55}}.primary,.open{{border:0;border-radius:999px;min-height:48px;padding:0 16px;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:linear-gradient(90deg,#ff6a00,#ff5200);color:white;text-decoration:none;font-weight:900;box-shadow:0 14px 30px #ff5f0040}}.secondary{{border:0;border-radius:999px;min-height:44px;padding:0 16px;background:white;color:#1f1f1f;font-weight:850;box-shadow:0 10px 24px #00000010}}.step-actions{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}}.step-actions button{{min-height:54px}}.cta{{display:grid;gap:12px;margin:18px 0}}.card{{border-radius:22px;background:#ffffffdd;border:1px solid #ff82001a;box-shadow:0 16px 38px #552d0a14}}.hero{{min-height:150px;margin:20px -22px 0;position:relative;overflow:hidden}}.mascot{{position:absolute;right:26px;bottom:8px;width:116px;height:116px;border-radius:52% 48% 44% 56%;background:radial-gradient(circle at 35% 22%,#ffbe55,#ff8e24 64%,#f97808)}}.quick{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}}.quick button{{min-height:78px;border:0;border-radius:18px;background:white;font-weight:850}}.quick b{{display:block;color:#ff5f00;font-size:22px}}.stepper{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 24px}}.step{{min-height:58px;border:0;border-radius:18px;background:white;display:grid;place-items:center;color:#777;font-weight:900;cursor:pointer}}.step:active{{transform:scale(.98)}}.step.active{{background:#ff5f00;color:white}}.options,.feed{{display:grid;gap:14px;margin-top:16px}}.option{{min-height:72px;border:1px solid #ff820026;border-radius:18px;background:white;text-align:left;padding:14px;font-weight:850}}.option.selected{{border-color:#ff5f00;color:#ff5f00}}.date-group{{margin-top:16px}}.date-divider{{display:flex;align-items:center;justify-content:center;min-height:34px;border:1px solid rgba(255,95,0,.36);border-radius:999px;background:#fffdf9;color:#1f1f1f;font-size:15px;font-weight:900;box-shadow:0 8px 20px #552d0a0a}}.masonry{{columns:2 150px;column-gap:10px;margin-top:10px}}.masonry-card{{break-inside:avoid;display:block;width:100%;margin:0 0 10px;border:1px solid rgba(255,95,0,.26);border-radius:12px;overflow:hidden;background:white;color:#1f1f1f;text-align:left;box-shadow:0 6px 18px #552d0a10;cursor:pointer}}.masonry-card:active{{transform:scale(.99)}}.masonry-card img{{display:block;width:100%;height:auto;aspect-ratio:3/4;object-fit:cover;background:#2a1d16}}.masonry-card:nth-child(3n+2) img{{aspect-ratio:1/1}}.masonry-card:nth-child(4n+3) img{{aspect-ratio:4/5}}.masonry-title{{display:block;padding:9px 10px 11px;font-size:14px;line-height:1.34;font-weight:850;white-space:normal;overflow:visible;word-break:break-word}}.script{{display:grid;grid-template-columns:116px 1fr;gap:13px;padding:14px;min-height:168px}}.thumb{{position:relative;overflow:hidden;border-radius:16px;min-height:142px;background:#2a1d16;color:white;padding:10px;font-size:12px;font-weight:900}}.thumb img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.thumb:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#00000010,#000000aa)}}.thumb span{{position:relative;z-index:1;background:#9e490ce0;border-radius:9px;padding:6px 8px}}.body{{min-width:0;display:flex;flex-direction:column;gap:8px}}.body h3{{margin:0;font-size:18px;line-height:1.22;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.body p{{margin:0;color:#69707a;font-size:13px;line-height:1.42;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}.tags{{display:flex;gap:6px;flex-wrap:wrap}}.tag{{padding:5px 8px;background:#fff0e8;font-size:11px}}.actions{{display:grid;grid-template-columns:1fr 38px 38px;gap:8px;margin-top:auto}}.icon{{border:0;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#fff0e8;color:#ff5f00;font-weight:900}}.tabs{{display:flex;gap:8px;overflow:auto;padding:4px 0 12px}}.tabs button{{border:1px solid #ff5f0038;border-radius:999px;padding:9px 13px;background:white;color:#777;font-size:12px;font-weight:850}}.tabs .active{{background:#ff5f00;color:white}}.bottom{{position:fixed;left:50%;bottom:0;transform:translateX(-50%);z-index:18;width:min(100%,480px);display:grid;grid-template-columns:repeat(2,1fr);gap:2px;padding:10px 14px;background:#fffffff0;border-radius:24px 24px 0 0;box-shadow:0 -14px 34px #00000014}}.bottom button{{border:0;background:transparent;min-height:54px;color:#777;font-size:12px;font-weight:750}}.bottom .active{{color:#ff5f00}}.modal{{position:fixed;inset:0;z-index:50;display:none;align-items:flex-end;background:#1f1f1f55;padding:18px 18px 0}}.modal.active{{display:flex}}.sheet{{width:min(100%,480px);max-height:88vh;overflow:auto;margin:0 auto;border-radius:28px 28px 0 0;background:#fffaf5;padding:18px}}.sheet-img{{height:220px;border-radius:20px;overflow:hidden;background:#2a1d16}}.sheet-img img{{width:100%;height:100%;object-fit:cover}}.submit{{display:grid;gap:10px;margin:14px 0;padding:14px;border-radius:18px;background:#fff0e8}}.submit input{{min-height:46px;border:1px solid #ff5f0038;border-radius:14px;padding:0 12px}}.state{{padding:18px}}@media(max-width:380px){{.view{{padding:18px}}h1{{font-size:36px}}.script{{grid-template-columns:104px 1fr}}}}
.modal{{padding:10px 10px 0}}.sheet{{height:96vh;max-height:96vh;border-radius:24px 24px 0 0;padding:12px 12px 24px}}.detail-top{{position:sticky;top:0;z-index:2;display:flex;justify-content:flex-end;padding:2px 0 8px;background:#fffaf5cc;backdrop-filter:blur(12px)}}.video-box{{position:relative;width:100%;height:min(78vh,760px);aspect-ratio:9/16;border-radius:18px;overflow:hidden;background:#111;margin-bottom:14px}}.video-box iframe,.video-box img,.video-box video{{position:absolute;inset:0;width:100%;height:100%;border:0;object-fit:contain;background:#111}}.video-fallback{{position:absolute;inset:auto 12px 12px;z-index:1;border-radius:14px;padding:10px;background:#00000099;color:white;font-size:12px;line-height:1.4}}.detail-title{{margin:8px 0 10px;font-size:25px;line-height:1.18;font-weight:900}}.social-actions{{display:flex;gap:10px;margin:14px 0 10px;padding:10px 0;border-top:1px solid rgba(255,95,0,.12);border-bottom:1px solid rgba(255,95,0,.12)}}.social-btn{{border:1px solid rgba(255,95,0,.26);border-radius:999px;min-width:48px;height:48px;padding:0 15px;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:white;color:#ff5f00;font-size:22px;font-weight:900;box-shadow:0 8px 20px #552d0a10}}.social-btn span{{font-size:13px;color:#1f1f1f}}.share-box{{display:none;margin:0 0 12px;padding:12px;border:1px solid rgba(255,95,0,.22);border-radius:16px;background:#fff7f0;color:#69707a;font-size:12px;line-height:1.45}}.share-box.active{{display:block}}.share-box b{{display:block;margin-bottom:6px;color:#1f1f1f;font-size:13px}}.share-box a{{display:block;color:#ff5f00;font-weight:850;word-break:break-all}}.script-html{{margin-top:12px;padding:14px;border-radius:18px;background:white;border:1px solid rgba(255,95,0,.14);overflow:hidden}}.script-loading{{margin-top:12px;padding:18px;border-radius:18px;background:white;border:1px solid rgba(255,95,0,.14);color:#69707a}}.script-loading b{{display:block;margin-bottom:8px;color:#1f1f1f;font-size:16px}}.script-progress{{position:relative;height:6px;margin-top:12px;overflow:hidden;border-radius:999px;background:#ffe4d2}}.script-progress:after{{content:"";position:absolute;inset:0 auto 0 0;width:42%;border-radius:999px;background:linear-gradient(90deg,#ff7a18,#ff5200);animation:scriptLoad 1.1s ease-in-out infinite}}@keyframes scriptLoad{{0%{{transform:translateX(-105%)}}100%{{transform:translateX(245%)}}}}.script-html *{{max-width:100%}}.script-html h1{{font-size:24px;line-height:1.18;margin:0 0 10px}}.script-html h2{{font-size:19px;line-height:1.25;margin:18px 0 10px}}.script-html h3{{font-size:16px;line-height:1.3;margin:14px 0 8px}}.script-html p,.script-html li,.script-html td,.script-html th{{font-size:14px;line-height:1.7;word-break:break-word}}.script-html img,.script-html video{{height:auto;border-radius:12px}}.script-html table{{display:block;width:100%;overflow-x:auto;border-collapse:collapse;white-space:normal}}.script-html th,.script-html td{{min-width:120px;border:1px solid #ffe0cc;padding:8px;vertical-align:top}}.script-html .wrap,.script-html .card{{max-width:100%;padding:0;box-shadow:none;background:transparent}}</style></head><body><main class="phone"><header class="top"><div class="brand">kwai <span>Koko</span></div><button class="icon" type="button">☰</button></header><div class="lang"><button data-lang="pt">PT</button><button data-lang="zh">中文</button></div>
<section class="view" data-view="home"><h1 data-html="homeTitle">Encontre roteiros que você consegue gravar</h1><p class="lead" data-t="homeLead">Responda 3 perguntas e veja roteiros para o seu estilo.</p><div class="hero"><div class="mascot"></div></div><div class="cta"><button class="primary" data-go="choose" data-t="start">Começar agora</button></div></section>
<section class="view" data-view="dashboard"><div class="title-row"><h1 data-t="todayTitle">脚本推荐</h1><button class="reselect-title" type="button" data-reselect="true" data-t="changePrefs">重新选择偏好</button></div><p class="lead" data-t="todayLead">Abra e escolha um roteiro para ver os detalhes.</p><div class="tags" id="filters"></div><div id="dashboard-feed"></div></section>
<section class="view" data-view="choose"><span class="step-label" id="step-label">Etapa 1 de 3</span><div class="stepper" id="stepper"></div><div id="question"></div><div class="step-actions"><button class="secondary" id="prev-step" type="button"><span data-t="prev">上一步</span></button><button class="primary" id="next-step" type="button"><span data-t="next">Próxima etapa</span> →</button></div></section>
<section class="view" data-view="saved"><h1 data-t="savedTitle">Sua lista de gravação</h1><div class="tabs" id="saved-tabs"></div><div class="feed" id="saved-feed"></div></section></main>
<nav class="bottom"><button data-go="dashboard">⌂<br><span data-t="navHome">脚本推荐</span></button><button data-go="saved">♡<br><span data-t="navSaved">Salvos</span></button></nav>
<div class="modal" id="modal"><section class="sheet"><div id="detail"></div></section></div>
<script>
const questions={questions_json}; const profileKey="koko_profile_v1"; const workspaceKey="koko_workspace_v1"; const langKey="koko_lang";
let lang=localStorage.getItem(langKey)||"pt"; let step=0; let savedTab="saved"; let entries=[];
let answers=JSON.parse(localStorage.getItem(profileKey)||"null")||{{people:"duo",scene:"couple",humor:"twist"}};
let workspace=JSON.parse(localStorage.getItem(workspaceKey)||"null")||{{saved:[],planned:[],finished:[],rejected:[]}};
const initialScriptId=(()=>{{const path=location.pathname.match(/^\\/script\\/([0-9a-f]{{32}})$/);if(path)return path[1];return new URLSearchParams(location.search).get("script")||""}})();
const I={{pt:{{homePill:"Biblioteca de roteiros",homeTitle:"Encontre roteiros que você consegue gravar",homeLead:"Responda 3 perguntas e veja roteiros para o seu estilo.",start:"Começar agora",seePopular:"Ver populares",todayPill:"Recomendação de roteiros",todayTitle:"Recomendação de roteiros",todayLead:"Abra e escolha um roteiro para ver os detalhes.",quickNew:"roteiros",quickSaved:"salvos",quickPlan:"para gravar",next:"Próxima etapa",prev:"Etapa anterior",finish:"Ver recomendações",libraryPill:"Biblioteca",libraryTitle:"Sua biblioteca recomendada",savedPill:"Meus roteiros",savedTitle:"Sua lista de gravação",navHome:"Roteiros",navLibrary:"Biblioteca",navSaved:"Salvos",navPrefs:"Perfil",changePrefs:"Mudar preferências",open:"Abrir",save:"Salvar",plan:"Vou gravar",done:"Gravado",reject:"Não serve",original:"Vídeo",details:"Detalhes",submitTitle:"Enviar vídeo gravado",submitHint:"Envie o link do vídeo gravado seguindo este roteiro. Vamos revisar e, se aprovado, ajudar com impulsionamento.",submitPlaceholder:"Cole aqui o link do seu vídeo",submitButton:"Enviar para revisão",submitOk:"Recebido. Vamos revisar seu vídeo.",submitError:"Não foi possível enviar. Confira o link.",empty:"Nada aqui ainda",emptyText:"Salve um roteiro da recomendação para montar sua lista.",statusSaved:"Salvos",statusPlanned:"Vou gravar",statusFinished:"Gravados",statusRejected:"Não servem",step:"Etapa"}},zh:{{homePill:"脚本推荐",homeTitle:"找到你真的能拍的脚本",homeLead:"回答 3 个问题，进入你的推荐脚本页面。",start:"开始选择",seePopular:"先看热门",todayPill:"脚本推荐",todayTitle:"脚本推荐",todayLead:"点开卡片，查看完整脚本和拍摄说明。",quickNew:"推荐脚本",quickSaved:"已收藏",quickPlan:"准备拍",next:"下一步",prev:"上一步",finish:"查看推荐",libraryPill:"脚本库",libraryTitle:"你的推荐脚本库",savedPill:"我的脚本",savedTitle:"你的拍摄清单",navHome:"脚本推荐",navLibrary:"脚本库",navSaved:"收藏",navPrefs:"偏好",changePrefs:"重新选择偏好",open:"打开",save:"收藏",plan:"准备拍",done:"已拍",reject:"不适合",original:"原视频",details:"完整脚本",submitTitle:"回传拍摄视频",submitHint:"上传按照脚本拍摄的视频，我们会审核后给您投流。",submitPlaceholder:"把你发布后的视频链接粘贴在这里",submitButton:"提交审核",submitOk:"已收到，我们会审核这个视频。",submitError:"提交失败，请检查链接。",empty:"这里还没有脚本",emptyText:"先从脚本推荐里收藏一个脚本。",statusSaved:"已收藏",statusPlanned:"准备拍",statusFinished:"已拍",statusRejected:"不适合",step:"第"}}}};
const t=k=>(I[lang]&&I[lang][k])||k; const label=x=>lang==="zh"?x.zh:x.pt; const esc=v=>String(v||"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
function hasProfile(){{return !!localStorage.getItem(profileKey)}} function saveProfile(){{localStorage.setItem(profileKey,JSON.stringify(answers))}} function saveWorkspace(){{localStorage.setItem(workspaceKey,JSON.stringify(workspace)); counts()}}
function ids(k){{return new Set(workspace[k]||[])}} function statusOf(id){{return ids("planned").has(id)?"planned":ids("finished").has(id)?"finished":ids("rejected").has(id)?"rejected":ids("saved").has(id)?"saved":""}} function entry(id){{return entries.find(e=>e.entry_id===id)}}
function setStatus(id,status){{["saved","planned","finished","rejected"].forEach(k=>workspace[k]=(workspace[k]||[]).filter(x=>x!==id)); if(status) workspace[status]=[...(workspace[status]||[]),id]; saveWorkspace(); renderCurrent()}}
function counts(){{const n=document.querySelector("#count-new");if(n)n.textContent=String(entries.length);const s=document.querySelector("#count-saved");if(s)s.textContent=String((workspace.saved||[]).length);const p=document.querySelector("#count-planned");if(p)p.textContent=String((workspace.planned||[]).length)}}
function applyLang(){{document.documentElement.lang=lang==="zh"?"zh-CN":"pt-BR";document.querySelectorAll("[data-lang]").forEach(b=>b.classList.toggle("active",b.dataset.lang===lang));document.querySelectorAll("[data-t]").forEach(n=>n.textContent=t(n.dataset.t));document.querySelectorAll("[data-html]").forEach(n=>n.innerHTML=t(n.dataset.html));renderQuestion();renderCurrent();counts()}}
function show(v){{if(v==="library")v="dashboard";if(["dashboard","saved"].includes(v)&&!hasProfile())v="home";if(v==="choose")step=0;document.querySelectorAll("[data-view]").forEach(x=>x.classList.toggle("active",x.dataset.view===v));if(v==="choose")renderQuestion();if(v==="dashboard")renderDashboard();if(v==="saved")renderSaved();document.querySelectorAll(".bottom button").forEach(b=>b.classList.toggle("active",b.dataset.go===v));scrollTo({{top:0,behavior:"smooth"}})}}
function renderQuestion(){{const q=questions[step];document.querySelector("#step-label").textContent=lang==="zh"?`${{t("step")}} ${{step+1}} / 3`:`${{t("step")}} ${{step+1}} de 3`;document.querySelector("#stepper").innerHTML=questions.map((_,i)=>`<button class="step ${{i===step?"active":""}}" type="button" data-step="${{i}}">${{i+1}}</button>`).join("");document.querySelector("#question").innerHTML=`<h1>${{esc(label(q))}}</h1><div class="options">${{q.options.map(o=>`<button class="option ${{answers[q.id]===o.id?"selected":""}}" data-answer="${{q.id}}" data-value="${{o.id}}">${{esc(label(o))}}</button>`).join("")}}</div>`;document.querySelector("#next-step span").textContent=step===questions.length-1?t("finish"):t("next");const prev=document.querySelector("#prev-step");if(prev){{prev.style.visibility=step===0?"hidden":"visible";prev.disabled=step===0}}}}
async function loadEntries(){{const p=new URLSearchParams({{limit:80}});Object.values(answers).forEach(v=>p.append("selected",v));const r=await fetch(`/api/creator/recommendations?${{p.toString()}}&_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"load failed");entries=d.entries||[];counts();return entries}}
function chips(){{const lookup=Object.fromEntries(questions.flatMap(q=>q.options.map(o=>[o.id,o])));return Object.values(answers).map(id=>lookup[id]).filter(Boolean).map(o=>`<span class="chip">${{esc(label(o))}} ✓</span>`).join("")}}
function dateKey(e){{const raw=String(e.script_date||"");const m=raw.match(/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})/);return m?`${{m[1]}}-${{m[2]}}-${{m[3]}}`:"recent"}}
function dateLabel(key){{if(key==="recent")return lang==="zh"?"近期":"Recentes";const [y,m,d]=key.split("-");return `${{y}}.${{Number(m)}}.${{Number(d)}}`}}
function masonryCard(e,i){{return `<button class="masonry-card" type="button" data-detail="${{esc(e.entry_id)}}"><img src="${{esc(e.thumbnail_url)}}" loading="lazy" alt=""><span class="masonry-title">${{esc(e.title)}}</span></button>`}}
function card(e,i){{const s=statusOf(e.entry_id);return `<article class="script card"><div class="thumb"><img src="${{esc(e.thumbnail_url)}}" loading="lazy" alt=""><span>${{Math.max(78,96-Math.min(i,18))}} match</span></div><div class="body"><h3>${{esc(e.title)}}</h3><p>${{esc(e.summary)}}</p><div class="tags"><span class="tag">${{esc(e.content_type)}}</span><span class="tag">1-3 min</span>${{s?`<span class="tag">${{s}}</span>`:""}}</div><div class="actions"><button class="open" data-detail="${{esc(e.entry_id)}}">▷ ${{t("open")}}</button><button class="icon" data-status="${{s==="saved"?"":"saved"}}" data-entry="${{esc(e.entry_id)}}">${{s==="saved"?"✓":"♡"}}</button><button class="icon" data-status="planned" data-entry="${{esc(e.entry_id)}}">＋</button></div></div></article>`}}
function renderList(sel,list){{document.querySelector(sel).innerHTML=list.length?list.map(card).join(""):`<section class="state card"><h3>${{t("empty")}}</h3><p class="lead">${{t("emptyText")}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`}}
function renderMasonry(sel,list){{const root=document.querySelector(sel);if(!list.length){{root.innerHTML=`<section class="state card"><h3>${{t("empty")}}</h3><p class="lead">${{t("emptyText")}}</p><button class="primary" data-go="dashboard">${{t("navHome")}}</button></section>`;return}}const groups=new Map();list.forEach(e=>{{const key=dateKey(e);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e)}});const keys=[...groups.keys()].sort((a,b)=>b.localeCompare(a));root.innerHTML=keys.map(key=>`<section class="date-group"><div class="date-divider">${{esc(dateLabel(key))}}</div><div class="masonry">${{groups.get(key).map(masonryCard).join("")}}</div></section>`).join("")}}
async function ensure(){{if(!entries.length)await loadEntries()}} async function renderDashboard(){{document.querySelector("#filters").innerHTML=chips();document.querySelector("#dashboard-feed").innerHTML=`<section class="state card"><h3>Loading...</h3></section>`;try{{await loadEntries();renderMasonry("#dashboard-feed",entries)}}catch(e){{document.querySelector("#dashboard-feed").innerHTML=`<section class="state card"><h3>Erro</h3></section>`}}}}
function savedList(k){{return (workspace[k]||[]).map(entry).filter(Boolean)}} async function renderSaved(){{document.querySelector("#saved-tabs").innerHTML=[["saved",t("statusSaved")],["planned",t("statusPlanned")],["finished",t("statusFinished")],["rejected",t("statusRejected")]].map(([id,txt])=>`<button class="${{savedTab===id?"active":""}}" data-tab="${{id}}">${{txt}} ${{(workspace[id]||[]).length}}</button>`).join("");await ensure();renderList("#saved-feed",savedList(savedTab))}}
function renderCurrent(){{const v=document.querySelector(".view.active")?.dataset.view;if(v==="dashboard")renderDashboard();if(v==="saved")renderSaved()}}
async function fetchScript(id){{let e=entry(id);if(e)return e;const r=await fetch(`/api/creator/scripts/${{encodeURIComponent(id)}}?html=0&_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"load failed");e=d.entry;if(!entries.some(x=>x.entry_id===e.entry_id))entries.unshift(e);else entries=entries.map(x=>x.entry_id===e.entry_id?{{...x,...e}}:x);return e}}
async function fetchScriptHtml(id){{const r=await fetch(`/api/creator/script-html/${{encodeURIComponent(id)}}?_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"html failed");entries=entries.map(x=>x.entry_id===id?{{...x,script_html:d.script_html||""}}:x);return d.script_html||""}}
function shareUrl(id){{return `${{location.origin}}/script/${{id}}`}}
async function copyText(text){{try{{if(navigator.clipboard){{await navigator.clipboard.writeText(text);return true}}}}catch(err){{}}try{{const ta=document.createElement("textarea");ta.value=text;ta.setAttribute("readonly","");ta.style.position="fixed";ta.style.top="0";ta.style.left="-9999px";document.body.appendChild(ta);ta.focus();ta.select();ta.setSelectionRange(0,ta.value.length);const ok=document.execCommand("copy");ta.remove();return ok}}catch(err){{return false}}}}
function showShareLink(id,copied){{const url=shareUrl(id);const box=document.querySelector("#share-output");if(box){{box.classList.add("active");box.innerHTML=`<b>${{copied?(lang==="zh"?"已复制分享链接":"Link copiado"):(lang==="zh"?"分享链接":"Link de compartilhamento")}}</b><a href="${{esc(url)}}" target="_blank" rel="noopener">${{esc(url)}}</a>`;if(!copied){{const link=box.querySelector("a");const range=document.createRange();range.selectNodeContents(link);const sel=window.getSelection();sel.removeAllRanges();sel.addRange(range)}}}}}}
function videoPreview(e){{const url=esc(e.video_url);const img=esc(e.thumbnail_url);return `<div class="video-box" data-video-box="${{esc(e.entry_id)}}" data-video-src="${{url}}"><img src="${{img}}" alt="video preview"><div class="video-fallback">${{url ? (lang==="zh"?"视频预览加载中":"Carregando preview") : ""}}</div></div>`}}
async function fetchVideoSource(id){{const r=await fetch(`/api/creator/video-source/${{encodeURIComponent(id)}}?_=${{Date.now()}}`);const d=await r.json();if(!r.ok)throw new Error(d.error||"video failed");return d.video_source_url||""}}
function hydrateVideo(e){{if(!e.video_url)return;setTimeout(async()=>{{const box=document.querySelector(`[data-video-box="${{e.entry_id}}"]`);if(!box||box.querySelector("video")||box.querySelector("iframe"))return;try{{const source=await fetchVideoSource(e.entry_id);if(source){{box.innerHTML=`<video src="${{esc(source)}}" poster="${{esc(e.thumbnail_url)}}" controls playsinline preload="metadata"></video>`;return}}}}catch(err){{}}box.innerHTML=`<iframe src="${{esc(e.video_url)}}" title="video preview" loading="lazy" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" sandbox="allow-scripts allow-same-origin allow-popups allow-presentation"></iframe><div class="video-fallback">${{lang==="zh"?"如果平台禁止内嵌播放，这里可能只显示空白。":"Se a plataforma bloquear embed, o preview pode aparecer em branco."}}</div>`}},350)}}
function scriptLoading(){{return `<section class="script-loading"><b>${{lang==="zh"?"脚本加载中请耐心等待":"Roteiro carregando, aguarde um momento"}}</b><span>${{lang==="zh"?"正在整理完整脚本内容，加载完成后会自动显示。":"Estamos preparando o roteiro completo. Ele aparecerá automaticamente."}}</span><div class="script-progress" aria-hidden="true"></div></section>`}}
function renderDetail(e){{const s=statusOf(e.entry_id);document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div>${{videoPreview(e)}}<h2 class="detail-title">${{esc(e.title)}}</h2><div class="tags"><span class="tag">${{esc(e.content_type)}}</span><span class="tag">1-3 min</span>${{s?`<span class="tag">${{s}}</span>`:""}}</div><div class="social-actions"><button class="social-btn" type="button" data-status="${{s==="saved"?"":"saved"}}" data-entry="${{esc(e.entry_id)}}" aria-label="${{t("save")}}">♡<span>${{s==="saved"?t("saved"):t("save")}}</span></button><button class="social-btn" type="button" data-copy-share="${{esc(e.entry_id)}}" aria-label="${{lang==="zh"?"复制分享链接":"Copiar link"}}">↗<span>${{lang==="zh"?"复制链接":"Copiar link"}}</span></button></div><div class="share-box" id="share-output"></div><div id="script-html-slot">${{e.script_html?`<article class="script-html">${{e.script_html}}</article>`:scriptLoading()}}</div><section class="submit"><b>${{t("submitTitle")}}</b><p class="lead">${{t("submitHint")}}</p><input type="url" data-submit-url="${{esc(e.entry_id)}}" placeholder="${{t("submitPlaceholder")}}"><button class="primary" data-submit="${{esc(e.entry_id)}}">${{t("submitButton")}}</button><div id="submit-status-${{esc(e.entry_id)}}"></div></section>`}}
function loadDetailHtml(e){{if(e.script_html)return;setTimeout(async()=>{{try{{const html=await fetchScriptHtml(e.entry_id);const slot=document.querySelector("#script-html-slot");if(slot)slot.innerHTML=html?`<article class="script-html">${{html}}</article>`:`<article class="script-html"><p>${{esc(e.summary)}}</p></article>`}}catch(err){{const slot=document.querySelector("#script-html-slot");if(slot)slot.innerHTML=`<article class="script-html"><p>${{esc(e.summary||err.message)}}</p></article>`}}}},300)}}
async function openDetail(id){{const modal=document.querySelector("#modal");modal.classList.add("active");const local=entry(id);if(local){{renderDetail(local);hydrateVideo(local);loadDetailHtml(local);return}}document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><section class="state card"><h3>${{lang==="zh"?"正在加载脚本..." :"Carregando roteiro..."}}</h3></section>`;try{{const e=await fetchScript(id);renderDetail(e);hydrateVideo(e);loadDetailHtml(e)}}catch(err){{document.querySelector("#detail").innerHTML=`<div class="detail-top"><button class="icon" data-close>×</button></div><section class="state card"><h3>${{lang==="zh"?"脚本加载失败":"Falha ao carregar"}}</h3><p>${{esc(err.message)}}</p></section>`}}}}
async function submitVideo(id){{const input=document.querySelector(`[data-submit-url="${{id}}"]`);const status=document.querySelector(`#submit-status-${{id}}`);const video_url=String(input?.value||"").trim();if(!video_url){{status.textContent=t("submitError");return}}status.textContent=lang==="zh"?"提交中...":"Enviando...";try{{const r=await fetch("/api/creator/submissions",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{entry_id:id,video_url,creator_id:"creator"}})}});if(!r.ok)throw new Error();status.textContent=t("submitOk");setStatus(id,"finished")}}catch(e){{status.textContent=t("submitError")}}}}
function closeDetail(){{document.querySelectorAll("#modal video").forEach(v=>{{try{{v.pause();v.removeAttribute("src");v.load()}}catch(e){{}}}});document.querySelector("#modal").classList.remove("active");document.querySelector("#detail").innerHTML=""}}
document.addEventListener("click",async e=>{{const l=e.target.closest("[data-lang]");if(l){{lang=l.dataset.lang;localStorage.setItem(langKey,lang);applyLang();return}}const reselect=e.target.closest("[data-reselect]");if(reselect){{show("choose");return}}const stepNav=e.target.closest("[data-step]");if(stepNav){{step=Number(stepNav.dataset.step)||0;renderQuestion();return}}if(e.target.closest("#prev-step")){{if(step>0){{step--;renderQuestion()}}return}}const tab=e.target.closest("[data-tab]");if(tab){{savedTab=tab.dataset.tab;renderSaved();return}}const d=e.target.closest("[data-detail]");if(d){{openDetail(d.dataset.detail);return}}if(e.target.closest("[data-close]")||e.target.id==="modal"){{closeDetail();return}}const copy=e.target.closest("[data-copy-share]");if(copy){{const id=copy.dataset.copyShare;const ok=await copyText(shareUrl(id));showShareLink(id,ok);const label=copy.querySelector("span");if(label)label.textContent=ok?(lang==="zh"?"已复制":"Copiado"):(lang==="zh"?"复制失败，请手动复制":"Copie manualmente");return}}const scrollSubmit=e.target.closest("[data-submit-scroll]");if(scrollSubmit){{document.querySelector(`[data-submit-url="${{scrollSubmit.dataset.submitScroll}}"]`)?.scrollIntoView({{behavior:"smooth",block:"center"}});return}}const sub=e.target.closest("[data-submit]");if(sub){{submitVideo(sub.dataset.submit);return}}const st=e.target.closest("[data-status]");if(st){{setStatus(st.dataset.entry,st.dataset.status);st.textContent=t(st.dataset.status==="saved"?"saved":st.dataset.status==="planned"?"plan":"save");return}}const go=e.target.closest("[data-go]");if(go){{if(go.dataset.savedTab)savedTab=go.dataset.savedTab;show(go.dataset.go);return}}const ans=e.target.closest("[data-answer]");if(ans){{answers[ans.dataset.answer]=ans.dataset.value;saveProfile();renderQuestion();return}}if(e.target.closest("#next-step")){{if(step<questions.length-1){{step++;renderQuestion()}}else{{saveProfile();show("dashboard")}}}}}});
applyLang();show(initialScriptId?"dashboard":hasProfile()?"dashboard":"home");if(initialScriptId)openDetail(initialScriptId);
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

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode() if length else "{}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/creator-portal"}:
            self.send_html(page_html())
            return
        if parsed.path == "/healthz":
            self.send_json({"ok": True})
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


def main() -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    sync_library(False)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(json.dumps({"port": PORT, "data_root": str(DATA_ROOT)}, ensure_ascii=False), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
