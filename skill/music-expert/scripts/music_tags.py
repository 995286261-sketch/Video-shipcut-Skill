#!/usr/bin/env python3
"""Controlled tag vocabulary shared by register / recommend (coarse theme matching).

Tags describe intent and style (semantic layer), never acoustic measurements:
they are deliberately kept OUT of analysis reports (music_analyze.py stays pure
DSP). Manual registrations must use vocabulary slugs; raw source tags (e.g. from
Freesound) are mapped best-effort through aliases and anything unmappable is
simply not counted — this is 大致匹配 by design, not a classifier.
references/tag-vocabulary.md documents the same table for humans.
"""
from __future__ import annotations

TAG_VOCABULARY = {
    "mood": {
        "epic": ("史诗", ["epic", "cinematic", "trailer", "heroic", "majestic", "glory"]),
        "dark": ("黑暗", ["dark", "dramatic", "tense", "suspense", "suspenseful", "sinister", "aggressive", "intense", "evil", "brutal"]),
        "warm": ("温暖", ["warm", "uplifting", "hopeful", "optimistic", "heartwarming", "feel-good", "inspirational", "positive"]),
        "calm": ("平静", ["calm", "peaceful", "relaxing", "meditation", "gentle", "soft", "chill", "soothing", "serene"]),
        "melancholy": ("忧郁", ["melancholy", "melancholic", "sad", "emotional", "sentimental", "pensive", "lonely", "bittersweet", "somber"]),
        "playful": ("轻快", ["playful", "fun", "funny", "quirky", "happy", "cheerful", "bright", "sunny", "carefree"]),
        "mysterious": ("神秘", ["mysterious", "mystery", "ethereal", "hypnotic", "otherworldly", "dreamy", "space", "cosmic"]),
    },
    "genre": {
        "orchestral": ("管弦", ["orchestral", "orchestra", "symphony", "symphonic", "strings", "choir", "score", "film-music"]),
        "electronic": ("电子", ["electronic", "synth", "synthesizer", "edm", "techno", "house", "trance", "dubstep", "synthwave", "chipwave"]),
        "acoustic": ("原声", ["acoustic", "guitar", "piano", "folk", "ukulele", "violin", "cello", "harp"]),
        "percussive": ("打击", ["percussion", "drum", "drums", "drum-loop", "rhythm", "808", "taiko", "bongos", "tribal"]),
        "jazz": ("爵士", ["jazz", "blues", "swing", "lounge", "bossa", "bebop", "neo-soul"]),
        "rock": ("摇滚", ["rock", "indie", "punk", "metal", "grunge", "alternative", "distorted"]),
        "world": ("世界", ["world", "ethnic", "oriental", "asian", "indian", "african", "celtic", "medieval"]),
    },
    "energy": {
        "driving": ("推进", ["driving", "energetic", "powerful", "fast", "upbeat", "action", "high-energy", "pumping", "anthemic", "hard"]),
        "steady": ("平稳", ["steady", "mid-tempo", "moderate", "groove", "groovy", "loop", "background", "funky"]),
        "ambient-low": ("舒缓", ["slow", "minimal", "quiet", "sparse", "ambient", "drone", "underwater", "atmospheric", "downtempo"]),
        "building": ("渐强", ["building", "crescendo", "rising", "build-up", "progressive", "climax", "development"]),
    },
}

DIMENSIONS = tuple(TAG_VOCABULARY)


def all_slugs() -> list[str]:
    return [slug for dimension in TAG_VOCABULARY.values() for slug in dimension]


def accepted_tags_text() -> str:
    return "; ".join(f"{dimension}: {'/'.join(slugs)}" for dimension, slugs in TAG_VOCABULARY.items())


def resolve_tag(raw: str) -> str | None:
    """Map one free-text tag to a vocabulary slug, or None if it cannot be mapped."""
    token = str(raw).strip().lower().replace("_", "-")
    if not token:
        return None
    for dimension in TAG_VOCABULARY.values():
        for slug, (zh, aliases) in dimension.items():
            if token == slug or token == zh or token in aliases:
                return slug
    for dimension in TAG_VOCABULARY.values():
        for slug, (_, aliases) in dimension.items():
            if len(token) >= 4 and any(alias in token or token in alias for alias in aliases if len(alias) >= 4):
                return slug
    return None


def normalize_tag_list(raw_tags: list) -> list[str]:
    """Best-effort normalization (for foreign tags e.g. Freesound): keep order, dedupe, drop unmappable."""
    slugs: list[str] = []
    for raw in raw_tags or []:
        slug = resolve_tag(str(raw))
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def strict_tag_list(raw_tags: list) -> tuple[list[str], list[str]]:
    """For manual registration: every tag must resolve; returns (slugs, unknowns)."""
    slugs: list[str] = []
    unknown: list[str] = []
    for raw in raw_tags:
        slug = resolve_tag(str(raw))
        if slug is None:
            unknown.append(str(raw))
        elif slug not in slugs:
            slugs.append(slug)
    return slugs, unknown
