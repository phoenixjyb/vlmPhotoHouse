from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from .db import AssetTag, AssetTagBlock, Tag


_EN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'_-]{1,31}")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,16}")
_EN_SPLIT_RE = re.compile(r"[^a-z0-9]+")

_EN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "baby",
    "be",
    "boy",
    "by",
    "caption",
    "child",
    "children",
    "city",
    "country",
    "for",
    "from",
    "girl",
    "in",
    "image",
    "is",
    "it",
    "man",
    "of",
    "on",
    "or",
    "people",
    "person",
    "photo",
    "picture",
    "scene",
    "shows",
    "showing",
    "that",
    "the",
    "this",
    "to",
    "view",
    "with",
    "woman",
}

_ZH_STOPWORDS = {
    "照片",
    "图片",
    "拍摄",
    "画面",
    "人物",
    "人们",
    "男人",
    "女人",
    "男孩",
    "女孩",
    "城市",
    "国家",
}


@dataclass(frozen=True)
class CanonicalTag:
    name: str
    tag_type: str
    synonyms_en: tuple[str, ...] = ()
    synonyms_zh: tuple[str, ...] = ()


@dataclass(frozen=True)
class TagCandidate:
    name: str
    tag_type: str
    score: float


_CANONICAL_TAGS: tuple[CanonicalTag, ...] = (
    CanonicalTag("newborn", "stage", ("newborn",), ("新生儿",)),
    CanonicalTag("infant", "stage", ("infant",), ("婴儿",)),
    CanonicalTag("toddler", "stage", ("toddler",), ("幼儿",)),
    CanonicalTag("child", "stage", ("child", "kid", "kids"), ("儿童", "小朋友")),
    CanonicalTag("sleeping", "activity", ("sleeping", "asleep", "nap", "napping"), ("睡觉", "睡眠", "午睡")),
    CanonicalTag("playing", "activity", ("playing", "playtime"), ("玩耍", "游戏", "玩乐")),
    CanonicalTag("walking", "activity", ("walking", "walk"), ("行走", "走路", "散步")),
    CanonicalTag("holding baby", "activity", ("holding baby", "carry baby"), ("抱宝宝", "抱着宝宝")),
    CanonicalTag("tummy time", "activity", ("tummy time",), ("趴趴练习", "趴着练习", "趴趴")),
    CanonicalTag("craft", "activity", ("craft", "handicraft"), ("手工", "手工课")),
    CanonicalTag("drawing", "activity", ("drawing",), ("画画", "绘画")),
    CanonicalTag("singing", "activity", ("singing",), ("唱歌",)),
    CanonicalTag("group activity", "activity", ("group activity",), ("集体活动",)),
    CanonicalTag("school event", "event", ("school event",), ("校园活动",)),
    CanonicalTag("bedroom", "scene", ("bedroom",), ("卧室",)),
    CanonicalTag("living room", "scene", ("living room",), ("客厅",)),
    CanonicalTag("indoor play area", "scene", ("indoor play area", "play area", "kids play zone"), ("室内游乐区", "儿童游乐区", "游乐区")),
    CanonicalTag("mall", "scene", ("mall", "shopping mall"), ("商场",)),
    CanonicalTag("store", "scene", ("store", "shop"), ("商店",)),
    CanonicalTag("outdoor path", "scene", ("outdoor path", "pathway", "walking path"), ("户外步道", "步道")),
    CanonicalTag("kindergarten", "scene", ("kindergarten", "daycare", "preschool"), ("幼儿园",)),
    CanonicalTag("classroom", "scene", ("classroom",), ("教室", "课堂")),
    CanonicalTag("playground", "scene", ("playground",), ("操场",)),
    CanonicalTag("crib", "object", ("crib", "baby crib"), ("婴儿床",)),
    CanonicalTag("stroller", "object", ("stroller", "baby stroller", "pram"), ("婴儿推车", "推车")),
    CanonicalTag("play mat", "object", ("play mat",), ("游戏垫", "爬行垫")),
    CanonicalTag("ball pit", "object", ("ball pit",), ("海洋球池", "球池")),
    CanonicalTag("plush toy", "object", ("plush toy", "stuffed toy"), ("毛绒玩具",)),
    CanonicalTag("toy piano", "object", ("toy piano",), ("玩具钢琴",)),
    CanonicalTag("backpack", "object", ("backpack", "school bag"), ("书包",)),
    CanonicalTag("school uniform", "object", ("school uniform",), ("园服", "校服")),
    CanonicalTag("craft material", "object", ("craft material", "craft supplies"), ("手工材料",)),
    CanonicalTag("close-up", "shot", ("close up", "close-up"), ("特写",)),
    CanonicalTag("top-down", "shot", ("top down", "top-down"), ("俯拍",)),
    CanonicalTag("low-angle", "shot", ("low angle", "low-angle"), ("低角度",)),
    CanonicalTag("portrait", "shot", ("portrait",), ("人像",)),
    CanonicalTag("candid", "shot", ("candid",), ("抓拍",)),
    CanonicalTag("sunny", "time_weather", ("sunny",), ("晴天",)),
    CanonicalTag("rainy", "time_weather", ("rainy",), ("雨天",)),
    CanonicalTag("snowy", "time_weather", ("snowy",), ("雪天",)),
    CanonicalTag("night", "time_weather", ("night", "nighttime"), ("夜晚", "夜间")),
)

_REQUIRED_BUCKETS: tuple[tuple[set[str], int], ...] = (
    ({"stage"}, 1),
    ({"activity", "event"}, 1),
    ({"scene"}, 1),
    ({"shot"}, 1),
)

_TYPE_CAPS: tuple[tuple[str, int], ...] = (
    ("object", 2),
    ("time_weather", 1),
    ("attribute", 1),
    ("mood_other", 1),
)

_HARD_TYPE_CAPS: dict[str, int] = {
    "stage": 1,
    "scene": 1,
    "shot": 1,
}


def _normalize_tag(raw: str) -> str:
    s = unicodedata.normalize("NFKC", str(raw or "")).strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s[:64]


def _normalize_en_phrase(raw: str) -> str:
    s = _EN_SPLIT_RE.sub(" ", str(raw or "").lower()).strip()
    return re.sub(r"\s+", " ", s)


def _normalized_text(raw: str) -> str:
    return unicodedata.normalize("NFKC", str(raw or ""))


def _extract_canonical_candidates(text: str) -> list[TagCandidate]:
    text_norm = _normalized_text(text)
    en_buf = f" {_normalize_en_phrase(text_norm)} "
    out: list[TagCandidate] = []

    for tag in _CANONICAL_TAGS:
        best = 0.0
        for syn in tag.synonyms_en:
            syn_norm = _normalize_en_phrase(syn)
            if syn_norm and f" {syn_norm} " in en_buf:
                best = max(best, 0.70 + min(len(syn_norm.split()), 4) * 0.08)
        for syn in tag.synonyms_zh:
            syn_norm = _normalize_tag(syn)
            if syn_norm and syn_norm in text_norm:
                best = max(best, 0.72 + min(len(syn_norm), 8) * 0.03)
        if best <= 0:
            continue
        type_boost = {
            "stage": 0.08,
            "activity": 0.06,
            "event": 0.06,
            "scene": 0.06,
            "shot": 0.05,
        }.get(tag.tag_type, 0.0)
        out.append(TagCandidate(name=tag.name, tag_type=tag.tag_type, score=round(best + type_boost, 4)))
    return out


def _select_candidates(candidates: list[TagCandidate], max_tags: int) -> list[TagCandidate]:
    if not candidates or max_tags <= 0:
        return []

    ranked = sorted(candidates, key=lambda x: (-x.score, x.name))
    used: set[str] = set()
    selected: list[TagCandidate] = []
    type_counts: dict[str, int] = {}

    def _append_if_fit(candidate: TagCandidate) -> bool:
        if candidate.name in used or len(selected) >= max_tags:
            return False
        cap = _HARD_TYPE_CAPS.get(candidate.tag_type)
        if cap is not None and type_counts.get(candidate.tag_type, 0) >= cap:
            return False
        used.add(candidate.name)
        selected.append(candidate)
        type_counts[candidate.tag_type] = type_counts.get(candidate.tag_type, 0) + 1
        return True

    for allowed_types, limit in _REQUIRED_BUCKETS:
        if len(selected) >= max_tags:
            break
        added = 0
        for cand in ranked:
            if cand.tag_type not in allowed_types:
                continue
            if _append_if_fit(cand):
                added += 1
            if added >= limit or len(selected) >= max_tags:
                break

    for tag_type, cap in _TYPE_CAPS:
        if len(selected) >= max_tags:
            break
        added = 0
        for cand in ranked:
            if cand.tag_type != tag_type:
                continue
            if _append_if_fit(cand):
                added += 1
            if added >= cap or len(selected) >= max_tags:
                break

    for cand in ranked:
        if len(selected) >= max_tags:
            break
        _append_if_fit(cand)

    return selected


def _extract_fallback_keywords(text: str, max_tags: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for m in _EN_TOKEN_RE.finditer(text):
        tok = _normalize_en_phrase(m.group(0))
        if not tok or len(tok) < 3 or tok.isdigit() or tok in _EN_STOPWORDS:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
        if len(out) >= max_tags:
            return out

    for m in _CJK_TOKEN_RE.finditer(text):
        tok = _normalize_tag(m.group(0))
        if len(tok) < 2 or tok in _ZH_STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
        if len(out) >= max_tags:
            break

    return out


def extract_caption_tag_candidates(text: str, max_tags: int = 8) -> list[dict[str, object]]:
    """Extract deterministic caption tags with canonical mapping and quotas."""
    limit = max(1, min(int(max_tags or 8), 32))
    src = str(text or "").strip()
    if not src:
        return []

    canonical = _select_candidates(_extract_canonical_candidates(src), limit)
    if canonical:
        return [{"name": c.name, "type": c.tag_type, "score": c.score} for c in canonical]

    fallback = _extract_fallback_keywords(_normalized_text(src), limit)
    return [{"name": nm, "type": "caption-auto", "score": 0.01} for nm in fallback]


def extract_caption_tags(text: str, max_tags: int = 8) -> list[str]:
    """Compatibility wrapper returning tag names only."""
    return [str(x["name"]) for x in extract_caption_tag_candidates(text=text, max_tags=max_tags)]


def upsert_asset_tags(
    session: Session,
    asset_id: int,
    names: Iterable[str],
    tag_type: str = "caption-auto",
    name_types: dict[str, str] | None = None,
) -> list[str]:
    """Insert missing tag rows and asset-tag links; return newly linked names."""
    normalized_types: dict[str, str] = {}
    for raw_name, raw_type in (name_types or {}).items():
        clean_name = _normalize_tag(raw_name)
        clean_type = _normalize_tag(raw_type)[:32]
        if clean_name and clean_type:
            normalized_types[clean_name] = clean_type

    blocked_tag_ids = {
        int(tag_id)
        for (tag_id,) in (
            session.query(AssetTagBlock.tag_id).filter(AssetTagBlock.asset_id == asset_id).all()
        )
    }

    added: list[str] = []
    for nm in names:
        clean = _normalize_tag(nm)
        if not clean:
            continue
        effective_type = normalized_types.get(clean) or _normalize_tag(tag_type)[:32] or None
        tag = session.query(Tag).filter(Tag.name == clean).first()
        if tag is None:
            tag = Tag(name=clean, type=effective_type)
            session.add(tag)
            session.flush()
        elif effective_type and (not tag.type or tag.type == "caption-auto"):
            tag.type = effective_type

        if int(tag.id) in blocked_tag_ids:
            continue

        exists = (
            session.query(AssetTag)
            .filter(AssetTag.asset_id == asset_id, AssetTag.tag_id == tag.id)
            .first()
        )
        if exists is None:
            session.add(AssetTag(asset_id=asset_id, tag_id=tag.id))
            added.append(clean)
    return added
