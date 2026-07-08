from __future__ import annotations

"""
Enormous Door Content Wizard
Workflow-first rebuild v23.1 packaging fix.

This version advances the workflow shell with:
- richer visual Draft Gallery cards
- true mini storyboard strips/cards
- deeper media analysis and stronger auto-inference
- migrated export/render logic inside the new 5-screen architecture

Primary flow:
1. Choose Outcome
2. Drop Files
3. Draft Gallery
4. Quick Refine
5. Export
"""

import copy
import importlib
import json
import math
import os
import queue
import random
import re
import shutil
import threading
import traceback
import wave
import sys
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# -----------------------------------------------------------------------------
# Optional dependencies
# -----------------------------------------------------------------------------

OPTIONAL_MODULES: Dict[str, bool] = {}
OPTIONAL_IMPORT_ERRORS: Dict[str, str] = {}
MOVIEPY_IMPORT_DIAGNOSTIC = "Not attempted yet."
FFMPEG_RUNTIME_DIAGNOSTIC = "Not resolved yet."


def optional_import(name: str):
    try:
        module = __import__(name)
        OPTIONAL_MODULES[name] = True
        OPTIONAL_IMPORT_ERRORS[name] = ""
        return module
    except Exception as exc:
        OPTIONAL_MODULES[name] = False
        OPTIONAL_IMPORT_ERRORS[name] = f"{type(exc).__name__}: {exc}"
        return None


def optional_import_from(module_name: str, names: List[str]):
    module = __import__(module_name, fromlist=names)
    return tuple(getattr(module, name) for name in names)


PIL = optional_import("PIL")
if PIL:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat, ImageTk
else:
    Image = ImageDraw = ImageFont = ImageOps = ImageStat = ImageTk = None

audioop = optional_import("audioop")

numpy = optional_import("numpy")
np = numpy

imageio_ffmpeg = optional_import("imageio_ffmpeg")
pytesseract = optional_import("pytesseract")

moviepy = optional_import("moviepy")
VideoFileClip = AudioFileClip = ImageClip = ColorClip = CompositeVideoClip = concatenate_videoclips = None

def _resolve_moviepy_runtime():
    global moviepy, VideoFileClip, AudioFileClip, ImageClip, ColorClip, CompositeVideoClip, concatenate_videoclips, MOVIEPY_IMPORT_DIAGNOSTIC
    attempts: List[str] = []

    if not moviepy:
        MOVIEPY_IMPORT_DIAGNOSTIC = OPTIONAL_IMPORT_ERRORS.get("moviepy", "moviepy not installed")
        return

    try:
        # Attempt 1: top-level re-exports used by moviepy 2.x source installs.
        (
            AudioFileClip,
            ColorClip,
            CompositeVideoClip,
            ImageClip,
            VideoFileClip,
            concatenate_videoclips,
        ) = optional_import_from(
            "moviepy",
            ["AudioFileClip", "ColorClip", "CompositeVideoClip", "ImageClip", "VideoFileClip", "concatenate_videoclips"],
        )
        OPTIONAL_MODULES["moviepy"] = True
        MOVIEPY_IMPORT_DIAGNOSTIC = "Available via moviepy top-level exports."
        return
    except Exception as exc:
        attempts.append(f"moviepy top-level exports: {type(exc).__name__}: {exc}")

    try:
        # Attempt 2: classic editor layout.
        (
            AudioFileClip,
            ColorClip,
            CompositeVideoClip,
            ImageClip,
            VideoFileClip,
            concatenate_videoclips,
        ) = optional_import_from(
            "moviepy.editor",
            ["AudioFileClip", "ColorClip", "CompositeVideoClip", "ImageClip", "VideoFileClip", "concatenate_videoclips"],
        )
        OPTIONAL_MODULES["moviepy"] = True
        MOVIEPY_IMPORT_DIAGNOSTIC = "Available via moviepy.editor exports."
        return
    except Exception as exc:
        attempts.append(f"moviepy.editor exports: {type(exc).__name__}: {exc}")

    try:
        # Attempt 3: split-module fallback for packaged runtimes where re-exports are not preserved.
        AudioFileClip = importlib.import_module("moviepy.audio.io.AudioFileClip").AudioFileClip
        VideoFileClip = importlib.import_module("moviepy.video.io.VideoFileClip").VideoFileClip
        _video_clip_mod = importlib.import_module("moviepy.video.VideoClip")
        ImageClip = getattr(_video_clip_mod, "ImageClip")
        ColorClip = getattr(_video_clip_mod, "ColorClip")
        _composite_mod = importlib.import_module("moviepy.video.compositing.CompositeVideoClip")
        CompositeVideoClip = getattr(_composite_mod, "CompositeVideoClip")
        concatenate_videoclips = getattr(_composite_mod, "concatenate_videoclips")
        OPTIONAL_MODULES["moviepy"] = True
        MOVIEPY_IMPORT_DIAGNOSTIC = f"Available via split moviepy submodules (packaged fallback). module={getattr(moviepy, '__file__', '(unknown)')}"
        return
    except Exception as exc:
        attempts.append(f"moviepy split submodules: {type(exc).__name__}: {exc}")

    OPTIONAL_MODULES["moviepy"] = False
    moviepy = None
    frozen_note = " [running in packaged EXE]" if getattr(sys, "frozen", False) else ""
    MOVIEPY_IMPORT_DIAGNOSTIC = " | ".join(attempts) + frozen_note if attempts else "Unknown moviepy runtime failure."

_resolve_moviepy_runtime()


def resolve_ffmpeg_executable() -> str:
    global FFMPEG_RUNTIME_DIAGNOSTIC
    candidates: List[str] = []

    if imageio_ffmpeg is not None:
        try:
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and Path(exe).exists():
                FFMPEG_RUNTIME_DIAGNOSTIC = f"Resolved via imageio_ffmpeg: {exe}"
                return exe
            if exe:
                candidates.append(exe)
        except Exception as exc:
            candidates.append(f"imageio_ffmpeg error: {type(exc).__name__}: {exc}")

    for probe in [
        shutil.which("ffmpeg"),
        str(Path(getattr(sys, "_MEIPASS", "")) / "ffmpeg.exe") if getattr(sys, "frozen", False) else "",
        str(Path(getattr(sys, "_MEIPASS", "")) / "ffmpeg") if getattr(sys, "frozen", False) else "",
        str(Path(sys.executable).resolve().parent / "ffmpeg.exe") if getattr(sys, "frozen", False) else "",
        str(Path(sys.executable).resolve().parent / "ffmpeg") if getattr(sys, "frozen", False) else "",
    ]:
        if probe and Path(probe).exists():
            FFMPEG_RUNTIME_DIAGNOSTIC = f"Resolved via runtime probe: {probe}"
            return probe
        if probe:
            candidates.append(probe)

    FFMPEG_RUNTIME_DIAGNOSTIC = "No ffmpeg executable found. Tried: " + " | ".join(candidates[:5]) if candidates else "No ffmpeg executable found."
    return ""


def resolve_ffprobe_executable() -> str:
    candidates: List[str] = []
    direct = shutil.which("ffprobe")
    if direct and Path(direct).exists():
        return direct
    if direct:
        candidates.append(direct)
    ffmpeg_exe = resolve_ffmpeg_executable()
    if ffmpeg_exe:
        ffmpeg_path = Path(ffmpeg_exe)
        sibling_names = ["ffprobe.exe", "ffprobe"]
        if ffmpeg_path.name.lower().startswith("ffmpeg"):
            sibling_names.insert(0, ffmpeg_path.name.lower().replace("ffmpeg", "ffprobe", 1))
        for name in sibling_names:
            probe = ffmpeg_path.with_name(name)
            if probe.exists():
                return str(probe)
            candidates.append(str(probe))
    return ""


def resolve_tesseract_executable() -> str:
    candidates = [
        shutil.which("tesseract"),
        shutil.which("tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    if getattr(sys, "frozen", False):
        candidates.extend([
            str(Path(sys.executable).resolve().parent / "tesseract.exe"),
            str(Path(getattr(sys, "_MEIPASS", "")) / "tesseract.exe"),
        ])
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return ""


whisper = optional_import("whisper")

tkinterdnd2 = optional_import("tkinterdnd2")
TkBase = tk.Tk
if tkinterdnd2:
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
        TkBase = TkinterDnD.Tk
    except Exception:
        OPTIONAL_MODULES["tkinterdnd2"] = False
        tkinterdnd2 = None
        DND_FILES = None
else:
    DND_FILES = None


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

APP_NAME = "Enormous Door Content Wizard"
APP_VERSION = "3.0.0-optimized"

# =============================================================================
# Enormous Door Brand Palette — dark industrial, heavy music mastering studio
# =============================================================================
ED: Dict[str, str] = {
    "bg_root":    "#0d0d0d",
    "bg_panel":   "#141414",
    "bg_card":    "#1c1c1c",
    "bg_input":   "#222222",
    "bg_hover":   "#252525",
    "red":        "#8b2d2d",
    "red_hover":  "#a53a3a",
    "red_lite":   "#c23535",
    "gold":       "#b8922a",
    "green":      "#2e7d32",
    "blue":       "#1a4a8a",
    "txt_primary":   "#f0ece8",
    "txt_secondary": "#a09890",
    "txt_dim":       "#575350",
    "border":     "#2a2828",
    "border_hi":  "#3c3836",
    "selected":   "#4a1a1a",
}

# =============================================================================
# Viral Content Intelligence — hook patterns, recipes, platform data
# Based on what actually performs on Reels/TikTok/Shorts in 2025-2026
# =============================================================================

VIRAL_HOOK_TEMPLATES: List[Dict[str, Any]] = [
    # Pattern-interrupt hooks (stop the scroll)
    {"angle": "pattern_interrupt", "label": "The Lie They Told You",
     "template": "Everyone says {wrong_belief}. That's wrong. Here's what actually happens.",
     "why": "Creates instant tension. Works for before/after and educational content."},
    {"angle": "pattern_interrupt", "label": "Nobody Talks About This",
     "template": "Nobody in {niche} talks about {hidden_truth}. Until now.",
     "why": "Curiosity gap. High share rate when the reveal is genuinely useful."},
    {"angle": "pattern_interrupt", "label": "The Real Reason",
     "template": "The real reason your {problem} sounds like {symptom}? It's not {common_blame}.",
     "why": "Reframes a frustration. Strong for mastering comparison demos."},

    # Proof hooks (let the result speak)
    {"angle": "proof", "label": "Before vs After (No Words)",
     "template": "No eq. No compression. Just mastering. Watch.",
     "why": "Pure proof. Best opener for audio comparison clips."},
    {"angle": "proof", "label": "The 3-Second Test",
     "template": "Can you hear the difference in 3 seconds? {play clip}",
     "why": "Gamifies the listen. High completion rate."},
    {"angle": "proof", "label": "I Fixed This Mix",
     "template": "This mix was {problem_description}. I fixed it. Here's the before/after.",
     "why": "Narrative setup → proof payoff. Strong for client work demos."},

    # Curiosity / open-loop hooks
    {"angle": "curiosity", "label": "The Counterintuitive Take",
     "template": "Louder isn't always better. This master proves it.",
     "why": "Contradicts a common belief. Drives comments + saves."},
    {"angle": "curiosity", "label": "I Shouldn't Share This",
     "template": "I probably shouldn't share this client session but... listen.",
     "why": "Creates exclusivity and FOMO. Use for real client demos."},
    {"angle": "curiosity", "label": "What Happened When",
     "template": "What happened when I mastered this the 'wrong' way.",
     "why": "Story-forward. High watch time when the ending lands."},

    # Direct / authority hooks
    {"angle": "direct", "label": "The Blunt Truth",
     "template": "Your mix is being rejected because of {specific reason}.",
     "why": "Direct value. Attracts people actively struggling with this."},
    {"angle": "direct", "label": "After {number} Mixes",
     "template": "After mastering {number} records I learned one thing nobody tells you.",
     "why": "Authority signal. Sets up a single punchy takeaway."},
    {"angle": "direct", "label": "Stop Doing This",
     "template": "Stop submitting mixes with {common_mistake}. Here's why it's hurting you.",
     "why": "Negative advice performs well. People self-identify and save."},
]

CONTENT_RECIPES: List[Dict[str, Any]] = [
    {
        "label": "60-Second Proof Drop",
        "icon": "🔊",
        "goal": "Before / After Comparison",
        "description": "Hook (3s) → Raw clip (10s) → Mastered clip (10s) → Reaction/result (5s) → CTA (3s)",
        "ideal_for": "Audio before/after demos",
        "platforms": ["Reels", "TikTok", "Shorts"],
        "hook_angle": "proof",
        "estimated_views_multiplier": 1.8,
        "tips": [
            "Start with the AFTER — hook with the best sound, then reveal the before",
            "No talking needed. Let the audio do the work.",
            "Caption: single line, under 80 chars",
        ],
    },
    {
        "label": "Authority Flex",
        "icon": "🏆",
        "goal": "Mastering Promo",
        "description": "Name drop (2s) → Proof clip (8s) → What changed (5s) → CTA (3s)",
        "ideal_for": "Client name drops, release announcements",
        "platforms": ["Reels", "Feed", "Shorts"],
        "hook_angle": "direct",
        "estimated_views_multiplier": 1.4,
        "tips": [
            "Use artist name or label in the first 2 seconds",
            "Sound quality IS the flex — make it obvious",
            "CTA: one action only",
        ],
    },
    {
        "label": "Teach + Prove",
        "icon": "🎓",
        "goal": "Educational Tip",
        "description": "Claim (3s) → Explanation (15s) → Proof example (10s) → Takeaway (5s)",
        "ideal_for": "Tips, tutorials, gear opinions",
        "platforms": ["YouTube Shorts", "TikTok", "Reels"],
        "hook_angle": "educational",
        "estimated_views_multiplier": 1.6,
        "tips": [
            "Make the claim polarising enough to spark comments",
            "Proof example should be audio, not talking",
            "End with a question to drive comments",
        ],
    },
    {
        "label": "The Pattern Interrupt",
        "icon": "⚡",
        "goal": "Mastering Promo",
        "description": "Surprising statement (2s) → Why it's true (10s) → Proof (10s) → CTA (3s)",
        "ideal_for": "Breaking the scroll, re-engagement after silence",
        "platforms": ["Reels", "TikTok"],
        "hook_angle": "pattern_interrupt",
        "estimated_views_multiplier": 2.1,
        "tips": [
            "First 2 seconds must be visually OR sonically surprising",
            "No logo at the start — it kills the pattern interrupt",
            "Sound on/off must both be compelling",
        ],
    },
    {
        "label": "Testimonial Drop",
        "icon": "💬",
        "goal": "Client Testimonial",
        "description": "Quote hook (3s) → Context (5s) → Proof audio (10s) → Artist reaction (5s) → CTA (3s)",
        "ideal_for": "Client wins, social proof, credibility building",
        "platforms": ["Reels", "Feed", "Stories"],
        "hook_angle": "proof",
        "estimated_views_multiplier": 1.3,
        "tips": [
            "Lead with the most impactful quote fragment",
            "Show the real result — don't describe it",
            "Tag the artist if they allow it",
        ],
    },
    {
        "label": "Release Teaser",
        "icon": "🔥",
        "goal": "New Release Teaser",
        "description": "Intrigue clip (5s) → Build (8s) → Drop/reveal (5s) → Link in bio CTA (3s)",
        "ideal_for": "New album/EP/single, pre-release buzz",
        "platforms": ["Stories", "Reels", "Shorts"],
        "hook_angle": "curiosity",
        "estimated_views_multiplier": 1.5,
        "tips": [
            "Don't reveal the full track — cut before the drop",
            "Use motion / visual energy to match the music",
            "Post 3–5 days before release for maximum reach",
        ],
    },
]

PLATFORM_BEST_TIMES: Dict[str, List[str]] = {
    "Reels":   ["Tue–Fri 6–9 AM", "Tue–Fri 12–2 PM", "Mon–Sat 7–10 PM"],
    "TikTok":  ["Tue–Fri 7–9 AM", "Tue–Thu 12–3 PM", "Tue–Fri 7–9 PM"],
    "Shorts":  ["Mon–Sat 8–11 AM", "Mon–Sat 5–8 PM"],
    "Stories": ["Mon–Fri 7–9 AM", "Mon–Fri 5–7 PM"],
    "Feed":    ["Mon–Wed 11 AM–1 PM", "Mon–Fri 8–9 AM"],
}

VIRAL_CAPTION_PATTERNS: List[Dict[str, str]] = [
    {"name": "Open Loop",      "pattern": "I wasn't going to share this but... [reveal at end]",
     "use_when": "You have a strong proof result"},
    {"name": "Polarising Take", "pattern": "[Strong opinion]. Agree or disagree? ↓",
     "use_when": "You want comments and debate"},
    {"name": "Question Hook",  "pattern": "Can you hear what changed? 👇 [before/after]",
     "use_when": "Audio comparison content"},
    {"name": "Teach + CTA",   "pattern": "[Tip]. Save this for when you need it →",
     "use_when": "Educational content with high save potential"},
    {"name": "Social Proof",   "pattern": "[Artist/label] trusted us with this one. Here's why.",
     "use_when": "Client work you can reference"},
    {"name": "Number Drop",    "pattern": "[X] records mastered. [Y] thing I wish I knew earlier.",
     "use_when": "Authority and experience posts"},
]
DEFAULT_ROOT_NAME = "EnormousDoor_ContentSystem"

ED_COLORS: Dict[str, str] = {
    "bg": "#0f0f10",
    "panel": "#171719",
    "panel_alt": "#1c1c1f",
    "panel_soft": "#232327",
    "text": "#f3f1ea",
    "muted": "#b6b1a6",
    "muted_soft": "#8c877d",
    "accent": "#8b2328",
    "accent_hover": "#a72c33",
    "accent_soft": "#311417",
    "success": "#2f7d45",
    "warning": "#a17a1c",
    "border": "#3a3530",
}

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
AUDIO_EXTS = {".wav", ".mp3", ".aif", ".aiff", ".flac", ".m4a", ".ogg"}
CAPTION_EXTS = {".srt", ".vtt", ".txt"}

CANVAS_FAMILIES: Dict[str, Tuple[int, int]] = {
    "9x16": (1080, 1920),
    "4x5": (1080, 1350),
    "1x1": (1080, 1080),
    "16x9": (1920, 1080),
    "2x3": (1080, 1620),
}

UI_SAFE_MARGINS: Dict[str, Dict[str, float]] = {
    "9x16": {"top": 0.12, "bottom": 0.20},
    "4x5": {"top": 0.08, "bottom": 0.14},
    "1x1": {"top": 0.06, "bottom": 0.12},
    "16x9": {"top": 0.08, "bottom": 0.10},
    "2x3": {"top": 0.10, "bottom": 0.16},
}

PLATFORM_VARIANTS: List[str] = [
    "Auto",
    "Reels",
    "Stories",
    "Feed",
    "Landscape",
    "Portrait Feed",
]

PLATFORM_SAFE_ZONE_PRESETS: Dict[str, Dict[str, Dict[str, float]]] = {
    "Reels": {
        "9x16": {"top": 0.16, "bottom": 0.25},
        "4x5": {"top": 0.10, "bottom": 0.18},
    },
    "Stories": {
        "9x16": {"top": 0.10, "bottom": 0.18},
        "2x3": {"top": 0.10, "bottom": 0.16},
    },
    "Feed": {
        "4x5": {"top": 0.08, "bottom": 0.16},
        "1x1": {"top": 0.06, "bottom": 0.14},
        "2x3": {"top": 0.10, "bottom": 0.18},
    },
    "Landscape": {
        "16x9": {"top": 0.08, "bottom": 0.12},
    },
    "Portrait Feed": {
        "2x3": {"top": 0.11, "bottom": 0.18},
        "4x5": {"top": 0.09, "bottom": 0.16},
    },
}

CAPTION_STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "ED Clean Lower Third": {
        "uppercase": False,
        "box_fill": (0, 0, 0, 112),
        "text_fill": (255, 255, 255, 255),
        "accent": (179, 45, 46, 255),
        "outline": False,
        "centered": False,
        "custom_accent": None,
    },
    "Bold Box": {
        "uppercase": True,
        "box_fill": (10, 10, 10, 185),
        "text_fill": (255, 255, 255, 255),
        "accent": (179, 45, 46, 255),
        "outline": False,
        "centered": False,
    },
    "Heavy Outline": {
        "uppercase": True,
        "box_fill": (0, 0, 0, 0),
        "text_fill": (255, 255, 255, 255),
        "accent": (179, 45, 46, 255),
        "outline": True,
        "centered": False,
    },
    "Minimal Centered": {
        "uppercase": False,
        "box_fill": (0, 0, 0, 96),
        "text_fill": (255, 255, 255, 255),
        "accent": (45, 111, 179, 255),
        "outline": False,
        "centered": True,
    },
}


# Font families for caption rendering
# Key = display name, Value = PIL font search name (falls back to default if missing)
CAPTION_FONT_FAMILIES: Dict[str, str] = {
    "Default":       "",            # PIL default — always available
    "Bold Sans":     "ariblk.ttf", # Arial Black / bold impact
    "Clean Sans":    "arial.ttf",  # Clean readable sans-serif
    "Condensed":     "arialbd.ttf",# Tight bold — good for hooks
    "Thin Modern":   "ariali.ttf", # Italic/thin modern look
}

CAPTION_FONT_FAMILY_LABELS: List[str] = list(CAPTION_FONT_FAMILIES.keys())

PLATFORM_SAFE_ZONE_DESCRIPTIONS: Dict[str, str] = {
    "Auto":              "No safe zone applied",
    "Reels / TikTok":   "Bottom 25% reserved for interaction buttons",
    "Stories":          "Top & bottom 15% reserved for UI",
    "YouTube Shorts":   "Bottom 20% reserved for subscribe / title",
    "Feed 4:5":         "Standard feed — full frame usable",
    "Feed Square":      "Square crop — centre-safe",
    "Landscape 16:9":   "Widescreen — full frame usable",
}

CAPTION_POSITION_PRESETS: List[str] = [
    "Bottom Center",
    "Bottom Left",
    "Mid Screen",
    "Top Center",
    "Stacked Emphasis",
    "Custom XY",
]


CAPTION_EMPHASIS_PRESETS: Dict[str, Dict[str, Any]] = {
    "Subtle": {
        "font_size": 14,
        "line_height": 18,
        "padding_y": 6,
        "padding_x": 8,
        "box_alpha_boost": 0.85,
        "accent_width": 2,
        "force_upper": False,
        "outline": False,
    },
    "Standard": {
        "font_size": 18,
        "line_height": 22,
        "padding_y": 8,
        "padding_x": 10,
        "box_alpha_boost": 1.0,
        "accent_width": 3,
        "force_upper": False,
        "outline": False,
    },
    "Punchy": {
        "font_size": 22,
        "line_height": 26,
        "padding_y": 10,
        "padding_x": 12,
        "box_alpha_boost": 1.12,
        "accent_width": 4,
        "force_upper": True,
        "outline": False,
    },
    "Trailer": {
        "font_size": 26,
        "line_height": 30,
        "padding_y": 12,
        "padding_x": 14,
        "box_alpha_boost": 1.2,
        "accent_width": 5,
        "force_upper": True,
        "outline": True,
    },
}

PLATFORM_EXPORT_STRENGTHS: Dict[str, List[str]] = {
    "Vertical Everywhere": ["Reels", "Stories", "Shorts"],
    "Meta Feed Pack": ["Feed 4:5", "Square Feed"],
    "Meta Creator Pack": ["Reels", "Stories", "Feed"],
    "Professional Cross-Post Pack": ["Reels", "Feed", "Landscape"],
    "Full Distribution Pack": ["Reels", "Feed", "Landscape", "Tall"],
    "Custom": ["Custom Output"],
}

PUBLISH_BUNDLES: Dict[str, List[str]] = {
    "Vertical Everywhere": ["9x16"],
    "Meta Feed Pack": ["4x5", "1x1"],
    "Meta Creator Pack": ["9x16", "4x5", "1x1"],
    "Professional Cross-Post Pack": ["9x16", "4x5", "1x1", "16x9"],
    "Full Distribution Pack": ["9x16", "4x5", "1x1", "16x9", "2x3"],
    "Custom": [],
}

FUNNEL_CTAS = [
    "Start Your Project",
    "Estimate Your Mastering Pricing",
    "Get Your Mastering Quote",
    "Send Your Mix",
    "Book Mastering",
    "See If Your Mix Is Ready",
    "Hear What Your Mix Needs",
    "Find Out What’s Holding It Back",
    "Define Your Heavy",
    "Compare Your Options",
    "See What Changes In Mastering",
    "Find The Right Next Step",
    "Hear The Difference",
    "Listen To Before / After",
    "See How It Translates",
    "Hear More Impact",
    "Get More Control",
    "See Why It Hits Harder",
]

HOOK_ANGLES = ["direct", "proof", "curiosity", "educational"]

GOAL_CARDS: List[Dict[str, Any]] = [
    {
        "label": "Sell Mastering",
        "goal": "Mastering Promo",
        "template_family": "Mastering Promo",
        "recommended_bundle": "Professional Cross-Post Pack",
        "hook_angle": "direct",
        "cta": "Start Your Project",
        "description": "Lead with authority, a strong opener, and a direct-response closer.",
    },
    {
        "label": "Show Before / After",
        "goal": "Before / After Comparison",
        "template_family": "Before / After Comparison",
        "recommended_bundle": "Meta Creator Pack",
        "hook_angle": "proof",
        "cta": "Listen To Before / After",
        "description": "Prioritize proof assets and comparison-friendly sequencing.",
    },
    {
        "label": "Teach Something",
        "goal": "Educational Tip",
        "template_family": "Educational Tip",
        "recommended_bundle": "Full Distribution Pack",
        "hook_angle": "educational",
        "cta": "Hear What Your Mix Needs",
        "description": "Frame the content around clarity, explanation, and proof.",
    },
    {
        "label": "Show Proof / Testimonial",
        "goal": "Client Testimonial",
        "template_family": "Client Testimonial",
        "recommended_bundle": "Meta Creator Pack",
        "hook_angle": "proof",
        "cta": "See What Changes In Mastering",
        "description": "Put testimonials, reactions, and result-focused proof first.",
    },
    {
        "label": "Push a CTA",
        "goal": "Offer / CTA",
        "template_family": "Offer / CTA",
        "recommended_bundle": "Meta Creator Pack",
        "hook_angle": "direct",
        "cta": "Get Your Mastering Quote",
        "description": "Keep the path simple: opener, proof, and a hard CTA close.",
    },
    {
        "label": "Tease a Release",
        "goal": "New Release Teaser",
        "template_family": "New Release Teaser",
        "recommended_bundle": "Vertical Everywhere",
        "hook_angle": "curiosity",
        "cta": "Hear The Difference",
        "description": "Use motion and energy to build fast teaser-style drafts.",
    },
    {
        "label": "Not Sure — Pick For Me",
        "goal": "Mastering Promo",
        "template_family": "Smart Auto",
        "recommended_bundle": "Meta Creator Pack",
        "hook_angle": "direct",
        "cta": "Start Your Project",
        "description": "Let the app infer the strongest direction from the media.",
    },
]

INTAKE_STAGES = [
    "Importing assets",
    "Creating previews",
    "Reading media",
    "Detecting pairs",
    "Inferring direction",
    "Ranking openers",
    "Building drafts",
    "Generating copy",
    "Preparing captions",
]


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "untitled"


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_json_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    tmp.replace(path)


def safe_copy(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    final = dst
    if final.exists():
        final = final.with_name(f"{final.stem}_{now_stamp()}{final.suffix}")
    shutil.copy2(src, final)
    return final


def infer_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTS:
        return "video"
    if suffix in IMAGE_EXTS:
        return "image"
    if suffix in AUDIO_EXTS:
        return "audio"
    if suffix in CAPTION_EXTS:
        return "captions"
    return "unknown"


def rms_from_pcm(frames: bytes, sample_width: int) -> float:
    """Compute RMS without requiring audioop (removed in Python 3.13)."""
    if not frames:
        return 0.0
    if audioop is not None:
        try:
            return float(audioop.rms(frames, sample_width))
        except Exception:
            pass
    if sample_width == 1:
        values = [b - 128 for b in frames]
    elif sample_width == 2:
        values = [int.from_bytes(frames[i:i+2], 'little', signed=True) for i in range(0, len(frames) - 1, 2)]
    elif sample_width == 3:
        values = []
        for i in range(0, len(frames) - 2, 3):
            chunk = frames[i:i+3]
            sign = b'\xff' if chunk[2] & 0x80 else b'\x00'
            values.append(int.from_bytes(chunk + sign, 'little', signed=True))
    elif sample_width == 4:
        values = [int.from_bytes(frames[i:i+4], 'little', signed=True) for i in range(0, len(frames) - 3, 4)]
    else:
        return 0.0
    if not values:
        return 0.0
    mean_sq = sum(v * v for v in values) / len(values)
    return math.sqrt(mean_sq)


def orientation_name(width: int, height: int) -> str:
    if not width or not height:
        return ""
    ratio = width / float(height)
    if ratio < 0.85:
        return "vertical"
    if ratio > 1.2:
        return "horizontal"
    return "square"


def resolve_ui_safe_margins(canvas_family: str, platform_variant: str = "Auto") -> Dict[str, float]:
    base = dict(UI_SAFE_MARGINS.get(canvas_family, UI_SAFE_MARGINS["9x16"]))
    if platform_variant != "Auto":
        override = PLATFORM_SAFE_ZONE_PRESETS.get(platform_variant, {}).get(canvas_family)
        if override:
            base.update(override)
    return base


def resolve_platform_variant_from_label(label: str) -> str:
    value = (label or "").lower()
    if "story" in value:
        return "Stories"
    if "reel" in value or "short" in value:
        return "Reels"
    if "landscape" in value:
        return "Landscape"
    if "portrait" in value:
        return "Portrait Feed"
    if "feed" in value:
        return "Feed"
    return "Auto"


def resolve_canvas_for_platform_variant(variant: str, fallback: str = "9x16") -> str:
    mapping = {
        "Reels": "9x16",
        "Stories": "9x16",
        "Feed": "4x5",
        "Landscape": "16x9",
        "Portrait Feed": "4x5",
        "Auto": fallback,
    }
    return mapping.get(variant, fallback)


def get_preview_font(size: int, bold: bool = False):
    if not ImageFont:
        return None
    candidates = []
    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ])
    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ])
    for font_path in candidates:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def csv_list(items: List[str]) -> str:
    return ", ".join(items)


def dependency_diagnostics_summary() -> str:
    runtime_mode = 'packaged EXE' if getattr(sys, 'frozen', False) else 'source / python'
    lines = []
    lines.append(f"runtime: {runtime_mode}")
    lines.append(f"executable: {sys.executable}")
    if getattr(sys, 'frozen', False):
        lines.append(f"_MEIPASS: {getattr(sys, '_MEIPASS', '(missing)')}")
    moviepy_status = "Available" if OPTIONAL_MODULES.get("moviepy", False) else "Unavailable"
    lines.append(f"moviepy: {moviepy_status}")
    if moviepy is not None:
        lines.append(f"moviepy module file: {getattr(moviepy, '__file__', '(unknown)')}")
    if MOVIEPY_IMPORT_DIAGNOSTIC:
        lines.append(f"moviepy detail: {MOVIEPY_IMPORT_DIAGNOSTIC}")
    ffmpeg_exe = resolve_ffmpeg_executable()
    lines.append(f"ffmpeg: {ffmpeg_exe if ffmpeg_exe else 'Unavailable'}")
    if FFMPEG_RUNTIME_DIAGNOSTIC:
        lines.append(f"ffmpeg detail: {FFMPEG_RUNTIME_DIAGNOSTIC}")
    for probe_name in [
        "moviepy.editor",
        "moviepy.audio.io.AudioFileClip",
        "moviepy.video.io.VideoFileClip",
        "moviepy.video.compositing.CompositeVideoClip",
    ]:
        try:
            spec = importlib.util.find_spec(probe_name)
            lines.append(f"probe {probe_name}: {'found' if spec else 'missing'}")
        except Exception as exc:
            lines.append(f"probe {probe_name}: error ({type(exc).__name__}: {exc})")
    for dep in ["PIL", "numpy", "imageio_ffmpeg", "pytesseract", "whisper", "tkinterdnd2", "audioop"]:
        status = "Available" if OPTIONAL_MODULES.get(dep, False) else "Unavailable"
        detail = OPTIONAL_IMPORT_ERRORS.get(dep, "")
        if detail and status == "Unavailable":
            lines.append(f"{dep}: {status} ({detail})")
        else:
            lines.append(f"{dep}: {status}")
    return "\n".join(lines)


def dependency_diagnostics_path() -> Path:
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path.cwd()
    filename = 'exe_dependency_diagnostics.txt' if getattr(sys, 'frozen', False) else 'source_dependency_diagnostics.txt'
    return base_dir / filename


def write_dependency_diagnostics_file() -> Optional[Path]:
    try:
        target = dependency_diagnostics_path()
        target.write_text(dependency_diagnostics_summary(), encoding='utf-8')
        return target
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------------


@dataclass
class MediaAnalysis:
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    audio_loudness: float = 0.0
    motion_score: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    speech_likelihood: float = 0.0
    talking_head_likelihood: float = 0.0
    split_screen_suitability: float = 0.0
    before_after_hint: str = ""
    dominant_orientation: str = ""
    preview_path: str = ""
    waveform_path: str = ""
    ocr_text: str = ""
    transcript_text: str = ""
    intent_signal: str = ""
    analysis_notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.duration:
            parts.append(f"{self.duration:.1f}s")
        if self.width and self.height:
            parts.append(f"{self.width}x{self.height}")
        if self.motion_score:
            parts.append(f"motion {self.motion_score:.2f}")
        if self.speech_likelihood:
            parts.append(f"speech {self.speech_likelihood:.2f}")
        return " | ".join(parts) if parts else "Not analyzed yet"


@dataclass
class Asset:
    asset_id: str
    path: str
    media_type: str
    title: str
    tags: List[str] = field(default_factory=list)
    content_goal_tags: List[str] = field(default_factory=list)
    role_tags: List[str] = field(default_factory=list)
    favorite: bool = False
    rating: int = 0
    notes: str = ""
    analysis: MediaAnalysis = field(default_factory=MediaAnalysis)


@dataclass
class PairSuggestion:
    before_asset_id: str
    after_asset_id: str
    score: float
    reason: str



@dataclass
class CaptionEvent:
    """A timed text overlay on a single storyboard card."""
    text: str = ""
    start_sec: float = 0.0          # seconds from clip start (0 = clip start)
    end_sec: float = 0.0            # 0 = play to end of clip
    position: str = "Bottom Center" # one of CAPTION_POSITION_PRESETS
    style: str = "ED Clean Lower Third"
    emphasis: str = "Standard"
    font_family: str = "Default"    # one of CAPTION_FONT_FAMILIES keys


@dataclass
class StoryboardCard:
    asset_id: str
    role: str = "support"
    duration_override: float = 0.0
    mute_audio: bool = False
    crop_focus_x: float = 0.5
    crop_focus_y: float = 0.5
    use_split_screen: bool = False
    pair_asset_id: str = ""
    compare_mode: str = "split-screen"
    caption_events: List["CaptionEvent"] = field(default_factory=list)
    caption_font_family: str = "Default"    # per-card font family override
    text_position_x: float = -1.0           # -1 = use preset; 0.0-1.0 = custom X
    text_position_y: float = -1.0           # -1 = use preset; 0.0-1.0 = custom Y

    def effective_duration(self, asset: Optional[Asset]) -> float:
        if self.duration_override > 0:
            return self.duration_override
        if asset:
            if asset.media_type == "image":
                return 2.5
            if asset.analysis.duration > 0:
                return min(asset.analysis.duration, 8.0 if self.role == "hook" else 10.0)
        return 3.0


@dataclass
class DraftOption:
    draft_id: str
    name: str
    label: str
    storyboard_cards: List[StoryboardCard] = field(default_factory=list)
    runtime_estimate: float = 0.0
    recommended_bundle: str = "Meta Creator Pack"
    hook_options: List[str] = field(default_factory=list)
    title_options: List[str] = field(default_factory=list)
    cta_options: List[str] = field(default_factory=list)
    rationale: str = ""
    confidence_score: float = 0.0
    style_tag: str = ""
    locked_platform_variant: str = ""
    locked_caption_style: str = ""
    locked_caption_position: str = ""
    locked_caption_emphasis: str = ""
    is_export_candidate: bool = False


@dataclass
class ExportVersionSnapshot:
    source_label: str = ""
    draft_id: str = ""
    draft_name: str = ""
    runtime_estimate: float = 0.0
    bundle: str = "Meta Creator Pack"
    platform_variant: str = "Auto"
    caption_style: str = "ED Clean Lower Third"
    caption_position: str = "Bottom Center"
    caption_emphasis: str = "Standard"
    hook: str = ""
    title: str = ""
    cta: str = ""
    rationale: str = ""
    storyboard_roles: List[str] = field(default_factory=list)
    storyboard_titles: List[str] = field(default_factory=list)
    storyboard_cards: List[Dict[str, Any]] = field(default_factory=list)
    export_path: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ProjectState:
    project_name: str = "Untitled Project"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    content_goal: str = GOAL_CARDS[0]["goal"]
    template_family: str = GOAL_CARDS[0]["template_family"]
    auto_inference_enabled: bool = False
    recommended_bundle: str = GOAL_CARDS[0]["recommended_bundle"]
    publish_bundle: str = GOAL_CARDS[0]["recommended_bundle"]
    hook_angle: str = GOAL_CARDS[0]["hook_angle"]
    cta_text: str = GOAL_CARDS[0]["cta"]
    title_text: str = ""
    hook_text: str = ""
    caption_mode: str = "Auto"
    caption_source_path: str = ""
    reference_text: str = ""
    reference_paths: List[str] = field(default_factory=list)
    reference_preview_paths: Dict[str, str] = field(default_factory=dict)
    reference_accent_color: str = ""    # hex color extracted from reference image
    reference_font_hint: str = ""       # bold/thin/serif hint from reference
    reference_media_types: Dict[str, str] = field(default_factory=dict)
    reference_preview_notes: Dict[str, str] = field(default_factory=dict)
    selected_reference_path: str = ""
    assets: List[Asset] = field(default_factory=list)
    pair_suggestions: List[PairSuggestion] = field(default_factory=list)
    drafts: List[DraftOption] = field(default_factory=list)
    selected_draft_id: str = ""
    selected_storyboard: List[StoryboardCard] = field(default_factory=list)
    selected_storyboard_index: int = -1
    preview_canvas_family: str = "9x16"
    preview_platform_variant: str = "Auto"
    preview_caption_style: str = "ED Clean Lower Third"
    preview_caption_position: str = "Bottom Center"
    preview_caption_emphasis: str = "Standard"
    export_candidate_draft_id: str = ""
    automation_notes: List[str] = field(default_factory=list)
    intake_state: str = "idle"
    intake_stage: str = ""
    intake_total: int = 0
    intake_processed: int = 0
    intake_current_item: str = ""
    intake_error: str = ""
    last_export_path: str = ""
    last_export_snapshot: Optional[ExportVersionSnapshot] = None
    export_score_weights: Dict[str, int] = field(default_factory=lambda: {"copy": 3, "proof": 3, "cta": 3, "platform": 2})
    export_decision_notes: str = ""
    final_approval_locked: bool = False
    approved_export_source: str = ""
    approved_export_snapshot: Optional[ExportVersionSnapshot] = None

    def selected_draft(self) -> Optional[DraftOption]:
        return next((d for d in self.drafts if d.draft_id == self.selected_draft_id), None)


# -----------------------------------------------------------------------------
# Content system
# -----------------------------------------------------------------------------


class ContentSystem:
    def __init__(self, root_dir: Optional[Path] = None):
        self.root = root_dir or (Path.home() / DEFAULT_ROOT_NAME)
        self.paths = {
            "library": self.root / "01_Reusable_Media_Library",
            "projects": self.root / "02_Active_Projects",
            "exports": self.root / "03_Finished_Exports",
            "templates": self.root / "04_Templates_and_Presets",
            "metadata": self.root / "05_Metadata_and_Indexes",
            "state": self.root / "06_App_State",
        }

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)
        library = self.paths["library"]
        for folder in [
            "video",
            "images",
            "audio",
            "branding",
            "text_library",
            "captions",
            "reference_inspiration",
            "proxy_previews",
            "raw_inbox",
            "derived_assets",
        ]:
            (library / folder).mkdir(parents=True, exist_ok=True)

    def library_target(self, media_type: str, src: Path) -> Path:
        mapping = {"video": "video", "image": "images", "audio": "audio", "captions": "captions"}
        return self.paths["library"] / mapping.get(media_type, "raw_inbox") / src.name

    def next_project_dir(self, project_name: str) -> Path:
        target = self.paths["projects"] / f"{slugify(project_name)}_{now_stamp()}"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def next_export_dir(self, project_name: str) -> Path:
        target = self.paths["exports"] / f"{slugify(project_name)}_{now_stamp()}"
        target.mkdir(parents=True, exist_ok=True)
        for folder in [
            "01_Masters",
            "02_Vertical_9x16",
            "03_Portrait_4x5",
            "04_Square_1x1",
            "05_Landscape_16x9",
            "06_Tall_2x3",
            "07_Captions",
            "08_Project_Files",
            "09_Archive_Notes",
        ]:
            (target / folder).mkdir(parents=True, exist_ok=True)
        return target


# -----------------------------------------------------------------------------
# Media analysis
# -----------------------------------------------------------------------------


class MediaAnalyzer:
    def __init__(self, content_system: ContentSystem):
        self.content_system = content_system
        self.proxy_dir = content_system.paths["library"] / "proxy_previews"
        self.proxy_dir.mkdir(parents=True, exist_ok=True)

    def analyze(self, asset: Asset) -> MediaAnalysis:
        path = Path(asset.path)
        try:
            if asset.media_type == "image":
                analysis = self._analyze_image(path)
            elif asset.media_type == "video":
                analysis = self._analyze_video(path)
            elif asset.media_type == "audio":
                analysis = self._analyze_audio(path)
            else:
                analysis = MediaAnalysis(analysis_notes=["Unsupported media type."])
        except Exception as exc:
            analysis = MediaAnalysis(analysis_notes=[f"Analysis failed: {exc}"])
        if not analysis.before_after_hint:
            analysis.before_after_hint = self._infer_before_after(path.stem.lower())
        analysis.split_screen_suitability = self._split_screen_score(analysis)
        analysis.talking_head_likelihood = self._talking_head_score(analysis)
        return analysis

    def detect_pair_suggestions(self, assets: List[Asset]) -> List[PairSuggestion]:
        suggestions: List[PairSuggestion] = []
        for i, a in enumerate(assets):
            for b in assets[i + 1 :]:
                pair = self._score_pair(a, b)
                if pair:
                    suggestions.append(pair)
        suggestions.sort(key=lambda p: p.score, reverse=True)
        return suggestions[:12]

    def _score_pair(self, a: Asset, b: Asset) -> Optional[PairSuggestion]:
        if a.media_type != b.media_type:
            return None
        hint_a = a.analysis.before_after_hint or self._infer_before_after(Path(a.path).stem.lower())
        hint_b = b.analysis.before_after_hint or self._infer_before_after(Path(b.path).stem.lower())
        name_a = self._normalize_pair_key(Path(a.path).stem)
        name_b = self._normalize_pair_key(Path(b.path).stem)
        score = 0.0
        reasons: List[str] = []
        if name_a and name_a == name_b:
            score += 2.4
            reasons.append("matching normalized filenames")
        if {hint_a, hint_b} == {"before", "after"}:
            score += 2.4
            reasons.append("before/after hints")
        if a.analysis.dominant_orientation and a.analysis.dominant_orientation == b.analysis.dominant_orientation:
            score += 0.4
            reasons.append("matching orientation")
        if a.analysis.duration and b.analysis.duration:
            diff = abs(a.analysis.duration - b.analysis.duration)
            if diff <= 1.5:
                score += 1.2
                reasons.append("similar duration")
            elif diff <= 4.0:
                score += 0.5
                reasons.append("compatible duration")
        if a.analysis.split_screen_suitability > 0.25 and b.analysis.split_screen_suitability > 0.25:
            score += 0.4
            reasons.append("split-screen friendly")
        if score < 2.0:
            return None
        if hint_a == "before" and hint_b == "after":
            before, after = a.asset_id, b.asset_id
        elif hint_a == "after" and hint_b == "before":
            before, after = b.asset_id, a.asset_id
        else:
            before, after = a.asset_id, b.asset_id
        return PairSuggestion(before, after, round(score, 3), ", ".join(reasons))

    def _normalize_pair_key(self, stem: str) -> str:
        value = stem.lower()
        value = re.sub(r"\b(before|after|master|premaster|mix|final|original|ref|comparison|compare)\b", "", value)
        value = re.sub(r"[_\-\s]+", " ", value).strip()
        return value

    def _infer_before_after(self, value: str) -> str:
        if re.search(r"\b(before|premaster|original|mix|unmastered|raw)\b", value):
            return "before"
        if re.search(r"\b(after|master|final|remaster|processed)\b", value):
            return "after"
        return ""

    def _infer_before_after_from_text(self, value: str) -> str:
        normalized = (value or "").lower()
        if not normalized:
            return ""
        phrase_rules = [
            (r"before\s*[/\-]\s*after", "before"),
            (r"before\s+(?:the\s+)?master(?:ing|ed)?", "before"),
            (r"after\s+(?:the\s+)?master(?:ing|ed)?", "after"),
            (r"before\s+master", "before"),
            (r"after\s+master", "after"),
            (r"premaster", "before"),
            (r"pre\s*master", "before"),
            (r"unmastered", "before"),
            (r"mastered", "after"),
            (r"raw\s*[/\-]\s*mastered", "before"),
            (r"mix\s*[/\-]\s*master", "before"),
            (r"before\s+and\s+after", "before"),
            (r"original\s*[/\-]\s*mastered", "before"),
            (r"a\s*/\s*b", "before"),
            (r"\bab comparison\b", "before"),
            (r"\bcomparison\b", "before"),
            (r"\bcompare\b", "before"),
            (r"\bversus\b", "before"),
            (r"\bvs\.?\b", "before"),
            (r"hear\s+the\s+difference", "before"),
            (r"listen\s+to\s+the\s+difference", "before"),
        ]
        for pattern, result in phrase_rules:
            if re.search(pattern, normalized):
                return result
        return self._infer_before_after(normalized)

    def _has_comparison_intent(self, value: str) -> bool:
        normalized = (value or "").lower()
        if not normalized:
            return False
        comparison_patterns = [
            r"before\s*[/\-]\s*after",
            r"before\s+(?:the\s+)?master(?:ing|ed)?",
            r"after\s+(?:the\s+)?master(?:ing|ed)?",
            r"\ba\s*/\s*b\b",
            r"\bab comparison\b",
            r"\bcomparison\b",
            r"\bcompare\b",
            r"\bversus\b",
            r"\bvs\.?\b",
            r"hear\s+the\s+difference",
            r"listen\s+to\s+the\s+difference",
            r"raw\s*[/\-]\s*mastered",
            r"mix\s*[/\-]\s*master",
            r"original\s*[/\-]\s*mastered",
            r"pre\s*master",
            r"premaster",
            r"unmastered",
            r"mastered",
        ]
        return any(re.search(pattern, normalized) for pattern in comparison_patterns)

    def _video_ocr_sample_times(self, duration: float) -> List[float]:
        duration = float(duration or 0.0)
        if duration <= 0.25:
            return [0.0]
        seed_points = [0.08, 0.16, 0.28, 0.40, 0.52, 0.64, 0.76, 0.88]
        absolute_points = [0.10, 0.35, 0.75, 1.50, 3.00, 5.00]
        sample_times: List[float] = []
        for point in absolute_points:
            if point < duration - 0.05:
                sample_times.append(point)
        for ratio in seed_points:
            t = max(0.0, min(duration - 0.05, duration * ratio))
            sample_times.append(t)
        unique_times: List[float] = []
        seen: set[str] = set()
        for t in sorted(sample_times):
            key = f"{t:.2f}"
            if key not in seen:
                seen.add(key)
                unique_times.append(round(t, 2))
        return unique_times[:10] or [0.0]

    def _ocr_variants_from_frame(self, frame_path: Path) -> List[Any]:
        if Image is None or ImageOps is None:
            return []
        variants: List[Any] = []
        with Image.open(frame_path) as raw_img:
            img = ImageOps.exif_transpose(raw_img).convert("RGB")
            gray = ImageOps.grayscale(img)
            gray = ImageOps.autocontrast(gray)
            w, h = gray.size
            crop_boxes = [
                (0, 0, w, h),
                (0, 0, w, max(1, int(h * 0.45))),
                (0, int(h * 0.10), w, int(h * 0.65)),
                (0, int(h * 0.55), w, h),
                (int(w * 0.05), int(h * 0.15), int(w * 0.95), int(h * 0.85)),
            ]
            for box in crop_boxes:
                crop = gray.crop(box)
                upscaled = crop.resize((max(1, crop.width * 2), max(1, crop.height * 2)))
                variants.append(upscaled)
                thresholded = upscaled.point(lambda p: 255 if p > 160 else 0)
                variants.append(thresholded)
        return variants

    def _extract_video_ocr_text(self, path: Path, existing_duration: float = 0.0) -> Tuple[str, List[str]]:
        notes: List[str] = []
        ffmpeg_exe = resolve_ffmpeg_executable()
        if not ffmpeg_exe:
            return "", ["OCR skipped: ffmpeg unavailable for frame sampling."]
        if Image is None:
            return "", ["OCR skipped: Pillow unavailable."]
        tesseract_exe = resolve_tesseract_executable()
        if pytesseract is None and not tesseract_exe:
            return "", ["OCR skipped: pytesseract / tesseract unavailable."]
        if pytesseract is not None and tesseract_exe:
            try:
                setattr(pytesseract.pytesseract, "tesseract_cmd", tesseract_exe)
            except Exception:
                pass

        duration = float(existing_duration or 0.0)
        if duration <= 0.0:
            ffprobe_path = resolve_ffprobe_executable()
            if ffprobe_path:
                try:
                    result = subprocess.run(
                        [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                        capture_output=True,
                        text=True,
                        timeout=4,
                        check=False,
                    )
                    if result.returncode == 0 and result.stdout:
                        payload = json.loads(result.stdout)
                        probed = float(((payload.get("format") or {}).get("duration") or 0.0))
                        if probed > 0.0:
                            duration = probed
                except Exception:
                    pass

        frame_texts: List[str] = []
        sample_times = self._video_ocr_sample_times(duration)
        with tempfile.TemporaryDirectory(prefix="ed_ocr_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            for idx, t in enumerate(sample_times, start=1):
                frame_path = tmp_path / f"frame_{idx}.png"
                try:
                    result = subprocess.run(
                        [ffmpeg_exe, "-y", "-ss", str(t), "-i", str(path), "-frames:v", "1", "-vf", "scale=1600:-1", str(frame_path)],
                        capture_output=True,
                        text=True,
                        timeout=8,
                        check=False,
                    )
                    if result.returncode != 0 or not frame_path.exists() or frame_path.stat().st_size == 0:
                        continue
                except Exception as exc:
                    notes.append(f"OCR frame sample {idx} skipped: {type(exc).__name__}: {exc}")
                    continue
                try:
                    variant_texts: List[str] = []
                    if pytesseract is not None:
                        for variant in self._ocr_variants_from_frame(frame_path):
                            for psm in (6, 11):
                                try:
                                    raw_text = pytesseract.image_to_string(variant, config=f"--psm {psm}")
                                except Exception:
                                    raw_text = ""
                                cleaned = re.sub(r"\s+", " ", (raw_text or "")).strip()
                                if cleaned:
                                    variant_texts.append(cleaned)
                    elif tesseract_exe:
                        ocr = subprocess.run(
                            [tesseract_exe, str(frame_path), "stdout", "--psm", "6"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            check=False,
                        )
                        if ocr.returncode == 0:
                            cleaned = re.sub(r"\s+", " ", (ocr.stdout or "")).strip()
                            if cleaned:
                                variant_texts.append(cleaned)
                    for cleaned in variant_texts:
                        if len(cleaned) >= 4:
                            frame_texts.append(cleaned)
                except Exception as exc:
                    notes.append(f"OCR sample {idx} failed: {type(exc).__name__}: {exc}")
        unique_bits: List[str] = []
        seen: set[str] = set()
        for bit in frame_texts:
            short = bit[:240]
            normalized_short = short.lower()
            if normalized_short not in seen:
                seen.add(normalized_short)
                unique_bits.append(short)
        if unique_bits:
            notes.append(f"OCR extracted on-screen text from {len(unique_bits)} sampled video frame variant(s).")
        else:
            notes.append("OCR found no usable on-screen text in sampled frames.")
        return " | ".join(unique_bits[:6]), notes

    def _extract_video_transcript_text(self, path: Path) -> Tuple[str, List[str]]:
        notes: List[str] = []
        if whisper is None:
            return "", ["Transcript skipped: Whisper unavailable."]
        ffmpeg_exe = resolve_ffmpeg_executable()
        if not ffmpeg_exe:
            return "", ["Transcript skipped: ffmpeg unavailable for audio extraction."]
        try:
            with tempfile.TemporaryDirectory(prefix="ed_transcript_") as tmp_dir:
                wav_path = Path(tmp_dir) / "audio.wav"
                extracted = subprocess.run(
                    [ffmpeg_exe, "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-t", "20", str(wav_path)],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if extracted.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
                    return "", ["Transcript skipped: audio extraction produced no usable wav."]
                model = getattr(self, "_whisper_model", None)
                if model is None:
                    self._whisper_model = whisper.load_model("tiny")
                    model = self._whisper_model
                result = model.transcribe(str(wav_path), fp16=False, verbose=False)
                transcript = re.sub(r"\s+", " ", (result.get("text") or "")).strip()
                if transcript:
                    notes.append("Transcript extracted from video audio.")
                else:
                    notes.append("Transcript extraction returned no usable speech text.")
                return transcript[:500], notes
        except Exception as exc:
            return "", [f"Transcript skipped: {type(exc).__name__}: {exc}"]


    def _analyze_image(self, path: Path) -> MediaAnalysis:
        analysis = MediaAnalysis(before_after_hint=self._infer_before_after(path.stem.lower()))
        if not Image:
            analysis.analysis_notes.append("Pillow unavailable; image analysis limited.")
            return analysis
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            analysis.width, analysis.height = img.size
            analysis.dominant_orientation = orientation_name(analysis.width, analysis.height)
            stat = ImageStat.Stat(img)
            analysis.brightness = float(sum(stat.mean) / len(stat.mean) / 255.0)
            analysis.contrast = float(sum(stat.stddev) / len(stat.stddev) / 128.0)
            analysis.preview_path = self._write_preview(img, path.stem)
            analysis.analysis_notes.append("Measured image brightness and contrast.")
        return analysis

    def _analyze_audio(self, path: Path) -> MediaAnalysis:
        analysis = MediaAnalysis(has_audio=True, before_after_hint=self._infer_before_after(path.stem.lower()))
        suffix = path.suffix.lower()
        if suffix == ".wav":
            with wave.open(str(path), "rb") as wav_file:
                rate = wav_file.getframerate()
                total_frames = wav_file.getnframes()
                width = wav_file.getsampwidth()
                sample_frames = min(total_frames, rate * 10)
                frames = wav_file.readframes(sample_frames)
                analysis.duration = total_frames / max(1, rate)
                if frames:
                    rms = rms_from_pcm(frames, width)
                    analysis.audio_loudness = min(1.0, rms / 12000.0)
                    analysis.waveform_path = self._waveform_from_bytes(frames, width, path.stem)
            analysis.speech_likelihood = self._speech_from_audio(analysis.audio_loudness, analysis.duration)
            analysis.analysis_notes.append("Sampled WAV loudness.")
            return analysis
        if moviepy and AudioFileClip and np is not None:
            clip = AudioFileClip(str(path))
            try:
                analysis.duration = float(clip.duration or 0.0)
                sample = clip.subclipped(0, min(8.0, max(0.5, analysis.duration))).to_soundarray(fps=11025)
                if sample.size:
                    mono = sample.mean(axis=1) if sample.ndim > 1 else sample
                    rms = float(np.sqrt(np.mean(mono.astype("float64") ** 2)))
                    analysis.audio_loudness = min(1.0, rms * 6.0)
                    analysis.waveform_path = self._waveform_from_array(mono, path.stem)
            finally:
                clip.close()
            analysis.speech_likelihood = self._speech_from_audio(analysis.audio_loudness, analysis.duration)
            analysis.analysis_notes.append("Sampled audio waveform via moviepy.")
            return analysis
        analysis.analysis_notes.append("Audio analysis limited without supported decoder.")
        return analysis

    def _analyze_video(self, path: Path) -> MediaAnalysis:
        analysis = MediaAnalysis(before_after_hint=self._infer_before_after(path.stem.lower()))
        analysis.analysis_notes.append("Fast intake mode: skipping video decode during import to prevent long stalls.")
        ffprobe_path = shutil.which("ffprobe")
        if ffprobe_path:
            try:
                result = subprocess.run(
                    [
                        ffprobe_path,
                        "-v", "error",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                        "-of", "json",
                        str(path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if result.returncode == 0 and result.stdout:
                    payload = json.loads(result.stdout)
                    stream = (payload.get("streams") or [{}])[0]
                    fmt = payload.get("format") or {}
                    analysis.width = int(stream.get("width") or 0)
                    analysis.height = int(stream.get("height") or 0)
                    analysis.dominant_orientation = orientation_name(analysis.width, analysis.height)
                    duration = fmt.get("duration")
                    if duration is not None:
                        analysis.duration = float(duration or 0.0)
                    rate = stream.get("r_frame_rate") or "0/1"
                    try:
                        num, den = rate.split("/")
                        den_v = float(den) if float(den) else 1.0
                        analysis.fps = float(num) / den_v
                    except Exception:
                        analysis.fps = 0.0
                    analysis.analysis_notes.append("ffprobe metadata read in fast intake mode.")
            except Exception as exc:
                analysis.analysis_notes.append(f"ffprobe metadata skipped: {type(exc).__name__}: {exc}")
        if not analysis.preview_path:
            analysis.preview_path = self.build_initial_asset_preview(path, "video", path.stem)
        analysis.speech_likelihood = 0.0
        analysis.talking_head_likelihood = 0.0
        analysis.split_screen_suitability = self._split_screen_score(analysis)
        return analysis


    def build_initial_asset_preview(self, path: Path, media_type: str, title: str = "") -> str:
        if media_type == "image" and Image is not None:
            try:
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    return self._write_preview(img, path.stem)
            except Exception:
                pass
        return self._write_media_placeholder(title or path.name, media_type, heading="Imported Asset", status="Preview pending")

    def _write_media_placeholder(self, title: str, media_type: str, heading: str = "Media Added", status: str = "Preview pending") -> str:
        if not Image or not ImageDraw:
            return ""
        image = Image.new("RGB", (320, 220), (20, 20, 20))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 319, 219), outline=(90, 90, 90), width=2)
        title_font = get_preview_font(18, bold=True)
        body_font = get_preview_font(15)
        draw.text((16, 18), heading[:24], fill=(255, 255, 255), font=title_font)
        draw.text((16, 64), f"Type: {media_type}", fill=(210, 210, 210), font=body_font)
        label = (title or media_type or "media")[:28]
        draw.text((16, 98), label, fill=(210, 210, 210), font=body_font)
        draw.text((16, 154), status[:28], fill=(160, 200, 255), font=body_font)
        preview_path = self.proxy_dir / f"{slugify(Path(title or media_type).stem if title else media_type)}_{now_stamp()}_placeholder.png"
        image.save(preview_path)
        return str(preview_path)

    def enrich_video_preview_and_duration(self, path: Path, existing_duration: float = 0.0) -> Tuple[str, float, List[str]]:
        notes: List[str] = []
        preview_path = ""
        duration = float(existing_duration or 0.0)

        ffprobe_path = resolve_ffprobe_executable()
        if ffprobe_path:
            try:
                result = subprocess.run(
                    [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    check=False,
                )
                if result.returncode == 0 and result.stdout:
                    payload = json.loads(result.stdout)
                    fmt = payload.get("format") or {}
                    probed = fmt.get("duration")
                    if probed is not None:
                        duration = float(probed or 0.0)
                        if duration > 0.0:
                            notes.append("Duration enriched via ffprobe.")
            except Exception as exc:
                notes.append(f"ffprobe duration skipped: {type(exc).__name__}: {exc}")
        else:
            notes.append("ffprobe unavailable for duration probe.")

        try:
            preview_path, source = self._reference_video_preview(path)
            if preview_path:
                notes.append(f"Poster enriched via {source}.")
        except Exception as exc:
            notes.append(f"Poster enrichment skipped: {type(exc).__name__}: {exc}")

        if duration <= 0.0 and moviepy and VideoFileClip:
            try:
                clip = VideoFileClip(str(path))
                try:
                    duration = float(getattr(clip, "duration", 0.0) or 0.0)
                    if duration > 0.0:
                        notes.append("Duration enriched via moviepy.")
                finally:
                    clip.close()
            except Exception as exc:
                notes.append(f"moviepy duration skipped: {type(exc).__name__}: {exc}")

        if not preview_path:
            notes.append("Poster enrichment produced no usable preview file.")
        if duration <= 0.0:
            notes.append("Duration enrichment produced no usable duration.")

        return preview_path, duration, notes

    def enrich_video_intent_signals(self, path: Path, existing_duration: float = 0.0) -> Tuple[str, float, str, str, str, List[str]]:
        preview_path, duration, notes = self.enrich_video_preview_and_duration(path, existing_duration)
        ocr_text, ocr_notes = self._extract_video_ocr_text(path, duration)
        transcript_text, transcript_notes = self._extract_video_transcript_text(path)
        notes.extend(ocr_notes)
        notes.extend(transcript_notes)
        combined_text = " ".join([Path(path).stem, ocr_text, transcript_text]).strip()
        before_after_hint = self._infer_before_after_from_text(combined_text)
        if before_after_hint:
            notes.append(f"Intent clue detected from OCR/transcript text: {before_after_hint}.")
        elif combined_text:
            notes.append("OCR/transcript enrichment found text, but no explicit before/after wording.")
        return preview_path, duration, ocr_text, transcript_text, before_after_hint, notes

    def build_reference_preview(self, path: Path) -> Tuple[str, str, str]:
        media_type = infer_media_type(path)
        note = "Added without a generated preview yet."
        preview_path = ""
        try:
            if media_type == "image":
                if Image:
                    with Image.open(path) as img:
                        img = ImageOps.exif_transpose(img).convert("RGB")
                        preview_path = self._write_preview(img, f"reference_{path.stem}")
                        note = "Image preview ready."
                else:
                    note = "Pillow unavailable, so image preview could not be generated."
            elif media_type == "video":
                preview_path, preview_source = self._reference_video_preview(path)
                if preview_path:
                    note = f"Video thumbnail ready ({preview_source})."
                else:
                    preview_path = self._write_media_placeholder(path.name, media_type, heading="Reference Added", status="No thumbnail yet")
                    note = "Video added, but no thumbnail could be generated."
            elif media_type == "audio":
                audio_analysis = self._analyze_audio(path)
                preview_path = audio_analysis.waveform_path
                if preview_path:
                    note = "Audio waveform preview ready."
                else:
                    preview_path = self._write_media_placeholder(path.name, media_type, heading="Reference Added", status="No waveform yet")
                    note = "Audio added, but no waveform preview could be generated."
            else:
                preview_path = self._write_media_placeholder(path.name, media_type, heading="Reference Added", status="Preview ready")
                note = f"{media_type.title()} reference added."
        except Exception as exc:
            preview_path = self._write_media_placeholder(path.name, media_type, heading="Reference Added", status="Preview failed")
            note = f"Added, but preview generation failed: {exc}"
        if not preview_path:
            preview_path = self._write_media_placeholder(path.name, media_type, heading="Reference Added", status="Preview unavailable")
        # Extract dominant accent color for style emulation
        accent_hex = self._extract_dominant_accent(path, media_type, preview_path)
        return preview_path, media_type, note, accent_hex

    def _extract_dominant_accent(self, path: Path, media_type: str, preview_path: str) -> str:
        """
        Extract the most visually prominent non-neutral color from a reference image
        and return it as a hex string for use in caption accent emulation.
        Falls back to empty string if PIL is unavailable or analysis fails.
        """
        try:
            if not Image:
                return ""
            img_path = preview_path if preview_path and Path(preview_path).exists() else str(path)
            if not Path(img_path).exists():
                return ""
            with Image.open(img_path) as img:
                img = img.convert("RGB").resize((80, 80))
                pixels = list(img.getdata())
            # Score pixels by saturation — most saturated wins
            best_score = 0
            best = (179, 45, 46)  # fallback: ED red
            for r, g, b in pixels:
                mn, mx = min(r, g, b), max(r, g, b)
                sat = (mx - mn) / mx if mx > 0 else 0
                lum = (r + g + b) / 765
                # Skip near-white, near-black, and near-grey
                if lum < 0.08 or lum > 0.92 or sat < 0.25:
                    continue
                score = sat * (1 - abs(lum - 0.5))
                if score > best_score:
                    best_score = score
                    best = (r, g, b)
            return "#{:02x}{:02x}{:02x}".format(*best)
        except Exception:
            return ""

    def _reference_video_preview(self, path: Path) -> Tuple[str, str]:
        preview_path = self._reference_video_preview_ffmpeg(path)
        if preview_path:
            return preview_path, "ffmpeg"
        if moviepy and VideoFileClip and Image is not None:
            try:
                clip = VideoFileClip(str(path))
                try:
                    duration = float(getattr(clip, "duration", 0.0) or 0.0)
                    target_t = 0.0 if duration <= 0.2 else max(0.0, min(duration - 0.05, max(0.25, duration * 0.35)))
                    frame = clip.get_frame(target_t)
                    preview = Image.fromarray(frame.astype("uint8"))
                    return self._write_preview(preview, f"reference_{path.stem}"), "moviepy"
                finally:
                    clip.close()
            except Exception:
                pass
        return "", ""

    def _reference_video_preview_ffmpeg(self, path: Path) -> str:
        ffmpeg_path = resolve_ffmpeg_executable()
        if not ffmpeg_path:
            return ""
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
                temp_path = handle.name
            commands = [
                [ffmpeg_path, "-y", "-ss", "00:00:00.50", "-i", str(path), "-frames:v", "1", "-vf", "thumbnail,scale=480:-1", temp_path],
                [ffmpeg_path, "-y", "-i", str(path), "-frames:v", "1", "-vf", "thumbnail,scale=480:-1", temp_path],
                [ffmpeg_path, "-y", "-i", str(path), "-frames:v", "1", "-vf", "scale=480:-1", temp_path],
            ]
            for command in commands:
                try:
                    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=8)
                    if result.returncode != 0:
                        continue
                    temp_file = Path(temp_path)
                    if not temp_file.exists() or temp_file.stat().st_size <= 0:
                        continue
                    if Image:
                        with Image.open(temp_file) as img:
                            img = ImageOps.exif_transpose(img).convert("RGB")
                            return self._write_preview(img, f"reference_{path.stem}")
                    output_path = self.proxy_dir / f"{slugify(path.stem)}_{now_stamp()}_ffmpeg_preview.jpg"
                    shutil.move(temp_path, output_path)
                    temp_path = ""
                    return str(output_path)
                except Exception:
                    continue
            return ""
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _sample_times(self, duration: float) -> List[float]:
        if duration <= 0.01:
            return [0.0]
        points = [0.12, 0.32, 0.52, 0.72]
        return [max(0.0, min(duration - 0.05, duration * p)) for p in points]

    def _write_preview(self, image, stem: str) -> str:
        if not Image:
            return ""
        thumb = image.copy()
        thumb.thumbnail((320, 220))
        path = self.proxy_dir / f"{slugify(stem)}_{now_stamp()}_preview.png"
        thumb.save(path)
        return str(path)

    def _waveform_from_bytes(self, raw_frames: bytes, sample_width: int, stem: str) -> str:
        if not Image or not raw_frames:
            return ""
        width, height = 320, 90
        image = Image.new("RGB", (width, height), (16, 16, 16))
        draw = ImageDraw.Draw(image)
        samples: List[int] = []
        if sample_width == 1:
            samples = [b - 128 for b in raw_frames[: width * 10]]
        elif sample_width == 2:
            for i in range(0, min(len(raw_frames), width * 40), 2):
                samples.append(int.from_bytes(raw_frames[i:i+2], byteorder="little", signed=True))
        if not samples:
            return ""
        chunk = max(1, len(samples) // width)
        center = height // 2
        for x in range(width):
            seg = samples[x * chunk : min(len(samples), (x + 1) * chunk)] or [0]
            peak = min(1.0, max(abs(v) for v in seg) / 32768.0)
            line_h = int(peak * (height // 2 - 2))
            draw.line((x, center - line_h, x, center + line_h), fill=(220, 220, 220))
        path = self.proxy_dir / f"{slugify(stem)}_{now_stamp()}_wave.png"
        image.save(path)
        return str(path)

    def _waveform_from_array(self, mono, stem: str) -> str:
        if not Image or np is None:
            return ""
        arr = np.asarray(mono, dtype="float64")
        if arr.size == 0:
            return ""
        width, height = 320, 90
        image = Image.new("RGB", (width, height), (16, 16, 16))
        draw = ImageDraw.Draw(image)
        center = height // 2
        chunk = max(1, arr.size // width)
        for x in range(width):
            seg = arr[x * chunk : min(arr.size, (x + 1) * chunk)]
            peak = float(np.max(np.abs(seg))) if seg.size else 0.0
            line_h = int(min(1.0, peak) * (height // 2 - 2))
            draw.line((x, center - line_h, x, center + line_h), fill=(220, 220, 220))
        path = self.proxy_dir / f"{slugify(stem)}_{now_stamp()}_wave.png"
        image.save(path)
        return str(path)

    def _speech_from_audio(self, loudness: float, duration: float) -> float:
        score = 0.12 + min(0.45, loudness * 0.65)
        if 5.0 <= duration <= 45.0:
            score += 0.20
        return max(0.0, min(1.0, score))

    def _speech_from_video(self, analysis: MediaAnalysis) -> float:
        score = 0.08
        score += min(0.45, analysis.audio_loudness * 0.55)
        if analysis.motion_score < 0.10:
            score += 0.18
        if analysis.dominant_orientation == "vertical":
            score += 0.12
        if 0.25 <= analysis.brightness <= 0.8:
            score += 0.08
        if 4.0 <= analysis.duration <= 30.0:
            score += 0.08
        return max(0.0, min(1.0, score))

    def _talking_head_score(self, analysis: MediaAnalysis) -> float:
        score = 0.0
        score += min(0.45, analysis.speech_likelihood * 0.5)
        if analysis.dominant_orientation == "vertical":
            score += 0.20
        if analysis.motion_score < 0.12:
            score += 0.20
        if 0.28 <= analysis.brightness <= 0.8:
            score += 0.10
        return max(0.0, min(1.0, score))

    def _split_screen_score(self, analysis: MediaAnalysis) -> float:
        score = 0.0
        if analysis.dominant_orientation in {"horizontal", "square"}:
            score += 0.35
        if 0.1 <= analysis.contrast <= 0.9:
            score += 0.20
        if analysis.motion_score <= 0.25:
            score += 0.25
        if analysis.width >= 900:
            score += 0.20
        return max(0.0, min(1.0, score))


# -----------------------------------------------------------------------------
# Draft generation
# -----------------------------------------------------------------------------


class DraftGenerator:
    def __init__(self, project: ProjectState):
        self.project = project
        self.asset_map = {asset.asset_id: asset for asset in project.assets}

    def generate(self) -> List[DraftOption]:
        assets = self.project.assets
        if not assets:
            return []
        hook_rank = sorted(assets, key=self._hook_score, reverse=True)
        proof_rank = sorted(assets, key=self._proof_score, reverse=True)
        cta_rank = sorted(assets, key=self._cta_score, reverse=True)
        support_rank = [a for a in assets if a.asset_id not in {x.asset_id for x in hook_rank[:3] + proof_rank[:3] + cta_rank[:3]}]

        pair = self.project.pair_suggestions[0] if self.project.pair_suggestions else None
        drafts: List[DraftOption] = []
        variants = [
            ("Best Performer", "Best Draft", "balanced"),
            ("More Proof-Heavy", "Proof Draft", "proof"),
            ("More Direct CTA", "CTA Draft", "cta"),
            ("More Educational", "Educational Draft", "educational"),
        ]
        for idx, (name, label, style_tag) in enumerate(variants, start=1):
            hook_asset = hook_rank[min(idx - 1, len(hook_rank) - 1)] if idx > 1 else hook_rank[0]
            proof_asset = proof_rank[0]
            cta_asset = cta_rank[0]
            cards: List[StoryboardCard] = [StoryboardCard(asset_id=hook_asset.asset_id, role="hook")]

            if pair and (self.project.content_goal in {"Before / After Comparison", "Mastering Promo"} or self.project.template_family == "Smart Auto"):
                cards.append(
                    StoryboardCard(
                        asset_id=pair.before_asset_id,
                        role="proof",
                        use_split_screen=(style_tag in {"balanced", "proof"}),
                        pair_asset_id=pair.after_asset_id,
                    )
                )
            else:
                if support_rank:
                    support = support_rank[min(idx - 1, len(support_rank) - 1)]
                    cards.append(StoryboardCard(asset_id=support.asset_id, role="support"))
                if proof_asset.asset_id not in {c.asset_id for c in cards}:
                    cards.append(StoryboardCard(asset_id=proof_asset.asset_id, role="proof"))

            if style_tag == "educational":
                extra_support = next((a for a in support_rank if a.asset_id not in {c.asset_id for c in cards}), None)
                if extra_support:
                    cards.insert(1, StoryboardCard(asset_id=extra_support.asset_id, role="support"))
            if style_tag == "cta":
                talking = next((a for a in cta_rank if a.analysis.talking_head_likelihood >= 0.35), None)
                if talking:
                    cta_asset = talking

            if cta_asset.asset_id not in {c.asset_id for c in cards}:
                cards.append(StoryboardCard(asset_id=cta_asset.asset_id, role="cta"))

            runtime = self._estimate_runtime(cards)
            hook_opts, title_opts, cta_opts = self._copy_options(style_tag)
            rationale = self._rationale(style_tag, hook_asset, cta_asset, pair)
            confidence = min(0.96, 0.58 + 0.08 * idx + (0.07 if pair else 0.0))
            drafts.append(
                DraftOption(
                    draft_id=f"draft_{idx}_{now_stamp()}",
                    name=name,
                    label=label,
                    storyboard_cards=cards,
                    runtime_estimate=runtime,
                    recommended_bundle=self.project.publish_bundle,
                    hook_options=hook_opts,
                    title_options=title_opts,
                    cta_options=cta_opts,
                    rationale=rationale,
                    confidence_score=round(confidence, 2),
                    style_tag=style_tag,
                )
            )
        return drafts

    def candidates_for_role(self, role: str) -> List[Tuple[Asset, float]]:
        if role == "hook":
            ranked = sorted(self.project.assets, key=self._hook_score, reverse=True)
            return [(a, round(self._hook_score(a), 2)) for a in ranked[:10]]
        if role == "proof":
            ranked = sorted(self.project.assets, key=self._proof_score, reverse=True)
            return [(a, round(self._proof_score(a), 2)) for a in ranked[:10]]
        if role == "cta":
            ranked = sorted(self.project.assets, key=self._cta_score, reverse=True)
            return [(a, round(self._cta_score(a), 2)) for a in ranked[:10]]
        ranked = sorted(self.project.assets, key=self._support_score, reverse=True)
        return [(a, round(self._support_score(a), 2)) for a in ranked[:10]]

    def _hook_score(self, asset: Asset) -> float:
        a = asset.analysis
        score = asset.rating * 0.6 + (1.4 if asset.favorite else 0.0)
        score += 1.0 if asset.media_type == "video" else 0.35 if asset.media_type == "image" else 0.0
        score += min(3.0, a.motion_score * 12.0)
        score += min(1.6, a.contrast * 2.2)
        score += 0.7 if 0.22 <= a.brightness <= 0.82 else 0.0
        if 0 < a.duration <= 6.0:
            score += 1.0
        if a.dominant_orientation == "vertical":
            score += 0.35
        return score

    def _proof_score(self, asset: Asset) -> float:
        a = asset.analysis
        score = asset.rating * 0.55 + (1.3 if asset.favorite else 0.0)
        score += 2.0 if a.before_after_hint else 0.0
        score += 1.2 if asset.media_type in {"video", "audio"} else 0.2
        score += min(1.2, a.audio_loudness * 1.8)
        score += 0.8 if 3.0 <= a.duration <= 18.0 else 0.0
        score += min(1.1, a.split_screen_suitability * 1.4)
        return score

    def _cta_score(self, asset: Asset) -> float:
        a = asset.analysis
        score = asset.rating * 0.5 + (1.3 if asset.favorite else 0.0)
        score += min(3.2, a.speech_likelihood * 4.0)
        score += min(1.3, a.talking_head_likelihood * 2.0)
        score += 0.7 if a.motion_score < 0.12 else 0.0
        score += 0.7 if 3.0 <= a.duration <= 20.0 else 0.0
        return score

    def _support_score(self, asset: Asset) -> float:
        a = asset.analysis
        score = asset.rating * 0.45 + (0.8 if asset.favorite else 0.0)
        score += 0.8 if asset.media_type in {"video", "image"} else 0.0
        score += min(1.0, a.motion_score * 5.0)
        score += 0.5 if 2.0 <= a.duration <= 12.0 else 0.0
        return score

    def _estimate_runtime(self, cards: List[StoryboardCard]) -> float:
        total = 0.0
        for card in cards:
            asset = self.asset_map.get(card.asset_id)
            total += card.effective_duration(asset)
        return round(total, 1)

    def _copy_options(self, style_tag: str) -> Tuple[List[str], List[str], List[str]]:
        goal = self.project.content_goal
        bundle_cta = self.project.cta_text
        hook_map = {
            "Mastering Promo": [
                "If the mix feels close but still does not hit, this is usually the gap.",
                "More loudness is not the same thing as more impact.",
                "This is what changes when the finish finally lands right.",
            ],
            "Before / After Comparison": [
                "Listen to what changed in the master.",
                "Before. After. Same source. Different finish.",
                "This is the difference the final step made.",
            ],
            "Educational Tip": [
                "A louder file is not the same thing as more impact.",
                "A dense mix still needs somewhere for the record to move.",
                "Translation problems usually reveal themselves here first.",
            ],
            "Client Testimonial": [
                "This is what changed for the band after mastering.",
                "The point is not louder. The point is control and translation.",
                "Proof matters more than promises.",
            ],
            "Offer / CTA": [
                "Guessing will not fix the mix.",
                "If this describes your mix, the next step should be clear.",
                "The right next step depends on what the mix is actually missing.",
            ],
            "New Release Teaser": [
                "This is what changed when the record finally hit right.",
                "The release lands differently when the finish is dialed in.",
                "Heavy music should feel controlled and dangerous at the same time.",
            ],
        }
        title_map = {
            "Mastering Promo": [
                "Heavy music mastering built for impact, control, and translation.",
                "More authority. Better translation. Stronger finish.",
                "A clearer finish for heavy records.",
            ],
            "Before / After Comparison": [
                "Same song. Different finish.",
                "Before / after. Same source. Better result.",
                "What changed in the master.",
            ],
            "Educational Tip": [
                "What your mix is telling you before mastering.",
                "Why impact and loudness are not the same thing.",
                "Where heavy mixes lose translation.",
            ],
            "Client Testimonial": [
                "What changed after the master was finished right.",
                "Client proof: better translation, more impact.",
                "Result-focused mastering proof.",
            ],
            "Offer / CTA": [
                "Not sure what your mix needs yet?",
                "Get clarity on the next step.",
                "Find out what is holding the mix back.",
            ],
            "New Release Teaser": [
                "New master. More impact. Better translation.",
                "The release hits harder when the finish is right.",
                "Hear the difference.",
            ],
        }
        hooks = hook_map.get(goal, ["This is what changes when the next step is right."])
        titles = title_map.get(goal, [f"{goal} built for a clearer next step."])
        ctas = [bundle_cta, "Start Your Project", "Get Your Mastering Quote"]
        if style_tag == "proof":
            hooks = hooks[::-1]
            ctas = ["Listen To Before / After", bundle_cta, "See What Changes In Mastering"]
        elif style_tag == "cta":
            ctas = [bundle_cta, "Send Your Mix", "Book Mastering"]
        elif style_tag == "educational":
            ctas = ["Hear What Your Mix Needs", bundle_cta, "Find The Right Next Step"]
        return hooks[:3], titles[:3], ctas[:3]

    def _rationale(self, style_tag: str, hook_asset: Asset, cta_asset: Asset, pair: Optional[PairSuggestion]) -> str:
        reasons = [f"Strong opener candidate: {hook_asset.title}"]
        if pair and style_tag in {"balanced", "proof"}:
            reasons.append(f"Matched comparison pair detected ({pair.reason})")
        if cta_asset.analysis.talking_head_likelihood >= 0.35:
            reasons.append(f"CTA closer favors likely talking-head content: {cta_asset.title}")
        if style_tag == "educational":
            reasons.append("Sequence leans toward explanation and proof.")
        if style_tag == "cta":
            reasons.append("Sequence leans toward a more direct CTA close.")
        return " | ".join(reasons)


# -----------------------------------------------------------------------------
# Exporter
# -----------------------------------------------------------------------------


class Exporter:
    def __init__(self, content_system: ContentSystem):
        self.content_system = content_system

    def export(self, project: ProjectState, progress: Optional[Callable[[str], None]] = None, export_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        export_dir = self.content_system.next_export_dir(project.project_name)
        archive_dir = export_dir / "09_Archive_Notes"
        package_files: List[str] = []

        project_snapshot_path = export_dir / "08_Project_Files" / "project_snapshot.json"
        safe_json_write(project_snapshot_path, asdict(project))
        package_files.append(str(project_snapshot_path))
        if project.caption_source_path:
            src = Path(project.caption_source_path)
            if src.exists():
                copied_caption = safe_copy(src, export_dir / "07_Captions" / src.name)
                package_files.append(str(copied_caption))

        manifest = {
            "project_name": project.project_name,
            "generated_at": datetime.now().isoformat(),
            "content_goal": project.content_goal,
            "template_family": project.template_family,
            "publish_bundle": project.publish_bundle,
            "selected_draft_id": project.selected_draft_id,
            "draft_count": len(project.drafts),
            "canvases": PUBLISH_BUNDLES.get(project.publish_bundle, ["9x16"]),
            "copy": {"hook": project.hook_text, "title": project.title_text, "cta": project.cta_text},
            "export_decision_notes": project.export_decision_notes,
            "final_approval_locked": project.final_approval_locked,
            "approved_export_source": project.approved_export_source,
            "export_score_weights": project.export_score_weights,
            "dependencies": OPTIONAL_MODULES,
        }
        manifest_path = archive_dir / "export_manifest.json"
        safe_json_write(manifest_path, manifest)
        package_files.append(str(manifest_path))
        if export_snapshot:
            compare_snapshot_path = archive_dir / "export_compare_snapshot.json"
            safe_json_write(compare_snapshot_path, export_snapshot)
            package_files.append(str(compare_snapshot_path))

        notes = [
            f"Project: {project.project_name}",
            f"Goal: {project.content_goal}",
            f"Template family: {project.template_family}",
            f"Bundle: {project.publish_bundle}",
            f"Hook: {project.hook_text}",
            f"Title: {project.title_text}",
            f"CTA: {project.cta_text}",
            "",
            "Automation notes",
            *project.automation_notes,
            "",
            "Export decision notes",
            (project.export_decision_notes or "No decision notes saved."),
            "",
            f"Final approval locked: {project.final_approval_locked}",
            f"Approved export source: {project.approved_export_source or 'None'}",
            f"Weight bias: copy {project.export_score_weights.get('copy', 3)} • proof {project.export_score_weights.get('proof', 3)} • CTA {project.export_score_weights.get('cta', 3)} • platform {project.export_score_weights.get('platform', 2)}",
            "",
            "Selected storyboard",
        ]
        asset_map = {a.asset_id: a for a in project.assets}
        for idx, card in enumerate(project.selected_storyboard, start=1):
            asset = asset_map.get(card.asset_id)
            if not asset:
                continue
            pair_note = ""
            if card.use_split_screen and card.pair_asset_id in asset_map:
                pair_note = f" + {asset_map[card.pair_asset_id].title} (split-screen)"
            notes.append(f"{idx}. {asset.title}{pair_note} [{card.role}] dur={card.effective_duration(asset):.1f}s mute={card.mute_audio}")
        archive_notes_path = archive_dir / "archive_notes.txt"
        archive_notes_path.write_text("\n".join(notes), encoding="utf-8")
        package_files.append(str(archive_notes_path))

        render_reports: List[Dict[str, Any]] = []
        media_outputs: List[str] = []
        if moviepy and VideoFileClip and ImageClip and ColorClip and concatenate_videoclips and project.selected_storyboard:
            canvases = PUBLISH_BUNDLES.get(project.publish_bundle, ["9x16"])
            for canvas_name in canvases:
                if progress:
                    progress(f"Rendering {canvas_name}...")
                report = self._render_canvas(project, export_dir, canvas_name)
                render_reports.append(report)
                if report.get("success"):
                    media_outputs.append(report.get("output_path", ""))
                    if progress:
                        progress(f"Rendered {canvas_name}: {Path(report.get('output_path', '')).name}")
                else:
                    if progress:
                        progress(f"Render issue on {canvas_name}: {report.get('reason', 'unknown render issue')}")
        else:
            render_reports.append({
                "canvas_name": "(none)",
                "success": False,
                "reason": "moviepy unavailable or storyboard missing; exported package without media renders.",
                "output_path": "",
                "clip_count": 0,
                "card_count": len(project.selected_storyboard),
                "card_reports": [],
            })

        render_log_lines = [
            f"Export dir: {export_dir}",
            f"Media outputs created: {len([p for p in media_outputs if p])}",
            "",
            "Canvas render reports",
        ]
        for report in render_reports:
            render_log_lines.append(f"- Canvas: {report.get('canvas_name', '(unknown)')}")
            render_log_lines.append(f"  Success: {report.get('success', False)}")
            render_log_lines.append(f"  Output: {report.get('output_path', '')}")
            render_log_lines.append(f"  Clip count: {report.get('clip_count', 0)} / card count: {report.get('card_count', 0)}")
            render_log_lines.append(f"  Reason: {report.get('reason', '')}")
            render_log_lines.append(f"  Render mode: {report.get('render_mode', '')}")
            attempts = report.get('attempts', []) or []
            if attempts:
                render_log_lines.append("  Attempts:")
                for attempt in attempts:
                    render_log_lines.append(
                        f"    - {attempt.get('render_mode', '')}: success={attempt.get('success', False)} codec={attempt.get('codec', '')} preset={attempt.get('preset', '')} reason={attempt.get('reason', '')}"
                    )
                    if attempt.get('exception'):
                        render_log_lines.append("      Exception:")
                        render_log_lines.append(attempt.get('exception'))
            card_reports = report.get('card_reports', []) or []
            if card_reports:
                render_log_lines.append("  Card reports:")
                for card_report in card_reports:
                    line = f"    - {card_report.get('title', card_report.get('asset_id', 'card'))}: {card_report.get('status', 'unknown')}"
                    if card_report.get('detail'):
                        line += f" ({card_report.get('detail')})"
                    render_log_lines.append(line)
            exception_text = report.get('exception', '')
            if exception_text:
                render_log_lines.append("  Exception:")
                render_log_lines.append(exception_text)
            render_log_lines.append("")

        render_log_path = archive_dir / "export_log.txt"
        render_log_path.write_text("\n".join(render_log_lines), encoding="utf-8")
        package_files.append(str(render_log_path))

        result_payload = {
            "success": bool([p for p in media_outputs if p]),
            "export_dir": str(export_dir),
            "media_outputs": [p for p in media_outputs if p],
            "package_files": package_files,
            "render_reports": render_reports,
            "render_log_path": str(render_log_path),
        }
        result_json_path = archive_dir / "export_result.json"
        safe_json_write(result_json_path, result_payload)
        package_files.append(str(result_json_path))
        result_payload["result_json_path"] = str(result_json_path)
        return result_payload


    def _render_canvas(self, project: ProjectState, export_dir: Path, canvas_name: str) -> Dict[str, Any]:
        width, height = CANVAS_FAMILIES[canvas_name]
        folder_map = {
            "9x16": "02_Vertical_9x16",
            "4x5": "03_Portrait_4x5",
            "1x1": "04_Square_1x1",
            "16x9": "05_Landscape_16x9",
            "2x3": "06_Tall_2x3",
        }
        output_path = export_dir / folder_map[canvas_name] / f"{slugify(project.project_name)}_{canvas_name}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        asset_map = {asset.asset_id: asset for asset in project.assets}
        clips = []
        card_reports: List[Dict[str, Any]] = []
        for card in project.selected_storyboard:
            asset = asset_map.get(card.asset_id)
            if not asset:
                card_reports.append({
                    "asset_id": card.asset_id,
                    "title": card.asset_id,
                    "status": "skipped",
                    "detail": "asset missing from asset map",
                })
                continue
            try:
                clip = self._clip_for_card(asset_map, asset, card, width, height)
                if clip is not None:
                    clips.append(clip)
                    card_reports.append({
                        "asset_id": asset.asset_id,
                        "title": asset.title,
                        "status": "built",
                        "detail": "primary clip built",
                    })
                else:
                    card_reports.append({
                        "asset_id": asset.asset_id,
                        "title": asset.title,
                        "status": "skipped",
                        "detail": "clip builder returned None",
                    })
            except Exception as exc:
                card_reports.append({
                    "asset_id": asset.asset_id,
                    "title": asset.title,
                    "status": "error",
                    "detail": f"{type(exc).__name__}: {exc}",
                })

        report = {
            "canvas_name": canvas_name,
            "output_path": str(output_path),
            "clip_count": len(clips),
            "card_count": len(project.selected_storyboard),
            "card_reports": card_reports,
            "success": False,
            "reason": "",
            "exception": "",
            "render_mode": "",
            "attempts": [],
        }
        if not clips:
            report["reason"] = "No valid clips were built for this canvas."
            report["render_mode"] = "none"
            return report

        try:
            primary_attempt = self._write_clip_stack(
                clips,
                output_path,
                render_mode="moviepy_compose_libx264",
                codec="libx264",
                audio_codec="aac",
                preset="medium",
            )
            report["attempts"].append(primary_attempt)
            if primary_attempt.get("success"):
                report["success"] = True
                report["reason"] = primary_attempt.get("reason", "")
                report["exception"] = primary_attempt.get("exception", "")
                report["render_mode"] = primary_attempt.get("render_mode", "")
                return report

            same_clips_fallback = self._write_clip_stack(
                clips,
                output_path,
                render_mode="moviepy_compose_mpeg4_fallback",
                codec="mpeg4",
                audio_codec="aac",
                preset="ultrafast",
            )
            report["attempts"].append(same_clips_fallback)
            if same_clips_fallback.get("success"):
                report["success"] = True
                report["reason"] = same_clips_fallback.get("reason", "")
                report["exception"] = same_clips_fallback.get("exception", "")
                report["render_mode"] = same_clips_fallback.get("render_mode", "")
                return report
        finally:
            for clip in clips:
                self._close_clip_safely(clip)

        fallback_clips, fallback_card_reports = self._build_simple_fallback_clips(project, asset_map, width, height)
        for fallback_card_report in fallback_card_reports:
            fallback_card_report.setdefault("detail", "")
            fallback_card_report["detail"] = (fallback_card_report["detail"] + " [simple fallback]").strip()
        if fallback_card_reports:
            report["card_reports"].extend(fallback_card_reports)

        if not fallback_clips:
            last_attempt = report["attempts"][-1] if report["attempts"] else {}
            report["reason"] = last_attempt.get("reason", "Primary and fallback render builders produced no usable clips.")
            report["exception"] = last_attempt.get("exception", "")
            report["render_mode"] = last_attempt.get("render_mode", "none")
            return report

        try:
            simple_attempt = self._write_clip_stack(
                fallback_clips,
                output_path,
                render_mode="simple_fallback_mpeg4",
                codec="mpeg4",
                audio_codec="aac",
                preset="ultrafast",
            )
            report["attempts"].append(simple_attempt)
            if simple_attempt.get("success"):
                report["success"] = True
                report["reason"] = simple_attempt.get("reason", "")
                report["exception"] = simple_attempt.get("exception", "")
                report["render_mode"] = simple_attempt.get("render_mode", "")
                report["clip_count"] = len(fallback_clips)
            else:
                report["reason"] = simple_attempt.get("reason", "")
                report["exception"] = simple_attempt.get("exception", "")
                report["render_mode"] = simple_attempt.get("render_mode", "")
        finally:
            for clip in fallback_clips:
                self._close_clip_safely(clip)
        return report

    def _write_clip_stack(
        self,
        clips: List[Any],
        output_path: Path,
        render_mode: str,
        codec: str = "libx264",
        audio_codec: str = "aac",
        preset: str = "medium",
    ) -> Dict[str, Any]:
        attempt = {
            "render_mode": render_mode,
            "codec": codec,
            "audio_codec": audio_codec,
            "preset": preset,
            "success": False,
            "reason": "",
            "exception": "",
        }
        final_clip = None
        try:
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            final_clip = concatenate_videoclips(clips, method="compose")
            if hasattr(final_clip, "with_fps"):
                final_clip = final_clip.with_fps(24)
            final_clip.write_videofile(
                str(output_path),
                codec=codec,
                audio_codec=audio_codec,
                fps=24,
                logger=None,
                preset=preset,
                threads=1,
                pixel_format="yuv420p",
            )
            if output_path.exists() and output_path.stat().st_size > 0:
                attempt["success"] = True
                attempt["reason"] = f"{render_mode} wrote {output_path.stat().st_size} bytes."
            else:
                attempt["reason"] = f"{render_mode} returned without producing an output file."
        except Exception:
            attempt["reason"] = f"{render_mode} raised an exception."
            attempt["exception"] = traceback.format_exc()
        finally:
            if final_clip is not None:
                try:
                    final_clip.close()
                except Exception:
                    pass
        return attempt

    def _build_simple_fallback_clips(
        self,
        project: ProjectState,
        asset_map: Dict[str, Asset],
        width: int,
        height: int,
    ) -> Tuple[List[Any], List[Dict[str, Any]]]:
        clips: List[Any] = []
        reports: List[Dict[str, Any]] = []
        for card in project.selected_storyboard:
            asset = asset_map.get(card.asset_id)
            if not asset:
                reports.append({
                    "asset_id": card.asset_id,
                    "title": card.asset_id,
                    "status": "skipped",
                    "detail": "simple fallback could not find asset",
                })
                continue
            try:
                clip = self._simple_fallback_clip_for_card(asset, card, width, height)
                if clip is None:
                    reports.append({
                        "asset_id": asset.asset_id,
                        "title": asset.title,
                        "status": "skipped",
                        "detail": "simple fallback returned None",
                    })
                    continue
                clips.append(clip)
                reports.append({
                    "asset_id": asset.asset_id,
                    "title": asset.title,
                    "status": "built",
                    "detail": "simple fallback clip built",
                })
            except Exception as exc:
                reports.append({
                    "asset_id": asset.asset_id,
                    "title": asset.title,
                    "status": "error",
                    "detail": f"simple fallback {type(exc).__name__}: {exc}",
                })
        return clips, reports

    def _close_clip_safely(self, clip: Any) -> None:
        if clip is None:
            return
        related = [
            getattr(clip, "_ed_source_clip", None),
            getattr(clip, "_ed_audio_clip", None),
        ]
        for item in related:
            if item is None:
                continue
            try:
                item.close()
            except Exception:
                pass
        try:
            clip.close()
        except Exception:
            pass

    def _clip_for_card(self, asset_map: Dict[str, Asset], asset: Asset, card: StoryboardCard, width: int, height: int):
        if card.pair_asset_id in asset_map:
            if card.compare_mode == "sequential":
                return self._sequential_compare_clip(asset, asset_map[card.pair_asset_id], card, width, height)
            if card.use_split_screen:
                return self._split_screen_clip(asset, asset_map[card.pair_asset_id], card, width, height)
        return self._single_asset_clip(asset, card, width, height)

    def _single_asset_clip(self, asset: Asset, card: StoryboardCard, width: int, height: int):
        duration = max(0.3, card.effective_duration(asset))
        path = Path(asset.path)
        if asset.media_type == "image":
            clip = ImageClip(str(path), duration=duration)
            return self._fit_clip(clip, width, height, card.crop_focus_x, card.crop_focus_y)
        if asset.media_type == "video":
            source = VideoFileClip(str(path))
            segment = source.subclipped(0, min(duration, float(source.duration or duration)))
            if card.mute_audio:
                segment = segment.without_audio()
            segment._ed_source_clip = source
            return self._fit_clip(segment, width, height, card.crop_focus_x, card.crop_focus_y)
        if asset.media_type == "audio":
            base = ColorClip((width, height), color=(0, 0, 0), duration=duration)
            audio = AudioFileClip(str(path)).subclipped(0, duration)
            base = base.with_audio(audio)
            base._ed_audio_clip = audio
            return base
        return None

    def _simple_fallback_clip_for_card(self, asset: Asset, card: StoryboardCard, width: int, height: int):
        duration = max(0.3, card.effective_duration(asset))
        path = Path(asset.path)
        if asset.media_type == "image":
            clip = ImageClip(str(path), duration=duration)
            return clip.resized(new_size=(width, height))
        if asset.media_type == "video":
            source = VideoFileClip(str(path))
            segment = source.subclipped(0, min(duration, float(source.duration or duration)))
            if card.mute_audio:
                segment = segment.without_audio()
            segment = segment.resized(new_size=(width, height))
            segment._ed_source_clip = source
            return segment
        if asset.media_type == "audio":
            base = ColorClip((width, height), color=(0, 0, 0), duration=duration)
            audio = AudioFileClip(str(path)).subclipped(0, duration)
            base = base.with_audio(audio)
            base._ed_audio_clip = audio
            return base
        return None

    def _split_screen_clip(self, left_asset: Asset, right_asset: Asset, card: StoryboardCard, width: int, height: int):
        duration = max(0.3, card.effective_duration(left_asset))
        half_width = width // 2
        left_card = StoryboardCard(asset_id=left_asset.asset_id, duration_override=duration, mute_audio=card.mute_audio, crop_focus_x=card.crop_focus_x, crop_focus_y=card.crop_focus_y)
        right_card = StoryboardCard(asset_id=right_asset.asset_id, duration_override=duration, mute_audio=True)
        left = self._single_asset_clip(left_asset, left_card, half_width, height)
        right = self._single_asset_clip(right_asset, right_card, half_width, height)
        if left is None or right is None:
            return left or right
        left = left.with_position((0, 0))
        right = right.with_position((half_width, 0))
        base = ColorClip((width, height), color=(0, 0, 0), duration=duration)
        return CompositeVideoClip([base, left, right], size=(width, height))

    def _sequential_compare_clip(self, first_asset: Asset, second_asset: Asset, card: StoryboardCard, width: int, height: int):
        total_duration = max(0.6, card.effective_duration(first_asset))
        half_duration = max(0.3, total_duration / 2.0)
        first_card = StoryboardCard(asset_id=first_asset.asset_id, duration_override=half_duration, mute_audio=card.mute_audio, crop_focus_x=card.crop_focus_x, crop_focus_y=card.crop_focus_y)
        second_card = StoryboardCard(asset_id=second_asset.asset_id, duration_override=half_duration, mute_audio=card.mute_audio)
        first_clip = self._single_asset_clip(first_asset, first_card, width, height)
        second_clip = self._single_asset_clip(second_asset, second_card, width, height)
        if first_clip is None or second_clip is None:
            return first_clip or second_clip
        return concatenate_videoclips([first_clip, second_clip], method="compose")

    def _fit_clip(self, clip, target_width: int, target_height: int, focus_x: float, focus_y: float):
        src_w = getattr(clip, "w", target_width) or target_width
        src_h = getattr(clip, "h", target_height) or target_height
        src_ratio = src_w / float(src_h)
        tgt_ratio = target_width / float(target_height)
        if src_ratio > tgt_ratio:
            resized = clip.resized(height=target_height)
            overflow = max(0, int(getattr(resized, "w", target_width)) - target_width)
            x1 = int(max(0, min(overflow, overflow * focus_x)))
            return resized.cropped(x1=x1, y1=0, width=target_width, height=target_height)
        resized = clip.resized(width=target_width)
        overflow = max(0, int(getattr(resized, "h", target_height)) - target_height)
        y1 = int(max(0, min(overflow, overflow * focus_y)))
        return resized.cropped(x1=0, y1=y1, width=target_width, height=target_height)


# -----------------------------------------------------------------------------
# Persistence
# -----------------------------------------------------------------------------


class ProjectSerializer:
    @staticmethod
    def save(project: ProjectState, path: Path) -> None:
        safe_json_write(path, asdict(project))

    @staticmethod
    def load(path: Path) -> ProjectState:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        assets: List[Asset] = []
        for item in payload.get("assets", []):
            assets.append(
                Asset(
                    asset_id=item["asset_id"],
                    path=item["path"],
                    media_type=item["media_type"],
                    title=item["title"],
                    tags=item.get("tags", []),
                    content_goal_tags=item.get("content_goal_tags", []),
                    role_tags=item.get("role_tags", []),
                    favorite=item.get("favorite", False),
                    rating=item.get("rating", 0),
                    notes=item.get("notes", ""),
                    analysis=MediaAnalysis(**item.get("analysis", {})),
                )
            )
        pairs = [PairSuggestion(**p) for p in payload.get("pair_suggestions", [])]
        drafts = []
        for item in payload.get("drafts", []):
            drafts.append(
                DraftOption(
                    draft_id=item["draft_id"],
                    name=item["name"],
                    label=item["label"],
                    storyboard_cards=[StoryboardCard(**c) for c in item.get("storyboard_cards", [])],
                    runtime_estimate=item.get("runtime_estimate", 0.0),
                    recommended_bundle=item.get("recommended_bundle", "Meta Creator Pack"),
                    hook_options=item.get("hook_options", []),
                    title_options=item.get("title_options", []),
                    cta_options=item.get("cta_options", []),
                    rationale=item.get("rationale", ""),
                    confidence_score=item.get("confidence_score", 0.0),
                    style_tag=item.get("style_tag", ""),
                    locked_platform_variant=item.get("locked_platform_variant", ""),
                    locked_caption_style=item.get("locked_caption_style", ""),
                    locked_caption_position=item.get("locked_caption_position", ""),
                    locked_caption_emphasis=item.get("locked_caption_emphasis", ""),
                    is_export_candidate=item.get("is_export_candidate", False),
                )
            )
        return ProjectState(
            project_name=payload.get("project_name", "Untitled Project"),
            created_at=payload.get("created_at", datetime.now().isoformat()),
            updated_at=payload.get("updated_at", datetime.now().isoformat()),
            content_goal=payload.get("content_goal", GOAL_CARDS[0]["goal"]),
            template_family=payload.get("template_family", GOAL_CARDS[0]["template_family"]),
            auto_inference_enabled=payload.get("auto_inference_enabled", payload.get("template_family") == "Smart Auto"),
            recommended_bundle=payload.get("recommended_bundle", GOAL_CARDS[0]["recommended_bundle"]),
            publish_bundle=payload.get("publish_bundle", GOAL_CARDS[0]["recommended_bundle"]),
            hook_angle=payload.get("hook_angle", GOAL_CARDS[0]["hook_angle"]),
            cta_text=payload.get("cta_text", GOAL_CARDS[0]["cta"]),
            title_text=payload.get("title_text", ""),
            hook_text=payload.get("hook_text", ""),
            caption_mode=payload.get("caption_mode", "Auto"),
            caption_source_path=payload.get("caption_source_path", ""),
            reference_text=payload.get("reference_text", ""),
            reference_paths=payload.get("reference_paths", []),
            reference_preview_paths=payload.get("reference_preview_paths", {}),
            reference_media_types=payload.get("reference_media_types", {}),
            reference_preview_notes=payload.get("reference_preview_notes", {}),
            selected_reference_path=payload.get("selected_reference_path", ""),
            assets=assets,
            pair_suggestions=pairs,
            drafts=drafts,
            selected_draft_id=payload.get("selected_draft_id", ""),
            selected_storyboard=[StoryboardCard(**c) for c in payload.get("selected_storyboard", [])],
            selected_storyboard_index=payload.get("selected_storyboard_index", -1),
            preview_canvas_family=payload.get("preview_canvas_family", "9x16"),
            preview_platform_variant=payload.get("preview_platform_variant", "Auto"),
            preview_caption_style=payload.get("preview_caption_style", "ED Clean Lower Third"),
            preview_caption_position=payload.get("preview_caption_position", "Bottom Center"),
            preview_caption_emphasis=payload.get("preview_caption_emphasis", "Standard"),
            export_candidate_draft_id=payload.get("export_candidate_draft_id", ""),
            automation_notes=payload.get("automation_notes", []),
            intake_state=payload.get("intake_state", "idle"),
            intake_stage=payload.get("intake_stage", ""),
            intake_total=payload.get("intake_total", 0),
            intake_processed=payload.get("intake_processed", 0),
            intake_current_item=payload.get("intake_current_item", ""),
            intake_error=payload.get("intake_error", ""),
            last_export_path=payload.get("last_export_path", ""),
            last_export_snapshot=ExportVersionSnapshot(**payload["last_export_snapshot"]) if payload.get("last_export_snapshot") else None,
            export_score_weights=payload.get("export_score_weights", {"copy": 3, "proof": 3, "cta": 3, "platform": 2}),
            export_decision_notes=payload.get("export_decision_notes", ""),
            final_approval_locked=payload.get("final_approval_locked", False),
            approved_export_source=payload.get("approved_export_source", ""),
            approved_export_snapshot=ExportVersionSnapshot(**payload["approved_export_snapshot"]) if payload.get("approved_export_snapshot") else None,
        )


# -----------------------------------------------------------------------------
# Controller
# -----------------------------------------------------------------------------


class AppController:
    def __init__(self, app: "WorkflowApp"):
        self.app = app
        self.content_system = ContentSystem()
        self.content_system.ensure()
        self.analyzer = MediaAnalyzer(self.content_system)
        self.exporter = Exporter(self.content_system)
        self.project = ProjectState()
        self.current_project_path: Optional[Path] = None
        self.worker_queue: queue.Queue = queue.Queue()
        self.advanced_mode_enabled = False
        self.restart_keep_media_and_regenerate = False
        self.intake_in_progress = False
        self.pending_asset_ids: List[str] = []
        self.active_intake_session_id: int = 0
        self.current_intake_asset_ids: List[str] = []
        self.stay_on_drop_files_after_direction_override = False

    def toggle_advanced_mode(self) -> None:
        self.advanced_mode_enabled = not self.advanced_mode_enabled
        mode = "Advanced" if self.advanced_mode_enabled else "Simple"
        self.project.automation_notes.append(f"Switched to {mode} Mode.")
        self.app.set_status(f"{mode} Mode enabled." if self.advanced_mode_enabled else "Simple Mode enabled.")
        self.app.refresh_all_screens()

    def set_advanced_mode(self, enabled: bool) -> None:
        self.advanced_mode_enabled = bool(enabled)
        self.app.refresh_all_screens()

    def set_goal_by_label(self, label: str) -> None:
        payload = next((item for item in GOAL_CARDS if item["label"] == label), GOAL_CARDS[0])
        self.project.content_goal = payload["goal"]
        self.project.template_family = payload["template_family"]
        self.project.auto_inference_enabled = payload["template_family"] == "Smart Auto"
        self.project.recommended_bundle = payload["recommended_bundle"]
        self.project.publish_bundle = payload["recommended_bundle"]
        self.project.hook_angle = payload["hook_angle"]
        self.project.cta_text = payload["cta"]
        bundle_canvases = PUBLISH_BUNDLES.get(payload["recommended_bundle"], ["9x16"])
        self.project.preview_canvas_family = bundle_canvases[0] if bundle_canvases else "9x16"
        self.project.automation_notes = [
            f"Outcome selected: {payload['label']}",
            f"Platform pack: {payload['recommended_bundle']}",
        ]
        if self.restart_keep_media_and_regenerate and self.project.assets:
            self.restart_keep_media_and_regenerate = False
            self.project.automation_notes.append("Keeping the same imported files and rebuilding recommendations for the new direction.")
            self.app.refresh_all_screens()
            self._run_background(self._rebuild_existing_media_for_new_goal, None, "Rebuilding recommendations for the new direction...")
            return

        self.app.refresh_all_screens()

        if self.project.assets and self.project.drafts:
            self.app.show_screen("draft_gallery")
            self.app.set_status(f"Direction selected: {payload['label']}. Review the updated recommendation or refine it.")
        else:
            self.app.show_screen("drop_files")
            if self.project.assets:
                self.app.set_status(f"Direction selected: {payload['label']}. Your files are still here — drop more or rebuild recommendations.")
            else:
                self.app.set_status(f"Direction selected: {payload['label']}. Add files to continue.")


    def override_goal_from_drop_files(self, label: str) -> None:
        payload = next((item for item in GOAL_CARDS if item["label"] == label), GOAL_CARDS[0])
        self.project.content_goal = payload["goal"]
        self.project.template_family = payload["template_family"]
        self.project.auto_inference_enabled = False
        self.project.recommended_bundle = payload["recommended_bundle"]
        self.project.publish_bundle = payload["recommended_bundle"]
        self.project.hook_angle = payload["hook_angle"]
        self.project.cta_text = payload["cta"]
        bundle_canvases = PUBLISH_BUNDLES.get(payload["recommended_bundle"], ["9x16"])
        self.project.preview_canvas_family = bundle_canvases[0] if bundle_canvases else "9x16"
        self.project.automation_notes.append(f"Direction override selected from Add Media: {payload['label']}.")
        if self.project.assets:
            self.stay_on_drop_files_after_direction_override = True
            self.app.refresh_all_screens()
            self._run_background(self._rebuild_existing_media_for_new_goal, None, f"Rebuilding recommendations for {payload['label']}...")
        else:
            self.app.refresh_all_screens()
            self.app.show_screen("drop_files")
            self.app.set_status(f"Direction selected: {payload['label']}. Add files to continue.")

    def import_reference_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Add Reference Inspiration")
        if not paths:
            return
        added = 0
        last_added = ""
        total = len(paths)
        for idx, raw_path in enumerate(paths, start=1):
            path = str(Path(raw_path))
            if path in self.project.reference_paths:
                last_added = path
                continue
            self.app.set_status(f"Preparing reference {idx}/{total}: {Path(path).name}")
            self.app.update_idletasks()
            preview_path, media_type, note, accent_hex = self.analyzer.build_reference_preview(Path(path))
            if accent_hex:
                self.project.reference_accent_color = accent_hex
            self.project.reference_paths.append(path)
            self.project.reference_preview_paths[path] = preview_path
            self.project.reference_media_types[path] = media_type
            self.project.reference_preview_notes[path] = note
            self.project.selected_reference_path = path
            self.project.automation_notes.append(f"Reference ready: {Path(path).name} — {note}")
            added += 1
            last_added = path
            self.app.refresh_all_screens()
            self.app.update_idletasks()
        if last_added:
            self.project.selected_reference_path = last_added
        self.app.refresh_all_screens()
        if added:
            self.app.set_status(f"Added {added} reference file(s). Preview ready on the right panel.")
        else:
            self.app.set_status("Those reference files were already attached.")

    def import_caption_file(self) -> None:
        path = filedialog.askopenfilename(title="Import Caption File", filetypes=[("Caption files", "*.srt *.vtt *.txt"), ("All files", "*.*")])
        if not path:
            return
        self.project.caption_source_path = path
        self.project.caption_mode = "Import Existing"
        self.project.automation_notes.append(f"Attached caption file: {Path(path).name}")
        self.app.refresh_all_screens()

    def remove_media_asset_by_id(self, asset_id: str) -> None:
        asset = next((a for a in self.project.assets if a.asset_id == asset_id), None)
        if not asset:
            self.app.set_status("Could not find that media item.")
            return
        was_active = asset_id in self.current_intake_asset_ids and self.intake_in_progress
        self.project.assets = [a for a in self.project.assets if a.asset_id != asset_id]
        self.project.selected_storyboard = [card for card in self.project.selected_storyboard if card.asset_id != asset_id]
        self.project.drafts = [draft for draft in self.project.drafts if all(card.asset_id != asset_id for card in draft.storyboard_cards)]
        self.pending_asset_ids = [queued_id for queued_id in self.pending_asset_ids if queued_id != asset_id]
        self.project.automation_notes.append(f"Removed media item: {asset.title}")
        if was_active:
            self.project.automation_notes.append(
                "Cancelled the current intake pass because the active media item was removed."
            )
            self._cancel_active_intake_session("Current intake was cancelled because the active media item was removed.")
            if self.pending_asset_ids:
                self.app.set_status(
                    f"Removed media item: {asset.title}. Starting the next queued intake pass now."
                )
                self.app.after(10, self._consume_pending_imports)
                return
        if not self.project.assets and not self.pending_asset_ids and not self.intake_in_progress:
            self._reset_after_last_media_removed(asset.title)
            return
        self.app.refresh_all_screens()
        self.app.set_status(f"Removed media item: {asset.title}")

    def import_media_files(self, paths: List[str]) -> None:
        if not paths:
            return
        normalized_paths: List[str] = []
        for raw in paths:
            try:
                candidate = Path(raw)
            except Exception:
                continue
            if candidate.exists() and infer_media_type(candidate) != "unknown":
                normalized_paths.append(str(candidate))
        if not normalized_paths:
            self.app.set_status("No valid media files were imported.")
            return
        if self.intake_in_progress:
            queued_assets = self._prepare_import_assets(normalized_paths, queued=True)
            if not queued_assets:
                self.app.set_status("No valid media files were imported.")
                return
            self.pending_asset_ids.extend([asset.asset_id for asset in queued_assets])
            queued_count = len(self.pending_asset_ids)
            self.project.automation_notes.append(
                f"Queued {len(queued_assets)} additional media file(s) while the current intake is still running."
            )
            self.app.refresh_all_screens()
            self.app.set_status(
                f"Current intake still running. Queued {len(queued_assets)} additional file(s) for the next pass ({queued_count} waiting)."
            )
            return
        imported_assets = self._prepare_import_assets(normalized_paths, queued=False)
        if not imported_assets:
            self.app.set_status("No valid media files were imported.")
            return
        self._start_import_batch(imported_assets)

    def _reset_after_last_media_removed(self, removed_title: str) -> None:
        self.project.pair_suggestions = []
        self.project.drafts = []
        self.project.selected_draft_id = ""
        self.project.selected_storyboard = []
        self.project.selected_storyboard_index = -1
        self.project.export_candidate_draft_id = ""
        self.project.intake_state = "idle"
        self.project.intake_stage = ""
        self.project.intake_total = 0
        self.project.intake_processed = 0
        self.project.intake_current_item = ""
        self.project.intake_error = ""
        self.current_intake_asset_ids = []
        self.project.automation_notes.append("All media was removed. Intake status reset and waiting for new media.")
        try:
            self.app.drop_files_screen.clear_intake_view("Start by adding one file. You can keep adding more before moving on.")
        except Exception:
            pass
        self.app.refresh_all_screens()
        self.app.set_status(f"Removed media item: {removed_title}. Intake status reset.")

    def _hard_reset_intake_session_state(self, message: str = "Preparing media intake...", *, state: str = "processing") -> None:
        self.project.intake_state = state
        self.project.intake_stage = INTAKE_STAGES[0] if state == "processing" and INTAKE_STAGES else ""
        self.project.intake_total = 0
        self.project.intake_processed = 0
        self.project.intake_current_item = message
        self.project.intake_error = ""
        self.app.drop_files_screen.reset_intake_view({"total": 0, "message": message})
        if state == "processing" and INTAKE_STAGES:
            self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[0])
            self.app.drop_files_screen.set_progress({
                "percent": 0,
                "message": message,
                "state": "processing",
                "stage": INTAKE_STAGES[0],
                "total": 0,
                "processed": 0,
                "detail": message,
            })
        else:
            self.app.drop_files_screen.set_progress({
                "percent": 0,
                "message": message,
                "state": state,
                "stage": "",
                "total": 0,
                "processed": 0,
                "detail": message,
            })

    def _asset_needs_video_followup(self, asset: Asset) -> bool:
        if asset.media_type != "video":
            return False
        preview_path = (asset.analysis.preview_path or "").lower()
        return asset.analysis.duration <= 0.0 or "placeholder" in preview_path or not preview_path

    def _start_video_followup_enrichment(self) -> None:
        if getattr(self, "video_followup_in_progress", False):
            return
        target_ids = [asset.asset_id for asset in self.project.assets if self._asset_needs_video_followup(asset)]
        if not target_ids:
            return
        self.video_followup_in_progress = True
        self.project.automation_notes.append(f"Starting video follow-up enrichment for {len(target_ids)} video asset(s).")
        self.app.refresh_all_screens()

        def runner(ids: List[str]):
            try:
                self._video_followup_enrichment_worker(ids)
            except Exception:
                tb = traceback.format_exc()
                self.worker_queue.put(("automation_note", f"Video follow-up enrichment error: {tb.splitlines()[-1] if tb.splitlines() else 'Unknown error'}"))
            finally:
                self.worker_queue.put(("video_followup_done", None))

        threading.Thread(target=runner, args=(list(target_ids),), daemon=True).start()

    def _video_followup_enrichment_worker(self, asset_ids: List[str]) -> None:
        for asset_id in asset_ids:
            asset = next((a for a in self.project.assets if a.asset_id == asset_id), None)
            if asset is None or asset.media_type != "video":
                continue
            previous_preview = asset.analysis.preview_path or ""
            previous_duration = float(asset.analysis.duration or 0.0)
            previous_ocr = asset.analysis.ocr_text or ""
            previous_transcript = asset.analysis.transcript_text or ""
            previous_hint = asset.analysis.before_after_hint or ""
            preview_path, duration, ocr_text, transcript_text, before_after_hint, notes = self.analyzer.enrich_video_intent_signals(Path(asset.path), asset.analysis.duration)
            updated_preview = bool(preview_path and Path(preview_path).exists() and preview_path != previous_preview)
            updated_duration = bool(duration > 0.0 and abs(duration - previous_duration) > 0.05)
            updated_ocr = bool(ocr_text and ocr_text != previous_ocr)
            updated_transcript = bool(transcript_text and transcript_text != previous_transcript)
            updated_hint = bool(before_after_hint and before_after_hint != previous_hint)
            if updated_preview:
                asset.analysis.preview_path = preview_path
            if updated_duration:
                asset.analysis.duration = duration
            if updated_ocr:
                asset.analysis.ocr_text = ocr_text
            if updated_transcript:
                asset.analysis.transcript_text = transcript_text
            if updated_hint:
                asset.analysis.before_after_hint = before_after_hint
                if before_after_hint not in asset.tags:
                    asset.tags.append(before_after_hint)
            if not updated_preview:
                notes.append("Video follow-up could not replace the placeholder preview.")
            if not updated_duration and duration <= 0.0:
                notes.append("Video follow-up could not determine real clip duration; keeping fallback duration.")
            for note in notes:
                if note not in asset.analysis.analysis_notes:
                    asset.analysis.analysis_notes.append(note)
            if updated_preview or updated_duration or updated_ocr or updated_transcript or updated_hint:
                parts = []
                if updated_preview:
                    parts.append("poster frame updated")
                if updated_duration:
                    parts.append(f"duration {asset.analysis.duration:.1f}s")
                if updated_ocr:
                    parts.append("OCR text captured")
                if updated_transcript:
                    parts.append("speech transcript captured")
                if updated_hint:
                    parts.append(f"intent hint {asset.analysis.before_after_hint}")
                self.worker_queue.put(("automation_note", f"Video follow-up updated {asset.title}: {', '.join(parts)}."))
                self.worker_queue.put(("video_asset_enriched", asset.asset_id))
            else:
                note_summary = next((n for n in reversed(notes) if n), "No richer video preview metadata could be generated.")
                self.worker_queue.put(("automation_note", f"Video follow-up left placeholder for {asset.title}: {note_summary}"))

    def _refresh_recommendations_after_video_followup(self) -> None:
        if not self.project.assets:
            return
        previous_goal = self.project.content_goal
        previous_export_candidate = self.project.export_candidate_draft_id
        self.project.pair_suggestions = self.analyzer.detect_pair_suggestions(self.project.assets)
        if getattr(self.project, "auto_inference_enabled", False):
            self._infer_direction(force=True)
            self._enforce_before_after_direction_if_needed(enrichment_pass=True)
            if self.project.content_goal != previous_goal:
                self.project.automation_notes.append(
                    f"Smart Auto re-ran after OCR/transcript enrichment and changed the recommendation to {self.project.content_goal}."
                )
            else:
                self.project.automation_notes.append(
                    "Smart Auto re-ran after OCR/transcript enrichment and kept the same recommended direction."
                )
        self._apply_auto_tags()
        self.project.drafts = DraftGenerator(self.project).generate()
        if self.project.drafts:
            draft = self.project.drafts[0]
            self.project.selected_draft_id = draft.draft_id
            self.project.selected_storyboard = [StoryboardCard(**asdict(c)) for c in draft.storyboard_cards]
            self.project.selected_storyboard_index = 0 if self.project.selected_storyboard else -1
            self.project.hook_text = draft.hook_options[0] if draft.hook_options else self.project.hook_text
            self.project.title_text = draft.title_options[0] if draft.title_options else self.project.title_text
            self.project.cta_text = draft.cta_options[0] if draft.cta_options else self.project.cta_text
            self.project.export_candidate_draft_id = draft.draft_id
            if draft.draft_id != previous_export_candidate:
                self.project.automation_notes.append(
                    f"Post-enrichment recommendation refreshed to {draft.name}."
                )
        self._infer_caption_mode()

    def _cancel_active_intake_session(self, reason: str) -> None:
        self.active_intake_session_id += 1
        self.intake_in_progress = False
        self.current_intake_asset_ids = []
        self._hard_reset_intake_session_state(reason, state="idle")
        self.app.refresh_all_screens()

    def _start_import_batch(self, imported_assets: List[Asset]) -> None:
        if not imported_assets:
            self.app.set_status("No valid media files were imported.")
            return
        self._hard_reset_intake_session_state("Preparing media intake...", state="processing")
        self.intake_in_progress = True
        self.active_intake_session_id += 1
        session_id = self.active_intake_session_id
        self.current_intake_asset_ids = [asset.asset_id for asset in imported_assets]
        self.project.intake_total = len(imported_assets)
        self.project.intake_processed = 0
        self.project.intake_current_item = f"Starting media intake for {len(imported_assets)} file(s)..."
        self.project.intake_error = ""
        self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[0])
        self.app.drop_files_screen.set_progress({
            "percent": 0,
            "message": self.project.intake_current_item,
            "state": "processing",
            "stage": INTAKE_STAGES[0],
            "total": len(imported_assets),
            "processed": 0,
            "detail": self.project.intake_current_item,
        })
        self.app.refresh_all_screens()
        self.app.set_status(self.project.intake_current_item)
        self.app.after(10, lambda sid=session_id, assets=list(imported_assets): self._intake_pipeline_main(sid, assets, stage="stage1", asset_index=0))

    def _intake_session_active(self, session_id: int) -> bool:
        return self.intake_in_progress and session_id == self.active_intake_session_id

    def _finish_intake_cycle_main(self, session_id: int, had_error: bool = False) -> None:
        if session_id != self.active_intake_session_id and not had_error:
            return
        self.intake_in_progress = False
        self.current_intake_asset_ids = []
        if had_error:
            if self.pending_asset_ids:
                self.app.set_status(
                    f"Media intake hit an error. {len(self.pending_asset_ids)} queued file(s) are still waiting."
                )
            return
        self.app.refresh_all_screens()
        self.app.show_screen("drop_files")
        if self.pending_asset_ids:
            self.app.set_status(
                f"Current intake pass complete. Continuing with {len(self.pending_asset_ids)} queued file(s)..."
            )
            self._consume_pending_imports()
        else:
            if self.project.drafts:
                self.app.set_status(
                    "Media intake complete. Add more media or reference items here, or click Next when you want to continue."
                )
            else:
                self.app.set_status(
                    "Media intake complete. Add more media or reference items here, or click Next when you want to continue."
                )
            self.app.after(50, self._start_video_followup_enrichment)

    def _intake_pipeline_main(self, session_id: int, imported: List[Asset], stage: str = "stage1", asset_index: int = 0) -> None:
        if not self._intake_session_active(session_id):
            return
        total = len(imported)
        try:
            if stage == "stage1":
                self.project.intake_state = "processing"
                self.project.intake_stage = INTAKE_STAGES[1]
                self.project.intake_current_item = "Creating previews for imported media..."
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[0])
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[1])
                self.app.drop_files_screen.set_progress({
                    "percent": 22,
                    "message": self.project.intake_current_item,
                    "state": "processing",
                    "stage": INTAKE_STAGES[1],
                    "total": total,
                    "processed": 0,
                    "detail": self.project.intake_current_item,
                })
                self.app.drop_files_screen.refresh()
                self.app.update_idletasks()
                self.app.after(10, lambda sid=session_id, assets=imported: self._intake_pipeline_main(sid, assets, stage="analyze", asset_index=0))
                return

            if stage == "analyze":
                self.project.intake_stage = INTAKE_STAGES[2]
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[1])
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[2])
                if asset_index >= total:
                    self.app.after(10, lambda sid=session_id, assets=imported: self._intake_pipeline_main(sid, assets, stage="pairs", asset_index=0))
                    return
                asset = imported[asset_index]
                if asset.asset_id not in {existing.asset_id for existing in self.project.assets}:
                    self.app.after(1, lambda sid=session_id, assets=imported, i=asset_index + 1: self._intake_pipeline_main(sid, assets, stage="analyze", asset_index=i))
                    return
                current_detail = f"Analyzing file {asset_index + 1}/{max(1, total)}: {asset.title}"
                self.project.intake_current_item = current_detail
                existing_preview = asset.analysis.preview_path
                existing_waveform = asset.analysis.waveform_path
                analyzed = self.analyzer.analyze(asset)
                if not self._intake_session_active(session_id):
                    return
                if asset.asset_id in {existing.asset_id for existing in self.project.assets}:
                    if not analyzed.preview_path and existing_preview:
                        analyzed.preview_path = existing_preview
                        analyzed.analysis_notes.append("Keeping placeholder preview until a richer preview is available.")
                    if not analyzed.waveform_path and existing_waveform:
                        analyzed.waveform_path = existing_waveform
                    asset.analysis = analyzed
                    asset.notes = ""
                self.project.intake_processed = asset_index + 1
                percent = 22 + ((asset_index + 1) / max(1, total)) * 38
                self.app.set_status(current_detail)
                self.app.drop_files_screen.set_progress({
                    "percent": percent,
                    "message": current_detail,
                    "state": "processing",
                    "stage": INTAKE_STAGES[2],
                    "total": total,
                    "processed": asset_index + 1,
                    "detail": current_detail,
                })
                self.app.drop_files_screen.refresh()
                self.app.update_idletasks()
                self.app.after(1, lambda sid=session_id, assets=imported, i=asset_index + 1: self._intake_pipeline_main(sid, assets, stage="analyze", asset_index=i))
                return

            if stage == "pairs":
                self.project.intake_stage = INTAKE_STAGES[3]
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[2])
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[3])
                self.app.set_status("Detecting likely before/after pairs...")
                self.app.drop_files_screen.set_progress({
                    "percent": 66,
                    "message": "Detecting likely before/after pairs...",
                    "state": "processing",
                    "stage": INTAKE_STAGES[3],
                    "total": total,
                    "processed": total,
                    "detail": "Detecting likely before/after pairs...",
                })
                self.project.pair_suggestions = self.analyzer.detect_pair_suggestions(self.project.assets)
                if self.project.pair_suggestions:
                    top_pair = self.project.pair_suggestions[0]
                    self.project.automation_notes.append(f"Detected likely comparison pair (score {top_pair.score:.2f}): {top_pair.reason}")
                self.app.drop_files_screen.refresh()
                self.app.update_idletasks()
                self.app.after(1, lambda sid=session_id, assets=imported: self._intake_pipeline_main(sid, assets, stage="infer", asset_index=0))
                return

            if stage == "infer":
                self.project.intake_stage = INTAKE_STAGES[4]
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[3])
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[4])
                self.app.set_status("Inferring the strongest content direction...")
                self.app.drop_files_screen.set_progress({
                    "percent": 72,
                    "message": "Inferring the strongest content direction...",
                    "state": "processing",
                    "stage": INTAKE_STAGES[4],
                    "total": total,
                    "processed": total,
                    "detail": "Inferring the strongest content direction...",
                })
                self._infer_direction()
                self._enforce_before_after_direction_if_needed()
                self.app.drop_files_screen.refresh()
                self.app.update_idletasks()
                self.app.after(1, lambda sid=session_id, assets=imported: self._intake_pipeline_main(sid, assets, stage="rank", asset_index=0))
                return

            if stage == "rank":
                self.project.intake_stage = INTAKE_STAGES[5]
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[4])
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[5])
                self.app.set_status("Ranking opener, proof, and CTA candidates...")
                self.app.drop_files_screen.set_progress({
                    "percent": 78,
                    "message": "Ranking opener, proof, and CTA candidates...",
                    "state": "processing",
                    "stage": INTAKE_STAGES[5],
                    "total": total,
                    "processed": total,
                    "detail": "Ranking opener, proof, and CTA candidates...",
                })
                self._apply_auto_tags()
                self.app.drop_files_screen.refresh()
                self.app.update_idletasks()
                self.app.after(1, lambda sid=session_id, assets=imported: self._intake_pipeline_main(sid, assets, stage="drafts", asset_index=0))
                return

            if stage == "drafts":
                self.project.intake_stage = INTAKE_STAGES[6]
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[5])
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[6])
                self.app.set_status("Building draft options...")
                self.app.drop_files_screen.set_progress({
                    "percent": 86,
                    "message": "Building draft options...",
                    "state": "processing",
                    "stage": INTAKE_STAGES[6],
                    "total": total,
                    "processed": total,
                    "detail": "Building draft options...",
                })
                self.project.drafts = DraftGenerator(self.project).generate()
                self.app.drop_files_screen.refresh()
                self.app.update_idletasks()
                self.app.after(1, lambda sid=session_id, assets=imported: self._intake_pipeline_main(sid, assets, stage="copy", asset_index=0))
                return

            if stage == "copy":
                self.project.intake_stage = INTAKE_STAGES[7]
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[6])
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[7])
                self.app.set_status("Generating copy suggestions...")
                self.app.drop_files_screen.set_progress({
                    "percent": 92,
                    "message": "Generating copy suggestions...",
                    "state": "processing",
                    "stage": INTAKE_STAGES[7],
                    "total": total,
                    "processed": total,
                    "detail": "Generating copy suggestions...",
                })
                self.app.drop_files_screen.refresh()
                self.app.update_idletasks()
                self.app.after(1, lambda sid=session_id, assets=imported: self._intake_pipeline_main(sid, assets, stage="captions", asset_index=0))
                return

            if stage == "captions":
                self.project.intake_stage = INTAKE_STAGES[8]
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[7])
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[8])
                self.app.set_status("Preparing caption recommendation...")
                self.app.drop_files_screen.set_progress({
                    "percent": 96,
                    "message": "Preparing caption recommendation...",
                    "state": "processing",
                    "stage": INTAKE_STAGES[8],
                    "total": total,
                    "processed": total,
                    "detail": "Preparing caption recommendation...",
                })
                self._infer_caption_mode()
                if self.project.drafts:
                    draft = self.project.drafts[0]
                    self.project.selected_draft_id = draft.draft_id
                    self.project.selected_storyboard = [StoryboardCard(**asdict(c)) for c in draft.storyboard_cards]
                    self.project.selected_storyboard_index = 0 if self.project.selected_storyboard else -1
                    self.project.hook_text = draft.hook_options[0] if draft.hook_options else self.project.hook_text
                    self.project.title_text = draft.title_options[0] if draft.title_options else self.project.title_text
                    self.project.cta_text = draft.cta_options[0] if draft.cta_options else self.project.cta_text
                    self.project.export_candidate_draft_id = draft.draft_id
                    self.project.automation_notes.append(f"Recommended draft auto-promoted for export: {draft.name}.")
                self.app.refresh_all_screens()
                self.project.intake_state = "complete"
                self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[8])
                self.app.drop_files_screen.set_progress({
                    "percent": 100,
                    "message": f"Media intake complete. Built {len(self.project.drafts)} draft option(s).",
                    "state": "complete",
                    "stage": INTAKE_STAGES[8],
                    "total": total,
                    "processed": total,
                    "detail": "Media intake complete.",
                })
                self.app.set_status(f"Media intake complete. Built {len(self.project.drafts)} draft option(s).")
                self.app.refresh_all_screens()
                self._finish_intake_cycle_main(session_id, had_error=False)
                return
        except Exception:
            if self._intake_session_active(session_id):
                self.project.intake_state = "error"
                self.project.intake_error = traceback.format_exc()
                self.app.drop_files_screen.set_progress({
                    "percent": max(0.0, float(self.project.intake_processed / max(1, total) * 100.0)),
                    "message": "Media intake error",
                    "state": "error",
                    "stage": self.project.intake_stage,
                    "total": total,
                    "processed": self.project.intake_processed,
                    "detail": self.project.intake_current_item or "Media intake error.",
                })
                tb_text = traceback.format_exc()
                self.project.automation_notes.append(f"Intake error: {tb_text.splitlines()[-1] if tb_text.splitlines() else 'Unknown error'}")
                self.app.set_status("Media intake error.")
                self.app.refresh_all_screens()
                messagebox.showerror(APP_NAME, tb_text)
                self._finish_intake_cycle_main(session_id, had_error=True)

    def _consume_pending_imports(self) -> None:
        if not self.pending_asset_ids:
            return
        queued_ids = list(dict.fromkeys(self.pending_asset_ids))
        self.pending_asset_ids.clear()
        queued_assets = [asset for asset in self.project.assets if asset.asset_id in queued_ids]
        if not queued_assets:
            self.app.refresh_all_screens()
            return
        for asset in queued_assets:
            asset.notes = ""
            asset.analysis.analysis_notes.append("Queued placeholder promoted into the active intake pass.")
        self.project.automation_notes.append(
            f"Continuing intake with {len(queued_assets)} queued media file(s)."
        )
        self.app.refresh_all_screens()
        self._start_import_batch(queued_assets)

    def _prepare_import_assets(self, paths: List[str], queued: bool = False) -> List[Asset]:
        valid_paths = [Path(p) for p in paths if Path(p).exists() and infer_media_type(Path(p)) != "unknown"]
        total = len(valid_paths)
        if not queued:
            self.project.intake_state = "processing"
            self.project.intake_stage = INTAKE_STAGES[0] if INTAKE_STAGES else ""
            self.project.intake_total = total
            self.project.intake_processed = 0
            self.project.intake_current_item = "Preparing media intake..."
            self.project.intake_error = ""
            self.app.drop_files_screen.reset_intake_view({"total": total, "message": "Preparing media intake..."})
            self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[0])
            self.app.refresh_all_screens()
        imported_assets: List[Asset] = []
        for idx, src in enumerate(valid_paths, start=1):
            current_detail = f"Importing file {idx}/{max(1, total)}: {src.name}"
            if not queued:
                self.project.intake_current_item = current_detail
                self.project.intake_processed = idx - 1
                self.app.drop_files_screen.set_stage_active(INTAKE_STAGES[0])
                self.app.drop_files_screen.set_progress({
                    "percent": (idx - 1) / max(1, total) * 20.0,
                    "message": current_detail,
                    "state": "processing",
                    "stage": INTAKE_STAGES[0],
                    "total": total,
                    "processed": idx - 1,
                    "detail": current_detail,
                })
                self.app.set_status(current_detail)
                self.app.update_idletasks()
            media_type = infer_media_type(src)
            copied = safe_copy(src, self.content_system.library_target(media_type, src))
            title = src.stem.replace("_", " ").replace("-", " ").strip() or src.stem
            asset = Asset(asset_id=f"asset_{now_stamp()}_{random.randint(1000, 9999)}", path=str(copied), media_type=media_type, title=title)
            asset.analysis.preview_path = self.analyzer.build_initial_asset_preview(copied, media_type, title)
            asset.analysis.analysis_notes.append("Imported and queued for analysis.")
            if queued:
                asset.notes = "Queued for the next intake pass."
                asset.analysis.analysis_notes.append("Visible queued placeholder created while another intake was still running.")
            stem_lower = src.stem.lower()
            if any(token in stem_lower for token in ["before", "premaster", "original", "mix"]):
                asset.tags.append("before")
            if any(token in stem_lower for token in ["after", "master", "final"]):
                asset.tags.append("after")
            self.project.assets.append(asset)
            imported_assets.append(asset)
            if not queued:
                self.project.intake_processed = idx
                self.project.intake_current_item = f"Imported file {idx}/{max(1, total)}: {src.name}"
                self.app.drop_files_screen.set_progress({
                    "percent": idx / max(1, total) * 20.0,
                    "message": self.project.intake_current_item,
                    "state": "processing",
                    "stage": INTAKE_STAGES[0],
                    "total": total,
                    "processed": idx,
                    "detail": self.project.intake_current_item,
                })
            self.app.refresh_all_screens()
            try:
                self.app.update()
            except Exception:
                self.app.update_idletasks()
        if not queued:
            self.app.drop_files_screen.set_stage_complete(INTAKE_STAGES[0])
        return imported_assets

    def regenerate_drafts(self) -> None:
        self._run_background(self._draft_regeneration_worker, None, "Regenerating draft options...")

    def select_draft(self, draft_id: str) -> None:
        draft = next((d for d in self.project.drafts if d.draft_id == draft_id), None)
        if not draft:
            return
        self.project.selected_draft_id = draft_id
        self.project.selected_storyboard = [StoryboardCard(**asdict(card)) for card in draft.storyboard_cards]
        self.project.selected_storyboard_index = 0 if self.project.selected_storyboard else -1
        self.project.hook_text = draft.hook_options[0] if draft.hook_options else self.project.hook_text
        self.project.title_text = draft.title_options[0] if draft.title_options else self.project.title_text
        self.project.cta_text = draft.cta_options[0] if draft.cta_options else self.project.cta_text
        bundle_canvases = PUBLISH_BUNDLES.get(self.project.publish_bundle, ["9x16"])
        if self.project.preview_canvas_family not in CANVAS_FAMILIES:
            self.project.preview_canvas_family = bundle_canvases[0] if bundle_canvases else "9x16"
        self._apply_draft_preview_preferences(draft)
        self.app.show_screen("quick_refine")
        self.app.refresh_all_screens()

    def open_recommended_quick_refine(self) -> None:
        draft = self.export_candidate_draft() or self.project.selected_draft() or (self.project.drafts[0] if self.project.drafts else None)
        if not draft:
            return
        self.select_draft(draft.draft_id)
        self.focus_refine_role("hook")
        self.app.set_status("Recommended draft loaded. Swap opener, proof, or CTA, or choose Looks Good when you are ready.")

    def try_another_recommendation(self) -> None:
        drafts = self.project.drafts
        if len(drafts) < 2:
            self.app.set_status("No alternate recommendation is available yet.")
            return
        current_id = self.project.export_candidate_draft_id or self.project.selected_draft_id or drafts[0].draft_id
        top_pool = drafts[: max(2, min(4, len(drafts)))]
        ids = [d.draft_id for d in top_pool]
        try:
            idx = ids.index(current_id)
        except ValueError:
            idx = 0
        target = top_pool[(idx + 1) % len(top_pool)]
        if target.draft_id == current_id and len(top_pool) > 1:
            target = top_pool[1]
        self.promote_export_candidate(target.draft_id)
        self.app.show_screen("draft_gallery")
        self.app.set_status(f"Trying another recommendation: {target.name}.")

    def _rebuild_existing_media_for_new_goal(self) -> None:
        self.worker_queue.put(("status", "Refreshing recommendations for the new direction..."))
        self._apply_auto_tags()
        self.project.drafts = DraftGenerator(self.project).generate()
        self._infer_caption_mode()
        if self.project.drafts:
            recommended = self.project.drafts[0]
            self.project.selected_draft_id = recommended.draft_id
            self.project.selected_storyboard = [StoryboardCard(**asdict(card)) for card in recommended.storyboard_cards]
            self.project.selected_storyboard_index = 0 if self.project.selected_storyboard else -1
            self.project.hook_text = recommended.hook_options[0] if recommended.hook_options else self.project.hook_text
            self.project.title_text = recommended.title_options[0] if recommended.title_options else self.project.title_text
            self.project.cta_text = recommended.cta_options[0] if recommended.cta_options else self.project.cta_text
            self.project.export_candidate_draft_id = recommended.draft_id
            for item in self.project.drafts:
                item.is_export_candidate = item.draft_id == recommended.draft_id
            self.worker_queue.put(("automation_note", f"Rebuilt recommendations for the new direction and promoted {recommended.name} for export."))
        self.worker_queue.put(("direction_rebuild_done", None))
        self.worker_queue.put(("status", "New direction ready."))

    def start_over_with_different_direction(self) -> None:
        self.project.selected_draft_id = ""
        self.project.selected_storyboard = []
        self.project.selected_storyboard_index = -1
        self.project.export_candidate_draft_id = ""
        self.project.final_approval_locked = False
        self.project.approved_export_source = ""
        self.project.approved_export_snapshot = None
        self.restart_keep_media_and_regenerate = False
        if self.project.assets:
            choice = messagebox.askyesnocancel(
                APP_NAME,
                "Keep the same imported files and instantly rebuild after you choose a new direction?\n\n"
                "Yes = keep files and auto-rebuild\n"
                "No = keep files but just return to Choose Outcome\n"
                "Cancel = stay here"
            )
            if choice is None:
                return
            self.restart_keep_media_and_regenerate = bool(choice)
            if choice:
                self.project.automation_notes.append("Starting over with a different direction. The same imported files will rebuild instantly after the new goal is chosen.")
                self.app.set_status("Choose a new direction. We will reuse your imported files and rebuild immediately.")
            else:
                self.project.automation_notes.append("Starting over with a different direction while keeping imported media available.")
                self.app.set_status("Choose a different direction. Your imported media is still available.")
        else:
            self.project.automation_notes.append("Starting over with a different direction.")
            self.app.set_status("Choose a different direction to continue.")
        self.app.show_screen("choose_outcome")
        self.app.refresh_all_screens()

    def export_recommended_version(self) -> None:
        draft = self.export_candidate_draft() or self.project.selected_draft() or (self.project.drafts[0] if self.project.drafts else None)
        if not draft:
            messagebox.showerror(APP_NAME, "No recommended draft is available yet.")
            return
        if self.project.export_candidate_draft_id != draft.draft_id:
            self.promote_export_candidate(draft.draft_id)
        self.app.show_screen("export")
        self.export_project()

    def looks_good_simple(self) -> None:
        snapshot = self.build_selected_export_snapshot()
        if snapshot is None:
            messagebox.showerror(APP_NAME, "No refined draft is ready yet.")
            return
        self.project.final_approval_locked = True
        self.project.approved_export_source = snapshot.source_label
        self.project.approved_export_snapshot = ExportVersionSnapshot(**asdict(snapshot))
        self.project.automation_notes.append("Simple Mode marked the current refined version as ready for export.")
        self.app.show_screen("export")
        self.app.set_status("Current refined version marked ready. Review or export it now.")
        self.app.refresh_all_screens()

    def apply_storyboard_replacement(self, asset_id: str) -> None:
        idx = self.project.selected_storyboard_index
        if idx < 0 or idx >= len(self.project.selected_storyboard):
            return
        card = self.project.selected_storyboard[idx]
        card.asset_id = asset_id
        if card.role == "proof":
            pair = next((p for p in self.project.pair_suggestions if p.before_asset_id == asset_id or p.after_asset_id == asset_id), None)
            if pair:
                other_id = pair.after_asset_id if pair.before_asset_id == asset_id else pair.before_asset_id
                if card.compare_mode not in {"split-screen", "sequential"}:
                    card.compare_mode = "split-screen"
                card.use_split_screen = card.compare_mode == "split-screen"
                card.pair_asset_id = other_id
                self.project.automation_notes.append(f"Comparison preview updated for proof slot using matched pair score {pair.score:.2f}.")
            else:
                card.use_split_screen = False
                card.pair_asset_id = ""
                card.compare_mode = "split-screen"
        else:
            card.use_split_screen = False
            card.pair_asset_id = ""
            card.compare_mode = "split-screen"
        self.app.refresh_all_screens()

    def focus_refine_role(self, role: str) -> None:
        storyboard = self.project.selected_storyboard
        if not storyboard:
            self.project.selected_storyboard_index = -1
            self.app.refresh_all_screens()
            return
        target = next((i for i, card in enumerate(storyboard) if card.role == role), None)
        if target is None:
            if role == "cta":
                target = max(0, len(storyboard) - 1)
            elif role == "proof":
                target = min(max(0, len(storyboard) - 1), 1)
            else:
                target = 0
        self.project.selected_storyboard_index = target
        self.app.refresh_all_screens()

    def save_card_controls(self, role: str, duration_override: float, mute_audio: bool, crop_x: float, crop_y: float) -> None:
        idx = self.project.selected_storyboard_index
        if idx < 0 or idx >= len(self.project.selected_storyboard):
            return
        card = self.project.selected_storyboard[idx]
        card.role = role
        card.duration_override = max(0.0, duration_override)
        card.mute_audio = mute_audio
        card.crop_focus_x = max(0.0, min(1.0, crop_x))
        card.crop_focus_y = max(0.0, min(1.0, crop_y))
        self.app.refresh_all_screens()

    def set_compare_mode(self, mode: str) -> None:
        idx = self.project.selected_storyboard_index
        if idx < 0 or idx >= len(self.project.selected_storyboard):
            return
        card = self.project.selected_storyboard[idx]
        if not card.pair_asset_id or card.role != "proof":
            return
        card.compare_mode = mode if mode in {"split-screen", "sequential"} else "split-screen"
        card.use_split_screen = card.compare_mode == "split-screen"
        self.project.automation_notes.append(f"Comparison mode set to {card.compare_mode} for the selected proof slot.")
        self.app.refresh_all_screens()

    def set_preview_canvas_family(self, canvas_family: str) -> None:
        if canvas_family not in CANVAS_FAMILIES:
            return
        self.project.preview_canvas_family = canvas_family
        self.project.automation_notes.append(f"Live crop preview switched to {canvas_family}.")
        self.app.refresh_all_screens()

    def set_preview_platform_variant(self, variant: str) -> None:
        if variant not in PLATFORM_VARIANTS:
            return
        self.project.preview_platform_variant = variant
        self.project.automation_notes.append(f"Preview safe-zone profile set to {variant}.")
        self.app.refresh_all_screens()

    def set_preview_caption_style(self, style_name: str) -> None:
        if style_name not in CAPTION_STYLE_PRESETS:
            return
        self.project.preview_caption_style = style_name
        self.project.automation_notes.append(f"Caption mock style set to {style_name}.")
        self.app.refresh_all_screens()

    def set_preview_caption_position(self, position_name: str) -> None:
        if position_name not in CAPTION_POSITION_PRESETS:
            return
        self.project.preview_caption_position = position_name
        self.project.automation_notes.append(f"Caption position preset set to {position_name}.")
        self.app.refresh_all_screens()

    def set_preview_caption_emphasis(self, emphasis_name: str) -> None:
        if emphasis_name not in CAPTION_EMPHASIS_PRESETS:
            return
        self.project.preview_caption_emphasis = emphasis_name
        self.project.automation_notes.append(f"Caption pacing preset set to {emphasis_name}.")
        self.app.refresh_all_screens()

    def set_preview_from_platform_label(self, draft_id: str, label: str) -> None:
        variant = resolve_platform_variant_from_label(label)
        self.project.selected_draft_id = draft_id
        self.project.preview_platform_variant = variant
        self.project.preview_canvas_family = resolve_canvas_for_platform_variant(variant, self.project.preview_canvas_family)
        self.app.refresh_all_screens()

    def _apply_draft_preview_preferences(self, draft: DraftOption) -> None:
        if draft.locked_platform_variant:
            self.project.preview_platform_variant = draft.locked_platform_variant
            self.project.preview_canvas_family = resolve_canvas_for_platform_variant(draft.locked_platform_variant, self.project.preview_canvas_family)
        if draft.locked_caption_style:
            self.project.preview_caption_style = draft.locked_caption_style
        if draft.locked_caption_position:
            self.project.preview_caption_position = draft.locked_caption_position
        if draft.locked_caption_emphasis:
            self.project.preview_caption_emphasis = draft.locked_caption_emphasis

    def lock_preview_setup_to_draft(self, draft_id: str) -> None:
        draft = next((d for d in self.project.drafts if d.draft_id == draft_id), None)
        if not draft:
            return
        draft.locked_platform_variant = self.project.preview_platform_variant
        draft.locked_caption_style = self.project.preview_caption_style
        draft.locked_caption_position = self.project.preview_caption_position
        draft.locked_caption_emphasis = self.project.preview_caption_emphasis
        self.project.automation_notes.append(
            f"Locked preview setup to {draft.name}: {draft.locked_platform_variant} • {draft.locked_caption_style} / {draft.locked_caption_position} / {draft.locked_caption_emphasis}."
        )
        self.app.refresh_all_screens()

    def set_export_score_weight(self, key: str, value: int) -> None:
        if key not in {"copy", "proof", "cta", "platform"}:
            return
        value = max(0, min(5, int(value)))
        self.project.export_score_weights[key] = value
        self.app.refresh_all_screens()

    def reset_export_score_weights(self) -> None:
        self.project.export_score_weights = {"copy": 3, "proof": 3, "cta": 3, "platform": 2}
        self.app.refresh_all_screens()

    def save_export_decision_notes(self, text: str) -> None:
        self.project.export_decision_notes = text.strip()
        self.app.refresh_all_screens()

    def approve_export_source(self, source: str) -> None:
        if source == "candidate":
            snapshot = self.build_draft_export_snapshot(self.export_candidate_draft(), "Export Candidate")
        else:
            snapshot = self.build_selected_export_snapshot()
        if snapshot is None:
            return
        self.project.final_approval_locked = True
        self.project.approved_export_source = snapshot.source_label
        self.project.approved_export_snapshot = ExportVersionSnapshot(**asdict(snapshot))
        self.project.automation_notes.append(f"Final export locked to {snapshot.source_label}: {snapshot.draft_name}.")
        self.app.refresh_all_screens()

    def clear_export_approval(self) -> None:
        self.project.final_approval_locked = False
        self.project.approved_export_source = ""
        self.project.approved_export_snapshot = None
        self.app.refresh_all_screens()

    def export_candidate_draft(self) -> Optional[DraftOption]:
        return next((d for d in self.project.drafts if d.draft_id == self.project.export_candidate_draft_id), None)

    def get_last_export_snapshot(self) -> Optional[ExportVersionSnapshot]:
        if self.project.last_export_snapshot is not None:
            return self.project.last_export_snapshot
        if not self.project.last_export_path:
            return None
        try:
            snapshot_path = Path(self.project.last_export_path) / "09_Archive_Notes" / "export_compare_snapshot.json"
            if snapshot_path.exists():
                data = json.loads(snapshot_path.read_text(encoding="utf-8"))
                self.project.last_export_snapshot = ExportVersionSnapshot(**data)
                return self.project.last_export_snapshot
        except Exception:
            return None
        return None

    def _compute_runtime_estimate(self, cards: List[StoryboardCard]) -> float:
        asset_map = {asset.asset_id: asset for asset in self.project.assets}
        total = 0.0
        for card in cards:
            asset = asset_map.get(card.asset_id)
            if asset is None:
                total += max(0.3, card.duration_override or 3.0)
            else:
                total += max(0.3, card.effective_duration(asset))
        return round(total, 2)

    def _snapshot_from_cards(
        self,
        *,
        source_label: str,
        draft_id: str,
        draft_name: str,
        cards: List[StoryboardCard],
        hook: str,
        title: str,
        cta: str,
        bundle: str,
        platform_variant: str,
        caption_style: str,
        caption_position: str,
        caption_emphasis: str,
        rationale: str = "",
        export_path: str = "",
    ) -> ExportVersionSnapshot:
        asset_map = {asset.asset_id: asset for asset in self.project.assets}
        role_parts: List[str] = []
        title_parts: List[str] = []
        for idx, card in enumerate(cards, start=1):
            asset = asset_map.get(card.asset_id)
            card_title = asset.title if asset else f"Missing asset {idx}"
            title_parts.append(card_title)
            role_label = card.role.upper()
            if getattr(card, "pair_asset_id", ""):
                role_label += " + COMPARE"
            role_parts.append(role_label)
        runtime = self._compute_runtime_estimate(cards)
        return ExportVersionSnapshot(
            source_label=source_label,
            draft_id=draft_id,
            draft_name=draft_name,
            runtime_estimate=runtime,
            bundle=bundle,
            platform_variant=platform_variant,
            caption_style=caption_style,
            caption_position=caption_position,
            caption_emphasis=caption_emphasis,
            hook=hook,
            title=title,
            cta=cta,
            rationale=rationale,
            storyboard_roles=role_parts,
            storyboard_titles=title_parts,
            storyboard_cards=[asdict(card) for card in cards],
            export_path=export_path,
        )

    def build_selected_export_snapshot(self) -> Optional[ExportVersionSnapshot]:
        if not self.project.selected_storyboard:
            return None
        draft = self.project.selected_draft()
        draft_name = draft.name if draft else "Selected Draft"
        return self._snapshot_from_cards(
            source_label="Selected Draft",
            draft_id=self.project.selected_draft_id,
            draft_name=draft_name,
            cards=self.project.selected_storyboard,
            hook=self.project.hook_text,
            title=self.project.title_text,
            cta=self.project.cta_text,
            bundle=self.project.publish_bundle,
            platform_variant=self.project.preview_platform_variant,
            caption_style=self.project.preview_caption_style,
            caption_position=self.project.preview_caption_position,
            caption_emphasis=self.project.preview_caption_emphasis,
            rationale=draft.rationale if draft else "Currently loaded draft with live Quick Refine changes.",
        )

    def build_draft_export_snapshot(self, draft: Optional[DraftOption], source_label: str = "Export Candidate") -> Optional[ExportVersionSnapshot]:
        if draft is None:
            return None
        return self._snapshot_from_cards(
            source_label=source_label,
            draft_id=draft.draft_id,
            draft_name=draft.name,
            cards=draft.storyboard_cards,
            hook=draft.hook_options[0] if draft.hook_options else self.project.hook_text,
            title=draft.title_options[0] if draft.title_options else self.project.title_text,
            cta=draft.cta_options[0] if draft.cta_options else self.project.cta_text,
            bundle=draft.recommended_bundle or self.project.publish_bundle,
            platform_variant=draft.locked_platform_variant or self.project.preview_platform_variant,
            caption_style=draft.locked_caption_style or self.project.preview_caption_style,
            caption_position=draft.locked_caption_position or self.project.preview_caption_position,
            caption_emphasis=draft.locked_caption_emphasis or self.project.preview_caption_emphasis,
            rationale=draft.rationale,
        )

    def _cards_from_snapshot(self, snapshot: ExportVersionSnapshot) -> List[StoryboardCard]:
        cards: List[StoryboardCard] = []
        for item in snapshot.storyboard_cards:
            if isinstance(item, StoryboardCard):
                cards.append(StoryboardCard(**asdict(item)))
            elif isinstance(item, dict):
                cards.append(StoryboardCard(**item))
        return cards

    def _project_for_snapshot(self, snapshot: ExportVersionSnapshot) -> ProjectState:
        export_project = copy.deepcopy(self.project)
        export_project.selected_draft_id = snapshot.draft_id
        export_project.publish_bundle = snapshot.bundle
        export_project.preview_platform_variant = snapshot.platform_variant
        export_project.preview_canvas_family = resolve_canvas_for_platform_variant(snapshot.platform_variant, export_project.preview_canvas_family)
        export_project.preview_caption_style = snapshot.caption_style
        export_project.preview_caption_position = snapshot.caption_position
        export_project.preview_caption_emphasis = snapshot.caption_emphasis
        export_project.hook_text = snapshot.hook
        export_project.title_text = snapshot.title
        export_project.cta_text = snapshot.cta
        export_project.selected_storyboard = self._cards_from_snapshot(snapshot)
        export_project.selected_storyboard_index = 0 if export_project.selected_storyboard else -1
        return export_project

    def _resolved_export_snapshot(self) -> Optional[ExportVersionSnapshot]:
        if self.project.final_approval_locked and self.project.approved_export_snapshot is not None:
            return self.project.approved_export_snapshot
        export_snapshot = self.build_draft_export_snapshot(self.export_candidate_draft(), "Export Candidate")
        if export_snapshot is not None:
            return export_snapshot
        return self.build_selected_export_snapshot()

    def promote_export_candidate(self, draft_id: str) -> None:
        draft = next((d for d in self.project.drafts if d.draft_id == draft_id), None)
        if not draft:
            return
        self.project.export_candidate_draft_id = draft_id
        for item in self.project.drafts:
            item.is_export_candidate = item.draft_id == draft_id
        self.project.selected_draft_id = draft_id
        self.project.selected_storyboard = [StoryboardCard(**asdict(card)) for card in draft.storyboard_cards]
        self.project.selected_storyboard_index = 0 if self.project.selected_storyboard else -1
        self._apply_draft_preview_preferences(draft)
        self.project.hook_text = draft.hook_options[0] if draft.hook_options else self.project.hook_text
        self.project.title_text = draft.title_options[0] if draft.title_options else self.project.title_text
        self.project.cta_text = draft.cta_options[0] if draft.cta_options else self.project.cta_text
        self.project.automation_notes.append(f"Promoted {draft.name} as the export candidate.")
        self.app.refresh_all_screens()

    def choose_copy_from_draft(self, draft_id: str, field_name: str, index: int = 0) -> None:
        draft = next((d for d in self.project.drafts if d.draft_id == draft_id), None)
        if not draft:
            return
        options = draft.hook_options if field_name == "hook" else draft.title_options if field_name == "title" else draft.cta_options
        if not options:
            return
        value = options[max(0, min(index, len(options) - 1))]
        self.choose_copy(field_name, value)

    def reorder_storyboard_card(self, from_idx: int, to_idx: int) -> None:
        if from_idx == to_idx:
            return
        storyboard = self.project.selected_storyboard
        if from_idx < 0 or to_idx < 0 or from_idx >= len(storyboard) or to_idx >= len(storyboard):
            return
        card = storyboard.pop(from_idx)
        storyboard.insert(to_idx, card)
        self.project.selected_storyboard_index = to_idx
        self.project.automation_notes.append(f"Reordered storyboard card {from_idx + 1} to position {to_idx + 1}.")
        self.app.refresh_all_screens()

    def choose_copy(self, field_name: str, value: str) -> None:
        if field_name == "hook":
            self.project.hook_text = value
        elif field_name == "title":
            self.project.title_text = value
        elif field_name == "cta":
            self.project.cta_text = value
        self.app.refresh_all_screens()

    def set_caption_mode(self, mode: str) -> None:
        self.project.caption_mode = mode
        self.app.refresh_all_screens()

    def _last_project_pointer_path(self) -> Path:
        return self.content_system.paths["state"] / "last_project_path.txt"

    def _write_last_project_pointer(self) -> None:
        if self.current_project_path:
            pointer = self._last_project_pointer_path()
            pointer.parent.mkdir(parents=True, exist_ok=True)
            pointer.write_text(str(self.current_project_path), encoding="utf-8")

    def _read_last_project_pointer(self) -> Optional[Path]:
        pointer = self._last_project_pointer_path()
        if not pointer.exists():
            return None
        try:
            path = Path(pointer.read_text(encoding="utf-8").strip())
            return path if path.exists() else None
        except Exception:
            return None

    def _load_project_from_path(self, path: Path) -> None:
        self.project = ProjectSerializer.load(path)
        self.current_project_path = path
        self._write_last_project_pointer()
        self.app.refresh_all_screens()
        self.app.set_status(f"Loaded project: {path.name}")

    def save_project(self) -> None:
        if self.current_project_path is None:
            project_dir = self.content_system.next_project_dir(self.project.project_name)
            self.current_project_path = project_dir / "project.json"
        ProjectSerializer.save(self.project, self.current_project_path)
        self._write_last_project_pointer()
        self.app.refresh_all_screens()
        self.app.set_status(f"Project saved: {self.current_project_path}")

    def save_project_as(self) -> None:
        initial_dir = str(self.content_system.paths["projects"])
        initial_name = f"{slugify(self.project.project_name)}.json"
        path = filedialog.asksaveasfilename(
            title="Save Project As",
            initialdir=initial_dir,
            initialfile=initial_name,
            defaultextension=".json",
            filetypes=[("Project JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self.current_project_path = Path(path)
        self.current_project_path.parent.mkdir(parents=True, exist_ok=True)
        ProjectSerializer.save(self.project, self.current_project_path)
        self._write_last_project_pointer()
        self.app.refresh_all_screens()
        self.app.set_status(f"Project saved as: {self.current_project_path}")

    def load_project(self) -> None:
        path = filedialog.askopenfilename(title="Load Project", initialdir=str(self.content_system.paths["projects"]), filetypes=[("Project JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self._load_project_from_path(Path(path))

    def continue_last_project(self) -> None:
        path = self._read_last_project_pointer()
        if not path:
            messagebox.showinfo(APP_NAME, "No recent project path was found yet. Save or load a project first.")
            return
        self._load_project_from_path(path)

    def open_current_project_folder(self) -> None:
        target = None
        if self.current_project_path and self.current_project_path.exists():
            target = self.current_project_path.parent
        elif self.content_system.paths["projects"].exists():
            target = self.content_system.paths["projects"]
        if not target:
            return
        try:
            os.startfile(str(target))
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open project folder.\n\n{exc}")

    def copy_current_project_path(self) -> None:
        value = str(self.current_project_path) if self.current_project_path else ""
        self.app.clipboard_clear()
        self.app.clipboard_append(value)
        self.app.update_idletasks()
        self.app.set_status("Current project path copied to clipboard." if value else "No current project path to copy.")

    def new_project(self) -> None:
        self.project = ProjectState()
        self.current_project_path = None
        self.app.refresh_all_screens()
        self.app.show_screen("choose_outcome")
        self.app.set_status("Started a new build.")

    def export_project(self) -> None:
        snapshot = self._resolved_export_snapshot()
        if snapshot is None:
            messagebox.showerror(APP_NAME, "Choose, promote, or approve a draft before exporting.")
            return
        # Reset the export progress bar to processing state immediately
        try:
            self.app.export_screen.export_started()
        except Exception:
            pass
        self._run_background(self._export_worker, None, "Preparing export package...")

    def drain_worker_queue(self) -> None:
        while True:
            try:
                kind, payload = self.worker_queue.get_nowait()
            except queue.Empty:
                break

            payload_session_id = None
            payload_value = payload
            if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[0], int):
                payload_session_id, payload_value = payload

            if kind in {"status", "intake_stage", "intake_reset", "intake_stage_active", "intake_stage_complete", "intake_progress", "intake_asset_ready", "intake_done", "intake_cycle_complete"}:
                if payload_session_id is not None and payload_session_id != self.active_intake_session_id:
                    continue

            if kind == "status":
                self.app.set_status(payload_value)
            elif kind == "intake_stage":
                self.app.drop_files_screen.set_stage_complete(payload_value)
            elif kind == "intake_reset":
                self.app.drop_files_screen.reset_intake_view(payload_value)
                self.app.refresh_all_screens()
            elif kind == "intake_stage_active":
                self.project.intake_state = "processing"
                self.project.intake_stage = str(payload_value or "")
                self.app.drop_files_screen.set_stage_active(self.project.intake_stage)
                self.app.drop_files_screen.refresh()
            elif kind == "intake_stage_complete":
                self.app.drop_files_screen.set_stage_complete(str(payload_value or ""))
                self.app.drop_files_screen.refresh()
            elif kind == "intake_progress":
                if isinstance(payload_value, dict):
                    self.project.intake_state = payload_value.get("state", self.project.intake_state)
                    self.project.intake_stage = payload_value.get("stage", self.project.intake_stage)
                    self.project.intake_total = int(payload_value.get("total", self.project.intake_total or 0) or 0)
                    self.project.intake_processed = int(payload_value.get("processed", self.project.intake_processed or 0) or 0)
                    self.project.intake_current_item = payload_value.get("detail", payload_value.get("message", self.project.intake_current_item))
                self.app.drop_files_screen.set_progress(payload_value)
                self.app.drop_files_screen.refresh()
                self.app.update_idletasks()
            elif kind == "intake_asset_ready":
                self.app.refresh_all_screens()
                self.app.update_idletasks()
            elif kind == "video_asset_enriched":
                self.app.refresh_all_screens()
                self.app.set_status("Updated video preview metadata.")
            elif kind == "video_followup_done":
                self.video_followup_in_progress = False
                self._refresh_recommendations_after_video_followup()
                self.app.refresh_all_screens()
            elif kind == "automation_note":
                self.project.automation_notes.append(payload_value)
                self.app.refresh_all_screens()
            elif kind == "intake_done":
                self.app.refresh_all_screens()
                self.app.show_screen("drop_files")
                if self.pending_asset_ids:
                    self.app.set_status(
                        f"Current intake pass complete. Continuing with {len(self.pending_asset_ids)} queued file(s)..."
                    )
                elif self.project.drafts:
                    self.app.set_status(
                        "Media intake complete. You can add more media or references here, or click Next to review the recommended drafts."
                    )
                else:
                    self.app.set_status("Media intake complete. You can add more media or references here, or click Next to continue.")
            elif kind == "intake_cycle_complete":
                had_error = bool(payload_value.get("had_error")) if isinstance(payload_value, dict) else False
                self.intake_in_progress = False
                self.current_intake_asset_ids = []
                if had_error:
                    if self.pending_asset_ids:
                        self.app.set_status(
                            f"Media intake hit an error. {len(self.pending_asset_ids)} queued file(s) are still waiting."
                        )
                elif self.pending_asset_ids:
                    self._consume_pending_imports()
            elif kind == "drafts_done":
                self.app.refresh_all_screens()
            elif kind == "direction_rebuild_done":
                self.app.refresh_all_screens()
                if self.stay_on_drop_files_after_direction_override:
                    self.stay_on_drop_files_after_direction_override = False
                    self.app.show_screen("drop_files")
                    self.app.set_status("Direction updated. Add more media or click Continue to Drafts when you are ready.")
                else:
                    self.app.show_screen("draft_gallery")
                    self.app.set_status("We rebuilt a fresh recommendation using the same imported files and your new direction.")
            elif kind == "export_log":
                self.app.export_screen.append_log(payload_value)
            elif kind == "export_done":
                export_path = payload_value.get("path", "") if isinstance(payload_value, dict) else str(payload_value)
                snapshot = payload_value.get("snapshot") if isinstance(payload_value, dict) else None
                self.project.last_export_path = export_path
                if snapshot:
                    try:
                        self.project.last_export_snapshot = ExportVersionSnapshot(**snapshot)
                    except Exception:
                        self.project.last_export_snapshot = None
                # Mark export progress bar complete (green)
                try:
                    self.app.export_screen._set_export_progress_state("complete", "Export complete.")
                    self.app.export_screen._export_progress_var.set(100)
                except Exception:
                    pass
                self.app.refresh_all_screens()
                media_outputs = payload_value.get("media_outputs", []) if isinstance(payload_value, dict) else []
                outputs_text = "\n".join(media_outputs[:10]) if media_outputs else "(no media outputs listed)"
                messagebox.showinfo(APP_NAME, f"Export complete:\n{export_path}\n\nMedia files created:\n{outputs_text}")
            elif kind == "error":
                error_session_id = payload.get("session_id") if isinstance(payload, dict) else None
                error_text = payload.get("text") if isinstance(payload, dict) else str(payload)
                if error_session_id is not None and error_session_id != self.active_intake_session_id:
                    continue
                if self.project.intake_state == "processing":
                    self.project.intake_state = "error"
                    self.project.intake_error = error_text
                    self.app.drop_files_screen.set_progress({
                        "percent": float(self.app.drop_files_screen.intake_progress_var.get()),
                        "message": "Media intake hit an error. Review the error dialog for details.",
                        "state": "error",
                        "stage": self.project.intake_stage,
                        "total": self.project.intake_total,
                        "processed": self.project.intake_processed,
                        "detail": self.project.intake_current_item,
                    })
                else:
                    # Non-intake error — mark export bar as failed if we were exporting
                    try:
                        if self.app.export_screen._export_progress_var.get() > 0:
                            self.app.export_screen._set_export_progress_state(
                                "error", "Export failed — see log for details.")
                    except Exception:
                        pass
                messagebox.showerror(APP_NAME, error_text)
                self.app.set_status("An error occurred.")
        self.app.after(150, self.drain_worker_queue)

    def _run_background(self, func, arg, status_text: str) -> None:
        self.app.set_status(status_text)

        def runner():
            try:
                if arg is None:
                    func()
                else:
                    func(arg)
            except Exception:
                self.worker_queue.put(("error", traceback.format_exc()))

        threading.Thread(target=runner, daemon=True).start()

    def _intake_pipeline(self, intake_payload: Dict[str, Any]) -> None:
        session_id = int(intake_payload.get("session_id", 0))
        imported = list(intake_payload.get("assets", []) or [])
        total = len(imported)

        def session_active() -> bool:
            return self.intake_in_progress and session_id == self.active_intake_session_id

        try:
            if not session_active():
                return
            self.project.intake_state = "processing"
            self.project.intake_stage = INTAKE_STAGES[1]
            self.project.intake_total = total
            self.project.intake_processed = 0
            self.project.intake_current_item = "Creating previews for imported media..."
            self.project.intake_error = ""
            self.worker_queue.put(("intake_stage_active", (session_id, INTAKE_STAGES[1])))
            self.worker_queue.put(("status", (session_id, self.project.intake_current_item)))
            self.worker_queue.put(("intake_progress", (session_id, {"percent": 22, "message": self.project.intake_current_item, "state": "processing", "stage": INTAKE_STAGES[1], "total": total, "processed": 0, "detail": self.project.intake_current_item})))

            if not session_active():
                return
            self.project.intake_stage = INTAKE_STAGES[2]
            self.worker_queue.put(("intake_stage_complete", (session_id, INTAKE_STAGES[1])))
            self.worker_queue.put(("intake_stage_active", (session_id, INTAKE_STAGES[2])))
            self.worker_queue.put(("status", (session_id, "Creating previews and reading media...")))
            for idx, asset in enumerate(imported, start=1):
                if not session_active():
                    return
                if asset.asset_id not in {existing.asset_id for existing in self.project.assets}:
                    continue
                current_detail = f"Analyzing file {idx}/{max(1, total)}: {asset.title}"
                self.project.intake_current_item = current_detail
                existing_preview = asset.analysis.preview_path
                existing_waveform = asset.analysis.waveform_path
                analyzed = self.analyzer.analyze(asset)
                if not session_active():
                    return
                if asset.asset_id not in {existing.asset_id for existing in self.project.assets}:
                    continue
                if not analyzed.preview_path and existing_preview:
                    analyzed.preview_path = existing_preview
                    analyzed.analysis_notes.append("Keeping placeholder preview until a richer preview is available.")
                if not analyzed.waveform_path and existing_waveform:
                    analyzed.waveform_path = existing_waveform
                asset.analysis = analyzed
                asset.notes = ""
                self.project.intake_processed = idx
                percent = 22 + (idx / max(1, total)) * 38
                self.worker_queue.put(("status", (session_id, current_detail)))
                self.worker_queue.put(("intake_progress", (session_id, {"percent": percent, "message": current_detail, "state": "processing", "stage": INTAKE_STAGES[2], "total": total, "processed": idx, "detail": current_detail})))
                self.worker_queue.put(("intake_asset_ready", (session_id, asset.asset_id)))

            if not session_active():
                return
            self.project.intake_stage = INTAKE_STAGES[3]
            self.worker_queue.put(("intake_stage_complete", (session_id, INTAKE_STAGES[2])))
            self.worker_queue.put(("intake_stage_active", (session_id, INTAKE_STAGES[3])))
            self.worker_queue.put(("status", (session_id, "Detecting likely before/after pairs...")))
            self.worker_queue.put(("intake_progress", (session_id, {"percent": 66, "message": "Detecting likely before/after pairs...", "state": "processing", "stage": INTAKE_STAGES[3], "total": total, "processed": total, "detail": "Detecting likely before/after pairs..."})))
            self.project.pair_suggestions = self.analyzer.detect_pair_suggestions(self.project.assets)
            if self.project.pair_suggestions:
                top_pair = self.project.pair_suggestions[0]
                self.worker_queue.put(("automation_note", f"Detected likely comparison pair (score {top_pair.score:.2f}): {top_pair.reason}"))

            if not session_active():
                return
            self.project.intake_stage = INTAKE_STAGES[4]
            self.worker_queue.put(("intake_stage_complete", (session_id, INTAKE_STAGES[3])))
            self.worker_queue.put(("intake_stage_active", (session_id, INTAKE_STAGES[4])))
            self.worker_queue.put(("status", (session_id, "Inferring the strongest content direction...")))
            self.worker_queue.put(("intake_progress", (session_id, {"percent": 72, "message": "Inferring the strongest content direction...", "state": "processing", "stage": INTAKE_STAGES[4], "total": total, "processed": total, "detail": "Inferring the strongest content direction..."})))
            self._infer_direction()

            if not session_active():
                return
            self.project.intake_stage = INTAKE_STAGES[5]
            self.worker_queue.put(("intake_stage_complete", (session_id, INTAKE_STAGES[4])))
            self.worker_queue.put(("intake_stage_active", (session_id, INTAKE_STAGES[5])))
            self.worker_queue.put(("status", (session_id, "Ranking opener, proof, and CTA candidates...")))
            self.worker_queue.put(("intake_progress", (session_id, {"percent": 78, "message": "Ranking opener, proof, and CTA candidates...", "state": "processing", "stage": INTAKE_STAGES[5], "total": total, "processed": total, "detail": "Ranking opener, proof, and CTA candidates..."})))
            self._apply_auto_tags()

            if not session_active():
                return
            self.project.intake_stage = INTAKE_STAGES[6]
            self.worker_queue.put(("intake_stage_complete", (session_id, INTAKE_STAGES[5])))
            self.worker_queue.put(("intake_stage_active", (session_id, INTAKE_STAGES[6])))
            self.worker_queue.put(("status", (session_id, "Building draft options...")))
            self.worker_queue.put(("intake_progress", (session_id, {"percent": 86, "message": "Building draft options...", "state": "processing", "stage": INTAKE_STAGES[6], "total": total, "processed": total, "detail": "Building draft options..."})))
            self.project.drafts = DraftGenerator(self.project).generate()

            if not session_active():
                return
            self.project.intake_stage = INTAKE_STAGES[7]
            self.worker_queue.put(("intake_stage_complete", (session_id, INTAKE_STAGES[6])))
            self.worker_queue.put(("intake_stage_active", (session_id, INTAKE_STAGES[7])))
            self.worker_queue.put(("status", (session_id, "Generating copy suggestions...")))
            self.worker_queue.put(("intake_progress", (session_id, {"percent": 92, "message": "Generating copy suggestions...", "state": "processing", "stage": INTAKE_STAGES[7], "total": total, "processed": total, "detail": "Generating copy suggestions..."})))

            if not session_active():
                return
            self.project.intake_stage = INTAKE_STAGES[8]
            self.worker_queue.put(("intake_stage_complete", (session_id, INTAKE_STAGES[7])))
            self.worker_queue.put(("intake_stage_active", (session_id, INTAKE_STAGES[8])))
            self.worker_queue.put(("status", (session_id, "Preparing caption recommendation...")))
            self.worker_queue.put(("intake_progress", (session_id, {"percent": 96, "message": "Preparing caption recommendation...", "state": "processing", "stage": INTAKE_STAGES[8], "total": total, "processed": total, "detail": "Preparing caption recommendation..."})))
            self._infer_caption_mode()

            if not session_active():
                return
            if self.project.drafts:
                draft = self.project.drafts[0]
                self.project.selected_draft_id = draft.draft_id
                self.project.selected_storyboard = [StoryboardCard(**asdict(c)) for c in draft.storyboard_cards]
                self.project.selected_storyboard_index = 0 if self.project.selected_storyboard else -1
                self.project.hook_text = draft.hook_options[0] if draft.hook_options else self.project.hook_text
                self.project.title_text = draft.title_options[0] if draft.title_options else self.project.title_text
                self.project.cta_text = draft.cta_options[0] if draft.cta_options else self.project.cta_text
                self.project.export_candidate_draft_id = draft.draft_id
                self.worker_queue.put(("automation_note", f"Recommended draft auto-promoted for export: {draft.name}."))

            if not session_active():
                return
            self.project.intake_state = "complete"
            self.worker_queue.put(("intake_stage_complete", (session_id, INTAKE_STAGES[8])))
            self.worker_queue.put(("intake_progress", (session_id, {"percent": 100, "message": f"Media intake complete. Built {len(self.project.drafts)} draft option(s).", "state": "complete", "stage": INTAKE_STAGES[8], "total": total, "processed": total, "detail": "Media intake complete."})))
            self.worker_queue.put(("status", (session_id, f"Media intake complete. Built {len(self.project.drafts)} draft option(s).")))
            self.worker_queue.put(("intake_done", (session_id, None)))
        except Exception:
            if session_active():
                self.project.intake_state = "error"
                self.project.intake_error = traceback.format_exc()
                self.worker_queue.put(("intake_progress", (session_id, {"percent": max(0.0, float(self.project.intake_processed / max(1, total) * 100.0)), "message": "Media intake error", "state": "error", "stage": self.project.intake_stage, "total": total, "processed": self.project.intake_processed, "detail": self.project.intake_current_item or "Media intake error."})))
                self.worker_queue.put(("status", (session_id, "Media intake error.")))
                self.worker_queue.put(("error", {"session_id": session_id, "text": traceback.format_exc()}))
        finally:
            self.worker_queue.put(("intake_cycle_complete", (session_id, {"had_error": self.project.intake_state == "error"})))

    def _apply_before_after_direction(self, reason: str) -> None:
        p = self.project
        p.content_goal = "Before / After Comparison"
        p.template_family = "Before / After Comparison"
        p.publish_bundle = "Meta Creator Pack"
        p.recommended_bundle = "Meta Creator Pack"
        p.hook_angle = "proof"
        p.cta_text = "Listen To Before / After"
        if reason:
            self.worker_queue.put(("automation_note", reason))

    def _should_force_before_after_direction(self) -> bool:
        p = self.project
        if not getattr(p, "auto_inference_enabled", False):
            return False
        if p.content_goal != "Mastering Promo":
            return False
        proof_like_assets = [a for a in p.assets if a.media_type in {"video", "audio"}]
        if not proof_like_assets:
            return False
        images = [a for a in p.assets if a.media_type == "image"]
        durations = [float(a.analysis.duration or 0.0) for a in proof_like_assets if float(a.analysis.duration or 0.0) > 0.0]
        similar_lengths = len(durations) >= 2 and (max(durations) - min(durations) <= max(2.0, 0.25 * max(durations)))
        combined_texts = [
            " ".join([Path(a.path).stem, a.analysis.ocr_text or "", a.analysis.transcript_text or ""]).lower()
            for a in proof_like_assets
        ]
        mastering_keywords = any(
            re.search(r"\b(before|after|premaster|unmastered|mastered|mastering|compare|comparison|versus|vs|a/b|difference)\b", txt)
            for txt in combined_texts
        )
        low_speech = all((a.analysis.speech_likelihood or 0.0) < 0.45 for a in proof_like_assets)
        low_talking = all((a.analysis.talking_head_likelihood or 0.0) < 0.35 for a in proof_like_assets)
        long_enough_demo = any(8.0 <= float(a.analysis.duration or 0.0) <= 45.0 for a in proof_like_assets)
        single_proof_with_support = (
            len(proof_like_assets) == 1
            and long_enough_demo
            and low_speech
            and low_talking
            and (bool(images) or len(p.assets) <= 2 or mastering_keywords)
        )
        paired_proof_demo = (
            len(proof_like_assets) == 2
            and similar_lengths
            and low_speech
            and low_talking
        )
        return single_proof_with_support or paired_proof_demo or mastering_keywords

    def _enforce_before_after_direction_if_needed(self, enrichment_pass: bool = False) -> None:
        if not self._should_force_before_after_direction():
            return
        reason = (
            "Smart Auto fallback forced Before / After Comparison because the imported media looks like proof/demo content rather than a talking-head or promo clip."
            if not enrichment_pass
            else
            "Post-enrichment fallback forced Before / After Comparison because the imported media still looks like proof/demo content rather than a talking-head or promo clip."
        )
        self._apply_before_after_direction(reason)

    def _infer_direction(self, force: bool = False) -> None:
        p = self.project
        if not force and not getattr(p, "auto_inference_enabled", False):
            return
        pair = p.pair_suggestions[0] if p.pair_suggestions else None
        talking = [a for a in p.assets if a.analysis.talking_head_likelihood >= 0.35]
        speech = [a for a in p.assets if a.analysis.speech_likelihood >= 0.35]
        images = [a for a in p.assets if a.media_type == "image"]
        proof_like_assets = [a for a in p.assets if a.media_type in {"video", "audio"}]
        durations = [a.analysis.duration for a in proof_like_assets if a.analysis.duration > 0]
        similar_lengths = len(durations) >= 2 and (max(durations) - min(durations) <= max(2.0, 0.25 * max(durations)))
        combined_text_by_asset = {
            a.asset_id: " ".join([Path(a.path).stem, a.analysis.ocr_text or "", a.analysis.transcript_text or ""]).strip()
            for a in proof_like_assets
        }
        comparison_signal_assets = [
            a for a in proof_like_assets
            if self.analyzer._has_comparison_intent(combined_text_by_asset.get(a.asset_id, ""))
        ]
        explicit_before_after_assets = [a for a in proof_like_assets if a.analysis.before_after_hint in {"before", "after"}]
        transcript_sparse = bool(proof_like_assets) and all(len((a.analysis.transcript_text or "").strip()) < 24 for a in proof_like_assets)
        pair_like_proof_assets = len(proof_like_assets) == 2 and similar_lengths and transcript_sparse
        likely_before_after_proof_set = (
            len(proof_like_assets) >= 2
            and similar_lengths
            and transcript_sparse
            and (
                len(comparison_signal_assets) >= 1
                or len(explicit_before_after_assets) >= 1
                or len(proof_like_assets) == 2
            )
        )
        single_clip_comparison_demo = len(proof_like_assets) == 1 and len(comparison_signal_assets) >= 1
        mastering_text_demo = len(proof_like_assets) == 1 and any(
            re.search(r"before\s+(?:the\s+)?master(?:ing|ed)?", combined_text_by_asset.get(a.asset_id, "").lower())
            or re.search(r"after\s+(?:the\s+)?master(?:ing|ed)?", combined_text_by_asset.get(a.asset_id, "").lower())
            for a in proof_like_assets
        )
        single_low_speech_proof_demo = (
            len(proof_like_assets) == 1
            and not talking
            and not speech
            and transcript_sparse
            and any(8.0 <= (a.analysis.duration or 0.0) <= 45.0 for a in proof_like_assets)
            and all((a.analysis.talking_head_likelihood or 0.0) < 0.20 for a in proof_like_assets)
            and all((a.analysis.speech_likelihood or 0.0) < 0.25 for a in proof_like_assets)
        )
        text_signaled_before_after = bool(comparison_signal_assets) or len(explicit_before_after_assets) >= 2
        if pair or text_signaled_before_after or likely_before_after_proof_set or single_clip_comparison_demo or mastering_text_demo or pair_like_proof_assets or single_low_speech_proof_demo:
            p.content_goal = "Before / After Comparison"
            p.template_family = "Before / After Comparison"
            p.publish_bundle = "Meta Creator Pack"
            p.recommended_bundle = "Meta Creator Pack"
            p.hook_angle = "proof"
            p.cta_text = "Listen To Before / After"
            if pair:
                self.worker_queue.put(("automation_note", "Strong comparison pair found, so the build now favors before/after content."))
            elif single_clip_comparison_demo:
                self.worker_queue.put(("automation_note", "A single proof clip contained OCR / transcript / filename comparison language, so the build now favors before/after content."))
            elif text_signaled_before_after or mastering_text_demo:
                self.worker_queue.put(("automation_note", "OCR / transcript / filename clues signaled before-and-after proof, including on-screen text such as Before Mastering / After Mastering, so the build now favors before/after content."))
            elif pair_like_proof_assets:
                self.worker_queue.put(("automation_note", "Two similarly timed proof-style media items were detected with sparse transcript content, so the build now favors before/after content."))
            elif single_low_speech_proof_demo:
                self.worker_queue.put(("automation_note", "A single low-speech proof-style demo clip was detected without promo or talking-head signals, so the build now favors before/after content."))
            else:
                self.worker_queue.put(("automation_note", "Multiple similarly timed proof-style media items were detected with comparison-oriented intent signals, so the build now favors before/after content."))
            return
        if talking:
            p.content_goal = "Offer / CTA"
            p.template_family = "Offer / CTA"
            p.publish_bundle = "Meta Creator Pack"
            p.recommended_bundle = "Meta Creator Pack"
            p.hook_angle = "direct"
            p.cta_text = "Get Your Mastering Quote"
            self.worker_queue.put(("automation_note", "Likely talking-head content found, so the build now favors a CTA/promo path."))
            return
        if speech:
            p.content_goal = "Educational Tip"
            p.template_family = "Educational Tip"
            p.publish_bundle = "Full Distribution Pack"
            p.recommended_bundle = "Full Distribution Pack"
            p.hook_angle = "educational"
            p.cta_text = "Hear What Your Mix Needs"
            self.worker_queue.put(("automation_note", "Speech-heavy content found, so the build now leans educational."))
            return
        if images and len(images) == len(p.assets):
            p.content_goal = "New Release Teaser"
            p.template_family = "New Release Teaser"
            p.publish_bundle = "Vertical Everywhere"
            p.recommended_bundle = "Vertical Everywhere"
            p.hook_angle = "curiosity"
            p.cta_text = "Hear The Difference"
            self.worker_queue.put(("automation_note", "Image-only content found, so the build now favors a teaser/promo direction."))
            return
        p.content_goal = "Mastering Promo"
        p.template_family = "Mastering Promo"
        p.publish_bundle = "Professional Cross-Post Pack"
        p.recommended_bundle = "Professional Cross-Post Pack"
        p.hook_angle = "direct"
        p.cta_text = "Start Your Project"
        self.worker_queue.put(("automation_note", "Defaulting to a mastering-promo direction because the imported media did not strongly signal before/after proof, talking-head promo, or education."))

    def _apply_auto_tags(self) -> None:
        if not self.project.assets:
            return
        generator = DraftGenerator(self.project)
        hook_assets = [a.asset_id for a, _ in generator.candidates_for_role("hook")[:3]]
        proof_assets = [a.asset_id for a, _ in generator.candidates_for_role("proof")[:3]]
        cta_assets = [a.asset_id for a, _ in generator.candidates_for_role("cta")[:3]]
        for asset in self.project.assets:
            role_tags: List[str] = []
            if asset.asset_id in hook_assets:
                role_tags.append("hook")
            if asset.asset_id in proof_assets:
                role_tags.append("proof")
            if asset.asset_id in cta_assets:
                role_tags.append("cta")
            if asset.analysis.talking_head_likelihood >= 0.35 and "talking_head" not in asset.tags:
                asset.tags.append("talking_head")
            asset.role_tags = sorted(set(role_tags))
            asset.content_goal_tags = [self.project.content_goal]

    def _infer_caption_mode(self) -> None:
        if self.project.caption_source_path:
            self.project.caption_mode = "Import Existing"
            return
        speech_assets = [a for a in self.project.assets if a.analysis.speech_likelihood >= 0.35]
        if speech_assets and whisper:
            self.project.caption_mode = "Auto"
            self.worker_queue.put(("automation_note", "Speech was detected and auto captions are recommended."))
        elif speech_assets:
            self.project.caption_mode = "Placeholder"
            self.worker_queue.put(("automation_note", "Speech was detected but Whisper is unavailable, so placeholder captions are recommended."))
        else:
            self.project.caption_mode = "None"
            self.worker_queue.put(("automation_note", "No strong speech was detected, so captions are optional for this build."))

    def _draft_regeneration_worker(self) -> None:
        self.project.drafts = DraftGenerator(self.project).generate()
        if self.project.drafts and not self.advanced_mode_enabled:
            recommended = self.project.drafts[0]
            self.project.export_candidate_draft_id = recommended.draft_id
            for item in self.project.drafts:
                item.is_export_candidate = item.draft_id == recommended.draft_id
            self.worker_queue.put(("automation_note", f"Recommended draft refreshed and auto-promoted for export: {recommended.name}."))
        self.worker_queue.put(("drafts_done", None))
        self.worker_queue.put(("status", "Drafts regenerated."))

    def _export_worker(self) -> None:
        snapshot = self._resolved_export_snapshot()
        if snapshot is None:
            self.worker_queue.put(("error", "No export-ready snapshot is available yet."))
            return
        export_project = self._project_for_snapshot(snapshot)
        export_result = self.exporter.export(
            export_project,
            progress=lambda msg: self.worker_queue.put(("export_log", msg)),
            export_snapshot=asdict(snapshot),
        )
        payload = {
            "path": str(export_result.get("export_dir", "")),
            "snapshot": asdict(snapshot),
            "media_outputs": export_result.get("media_outputs", []),
            "render_log_path": export_result.get("render_log_path", ""),
            "result_json_path": export_result.get("result_json_path", ""),
        }
        if export_result.get("success"):
            self.worker_queue.put(("export_done", payload))
            self.worker_queue.put(("status", f"Export complete: {export_result.get('export_dir', '')}"))
        else:
            detail_bits = []
            if export_result.get("render_log_path"):
                detail_bits.append(f"Render log: {export_result.get('render_log_path')}")
            if export_result.get("result_json_path"):
                detail_bits.append(f"Result json: {export_result.get('result_json_path')}")
            detail_text = "\n".join(detail_bits)
            failure_message = "Export failed: no media outputs were created, even after render fallbacks."
            if detail_text:
                failure_message += f"\n\n{detail_text}"
            self.worker_queue.put(("error", failure_message))
            self.worker_queue.put(("status", "Export failed: no media files were created."))



# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------


class ScrollFrame(ttk.Frame):
    def __init__(self, parent, orient: str = "vertical", height: int = 300):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, height=height)
        if orient == "vertical":
            self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
            self.canvas.configure(yscrollcommand=self.scrollbar.set)
            self.scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
            self.canvas.configure(xscrollcommand=self.scrollbar.set)
            self.scrollbar.grid(row=1, column=0, sticky="ew")
        self.inner = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        self.canvas.itemconfigure(self.window_id, width=event.width if event else self.canvas.winfo_width())


class MiniStoryboardStrip(ttk.Frame):
    def __init__(self, parent, select_callback: Optional[Callable[[int], None]] = None, reorder_callback: Optional[Callable[[int, int], None]] = None, height: int = 130):
        super().__init__(parent)
        self.select_callback = select_callback
        self.reorder_callback = reorder_callback
        self.scroll = ScrollFrame(self, orient="horizontal", height=height)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.photo_cache: Dict[str, Any] = {}
        self.drag_from_index: Optional[int] = None
        self.drag_hover_index: Optional[int] = None
        self.cards: List[StoryboardCard] = []
        self.selected_index: int = -1
        self.selected_card: Optional[StoryboardCard] = None

    def _palette_for_role(self, role: str, selected: bool, drag_hover: bool) -> Dict[str, str]:
        if drag_hover:
            return {"bg": "#384b5e", "title": "#ffffff", "meta": "#e7eef7", "sub": "#d2dbe7"}
        role_key = (role or "").strip().lower()
        if role_key == "processing":
            return {
                "bg": "#27548a" if selected else "#1f5fbf",
                "title": "#ffffff",
                "meta": "#ffffff",
                "sub": "#e1eeff",
            }
        if role_key == "queued":
            return {
                "bg": "#8a6514" if selected else "#b0821d",
                "title": "#ffffff",
                "meta": "#fff7dc",
                "sub": "#fff0bf",
            }
        return {
            "bg": "#562727" if selected else "#2a2a2a",
            "title": "#ffffff",
            "meta": "#d0d0d0",
            "sub": "#bfbfbf",
        }

    def render(self, cards: List[StoryboardCard], asset_map: Dict[str, Asset], selected_index: int = -1) -> None:
        self.cards = cards[:]
        if selected_index >= 0:
            self.selected_index = selected_index
        elif self.selected_index >= len(cards):
            self.selected_index = -1
        self.selected_card = self.cards[self.selected_index] if 0 <= self.selected_index < len(self.cards) else None
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        self.photo_cache.clear()
        if not cards:
            self.selected_index = -1
            self.selected_card = None
            ttk.Label(self.scroll.inner, text="No cards yet.").grid(row=0, column=0, padx=6, pady=6)
            return
        for idx, card in enumerate(cards):
            asset = asset_map.get(card.asset_id)
            drag_hover = self.drag_from_index is not None and idx == self.drag_hover_index and idx != self.drag_from_index
            palette = self._palette_for_role(card.role, idx == self.selected_index, drag_hover)
            bg = palette["bg"]
            outer = tk.Frame(self.scroll.inner, bd=1, relief="solid", bg=bg)
            outer.grid(row=0, column=idx, padx=6, pady=6)
            if self.select_callback or self.reorder_callback:
                outer.configure(cursor="hand2")
            title = asset.title if asset else card.asset_id
            title_lbl = tk.Label(outer, text=f"{idx + 1}. {title}", bg=bg, fg=palette["title"], font=("Arial", 9, "bold"), wraplength=130, justify="left")
            title_lbl.pack(fill="x", padx=6, pady=(6, 4))
            thumb = tk.Label(outer, bg=bg)
            thumb.pack(padx=6, pady=(0, 4))
            self._set_thumb(thumb, asset)
            role_text = f"{card.role}"
            role_lbl = tk.Label(outer, text=role_text, bg=bg, fg=palette["meta"])
            role_lbl.pack(fill="x", padx=6)
            if (card.role or "").lower() == "processing":
                split_text = "Analyzing now"
            elif (card.role or "").lower() == "queued":
                split_text = "Waiting in queue"
            elif card.pair_asset_id:
                split_text = card.compare_mode if card.compare_mode in {"split-screen", "sequential"} else ("split-screen" if card.use_split_screen else "sequential")
            else:
                split_text = "single"
            split_lbl = tk.Label(outer, text=split_text, bg=bg, fg=palette["meta"])
            split_lbl.pack(fill="x", padx=6)
            if asset and card.role == asset.media_type and asset.analysis.duration > 0:
                duration_text = f"{asset.analysis.duration:.1f}s"
            else:
                duration_text = f"{card.effective_duration(asset):.1f}s"
            dur_lbl = tk.Label(outer, text=duration_text, bg=bg, fg=palette["meta"])
            dur_lbl.pack(fill="x", padx=6, pady=(0, 4))
            if (card.role or "").lower() == "processing":
                footer_text = "Blue = processing"
            elif (card.role or "").lower() == "queued":
                footer_text = "Gold = queued"
            else:
                footer_text = "Drag to reorder"
            drag_lbl = tk.Label(outer, text=footer_text, bg=bg, fg=palette["sub"], font=("Arial", 8))
            drag_lbl.pack(fill="x", padx=6, pady=(0, 6))
            for widget in (outer, title_lbl, thumb, role_lbl, split_lbl, dur_lbl, drag_lbl):
                self._bind_card(widget, idx)

    def _bind_card(self, widget, idx: int) -> None:
        widget.bind("<ButtonPress-1>", lambda e, i=idx: self._on_press(i))
        widget.bind("<Enter>", lambda e, i=idx: self._on_enter(i))
        widget.bind("<ButtonRelease-1>", lambda e, i=idx: self._on_release(i))

    def _on_press(self, idx: int) -> None:
        self.drag_from_index = idx
        self.drag_hover_index = idx
        self.selected_index = idx
        self.selected_card = self.cards[idx] if 0 <= idx < len(self.cards) else None
        if self.select_callback:
            self.select_callback(idx)

    def _on_enter(self, idx: int) -> None:
        if self.drag_from_index is not None:
            self.drag_hover_index = idx

    def _on_release(self, idx: int) -> None:
        if self.drag_from_index is not None and self.reorder_callback:
            target = self.drag_hover_index if self.drag_hover_index is not None else idx
            if target != self.drag_from_index:
                self.reorder_callback(self.drag_from_index, target)
        self.drag_from_index = None
        self.drag_hover_index = None

    def _set_thumb(self, label, asset: Optional[Asset]) -> None:
        if not asset or not Image or not ImageTk:
            label.configure(text="No preview", fg="#cccccc")
            return
        preview_path = asset.analysis.preview_path or (asset.path if asset.media_type == "image" else asset.analysis.waveform_path)
        if not preview_path or not Path(preview_path).exists():
            label.configure(text="No preview", fg="#cccccc")
            return
        try:
            with Image.open(preview_path) as img:
                img.thumbnail((130, 72))
                photo = ImageTk.PhotoImage(img)
                self.photo_cache[asset.asset_id + str(id(label))] = photo
                label.configure(image=photo, text="")
        except Exception:
            label.configure(text="Preview error", fg="#cccccc")


class ReplacementCandidateGallery(ttk.Frame):
    def __init__(self, parent, replace_callback: Callable[[str], None], preview_callback: Optional[Callable[[str], None]] = None, height: int = 360):
        super().__init__(parent)
        self.replace_callback = replace_callback
        self.preview_callback = preview_callback
        self.scroll = ScrollFrame(self, orient="vertical", height=height)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.photo_cache: Dict[str, Any] = {}

    def render(
        self,
        candidates: List[Tuple[Asset, float]],
        current_asset_id: str,
        role: str,
        preview_asset_id: str = "",
        matched_pair_ids: Optional[set[str]] = None,
        **kwargs,
    ) -> None:
        if matched_pair_ids is None and "matched_candidate_ids" in kwargs:
            matched_pair_ids = kwargs.pop("matched_candidate_ids")
        matched_pair_ids = matched_pair_ids or set()
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        self.photo_cache.clear()
        if not candidates:
            ttk.Label(self.scroll.inner, text="No replacements available yet.").grid(row=0, column=0, padx=8, pady=8, sticky="w")
            return
        for col in range(2):
            self.scroll.inner.columnconfigure(col, weight=1)
        for idx, (asset, score) in enumerate(candidates):
            row, col = divmod(idx, 2)
            is_current = asset.asset_id == current_asset_id
            is_preview = asset.asset_id == preview_asset_id
            is_matched = asset.asset_id in matched_pair_ids
            bg = "#3b4b5a" if is_preview and not is_current else "#4d2b2b" if is_current else "#262626"
            outer = tk.Frame(self.scroll.inner, bd=1, relief="solid", bg=bg)
            outer.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            badges = []
            if is_current:
                badges.append("CURRENT SLOT")
            if is_preview:
                badges.append("PREVIEW CANDIDATE")
            if is_matched:
                badges.append("MATCHED PAIR")
            if asset.analysis.before_after_hint:
                badges.append(asset.analysis.before_after_hint.upper())
            badge_text = " • ".join(badges) if badges else "AVAILABLE CANDIDATE"
            badge_lbl = tk.Label(outer, text=badge_text, bg=bg, fg="#f2bdbd" if is_current else "#cfe3ff" if is_preview else "#d8d8d8", wraplength=220, justify="left")
            badge_lbl.pack(fill="x", padx=8, pady=(8, 2))
            title = f"{asset.title}"
            title_lbl = tk.Label(outer, text=title, bg=bg, fg="white", font=("Arial", 10, "bold"), wraplength=220, justify="left")
            title_lbl.pack(fill="x", padx=8, pady=(0, 4))
            thumb = tk.Label(outer, bg=bg)
            thumb.pack(padx=8, pady=(0, 6))
            self._set_thumb(thumb, asset)
            meta_lbl = tk.Label(outer, text=f"{asset.media_type.title()} • {score:.2f}", bg=bg, fg="#d0d0d0", anchor="w")
            meta_lbl.pack(fill="x", padx=8)
            badges_lbl = tk.Label(outer, text=self._badges(asset), bg=bg, fg="#d0d0d0", wraplength=220, justify="left")
            badges_lbl.pack(fill="x", padx=8, pady=(2, 0))
            reason_lbl = tk.Label(outer, text=self._reason(asset, role), bg=bg, fg="#cfcfcf", wraplength=220, justify="left")
            reason_lbl.pack(fill="x", padx=8, pady=(4, 8))
            if self.preview_callback:
                for widget in (outer, badge_lbl, title_lbl, thumb, meta_lbl, badges_lbl, reason_lbl):
                    widget.configure(cursor="hand2")
                    widget.bind("<Button-1>", lambda e, aid=asset.asset_id: self.preview_callback(aid))
            btn_text = "Already in slot" if is_current else "Replace this slot"
            btn_state = "disabled" if is_current else "normal"
            ttk.Button(outer, text=btn_text, state=btn_state, command=lambda aid=asset.asset_id: self.replace_callback(aid)).pack(anchor="w", padx=8, pady=(0, 8))

    def _badges(self, asset: Asset) -> str:
        badges = []
        a = asset.analysis
        if a.talking_head_likelihood >= 0.35:
            badges.append("talking head")
        if a.split_screen_suitability >= 0.35:
            badges.append("comparison")
        if a.dominant_orientation:
            badges.append(a.dominant_orientation)
        return " • ".join(badges) if badges else "No special tags"

    def _reason(self, asset: Asset, role: str) -> str:
        a = asset.analysis
        if role == "hook":
            return f"Motion {a.motion_score:.2f} • contrast {a.contrast:.2f} • strong opener candidate"
        if role == "proof":
            pair_hint = "pair-ready" if a.before_after_hint or a.split_screen_suitability >= 0.35 else "evidence-focused"
            return f"Audio {a.audio_loudness:.2f} • {pair_hint} • proof candidate"
        if role == "cta":
            return f"Speech {a.speech_likelihood:.2f} • talking-head {a.talking_head_likelihood:.2f} • closer candidate"
        return f"Motion {a.motion_score:.2f} • duration {a.duration:.1f}s • support candidate"

    def _set_thumb(self, label, asset: Optional[Asset]) -> None:
        if not asset or not Image or not ImageTk:
            label.configure(text="No preview", fg="#cccccc")
            return
        preview_path = asset.analysis.preview_path or (asset.path if asset.media_type == "image" else asset.analysis.waveform_path)
        if not preview_path or not Path(preview_path).exists():
            label.configure(text="No preview", fg="#cccccc")
            return
        try:
            with Image.open(preview_path) as img:
                img.thumbnail((220, 120))
                photo = ImageTk.PhotoImage(img)
                self.photo_cache[asset.asset_id + str(id(label))] = photo
                label.configure(image=photo, text="")
        except Exception:
            label.configure(text="Preview error", fg="#cccccc")


class ComparisonPreviewPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.photo_cache: Dict[str, Any] = {}
        self.sequential_job = None
        self.sequential_frames: List[Any] = []
        self.sequential_index = 0
        self.transport_playing = False
        self.transport_label = None

        self.left_wrap = ttk.LabelFrame(self, text="Current Slot", padding=8)
        self.left_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.right_wrap = ttk.LabelFrame(self, text="Preview Candidate", padding=8)
        self.right_wrap.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        for frame in (self.left_wrap, self.right_wrap):
            frame.columnconfigure(0, weight=1)

        self.left_badge_var = tk.StringVar(value="CURRENT SLOT")
        self.right_badge_var = tk.StringVar(value="PREVIEW CANDIDATE")
        ttk.Label(self.left_wrap, textvariable=self.left_badge_var, foreground="#b32d2e").grid(row=0, column=0, sticky="w")
        ttk.Label(self.right_wrap, textvariable=self.right_badge_var, foreground="#2d6fb3").grid(row=0, column=0, sticky="w")
        self.left_title = ttk.Label(self.left_wrap, text="No asset selected", wraplength=260, justify="left")
        self.left_title.grid(row=1, column=0, sticky="w")
        self.left_media = tk.Label(self.left_wrap)
        self.left_media.grid(row=2, column=0, sticky="ew", pady=(6, 6))
        self.left_meta = ttk.Label(self.left_wrap, text="", wraplength=260, justify="left")
        self.left_meta.grid(row=3, column=0, sticky="w")
        self.right_title = ttk.Label(self.right_wrap, text="Click a candidate card to preview it here", wraplength=260, justify="left")
        self.right_title.grid(row=1, column=0, sticky="w")
        self.right_media = tk.Label(self.right_wrap)
        self.right_media.grid(row=2, column=0, sticky="ew", pady=(6, 6))
        self.right_meta = ttk.Label(self.right_wrap, text="", wraplength=260, justify="left")
        self.right_meta.grid(row=3, column=0, sticky="w")

        self.note_var = tk.StringVar(value="Side-by-side preview helps you judge before/after and proof swaps faster.")
        ttk.Label(self, textvariable=self.note_var, wraplength=680, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 8))

        self.crop_wrap = ttk.LabelFrame(self, text="Live Output Crop Preview", padding=8)
        self.crop_wrap.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.crop_wrap.columnconfigure(0, weight=1)
        self.crop_wrap.columnconfigure(1, weight=1)

        ttk.Label(self.crop_wrap, text="Final Export Framing", font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(self.crop_wrap, text="Current Slot", foreground="#b32d2e").grid(row=1, column=0, sticky="w", pady=(4, 2))
        ttk.Label(self.crop_wrap, text="Preview Candidate", foreground="#2d6fb3").grid(row=1, column=1, sticky="w", pady=(4, 2))
        self.final_left = tk.Label(self.crop_wrap)
        self.final_left.grid(row=2, column=0, padx=(0, 6), pady=(0, 8), sticky="nsew")
        self.final_right = tk.Label(self.crop_wrap)
        self.final_right.grid(row=2, column=1, padx=(6, 0), pady=(0, 8), sticky="nsew")

        ttk.Label(self.crop_wrap, text="Comparison Composite Preview", font=("Arial", 10, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.composite_mode_var = tk.StringVar(value="Full composite compare preview will appear here.")
        ttk.Label(self.crop_wrap, textvariable=self.composite_mode_var, foreground="#666666", wraplength=680, justify="left").grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 4))
        self.compare_composite = tk.Label(self.crop_wrap)
        self.compare_composite.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        transport = ttk.Frame(self.crop_wrap)
        transport.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        transport.columnconfigure(4, weight=1)
        self.transport_prev_btn = ttk.Button(transport, text="◀ Prev", command=self._step_prev)
        self.transport_prev_btn.grid(row=0, column=0, padx=(0, 6))
        self.transport_play_btn = ttk.Button(transport, text="Play", command=self._toggle_playback)
        self.transport_play_btn.grid(row=0, column=1, padx=(0, 6))
        self.transport_next_btn = ttk.Button(transport, text="Next ▶", command=self._step_next)
        self.transport_next_btn.grid(row=0, column=2, padx=(0, 10))
        self.transport_slider_var = tk.DoubleVar(value=1.0)
        self.transport_slider = ttk.Scale(transport, from_=1, to=2, orient="horizontal", variable=self.transport_slider_var, command=self._on_transport_scrub)
        self.transport_slider.grid(row=0, column=3, columnspan=2, sticky="ew")
        self.transport_status_var = tk.StringVar(value="Transport becomes active in Sequential compare mode.")
        ttk.Label(transport, textvariable=self.transport_status_var, foreground="#666666").grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))

        self.crop_note_var = tk.StringVar(value="Safe-zone overlays show caption space, key focus area, and per-canvas top/bottom UI margins.")
        ttk.Label(self.crop_wrap, textvariable=self.crop_note_var, wraplength=680, justify="left").grid(row=7, column=0, columnspan=2, sticky="w")

    def render(
        self,
        current_asset: Optional[Asset],
        preview_asset: Optional[Asset],
        role: str,
        pair_asset: Optional[Asset] = None,
        compare_mode: str = "split-screen",
        canvas_family: str = "9x16",
        current_focus: Tuple[float, float] = (0.5, 0.5),
        preview_focus: Tuple[float, float] = (0.5, 0.5),
        caption_text: str = "",
        platform_variant: str = "Auto",
        caption_style: str = "ED Clean Lower Third",
        caption_position: str = "Bottom Center",
        caption_emphasis: str = "Standard",
    ) -> None:
        self.photo_cache.clear()
        self._stop_sequential_animation()
        matched_current_preview = False
        if current_asset and preview_asset:
            hints = {current_asset.analysis.before_after_hint, preview_asset.analysis.before_after_hint}
            matched_current_preview = hints == {"before", "after"}

        current_badges = ["CURRENT SLOT"]
        preview_badges = ["PREVIEW CANDIDATE"]
        if current_asset and current_asset.analysis.before_after_hint:
            current_badges.append(current_asset.analysis.before_after_hint.upper())
        if preview_asset and preview_asset.analysis.before_after_hint:
            preview_badges.append(preview_asset.analysis.before_after_hint.upper())
        if matched_current_preview:
            current_badges.append("MATCHED PAIR")
            preview_badges.append("MATCHED PAIR")
        elif pair_asset and current_asset:
            current_badges.append("MATCHED PAIR")
        self.left_badge_var.set(" • ".join(current_badges))
        self.right_badge_var.set(" • ".join(preview_badges))

        self._render_side(self.left_title, self.left_media, self.left_meta, current_asset, "Current slot")
        self._render_side(self.right_title, self.right_media, self.right_meta, preview_asset, "Preview candidate")

        note = f"Previewing {compare_mode} compare behavior for {canvas_family} using {platform_variant} safe zones, {caption_style} caption styling, and {caption_position} placement."
        if role == "proof" and current_asset and preview_asset:
            if matched_current_preview:
                note = f"Matched Before / After pair detected. Previewing {compare_mode} compare behavior for {canvas_family} using {platform_variant} safe zones, {caption_style} styling, and {caption_position} placement."
            elif preview_asset.analysis.split_screen_suitability >= 0.35:
                note = f"Candidate looks comparison-friendly. Previewing {compare_mode} mode for {canvas_family} with {caption_style} styling and {caption_position} placement."
            elif pair_asset and {current_asset.analysis.before_after_hint, pair_asset.analysis.before_after_hint} == {"before", "after"}:
                note = f"Current proof slot already has a matched Before / After pair with {pair_asset.title}."
        self.note_var.set(note)

        self._render_crop(self.final_left, current_asset, canvas_family, current_focus, mode="full", side="current", caption_text=caption_text, platform_variant=platform_variant, caption_style=caption_style, caption_position=caption_position, caption_emphasis=caption_emphasis)
        self._render_crop(self.final_right, preview_asset, canvas_family, preview_focus, mode="full", side="preview", caption_text=caption_text, platform_variant=platform_variant, caption_style=caption_style, caption_position=caption_position, caption_emphasis=caption_emphasis)
        self._render_composite_compare(
            self.compare_composite,
            current_asset,
            preview_asset,
            canvas_family,
            compare_mode,
            current_focus,
            preview_focus,
            caption_text,
            platform_variant,
            caption_style,
            caption_position,
            caption_emphasis,
        )
        margin = resolve_ui_safe_margins(canvas_family, platform_variant)
        self.crop_note_var.set(
            f"{canvas_family} / {platform_variant}: yellow = caption-safe area, cyan = key visual focus, red = crop focus. Magenta top/bottom bands show UI-safe margins (top {int(margin['top']*100)}%, bottom {int(margin['bottom']*100)}%). Caption mock style: {caption_style} • pacing: {caption_emphasis}."
        )

    def _render_side(self, title_lbl, media_lbl, meta_lbl, asset: Optional[Asset], fallback: str) -> None:
        if not asset:
            title_lbl.configure(text=fallback)
            media_lbl.configure(image="", text="No preview", fg="#cccccc")
            meta_lbl.configure(text="")
            return
        title_lbl.configure(text=asset.title)
        preview_path = asset.analysis.preview_path or (asset.path if asset.media_type == "image" else asset.analysis.waveform_path)
        self._set_image_from_path(media_lbl, preview_path, asset.asset_id + str(id(media_lbl)), (250, 150))
        a = asset.analysis
        hint_text = a.before_after_hint.title() if a.before_after_hint else "No pair hint"
        meta_lbl.configure(text=f"{asset.media_type.title()} • {a.summary()} • {hint_text}")

    def _render_crop(self, label, asset: Optional[Asset], canvas_family: str, focus: Tuple[float, float], mode: str = "full", side: str = "current", caption_text: str = "", platform_variant: str = "Auto", caption_style: str = "ED Clean Lower Third", caption_position: str = "Bottom Center", caption_emphasis: str = "Standard") -> None:
        if not asset:
            label.configure(image="", text="No crop preview", fg="#cccccc")
            return
        preview_path = asset.analysis.preview_path or (asset.path if asset.media_type == "image" else asset.analysis.waveform_path)
        if not preview_path or not Image or not ImageTk or not Path(preview_path).exists():
            label.configure(image="", text="No crop preview", fg="#cccccc")
            return
        try:
            with Image.open(preview_path) as img:
                img = ImageOps.exif_transpose(img).convert("RGB")
                target_w, target_h = CANVAS_FAMILIES.get(canvas_family, CANVAS_FAMILIES["9x16"])
                if mode == "split":
                    target_w = max(1, target_w // 2)
                cropped = self._crop_to_dimensions(img, target_w, target_h, focus)
                overlaid = self._apply_safe_zone_overlays(cropped, focus, canvas_family=canvas_family, mode=mode, side=side, caption_text=caption_text, platform_variant=platform_variant, caption_style=caption_style, caption_position=caption_position, caption_emphasis=caption_emphasis)
                overlaid.thumbnail((220, 180))
                photo = ImageTk.PhotoImage(overlaid)
                key = asset.asset_id + str(id(label)) + canvas_family + mode + side + caption_text[:20] + platform_variant + caption_style
                self.photo_cache[key] = photo
                label.configure(image=photo, text="")
        except Exception:
            label.configure(image="", text="Crop preview error", fg="#cccccc")

    def _render_composite_compare(
        self,
        label,
        current_asset: Optional[Asset],
        preview_asset: Optional[Asset],
        canvas_family: str,
        compare_mode: str,
        current_focus: Tuple[float, float],
        preview_focus: Tuple[float, float],
        caption_text: str,
        platform_variant: str,
        caption_style: str,
        caption_position: str,
        caption_emphasis: str = "Standard",
    ) -> None:
        if not Image or not ImageTk or not current_asset or not preview_asset:
            label.configure(image="", text="Preview a candidate to see the full comparison composite.", fg="#cccccc")
            self.composite_mode_var.set("Comparison composite preview will appear here once both sides are available.")
            return
        curr_path = current_asset.analysis.preview_path or (current_asset.path if current_asset.media_type == "image" else current_asset.analysis.waveform_path)
        prev_path = preview_asset.analysis.preview_path or (preview_asset.path if preview_asset.media_type == "image" else preview_asset.analysis.waveform_path)
        if not curr_path or not prev_path or not Path(curr_path).exists() or not Path(prev_path).exists():
            label.configure(image="", text="Composite preview unavailable for this media.", fg="#cccccc")
            return
        try:
            with Image.open(curr_path) as curr_img_raw, Image.open(prev_path) as prev_img_raw:
                curr_img_raw = ImageOps.exif_transpose(curr_img_raw).convert("RGB")
                prev_img_raw = ImageOps.exif_transpose(prev_img_raw).convert("RGB")
                target_w, target_h = CANVAS_FAMILIES.get(canvas_family, CANVAS_FAMILIES["9x16"])
                base_w = 520
                base_h = max(220, int(round(base_w * target_h / float(target_w))))
                current_hint = current_asset.analysis.before_after_hint.upper() if current_asset.analysis.before_after_hint else "CURRENT SLOT"
                preview_hint = preview_asset.analysis.before_after_hint.upper() if preview_asset.analysis.before_after_hint else "PREVIEW CANDIDATE"
                if compare_mode == "split-screen":
                    half_w = max(1, target_w // 2)
                    curr_crop = self._crop_to_dimensions(curr_img_raw, half_w, target_h, current_focus)
                    prev_crop = self._crop_to_dimensions(prev_img_raw, half_w, target_h, preview_focus)
                    curr_crop = self._apply_safe_zone_overlays(curr_crop, current_focus, canvas_family=canvas_family, mode="split", side="current", caption_text=caption_text, platform_variant=platform_variant, caption_style=caption_style, caption_position=caption_position, caption_emphasis=caption_emphasis)
                    prev_crop = self._apply_safe_zone_overlays(prev_crop, preview_focus, canvas_family=canvas_family, mode="split", side="preview", caption_text=caption_text, platform_variant=platform_variant, caption_style=caption_style, caption_position=caption_position, caption_emphasis=caption_emphasis)
                    curr_crop = curr_crop.resize((base_w // 2, base_h))
                    prev_crop = prev_crop.resize((base_w - base_w // 2, base_h))
                    composite = Image.new("RGB", (base_w, base_h), (12, 12, 12))
                    composite.paste(curr_crop, (0, 0))
                    composite.paste(prev_crop, (base_w // 2, 0))
                    if ImageDraw:
                        draw = ImageDraw.Draw(composite)
                        gutter_x = base_w // 2
                        draw.line((gutter_x, 0, gutter_x, base_h), fill=(110, 190, 255), width=4)
                        self._draw_badge(draw, (8, 8), current_hint, (179, 45, 46, 255))
                        self._draw_badge(draw, (base_w - 152, 8), preview_hint, (45, 111, 179, 255))
                    photo = ImageTk.PhotoImage(composite)
                    key = f"composite_split_{id(label)}_{current_asset.asset_id}_{preview_asset.asset_id}_{canvas_family}_{platform_variant}_{caption_style}_{caption_text[:20]}"
                    self.photo_cache[key] = photo
                    label.configure(image=photo, text="")
                    self._set_transport_enabled(False, "Transport is available in Sequential compare mode.")
                    self.composite_mode_var.set(f"Split-screen composite preview for {canvas_family} • {platform_variant}. Caption style: {caption_style}. Caption position: {caption_position}.")
                else:
                    frame_one = self._crop_to_dimensions(curr_img_raw, target_w, target_h, current_focus)
                    frame_two = self._crop_to_dimensions(prev_img_raw, target_w, target_h, preview_focus)
                    frame_one = self._apply_safe_zone_overlays(frame_one, current_focus, canvas_family=canvas_family, mode="full", side="current", caption_text=caption_text, platform_variant=platform_variant, caption_style=caption_style, caption_position=caption_position, caption_emphasis=caption_emphasis)
                    frame_two = self._apply_safe_zone_overlays(frame_two, preview_focus, canvas_family=canvas_family, mode="full", side="preview", caption_text=caption_text, platform_variant=platform_variant, caption_style=caption_style, caption_position=caption_position, caption_emphasis=caption_emphasis)
                    frame_one = frame_one.resize((base_w, base_h))
                    frame_two = frame_two.resize((base_w, base_h))
                    if ImageDraw:
                        draw_one = ImageDraw.Draw(frame_one)
                        draw_two = ImageDraw.Draw(frame_two)
                        self._draw_badge(draw_one, (8, 8), f"FRAME 1 • {current_hint}", (179, 45, 46, 255))
                        self._draw_badge(draw_two, (8, 8), f"FRAME 2 • {preview_hint}", (45, 111, 179, 255))
                    photo_one = ImageTk.PhotoImage(frame_one)
                    photo_two = ImageTk.PhotoImage(frame_two)
                    key_one = f"sequential_one_{id(label)}_{current_asset.asset_id}_{canvas_family}_{platform_variant}_{caption_style}_{caption_text[:20]}"
                    key_two = f"sequential_two_{id(label)}_{preview_asset.asset_id}_{canvas_family}_{platform_variant}_{caption_style}_{caption_text[:20]}"
                    self.photo_cache[key_one] = photo_one
                    self.photo_cache[key_two] = photo_two
                    self.sequential_frames = [photo_one, photo_two]
                    self.sequential_index = 0
                    self.transport_label = label
                    label.configure(image=self.sequential_frames[0], text="")
                    self._set_transport_enabled(True, f"Sequential mock player ready • frame 1 / {len(self.sequential_frames)}")
                    self.transport_playing = True
                    self.transport_play_btn.configure(text="Pause")
                    self.composite_mode_var.set(f"Live sequential mock player for {canvas_family} • {platform_variant}. Cycling current slot and preview candidate with {caption_style} styling and {caption_position} placement.")
                    self.sequential_job = self.after(700, lambda: self._advance_sequential_preview(label))
        except Exception:
            label.configure(image="", text="Composite preview error", fg="#cccccc")

    def _set_transport_enabled(self, enabled: bool, status: str = "") -> None:
        state = "normal" if enabled else "disabled"
        for widget in (self.transport_prev_btn, self.transport_play_btn, self.transport_next_btn, self.transport_slider):
            try:
                widget.configure(state=state)
            except Exception:
                pass
        if enabled:
            self.transport_slider.configure(from_=1, to=max(1, len(self.sequential_frames)))
            self.transport_slider_var.set(max(1, self.sequential_index + 1))
        else:
            self.transport_slider.configure(from_=1, to=2)
            self.transport_slider_var.set(1)
            self.transport_play_btn.configure(text="Play")
        self.transport_status_var.set(status or ("Transport active" if enabled else "Transport becomes active in Sequential compare mode."))

    def _show_transport_frame(self, index: int) -> None:
        if not self.sequential_frames or self.transport_label is None:
            return
        self.sequential_index = max(0, min(index, len(self.sequential_frames) - 1))
        self.transport_label.configure(image=self.sequential_frames[self.sequential_index], text="")
        self.transport_slider_var.set(self.sequential_index + 1)
        self.transport_status_var.set(f"Sequential mock player • frame {self.sequential_index + 1} / {len(self.sequential_frames)}")

    def _advance_sequential_preview(self, label=None) -> None:
        if not self.sequential_frames:
            self.sequential_job = None
            return
        if label is not None:
            self.transport_label = label
        self.sequential_index = (self.sequential_index + 1) % len(self.sequential_frames)
        self._show_transport_frame(self.sequential_index)
        if self.transport_playing:
            self.sequential_job = self.after(700, self._advance_sequential_preview)
        else:
            self.sequential_job = None

    def _toggle_playback(self) -> None:
        if not self.sequential_frames:
            return
        self.transport_playing = not self.transport_playing
        self.transport_play_btn.configure(text="Pause" if self.transport_playing else "Play")
        if self.transport_playing:
            if self.sequential_job is None:
                self.sequential_job = self.after(700, self._advance_sequential_preview)
        else:
            if self.sequential_job is not None:
                try:
                    self.after_cancel(self.sequential_job)
                except Exception:
                    pass
                self.sequential_job = None

    def _step_prev(self) -> None:
        if not self.sequential_frames:
            return
        self.transport_playing = False
        self.transport_play_btn.configure(text="Play")
        if self.sequential_job is not None:
            try:
                self.after_cancel(self.sequential_job)
            except Exception:
                pass
            self.sequential_job = None
        self._show_transport_frame((self.sequential_index - 1) % len(self.sequential_frames))

    def _step_next(self) -> None:
        if not self.sequential_frames:
            return
        self.transport_playing = False
        self.transport_play_btn.configure(text="Play")
        if self.sequential_job is not None:
            try:
                self.after_cancel(self.sequential_job)
            except Exception:
                pass
            self.sequential_job = None
        self._show_transport_frame((self.sequential_index + 1) % len(self.sequential_frames))

    def _on_transport_scrub(self, value: str) -> None:
        if not self.sequential_frames:
            return
        try:
            idx = int(round(float(value))) - 1
        except Exception:
            return
        self.transport_playing = False
        self.transport_play_btn.configure(text="Play")
        if self.sequential_job is not None:
            try:
                self.after_cancel(self.sequential_job)
            except Exception:
                pass
            self.sequential_job = None
        self._show_transport_frame(idx)

    def _stop_sequential_animation(self) -> None:
        if self.sequential_job is not None:
            try:
                self.after_cancel(self.sequential_job)
            except Exception:
                pass
            self.sequential_job = None
        self.sequential_frames = []
        self.sequential_index = 0
        self.transport_playing = False
        self.transport_label = None
        self._set_transport_enabled(False, "Transport becomes active in Sequential compare mode.")

    def _crop_to_dimensions(self, img, target_w: int, target_h: int, focus: Tuple[float, float]):
        tgt_ratio = target_w / float(target_h)
        src_w, src_h = img.size
        src_ratio = src_w / float(src_h)
        fx = max(0.0, min(1.0, focus[0]))
        fy = max(0.0, min(1.0, focus[1]))
        if src_ratio > tgt_ratio:
            crop_h = src_h
            crop_w = int(round(crop_h * tgt_ratio))
            overflow = max(0, src_w - crop_w)
            left = int(round(overflow * fx))
            left = max(0, min(left, overflow))
            box = (left, 0, left + crop_w, src_h)
        else:
            crop_w = src_w
            crop_h = int(round(crop_w / tgt_ratio))
            overflow = max(0, src_h - crop_h)
            top = int(round(overflow * fy))
            top = max(0, min(top, overflow))
            box = (0, top, src_w, top + crop_h)
        return img.crop(box)

    def _wrap_caption(self, text: str, line_len: int = 24) -> List[str]:
        text = (text or "").strip()
        if not text:
            return []
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if len(candidate) <= line_len or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:3]

    def _apply_safe_zone_overlays(self, img, focus: Tuple[float, float], canvas_family: str = "9x16", mode: str = "full", side: str = "current", caption_text: str = "", platform_variant: str = "Auto", caption_style: str = "ED Clean Lower Third", caption_position: str = "Bottom Center", caption_emphasis: str = "Standard"):
        if not ImageDraw:
            return img
        output = img.copy().convert("RGBA")
        overlay = Image.new("RGBA", output.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        w, h = output.size
        margin = resolve_ui_safe_margins(canvas_family, platform_variant)
        top_h = int(h * margin["top"])
        bottom_h = int(h * margin["bottom"])

        draw.rectangle((0, 0, w, top_h), fill=(190, 60, 200, 52))
        draw.rectangle((0, h - bottom_h, w, h), fill=(190, 60, 200, 52))
        draw.line((0, top_h, w, top_h), fill=(210, 90, 220, 180), width=2)
        draw.line((0, h - bottom_h, w, h - bottom_h), fill=(210, 90, 220, 180), width=2)
        draw.rectangle((1, 1, w - 2, h - 2), outline=(255, 255, 255, 210), width=2)

        mx = int(w * 0.08)
        caption_box = self._resolve_caption_box(w, h, top_h, bottom_h, caption_position)
        caption_top = caption_box[1]
        caption_bottom = caption_box[3]
        draw.rectangle(caption_box, outline=(240, 210, 60, 220), width=2)

        fx1 = int(w * 0.18)
        fy1 = max(top_h + 4, int(h * 0.12))
        fx2 = int(w * 0.82)
        fy2 = min(h - bottom_h - 8, int(h * 0.68))
        draw.rectangle((fx1, fy1, fx2, fy2), outline=(80, 220, 220, 220), width=2)

        px = int(max(0.0, min(1.0, focus[0])) * (w - 1))
        py = int(max(0.0, min(1.0, focus[1])) * (h - 1))
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), outline=(220, 70, 70, 230), width=2)
        draw.line((px - 10, py, px + 10, py), fill=(220, 70, 70, 230), width=2)
        draw.line((px, py - 10, px, py + 10), fill=(220, 70, 70, 230), width=2)

        if mode == "split":
            gutter_color = (120, 220, 255, 230)
            x = w - 3 if side == "current" else 2
            draw.line((x, 0, x, h), fill=gutter_color, width=3)

        caption_lines = self._wrap_caption(caption_text[:90], line_len=max(16, int(w / 12)))
        if caption_lines:
            self._draw_caption_mock(draw, (caption_box[0] + 6, caption_box[1] + 6, caption_box[2] - 6, caption_box[3] - 6), caption_lines, caption_style, caption_position, caption_emphasis)

        return Image.alpha_composite(output, overlay).convert("RGB")

    def _resolve_caption_box(self, w: int, h: int, top_h: int, bottom_h: int, caption_position: str) -> Tuple[int, int, int, int]:
        mx = max(6, int(w * 0.08))
        x1 = max(2, min(mx, w - 4))
        x2 = max(x1 + 2, w - x1)
        if caption_position == "Mid Screen":
            top = max(top_h + 10, int(h * 0.42))
            bottom = min(h - bottom_h - 10, int(h * 0.60))
        elif caption_position == "Stacked Emphasis":
            top = max(top_h + 10, int(h * 0.54))
            bottom = min(h - bottom_h - 8, int(h * 0.86))
        elif caption_position == "Top Center":
            top = max(top_h + 6, int(h * 0.06))
            bottom = min(int(h * 0.22), h - bottom_h - 10)
        elif caption_position == "Bottom Left":
            top = max(top_h + 8, int(h * 0.74))
            bottom = min(h - bottom_h - 6, int(h * 0.94))
            x1 = max(2, int(w * 0.04))
            x2 = min(int(w * 0.60), w - 2)
        else:  # Bottom Center (default) and Custom XY fallback
            top = max(top_h + 8, int(h * 0.74))
            bottom = min(h - bottom_h - 6, int(h * 0.94))
        if bottom <= top:
            top = max(top_h + 8, int(h * 0.55))
            bottom = min(h - bottom_h - 8, int(h * 0.82))
        top = max(2, min(top, h - 4))
        bottom = max(top + 2, min(bottom, h - 2))
        if bottom <= top:
            top = max(2, min(h - 12, top_h + 4))
            bottom = min(h - 2, top + max(8, min(24, h // 6)))
        return (x1, top, x2, bottom)

    def _draw_caption_mock(self, draw, box: Tuple[int, int, int, int], lines: List[str], caption_style: str, caption_position: str, caption_emphasis: str = "Standard") -> None:
        style = CAPTION_STYLE_PRESETS.get(caption_style, CAPTION_STYLE_PRESETS["ED Clean Lower Third"])
        emphasis = CAPTION_EMPHASIS_PRESETS.get(caption_emphasis, CAPTION_EMPHASIS_PRESETS["Standard"])
        x1, y1, x2, y2 = box
        if x2 <= x1 or y2 <= y1:
            return
        force_upper = style.get("uppercase") or emphasis.get("force_upper")
        rendered_lines = [line.upper() if force_upper else line for line in lines]
        font_size = int(emphasis.get("font_size", 18))
        line_height = int(emphasis.get("line_height", 22))
        padding_y = int(emphasis.get("padding_y", 8))
        padding_x = int(emphasis.get("padding_x", 10))
        font = get_preview_font(font_size, bold=caption_emphasis in {"Punchy", "Trailer"} or style.get("outline"))
        block_height = max(2, min(y2 - y1, line_height * len(rendered_lines) + padding_y * 2))
        if style.get("centered"):
            box_y1 = y1 + max(0, (y2 - y1 - block_height) // 2)
        else:
            box_y1 = y1
        box_y2 = max(box_y1 + 2, box_y1 + block_height)
        box_y2 = min(y2, box_y2)
        if box_y2 <= box_y1:
            return
        box_fill = list(style.get("box_fill", (0, 0, 0, 100)))
        if len(box_fill) == 4:
            box_fill[3] = max(0, min(255, int(box_fill[3] * emphasis.get("box_alpha_boost", 1.0))))
        if box_fill[-1] > 0:
            draw.rectangle((x1, box_y1, x2, box_y2), fill=tuple(box_fill))
        accent = style.get("custom_accent") or style.get("accent", (179, 45, 46, 255))
        draw.line((x1, box_y1, x2, box_y1), fill=accent, width=int(emphasis.get("accent_width", 3)))
        text_fill = style.get("text_fill", (255, 255, 255, 255))
        text_y = box_y1 + padding_y
        for line in rendered_lines:
            if style.get("centered"):
                approx_width = max(24, len(line) * max(7, font_size // 2))
                tx = max(x1 + padding_x, x1 + ((x2 - x1) - approx_width) // 2)
            else:
                tx = x1 + padding_x
            if style.get("outline") or emphasis.get("outline"):
                for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)]:
                    draw.text((tx + ox, text_y + oy), line, fill=(0, 0, 0, 255), font=font)
            draw.text((tx, text_y), line, fill=text_fill, font=font)
            text_y += line_height

    def _draw_badge(self, draw, pos: Tuple[int, int], text: str, accent: Tuple[int, int, int, int]) -> None:
        x, y = pos
        width = max(94, len(text) * 7 + 14)
        draw.rectangle((x, y, x + width, y + 24), fill=(20, 20, 20), outline=accent, width=1)
        draw.text((x + 6, y + 6), text, fill=(255, 255, 255, 255), font=(ImageFont.load_default() if ImageFont else None))

    def _set_image_from_path(self, label, preview_path: str, cache_key: str, max_size: Tuple[int, int]) -> None:
        if preview_path and Image and ImageTk and Path(preview_path).exists():
            try:
                with Image.open(preview_path) as img:
                    img.thumbnail(max_size)
                    photo = ImageTk.PhotoImage(img)
                    self.photo_cache[cache_key] = photo
                    label.configure(image=photo, text="")
                    return
            except Exception:
                label.configure(image="", text="Preview error", fg="#cccccc")
                return
        label.configure(image="", text="No preview", fg="#cccccc")


class DraftOutputPreviewPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.photo_cache: Dict[str, Any] = {}
        self.frames: List[Any] = []
        self.frame_index = 0
        self.playing = False
        self.play_job = None

        self.max_thumb_size = 900  # large default so text overlays are readable
        self.preview_label = tk.Label(self, bg="#101010",
                                      width=420, height=320,  # minimum visible size
                                      anchor="center")
        self.preview_label.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        transport = ttk.Frame(self)
        transport.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        transport.columnconfigure(4, weight=1)
        self.prev_btn = ttk.Button(transport, text="◀ Prev", command=self._prev)
        self.prev_btn.grid(row=0, column=0, padx=(0, 6))
        self.play_btn = ttk.Button(transport, text="Play", command=self._toggle)
        self.play_btn.grid(row=0, column=1, padx=(0, 6))
        self.next_btn = ttk.Button(transport, text="Next ▶", command=self._next)
        self.next_btn.grid(row=0, column=2, padx=(0, 10))
        self.slider_var = tk.DoubleVar(value=1.0)
        self.slider = ttk.Scale(transport, from_=1, to=2, orient="horizontal", variable=self.slider_var, command=self._scrub)
        self.slider.grid(row=0, column=3, columnspan=2, sticky="ew")
        self.status_var = tk.StringVar(value="Select a draft to see the animated output mock.")
        ttk.Label(transport, textvariable=self.status_var, foreground="#666666").grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))

    def set_display_size(self, max_size: int) -> None:
        self.max_thumb_size = max(600, int(max_size))

    def render(self, draft: Optional[DraftOption], asset_map: Dict[str, Asset], project: ProjectState) -> None:
        self._stop()
        self.photo_cache.clear()
        if not draft or not Image or not ImageTk:
            self.preview_label.configure(image="", text="No preview\n\nAdd media and generate a draft.", fg="#888888")
            self._set_transport(False, "Select a draft to see the preview.")
            return

        canvas_family = project.preview_canvas_family
        platform_variant = project.preview_platform_variant
        caption_style = project.preview_caption_style
        caption_position = project.preview_caption_position
        caption_emphasis = project.preview_caption_emphasis
        target_w, target_h = CANVAS_FAMILIES.get(canvas_family, CANVAS_FAMILIES["9x16"])

        # ── Fixed display size (portrait or landscape) ─────────────────────
        is_portrait = target_h >= target_w
        if is_portrait:
            disp_h = min(self.max_thumb_size, 680)
            disp_w = max(1, int(disp_h * target_w / target_h))
        else:
            disp_w = min(self.max_thumb_size, 800)
            disp_h = max(1, int(disp_w * target_h / target_w))

        # role→caption text from live project (already written back in refresh)
        _role_text = {
            "hook":    project.hook_text or project.title_text or "Hook",
            "proof":   project.title_text or project.hook_text or "Proof",
            "cta":     project.cta_text or "Start Your Project",
            "support": project.title_text or project.hook_text or "",
        }
        selected_card_map = {c.asset_id: c for c in (project.selected_storyboard or [])}

        # Font size that looks right at the display resolution
        # ~5% of display height is a good rule of thumb
        base_font_px = max(14, int(disp_h * 0.045))

        frames = []
        for idx, card in enumerate(draft.storyboard_cards[:8]):
            asset = asset_map.get(card.asset_id)

            # ── 1. Get source image ────────────────────────────────────
            src_img = None
            if asset:
                pp = asset.analysis.preview_path or (
                    asset.path if asset.media_type == "image" else "")
                if pp and Path(pp).exists():
                    try:
                        with Image.open(pp) as raw:
                            src_img = ImageOps.exif_transpose(raw).convert("RGB")
                    except Exception:
                        pass

            # ── 2. Crop to aspect ratio then resize to display size ────
            if src_img:
                cropped = self._crop_to_aspect(
                    src_img, target_w, target_h,
                    card.crop_focus_x, card.crop_focus_y)
                try:
                    frame = cropped.resize((disp_w, disp_h), Image.LANCZOS)
                except Exception:
                    frame = cropped.resize((disp_w, disp_h))
            else:
                frame = Image.new("RGB", (disp_w, disp_h), (18, 18, 18))
                if ImageDraw:
                    d = ImageDraw.Draw(frame)
                    d.rectangle((0, 0, disp_w-1, disp_h-1), outline=(80, 80, 80), width=2)
                    lbl = asset.title if asset else f"Clip {idx+1}"
                    d.text((12, 12), lbl, fill=(180, 180, 180),
                           font=get_preview_font(base_font_px, bold=True))

            # ── 3. Draw caption overlay at display resolution ──────────
            live_card = selected_card_map.get(card.asset_id)
            cap_events = live_card.caption_events if (live_card and live_card.caption_events) else None
            fallback_text = _role_text.get(card.role, "") or project.hook_text or ""

            frame = self._draw_caption_on_display(
                frame, disp_w, disp_h,
                caption_style, caption_position, caption_emphasis,
                fallback_text, cap_events, base_font_px,
                platform_variant, canvas_family,
            )

            photo = ImageTk.PhotoImage(frame)
            self.photo_cache[f"frame_{idx}"] = photo
            frames.append(photo)

        self.frames = frames
        if not frames:
            self.preview_label.configure(image="", text="No preview available", fg="#888888")
            self._set_transport(False, "Preview unavailable for this draft.")
            return
        self.frame_index = 0
        self.preview_label.configure(image=frames[0], text="")
        self._set_transport(True,
            f"Animated output mock • {canvas_family} • {platform_variant} • "
            f"{caption_style} / {caption_emphasis}")

    def _crop_to_aspect(self, img, target_w: int, target_h: int,
                         focus_x: float = 0.5, focus_y: float = 0.5):
        """Crop source image to target aspect ratio, centred on focus point."""
        src_w, src_h = img.size
        tgt_ratio = target_w / float(target_h)
        src_ratio = src_w / float(src_h)
        fx = max(0.0, min(1.0, focus_x))
        fy = max(0.0, min(1.0, focus_y))
        if src_ratio > tgt_ratio:
            crop_h = src_h
            crop_w = int(round(crop_h * tgt_ratio))
            overflow = max(0, src_w - crop_w)
            left = max(0, min(int(round(overflow * fx)), overflow))
            box = (left, 0, left + crop_w, src_h)
        else:
            crop_w = src_w
            crop_h = int(round(crop_w / tgt_ratio))
            overflow = max(0, src_h - crop_h)
            top = max(0, min(int(round(overflow * fy)), overflow))
            box = (0, top, src_w, top + crop_h)
        return img.crop(box)

    def _draw_caption_on_display(self, frame, disp_w: int, disp_h: int,
                                  caption_style: str, caption_position: str,
                                  caption_emphasis: str, caption_text: str,
                                  caption_events, base_font_px: int,
                                  platform_variant: str, canvas_family: str):
        """
        Draw caption overlay directly on the display-sized image.
        All measurements are in display pixels, so font sizes are exactly
        what the user sees — no scaling surprises.
        """
        if not ImageDraw or not caption_text:
            return frame
        try:
            style = dict(CAPTION_STYLE_PRESETS.get(
                caption_style, CAPTION_STYLE_PRESETS["ED Clean Lower Third"]))
            emphasis = CAPTION_EMPHASIS_PRESETS.get(
                caption_emphasis, CAPTION_EMPHASIS_PRESETS["Standard"])

            # Use the selected caption events text if present
            texts = []
            if caption_events:
                texts = [(evt.text, evt.position or caption_position) for evt in caption_events]
            else:
                texts = [(caption_text, caption_position)]

            output = frame.copy().convert("RGBA")
            overlay = Image.new("RGBA", output.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Safe zone bands
            margin = resolve_ui_safe_margins(canvas_family, platform_variant)
            top_band = int(disp_h * margin.get("top", 0.12))
            bot_band = int(disp_h * margin.get("bottom", 0.20))
            if top_band > 0:
                draw.rectangle((0, 0, disp_w, top_band), fill=(190, 60, 200, 40))
            if bot_band > 0:
                draw.rectangle((0, disp_h - bot_band, disp_w, disp_h), fill=(190, 60, 200, 40))

            font = get_preview_font(base_font_px, bold=caption_emphasis in {"Punchy", "Trailer"})
            line_h = int(base_font_px * 1.4)
            pad_x = int(disp_w * 0.04)
            pad_y = int(base_font_px * 0.5)

            for text, position in texts:
                if not text:
                    continue

                # Word-wrap
                max_chars = max(8, int(disp_w / (base_font_px * 0.55)))
                words = text.split()
                lines, cur = [], ""
                for word in words:
                    test = (cur + " " + word).strip()
                    if len(test) <= max_chars or not cur:
                        cur = test
                    else:
                        lines.append(cur)
                        cur = word
                if cur:
                    lines.append(cur)

                block_h = line_h * len(lines) + pad_y * 2
                margin_x = int(disp_w * 0.06)
                bx1, bx2 = margin_x, disp_w - margin_x

                # Y position
                if position == "Top Center":
                    by1 = top_band + 6
                elif position == "Mid Screen":
                    by1 = (disp_h - block_h) // 2
                else:  # Bottom Center / Bottom Left / default
                    by1 = disp_h - bot_band - block_h - 6
                by1 = max(top_band + 2, min(by1, disp_h - block_h - 2))
                by2 = by1 + block_h

                if "Bottom Left" in position:
                    bx2 = int(disp_w * 0.65)

                # Background box
                box_fill = list(style.get("box_fill", (0, 0, 0, 180)))
                box_fill[3] = min(220, int(box_fill[3] * 1.3))
                draw.rectangle((bx1, by1, bx2, by2), fill=tuple(box_fill))

                # Accent line
                accent = style.get("custom_accent") or style.get("accent", (179, 45, 46, 255))
                draw.rectangle((bx1, by1, bx2, by1 + max(3, base_font_px // 6)),
                                fill=accent)

                # Text
                force_upper = style.get("uppercase") or emphasis.get("force_upper")
                text_fill = style.get("text_fill", (255, 255, 255, 255))
                ty = by1 + pad_y
                for line in lines:
                    rendered_line = line.upper() if force_upper else line
                    tx = bx1 + pad_x
                    if style.get("centered"):
                        try:
                            bbox = draw.textbbox((0, 0), rendered_line, font=font)
                            tw = bbox[2] - bbox[0]
                            tx = max(bx1 + pad_x, bx1 + ((bx2 - bx1) - tw) // 2)
                        except Exception:
                            pass
                    if style.get("outline"):
                        for ox, oy in [(-1,0),(1,0),(0,-1),(0,1)]:
                            draw.text((tx+ox, ty+oy), rendered_line,
                                      fill=(0,0,0,255), font=font)
                    draw.text((tx, ty), rendered_line, fill=text_fill, font=font)
                    ty += line_h

            return Image.alpha_composite(output, overlay).convert("RGB")
        except Exception:
            return frame

    def _frame_for_card(self, asset: Optional[Asset], card: StoryboardCard, target_w: int, target_h: int, project: ProjectState, idx: int):
        if not Image:
            return None
        if asset:
            preview_path = asset.analysis.preview_path or (asset.path if asset.media_type == "image" else "")
            if preview_path and Path(preview_path).exists():
                try:
                    with Image.open(preview_path) as img:
                        img = ImageOps.exif_transpose(img).convert("RGB")
                        return self._crop_to_dimensions(img, target_w, target_h, (card.crop_focus_x, card.crop_focus_y))
                except Exception:
                    pass
        bg = Image.new("RGB", (target_w, target_h), (18, 18, 18))
        if ImageDraw:
            draw = ImageDraw.Draw(bg)
            draw.rectangle((0, 0, target_w - 1, target_h - 1), outline=(90, 90, 90), width=2)
            title = asset.title if asset else f"Storyboard {idx + 1}"
            font = get_preview_font(22, bold=True)
            draw.text((24, 24), title, fill=(255, 255, 255), font=font)
            draw.text((24, 60), f"Role: {card.role}", fill=(200, 200, 200), font=get_preview_font(18))
        return bg

    def _crop_to_dimensions(self, img, target_w: int, target_h: int, focus: Tuple[float, float]):
        src_w, src_h = img.size
        src_ratio = src_w / float(src_h)
        tgt_ratio = target_w / float(target_h)
        fx = max(0.0, min(1.0, focus[0]))
        fy = max(0.0, min(1.0, focus[1]))
        if src_ratio > tgt_ratio:
            crop_h = src_h
            crop_w = int(round(crop_h * tgt_ratio))
            overflow = max(0, src_w - crop_w)
            left = int(round(overflow * fx))
            left = max(0, min(left, overflow))
            box = (left, 0, left + crop_w, src_h)
        else:
            crop_w = src_w
            crop_h = int(round(crop_w / tgt_ratio))
            overflow = max(0, src_h - crop_h)
            top = int(round(overflow * fy))
            top = max(0, min(top, overflow))
            box = (0, top, src_w, top + crop_h)
        cropped = img.crop(box)
        # ── Always resize to the render target so caption text is legible ──
        # Cap at 4× the display thumb size to avoid massive memory use
        render_w = min(target_w, self.max_thumb_size * 2)
        render_h = min(target_h, self.max_thumb_size * 2)
        try:
            return cropped.resize((render_w, render_h), Image.LANCZOS)
        except Exception:
            return cropped.resize((render_w, render_h))

    def _caption_text_for_role(self, project: ProjectState, role: str) -> str:
        if role == "hook":
            return project.hook_text or "Hook preview"
        if role == "cta":
            return project.cta_text or "Start Your Project"
        if role == "proof":
            return project.title_text or "Proof / result"
        return project.title_text or project.hook_text or "Enormous Door"

    def _wrap_caption(self, text: str, line_len: int = 24) -> List[str]:
        text = (text or "").strip()
        if not text:
            return []
        words = text.split()
        lines, current = [], ""
        for word in words:
            candidate = (current + " " + word).strip()
            if len(candidate) <= line_len or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:3]

    def _resolve_caption_box(self, w: int, h: int, top_h: int, bottom_h: int,
                              caption_position: str,
                              custom_x: float = -1.0,
                              custom_y: float = -1.0) -> Tuple[int, int, int, int]:
        mx = max(6, int(w * 0.08))
        x1 = max(2, min(mx, w - 4))
        x2 = max(x1 + 2, w - x1)

        # Custom XY overrides preset entirely
        if caption_position == "Custom XY" and 0.0 <= custom_x <= 1.0 and 0.0 <= custom_y <= 1.0:
            box_h = max(24, int(h * 0.12))
            top = int(custom_y * h)
            bottom = min(h - 2, top + box_h)
            x_offset = int(custom_x * w)
            x1 = max(2, x_offset - int(w * 0.4))
            x2 = min(w - 2, x_offset + int(w * 0.4))
        elif caption_position == "Mid Screen":
            top = max(top_h + 10, int(h * 0.42))
            bottom = min(h - bottom_h - 10, int(h * 0.60))
        elif caption_position == "Stacked Emphasis":
            top = max(top_h + 10, int(h * 0.54))
            bottom = min(h - bottom_h - 8, int(h * 0.86))
        elif caption_position == "Top Center":
            top = max(top_h + 6, int(h * 0.06))
            bottom = min(int(h * 0.22), h - bottom_h - 10)
        elif caption_position == "Bottom Left":
            top = max(top_h + 8, int(h * 0.74))
            bottom = min(h - bottom_h - 6, int(h * 0.94))
            x1 = max(2, int(w * 0.04))
            x2 = min(int(w * 0.60), w - 2)
        else:  # Bottom Center (default)
            top = max(top_h + 8, int(h * 0.74))
            bottom = min(h - bottom_h - 6, int(h * 0.94))

        if bottom <= top:
            top = max(top_h + 8, int(h * 0.55))
            bottom = min(h - bottom_h - 8, int(h * 0.82))
        top = max(2, min(top, h - 4))
        bottom = max(top + 2, min(bottom, h - 2))
        if bottom <= top:
            top = max(2, min(h - 12, top_h + 4))
            bottom = min(h - 2, top + max(8, min(24, h // 6)))
        return (x1, top, x2, bottom)

    def _draw_caption_mock(self, draw, box: Tuple[int, int, int, int], lines: List[str],
                            caption_style: str, caption_position: str,
                            caption_emphasis: str = "Standard",
                            font_family: str = "Default") -> None:
        style = dict(CAPTION_STYLE_PRESETS.get(caption_style,
                                                CAPTION_STYLE_PRESETS["ED Clean Lower Third"]))
        emphasis = CAPTION_EMPHASIS_PRESETS.get(caption_emphasis,
                                                 CAPTION_EMPHASIS_PRESETS["Standard"])
        x1, y1, x2, y2 = box
        if x2 <= x1 or y2 <= y1:
            return
        force_upper = style.get("uppercase") or emphasis.get("force_upper")
        rendered = [line.upper() if force_upper else line for line in lines]

        # Scale font size proportionally to the image height so text is legible
        # at any canvas resolution. The preset sizes are tuned for a 1080×1920 canvas.
        # Derive a scale factor from the actual box height vs expected ~20% of canvas.
        img_h = y2 - y1   # approximate canvas height from box extents
        if img_h > 0:
            # box is ~20% of canvas height in the presets → back-calculate canvas h
            approx_canvas_h = img_h / 0.20
            scale = max(0.5, min(3.0, approx_canvas_h / 1920.0))
        else:
            scale = 1.0
        base_size = int(emphasis.get("font_size", 18))
        scaled_size = max(10, int(base_size * scale))
        line_h_base = int(emphasis.get("line_height", 22))
        line_height = max(12, int(line_h_base * scale))
        padding_y = max(4, int(emphasis.get("padding_y", 8) * scale))
        padding_x = max(4, int(emphasis.get("padding_x", 10) * scale))
        accent_w = max(2, int(emphasis.get("accent_width", 3) * scale))

        font = get_preview_font(scaled_size,
                                bold=caption_emphasis in {"Punchy", "Trailer"} or style.get("outline"))
        block_height = max(2, min(y2 - y1, line_height * len(rendered) + padding_y * 2))
        box_y1 = y1 if not style.get("centered") else y1 + max(0, (y2 - y1 - block_height) // 2)
        box_y2 = max(box_y1 + 2, box_y1 + block_height)
        box_y2 = min(y2, box_y2)
        if box_y2 <= box_y1:
            return
        box_fill = list(style.get("box_fill", (0, 0, 0, 140)))
        if len(box_fill) == 4:
            box_fill[3] = max(0, min(255, int(box_fill[3] * emphasis.get("box_alpha_boost", 1.0))))
        if box_fill[-1] > 0:
            draw.rectangle((x1, box_y1, x2, box_y2), fill=tuple(box_fill))
        accent = style.get("custom_accent") or style.get("accent", (179, 45, 46, 255))
        draw.line((x1, box_y1, x2, box_y1), fill=accent, width=accent_w)
        text_fill = style.get("text_fill", (255, 255, 255, 255))
        text_y = box_y1 + padding_y
        for line in rendered:
            if style.get("centered"):
                approx_width = max(24, len(line) * max(7, scaled_size // 2))
                tx = max(x1 + padding_x, x1 + ((x2 - x1) - approx_width) // 2)
            else:
                tx = x1 + padding_x
            if style.get("outline") or emphasis.get("outline"):
                for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)]:
                    draw.text((tx + ox, text_y + oy), line, fill=(0, 0, 0, 255), font=font)
            draw.text((tx, text_y), line, fill=text_fill, font=font)
            text_y += line_height

    def _apply_overlays(self, img, focus: Tuple[float, float], canvas_family: str,
                         project: ProjectState, role: str,
                         caption_style: str, caption_position: str,
                         caption_emphasis: str, platform_variant: str,
                         caption_events: Optional[List] = None,
                         card_font_family: str = "Default",
                         card_pos_x: float = -1.0,
                         card_pos_y: float = -1.0,
                         fallback_caption_text: str = ""):
        if not ImageDraw:
            return img
        output = img.copy().convert("RGBA")
        overlay = Image.new("RGBA", output.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        w, h = output.size
        margin = resolve_ui_safe_margins(canvas_family, platform_variant)
        top_h = int(h * margin["top"])
        bottom_h = int(h * margin["bottom"])

        # Safe zone overlays (purple tint = restricted UI area)
        draw.rectangle((0, 0, w, top_h), fill=(190, 60, 200, 52))
        draw.rectangle((0, h - bottom_h, w, h), fill=(190, 60, 200, 52))
        draw.line((0, top_h, w, top_h), fill=(210, 90, 220, 180), width=2)
        draw.line((0, h - bottom_h, w, h - bottom_h), fill=(210, 90, 220, 180), width=2)

        # Safe zone label
        safe_desc = PLATFORM_SAFE_ZONE_DESCRIPTIONS.get(platform_variant, "")
        if safe_desc and top_h > 8:
            try:
                lbl_font = get_preview_font(9, bold=False)
                draw.text((6, 4), f"⚠ {platform_variant}: {safe_desc[:50]}", fill=(220, 180, 255, 200), font=lbl_font)
            except Exception:
                pass

        # Frame border
        draw.rectangle((1, 1, w - 2, h - 2), outline=(255, 255, 255, 210), width=2)

        # Subject focus crosshair
        fx1 = int(w * 0.18); fy1 = max(top_h + 4, int(h * 0.12))
        fx2 = int(w * 0.82); fy2 = min(h - bottom_h - 8, int(h * 0.68))
        draw.rectangle((fx1, fy1, fx2, fy2), outline=(80, 220, 220, 220), width=2)
        px = int(max(0.0, min(1.0, focus[0])) * (w - 1))
        py = int(max(0.0, min(1.0, focus[1])) * (h - 1))
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), outline=(220, 70, 70, 230), width=2)
        draw.line((px - 10, py, px + 10, py), fill=(220, 70, 70, 230), width=2)
        draw.line((px, py - 10, px, py + 10), fill=(220, 70, 70, 230), width=2)

        # Render timed caption events if present
        if caption_events:
            for evt in caption_events:
                evt_pos = evt.position if evt.position else caption_position
                evt_style = evt.style if evt.style else caption_style
                evt_emphasis = evt.emphasis if evt.emphasis else caption_emphasis
                cx = evt.font_family if hasattr(evt, "font_family") else card_font_family
                caption_box = self._resolve_caption_box(w, h, top_h, bottom_h, evt_pos,
                                                         card_pos_x, card_pos_y)
                draw.rectangle(caption_box, outline=(240, 210, 60, 220), width=2)
                # Draw timing label above the caption box
                start_str = f"{evt.start_sec:.1f}s"
                end_str = "end" if evt.end_sec == 0 else f"{evt.end_sec:.1f}s"
                try:
                    t_font = get_preview_font(9, bold=True)
                    draw.text((caption_box[0] + 4, caption_box[1] - 14),
                              f"TEXT @ {start_str}→{end_str}",
                              fill=(240, 210, 60, 220), font=t_font)
                except Exception:
                    pass
                lines = self._wrap_caption(evt.text[:90], line_len=max(16, int(w / 12)))
                if lines:
                    self._draw_caption_mock(draw,
                        (caption_box[0] + 6, caption_box[1] + 6,
                         caption_box[2] - 6, caption_box[3] - 6),
                        lines, evt_style, evt_pos, evt_emphasis, cx)
        else:
            # No timed events — render the explicit fallback caption text
            caption_box = self._resolve_caption_box(w, h, top_h, bottom_h, caption_position,
                                                     card_pos_x, card_pos_y)
            draw.rectangle(caption_box, outline=(240, 210, 60, 220), width=2)
            # Use the explicitly passed fallback text (always non-empty from render())
            # Fall back to _caption_text_for_role only when called from outside render()
            text_to_show = (fallback_caption_text.strip()
                            or self._caption_text_for_role(project, role))
            lines = self._wrap_caption(text_to_show[:90], line_len=max(16, int(w / 12)))
            if lines:
                self._draw_caption_mock(draw,
                    (caption_box[0] + 6, caption_box[1] + 6,
                     caption_box[2] - 6, caption_box[3] - 6),
                    lines, caption_style, caption_position, caption_emphasis, card_font_family)
        return Image.alpha_composite(output, overlay).convert("RGB")

    def _set_transport(self, enabled: bool, status: str) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (self.prev_btn, self.play_btn, self.next_btn, self.slider):
            try:
                widget.configure(state=state)
            except Exception:
                pass
        if enabled:
            self.slider.configure(from_=1, to=max(1, len(self.frames)))
            self.slider_var.set(max(1, self.frame_index + 1))
        else:
            self.slider.configure(from_=1, to=2)
            self.slider_var.set(1)
            self.play_btn.configure(text="Play")
        self.status_var.set(status)

    def _show_frame(self, index: int) -> None:
        if not self.frames:
            return
        self.frame_index = max(0, min(index, len(self.frames) - 1))
        self.preview_label.configure(image=self.frames[self.frame_index], text="")
        self.slider_var.set(self.frame_index + 1)
        self.status_var.set(f"Animated output mock • frame {self.frame_index + 1} / {len(self.frames)}")

    def _advance(self) -> None:
        if not self.frames:
            self.play_job = None
            return
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self._show_frame(self.frame_index)
        if self.playing:
            self.play_job = self.after(850, self._advance)
        else:
            self.play_job = None

    def _toggle(self) -> None:
        if not self.frames:
            return
        self.playing = not self.playing
        self.play_btn.configure(text="Pause" if self.playing else "Play")
        if self.playing and self.play_job is None:
            self.play_job = self.after(850, self._advance)
        elif not self.playing and self.play_job is not None:
            try:
                self.after_cancel(self.play_job)
            except Exception:
                pass
            self.play_job = None

    def _prev(self) -> None:
        if not self.frames:
            return
        self._stop()
        self._show_frame((self.frame_index - 1) % len(self.frames))

    def _next(self) -> None:
        if not self.frames:
            return
        self._stop()
        self._show_frame((self.frame_index + 1) % len(self.frames))

    def _scrub(self, value: str) -> None:
        if not self.frames:
            return
        try:
            idx = int(round(float(value))) - 1
        except Exception:
            return
        self._stop()
        self._show_frame(idx)

    def _stop(self) -> None:
        self.playing = False
        self.play_btn.configure(text="Play")
        if self.play_job is not None:
            try:
                self.after_cancel(self.play_job)
            except Exception:
                pass
            self.play_job = None


class CopySuggestionPanel(ttk.Frame):
    def __init__(self, parent, apply_callback: Callable[[str, str], None]):
        super().__init__(parent)
        self.apply_callback = apply_callback
        self.columnconfigure(0, weight=1)
        self.scroll = ScrollFrame(self, orient="vertical", height=300)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)

    def render(self, draft: Optional[DraftOption], current_values: Dict[str, str]) -> None:
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        if not draft:
            ttk.Label(self.scroll.inner, text="Choose a draft to see copy suggestions.").grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return
        groups = [
            ("hook", "Hook suggestions", draft.hook_options),
            ("title", "Title suggestions", draft.title_options),
            ("cta", "CTA suggestions", draft.cta_options),
        ]
        for row, (field_name, heading, options) in enumerate(groups):
            section = ttk.LabelFrame(self.scroll.inner, text=heading, padding=8)
            section.grid(row=row, column=0, sticky="ew", padx=6, pady=6)
            for col, option in enumerate(options):
                bg = "#4d2b2b" if option == current_values.get(field_name, "") else "#262626"
                card = tk.Frame(section, bd=1, relief="solid", bg=bg)
                card.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)
                section.columnconfigure(col, weight=1)
                tk.Label(card, text=option, bg=bg, fg="white", wraplength=190, justify="left").pack(fill="x", padx=8, pady=(8, 8))
                ttk.Button(card, text="Apply", command=lambda f=field_name, v=option: self.apply_callback(f, v)).pack(anchor="w", padx=8, pady=(0, 8))


# -----------------------------------------------------------------------------
# Screens
# -----------------------------------------------------------------------------


class BaseScreen(tk.Frame):
    """Base class for all workflow screens. Uses tk.Frame so bg= is valid."""
    def __init__(self, parent, controller: AppController):
        super().__init__(parent, bg=ED["bg_root"], padx=10, pady=10)
        self.controller = controller

    def refresh(self) -> None:
        pass

    # ── Shared widget factories ───────────────────────────────────────
    def _ed_btn(self, parent, text: str, cmd, primary=False, small=False, **kw) -> tk.Button:
        bg  = ED["red"] if primary else ED["bg_card"]
        fg  = "#ffffff" if primary else ED["txt_primary"]
        abg = ED["red_hover"] if primary else ED["bg_hover"]
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg=fg, activebackground=abg, activeforeground=fg,
                         font=("Arial", 9 if small else 10, "bold" if primary else "normal"),
                         relief="flat", bd=0,
                         padx=(8 if small else 14), pady=(4 if small else 7),
                         cursor="hand2", **kw)

    def _card(self, parent, title: str, accent: str = None) -> tk.Frame:
        """Returns (outer_frame, inner_frame) — a titled dark card."""
        accent = accent or ED["red"]
        outer = tk.Frame(parent, bg=ED["bg_card"],
                         highlightbackground=ED["border"], highlightthickness=1)
        outer.columnconfigure(0, weight=1)
        bar = tk.Frame(outer, bg=accent, padx=10, pady=5)
        bar.grid(row=0, column=0, sticky="ew")
        tk.Label(bar, text=title.upper(), bg=accent, fg="#ffffff",
                 font=("Arial", 8, "bold")).pack(side="left")
        inner = tk.Frame(outer, bg=ED["bg_card"], padx=10, pady=10)
        inner.grid(row=1, column=0, sticky="nsew")
        inner.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        return outer, inner

    def _tk_text(self, parent, height=6, **kw) -> tk.Text:
        return tk.Text(parent, height=height, wrap="word",
                       bg=ED["bg_input"], fg=ED["txt_primary"],
                       insertbackground=ED["txt_primary"],
                       selectbackground=ED["selected"],
                       selectforeground=ED["txt_primary"],
                       relief="flat", bd=0, font=("Arial", 10),
                       highlightthickness=1,
                       highlightbackground=ED["border"],
                       highlightcolor=ED["red"], **kw)

    def _tk_listbox(self, parent, height=6, **kw) -> tk.Listbox:
        return tk.Listbox(parent, height=height,
                          bg=ED["bg_input"], fg=ED["txt_primary"],
                          selectbackground=ED["red"], selectforeground="#ffffff",
                          activestyle="none", relief="flat", bd=0,
                          font=("Arial", 10), highlightthickness=1,
                          highlightbackground=ED["border"],
                          highlightcolor=ED["red"], exportselection=False, **kw)


class ChooseOutcomeScreen(BaseScreen):
    """
    Step 1 — What do you want to build today?
    Redesigned as a two-panel layout:
      Left:  Goal cards (what you want) + Content Recipes (how to get there)
      Right: Viral Intelligence panel — hook templates, caption patterns, timing
    """
    def __init__(self, parent, controller: AppController):
        super().__init__(parent, controller)
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)

        # ── Hero header ───────────────────────────────────────────────
        hdr = tk.Frame(self, bg=ED["bg_root"], pady=12)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.columnconfigure(0, weight=1)
        tk.Label(hdr, text="What do you want to build today?",
                 bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 22, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(hdr,
                 text="Choose your goal — the wizard sets up everything else. "
                      "Pick a Content Recipe on the right for a proven viral structure.",
                 bg=ED["bg_root"], fg=ED["txt_secondary"],
                 font=("Arial", 10), wraplength=1050, justify="left").grid(
                     row=1, column=0, sticky="w", pady=(4, 0))
        self.keep_media_hint_var = tk.StringVar(value="")
        tk.Label(hdr, textvariable=self.keep_media_hint_var,
                 bg=ED["bg_root"], fg=ED["gold"],
                 font=("Arial", 9, "italic"), wraplength=1050).grid(
                     row=2, column=0, sticky="w", pady=(4, 0))
        tk.Frame(self, bg=ED["border_hi"], height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        # ══════════════════════════════════════════════════════════════
        # LEFT — Goal cards
        # ══════════════════════════════════════════════════════════════
        left = tk.Frame(self, bg=ED["bg_root"])
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.columnconfigure(1, weight=1)
        left.columnconfigure(2, weight=1)

        tk.Label(left, text="CHOOSE YOUR DIRECTION",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold")).grid(
                     row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.goal_cards: List[tk.Frame] = []
        for idx, item in enumerate(GOAL_CARDS):
            row, col = divmod(idx, 3)
            grid_row = row * 2 + 1    # leave gap rows for spacing

            border_outer = tk.Frame(left, bg=ED["border"], padx=1, pady=1)
            border_outer.grid(row=grid_row, column=col, sticky="nsew",
                              padx=5, pady=5)
            border_outer.columnconfigure(0, weight=1)

            card = tk.Frame(border_outer, bg=ED["bg_card"], padx=14, pady=12)
            card.grid(row=0, column=0, sticky="nsew")
            card.columnconfigure(0, weight=1)

            # Chip
            chip_bg = ED["red"] if item.get("hook_angle") == "proof" else \
                      ED["gold"] if item.get("hook_angle") == "curiosity" else \
                      ED["blue"] if item.get("hook_angle") == "educational" else ED["red"]
            chip = tk.Frame(card, bg=chip_bg)
            chip.grid(row=0, column=0, sticky="w", pady=(0, 8))
            tk.Label(chip, text=item["label"].upper(),
                     bg=chip_bg, fg="#ffffff",
                     font=("Arial", 8, "bold"), padx=8, pady=3).pack()

            tk.Label(card, text=item["description"],
                     bg=ED["bg_card"], fg=ED["txt_secondary"],
                     font=("Arial", 9), wraplength=220, justify="left").grid(
                         row=1, column=0, sticky="w")

            tk.Label(card, text=f"→ {item['template_family']}",
                     bg=ED["bg_card"], fg=ED["txt_dim"],
                     font=("Arial", 8)).grid(row=2, column=0, sticky="w", pady=(6, 10))

            btn = tk.Button(card, text="Choose This Direction →",
                            command=lambda label=item["label"]: self.controller.set_goal_by_label(label),
                            bg=ED["red"], fg="#ffffff",
                            activebackground=ED["red_hover"], activeforeground="#ffffff",
                            font=("Arial", 9, "bold"), relief="flat", bd=0,
                            padx=10, pady=6, cursor="hand2")
            btn.grid(row=3, column=0, sticky="w")
            self.goal_cards.append(card)

        # Quick action strip
        strip = tk.Frame(left, bg=ED["bg_root"])
        strip.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        tk.Label(strip,
                 text="Not sure? Choose 'Not Sure — Pick For Me' and the app will infer "
                      "the strongest direction from your files.  You can always change later.",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 8, "italic"), wraplength=700, justify="left").pack(side="left")

        act = tk.Frame(left, bg=ED["bg_root"])
        act.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._ed_btn(act, "+ Add Reference Examples",
                     self.controller.import_reference_files, small=True).pack(side="left", padx=(0, 8))
        self._ed_btn(act, "+ Import Caption File",
                     self.controller.import_caption_file, small=True).pack(side="left")

        self.summary_var = tk.StringVar(value="")
        self.summary_lbl = tk.Label(left, textvariable=self.summary_var,
                                    bg=ED["bg_root"], fg=ED["txt_dim"],
                                    font=("Arial", 8), wraplength=700)
        self.summary_lbl.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # ══════════════════════════════════════════════════════════════
        # RIGHT — Viral Intelligence panel
        # ══════════════════════════════════════════════════════════════
        right = tk.Frame(self, bg=ED["bg_root"])
        right.grid(row=2, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        # ── Content Recipes ───────────────────────────────────────────
        rec_outer, rec_inner = self._card(right, "Content Recipes — Proven Viral Structures", ED["red"])
        rec_outer.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self._recipe_buttons: List[tk.Button] = []
        for i, recipe in enumerate(CONTENT_RECIPES):
            row_f = tk.Frame(rec_inner, bg=ED["bg_card"])
            row_f.pack(fill="x", pady=(0, 6))
            row_f.columnconfigure(1, weight=1)

            icon_lbl = tk.Label(row_f, text=recipe["icon"],
                                bg=ED["bg_card"], fg=ED["txt_primary"],
                                font=("Arial", 14), width=3)
            icon_lbl.grid(row=0, column=0, sticky="w")

            meta = tk.Frame(row_f, bg=ED["bg_card"])
            meta.grid(row=0, column=1, sticky="ew")
            tk.Label(meta, text=recipe["label"],
                     bg=ED["bg_card"], fg=ED["txt_primary"],
                     font=("Arial", 10, "bold"), anchor="w").pack(anchor="w")
            tk.Label(meta, text=recipe["ideal_for"],
                     bg=ED["bg_card"], fg=ED["txt_dim"],
                     font=("Arial", 8)).pack(anchor="w")

            mult = recipe["estimated_views_multiplier"]
            mult_color = ED["green"] if mult >= 1.8 else ED["gold"] if mult >= 1.4 else ED["txt_secondary"]
            tk.Label(row_f, text=f"×{mult:.1f}",
                     bg=ED["bg_card"], fg=mult_color,
                     font=("Arial", 10, "bold")).grid(row=0, column=2, padx=(8, 0))

            use_btn = tk.Button(row_f, text="Use",
                                command=lambda r=recipe: self._apply_recipe(r),
                                bg=ED["bg_panel"], fg=ED["txt_secondary"],
                                activebackground=ED["red"], activeforeground="#ffffff",
                                font=("Arial", 8), relief="flat", bd=0,
                                padx=8, pady=3, cursor="hand2")
            use_btn.grid(row=0, column=3, padx=(6, 0))
            self._recipe_buttons.append(use_btn)

        # ── Hook Intelligence ─────────────────────────────────────────
        hook_outer, hook_inner = self._card(right, "Hook Intelligence — Stop the Scroll", ED["gold"])
        hook_outer.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        self._selected_hook_var = tk.StringVar(value="")
        self._hook_template_var = tk.StringVar(value="Select a hook pattern below to see the template.")

        tk.Label(hook_inner, textvariable=self._hook_template_var,
                 bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 10, "italic"), wraplength=380, justify="left").pack(
                     fill="x", pady=(0, 8))

        # Hook angle filter
        filter_row = tk.Frame(hook_inner, bg=ED["bg_card"])
        filter_row.pack(fill="x", pady=(0, 8))
        self._hook_filter = tk.StringVar(value="all")
        for angle, label in [("all", "All"), ("proof", "Proof"), ("curiosity", "Curiosity"),
                              ("direct", "Direct"), ("pattern_interrupt", "Pattern Interrupt")]:
            tk.Radiobutton(filter_row, text=label,
                           variable=self._hook_filter, value=angle,
                           command=self._refresh_hook_list,
                           bg=ED["bg_card"], fg=ED["txt_secondary"],
                           selectcolor=ED["red"], activebackground=ED["bg_card"],
                           font=("Arial", 8)).pack(side="left", padx=(0, 8))

        self._hook_listbox = self._tk_listbox(hook_inner, height=7)
        self._hook_listbox.pack(fill="x")
        self._hook_listbox.bind("<<ListboxSelect>>", self._on_hook_selected)
        self._refresh_hook_list()

        hook_why_var = tk.StringVar(value="")
        self._hook_why_var = hook_why_var
        tk.Label(hook_inner, textvariable=hook_why_var,
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8, "italic"), wraplength=380, justify="left").pack(
                     fill="x", pady=(6, 0))

        # ── Viral Timing ──────────────────────────────────────────────
        time_outer, time_inner = self._card(right, "Best Post Times", ED["blue"])
        time_outer.grid(row=2, column=0, sticky="ew")
        for platform, times in list(PLATFORM_BEST_TIMES.items())[:4]:
            row_f = tk.Frame(time_inner, bg=ED["bg_card"])
            row_f.pack(fill="x", pady=(0, 3))
            tk.Label(row_f, text=f"{platform}:",
                     bg=ED["bg_card"], fg=ED["txt_secondary"],
                     font=("Arial", 9, "bold"), width=9, anchor="w").pack(side="left")
            tk.Label(row_f, text=times[0],
                     bg=ED["bg_card"], fg=ED["txt_dim"],
                     font=("Arial", 8)).pack(side="left")

    def _refresh_hook_list(self) -> None:
        self._hook_listbox.delete(0, "end")
        angle = self._hook_filter.get()
        self._displayed_hooks = [
            h for h in VIRAL_HOOK_TEMPLATES
            if angle == "all" or h["angle"] == angle
        ]
        for hook in self._displayed_hooks:
            self._hook_listbox.insert("end", f"  {hook['label']}")

    def _on_hook_selected(self, _event=None) -> None:
        sel = self._hook_listbox.curselection()
        if not sel:
            return
        hook = self._displayed_hooks[sel[0]]
        self._hook_template_var.set(f'"{hook["template"]}"')
        self._hook_why_var.set(f"Why it works: {hook['why']}")

    def _apply_recipe(self, recipe: Dict[str, Any]) -> None:
        """Apply a content recipe — sets goal and advances to Add Media."""
        goal_label = next((g["label"] for g in GOAL_CARDS
                           if g["goal"] == recipe["goal"]), None)
        if goal_label:
            self.controller.set_goal_by_label(goal_label)
        # Store recipe tips in automation notes
        tips_note = f"Content Recipe: {recipe['label']}\n" + \
                    "\n".join(f"  • {t}" for t in recipe["tips"])
        self.controller.project.automation_notes.append(tips_note)
        self.controller.app.set_status(
            f"Recipe applied: {recipe['label']}. Add your media to continue.")

    def refresh(self) -> None:
        p = self.controller.project
        self.summary_var.set(
            f"Goal: {p.content_goal}  ·  Bundle: {p.publish_bundle}  ·  CTA: {p.cta_text}"
        )
        if self.controller.restart_keep_media_and_regenerate and p.assets:
            self.keep_media_hint_var.set(
                f"✓ {len(p.assets)} file(s) kept — choosing a new direction rebuilds recommendations immediately.")
        elif p.assets:
            self.keep_media_hint_var.set(
                f"✓ {len(p.assets)} file(s) already imported.")
        else:
            self.keep_media_hint_var.set("")
        if not self.controller.advanced_mode_enabled:
            self.summary_lbl.grid_remove()
        else:
            self.summary_lbl.grid()


class DropFilesScreen(BaseScreen):
    def __init__(self, parent, controller: AppController):
        super().__init__(parent, controller)
        self.columnconfigure(0, weight=2)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self._reference_preview_image = None

        # ── Header ────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=ED["bg_root"], pady=12)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(hdr, text="Add Your Files",
                 bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 20, "bold"), anchor="w").pack(anchor="w")
        tk.Label(hdr,
                 text="Drop media here or click Browse. "
                      "The app analyzes everything automatically — "
                      "you just confirm the direction and continue.",
                 bg=ED["bg_root"], fg=ED["txt_secondary"],
                 font=("Arial", 10), wraplength=1050, justify="left").pack(
                     anchor="w", pady=(4, 0))
        tk.Frame(self, bg=ED["border_hi"], height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # ══════════════════════════════════════════════════════════════
        # LEFT — Media intake
        # ══════════════════════════════════════════════════════════════
        left_outer, left = self._card(self, "MEDIA INTAKE")
        left_outer.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)

        # Drop zone
        drop_zone = tk.Frame(left, bg=ED["bg_input"],
                             highlightbackground=ED["border"], highlightthickness=2,
                             cursor="hand2")
        drop_zone.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        drop_zone.columnconfigure(0, weight=1)
        self.drop_hint = tk.Label(drop_zone,
                                  text="DROP FILES HERE\n\nor click Browse Files",
                                  bg=ED["bg_input"], fg=ED["txt_dim"],
                                  font=("Arial", 13, "bold"),
                                  anchor="center", justify="center")
        self.drop_hint.pack(pady=28, padx=20)
        if tkinterdnd2 and DND_FILES:
            self.drop_hint.drop_target_register(DND_FILES)
            self.drop_hint.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_hint.bind("<Enter>",
            lambda e: self.drop_hint.configure(bg=ED["bg_hover"], fg=ED["txt_primary"]))
        self.drop_hint.bind("<Leave>",
            lambda e: self.drop_hint.configure(bg=ED["bg_input"], fg=ED["txt_dim"]))

        btns = tk.Frame(left, bg=ED["bg_card"])
        btns.grid(row=1, column=0, sticky="w", pady=(0, 10))
        self._ed_btn(btns, "Browse Files", self._browse_files, primary=True).pack(
            side="left", padx=(0, 8))
        self._ed_btn(btns, "Add Caption File",
                     self.controller.import_caption_file).pack(side="left")

        # Status box
        status_outer, status_inner = self._card(left, "WHAT THE APP IS DOING", ED["bg_panel"])
        status_outer.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        status_outer.configure(highlightbackground=ED["border"])

        self.intake_state_var = tk.StringVar(value="○  Status: Idle")
        self.intake_state_label = tk.Label(status_inner, textvariable=self.intake_state_var,
                                           bg=ED["bg_card"], fg=ED["txt_dim"],
                                           font=("Arial", 10, "bold"))
        self.intake_state_label.pack(anchor="w")
        self.intake_progress_var = tk.DoubleVar(value=0.0)
        self._ensure_intake_progress_styles()
        self.intake_progressbar = ttk.Progressbar(
            status_inner, orient="horizontal", mode="determinate",
            variable=self.intake_progress_var, maximum=100,
            style="ED.IntakeIdle.Horizontal.TProgressbar")
        self.intake_progressbar.pack(fill="x", pady=(6, 4))
        self.intake_progress_text_var = tk.StringVar(value="Waiting for media intake to start.")
        tk.Label(status_inner, textvariable=self.intake_progress_text_var,
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 9), wraplength=640, justify="left").pack(anchor="w")
        self._apply_intake_state_style("idle")

        # Media strip
        strip_outer, strip_inner = self._card(left, "YOUR MEDIA", ED["bg_panel"])
        strip_outer.grid(row=3, column=0, sticky="nsew")
        strip_inner.columnconfigure(0, weight=1)
        strip_inner.rowconfigure(0, weight=1)
        self.imported_strip = MiniStoryboardStrip(
            strip_inner, select_callback=self._on_imported_asset_selected, height=150)
        self.imported_strip.grid(row=0, column=0, sticky="nsew")

        act_row = tk.Frame(strip_inner, bg=ED["bg_card"])
        act_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        act_row.columnconfigure(0, weight=1)
        self.selected_media_var = tk.StringVar(value="No media selected.")
        tk.Label(act_row, textvariable=self.selected_media_var,
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(act_row, text="Blue = working  ·  Gold = queued  ·  Dark = ready",
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8)).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self._ed_btn(act_row, "Delete Selected",
                     self._delete_selected_media, small=True).grid(row=0, column=1, sticky="e")

        self.drop_files_cta_var = tk.StringVar(value="")
        tk.Label(act_row, textvariable=self.drop_files_cta_var,
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8), wraplength=520, justify="left").grid(
                     row=2, column=0, sticky="w", pady=(8, 0))
        self.continue_to_drafts_btn = self._ed_btn(
            act_row, "Continue to Drafts →",
            lambda: self.controller.app.show_screen("draft_gallery"),
            primary=True)
        self.continue_to_drafts_btn.grid(row=2, column=1, sticky="e", pady=(8, 0))

        # Direction check
        dir_outer, dir_inner = self._card(left, "DIRECTION CHECK", ED["gold"])
        dir_outer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.detected_direction_var = tk.StringVar(value="Detected direction: Not set yet.")
        self.direction_hint_var = tk.StringVar(value="")
        tk.Label(dir_inner, textvariable=self.detected_direction_var,
                 bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 10), wraplength=760, justify="left").pack(anchor="w")
        tk.Label(dir_inner, textvariable=self.direction_hint_var,
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8, "italic"), wraplength=760, justify="left").pack(
                     anchor="w", pady=(4, 8))
        override_row = tk.Frame(dir_inner, bg=ED["bg_card"])
        override_row.pack(anchor="w")
        # All three start neutral — refresh() highlights whichever matches the current goal
        self.use_before_after_btn = self._ed_btn(
            override_row, "Use Before / After",
            lambda: self.controller.override_goal_from_drop_files("Show Before / After"),
            small=True)
        self.use_before_after_btn.pack(side="left", padx=(0, 6))
        self.use_mastering_btn = self._ed_btn(
            override_row, "Use Mastering Promo",
            lambda: self.controller.override_goal_from_drop_files("Sell Mastering"),
            small=True)
        self.use_mastering_btn.pack(side="left", padx=(0, 6))
        self.use_education_btn = self._ed_btn(
            override_row, "Use Educational Tip",
            lambda: self.controller.override_goal_from_drop_files("Teach Something"),
            small=True)
        self.use_education_btn.pack(side="left")

        # ══════════════════════════════════════════════════════════════
        # RIGHT — Reference, Progress, Caption Intelligence
        # ══════════════════════════════════════════════════════════════
        right_container = tk.Frame(self, bg=ED["bg_root"])
        right_container.grid(row=2, column=1, sticky="nsew")
        right_container.columnconfigure(0, weight=1)
        right_container.rowconfigure(1, weight=1)
        right_container.rowconfigure(2, weight=1)

        # Reference panel
        ref_outer, ref_inner = self._card(right_container, "REFERENCE INSPIRATION")
        ref_outer.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ref_inner.columnconfigure(0, weight=1)

        self.reference_summary_var = tk.StringVar(
            value="No reference examples added yet. Add one to guide the feel and visual direction.")
        tk.Label(ref_inner, textvariable=self.reference_summary_var,
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 9), wraplength=340, justify="left").grid(
                     row=0, column=0, sticky="w", pady=(0, 6))

        # Listbox (full width, short)
        self.reference_listbox = self._tk_listbox(ref_inner, height=3)
        self.reference_listbox.grid(row=1, column=0, sticky="ew")
        self.reference_listbox.bind("<<ListboxSelect>>", lambda e: self._on_reference_selected())

        # Full-width preview below the listbox
        prev_outer = tk.Frame(ref_inner, bg=ED["bg_input"],
                              highlightbackground=ED["border"], highlightthickness=1,
                              height=240)          # fixed pixel height — always visible
        prev_outer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        prev_outer.grid_propagate(False)           # hold the height even when empty
        prev_outer.columnconfigure(0, weight=1)
        prev_outer.rowconfigure(0, weight=1)

        self.reference_preview_label = tk.Label(prev_outer,
            text="No preview\n\nSelect a file above\nto confirm it here.",
            bg=ED["bg_input"], fg=ED["txt_dim"],
            font=("Arial", 9), anchor="center", justify="center")
        self.reference_preview_label.grid(row=0, column=0, sticky="nsew")

        # Status and detail below the preview image
        self.reference_preview_status_var = tk.StringVar(value="")
        tk.Label(ref_inner, textvariable=self.reference_preview_status_var,
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 8), wraplength=360, justify="left").grid(
                     row=3, column=0, sticky="w", pady=(4, 0))
        self.reference_detail_var = tk.StringVar(value="")
        tk.Label(ref_inner, textvariable=self.reference_detail_var,
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8)).grid(row=4, column=0, sticky="w", pady=(1, 0))

        ref_act = tk.Frame(ref_inner, bg=ED["bg_card"])
        ref_act.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self._ed_btn(ref_act, "+ Add", self.controller.import_reference_files,
                     primary=True, small=True).pack(side="left", padx=(0, 6))
        self._ed_btn(ref_act, "Remove", self._remove_selected_reference,
                     small=True).pack(side="left", padx=(0, 6))
        self._ed_btn(ref_act, "Open", self._open_selected_reference,
                     small=True).pack(side="left")

        # Progress panel
        prog_outer, prog_inner = self._card(right_container, "BEHIND THE SCENES", ED["bg_panel"])
        prog_outer.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self.stage_vars: Dict[str, tk.StringVar] = {}
        self.stage_labels: Dict[str, Any] = {}
        self._active_stage: str = ""
        self._completed_stages: set = set()
        for idx, stage in enumerate(INTAKE_STAGES):
            var = tk.StringVar(value=f"○  {stage}")
            lbl = tk.Label(prog_inner, textvariable=var,
                           bg=ED["bg_card"], fg=ED["txt_dim"],
                           font=("Arial", 9), anchor="w")
            lbl.pack(anchor="w", pady=1)
            self.stage_vars[stage] = var
            self.stage_labels[stage] = lbl

        # Caption Intelligence panel — NEW
        cap_outer, cap_inner = self._card(right_container, "CAPTION INTELLIGENCE", ED["gold"])
        cap_outer.grid(row=2, column=0, sticky="nsew")
        tk.Label(cap_inner,
                 text="Proven caption patterns that drive saves, comments & shares:",
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 9), wraplength=360, justify="left").pack(
                     anchor="w", pady=(0, 8))

        self._cap_pattern_var = tk.StringVar(value="")
        self._cap_use_when_var = tk.StringVar(value="")

        self._cap_listbox = self._tk_listbox(cap_inner, height=6)
        self._cap_listbox.pack(fill="x")
        for pat in VIRAL_CAPTION_PATTERNS:
            self._cap_listbox.insert("end", f"  {pat['name']}")
        self._cap_listbox.bind("<<ListboxSelect>>", self._on_caption_pattern_selected)

        tk.Label(cap_inner, textvariable=self._cap_pattern_var,
                 bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 9, "italic"), wraplength=360, justify="left").pack(
                     anchor="w", pady=(8, 0))
        tk.Label(cap_inner, textvariable=self._cap_use_when_var,
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8), wraplength=360, justify="left").pack(
                     anchor="w", pady=(4, 0))

    def _on_caption_pattern_selected(self, _event=None) -> None:
        sel = self._cap_listbox.curselection()
        if not sel:
            return
        pat = VIRAL_CAPTION_PATTERNS[sel[0]]
        self._cap_pattern_var.set(f'"{pat["pattern"]}"')
        self._cap_use_when_var.set(f"Use when: {pat['use_when']}")

    # Keep notes_text alive for refresh() compatibility
    @property
    def notes_text(self):
        return getattr(self, "_notes_text_compat", None)

    def _browse_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Add Media Assets")
        self.controller.import_media_files(list(paths))

    def _on_drop(self, event) -> None:
        paths = [str(Path(item)) for item in self.tk.splitlist(event.data)]
        self.controller.import_media_files(paths)

    def _delete_selected_media(self) -> None:
        card = getattr(self.imported_strip, "selected_card", None)
        if not card:
            self.controller.app.set_status("Select a media item first.")
            return
        self.controller.remove_media_asset_by_id(card.asset_id)

    def _on_imported_asset_selected(self, idx: int) -> None:
        cards = getattr(self.imported_strip, "cards", [])
        if not (0 <= idx < len(cards)):
            self.selected_media_var.set("No media selected.")
            return
        asset_id = cards[idx].asset_id
        asset = next((item for item in self.controller.project.assets if item.asset_id == asset_id), None)
        if asset:
            self.selected_media_var.set(f"Selected: {asset.title} [{asset.media_type}]")
            self.controller.app.set_status(f"Selected media item: {asset.title}")

    def _remove_selected_reference(self) -> None:
        selection = self.reference_listbox.curselection()
        if not selection:
            self.controller.app.set_status("Select a reference item first.")
            return
        idx = selection[0]
        if 0 <= idx < len(self.controller.project.reference_paths):
            removed_path = self.controller.project.reference_paths[idx]
            removed = Path(removed_path).name
            del self.controller.project.reference_paths[idx]
            self.controller.project.reference_preview_paths.pop(removed_path, None)
            self.controller.project.reference_media_types.pop(removed_path, None)
            self.controller.project.reference_preview_notes.pop(removed_path, None)
            if self.controller.project.selected_reference_path == removed_path:
                self.controller.project.selected_reference_path = self.controller.project.reference_paths[0] if self.controller.project.reference_paths else ""
            self.controller.project.automation_notes.append(f"Removed reference file: {removed}")
            self.refresh()
            self.controller.app.set_status(f"Removed reference item: {removed}")

    def _open_selected_reference(self) -> None:
        selection = self.reference_listbox.curselection()
        if not selection:
            self.controller.app.set_status("Select a reference item first.")
            return
        idx = selection[0]
        if 0 <= idx < len(self.controller.project.reference_paths):
            ref_path = Path(self.controller.project.reference_paths[idx])
            try:
                if sys.platform.startswith("win"):
                    os.startfile(str(ref_path))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(ref_path)])
                else:
                    subprocess.Popen(["xdg-open", str(ref_path)])
                self.controller.app.set_status(f"Opened reference item: {ref_path.name}")
            except Exception as exc:
                self.controller.app.set_status(f"Could not open reference item: {exc}")

    def _on_reference_selected(self) -> None:
        selection = self.reference_listbox.curselection()
        if selection and 0 <= selection[0] < len(self.controller.project.reference_paths):
            self.controller.project.selected_reference_path = self.controller.project.reference_paths[selection[0]]
        self._refresh_reference_preview()

    def _refresh_reference_preview(self) -> None:
        selection = self.reference_listbox.curselection()
        if not selection:
            self.reference_preview_label.configure(image="", text="No preview")
            self._reference_preview_image = None
            self.reference_preview_status_var.set("Attach a reference to confirm it here.")
            self.reference_detail_var.set("")
            return
        idx = selection[0]
        if not (0 <= idx < len(self.controller.project.reference_paths)):
            self.reference_preview_label.configure(image="", text="No preview")
            self._reference_preview_image = None
            self.reference_preview_status_var.set("No reference preview available.")
            self.reference_detail_var.set("")
            return
        ref_path_str = self.controller.project.reference_paths[idx]
        ref_path = Path(ref_path_str)
        media_type = self.controller.project.reference_media_types.get(ref_path_str, infer_media_type(ref_path))
        preview_path = self.controller.project.reference_preview_paths.get(ref_path_str, "")
        note = self.controller.project.reference_preview_notes.get(ref_path_str, f"{media_type.title()} reference attached.")

        needs_metadata = (
            ref_path.exists()
            and (
                ref_path_str not in self.controller.project.reference_media_types
                or ref_path_str not in self.controller.project.reference_preview_notes
                or not preview_path
                or (preview_path and not Path(preview_path).exists())
            )
        )
        if needs_metadata:
            rebuilt_preview, rebuilt_type, rebuilt_note, rebuilt_accent = self.controller.analyzer.build_reference_preview(ref_path)
            if rebuilt_accent:
                self.controller.project.reference_accent_color = rebuilt_accent
            self.controller.project.reference_preview_paths[ref_path_str] = rebuilt_preview
            self.controller.project.reference_media_types[ref_path_str] = rebuilt_type
            self.controller.project.reference_preview_notes[ref_path_str] = rebuilt_note
            preview_path = rebuilt_preview
            media_type = rebuilt_type
            note = rebuilt_note

        self.reference_detail_var.set(f"{ref_path.name}\nType: {media_type}")
        self.reference_preview_status_var.set(note)
        if preview_path and Image and ImageTk and Path(preview_path).exists():
            try:
                with Image.open(preview_path) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    img.thumbnail((320, 260))
                    photo = ImageTk.PhotoImage(img)
                self._reference_preview_image = photo
                self.reference_preview_label.configure(image=photo, text="")
                return
            except Exception:
                pass
        self._reference_preview_image = None
        if media_type == "video":
            fallback_label = "Video added\nNo thumbnail"
        elif media_type == "audio":
            fallback_label = "Audio added\nNo waveform"
        else:
            fallback_label = f"{media_type}\nNo preview"
        self.reference_preview_label.configure(image="", text=fallback_label)

    def _ensure_intake_progress_styles(self) -> None:
        try:
            style = ttk.Style(self)
            style.configure("ED.IntakeIdle.Horizontal.TProgressbar", troughcolor="#dddddd", background="#8a8a8a", lightcolor="#8a8a8a", darkcolor="#8a8a8a", bordercolor="#aaaaaa")
            style.configure("ED.IntakeProcessing.Horizontal.TProgressbar", troughcolor="#dddddd", background="#1f5fbf", lightcolor="#1f5fbf", darkcolor="#1f5fbf", bordercolor="#1f5fbf")
            style.configure("ED.IntakeComplete.Horizontal.TProgressbar", troughcolor="#dddddd", background="#1f7a1f", lightcolor="#1f7a1f", darkcolor="#1f7a1f", bordercolor="#1f7a1f")
            style.configure("ED.IntakeError.Horizontal.TProgressbar", troughcolor="#dddddd", background="#b22d2d", lightcolor="#b22d2d", darkcolor="#b22d2d", bordercolor="#b22d2d")
        except Exception:
            pass

    def _apply_stage_visual(self, stage: str, state: str) -> None:
        palette = {
            "pending": {"prefix": "○", "foreground": "#666666"},
            "active": {"prefix": "▶", "foreground": "#1f5fbf"},
            "complete": {"prefix": "●", "foreground": "#1f7a1f"},
            "error": {"prefix": "✖", "foreground": "#b22d2d"},
        }
        resolved = palette.get(state, palette["pending"])
        if stage in self.stage_vars:
            self.stage_vars[stage].set(f"{resolved['prefix']} {stage}")
        label = self.stage_labels.get(stage)
        if label is not None:
            try:
                label.configure(foreground=resolved["foreground"])
            except Exception:
                pass

    def _apply_intake_state_style(self, state: str) -> None:
        palette = {
            "idle": {"label": "○ Status: Idle", "foreground": "#666666", "style": "ED.IntakeIdle.Horizontal.TProgressbar"},
            "processing": {"label": "▶ Status: Processing", "foreground": "#1f5fbf", "style": "ED.IntakeProcessing.Horizontal.TProgressbar"},
            "complete": {"label": "● Status: Intake complete", "foreground": "#1f7a1f", "style": "ED.IntakeComplete.Horizontal.TProgressbar"},
            "error": {"label": "✖ Status: Intake error", "foreground": "#b22d2d", "style": "ED.IntakeError.Horizontal.TProgressbar"},
        }
        resolved = palette.get(state, palette["idle"])
        self.intake_state_var.set(resolved["label"])
        try:
            self.intake_state_label.configure(foreground=resolved["foreground"])
        except Exception:
            pass
        try:
            self.intake_progressbar.configure(style=resolved["style"])
        except Exception:
            pass

    def reset_intake_view(self, payload: Optional[Dict[str, Any]] = None) -> None:
        self.intake_progress_var.set(0.0)
        message = "Preparing media intake..."
        if isinstance(payload, dict):
            message = payload.get("message", message)
        self._apply_intake_state_style("processing")
        self.intake_progress_text_var.set(message)
        self._active_stage = ""
        self._completed_stages.clear()
        for stage in INTAKE_STAGES:
            self._apply_stage_visual(stage, "pending")

    def clear_intake_view(self, message: str = "Start by adding one file. You can keep adding more before moving on.") -> None:
        self.intake_progress_var.set(0.0)
        self._apply_intake_state_style("idle")
        self.intake_progress_text_var.set(message)
        self._active_stage = ""
        self._completed_stages.clear()
        for stage in INTAKE_STAGES:
            self._apply_stage_visual(stage, "pending")

    def set_progress(self, payload: Optional[Dict[str, Any]] = None) -> None:
        if not isinstance(payload, dict):
            return
        total = int(payload.get("total", 0) or 0)
        processed = int(payload.get("processed", 0) or 0)
        detail = payload.get("detail", "")
        base_message = payload.get("message", "Processing media...")
        if total > 0 and detail:
            message = f"{base_message}\n{processed}/{total} complete • {detail}"
        elif total > 0:
            message = f"{base_message}\n{processed}/{total} complete"
        else:
            message = base_message
        self.intake_progress_var.set(float(payload.get("percent", 0.0)))
        self.intake_progress_text_var.set(message)
        state = payload.get("state")
        if state == "complete":
            self._apply_intake_state_style("complete")
        elif state == "error":
            self._apply_intake_state_style("error")
        else:
            self._apply_intake_state_style("processing")

    def set_stage_active(self, stage: str) -> None:
        self._active_stage = stage
        for name in INTAKE_STAGES:
            if name in self._completed_stages:
                self._apply_stage_visual(name, "complete")
            elif name == stage:
                self._apply_stage_visual(name, "active")
            else:
                self._apply_stage_visual(name, "pending")

    def set_stage_complete(self, stage: str) -> None:
        self._completed_stages.add(stage)
        self._apply_stage_visual(stage, "complete")

    def refresh(self) -> None:
        project = self.controller.project
        intake_state = getattr(project, "intake_state", "idle")
        for stage in INTAKE_STAGES:
            if stage in self._completed_stages:
                self._apply_stage_visual(stage, "complete")
            elif stage == self._active_stage:
                self._apply_stage_visual(stage, "active" if intake_state != "error" else "error")
            else:
                self._apply_stage_visual(stage, "pending")
        if intake_state == "complete":
            self._apply_intake_state_style("complete")
        elif intake_state == "error":
            self._apply_intake_state_style("error")
        elif intake_state == "processing":
            self._apply_intake_state_style("processing")
        else:
            self._apply_intake_state_style("idle")

        if not project.assets and not getattr(self.controller, "intake_in_progress", False) and not project.intake_current_item:
            self.clear_intake_view("Start by adding one file. You can keep adding more before moving on.")
        elif project.intake_total > 0 or project.intake_current_item:
            self.set_progress({
                "percent": float(self.intake_progress_var.get()),
                "message": project.intake_current_item or "Waiting for media intake to start.",
                "state": intake_state,
                "stage": project.intake_stage,
                "total": project.intake_total,
                "processed": project.intake_processed,
                "detail": project.intake_current_item,
            })

        asset_map = {asset.asset_id: asset for asset in project.assets}
        cards: List[StoryboardCard] = []
        active_ids = set(getattr(self.controller, "current_intake_asset_ids", []))
        queued_ids = set(getattr(self.controller, "pending_asset_ids", []))
        for asset in project.assets[:24]:
            if asset.asset_id in queued_ids:
                role = "queued"
            elif asset.asset_id in active_ids and getattr(self.controller, "intake_in_progress", False):
                role = "processing"
            else:
                role = asset.media_type
            cards.append(StoryboardCard(asset_id=asset.asset_id, role=role))
        selected_index = getattr(self.imported_strip, "selected_index", -1)
        self.imported_strip.render(cards, asset_map, selected_index=selected_index)
        selected = getattr(self.imported_strip, "selected_card", None)
        if selected and selected.asset_id in asset_map:
            asset = asset_map[selected.asset_id]
            if asset.asset_id in queued_ids:
                self.selected_media_var.set(f"Selected: {asset.title} [{asset.media_type}] — queued for next intake pass.")
            elif asset.asset_id in active_ids and getattr(self.controller, "intake_in_progress", False):
                self.selected_media_var.set(f"Selected: {asset.title} [{asset.media_type}] — intake in progress.")
            else:
                self.selected_media_var.set(f"Selected: {asset.title} [{asset.media_type}]")
        elif project.assets:
            self.selected_media_var.set("Click a media item to confirm selection or delete it.")
        else:
            self.selected_media_var.set("No media selected.")
        try:
            self.continue_to_drafts_btn.configure(state=("normal" if bool(project.assets) else "disabled"))
        except Exception:
            pass
        if project.assets:
            self.drop_files_cta_var.set("Your media is ready. Add more files or reference examples, or click Continue to Drafts.")
        else:
            self.drop_files_cta_var.set("Start by adding one file. You can keep adding more before moving on.")

        current_goal = project.content_goal or "Not set yet"
        if not project.assets:
            self.detected_direction_var.set("Detected direction right now: Waiting for media")
            self.direction_hint_var.set("After you add media, the app will recommend a direction here.")
        else:
            self.detected_direction_var.set(f"Detected direction right now: {current_goal}")
            if getattr(project, "auto_inference_enabled", False) and current_goal == "Mastering Promo":
                self.direction_hint_var.set("The app currently thinks this looks like a promo-style draft. If these are really before/after proof clips, switch the direction here before continuing.")
            elif getattr(project, "auto_inference_enabled", False):
                self.direction_hint_var.set("The app made its best guess from the media. You can switch directions here any time before continuing.")
            else:
                self.direction_hint_var.set("You manually set this direction. You can still switch it here before continuing.")
        try:
            enabled = bool(project.assets)
            state = "normal" if enabled else "disabled"
            self.use_before_after_btn.configure(state=state)
            self.use_mastering_btn.configure(state=state)
            self.use_education_btn.configure(state=state)

            # Highlight the button that matches the current direction;
            # all others revert to the inactive style.
            goal = project.content_goal or ""
            _ACTIVE   = {"bg": ED["red"],     "fg": "#ffffff", "activebackground": ED["red_hover"]}
            _INACTIVE = {"bg": ED["bg_card"],  "fg": ED["txt_primary"], "activebackground": ED["bg_hover"]}

            ba_active   = goal == "Before / After Comparison"
            mast_active = goal in {"Mastering Promo", "Offer / CTA", "New Release Teaser", "Client Testimonial"}
            edu_active  = goal == "Educational Tip"

            for btn, active in [
                (self.use_before_after_btn, ba_active),
                (self.use_mastering_btn,    mast_active),
                (self.use_education_btn,    edu_active),
            ]:
                style = _ACTIVE if active else _INACTIVE
                btn.configure(**style)
        except Exception:
            pass

        self.reference_listbox.delete(0, "end")
        selected_reference_index = -1
        for idx, ref in enumerate(project.reference_paths):
            ref_path = Path(ref)
            media_type = project.reference_media_types.get(ref, infer_media_type(ref_path))
            self.reference_listbox.insert("end", f"{ref_path.name} [{media_type}]")
            if ref == project.selected_reference_path:
                selected_reference_index = idx
        if selected_reference_index >= 0:
            self.reference_listbox.selection_clear(0, "end")
            self.reference_listbox.selection_set(selected_reference_index)
            self.reference_listbox.activate(selected_reference_index)
            self.reference_listbox.see(selected_reference_index)
        elif project.reference_paths:
            self.reference_listbox.selection_clear(0, "end")
            self.reference_listbox.selection_set(0)
            self.reference_listbox.activate(0)
            self.reference_listbox.see(0)
            project.selected_reference_path = project.reference_paths[0]
        ref_count = len(project.reference_paths)
        if ref_count == 0:
            self.reference_summary_var.set("No reference examples added yet. Add one if you want the app to chase a certain feel.")
        elif ref_count == 1:
            self.reference_summary_var.set("1 reference example added. Select it to confirm the preview and status here.")
        else:
            self.reference_summary_var.set(f"{ref_count} reference examples added. Select one to confirm the preview, open it, or remove it.")
        self._refresh_reference_preview()

        if self.notes_text is not None:
            self.notes_text.delete("1.0", "end")
            self.notes_text.insert("1.0", "\n".join(project.automation_notes or ["No automation notes yet."]))


class DraftGalleryScreen(BaseScreen):
    def __init__(self, parent, controller: AppController):
        super().__init__(parent, controller)
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text="Review your recommended drafts", style="ED.Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(self, text="We recommend a best version first. Use it, try another option, or go back and add more media if you need more proof.", style="ED.Subhead.TLabel", wraplength=980).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 12))

        left = ttk.LabelFrame(self, text="Draft Options", padding=10)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        self.left_panel = left
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.scroll = ScrollFrame(left, orient="vertical", height=560)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        actions = ttk.Frame(left)
        actions.grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Button(actions, text="Refresh Draft Ideas", style="ED.Secondary.TButton", command=self.controller.regenerate_drafts).grid(row=0, column=0, padx=(0, 8))
        self.more_options_btn = ttk.Button(actions, text="More Options", style="ED.Secondary.TButton", command=self._toggle_more_options)
        self.more_options_btn.grid(row=0, column=1)

        # Right panel wrapped in a ScrollFrame so the preview image,
        # copy tabs, and option cards are always reachable
        right_scroll_outer = ttk.LabelFrame(self, text="Draft Details", padding=4)
        right_scroll_outer.grid(row=2, column=1, sticky="nsew")
        right_scroll_outer.columnconfigure(0, weight=1)
        right_scroll_outer.rowconfigure(0, weight=1)
        self.right_panel = right_scroll_outer

        right_scroll = ScrollFrame(right_scroll_outer, orient="vertical", height=700)
        right_scroll.grid(row=0, column=0, sticky="nsew")

        right = right_scroll.inner   # all widgets go into the scrollable inner frame
        right.columnconfigure(0, weight=1)

        self.detail_var = tk.StringVar(value="Select a draft to see details.")
        self.detail_label = ttk.Label(right, textvariable=self.detail_var, wraplength=430, justify="left")
        self.detail_label.grid(row=0, column=0, sticky="w")
        self.recommendation_box = ttk.LabelFrame(right, text="Recommended for you", padding=10)
        self.recommendation_box.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        self.recommendation_box.columnconfigure(0, weight=1)
        self.recommendation_title_var = tk.StringVar(value="We picked this version because…")
        self.recommendation_reason_var = tk.StringVar(value="Add media to generate a recommendation.")
        self.recommendation_reassurance_var = tk.StringVar(value="You can always try another recommendation later.")
        ttk.Label(self.recommendation_box, textvariable=self.recommendation_title_var, font=("Arial", 12, "bold"), wraplength=410, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(self.recommendation_box, textvariable=self.recommendation_reason_var, wraplength=410, justify="left").grid(row=1, column=0, sticky="w", pady=(6, 6))
        ttk.Label(self.recommendation_box, textvariable=self.recommendation_reassurance_var, foreground="#666666", wraplength=410, justify="left").grid(row=2, column=0, sticky="w", pady=(0, 10))
        # ── Live Hook / Title / CTA strip — always visible ─────────────
        htc_outer = tk.Frame(self.recommendation_box, bg=ED["bg_card"],
                             highlightbackground=ED["border"], highlightthickness=1)
        htc_outer.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        htc_outer.columnconfigure(0, weight=1)
        htc_title = tk.Frame(htc_outer, bg="#0a0a0a", padx=10, pady=5)
        htc_title.pack(fill="x")
        tk.Label(htc_title, text="YOUR HOOK  ·  TITLE  ·  CTA",
                 bg="#0a0a0a", fg=ED["txt_dim"],
                 font=("Arial", 8, "bold")).pack(side="left")
        tk.Label(htc_title, text="← what goes into the compiled post",
                 bg="#0a0a0a", fg=ED["txt_dim"],
                 font=("Arial", 7)).pack(side="left", padx=(8, 0))

        htc_body = tk.Frame(htc_outer, bg=ED["bg_card"], padx=10, pady=8)
        htc_body.pack(fill="x")
        htc_body.columnconfigure(1, weight=1)

        tk.Label(htc_body, text="HOOK",
                 bg=ED["bg_card"], fg=ED["red"],
                 font=("Arial", 8, "bold"), width=6, anchor="w").grid(
                     row=0, column=0, sticky="w")
        self._htc_hook_var = tk.StringVar(value="—")
        tk.Text(htc_body, textvariable=None,
                height=1, wrap="none",
                bg=ED["bg_card"], fg="#ffffff",
                insertbackground=ED["bg_card"],
                relief="flat", bd=0, font=("Arial", 10, "bold"),
                state="disabled", cursor="arrow").grid(
                    row=0, column=1, sticky="ew")
        # Use Label for hook text — simpler and reliable
        self._htc_hook_lbl = tk.Label(htc_body,
                 textvariable=self._htc_hook_var,
                 bg=ED["bg_card"], fg="#ffffff",
                 font=("Arial", 10, "bold"), anchor="w", wraplength=800)
        self._htc_hook_lbl.grid(row=0, column=1, sticky="ew")

        tk.Label(htc_body, text="TITLE",
                 bg=ED["bg_card"], fg=ED["gold"],
                 font=("Arial", 8, "bold"), width=6, anchor="w").grid(
                     row=1, column=0, sticky="w", pady=(4, 0))
        self._htc_title_var = tk.StringVar(value="—")
        self._htc_title_lbl = tk.Label(htc_body,
                 textvariable=self._htc_title_var,
                 bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 10), anchor="w", wraplength=800)
        self._htc_title_lbl.grid(row=1, column=1, sticky="ew", pady=(4, 0))

        tk.Label(htc_body, text="CTA",
                 bg=ED["bg_card"], fg=ED["green"],
                 font=("Arial", 8, "bold"), width=6, anchor="w").grid(
                     row=2, column=0, sticky="w", pady=(4, 0))
        self._htc_cta_var = tk.StringVar(value="—")
        self._htc_cta_lbl = tk.Label(htc_body,
                 textvariable=self._htc_cta_var,
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 10), anchor="w", wraplength=800)
        self._htc_cta_lbl.grid(row=2, column=1, sticky="ew", pady=(4, 0))
        # ────────────────────────────────────────────────────────────────

        self.hero_preview = DraftOutputPreviewPanel(self.recommendation_box)
        self.hero_preview.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        self.hero_preview.set_display_size(900)  # large enough to read text overlays
        self.copy_preview_box = ttk.LabelFrame(self.recommendation_box, text="Final text going into this draft", padding=10)
        self.copy_preview_box.grid(row=5, column=0, sticky="ew", pady=(0, 12))
        self.copy_preview_box.columnconfigure(0, weight=1)
        self.copy_preview_intro_var = tk.StringVar(value="The preview above uses the current Hook, Title, and CTA. Choose a tab below so you can clearly see the exact wording that will go into the compiled clip.")
        ttk.Label(self.copy_preview_box, textvariable=self.copy_preview_intro_var, style="ED.Subhead.TLabel", wraplength=760, justify="left").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.copy_preview_selected_field = tk.StringVar(value="hook")
        self.copy_preview_tab_bar = ttk.Frame(self.copy_preview_box)
        self.copy_preview_tab_bar.grid(row=1, column=0, sticky="w", pady=(0, 10))
        self.copy_preview_inner = ttk.Frame(self.copy_preview_box)
        self.copy_preview_inner.grid(row=2, column=0, sticky="ew")
        self.copy_preview_inner.columnconfigure(0, weight=1)
        recommendation_actions = ttk.Frame(self.recommendation_box)
        recommendation_actions.grid(row=6, column=0, sticky="w")
        ttk.Button(recommendation_actions, text="Open Quick Refine", style="ED.Secondary.TButton", command=self.controller.open_recommended_quick_refine).grid(row=0, column=0, padx=(0, 8))
        export_now = tk.Button(recommendation_actions, text="Export Recommended Version", command=self.controller.export_recommended_version, font=("Arial", 11, "bold"), bg="#8b2d2d", fg="#ffffff", activebackground="#a53a3a", activeforeground="#ffffff", padx=12, pady=6)
        export_now.grid(row=0, column=1, padx=(0, 8))
        self.try_another_btn = ttk.Button(recommendation_actions, text="Try Another Recommendation", style="ED.Secondary.TButton", command=self.controller.try_another_recommendation)
        self.try_another_btn.grid(row=0, column=2, padx=(0, 8))
        self.start_over_btn = ttk.Button(recommendation_actions, text="Start Over With Different Direction", style="ED.Secondary.TButton", command=self.controller.start_over_with_different_direction)
        self.start_over_btn.grid(row=0, column=3, padx=(0, 8))
        self.recommendation_more_options_btn = ttk.Button(recommendation_actions, text="More Options", style="ED.Secondary.TButton", command=self._toggle_more_options)
        self.recommendation_more_options_btn.grid(row=0, column=4)

        self.advanced_preview_controls = ttk.Frame(right)
        self.advanced_preview_controls.grid(row=2, column=0, sticky="ew", pady=(8, 8))
        self.simple_gallery_hint_var = tk.StringVar(value="")
        self.simple_gallery_hint = ttk.Label(right, textvariable=self.simple_gallery_hint_var, foreground="#666666", wraplength=430, justify="left")
        self.simple_gallery_hint.grid(row=2, column=0, sticky="ew", pady=(8, 8))
        controls = self.advanced_preview_controls
        ttk.Label(controls, text="Text size").grid(row=0, column=0, sticky="w")
        self.caption_emphasis_var = tk.StringVar(value=self.controller.project.preview_caption_emphasis)
        self.caption_emphasis_box = ttk.Combobox(controls, textvariable=self.caption_emphasis_var, values=list(CAPTION_EMPHASIS_PRESETS.keys()), state="readonly", width=12)
        self.caption_emphasis_box.grid(row=0, column=1, sticky="w", padx=(8, 10))
        self.caption_emphasis_box.bind("<<ComboboxSelected>>", lambda e: self._on_emphasis_changed())
        ttk.Label(controls, text="Caption style").grid(row=0, column=2, sticky="w")
        self.caption_style_var = tk.StringVar(value=self.controller.project.preview_caption_style)
        self.caption_style_box = ttk.Combobox(controls, textvariable=self.caption_style_var, values=list(CAPTION_STYLE_PRESETS.keys()), state="readonly", width=18)
        self.caption_style_box.grid(row=0, column=3, sticky="w", padx=(8, 10))
        self.caption_style_box.bind("<<ComboboxSelected>>", lambda e: self._on_style_changed())
        ttk.Label(controls, text="Caption position").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.caption_position_var = tk.StringVar(value=self.controller.project.preview_caption_position)
        self.caption_position_box = ttk.Combobox(controls, textvariable=self.caption_position_var, values=CAPTION_POSITION_PRESETS, state="readonly", width=16)
        self.caption_position_box.grid(row=1, column=1, sticky="w", padx=(8, 10), pady=(6, 0))
        self.caption_position_box.bind("<<ComboboxSelected>>", lambda e: self._on_position_changed())
        ttk.Label(controls, text="Platform").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.platform_var = tk.StringVar(value=self.controller.project.preview_platform_variant)
        self.platform_box = ttk.Combobox(controls, textvariable=self.platform_var, values=PLATFORM_VARIANTS, state="readonly", width=14)
        self.platform_box.grid(row=1, column=3, sticky="w", padx=(8, 10), pady=(6, 0))
        self.platform_box.bind("<<ComboboxSelected>>", lambda e: self._on_platform_changed())

        self.detail_strip = MiniStoryboardStrip(right, height=150)
        self.detail_strip.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.preview_panel = DraftOutputPreviewPanel(right)
        self.preview_panel.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        self.copy_text = tk.Text(right, height=9, wrap="word")
        self.copy_text.grid(row=5, column=0, sticky="nsew")
        self.button_row = ttk.Frame(right)
        self.button_row.grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Button(self.button_row, text="Use This Draft", command=self._use_selected).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(self.button_row, text="Preview Output Formats", command=self._show_bundle_info).grid(row=0, column=1)
        self.selected_id: str = ""
        self.card_photo_cache: Dict[str, Any] = {}
        self.show_all_options_in_simple: bool = False

    def _toggle_more_options(self) -> None:
        self.show_all_options_in_simple = not self.show_all_options_in_simple
        self.refresh()

    def _platform_labels(self, draft: DraftOption) -> List[str]:
        labels = list(PLATFORM_EXPORT_STRENGTHS.get(draft.recommended_bundle, [draft.recommended_bundle]))
        if draft.style_tag == "cta" and "CTA Strong" not in labels:
            labels.insert(0, "CTA Strong")
        elif draft.style_tag == "proof" and "Proof Strong" not in labels:
            labels.insert(0, "Proof Strong")
        elif draft.style_tag == "educational" and "Teach / Explain" not in labels:
            labels.insert(0, "Teach / Explain")
        elif draft.style_tag == "balanced" and "Best All-Around" not in labels:
            labels.insert(0, "Best All-Around")
        return labels[:4]

    def _platform_toggle_row(self, parent, draft: DraftOption) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="Preview style:", foreground="#9d9388").pack(side="left", padx=(0, 8))
        selected_variant = self.controller.project.preview_platform_variant if draft.draft_id == self.selected_id else ""
        for label in self._platform_labels(draft):
            variant = resolve_platform_variant_from_label(label)
            is_selected = draft.draft_id == self.selected_id and selected_variant == variant
            btn = tk.Button(
                row,
                text=(f"✓ {label}" if is_selected else label),
                command=lambda did=draft.draft_id, lbl=label: self._preview_platform(did, lbl),
                bg="#b32d2e" if is_selected else "#171717",
                fg="#f6f1e8",
                activebackground="#d23b3d" if is_selected else "#262626",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=10,
                pady=6,
                highlightthickness=1,
                highlightbackground="#7a1f1f" if is_selected else "#4a443d",
                highlightcolor="#7a1f1f" if is_selected else "#4a443d",
                cursor="hand2",
            )
            btn.pack(side="left", padx=(0, 4))

    def _copy_preview_cards(self, parent, draft: DraftOption) -> None:
        holder = ttk.Frame(parent)
        holder.pack(fill="x", pady=(6, 10))
        note = tk.Frame(holder, bd=1, relief="solid", bg="#111111", highlightthickness=1, highlightbackground="#38322d")
        note.pack(fill="x")
        tk.Label(note, text="Readable copy preview lives on the right", bg="#111111", fg="#f6f1e8", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        tk.Message(
            note,
            text="Select this draft, then use the larger Hook / Title / CTA choices in the right-side panel to see exactly what text goes into the compiled clip.",
            bg="#111111",
            fg="#d5cec4",
            width=580,
            justify="left",
            font=("Arial", 10),
        ).pack(fill="x", padx=10, pady=(0, 10))

    def _draft_card(self, parent, draft: DraftOption, simple_rank_label: str = "") -> None:
        frame = ttk.Frame(parent, padding=10, relief="ridge")
        frame.pack(fill="x", pady=6)
        top = ttk.Frame(frame)
        top.pack(fill="x")
        left_top = ttk.Frame(top)
        left_top.pack(side="left")
        ttk.Label(left_top, text=draft.name, font=("Arial", 12, "bold")).pack(side="left")
        if simple_rank_label:
            tk.Label(left_top, text=simple_rank_label, bg="#1f2f44", fg="#ffffff", padx=8, pady=3).pack(side="left", padx=(8, 0))
        if self.controller.project.export_candidate_draft_id == draft.draft_id:
            tk.Label(left_top, text="EXPORT CANDIDATE", bg="#7a1f1f", fg="#ffffff", padx=8, pady=3).pack(side="left", padx=(8, 0))
        ttk.Label(top, text=f"{int(draft.confidence_score * 100)}% confidence").pack(side="right")
        ttk.Label(frame, text=f"{draft.style_tag.title()} • {draft.runtime_estimate:.1f}s • {draft.recommended_bundle}", foreground="#555555").pack(anchor="w", pady=(2, 2))
        badge_row = ttk.Frame(frame)
        badge_row.pack(fill="x", pady=(0, 6))
        ttk.Label(badge_row, text="Strongest on:", foreground="#666666").pack(side="left", padx=(0, 6))
        for label in self._platform_labels(draft):
            tk.Label(badge_row, text=label, bg="#1f1f1f", fg="#e8e8e8", padx=8, pady=3).pack(side="left", padx=(0, 4))
        if self.controller.advanced_mode_enabled and (draft.locked_platform_variant or draft.locked_caption_style or draft.locked_caption_position or draft.locked_caption_emphasis):
            locked_bits = [
                draft.locked_platform_variant or "Auto",
                draft.locked_caption_style or self.controller.project.preview_caption_style,
                draft.locked_caption_position or self.controller.project.preview_caption_position,
                draft.locked_caption_emphasis or self.controller.project.preview_caption_emphasis,
            ]
            ttk.Label(frame, text=f"Locked preview: {' • '.join(locked_bits)}", foreground="#8a4b4b").pack(anchor="w", pady=(0, 6))
        self._platform_toggle_row(frame, draft)
        strip = MiniStoryboardStrip(frame, height=120)
        strip.pack(fill="x")
        strip.render(draft.storyboard_cards, {a.asset_id: a for a in self.controller.project.assets})
        self._copy_preview_cards(frame, draft)
        ttk.Label(frame, text=draft.rationale, wraplength=700).pack(anchor="w", pady=(2, 6))
        btns = ttk.Frame(frame)
        btns.pack(fill="x")
        ttk.Button(btns, text="Preview This Draft", command=lambda did=draft.draft_id: self._select(did)).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Use This Draft", command=lambda did=draft.draft_id: self.controller.select_draft(did)).pack(side="left", padx=(0, 6))
        if self.controller.advanced_mode_enabled:
            ttk.Button(btns, text="Lock Preview Setup", command=lambda did=draft.draft_id: self.controller.lock_preview_setup_to_draft(did)).pack(side="left", padx=(0, 6))
            ttk.Button(btns, text=("Export Candidate" if self.controller.project.export_candidate_draft_id == draft.draft_id else "Promote to Export"), command=lambda did=draft.draft_id: self.controller.promote_export_candidate(did)).pack(side="left")

    def _preview_platform(self, draft_id: str, label: str) -> None:
        self.selected_id = draft_id
        self.controller.set_preview_from_platform_label(draft_id, label)

    def _select(self, draft_id: str) -> None:
        self.selected_id = draft_id
        draft = next((d for d in self.controller.project.drafts if d.draft_id == draft_id), None)
        if draft:
            self.controller._apply_draft_preview_preferences(draft)
        self.refresh()

    def _use_selected(self) -> None:
        if self.selected_id:
            self.controller.select_draft(self.selected_id)

    def _set_copy_preview_field(self, field_name: str) -> None:
        if field_name not in {"hook", "title", "cta"}:
            field_name = "hook"
        self.copy_preview_selected_field.set(field_name)
        draft = next((d for d in self.controller.project.drafts if d.draft_id == self.selected_id), None)
        self._render_copy_preview_panel(draft)

    def _show_bundle_info(self) -> None:
        draft = next((d for d in self.controller.project.drafts if d.draft_id == self.selected_id), None)
        if not draft:
            return
        bundle = PUBLISH_BUNDLES.get(draft.recommended_bundle, ["9x16"])
        messagebox.showinfo(APP_NAME, f"Platform pack: {draft.recommended_bundle}\nFormats: {', '.join(bundle)}")

    def _on_platform_changed(self) -> None:
        self.controller.set_preview_platform_variant(self.platform_var.get())

    def _on_style_changed(self) -> None:
        self.controller.set_preview_caption_style(self.caption_style_var.get())

    def _on_position_changed(self) -> None:
        self.controller.set_preview_caption_position(self.caption_position_var.get())

    def _on_emphasis_changed(self) -> None:
        self.controller.set_preview_caption_emphasis(self.caption_emphasis_var.get())

    def _render_copy_preview_panel(self, draft: Optional[DraftOption]) -> None:
        for child in self.copy_preview_tab_bar.winfo_children():
            child.destroy()
        for child in self.copy_preview_inner.winfo_children():
            child.destroy()
        self.copy_preview_inner.columnconfigure(0, weight=1)

        p = self.controller.project
        sections = [
            ("Hook",  "hook",  (draft.hook_options  if draft else []),
             p.hook_text  or (draft.hook_options[0]  if draft and draft.hook_options  else "")),
            ("Title", "title", (draft.title_options if draft else []),
             p.title_text or (draft.title_options[0] if draft and draft.title_options else "")),
            ("CTA",   "cta",   (draft.cta_options   if draft else []),
             p.cta_text   or (draft.cta_options[0]   if draft and draft.cta_options   else "")),
        ]
        selected_field = self.copy_preview_selected_field.get()
        if selected_field not in {field for _, field, _, _ in sections}:
            selected_field = "hook"
            self.copy_preview_selected_field.set(selected_field)

        for label, field_name, _options, _current_value in sections:
            is_selected = field_name == selected_field
            tk.Button(
                self.copy_preview_tab_bar,
                text=(f"✓ {label}" if is_selected else label),
                command=(lambda f=field_name: self._set_copy_preview_field(f)),
                bg="#b32d2e" if is_selected else "#171717",
                fg="#ffffff" if is_selected else "#f6f1e8",
                activebackground="#d23b3d" if is_selected else "#262626",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=12,
                pady=8,
                cursor="hand2",
                highlightthickness=1,
                highlightbackground="#7a1f1f" if is_selected else "#4a443d",
                highlightcolor="#7a1f1f" if is_selected else "#4a443d",
            ).pack(side="left", padx=(0, 6))

        if not draft:
            empty = tk.Frame(self.copy_preview_inner, bd=1, relief="solid", bg="#111111", highlightthickness=1, highlightbackground="#38322d")
            empty.grid(row=0, column=0, sticky="ew")
            tk.Label(
                empty,
                text="Choose a draft to see the final Hook, Title, and CTA selections that will go into the compiled clip.",
                bg="#111111",
                fg="#d5cec4",
                wraplength=700,
                justify="left",
                anchor="w",
                font=("Arial", 10),
            ).pack(fill="x", padx=12, pady=12)
            return

        label, field_name, options, current_value = next(
            item for item in sections if item[1] == selected_field
        )
        frame = tk.Frame(self.copy_preview_inner, bd=1, relief="solid", bg="#0f0f0f", highlightthickness=1, highlightbackground="#38322d")
        frame.grid(row=0, column=0, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        header = tk.Frame(frame, bg="#0f0f0f")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        tk.Label(header, text=label.upper(), bg="#0f0f0f", fg="#f6f1e8", font=("Arial", 11, "bold")).pack(side="left")
        tk.Label(header, text=f"Current {label}", bg="#7a1f1f", fg="#ffffff", font=("Arial", 9, "bold"), padx=8, pady=3).pack(side="left", padx=(10, 0))

        current_box = tk.Frame(frame, bg="#1a0808", highlightthickness=1, highlightbackground="#7a1f1f")
        current_box.grid(row=1, column=0, sticky="ew", padx=12)
        current_text = (current_value or (options[0] if options else "No suggestion available.")).strip() or "No suggestion available."
        cur_txt = tk.Text(current_box, height=2, wrap="word",
                          bg="#1a0808", fg="#ffffff",
                          insertbackground="#1a0808",
                          selectbackground="#b32d2e",
                          relief="flat", bd=0,
                          font=("Arial", 12, "bold"),
                          padx=14, pady=10,
                          cursor="arrow")
        cur_txt.insert("1.0", current_text)
        cur_txt.configure(state="disabled")
        cur_txt.pack(fill="x")

        # ── Custom text entry ─────────────────────────────────────────
        custom_row = tk.Frame(frame, bg="#0f0f0f")
        custom_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 0))
        custom_row.columnconfigure(0, weight=1)
        tk.Label(custom_row, text=f"Write your own {label}:",
                 bg="#0f0f0f", fg="#c8beb3",
                 font=("Arial", 9)).grid(row=0, column=0, sticky="w", pady=(0, 4))
        custom_var = tk.StringVar(value=current_text)
        custom_entry = tk.Entry(
            custom_row,
            textvariable=custom_var,
            bg=ED["bg_input"], fg=ED["txt_primary"],
            insertbackground=ED["txt_primary"],
            relief="flat", bd=0, font=("Arial", 11),
            highlightthickness=1,
            highlightbackground=ED["border"],
            highlightcolor=ED["red"])
        custom_entry.grid(row=1, column=0, sticky="ew")

        def _apply_custom(field=field_name, var=custom_var):
            val = var.get().strip()
            if val:
                self.controller.choose_copy(field, val)

        apply_btn = tk.Button(
            custom_row, text="Apply →",
            command=_apply_custom,
            bg=ED["red"], fg="#ffffff",
            activebackground=ED["red_hover"], activeforeground="#ffffff",
            font=("Arial", 9, "bold"), relief="flat", bd=0,
            padx=10, pady=5, cursor="hand2")
        apply_btn.grid(row=1, column=1, padx=(8, 0))
        # Also apply on Enter key
        custom_entry.bind("<Return>", lambda e: _apply_custom())

        helper = tk.Label(
            frame,
            text=f"Showing {label} choices. Click Title or CTA above to preview those recommendations too.",
            bg="#0f0f0f",
            fg="#c8beb3",
            font=("Arial", 9),
            anchor="w",
            justify="left",
        )
        helper.grid(row=3, column=0, sticky="ew", padx=12, pady=(8, 0))

        options_holder = tk.Frame(frame, bg="#0f0f0f")
        options_holder.grid(row=4, column=0, sticky="ew", padx=12, pady=(10, 12))
        option_list = options[:3] if options else [current_text]
        for col, option in enumerate(option_list):
            is_current = (option == current_text)
            card_bg   = "#1a1212" if is_current else "#111111"
            border_bg = "#b32d2e" if is_current else "#38322d"
            card = tk.Frame(
                options_holder,
                bg=card_bg,
                highlightthickness=2,
                highlightbackground=border_bg,
                bd=0,
            )
            card.grid(row=0, column=col, sticky="nsew", padx=(0, 8))
            options_holder.grid_columnconfigure(col, weight=1)

            badge_bg = "#b32d2e" if is_current else "#2a2828"
            badge_fg = "#ffffff"
            badge_text = f"CURRENT {label.upper()}" if is_current else f"ALT {label.upper()}"
            tk.Label(card, text=badge_text,
                     bg=badge_bg, fg=badge_fg,
                     font=("Arial", 9, "bold"),
                     padx=8, pady=3).pack(fill="x", padx=0, pady=(0, 0))

            # Use read-only Text widget — immune to global option_add color overrides
            opt_text = option.strip() if option else "—"
            txt = tk.Text(card, height=3, wrap="word",
                          bg=card_bg, fg="#ffffff",
                          insertbackground=card_bg,
                          selectbackground="#b32d2e",
                          relief="flat", bd=0,
                          font=("Arial", 10),
                          padx=10, pady=8,
                          cursor="arrow")
            txt.insert("1.0", opt_text)
            txt.configure(state="disabled")
            txt.pack(fill="x", padx=0, pady=0)

            btn_text = f"✓ Currently selected" if is_current else f"Use as {label}"
            tk.Button(
                card,
                text=btn_text,
                command=(lambda f=field_name, v=option: self.controller.choose_copy(f, v)),
                bg="#b32d2e" if is_current else "#2a2020",
                fg="#ffffff",
                activebackground="#d23b3d",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=10,
                pady=7,
                cursor="hand2",
            ).pack(fill="x", padx=0, pady=(0, 0))

    def refresh(self) -> None:
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        drafts = self.controller.project.drafts
        recommended = self.controller.export_candidate_draft() or (drafts[0] if drafts else None)
        if recommended and (not self.selected_id or not any(d.draft_id == self.selected_id for d in drafts)):
            self.selected_id = recommended.draft_id
        elif not self.selected_id and drafts:
            self.selected_id = drafts[0].draft_id
        self.platform_var.set(self.controller.project.preview_platform_variant)
        self.caption_style_var.set(self.controller.project.preview_caption_style)
        self.caption_position_var.set(self.controller.project.preview_caption_position)
        self.caption_emphasis_var.set(self.controller.project.preview_caption_emphasis)

        simple_mode = not self.controller.advanced_mode_enabled
        if simple_mode:
            self.advanced_preview_controls.grid_remove()
            self.simple_gallery_hint.grid()
            if self.show_all_options_in_simple:
                self.simple_gallery_hint_var.set("Simple Mode is showing the full gallery now. Collapse it again if you want to return to the calmer recommended path.")
            else:
                self.simple_gallery_hint_var.set("Simple Mode keeps things calm. Start with the recommended version, try one alternate, or add more media before moving on.")
            self.detail_strip.grid_remove()
            self.preview_panel.grid_remove()
            self.copy_text.grid_remove()
            self.button_row.grid_remove()
            self.hero_preview.grid()
            self.detail_label.grid_remove()
            self.try_another_btn.grid()
            self.start_over_btn.grid()
            if self.show_all_options_in_simple:
                self.left_panel.grid()
                self.right_panel.grid(row=2, column=1, sticky="nsew")
                self.recommendation_more_options_btn.configure(text="Fewer Options")
                self.more_options_btn.grid()
                self.more_options_btn.configure(text="Fewer Options")
                self.more_options_btn.grid_remove()
                self.recommendation_more_options_btn.grid()
                self.hero_preview.set_display_size(460)
            else:
                self.left_panel.grid_remove()
                self.right_panel.grid(row=2, column=0, columnspan=2, sticky="nsew")
                self.recommendation_more_options_btn.configure(text="More Options")
                self.more_options_btn.grid_remove()
                self.recommendation_more_options_btn.grid()
                self.hero_preview.set_display_size(700)
        else:
            self.left_panel.grid()
            self.right_panel.grid(row=2, column=1, columnspan=1, sticky="nsew")
            self.advanced_preview_controls.grid()
            self.simple_gallery_hint.grid_remove()
            self.detail_strip.grid()
            self.preview_panel.grid()
            self.copy_text.grid()
            self.button_row.grid()
            self.hero_preview.grid_remove()
            self.detail_label.grid()
            self.try_another_btn.grid_remove()
            self.start_over_btn.grid_remove()
            self.recommendation_more_options_btn.grid_remove()
            self.hero_preview.set_display_size(420)

        visible_drafts = drafts
        if simple_mode and not self.show_all_options_in_simple:
            visible_drafts = drafts[:2]
        if simple_mode and len(drafts) > 2:
            self.more_options_btn.configure(text=("Fewer Options" if self.show_all_options_in_simple else "More Options"))
        else:
            self.more_options_btn.grid_remove()
            if simple_mode:
                self.recommendation_more_options_btn.grid_remove()

        for idx, draft in enumerate(visible_drafts):
            rank_label = ""
            if simple_mode and not self.show_all_options_in_simple:
                if idx == 0:
                    rank_label = "RECOMMENDED VERSION"
                elif idx == 1:
                    rank_label = "ALTERNATE RECOMMENDATION"
            self._draft_card(self.scroll.inner, draft, rank_label)

        draft = next((d for d in drafts if d.draft_id == self.selected_id), None)
        self.copy_text.delete("1.0", "end")
        if not draft:
            self.detail_var.set("No drafts generated yet. Import media first.")
            self.detail_strip.render([], {})
            self.preview_panel.render(None, {}, self.controller.project)
            self.hero_preview.render(None, {}, self.controller.project)
            self._render_copy_preview_panel(None)
            self.recommendation_reason_var.set("Add media to generate a recommendation.")
            return

        recommended = self.controller.export_candidate_draft() or draft
        self.recommendation_title_var.set(f"We picked {recommended.name} because…")
        self.recommendation_reason_var.set(f"{recommended.rationale}\n\nRecommended bundle: {recommended.recommended_bundle} • {int(recommended.confidence_score * 100)}% confidence")
        asset_map = {asset.asset_id: asset for asset in self.controller.project.assets}

        # ── Populate HTC strip with live project text OR draft's first option ──
        p = self.controller.project
        hook_display  = p.hook_text  or (recommended.hook_options[0]  if recommended.hook_options  else "—")
        title_display = p.title_text or (recommended.title_options[0] if recommended.title_options else "—")
        cta_display   = p.cta_text   or (recommended.cta_options[0]   if recommended.cta_options   else "—")
        # Also write back to project so the preview overlay picks it up
        if not p.hook_text  and hook_display  != "—": p.hook_text  = hook_display
        if not p.title_text and title_display != "—": p.title_text = title_display
        if not p.cta_text   and cta_display   != "—": p.cta_text   = cta_display
        try:
            self._htc_hook_var.set(hook_display)
            self._htc_title_var.set(title_display)
            self._htc_cta_var.set(cta_display)
        except Exception:
            pass

        self.hero_preview.render(recommended, asset_map, self.controller.project)
        self._render_copy_preview_panel(draft)

        self.detail_var.set(
            f"{draft.name}\n\nWhy this was chosen: {draft.rationale}\n\nEstimated runtime: {draft.runtime_estimate:.1f}s\nRecommended bundle: {draft.recommended_bundle}\nLive preview platform: {self.controller.project.preview_platform_variant} • pacing: {self.controller.project.preview_caption_emphasis}"
        )
        self.detail_strip.render(draft.storyboard_cards, asset_map)
        self.preview_panel.render(draft, asset_map, self.controller.project)
        lines = [
            "Hook options",
            *[f"- {line}" for line in draft.hook_options],
            "",
            "Title options",
            *[f"- {line}" for line in draft.title_options],
            "",
            "CTA options",
            *[f"- {line}" for line in draft.cta_options],
        ]
        self.copy_text.insert("1.0", "\n".join(lines))


class QuickRefineScreen(BaseScreen):
    def __init__(self, parent, controller: AppController):
        super().__init__(parent, controller)
        self.preview_candidate_id: str = ""
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text="Polish your post — this is where you fine-tune", style="ED.Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(self, text="Swap clips if needed, set your caption timing, and tweak your text. When it looks right, hit Looks Good.", style="ED.Subhead.TLabel", wraplength=980).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 12))

        left = ttk.LabelFrame(self, text="Swap Clips", padding=10)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(5, weight=1)

        self.story_strip = MiniStoryboardStrip(left, select_callback=self._select_card, reorder_callback=self._reorder_cards, height=150)
        self.story_strip.grid(row=0, column=0, sticky="ew")
        self.slot_buttons = ttk.Frame(left)
        self.slot_buttons.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        self.slot_summary_var = tk.StringVar(value="Choose a slot to see visual replacements.")
        ttk.Label(left, textvariable=self.slot_summary_var, wraplength=760, justify="left").grid(row=2, column=0, sticky="w", pady=(0, 8))
        self.simple_refine_hint_var = tk.StringVar(value="")
        self.simple_refine_hint = ttk.Label(left, textvariable=self.simple_refine_hint_var, foreground="#666666", wraplength=760, justify="left")
        self.simple_refine_hint.grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.advanced_preview_controls = ttk.Frame(left)
        preview_controls = self.advanced_preview_controls
        preview_controls.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        preview_controls.columnconfigure(9, weight=1)
        self.compare_mode_var = tk.StringVar(value="split-screen")
        self.preview_canvas_var = tk.StringVar(value=self.controller.project.preview_canvas_family)
        self.preview_platform_var = tk.StringVar(value=self.controller.project.preview_platform_variant)
        self.preview_caption_style_var = tk.StringVar(value=self.controller.project.preview_caption_style)
        self.preview_caption_position_var = tk.StringVar(value=self.controller.project.preview_caption_position)
        self.preview_caption_emphasis_var = tk.StringVar(value=self.controller.project.preview_caption_emphasis)
        ttk.Label(preview_controls, text="Compare mode").grid(row=0, column=0, sticky="w")
        self.compare_split_btn = ttk.Radiobutton(preview_controls, text="Split-screen", value="split-screen", variable=self.compare_mode_var, command=self._on_compare_mode_changed)
        self.compare_split_btn.grid(row=0, column=1, sticky="w", padx=(8, 6))
        self.compare_seq_btn = ttk.Radiobutton(preview_controls, text="Sequential", value="sequential", variable=self.compare_mode_var, command=self._on_compare_mode_changed)
        self.compare_seq_btn.grid(row=0, column=2, sticky="w", padx=(0, 12))
        ttk.Label(preview_controls, text="Canvas preview").grid(row=0, column=3, sticky="w")
        self.preview_canvas_box = ttk.Combobox(preview_controls, textvariable=self.preview_canvas_var, values=list(CANVAS_FAMILIES.keys()), state="readonly", width=8)
        self.preview_canvas_box.grid(row=0, column=4, sticky="w", padx=(8, 0))
        self.preview_canvas_box.bind("<<ComboboxSelected>>", lambda e: self._on_preview_canvas_changed())
        ttk.Label(preview_controls, text="Platform safe zone").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.preview_platform_box = ttk.Combobox(preview_controls, textvariable=self.preview_platform_var, values=PLATFORM_VARIANTS, state="readonly", width=14)
        self.preview_platform_box.grid(row=1, column=1, columnspan=2, sticky="w", padx=(8, 6), pady=(6, 0))
        self.preview_platform_box.bind("<<ComboboxSelected>>", lambda e: self._on_preview_platform_changed())
        ttk.Label(preview_controls, text="Caption style").grid(row=1, column=3, sticky="w", pady=(6, 0))
        self.preview_caption_style_box = ttk.Combobox(preview_controls, textvariable=self.preview_caption_style_var, values=list(CAPTION_STYLE_PRESETS.keys()), state="readonly", width=20)
        self.preview_caption_style_box.grid(row=1, column=4, sticky="w", padx=(8, 6), pady=(6, 0))
        self.preview_caption_style_box.bind("<<ComboboxSelected>>", lambda e: self._on_preview_caption_style_changed())
        ttk.Label(preview_controls, text="Caption position").grid(row=1, column=5, sticky="w", pady=(6, 0))
        self.preview_caption_position_box = ttk.Combobox(preview_controls, textvariable=self.preview_caption_position_var, values=CAPTION_POSITION_PRESETS, state="readonly", width=16)
        self.preview_caption_position_box.grid(row=1, column=6, sticky="w", padx=(8, 6), pady=(6, 0))
        self.preview_caption_position_box.bind("<<ComboboxSelected>>", lambda e: self._on_preview_caption_position_changed())
        ttk.Label(preview_controls, text="Text size").grid(row=1, column=7, sticky="w", pady=(6, 0))
        self.preview_caption_emphasis_box = ttk.Combobox(preview_controls, textvariable=self.preview_caption_emphasis_var, values=list(CAPTION_EMPHASIS_PRESETS.keys()), state="readonly", width=12)
        self.preview_caption_emphasis_box.grid(row=1, column=8, sticky="w", padx=(8, 0), pady=(6, 0))
        self.preview_caption_emphasis_box.bind("<<ComboboxSelected>>", lambda e: self._on_preview_caption_emphasis_changed())
        self.comparison_preview = ComparisonPreviewPanel(left)
        self.comparison_preview.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.candidate_gallery = ReplacementCandidateGallery(left, replace_callback=self._replace_with_asset, preview_callback=self._preview_candidate, height=360)
        self.candidate_gallery.grid(row=5, column=0, sticky="nsew")

        # ── Right panel — scrollable so all controls are reachable ──────
        right_outer = ttk.LabelFrame(self, text="Text, Captions & Card Controls", padding=4)
        right_outer.grid(row=2, column=1, sticky="nsew")
        right_outer.columnconfigure(0, weight=1)
        right_outer.rowconfigure(0, weight=1)
        right_scroll = ScrollFrame(right_outer, orient="vertical", height=700)
        right_scroll.grid(row=0, column=0, sticky="nsew")
        right = right_scroll.inner
        right.columnconfigure(1, weight=1)

        self.hook_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.cta_var = tk.StringVar()
        self.caption_mode_var = tk.StringVar()
        self.card_role_var = tk.StringVar(value="support")
        self.card_duration_var = tk.DoubleVar(value=0.0)
        self.card_mute_var = tk.BooleanVar(value=False)
        self.card_crop_x_var = tk.DoubleVar(value=0.5)
        self.card_crop_y_var = tk.DoubleVar(value=0.5)

        # ── Copy section ──────────────────────────────────────────────
        copy_hdr = tk.Frame(right, bg=ED["red"], padx=10, pady=5)
        copy_hdr.grid(row=0, column=0, columnspan=3, sticky="ew")
        tk.Label(copy_hdr, text="COPY — Hook, Title & CTA",
                 bg=ED["red"], fg="#ffffff", font=("Arial", 8, "bold")).pack(side="left")

        def _field_row(row, label, var, tip, is_combo=False, combo_vals=None, cmd=None):
            tk.Label(right, text=label, bg=ED["bg_root"], fg=ED["txt_primary"],
                     font=("Arial", 9, "bold")).grid(row=row, column=0, sticky="w", pady=(6, 0))
            if is_combo:
                cb = ttk.Combobox(right, textvariable=var, values=combo_vals or [], width=22)
                cb.grid(row=row, column=1, sticky="ew", padx=(4, 0), pady=(6, 0))
            else:
                e = tk.Entry(right, textvariable=var,
                             bg=ED["bg_input"], fg=ED["txt_primary"],
                             insertbackground=ED["txt_primary"],
                             relief="flat", bd=0, font=("Arial", 10),
                             highlightthickness=1,
                             highlightbackground=ED["border"],
                             highlightcolor=ED["red"])
                e.grid(row=row, column=1, sticky="ew", padx=(4, 0), pady=(6, 0))
                e.bind("<Return>", lambda e, c=cmd: c() if c else None)
            if cmd:
                self._ed_btn(right, "Apply", cmd, primary=True, small=True).grid(
                    row=row, column=2, padx=(6, 0), pady=(6, 0))
            tk.Label(right, text=f"  ↳ {tip}", bg=ED["bg_root"], fg=ED["txt_dim"],
                     font=("Arial", 7, "italic")).grid(
                         row=row+1, column=1, columnspan=2, sticky="w", pady=(0, 0))

        _field_row(1,  "Hook",  self.hook_var,
                   "First words seen/heard. Must hook in under 2 seconds.",
                   cmd=lambda: self.controller.choose_copy("hook", self.hook_var.get()))
        _field_row(3,  "Title", self.title_var,
                   "Supporting headline — what this content is really about.",
                   cmd=lambda: self.controller.choose_copy("title", self.title_var.get()))
        _field_row(5,  "CTA",   self.cta_var,
                   "Call to action — one clear next step for the viewer.",
                   is_combo=True, combo_vals=FUNNEL_CTAS,
                   cmd=lambda: self.controller.choose_copy("cta", self.cta_var.get()))

        ttk.Separator(right).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        # ── Caption Text Timing — NEW ─────────────────────────────────
        cap_hdr = tk.Frame(right, bg=ED["gold"], padx=10, pady=5)
        cap_hdr.grid(row=8, column=0, columnspan=3, sticky="ew")
        tk.Label(cap_hdr, text="CAPTION TIMING — When text appears",
                 bg=ED["gold"], fg="#000000", font=("Arial", 8, "bold")).pack(side="left")
        tk.Label(cap_hdr,
                 text="  Set text and the exact second it appears on each clip.",
                 bg=ED["gold"], fg="#3a2a00", font=("Arial", 7)).pack(side="left")

        # Caption events list
        tk.Label(right,
                 text="Add a timed text overlay to the selected clip:",
                 bg=ED["bg_root"], fg=ED["txt_secondary"],
                 font=("Arial", 9)).grid(row=9, column=0, columnspan=3, sticky="w", pady=(6, 2))

        evt_frame = tk.Frame(right, bg=ED["bg_card"],
                             highlightbackground=ED["border"], highlightthickness=1)
        evt_frame.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        evt_frame.columnconfigure(1, weight=1)

        tk.Label(evt_frame, text="Text:", bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 9)).grid(row=0, column=0, sticky="w", padx=(8, 4), pady=(8, 0))
        self.caption_evt_text_var = tk.StringVar(value="")
        tk.Entry(evt_frame, textvariable=self.caption_evt_text_var,
                 bg=ED["bg_input"], fg=ED["txt_primary"],
                 insertbackground=ED["txt_primary"],
                 relief="flat", bd=0, font=("Arial", 10),
                 highlightthickness=1,
                 highlightbackground=ED["border"],
                 highlightcolor=ED["red"]).grid(
                     row=0, column=1, columnspan=3, sticky="ew", padx=(0, 8), pady=(8, 0))

        tk.Label(evt_frame, text="Appears at (sec):", bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 9)).grid(row=1, column=0, sticky="w", padx=(8, 4), pady=(4, 0))
        self.caption_evt_start_var = tk.DoubleVar(value=0.0)
        tk.Spinbox(evt_frame, from_=0.0, to=120.0, increment=0.5,
                   textvariable=self.caption_evt_start_var,
                   bg=ED["bg_input"], fg=ED["txt_primary"],
                   buttonbackground=ED["bg_card"],
                   insertbackground=ED["txt_primary"],
                   readonlybackground=ED["bg_input"],
                   selectforeground=ED["txt_primary"],
                   selectbackground=ED["selected"],
                   relief="flat", bd=1,
                   highlightbackground=ED["border"],
                   highlightthickness=1,
                   font=("Arial", 10), width=7).grid(
                       row=1, column=1, sticky="w", padx=(0, 8), pady=(4, 0))
        tk.Label(evt_frame, text="Until (sec, 0=end):", bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 9)).grid(row=1, column=2, sticky="w", padx=(8, 4), pady=(4, 0))
        self.caption_evt_end_var = tk.DoubleVar(value=0.0)
        tk.Spinbox(evt_frame, from_=0.0, to=120.0, increment=0.5,
                   textvariable=self.caption_evt_end_var,
                   bg=ED["bg_input"], fg=ED["txt_primary"],
                   buttonbackground=ED["bg_card"],
                   insertbackground=ED["txt_primary"],
                   readonlybackground=ED["bg_input"],
                   selectforeground=ED["txt_primary"],
                   selectbackground=ED["selected"],
                   relief="flat", bd=1,
                   highlightbackground=ED["border"],
                   highlightthickness=1,
                   font=("Arial", 10), width=7).grid(
                       row=1, column=3, sticky="w", padx=(0, 8), pady=(4, 0))

        tk.Label(evt_frame, text="Style:", bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 9)).grid(row=2, column=0, sticky="w", padx=(8, 4), pady=(4, 0))
        self.caption_evt_style_var = tk.StringVar(value=list(CAPTION_STYLE_PRESETS.keys())[0])
        ttk.Combobox(evt_frame, textvariable=self.caption_evt_style_var,
                     values=list(CAPTION_STYLE_PRESETS.keys()),
                     state="readonly", width=18).grid(
                         row=2, column=1, sticky="w", padx=(0, 4), pady=(4, 0))
        tk.Label(evt_frame, text="Position:", bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 9)).grid(row=2, column=2, sticky="w", padx=(8, 4), pady=(4, 0))
        self.caption_evt_pos_var = tk.StringVar(value="Bottom Center")
        ttk.Combobox(evt_frame, textvariable=self.caption_evt_pos_var,
                     values=CAPTION_POSITION_PRESETS,
                     state="readonly", width=14).grid(
                         row=2, column=3, sticky="w", padx=(0, 8), pady=(4, 0))

        evt_btn_row = tk.Frame(evt_frame, bg=ED["bg_card"])
        evt_btn_row.grid(row=3, column=0, columnspan=4, sticky="w", padx=8, pady=(6, 8))
        self._ed_btn(evt_btn_row, "+ Add Caption Event",
                     self._add_caption_event, primary=True, small=True).pack(side="left", padx=(0, 8))
        self._ed_btn(evt_btn_row, "Clear All Events",
                     self._clear_caption_events, small=True).pack(side="left")

        # Events list display
        self._caption_events_frame = tk.Frame(right, bg=ED["bg_root"])
        self._caption_events_frame.grid(row=11, column=0, columnspan=3, sticky="ew")
        self._caption_events_frame.columnconfigure(0, weight=1)

        ttk.Separator(right).grid(row=12, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        # ── Font & Visual Styling ─────────────────────────────────────
        font_hdr = tk.Frame(right, bg=ED["blue"], padx=10, pady=5)
        font_hdr.grid(row=13, column=0, columnspan=3, sticky="ew")
        tk.Label(font_hdr, text="FONT & VISUAL STYLE",
                 bg=ED["blue"], fg="#ffffff", font=("Arial", 8, "bold")).pack(side="left")

        # Font family
        tk.Label(right, text="Font family", bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold")).grid(row=14, column=0, sticky="w", pady=(8, 0))
        self.font_family_var = tk.StringVar(value="Default")
        ttk.Combobox(right, textvariable=self.font_family_var,
                     values=CAPTION_FONT_FAMILY_LABELS,
                     state="readonly", width=16).grid(
                         row=14, column=1, sticky="ew", padx=(4, 0), pady=(8, 0))
        tk.Label(right, text="  ↳ Clean / Bold / Condensed / Thin affect text weight",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(row=15, column=1, columnspan=2, sticky="w")

        # Caption style
        tk.Label(right, text="Caption style", bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold")).grid(row=16, column=0, sticky="w", pady=(6, 0))
        self.caption_mode_var2 = tk.StringVar(value=list(CAPTION_STYLE_PRESETS.keys())[0])
        ttk.Combobox(right, textvariable=self.caption_mode_var2,
                     values=list(CAPTION_STYLE_PRESETS.keys()),
                     state="readonly", width=20).grid(
                         row=16, column=1, sticky="ew", padx=(4, 0), pady=(6, 0))
        tk.Label(right, text="  ↳ Lower Third = subtle. Bold Box = punchy. Heavy Outline = high contrast.",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(row=17, column=1, columnspan=2, sticky="w")

        # Caption size
        tk.Label(right, text="Text size", bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold")).grid(row=18, column=0, sticky="w", pady=(6, 0))
        self.caption_emphasis_var2 = tk.StringVar(value="Standard")
        size_row = tk.Frame(right, bg=ED["bg_root"])
        size_row.grid(row=18, column=1, sticky="w", padx=(4, 0), pady=(6, 0))
        for sz in ["Subtle", "Standard", "Punchy", "Trailer"]:
            tk.Radiobutton(size_row, text=sz,
                           variable=self.caption_emphasis_var2, value=sz,
                           bg=ED["bg_root"], fg=ED["txt_secondary"],
                           selectcolor=ED["red"],
                           activebackground=ED["bg_root"],
                           font=("Arial", 9)).pack(side="left", padx=(0, 8))
        tk.Label(right, text="  ↳ Subtle=14pt  Standard=18pt  Punchy=22pt  Trailer=26pt",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(row=19, column=1, columnspan=2, sticky="w")

        # Reference accent color
        self._ref_accent_swatch = tk.Frame(right, bg=ED["red"], width=18, height=18)
        tk.Label(right, text="Ref. accent color", bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold")).grid(row=20, column=0, sticky="w", pady=(6, 0))
        self._ref_accent_swatch.grid(row=20, column=1, sticky="w", padx=(4, 0), pady=(6, 0))
        self._ed_btn(right, "Apply to Caption",
                     self._apply_reference_accent, small=True).grid(
                         row=20, column=2, padx=(6, 0), pady=(6, 0))
        tk.Label(right, text="  ↳ Applies the dominant color from your reference image to caption accents.",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(row=21, column=1, columnspan=2, sticky="w")

        ttk.Separator(right).grid(row=22, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        # ── Position & Frame Placement ────────────────────────────────
        pos_hdr = tk.Frame(right, bg=ED["bg_card"], padx=10, pady=5,
                           highlightbackground=ED["border"], highlightthickness=1)
        pos_hdr.grid(row=23, column=0, columnspan=3, sticky="ew")
        tk.Label(pos_hdr, text="POSITION — Where text sits in the frame",
                 bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 8, "bold")).pack(side="left")

        tk.Label(right, text="Vertical position", bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold")).grid(row=24, column=0, sticky="w", pady=(8, 0))
        self.caption_pos_var2 = tk.StringVar(value="Bottom Center")
        ttk.Combobox(right, textvariable=self.caption_pos_var2,
                     values=CAPTION_POSITION_PRESETS,
                     state="readonly", width=16).grid(
                         row=24, column=1, sticky="ew", padx=(4, 0), pady=(8, 0))
        tk.Label(right, text="  ↳ Bottom: safe from Reels UI. Mid: high-impact. Top: danger zone on Stories.",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(row=25, column=1, columnspan=2, sticky="w")

        # Platform safe zone
        tk.Label(right, text="Platform", bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold")).grid(row=26, column=0, sticky="w", pady=(6, 0))
        from tkinter import ttk as _ttk
        self.platform_var2 = tk.StringVar(value="Auto")
        self.platform_combo2 = ttk.Combobox(right, textvariable=self.platform_var2,
                                             values=PLATFORM_VARIANTS,
                                             state="readonly", width=16)
        self.platform_combo2.grid(row=26, column=1, sticky="ew", padx=(4, 0), pady=(6, 0))
        self.platform_combo2.bind("<<ComboboxSelected>>", lambda e: self._on_platform2_changed())
        self._platform_safe_note = tk.StringVar(value="  ↳ No safe zone applied.")
        tk.Label(right, textvariable=self._platform_safe_note,
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic"), wraplength=340).grid(
                     row=27, column=1, columnspan=2, sticky="w")

        self._ed_btn(right, "Apply All Style Settings",
                     self._apply_all_style, primary=True).grid(
                         row=28, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        ttk.Separator(right).grid(row=29, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        # ── Card controls (advanced) ──────────────────────────────────
        card_hdr = tk.Frame(right, bg=ED["bg_card"], padx=10, pady=5)
        card_hdr.grid(row=30, column=0, columnspan=3, sticky="ew")
        tk.Label(card_hdr, text="CLIP CONTROLS — Duration, Crop & Role",
                 bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 8, "bold")).pack(side="left")

        self.simple_card_hint_var = tk.StringVar(value="")
        self.simple_card_hint = ttk.Label(right, textvariable=self.simple_card_hint_var,
                                           foreground="#666666", wraplength=420, justify="left")
        self.simple_card_hint.grid(row=31, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(right, text="Clip role").grid(row=32, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(right, textvariable=self.card_role_var,
                     values=["hook", "support", "proof", "cta"],
                     state="readonly").grid(row=32, column=1, sticky="ew", pady=(8, 0))
        tk.Label(right, text="  ↳ Hook=opener  Proof=result  CTA=close  Support=filler",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(row=33, column=1, columnspan=2, sticky="w")
        ttk.Label(right, text="Duration (sec)").grid(row=34, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(right, textvariable=self.card_duration_var).grid(
            row=34, column=1, sticky="ew", pady=(6, 0))
        tk.Label(right, text="  ↳ 0 = use clip's natural length. Override for precise timing.",
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(row=35, column=1, columnspan=2, sticky="w")
        ttk.Checkbutton(right, text="Mute clip audio", variable=self.card_mute_var).grid(
            row=36, column=1, sticky="w", pady=(6, 0))
        ttk.Label(right, text="Crop X (left↔right)").grid(row=37, column=0, sticky="w", pady=(6, 0))
        ttk.Scale(right, from_=0.0, to=1.0, variable=self.card_crop_x_var,
                  orient="horizontal").grid(row=37, column=1, sticky="ew", pady=(6, 0))
        ttk.Label(right, text="Crop Y (top↕bottom)").grid(row=38, column=0, sticky="w", pady=(6, 0))
        ttk.Scale(right, from_=0.0, to=1.0, variable=self.card_crop_y_var,
                  orient="horizontal").grid(row=38, column=1, sticky="ew", pady=(6, 0))
        self._ed_btn(right, "Save Clip Settings", self._save_card_controls,
                     primary=True, small=True).grid(
                         row=39, column=1, sticky="e", pady=(10, 0))

        ttk.Separator(right).grid(row=40, column=0, columnspan=3, sticky="ew", pady=(12, 6))

        # ── LOOKS GOOD (simple) + copy suggestions (advanced) ─────────
        self.simple_refine_hint_var = tk.StringVar(value="")
        self.simple_refine_hint = ttk.Label(right, textvariable=self.simple_refine_hint_var,
                                             foreground="#666666", wraplength=420, justify="left")
        self.simple_refine_hint.grid(row=41, column=0, columnspan=3, sticky="w")

        self.simple_mode_refine_box = ttk.Frame(right)
        self.simple_mode_refine_box.grid(row=42, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Label(self.simple_mode_refine_box,
                  text="Simple Mode keeps this step focused. Add caption timing above, "
                       "then use Looks Good to export.",
                  foreground="#666666", wraplength=420, justify="left").pack(anchor="w", pady=(0, 8))
        self.simple_mode_done_btn = tk.Button(
            self.simple_mode_refine_box, text="✓  LOOKS GOOD — READY TO EXPORT",
            command=self.controller.looks_good_simple,
            font=("Arial", 13, "bold"),
            bg=ED["red"], fg="#ffffff",
            activebackground=ED["red_hover"], activeforeground="#ffffff",
            padx=18, pady=10, relief="flat", bd=0, cursor="hand2")
        self.simple_mode_done_btn.pack(fill="x")

        ttk.Label(right, text="Visual copy suggestions",
                  font=("Arial", 11, "bold")).grid(row=43, column=0, columnspan=3,
                                                    sticky="w", pady=(14, 6))
        self.copy_suggestion_panel = CopySuggestionPanel(right,
                                                          apply_callback=self.controller.choose_copy)
        self.copy_suggestion_panel.grid(row=44, column=0, columnspan=3, sticky="nsew")

        self._right_panel = right
        self._advanced_card_rows = set(range(30, 40))
        self._simple_hidden_rows = {43, 44}

    def _add_caption_event(self) -> None:
        """Add a CaptionEvent to the currently selected storyboard card."""
        p = self.controller.project
        idx = getattr(p, "selected_storyboard_index", -1)
        if not p.selected_storyboard or idx < 0 or idx >= len(p.selected_storyboard):
            self.controller.app.set_status("Select a clip in the strip above first.")
            return
        card = p.selected_storyboard[idx]
        text = self.caption_evt_text_var.get().strip()
        if not text:
            self.controller.app.set_status("Enter caption text before adding.")
            return
        evt = CaptionEvent(
            text=text,
            start_sec=float(self.caption_evt_start_var.get()),
            end_sec=float(self.caption_evt_end_var.get()),
            position=self.caption_evt_pos_var.get(),
            style=self.caption_evt_style_var.get(),
            emphasis=self.caption_emphasis_var2.get() if hasattr(self, "caption_emphasis_var2") else "Standard",
            font_family=self.font_family_var.get() if hasattr(self, "font_family_var") else "Default",
        )
        card.caption_events.append(evt)
        self.caption_evt_text_var.set("")
        p.automation_notes.append(
            f"Caption event added to clip {idx+1}: '{text[:40]}' at {evt.start_sec:.1f}s–"
            f"{'end' if evt.end_sec == 0 else f'{evt.end_sec:.1f}s'} [{evt.position}]")
        self.controller.app.set_status(f"Caption event added: '{text[:30]}…' at {evt.start_sec:.1f}s")
        self.refresh()

    def _clear_caption_events(self) -> None:
        p = self.controller.project
        idx = getattr(p, "selected_storyboard_index", -1)
        if not p.selected_storyboard or idx < 0 or idx >= len(p.selected_storyboard):
            return
        p.selected_storyboard[idx].caption_events.clear()
        p.automation_notes.append(f"All caption events cleared from clip {idx+1}.")
        self.refresh()

    def _apply_reference_accent(self) -> None:
        """Apply the extracted reference accent color to the caption style."""
        accent = getattr(self.controller.project, "reference_accent_color", "")
        if not accent:
            self.controller.app.set_status("No reference image added yet — add one on Add Media.")
            return
        # Convert hex to RGBA tuple and patch the first caption style
        try:
            h = accent.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            for preset in CAPTION_STYLE_PRESETS.values():
                preset["custom_accent"] = (r, g, b, 255)
            self.controller.project.automation_notes.append(
                f"Reference accent color {accent} applied to caption styles.")
            self.controller.app.set_status(
                f"Accent color {accent} from reference applied to captions.")
            self.controller.app.refresh_all_screens()
        except Exception as exc:
            self.controller.app.set_status(f"Could not apply accent: {exc}")

    def _apply_all_style(self) -> None:
        """Write font family, style, emphasis, position and platform to the project."""
        p = self.controller.project
        if hasattr(self, "caption_mode_var2"):
            p.preview_caption_style = self.caption_mode_var2.get()
        if hasattr(self, "caption_emphasis_var2"):
            p.preview_caption_emphasis = self.caption_emphasis_var2.get()
        if hasattr(self, "caption_pos_var2"):
            p.preview_caption_position = self.caption_pos_var2.get()
        if hasattr(self, "platform_var2"):
            p.preview_platform_variant = self.platform_var2.get()
        if hasattr(self, "font_family_var"):
            # Apply per-card font family to all selected storyboard cards
            idx = getattr(p, "selected_storyboard_index", -1)
            if p.selected_storyboard and idx >= 0:
                p.selected_storyboard[idx].caption_font_family = self.font_family_var.get()
        p.automation_notes.append("Caption style, font, size, position and platform updated.")
        self.controller.app.set_status("Style settings applied.")
        self.controller.app.refresh_all_screens()

    def _on_platform2_changed(self) -> None:
        plat = self.platform_var2.get()
        desc = PLATFORM_SAFE_ZONE_DESCRIPTIONS.get(plat, "")
        if hasattr(self, "_platform_safe_note"):
            self._platform_safe_note.set(f"  ↳ {desc}" if desc else "")

    def _refresh_caption_events_display(self) -> None:
        """Rebuild the caption events list display for the selected card."""
        frame = self._caption_events_frame
        for child in frame.winfo_children():
            child.destroy()
        p = self.controller.project
        idx = getattr(p, "selected_storyboard_index", -1)
        if not p.selected_storyboard or idx < 0 or idx >= len(p.selected_storyboard):
            return
        card = p.selected_storyboard[idx]
        if not card.caption_events:
            tk.Label(frame, text="No caption events on this clip yet.",
                     bg=ED["bg_root"], fg=ED["txt_dim"],
                     font=("Arial", 8, "italic")).pack(anchor="w")
            return
        for i, evt in enumerate(card.caption_events):
            row_f = tk.Frame(frame, bg=ED["bg_card"],
                             highlightbackground=ED["border"], highlightthickness=1)
            row_f.pack(fill="x", pady=(0, 4))
            row_f.columnconfigure(1, weight=1)
            end_str = "end" if evt.end_sec == 0 else f"{evt.end_sec:.1f}s"
            tk.Label(row_f,
                     text=f"  {evt.start_sec:.1f}s→{end_str}",
                     bg=ED["bg_card"], fg=ED["gold"],
                     font=("Arial", 9, "bold"), width=12).pack(side="left")
            tk.Label(row_f, text=f"{evt.text[:60]}",
                     bg=ED["bg_card"], fg=ED["txt_primary"],
                     font=("Arial", 9)).pack(side="left", padx=(4, 0))
            tk.Label(row_f, text=f"  [{evt.position}]",
                     bg=ED["bg_card"], fg=ED["txt_dim"],
                     font=("Arial", 8)).pack(side="left")

            def _rm(idx=idx, i=i):
                self.controller.project.selected_storyboard[idx].caption_events.pop(i)
                self.refresh()

            tk.Button(row_f, text="✕", command=_rm,
                      bg=ED["bg_card"], fg=ED["txt_dim"],
                      activebackground=ED["red"], activeforeground="#ffffff",
                      font=("Arial", 8), relief="flat", bd=0,
                      padx=4, cursor="hand2").pack(side="right", padx=(0, 6))

    def _apply_mode_visibility(self) -> None:
        if self.controller.advanced_mode_enabled:
            self.advanced_preview_controls.grid()
            self.simple_refine_hint.grid_remove()
            self.simple_card_hint.grid_remove()
            self.simple_mode_refine_box.grid_remove()
        else:
            self.advanced_preview_controls.grid_remove()
            self.simple_refine_hint.grid()
            self.simple_refine_hint_var.set(
                "Simple Mode: add caption timing above, swap clips if needed, then click Looks Good.")
            self.simple_card_hint.grid()
            self.simple_card_hint_var.set(
                "Clip controls (role, crop, mute) are hidden in Simple Mode. "
                "Switch to Advanced Mode to access them.")
            self.simple_mode_refine_box.grid()

    def _select_card(self, index: int) -> None:
        self.controller.project.selected_storyboard_index = index
        self.preview_candidate_id = ""
        self.refresh()

    def _select_role(self, role: str) -> None:
        self.preview_candidate_id = ""
        self.controller.focus_refine_role(role)

    def _done_simple_refine(self) -> None:
        self.controller.looks_good_simple()

    def _reorder_cards(self, from_idx: int, to_idx: int) -> None:
        self.controller.reorder_storyboard_card(from_idx, to_idx)

    def _replace_with_asset(self, asset_id: str) -> None:
        self.controller.apply_storyboard_replacement(asset_id)
        self.preview_candidate_id = ""

    def _preview_candidate(self, asset_id: str) -> None:
        self.preview_candidate_id = asset_id
        self.refresh()

    def _save_card_controls(self) -> None:
        self.controller.save_card_controls(
            self.card_role_var.get(),
            float(self.card_duration_var.get() or 0.0),
            bool(self.card_mute_var.get()),
            float(self.card_crop_x_var.get()),
            float(self.card_crop_y_var.get()),
        )

    def _on_compare_mode_changed(self) -> None:
        self.controller.set_compare_mode(self.compare_mode_var.get())

    def _on_preview_canvas_changed(self) -> None:
        self.controller.set_preview_canvas_family(self.preview_canvas_var.get())

    def _on_preview_platform_changed(self) -> None:
        self.controller.set_preview_platform_variant(self.preview_platform_var.get())

    def _on_preview_caption_style_changed(self) -> None:
        self.controller.set_preview_caption_style(self.preview_caption_style_var.get())

    def _on_preview_caption_position_changed(self) -> None:
        self.controller.set_preview_caption_position(self.preview_caption_position_var.get())

    def _on_preview_caption_emphasis_changed(self) -> None:
        self.controller.set_preview_caption_emphasis(self.preview_caption_emphasis_var.get())


    def _build_slot_buttons(self, storyboard: List[StoryboardCard], asset_map: Dict[str, Asset], selected_index: int) -> None:
        for child in self.slot_buttons.winfo_children():
            child.destroy()
        if not storyboard:
            return
        if not self.controller.advanced_mode_enabled:
            selected_role = storyboard[selected_index].role if 0 <= selected_index < len(storyboard) else "hook"
            actions = [
                ("Swap opener", "hook"),
                ("Swap proof", "proof"),
                ("Swap CTA", "cta"),
            ]
            for idx, (label, role) in enumerate(actions):
                btn = ttk.Button(self.slot_buttons, text=label, command=lambda r=role: self._select_role(r))
                btn.grid(row=0, column=idx, padx=(0, 6), sticky="w")
                if role == selected_role:
                    try:
                        btn.state(["pressed"])
                    except Exception:
                        pass
            done_btn = tk.Button(self.slot_buttons, text="Done", command=self._done_simple_refine, font=("Arial", 11, "bold"), bg="#8b2d2d", fg="#ffffff", activebackground="#a53a3a", activeforeground="#ffffff", padx=12, pady=6)
            done_btn.grid(row=0, column=len(actions), padx=(6, 0), sticky="w")
            return
        for idx, card in enumerate(storyboard):
            asset = asset_map.get(card.asset_id)
            label = f"{card.role.title()} • {asset.title if asset else card.asset_id}"
            style = "Accent.TButton" if idx == selected_index else "TButton"
            ttk.Button(self.slot_buttons, text=label, style=style, command=lambda i=idx: self._select_card(i)).grid(row=0, column=idx, padx=(0, 6), sticky="w")

    def _caption_mock_text(self, card: StoryboardCard) -> str:
        p = self.controller.project
        if card.role == "hook":
            return p.hook_text or p.title_text
        if card.role == "cta":
            return p.cta_text
        if card.role == "proof":
            return p.title_text or p.hook_text
        return p.title_text or p.hook_text or p.cta_text

    def refresh(self) -> None:
        p = self.controller.project
        asset_map = {asset.asset_id: asset for asset in p.assets}
        self.story_strip.render(p.selected_storyboard, asset_map, p.selected_storyboard_index)
        self._build_slot_buttons(p.selected_storyboard, asset_map, p.selected_storyboard_index)
        self.hook_var.set(p.hook_text)
        self.title_var.set(p.title_text)
        self.cta_var.set(p.cta_text)
        self.caption_mode_var.set(p.caption_mode)
        self._apply_mode_visibility()

        draft = p.selected_draft()
        self.copy_suggestion_panel.render(draft, {"hook": p.hook_text, "title": p.title_text, "cta": p.cta_text})

        idx = p.selected_storyboard_index
        if idx < 0 or idx >= len(p.selected_storyboard):
            self.slot_summary_var.set("Choose a storyboard slot to see visual replacements." if self.controller.advanced_mode_enabled else "Simple Mode: choose Swap opener, Swap proof, or Swap CTA.")
            self.preview_canvas_var.set(p.preview_canvas_family)
            self.preview_platform_var.set(p.preview_platform_variant)
            self.preview_caption_style_var.set(p.preview_caption_style)
            self.preview_caption_position_var.set(p.preview_caption_position)
            self.preview_caption_emphasis_var.set(p.preview_caption_emphasis)
            self.compare_split_btn.configure(state="disabled")
            self.compare_seq_btn.configure(state="disabled")
            self.candidate_gallery.render([], "", "support", "")
            self.comparison_preview.render(None, None, "support", canvas_family=p.preview_canvas_family, platform_variant=p.preview_platform_variant, caption_style=p.preview_caption_style, caption_position=p.preview_caption_position, caption_emphasis=p.preview_caption_emphasis)
            return

        card = p.selected_storyboard[idx]
        asset = asset_map.get(card.asset_id)
        asset_name = asset.title if asset else card.asset_id
        if self.controller.advanced_mode_enabled:
            self.slot_summary_var.set(
                f"Selected slot: {card.role.title()} • {asset_name}. Drag on the strip to reorder, click a candidate card to preview it, choose split-screen or sequential when a pair exists, and use the live {p.preview_canvas_family} crop preview before replacing."
            )
        else:
            self.slot_summary_var.set(
                f"Simple Mode is focused on the {card.role.title()} slot right now: {asset_name}. Pick a replacement below or click Looks Good to move straight to export."
            )
        self.card_role_var.set(card.role)
        self.card_duration_var.set(card.duration_override)
        self.card_mute_var.set(card.mute_audio)
        self.card_crop_x_var.set(card.crop_focus_x)
        self.card_crop_y_var.set(card.crop_focus_y)
        self.compare_mode_var.set(card.compare_mode if card.compare_mode in {"split-screen", "sequential"} else "split-screen")
        self.preview_canvas_var.set(p.preview_canvas_family)
        self.preview_platform_var.set(p.preview_platform_variant)
        self.preview_caption_style_var.set(p.preview_caption_style)
        self.preview_caption_position_var.set(p.preview_caption_position)
        self.preview_caption_emphasis_var.set(p.preview_caption_emphasis)

        # Sync new style controls
        try:
            if hasattr(self, "caption_mode_var2"):
                self.caption_mode_var2.set(p.preview_caption_style)
            if hasattr(self, "caption_emphasis_var2"):
                self.caption_emphasis_var2.set(p.preview_caption_emphasis)
            if hasattr(self, "caption_pos_var2"):
                self.caption_pos_var2.set(p.preview_caption_position)
            if hasattr(self, "platform_var2"):
                self.platform_var2.set(p.preview_platform_variant)
                self._on_platform2_changed()
            if hasattr(self, "font_family_var"):
                self.font_family_var.set(card.caption_font_family or "Default")
            # Update reference accent swatch
            accent = getattr(p, "reference_accent_color", "")
            if hasattr(self, "_ref_accent_swatch") and accent:
                try:
                    self._ref_accent_swatch.configure(bg=accent)
                except Exception:
                    pass
        except Exception:
            pass

        # Refresh timed caption events display
        try:
            self._refresh_caption_events_display()
        except Exception:
            pass

        has_pair = bool(card.pair_asset_id and card.role == "proof")
        compare_state = "normal" if has_pair else "disabled"
        self.compare_split_btn.configure(state=compare_state)
        self.compare_seq_btn.configure(state=compare_state)
        if not has_pair:
            self.compare_mode_var.set("split-screen")

        generator = DraftGenerator(p)
        candidates = generator.candidates_for_role(card.role)
        current_id = card.asset_id
        preview_id = self.preview_candidate_id
        if not preview_id:
            first_other = next((candidate.asset_id for candidate, _score in candidates if candidate.asset_id != current_id), current_id)
            preview_id = first_other
            self.preview_candidate_id = preview_id
        matched_candidate_ids = set()
        if asset:
            for pair in p.pair_suggestions:
                if pair.before_asset_id == asset.asset_id:
                    matched_candidate_ids.add(pair.after_asset_id)
                elif pair.after_asset_id == asset.asset_id:
                    matched_candidate_ids.add(pair.before_asset_id)
        self.candidate_gallery.render(candidates, current_id, card.role, preview_id, matched_pair_ids=matched_candidate_ids)
        preview_asset = asset_map.get(preview_id)
        pair_asset = asset_map.get(card.pair_asset_id) if card.pair_asset_id else None
        # Use first caption event text if present, else fall back to project hook
        if card.caption_events:
            caption_text = card.caption_events[0].text
        else:
            caption_text = self._caption_mock_text(card)
        self.comparison_preview.render(
            asset,
            preview_asset,
            card.role,
            pair_asset,
            compare_mode=self.compare_mode_var.get(),
            canvas_family=p.preview_canvas_family,
            current_focus=(card.crop_focus_x, card.crop_focus_y),
            preview_focus=(0.5, 0.5),
            caption_text=caption_text,
            platform_variant=p.preview_platform_variant,
            caption_style=p.preview_caption_style,
            caption_position=p.preview_caption_position,
            caption_emphasis=p.preview_caption_emphasis,
        )


class ExportScreen(BaseScreen):
    def __init__(self, parent, controller: AppController):
        super().__init__(parent, controller)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(11, weight=1)

        # ── Header ────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=ED["bg_root"], pady=12)
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Label(hdr, text="Export Your Final Version",
                 bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 20, "bold"), anchor="w").pack(anchor="w")
        tk.Label(hdr,
                 text="Check the viral scorecard below, review the recommended version, "
                      "then hit EXPORT RECOMMENDED VERSION.",
                 bg=ED["bg_root"], fg=ED["txt_secondary"],
                 font=("Arial", 10), wraplength=1200, justify="left").pack(
                     anchor="w", pady=(4, 0))
        tk.Frame(self, bg=ED["border_hi"], height=1).grid(
            row=1, column=0, sticky="ew", pady=(0, 10))

        # ── Viral Post Scorecard — NEW ────────────────────────────────
        score_outer, score_inner = self._card(self, "VIRAL POST SCORECARD", ED["gold"])
        score_outer.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        score_inner.columnconfigure(0, weight=1)
        score_inner.columnconfigure(1, weight=1)
        score_inner.columnconfigure(2, weight=1)
        score_inner.columnconfigure(3, weight=1)

        tk.Label(score_inner,
                 text="Before you export: confirm each element is working.",
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 9), justify="left").grid(
                     row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        self._score_vars: Dict[str, tk.StringVar] = {}
        self._score_labels: Dict[str, tk.Label] = {}
        scorecard_items = [
            ("hook",      "Hook",        "First 2s grab attention?"),
            ("proof",     "Proof",       "Result is clearly audible?"),
            ("cta",       "CTA",         "Single clear call to action?"),
            ("caption",   "Caption",     "Under 80 chars, pattern in use?"),
            ("runtime",   "Runtime",     "Under 60 seconds?"),
            ("platform",  "Platform",    "Format matches destination?"),
        ]
        for col, (key, label, tip) in enumerate(scorecard_items):
            frame = tk.Frame(score_inner, bg=ED["bg_panel"],
                             highlightbackground=ED["border"], highlightthickness=1)
            grid_row = 1 + col // 4
            grid_col = col % 4
            frame.grid(row=grid_row, column=grid_col,
                       sticky="nsew", padx=4, pady=4)
            tk.Label(frame, text=label,
                     bg=ED["bg_panel"], fg=ED["txt_primary"],
                     font=("Arial", 10, "bold")).pack(padx=8, pady=(8, 2))
            var = tk.StringVar(value="?")
            lbl = tk.Label(frame, textvariable=var,
                           bg=ED["bg_panel"], fg=ED["txt_dim"],
                           font=("Arial", 20, "bold"))
            lbl.pack(padx=8, pady=4)
            tk.Label(frame, text=tip,
                     bg=ED["bg_panel"], fg=ED["txt_dim"],
                     font=("Arial", 7), wraplength=140, justify="center").pack(
                         padx=8, pady=(0, 8))
            self._score_vars[key] = var
            self._score_labels[key] = lbl

        # Recommended timing strip
        timing_row = tk.Frame(score_inner, bg=ED["bg_card"])
        timing_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        tk.Label(timing_row, text="Best time to post →",
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 9, "bold")).pack(side="left", padx=(0, 10))
        self._timing_var = tk.StringVar(value="Select a platform in Quick Refine to see timing.")
        tk.Label(timing_row, textvariable=self._timing_var,
                 bg=ED["bg_card"], fg=ED["gold"],
                 font=("Arial", 9)).pack(side="left")

        # ── How to export ─────────────────────────────────────────────
        self.export_howto_var = tk.StringVar(
            value="1) Confirm the scorecard above is green.  "
                  "2) Click EXPORT RECOMMENDED VERSION.  "
                  "3) Wait for the export-complete popup.  "
                  "4) Your rendered package is in the export folder.")
        howto_outer, howto_inner = self._card(self, "HOW TO EXPORT", ED["bg_panel"])
        howto_outer.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        tk.Label(howto_inner, textvariable=self.export_howto_var,
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 9), wraplength=1180, justify="left").pack(anchor="w")
        self.export_primary_note_var = tk.StringVar(
            value="Main action on this page: click the red EXPORT RECOMMENDED VERSION button.")
        tk.Label(howto_inner, textvariable=self.export_primary_note_var,
                 bg=ED["bg_card"], fg=ED["txt_primary"],
                 font=("Arial", 10, "bold"), wraplength=1180, justify="left").pack(
                     anchor="w", pady=(6, 0))

        recommendation = ttk.LabelFrame(self, text="Winner / Loser Recommendation", padding=10)
        recommendation.grid(row=4, column=0, sticky="ew")
        recommendation.columnconfigure(1, weight=1)
        self.recommendation_var = tk.StringVar(value="Add and refine drafts to generate a recommendation.")
        self.confidence_strip_var = tk.StringVar(value="Confidence scores will appear here.")
        self.preference_reason_var = tk.StringVar(value="Use the buttons below to see why Selected Draft or Export Candidate is the stronger choice.")
        self.loss_reason_var = tk.StringVar(value="The lower-scoring version will show a plain-English loss explanation here.")
        ttk.Label(recommendation, textvariable=self.recommendation_var, font=("Arial", 11, "bold"), wraplength=1180, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(recommendation, textvariable=self.confidence_strip_var, wraplength=1180, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.advanced_reason_buttons = ttk.Frame(recommendation)
        reason_buttons = self.advanced_reason_buttons
        reason_buttons.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Button(reason_buttons, text="Why prefer Selected Draft", command=lambda: self._show_preference_reasons("selected")).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(reason_buttons, text="Why prefer Export Candidate", command=lambda: self._show_preference_reasons("candidate")).grid(row=0, column=1)
        ttk.Label(recommendation, textvariable=self.preference_reason_var, wraplength=1180, justify="left").grid(row=2, column=1, sticky="w", padx=(10, 0))
        ttk.Label(recommendation, textvariable=self.loss_reason_var, wraplength=1180, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.simple_export_hint_var = tk.StringVar(value="")
        self.simple_export_hint = ttk.Label(recommendation, textvariable=self.simple_export_hint_var, wraplength=1180, justify="left", foreground="#666666")
        self.simple_export_hint.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.advanced_weight_frame = ttk.LabelFrame(recommendation, text="Manual Weight Bias", padding=8)
        weight_frame = self.advanced_weight_frame
        weight_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.weight_vars: Dict[str, tk.IntVar] = {}
        for idx, (label_text, key) in enumerate([("Copy", "copy"), ("Proof", "proof"), ("CTA", "cta"), ("Platform", "platform")]):
            ttk.Label(weight_frame, text=label_text).grid(row=0, column=idx * 2, sticky="w", padx=(0 if idx == 0 else 10, 4))
            var = tk.IntVar(value=self.controller.project.export_score_weights.get(key, 3 if key != "platform" else 2))
            self.weight_vars[key] = var
            spin = tk.Spinbox(weight_frame, from_=0, to=5, width=4,
                            textvariable=var,
                            command=lambda k=key, v=var: self._on_weight_change(k, v),
                            bg=ED["bg_input"], fg=ED["txt_primary"],
                            buttonbackground=ED["bg_card"],
                            insertbackground=ED["txt_primary"],
                            readonlybackground=ED["bg_input"],
                            selectforeground=ED["txt_primary"],
                            selectbackground=ED["selected"],
                            relief="flat", bd=1,
                            highlightbackground=ED["border"],
                            highlightthickness=1,
                            font=("Arial", 10))
            spin.grid(row=0, column=idx * 2 + 1, sticky="w")
            spin.bind("<FocusOut>", lambda e, k=key, v=var: self._on_weight_change(k, v))
            spin.bind("<Return>", lambda e, k=key, v=var: self._on_weight_change(k, v))
        ttk.Button(weight_frame, text="Reset Balanced", command=self._reset_weight_bias).grid(row=0, column=8, sticky="e", padx=(12, 0))

        self.advanced_notes_frame = ttk.LabelFrame(recommendation, text="Export Decision Notes", padding=8)
        notes_frame = self.advanced_notes_frame
        notes_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        notes_frame.columnconfigure(0, weight=1)
        self.decision_notes_text = tk.Text(notes_frame, height=4, wrap="word")
        self.decision_notes_text.grid(row=0, column=0, sticky="ew")
        ttk.Button(notes_frame, text="Save Decision Notes", command=self._save_decision_notes).grid(row=1, column=0, sticky="e", pady=(6, 0))

        self.advanced_approval_frame = ttk.LabelFrame(recommendation, text="Final Approval / Lock", padding=8)
        approval_frame = self.advanced_approval_frame
        approval_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        approval_frame.columnconfigure(1, weight=1)
        self.approval_status_var = tk.StringVar(value="No export version is locked yet.")
        ttk.Label(approval_frame, textvariable=self.approval_status_var, wraplength=1180, justify="left").grid(row=0, column=0, columnspan=4, sticky="w")
        self.approve_selected_btn = ttk.Button(approval_frame, text="Approve Selected Draft", command=lambda: self.controller.approve_export_source("selected"))
        self.approve_selected_btn.grid(row=1, column=0, sticky="w", pady=(6, 0), padx=(0, 6))
        self.approve_candidate_btn = ttk.Button(approval_frame, text="Approve Export Candidate", command=lambda: self.controller.approve_export_source("candidate"))
        self.approve_candidate_btn.grid(row=1, column=1, sticky="w", pady=(6, 0), padx=(0, 6))
        self.clear_lock_btn = ttk.Button(approval_frame, text="Clear Lock", command=self.controller.clear_export_approval)
        self.clear_lock_btn.grid(row=1, column=2, sticky="w", pady=(6, 0))

        compare = ttk.Frame(self)
        compare.grid(row=5, column=0, sticky="nsew", pady=(12, 0))
        for c in range(3):
            compare.columnconfigure(c, weight=1)

        self.selected_compare = self._build_compare_card(compare, "Selected Draft", 0, self._promote_selected)
        self.export_compare = self._build_compare_card(compare, "Export Candidate", 1, self._load_export_candidate)
        self.last_compare = self._build_compare_card(compare, "Last Exported Version", 2, None)

        self.compare_frame = ttk.LabelFrame(self, text="Copy Compare", padding=8)
        self.compare_frame.grid(row=6, column=0, sticky="nsew", pady=(12, 0))
        self.compare_frame.columnconfigure(0, weight=1)
        self.copy_compare_text = tk.Text(self.compare_frame, height=8, wrap="word")
        self.copy_compare_text.grid(row=0, column=0, sticky="nsew")

        self.delta_frame = ttk.LabelFrame(self, text="Storyboard Delta Summary", padding=8)
        self.delta_frame.grid(row=7, column=0, sticky="ew", pady=(12, 0))
        self.delta_frame.columnconfigure(0, weight=1)
        self.delta_text = tk.Text(self.delta_frame, height=8, wrap="word")
        self.delta_text.grid(row=0, column=0, sticky="ew")

        self.summary_text = tk.Text(self, height=7, wrap="word")
        self.summary_text.grid(row=8, column=0, sticky="ew", pady=(12, 0))

        self.action_buttons = ttk.Frame(self)
        self.action_buttons.grid(row=9, column=0, sticky="w", pady=(12, 0))
        ttk.Button(self.action_buttons, text="Export Recommended Pack", command=self.controller.export_project).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(self.action_buttons, text="Save Project", command=self.controller.save_project).grid(row=0, column=1)
        self.simple_export_button = tk.Button(
            self, text="EXPORT RECOMMENDED VERSION",
            command=self.controller.export_project,
            font=("Arial", 16, "bold"),
            bg=ED["red"], fg="#ffffff",
            activebackground=ED["red_hover"], activeforeground="#ffffff",
            padx=22, pady=14, bd=0, relief="flat", cursor="hand2")
        self.simple_export_button.grid(row=10, column=0, sticky="ew", pady=(12, 0))

        # ── Export Progress Panel — directly below the button so it's always visible
        exp_prog_frame = tk.Frame(self, bg=ED["bg_card"],
                                  highlightbackground=ED["border"], highlightthickness=1)
        exp_prog_frame.grid(row=11, column=0, sticky="ew", pady=(6, 0))
        exp_prog_frame.columnconfigure(0, weight=1)

        prog_title = tk.Frame(exp_prog_frame, bg=ED["red"], padx=10, pady=5)
        prog_title.grid(row=0, column=0, sticky="ew")
        tk.Label(prog_title, text="EXPORT PROGRESS",
                 bg=ED["red"], fg="#ffffff",
                 font=("Arial", 8, "bold")).pack(side="left")

        prog_body = tk.Frame(exp_prog_frame, bg=ED["bg_card"], padx=10, pady=10)
        prog_body.grid(row=1, column=0, sticky="nsew")
        prog_body.columnconfigure(0, weight=1)
        prog_body.rowconfigure(2, weight=1)

        self._export_status_var = tk.StringVar(value="Waiting for export to start.")
        self._export_status_label = tk.Label(
            prog_body, textvariable=self._export_status_var,
            bg=ED["bg_card"], fg=ED["txt_dim"],
            font=("Arial", 10, "bold"), anchor="w")
        self._export_status_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self._export_progress_var = tk.DoubleVar(value=0.0)
        self._export_progressbar = ttk.Progressbar(
            prog_body, orient="horizontal", mode="determinate",
            variable=self._export_progress_var, maximum=100)
        self._export_progressbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.after(100, self._init_export_bar_style)

        self.log_text = self._tk_text(prog_body, height=6)
        self.log_text.grid(row=2, column=0, sticky="nsew")

    def _build_compare_card(self, parent, title: str, column: int, action_cmd):
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        status_var = tk.StringVar(value="No version available.")
        badges_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=status_var, justify="left", wraplength=320).grid(row=0, column=0, sticky="w")
        bar = tk.Canvas(frame, height=20, highlightthickness=0, bg="#1b1b1b")
        bar.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(frame, textvariable=badges_var, justify="left", wraplength=320).grid(row=2, column=0, sticky="w", pady=(6, 0))
        body = tk.Text(frame, height=17, wrap="word")
        body.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        button = None
        if action_cmd is not None:
            button = ttk.Button(frame, command=action_cmd)
            button.grid(row=4, column=0, sticky="w", pady=(8, 0))
        return {"frame": frame, "status": status_var, "badges": badges_var, "bar": bar, "body": body, "button": button}

    def _copy_score(self, snapshot: ExportVersionSnapshot) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        if snapshot.hook.strip():
            score += 10
            reasons.append("hook present")
            if len(snapshot.hook.strip()) <= 90:
                score += 3
                reasons.append("hook length is tight")
        if snapshot.title.strip():
            score += 9
            reasons.append("title present")
            if len(snapshot.title.strip()) <= 90:
                score += 2
        if snapshot.cta.strip():
            score += 8
            reasons.append("CTA present")
            if snapshot.cta in FUNNEL_CTAS:
                score += 3
                reasons.append("CTA matches funnel language")
        return min(35, score), reasons

    def _structure_score(self, snapshot: ExportVersionSnapshot) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        count = len(snapshot.storyboard_roles)
        if 2 <= count <= 6:
            score += 12
            reasons.append("runtime-friendly structure")
        elif count > 0:
            score += 6
        roles = snapshot.storyboard_roles
        upper_roles = [r.upper() for r in roles]
        if any(r.startswith("HOOK") for r in upper_roles):
            score += 8
            reasons.append("clear opener")
        if any(r.startswith("CTA") for r in upper_roles):
            score += 8
            reasons.append("clear closer")
        if any(r.startswith("PROOF") for r in upper_roles):
            score += 5
            reasons.append("proof present")
        if 8.0 <= snapshot.runtime_estimate <= 28.0:
            score += 2
        return min(35, score), reasons

    def _platform_score(self, snapshot: ExportVersionSnapshot) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        bundle_canvases = PUBLISH_BUNDLES.get(snapshot.bundle, [])
        expected_canvas = resolve_canvas_for_platform_variant(snapshot.platform_variant, bundle_canvases[0] if bundle_canvases else "9x16")
        if snapshot.platform_variant != "Auto":
            score += 8
            reasons.append(f"platform intent is set to {snapshot.platform_variant}")
        else:
            score += 4
        if expected_canvas in bundle_canvases or snapshot.platform_variant == "Auto":
            score += 8
            reasons.append("bundle supports the chosen platform")
        elif bundle_canvases:
            score += 3
        if snapshot.bundle != "Custom":
            score += 4
            reasons.append("bundle stays in a standard export pack")
        return min(20, score), reasons

    def _proof_score(self, snapshot: ExportVersionSnapshot) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        roles = [r.upper() for r in snapshot.storyboard_roles]
        if any("PROOF" in r for r in roles):
            score += 8
            reasons.append("proof role is present")
        if any("COMPARE" in r for r in roles):
            score += 6
            reasons.append("comparison proof is present")
        if len(snapshot.storyboard_titles) >= 3:
            score += 3
            reasons.append("enough room for proof to land")
        if snapshot.runtime_estimate >= 8.0:
            score += 3
        return min(20, score), reasons

    def _cta_strength_score(self, snapshot: ExportVersionSnapshot) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        roles = [r.upper() for r in snapshot.storyboard_roles]
        if any(r.startswith("CTA") for r in roles):
            score += 8
            reasons.append("CTA role is present")
        if roles and roles[-1].startswith("CTA"):
            score += 5
            reasons.append("CTA lands at the close")
        if snapshot.cta.strip():
            score += 4
            reasons.append("CTA copy is present")
        if snapshot.cta in FUNNEL_CTAS:
            score += 3
            reasons.append("CTA uses funnel language")
        return min(20, score), reasons

    def _caption_score(self, snapshot: ExportVersionSnapshot) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        if snapshot.caption_style in CAPTION_STYLE_PRESETS:
            score += 3
            reasons.append("caption style selected")
        if snapshot.caption_position in CAPTION_POSITION_PRESETS:
            score += 2
            reasons.append("caption placement selected")
        if snapshot.caption_emphasis in CAPTION_EMPHASIS_PRESETS:
            score += 3
            reasons.append("caption pacing selected")
        if snapshot.platform_variant in {"Reels", "Stories", "Feed", "Portrait Feed", "Landscape"}:
            score += 2
            reasons.append("caption treatment tied to platform preview")
        return min(10, score), reasons

    def _confidence_breakdown(self, snapshot: Optional[ExportVersionSnapshot]) -> Tuple[int, Dict[str, int], List[str]]:
        if snapshot is None:
            return 0, {"copy": 0, "proof": 0, "cta": 0, "platform": 0, "caption": 0}, []
        copy_score, copy_reasons = self._copy_score(snapshot)
        proof_score, proof_reasons = self._proof_score(snapshot)
        cta_score, cta_reasons = self._cta_strength_score(snapshot)
        platform_score, platform_reasons = self._platform_score(snapshot)
        caption_score, caption_reasons = self._caption_score(snapshot)
        component_pct = {
            "copy": int(round((copy_score / 35.0) * 100)),
            "proof": int(round((proof_score / 20.0) * 100)),
            "cta": int(round((cta_score / 20.0) * 100)),
            "platform": int(round((platform_score / 20.0) * 100)),
            "caption": int(round((caption_score / 10.0) * 100)),
        }
        weights = dict(self.controller.project.export_score_weights)
        weighted_pairs = [
            ("copy", max(0, int(weights.get("copy", 3)))),
            ("proof", max(0, int(weights.get("proof", 3)))),
            ("cta", max(0, int(weights.get("cta", 3)))),
            ("platform", max(0, int(weights.get("platform", 2)))),
            ("caption", 1),
        ]
        denom = sum(weight for _, weight in weighted_pairs) or 1
        total = int(round(sum(component_pct[key] * weight for key, weight in weighted_pairs) / denom))
        reasons = copy_reasons + proof_reasons + cta_reasons + platform_reasons + caption_reasons
        return total, component_pct, reasons

    def _snapshot_lines(self, snapshot: ExportVersionSnapshot, diff_fields: Optional[set] = None) -> List[str]:
        diff_fields = diff_fields or set()
        confidence, breakdown, _ = self._confidence_breakdown(snapshot)
        def mark(label: str, key: str) -> str:
            return f"{label}  [DIFF]" if key in diff_fields else label
        lines = [
            f"Draft: {snapshot.draft_name}",
            f"Final confidence: {confidence}/100",
            f"Breakdown: copy {breakdown['copy']} • proof {breakdown['proof']} • CTA {breakdown['cta']} • platform {breakdown['platform']} • caption {breakdown['caption']}",
            f"Weight bias: copy {self.controller.project.export_score_weights.get('copy', 3)} • proof {self.controller.project.export_score_weights.get('proof', 3)} • CTA {self.controller.project.export_score_weights.get('cta', 3)} • platform {self.controller.project.export_score_weights.get('platform', 2)}",
            f"Runtime: {snapshot.runtime_estimate:.1f}s",
            f"{mark('Bundle', 'bundle')}: {snapshot.bundle}",
            f"{mark('Platform preview', 'platform')}: {snapshot.platform_variant}",
            f"{mark('Caption style', 'caption')}: {snapshot.caption_style}",
            f"{mark('Caption position', 'caption')}: {snapshot.caption_position}",
            f"{mark('Caption emphasis', 'caption')}: {snapshot.caption_emphasis}",
            "",
            f"{mark('Hook', 'hook')}: {snapshot.hook}",
            f"{mark('Title', 'title')}: {snapshot.title}",
            f"{mark('CTA', 'cta')}: {snapshot.cta}",
            "",
            mark('Storyboard roles', 'storyboard'),
            " → ".join(snapshot.storyboard_roles[:6]) if snapshot.storyboard_roles else "No storyboard",
            "",
            mark('Storyboard titles', 'storyboard'),
        ]
        for title in snapshot.storyboard_titles[:6]:
            lines.append(f"- {title}")
        if snapshot.rationale:
            lines.extend(["", mark('Why this version exists', 'rationale'), snapshot.rationale])
        if snapshot.export_path:
            lines.extend(["", f"Export path: {snapshot.export_path}"])
        return lines

    def _confidence_bar_color(self, score: int) -> str:
        if score >= 80:
            return "#4caf50"
        if score >= 60:
            return "#ffb300"
        return "#ef5350"

    def _render_confidence_bar(self, canvas: tk.Canvas, score: int) -> None:
        canvas.delete("all")
        width = max(int(canvas.winfo_width() or 280), 180)
        height = max(int(canvas.winfo_height() or 20), 18)
        canvas.create_rectangle(0, 2, width, height - 2, fill="#2a2a2a", outline="#3a3a3a")
        fill_w = int((max(0, min(100, score)) / 100.0) * width)
        canvas.create_rectangle(0, 2, fill_w, height - 2, fill=self._confidence_bar_color(score), outline="")
        canvas.create_text(width // 2, height // 2, text=f"{score}/100", fill="white")

    def _diff_fields(self, snapshot: Optional[ExportVersionSnapshot], others: List[Optional[ExportVersionSnapshot]]) -> set:
        if snapshot is None:
            return set()
        diff = set()
        valid = [o for o in others if o is not None]
        if not valid:
            return diff
        if any(snapshot.bundle != o.bundle for o in valid):
            diff.add("bundle")
        if any(snapshot.platform_variant != o.platform_variant for o in valid):
            diff.add("platform")
        if any((snapshot.caption_style, snapshot.caption_position, snapshot.caption_emphasis) != (o.caption_style, o.caption_position, o.caption_emphasis) for o in valid):
            diff.add("caption")
        if any(snapshot.hook != o.hook for o in valid):
            diff.add("hook")
        if any(snapshot.title != o.title for o in valid):
            diff.add("title")
        if any(snapshot.cta != o.cta for o in valid):
            diff.add("cta")
        if any((snapshot.storyboard_roles, snapshot.storyboard_titles) != (o.storyboard_roles, o.storyboard_titles) for o in valid):
            diff.add("storyboard")
        if any(snapshot.rationale != o.rationale for o in valid):
            diff.add("rationale")
        return diff

    def _badge_text(self, diff_fields: set) -> str:
        mapping = {
            "bundle": "BUNDLE",
            "platform": "PLATFORM",
            "caption": "CAPTION",
            "hook": "HOOK",
            "title": "TITLE",
            "cta": "CTA",
            "storyboard": "STRUCTURE",
            "rationale": "RATIONALE",
        }
        badges = [f"[{mapping[key]}]" for key in ["bundle", "platform", "caption", "hook", "title", "cta", "storyboard", "rationale"] if key in diff_fields]
        return " ".join(badges) if badges else "[NO MAJOR DIFFS]"

    def _render_compare_card(self, ui: Dict[str, Any], snapshot: Optional[ExportVersionSnapshot], others: List[Optional[ExportVersionSnapshot]], *, empty_message: str, button_text: str = "", button_enabled: bool = False) -> None:
        score = 0
        if snapshot is None:
            status = empty_message
            diff_fields = set()
            ui["badges"].set("")
        else:
            score, _, _ = self._confidence_breakdown(snapshot)
            locked_here = (
                self.controller.project.final_approval_locked
                and self.controller.project.approved_export_snapshot is not None
                and self.controller.project.approved_export_snapshot.source_label == snapshot.source_label
                and self.controller.project.approved_export_snapshot.draft_name == snapshot.draft_name
            )
            status = f"{snapshot.source_label} ready for comparison • confidence {score}/100."
            if locked_here:
                status += " • LOCKED FOR RENDER"
            diff_fields = self._diff_fields(snapshot, others)
            badge_prefix = "LOCKED FOR RENDER • " if locked_here else ""
            ui["badges"].set(badge_prefix + "Field diff badges: " + self._badge_text(diff_fields))
        ui["status"].set(status)
        self._render_confidence_bar(ui["bar"], score)
        ui["body"].configure(state="normal")
        ui["body"].delete("1.0", "end")
        if snapshot is None:
            ui["body"].insert("1.0", empty_message)
        else:
            ui["body"].insert("1.0", "\n".join(self._snapshot_lines(snapshot, diff_fields)))
        ui["body"].configure(state="disabled")
        if ui["button"] is not None:
            ui["button"].configure(text=button_text, state=("normal" if button_enabled else "disabled"))

    def _promote_selected(self) -> None:
        draft_id = self.controller.project.selected_draft_id
        if draft_id:
            self.controller.promote_export_candidate(draft_id)

    def _load_export_candidate(self) -> None:
        draft_id = self.controller.project.export_candidate_draft_id
        if draft_id:
            self.controller.select_draft(draft_id)

    def _on_weight_change(self, key: str, var: tk.IntVar) -> None:
        try:
            value = int(var.get())
        except Exception:
            value = self.controller.project.export_score_weights.get(key, 3 if key != "platform" else 2)
            var.set(value)
            return
        self.controller.set_export_score_weight(key, value)

    def _reset_weight_bias(self) -> None:
        self.controller.reset_export_score_weights()
        for key, var in getattr(self, "weight_vars", {}).items():
            var.set(self.controller.project.export_score_weights.get(key, 3 if key != "platform" else 2))

    def _save_decision_notes(self) -> None:
        note_text = self.decision_notes_text.get("1.0", "end").strip()
        self.controller.save_export_decision_notes(note_text)

    def append_log(self, text: str) -> None:
        """Write a line to the export log and update the progress bar + status label."""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

        # Drive the color progress bar from log message content
        t = text.lower()
        try:
            if any(kw in t for kw in ("error", "failed", "fail")):
                self._set_export_progress_state("error", text)
            elif any(kw in t for kw in ("complete", "done", "success", "wrote", "saved", "exported")):
                self._set_export_progress_state("complete", text)
            elif any(kw in t for kw in ("render", "building", "writing", "encoding",
                                         "composit", "generat", "preparing", "packing")):
                self._set_export_progress_state("processing", text)
                # Advance progress bar incrementally for long render stages
                cur = self._export_progress_var.get()
                if cur < 90:
                    self._export_progress_var.set(min(90, cur + 8))
            else:
                cur = self._export_progress_var.get()
                if cur < 60:
                    self._export_progress_var.set(min(60, cur + 4))
        except Exception:
            pass

    def _init_export_bar_style(self) -> None:
        """Register the export progress bar style once the root window is available."""
        try:
            s = ttk.Style(self.winfo_toplevel())
            s.configure("ED.Export.Horizontal.TProgressbar",
                        troughcolor=ED["bg_input"],
                        background=ED["txt_dim"],
                        bordercolor=ED["bg_input"],
                        lightcolor=ED["txt_dim"],
                        darkcolor=ED["txt_dim"])
            self._export_progressbar.configure(style="ED.Export.Horizontal.TProgressbar")
        except Exception:
            pass

    def _set_export_progress_state(self, state: str, message: str = "") -> None:
        """Update the export progress bar colour and status label."""
        _STATES = {
            "idle":       {"fg": ED["txt_dim"],   "pct": 0,    "bar": ED["txt_dim"],   "label": "Waiting for export to start."},
            "processing": {"fg": ED["blue"],      "pct": None, "bar": ED["blue"],      "label": ""},
            "complete":   {"fg": ED["green"],     "pct": 100,  "bar": ED["green"],     "label": "Export complete."},
            "error":      {"fg": ED["red_lite"],  "pct": None, "bar": ED["red_lite"],  "label": "Export failed — see log below."},
        }
        cfg = _STATES.get(state, _STATES["idle"])
        try:
            bar_color = cfg["bar"]
            s = ttk.Style(self.winfo_toplevel())
            s.configure("ED.Export.Horizontal.TProgressbar",
                        background=bar_color,
                        lightcolor=bar_color,
                        darkcolor=bar_color,
                        troughcolor=ED["bg_input"],
                        bordercolor=ED["bg_input"])
            self._export_progressbar.configure(style="ED.Export.Horizontal.TProgressbar")
            self._export_progressbar.update_idletasks()
        except Exception:
            pass
        label = message.strip() if (message and state == "processing") else cfg["label"]
        if label:
            self._export_status_var.set(label)
        try:
            self._export_status_label.configure(fg=cfg["fg"])
        except Exception:
            pass
        if cfg["pct"] is not None:
            self._export_progress_var.set(cfg["pct"])

    def export_started(self) -> None:
        """Reset progress bar to processing state when export begins."""
        self._export_progress_var.set(5)
        self._set_export_progress_state("processing", "Preparing export package…")
        try:
            self._export_progressbar.update_idletasks()
        except Exception:
            pass
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _copy_compare_lines(self, selected_snapshot: Optional[ExportVersionSnapshot], export_snapshot: Optional[ExportVersionSnapshot], last_snapshot: Optional[ExportVersionSnapshot]) -> List[str]:
        rows = [
            ("Selected Draft", selected_snapshot),
            ("Export Candidate", export_snapshot),
            ("Last Exported", last_snapshot),
        ]
        lines = ["Hook"]
        for label, snap in rows:
            lines.append(f"- {label}: {snap.hook if snap else '—'}")
        lines.extend(["", "Title"])
        for label, snap in rows:
            lines.append(f"- {label}: {snap.title if snap else '—'}")
        lines.extend(["", "CTA"])
        for label, snap in rows:
            lines.append(f"- {label}: {snap.cta if snap else '—'}")
        return lines

    def _storyboard_delta_lines(self, selected_snapshot: Optional[ExportVersionSnapshot], export_snapshot: Optional[ExportVersionSnapshot], last_snapshot: Optional[ExportVersionSnapshot]) -> List[str]:
        lines: List[str] = []
        def compare_pair(name_a: str, a: Optional[ExportVersionSnapshot], name_b: str, b: Optional[ExportVersionSnapshot]):
            if a is None or b is None:
                return
            deltas: List[str] = []
            if (a.storyboard_titles[:1] or [""])[0] != (b.storyboard_titles[:1] or [""])[0]:
                deltas.append("new opener")
            if (a.storyboard_titles[-1:] or [""])[0] != (b.storyboard_titles[-1:] or [""])[0]:
                deltas.append("different CTA closer")
            if a.caption_style != b.caption_style or a.caption_position != b.caption_position or a.caption_emphasis != b.caption_emphasis:
                deltas.append("caption treatment changed")
            if a.bundle != b.bundle:
                deltas.append("bundle changed")
            if a.platform_variant != b.platform_variant:
                deltas.append("platform preview changed")
            if a.storyboard_roles != b.storyboard_roles or a.storyboard_titles != b.storyboard_titles:
                deltas.append("storyboard structure changed")
            if a.hook != b.hook or a.title != b.title or a.cta != b.cta:
                deltas.append("copy changed")
            if not deltas:
                deltas.append("no major changes")
            lines.append(f"{name_a} vs {name_b}: " + ", ".join(deltas))
        compare_pair("Selected Draft", selected_snapshot, "Export Candidate", export_snapshot)
        compare_pair("Export Candidate", export_snapshot, "Last Exported", last_snapshot)
        compare_pair("Selected Draft", selected_snapshot, "Last Exported", last_snapshot)
        return lines or ["Not enough versions are available to calculate deltas yet."]

    def _recommendation_payload(self, selected_snapshot: Optional[ExportVersionSnapshot], export_snapshot: Optional[ExportVersionSnapshot]):
        selected_score, _, selected_reasons = self._confidence_breakdown(selected_snapshot)
        export_score, _, export_reasons = self._confidence_breakdown(export_snapshot)
        if selected_snapshot is None and export_snapshot is None:
            return "No recommendation yet.", "Confidence scores need a selected draft or export candidate.", [], []
        if export_snapshot is None:
            return f"Winner: Selected Draft • Loser: —", f"Selected Draft confidence {selected_score}/100.", selected_reasons[:5], []
        if selected_snapshot is None:
            return f"Winner: Export Candidate • Loser: —", f"Export Candidate confidence {export_score}/100.", [], export_reasons[:5]
        if abs(selected_score - export_score) < 4:
            recommendation = f"Toss-up • Selected Draft {selected_score}/100 vs Export Candidate {export_score}/100"
        elif export_score > selected_score:
            recommendation = f"Winner: Export Candidate • Loser: Selected Draft"
        else:
            recommendation = f"Winner: Selected Draft • Loser: Export Candidate"
        weights = self.controller.project.export_score_weights
        confidence_line = (
            f"Selected Draft {selected_score}/100 • Export Candidate {export_score}/100 • "
            f"Manual bias: copy {weights.get('copy', 3)} • proof {weights.get('proof', 3)} • CTA {weights.get('cta', 3)} • platform {weights.get('platform', 2)}."
        )
        return recommendation, confidence_line, selected_reasons[:6], export_reasons[:6]

    def _show_preference_reasons(self, which: str) -> None:
        selected_snapshot = self.controller.build_selected_export_snapshot()
        export_snapshot = self.controller.build_draft_export_snapshot(self.controller.export_candidate_draft(), "Export Candidate")
        _, _, selected_reasons, export_reasons = self._recommendation_payload(selected_snapshot, export_snapshot)
        reasons = selected_reasons if which == "selected" else export_reasons
        label = "Selected Draft" if which == "selected" else "Export Candidate"
        if not reasons:
            self.preference_reason_var.set(f"{label}: no strong reasons are available yet.")
            return
        self.preference_reason_var.set(f"{label}: " + "; ".join(reasons))

    def _why_this_lost(self, selected_snapshot: Optional[ExportVersionSnapshot], export_snapshot: Optional[ExportVersionSnapshot]) -> str:
        selected_score, selected_breakdown, _ = self._confidence_breakdown(selected_snapshot)
        export_score, export_breakdown, _ = self._confidence_breakdown(export_snapshot)
        if selected_snapshot is None or export_snapshot is None:
            return "Why this lost: a lower-scoring version will appear once both Selected Draft and Export Candidate exist."
        if abs(selected_score - export_score) < 4:
            return "Why this lost: neither version is meaningfully behind — this is effectively a toss-up."
        winner_label = "Export Candidate" if export_score > selected_score else "Selected Draft"
        loser_label = "Selected Draft" if export_score > selected_score else "Export Candidate"
        winner = export_breakdown if export_score > selected_score else selected_breakdown
        loser = selected_breakdown if export_score > selected_score else export_breakdown
        friendly = {
            "copy": "copy strength",
            "proof": "proof delivery",
            "cta": "CTA strength",
            "platform": "platform fit",
            "caption": "caption treatment",
        }
        gaps = []
        for key in ("copy", "proof", "cta", "platform", "caption"):
            gap = winner[key] - loser[key]
            if gap > 0:
                gaps.append((gap, friendly[key]))
        gaps.sort(reverse=True)
        if not gaps:
            return f"Why this lost: {loser_label} trails slightly overall, but without one dominant weakness."
        top = ", ".join(name for _, name in gaps[:2])
        return f"Why this lost: {loser_label} trails {winner_label} mainly on {top}."

    def _refresh_viral_scorecard(self) -> None:
        """Update the 6-item viral scorecard based on current project state."""
        p = self.controller.project

        def _set(key: str, ok) -> None:
            var = self._score_vars.get(key)
            lbl = self._score_labels.get(key)
            if not var or not lbl:
                return
            if ok is True:
                var.set("✓"); lbl.configure(fg=ED["green"])
            elif ok is False:
                var.set("✗"); lbl.configure(fg=ED["red_lite"])
            else:
                var.set("?"); lbl.configure(fg=ED["txt_dim"])

        # Hook — has text and is concise
        hook = (p.hook_text or "").strip()
        _set("hook", (bool(hook) and len(hook) <= 120) if hook else None)

        # Proof — pair suggestion or audio/video assets present
        _set("proof",
             (bool(p.pair_suggestions) or
              any(a.media_type in {"audio","video"} for a in p.assets))
             if p.assets else None)

        # CTA — non-default CTA set
        cta = (p.cta_text or "").strip()
        _set("cta", (bool(cta) and cta != "Start Your Project") if cta else None)

        # Caption — mode is configured
        cap_mode = getattr(p, "caption_mode", "")
        _set("caption", cap_mode not in {"None", ""} if cap_mode else None)

        # Runtime — storyboard totals ≤ 60s
        if p.selected_storyboard:
            asset_map = {a.asset_id: a for a in p.assets}
            total_dur = sum(
                c.effective_duration(asset_map.get(c.asset_id))
                for c in p.selected_storyboard
            )
            _set("runtime", total_dur <= 60.0)
        else:
            _set("runtime", None)

        # Platform — specific platform chosen
        plat = getattr(p, "preview_platform_variant", "Auto")
        _set("platform", plat not in {"Auto", ""} if plat else None)

        # Timing strip
        times = PLATFORM_BEST_TIMES.get(plat, [])
        if times:
            self._timing_var.set(f"{plat}: {' • '.join(times[:2])}")
        else:
            self._timing_var.set("Set a platform in Quick Refine to see best post times.")

    def refresh(self) -> None:
        self._refresh_viral_scorecard()
        if self.controller.advanced_mode_enabled:
            self.simple_export_hint.grid_remove()
            self.simple_export_button.grid_remove()
            self.action_buttons.grid()
            self.advanced_reason_buttons.grid()
            self.advanced_weight_frame.grid()
            self.advanced_notes_frame.grid()
            self.advanced_approval_frame.grid()
            # Show the comparison panels only in advanced mode
            try:
                self.compare_frame.grid()
                self.delta_frame.grid()
                self.summary_text.grid()
            except Exception:
                pass
        else:
            self.simple_export_hint.grid()
            self.simple_export_hint_var.set("Simple Mode keeps the recommendation automatic. Review the winner strip, then click the giant EXPORT RECOMMENDED VERSION button on this page to render the final package.")
            self.simple_export_button.grid()
            self.action_buttons.grid_remove()
            self.advanced_reason_buttons.grid_remove()
            self.advanced_weight_frame.grid_remove()
            self.advanced_notes_frame.grid_remove()
            self.advanced_approval_frame.grid_remove()
            # Hide heavy comparison panels in Simple Mode — keeps button+progress visible
            try:
                self.compare_frame.grid_remove()
                self.delta_frame.grid_remove()
                self.summary_text.grid_remove()
            except Exception:
                pass
        p = self.controller.project
        selected_snapshot = self.controller.build_selected_export_snapshot()
        export_snapshot = self.controller.build_draft_export_snapshot(self.controller.export_candidate_draft(), "Export Candidate")
        last_snapshot = self.controller.get_last_export_snapshot()

        self._render_compare_card(
            self.selected_compare,
            selected_snapshot,
            [export_snapshot, last_snapshot],
            empty_message="No selected draft is loaded in Quick Refine yet.",
            button_text="Promote Selected to Export",
            button_enabled=bool(p.selected_draft_id),
        )
        self._render_compare_card(
            self.export_compare,
            export_snapshot,
            [selected_snapshot, last_snapshot],
            empty_message="No export candidate has been marked yet.",
            button_text="Load Export Candidate",
            button_enabled=bool(p.export_candidate_draft_id),
        )
        self._render_compare_card(
            self.last_compare,
            last_snapshot,
            [selected_snapshot, export_snapshot],
            empty_message="Nothing has been exported yet in this project.",
        )

        recommendation, confidence_line, selected_reasons, export_reasons = self._recommendation_payload(selected_snapshot, export_snapshot)
        self.recommendation_var.set(recommendation)
        self.confidence_strip_var.set(confidence_line)
        if selected_reasons or export_reasons:
            self.preference_reason_var.set("Selected Draft: " + "; ".join(selected_reasons[:3]) + (" • " if export_reasons else "") + ("Export Candidate: " + "; ".join(export_reasons[:3]) if export_reasons else ""))
        else:
            self.preference_reason_var.set("Use the buttons below to see why Selected Draft or Export Candidate is the stronger choice.")
        self.loss_reason_var.set(self._why_this_lost(selected_snapshot, export_snapshot))

        for key, var in self.weight_vars.items():
            target_value = self.controller.project.export_score_weights.get(key, 3 if key != "platform" else 2)
            if var.get() != target_value:
                var.set(target_value)
        if self.focus_get() is not self.decision_notes_text:
            current_notes = self.decision_notes_text.get("1.0", "end").strip()
            if current_notes != self.controller.project.export_decision_notes:
                self.decision_notes_text.delete("1.0", "end")
                self.decision_notes_text.insert("1.0", self.controller.project.export_decision_notes)
        if p.final_approval_locked and p.approved_export_snapshot is not None:
            self.approval_status_var.set(
                f"LOCKED FOR RENDER • {p.approved_export_source}: {p.approved_export_snapshot.draft_name}. "
                f"This frozen version will be exported until you clear the lock."
            )
        else:
            self.approval_status_var.set("No export version is locked yet. Approve Selected Draft or Export Candidate to freeze the final export choice before render.")
        self.approve_selected_btn.configure(state=("normal" if selected_snapshot is not None else "disabled"))
        self.approve_candidate_btn.configure(state=("normal" if export_snapshot is not None else "disabled"))
        self.clear_lock_btn.configure(state=("normal" if p.final_approval_locked else "disabled"))

        self.copy_compare_text.configure(state="normal")
        self.copy_compare_text.delete("1.0", "end")
        self.copy_compare_text.insert("1.0", "\n".join(self._copy_compare_lines(selected_snapshot, export_snapshot, last_snapshot)))
        self.copy_compare_text.configure(state="disabled")

        self.delta_text.configure(state="normal")
        self.delta_text.delete("1.0", "end")
        self.delta_text.insert("1.0", "\n".join(self._storyboard_delta_lines(selected_snapshot, export_snapshot, last_snapshot)))
        self.delta_text.configure(state="disabled")

        if p.final_approval_locked and p.approved_export_snapshot is not None:
            target_name = p.approved_export_snapshot.draft_name
            target_rule = f"Export target is LOCKED to {p.approved_export_source}. Clear the lock to let live selection or export-candidate state take over again."
        else:
            target_name = export_snapshot.draft_name if export_snapshot else selected_snapshot.draft_name if selected_snapshot else "None"
            target_rule = "Export target resolves to the Export Candidate when one is marked. Otherwise it uses the currently selected draft."
        compare_hint = "Use this screen to sanity-check copy, bundle, pacing, caption treatment, and the recommendation strip before final export."
        lines = [
            f"Project: {p.project_name}",
            f"Goal: {p.content_goal}",
            f"Template family: {p.template_family}",
            f"Platform pack: {p.publish_bundle}",
            f"Drafts generated: {len(p.drafts)}",
            f"Current export target: {target_name}",
            target_rule,
            compare_hint,
            "",
            "To export now:",
            "1. Review the winner strip.",
            "2. Click EXPORT RECOMMENDED VERSION.",
            "3. Wait for the export-complete popup.",
            "4. Open the rendered export folder from the popup path.",
        ]
        if p.export_decision_notes:
            lines.extend(["", "Saved export decision notes:", p.export_decision_notes])
        if p.last_export_path:
            lines.extend(["", f"Last export folder: {p.last_export_path}"])
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", "\n".join(lines))


# -----------------------------------------------------------------------------
# Main app
# -----------------------------------------------------------------------------






@dataclass
class TextLayer:
    """One text element on the visual canvas."""
    layer_id:    str   = field(default_factory=lambda: f"layer_{random.randint(100000,999999)}")
    text:        str   = "New Text"
    x:           float = 0.5        # 0-1 fractional canvas position
    y:           float = 0.80
    font_size:   int   = 52         # display pixels on the preview canvas
    font_family: str   = "Default"
    bold:        bool  = False
    italic:      bool  = False
    uppercase:   bool  = False
    color:       str   = "#ffffff"  # hex
    bg_color:    str   = ""         # "" = no background box
    bg_alpha:    int   = 140        # 0-255
    outline:     bool  = False
    outline_color: str = "#000000"
    align:       str   = "left"     # left / center / right
    animation:   str   = "None"     # None / Fade In / Slide Up / Slide Left / Zoom In / Typewriter
    anim_start:  float = 0.0        # seconds into clip
    anim_end:    float = 0.0        # 0 = to end
    opacity:     float = 1.0        # 0.0-1.0


# Animation preset descriptions shown in the UI
ANIMATION_PRESETS: List[str] = [
    "None",
    "Fade In",
    "Slide Up",
    "Slide Left",
    "Zoom In",
    "Typewriter",
]

FONT_CHOICES: Dict[str, str] = {
    "Default":    "",
    "Bold Sans":  "ariblk.ttf",
    "Clean Sans": "arial.ttf",
    "Condensed":  "arialbd.ttf",
    "Thin":       "ariali.ttf",
}

COLOR_SWATCHES: List[Tuple[str, str]] = [
    ("#ffffff", "White"),
    ("#f0ece8", "Off-white"),
    ("#000000", "Black"),
    ("#8b2d2d", "ED Crimson"),
    ("#b8922a", "ED Gold"),
    ("#2e7d32", "ED Green"),
    ("#1a4a8a", "ED Blue"),
    ("#ff4444", "Hot Red"),
    ("#44aaff", "Sky Blue"),
    ("#ffcc00", "Yellow"),
]


# =============================================================================
#  CanvasEditorScreen  — Step 4.5: Visual Text Composer
# =============================================================================



class CanvasEditorScreen(BaseScreen):
    """
    Canva-style visual text compositor.
    - Click the canvas to place / select text layers
    - Drag layers to reposition
    - Right panel: font, size, color, animation, timing controls
    - Live preview renders text overlaid on the current media frame
    """

    CANVAS_W = 360   # preview canvas display pixels (9x16 aspect portrait)
    CANVAS_H = 640

    def __init__(self, parent, controller: AppController):
        super().__init__(parent, controller)
        self.columnconfigure(0, weight=0)   # left tools
        self.columnconfigure(1, weight=1)   # canvas
        self.columnconfigure(2, weight=0)   # right properties
        self.rowconfigure(1, weight=1)

        # State
        self._layers:        List[TextLayer] = []
        self._selected:      Optional[str]   = None   # layer_id
        self._drag_start:    Optional[Tuple[int,int]] = None
        self._drag_orig:     Optional[Tuple[float,float]] = None
        self._bg_image:      Optional[Any]   = None   # tk PhotoImage of current frame
        self._bg_pil:        Optional[Any]   = None   # PIL image of current frame
        self._redraw_job:    Optional[str]   = None

        # ── Header ────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=ED["bg_root"], pady=8)
        hdr.grid(row=0, column=0, columnspan=3, sticky="ew")
        tk.Label(hdr, text="Visual Text Composer",
                 bg=ED["bg_root"], fg=ED["txt_primary"],
                 font=("Arial", 18, "bold")).pack(side="left")
        tk.Label(hdr,
                 text="  Click the canvas to select layers. Drag to reposition. "
                      "Add text, pick a style, set animation timing, then Done.",
                 bg=ED["bg_root"], fg=ED["txt_secondary"],
                 font=("Arial", 9)).pack(side="left", padx=(8, 0))
        self._ed_btn(hdr, "← Back to Quick Refine",
                     lambda: controller.app.show_screen("quick_refine"),
                     small=True).pack(side="right", padx=(0, 8))
        self._ed_btn(hdr, "✓ Done — Go to Export",
                     lambda: controller.app.show_screen("export"),
                     primary=True, small=True).pack(side="right")

        tk.Frame(self, bg=ED["border_hi"], height=1).grid(
            row=0, column=0, columnspan=3, sticky="sew")

        # ── Left: layer list + add controls ──────────────────────
        left = tk.Frame(self, bg=ED["bg_panel"], width=200)
        left.grid(row=1, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)

        tk.Label(left, text="LAYERS",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold"), padx=10, pady=6).grid(
                     row=0, column=0, sticky="ew")
        tk.Frame(left, bg=ED["border"], height=1).grid(row=1, column=0, sticky="ew")

        # Layer list
        list_frame = tk.Frame(left, bg=ED["bg_panel"])
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        self._layer_list_frame = list_frame

        # Add / delete buttons
        btn_row = tk.Frame(left, bg=ED["bg_panel"], pady=6, padx=8)
        btn_row.grid(row=4, column=0, sticky="ew")
        self._ed_btn(btn_row, "+ Add Text",
                     self._add_layer, primary=True, small=True).pack(
                         side="left", padx=(0, 6))
        self._ed_btn(btn_row, "Delete",
                     self._delete_selected, small=True).pack(side="left")

        # Clip selector
        clip_frame = tk.Frame(left, bg=ED["bg_panel"], padx=8, pady=4)
        clip_frame.grid(row=5, column=0, sticky="ew")
        tk.Label(clip_frame, text="CLIP",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold")).pack(anchor="w")
        self._clip_var = tk.StringVar(value="All clips")
        self._clip_combo = ttk.Combobox(clip_frame, textvariable=self._clip_var,
                                         values=["All clips"], state="readonly", width=18)
        self._clip_combo.pack(fill="x", pady=(2, 0))
        self._clip_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_bg())

        # ── Centre: tk.Canvas preview ────────────────────────────
        canvas_outer = tk.Frame(self, bg=ED["bg_root"], padx=20, pady=20)
        canvas_outer.grid(row=1, column=1, sticky="nsew")
        canvas_outer.columnconfigure(0, weight=1)
        canvas_outer.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(canvas_outer,
                                  width=self.CANVAS_W,
                                  height=self.CANVAS_H,
                                  bg="#1a1a1a",
                                  cursor="crosshair",
                                  highlightthickness=2,
                                  highlightbackground=ED["border"])
        self._canvas.grid(row=0, column=0)
        self._canvas.bind("<ButtonPress-1>",   self._on_canvas_click)
        self._canvas.bind("<B1-Motion>",        self._on_canvas_drag)
        self._canvas.bind("<ButtonRelease-1>",  self._on_canvas_release)

        # Canvas info strip
        info_strip = tk.Frame(canvas_outer, bg=ED["bg_root"])
        info_strip.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        info_strip.columnconfigure(0, weight=1)
        self._canvas_info_var = tk.StringVar(
            value="Click a layer to select it. Drag to move. Use the panel on the right to style.")
        tk.Label(info_strip, textvariable=self._canvas_info_var,
                 bg=ED["bg_root"], fg=ED["txt_dim"],
                 font=("Arial", 8, "italic")).grid(row=0, column=0, sticky="w")

        # ── Right: Properties panel ───────────────────────────────
        right_outer = tk.Frame(self, bg=ED["bg_panel"], width=320)
        right_outer.grid(row=1, column=2, sticky="nsew")
        right_outer.grid_propagate(False)
        right_scroll = ScrollFrame(right_outer, orient="vertical", height=600)
        right_scroll.grid(row=0, column=0, sticky="nsew")
        right_outer.columnconfigure(0, weight=1)
        right_outer.rowconfigure(0, weight=1)
        rp = right_scroll.inner   # right properties inner frame
        rp.columnconfigure(1, weight=1)
        self._rp = rp

        def _sec_hdr(text, color=None):
            f = tk.Frame(rp, bg=color or ED["red"], padx=10, pady=4)
            f.grid(sticky="ew", pady=(10, 0))
            f.columnconfigure(0, weight=1)
            tk.Label(f, text=text, bg=color or ED["red"],
                     fg="#ffffff", font=("Arial", 8, "bold")).pack(side="left")
            return f

        def _row(label, widget_fn, tooltip=""):
            r = getattr(_row, "_r", 0) + 1
            setattr(_row, "_r", r)
            tk.Label(rp, text=label, bg=ED["bg_panel"], fg=ED["txt_primary"],
                     font=("Arial", 9, "bold"), anchor="w").grid(
                         row=r*2-1, column=0, sticky="w", padx=(10, 4), pady=(6, 0))
            w = widget_fn(rp)
            if w:
                w.grid(row=r*2-1, column=1, sticky="ew", padx=(0, 10), pady=(6, 0))
            if tooltip:
                tk.Label(rp, text=f"  ↳ {tooltip}",
                         bg=ED["bg_panel"], fg=ED["txt_dim"],
                         font=("Arial", 7, "italic")).grid(
                             row=r*2, column=0, columnspan=2, sticky="w", padx=(10, 0))
            return w

        _row._r = 0

        # Text content
        _sec_hdr("TEXT CONTENT")
        self._text_var = tk.StringVar()
        _row("Content", lambda p: tk.Entry(p, textvariable=self._text_var,
                                            bg=ED["bg_input"], fg=ED["txt_primary"],
                                            insertbackground=ED["txt_primary"],
                                            relief="flat", bd=0, font=("Arial", 10),
                                            highlightthickness=1,
                                            highlightbackground=ED["border"],
                                            highlightcolor=ED["red"]),
             "The text shown on the video frame")
        self._text_var.trace_add("write", lambda *_: self._apply_prop("text", self._text_var.get()))

        # Quick fill buttons
        qf_frame = tk.Frame(rp, bg=ED["bg_panel"])
        qf_frame.grid(sticky="ew", padx=10, pady=(4, 0))
        tk.Label(qf_frame, text="Quick fill:", bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 8)).pack(side="left", padx=(0, 6))
        for lbl, key in [("Hook", "hook"), ("Title", "title"), ("CTA", "cta")]:
            tk.Button(qf_frame, text=lbl,
                      command=lambda k=key: self._fill_from_project(k),
                      bg=ED["bg_card"], fg=ED["txt_secondary"],
                      activebackground=ED["red"], activeforeground="#ffffff",
                      font=("Arial", 8), relief="flat", bd=0,
                      padx=8, pady=3, cursor="hand2").pack(side="left", padx=(0, 4))

        # Typography
        _sec_hdr("TYPOGRAPHY", ED["blue"])
        self._font_var = tk.StringVar(value="Default")
        _row("Font", lambda p: ttk.Combobox(p, textvariable=self._font_var,
                                              values=list(FONT_CHOICES.keys()),
                                              state="readonly", width=14),
             "Clean Sans = readable, Bold Sans = punchy, Condensed = tight")
        self._font_var.trace_add("write", lambda *_: self._apply_prop("font_family", self._font_var.get()))

        self._size_var = tk.IntVar(value=52)
        size_row = tk.Frame(rp, bg=ED["bg_panel"])
        size_row.grid(sticky="ew", padx=10, pady=(6, 0))
        tk.Label(size_row, text="Size", bg=ED["bg_panel"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold"), width=12, anchor="w").pack(side="left")
        self._size_scale = ttk.Scale(size_row, from_=12, to=160,
                                      variable=self._size_var, orient="horizontal",
                                      command=lambda v: self._apply_prop("font_size", int(float(v))))
        self._size_scale.pack(side="left", fill="x", expand=True)
        self._size_lbl = tk.Label(size_row, textvariable=self._size_var,
                                   bg=ED["bg_panel"], fg=ED["gold"],
                                   font=("Arial", 9, "bold"), width=4)
        self._size_lbl.pack(side="left")
        tk.Label(rp, text="  ↳ 40-60 = standard overlay, 80+ = title card, 120+ = hero text",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(sticky="w", padx=(10, 0))

        # Style toggles
        style_row = tk.Frame(rp, bg=ED["bg_panel"])
        style_row.grid(sticky="ew", padx=10, pady=(6, 0))
        tk.Label(style_row, text="Style", bg=ED["bg_panel"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold"), width=12, anchor="w").pack(side="left")
        self._bold_var   = tk.BooleanVar(value=False)
        self._italic_var = tk.BooleanVar(value=False)
        self._upper_var  = tk.BooleanVar(value=False)
        self._outline_var = tk.BooleanVar(value=False)
        for lbl, var, key in [("B", self._bold_var, "bold"),
                                ("I", self._italic_var, "italic"),
                                ("AA", self._upper_var, "uppercase"),
                                ("⬜", self._outline_var, "outline")]:
            def _make_cb(v=var, k=key):
                return tk.Checkbutton(style_row, text=lbl, variable=v,
                                       command=lambda: self._apply_prop(k, v.get()),
                                       bg=ED["bg_panel"], fg=ED["txt_primary"],
                                       selectcolor=ED["red"],
                                       activebackground=ED["bg_panel"],
                                       font=("Arial", 9, "bold"))
            _make_cb().pack(side="left", padx=(0, 8))

        # Alignment
        align_row = tk.Frame(rp, bg=ED["bg_panel"])
        align_row.grid(sticky="ew", padx=10, pady=(6, 0))
        tk.Label(align_row, text="Align", bg=ED["bg_panel"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold"), width=12, anchor="w").pack(side="left")
        self._align_var = tk.StringVar(value="left")
        for a, icon in [("left", "⬅"), ("center", "⬛"), ("right", "➡")]:
            tk.Radiobutton(align_row, text=icon, variable=self._align_var, value=a,
                           command=lambda: self._apply_prop("align", self._align_var.get()),
                           bg=ED["bg_panel"], fg=ED["txt_secondary"],
                           selectcolor=ED["red"],
                           activebackground=ED["bg_panel"],
                           font=("Arial", 11)).pack(side="left", padx=(0, 6))

        # Color
        _sec_hdr("COLOUR")
        color_grid = tk.Frame(rp, bg=ED["bg_panel"])
        color_grid.grid(sticky="ew", padx=10, pady=(6, 0))
        self._color_var = tk.StringVar(value="#ffffff")
        self._color_swatch = tk.Frame(color_grid, bg="#ffffff", width=28, height=28,
                                       highlightbackground=ED["border_hi"],
                                       highlightthickness=1)
        self._color_swatch.pack(side="left", padx=(0, 8))
        for hex_c, name in COLOR_SWATCHES:
            sw = tk.Frame(color_grid, bg=hex_c, width=22, height=22,
                          cursor="hand2",
                          highlightbackground=ED["border"],
                          highlightthickness=1)
            sw.pack(side="left", padx=(0, 3))
            sw.bind("<Button-1>", lambda e, c=hex_c: self._set_color(c))
            sw.bind("<Enter>", lambda e, f=sw, c=hex_c: (f.configure(highlightbackground=ED["txt_primary"]),))
            sw.bind("<Leave>", lambda e, f=sw: (f.configure(highlightbackground=ED["border"]),))
        tk.Label(rp, text="  ↳ Click a swatch to set text color",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(sticky="w", padx=(10, 0))

        # Background box
        bg_row = tk.Frame(rp, bg=ED["bg_panel"])
        bg_row.grid(sticky="ew", padx=10, pady=(6, 0))
        tk.Label(bg_row, text="Background", bg=ED["bg_panel"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold"), width=12, anchor="w").pack(side="left")
        self._bg_color_var = tk.StringVar(value="")
        self._has_bg_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bg_row, text="Box behind text", variable=self._has_bg_var,
                       command=self._on_bg_toggle,
                       bg=ED["bg_panel"], fg=ED["txt_secondary"],
                       selectcolor=ED["red"],
                       activebackground=ED["bg_panel"],
                       font=("Arial", 9)).pack(side="left", padx=(0, 8))
        self._bg_alpha_var = tk.IntVar(value=140)
        ttk.Scale(bg_row, from_=0, to=255, variable=self._bg_alpha_var,
                  orient="horizontal",
                  command=lambda v: self._apply_prop("bg_alpha", int(float(v)))).pack(
                      side="left", fill="x", expand=True)
        tk.Label(bg_row, text="opacity", bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 8)).pack(side="left", padx=(4, 0))

        # Animation
        _sec_hdr("ANIMATION", ED["gold"])
        self._anim_var = tk.StringVar(value="None")
        anim_grid = tk.Frame(rp, bg=ED["bg_panel"])
        anim_grid.grid(sticky="ew", padx=10, pady=(6, 0))
        for anim in ANIMATION_PRESETS:
            btn = tk.Button(anim_grid, text=anim,
                            command=lambda a=anim: self._set_animation(a),
                            bg=ED["bg_card"], fg=ED["txt_secondary"],
                            activebackground=ED["red"], activeforeground="#ffffff",
                            font=("Arial", 9), relief="flat", bd=0,
                            padx=10, pady=5, cursor="hand2")
            btn.pack(side="left", padx=(0, 4), pady=(4, 0))
            btn.bind("<Configure>", lambda e, b=btn, a=anim:
                     b.configure(bg=ED["red"], fg="#ffffff")
                     if self._anim_var.get() == a else
                     b.configure(bg=ED["bg_card"], fg=ED["txt_secondary"]))
            self._anim_btns = getattr(self, "_anim_btns", []) + [(anim, btn)]
        tk.Label(rp, text="  ↳ Animations play on the final exported video",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(sticky="w", padx=(10, 0))

        # Timing
        _sec_hdr("TIMING", ED["bg_card"])
        timing_frame = tk.Frame(rp, bg=ED["bg_panel"])
        timing_frame.grid(sticky="ew", padx=10, pady=(6, 0))
        timing_frame.columnconfigure(1, weight=1)
        timing_frame.columnconfigure(3, weight=1)
        tk.Label(timing_frame, text="Appears at (sec):",
                 bg=ED["bg_panel"], fg=ED["txt_primary"],
                 font=("Arial", 9)).grid(row=0, column=0, sticky="w")
        self._anim_start_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(timing_frame, from_=0.0, to=120.0, increment=0.5,
                    textvariable=self._anim_start_var, width=6).grid(
                        row=0, column=1, sticky="w", padx=(6, 14))
        tk.Label(timing_frame, text="Until (sec, 0=end):",
                 bg=ED["bg_panel"], fg=ED["txt_primary"],
                 font=("Arial", 9)).grid(row=0, column=2, sticky="w")
        self._anim_end_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(timing_frame, from_=0.0, to=120.0, increment=0.5,
                    textvariable=self._anim_end_var, width=6).grid(
                        row=0, column=3, sticky="w", padx=(6, 0))
        for v, k in [(self._anim_start_var, "anim_start"),
                     (self._anim_end_var, "anim_end")]:
            v.trace_add("write", lambda *_, var=v, key=k:
                        self._apply_prop(key, float(var.get())))
        tk.Label(rp, text="  ↳ Example: BEFORE = 0s→10s, AFTER = 10s→0 (end)",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(sticky="w", padx=(10, 0))

        # Opacity
        op_row = tk.Frame(rp, bg=ED["bg_panel"])
        op_row.grid(sticky="ew", padx=10, pady=(6, 0))
        tk.Label(op_row, text="Opacity", bg=ED["bg_panel"], fg=ED["txt_primary"],
                 font=("Arial", 9, "bold"), width=12, anchor="w").pack(side="left")
        self._opacity_var = tk.DoubleVar(value=1.0)
        ttk.Scale(op_row, from_=0.0, to=1.0, variable=self._opacity_var,
                  orient="horizontal",
                  command=lambda v: self._apply_prop("opacity", float(v))).pack(
                      side="left", fill="x", expand=True)

        # Apply button
        self._ed_btn(rp, "Apply to Clip Layers →",
                     self._push_to_caption_events,
                     primary=True).grid(sticky="ew", padx=10, pady=(14, 4))
        tk.Label(rp, text="  Saves all layers as timed caption events on the selected clip.",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 7, "italic")).grid(sticky="w", padx=(10, 0), pady=(0, 8))

        self._update_props_panel()

    # ── Layer management ──────────────────────────────────────────────────────

    def _add_layer(self) -> None:
        p = self.controller.project
        text = p.hook_text or "New Text"
        layer = TextLayer(text=text, x=0.5, y=0.80)
        self._layers.append(layer)
        self._selected = layer.layer_id
        self._rebuild_layer_list()
        self._update_props_panel()
        self._redraw()

    def _delete_selected(self) -> None:
        if not self._selected:
            return
        self._layers = [l for l in self._layers if l.layer_id != self._selected]
        self._selected = self._layers[-1].layer_id if self._layers else None
        self._rebuild_layer_list()
        self._update_props_panel()
        self._redraw()

    def _rebuild_layer_list(self) -> None:
        for child in self._layer_list_frame.winfo_children():
            child.destroy()
        for i, layer in enumerate(reversed(self._layers)):
            is_sel = layer.layer_id == self._selected
            row = tk.Frame(self._layer_list_frame,
                           bg=ED["selected"] if is_sel else ED["bg_panel"],
                           cursor="hand2")
            row.pack(fill="x")
            tk.Label(row,
                     text=f"  T  {layer.text[:22]}{'…' if len(layer.text)>22 else ''}",
                     bg=ED["selected"] if is_sel else ED["bg_panel"],
                     fg=ED["txt_primary"] if is_sel else ED["txt_secondary"],
                     font=("Arial", 9), anchor="w").pack(fill="x", pady=4, padx=4)
            row.bind("<Button-1>", lambda e, lid=layer.layer_id: self._select_layer(lid))

    def _select_layer(self, layer_id: str) -> None:
        self._selected = layer_id
        self._rebuild_layer_list()
        self._update_props_panel()
        self._redraw()

    # ── Properties sync ──────────────────────────────────────────────────────

    def _selected_layer(self) -> Optional[TextLayer]:
        if not self._selected:
            return None
        return next((l for l in self._layers if l.layer_id == self._selected), None)

    def _apply_prop(self, key: str, value) -> None:
        layer = self._selected_layer()
        if not layer:
            return
        setattr(layer, key, value)
        self._rebuild_layer_list()
        self._schedule_redraw()

    def _update_props_panel(self) -> None:
        layer = self._selected_layer()
        if not layer:
            return
        try:
            self._text_var.set(layer.text)
            self._font_var.set(layer.font_family)
            self._size_var.set(layer.font_size)
            self._bold_var.set(layer.bold)
            self._italic_var.set(layer.italic)
            self._upper_var.set(layer.uppercase)
            self._outline_var.set(layer.outline)
            self._align_var.set(layer.align)
            self._color_var.set(layer.color)
            self._color_swatch.configure(bg=layer.color)
            self._has_bg_var.set(bool(layer.bg_color))
            self._bg_alpha_var.set(layer.bg_alpha)
            self._anim_var.set(layer.animation)
            self._anim_start_var.set(layer.anim_start)
            self._anim_end_var.set(layer.anim_end)
            self._opacity_var.set(layer.opacity)
            self._refresh_anim_buttons()
        except Exception:
            pass

    def _set_color(self, hex_c: str) -> None:
        self._apply_prop("color", hex_c)
        try:
            self._color_swatch.configure(bg=hex_c)
        except Exception:
            pass

    def _on_bg_toggle(self) -> None:
        has = self._has_bg_var.get()
        self._apply_prop("bg_color", "#000000" if has else "")

    def _set_animation(self, anim: str) -> None:
        self._anim_var.set(anim)
        self._apply_prop("animation", anim)
        self._refresh_anim_buttons()

    def _refresh_anim_buttons(self) -> None:
        cur = self._anim_var.get()
        for anim, btn in getattr(self, "_anim_btns", []):
            try:
                btn.configure(
                    bg=ED["red"] if anim == cur else ED["bg_card"],
                    fg="#ffffff" if anim == cur else ED["txt_secondary"])
            except Exception:
                pass

    def _fill_from_project(self, key: str) -> None:
        p = self.controller.project
        text = {"hook": p.hook_text, "title": p.title_text, "cta": p.cta_text}.get(key, "")
        if text:
            self._text_var.set(text)
            self._apply_prop("text", text)

    # ── Canvas interaction ────────────────────────────────────────────────────

    def _canvas_to_frac(self, cx: int, cy: int) -> Tuple[float, float]:
        return cx / self.CANVAS_W, cy / self.CANVAS_H

    def _frac_to_canvas(self, fx: float, fy: float) -> Tuple[int, int]:
        return int(fx * self.CANVAS_W), int(fy * self.CANVAS_H)

    def _on_canvas_click(self, event: tk.Event) -> None:
        """Select a layer if click is near its position, else deselect."""
        fx, fy = self._canvas_to_frac(event.x, event.y)
        hit = None
        for layer in reversed(self._layers):   # top-most first
            lx, ly = self._frac_to_canvas(layer.x, layer.y)
            if abs(event.x - lx) < 80 and abs(event.y - ly) < 30:
                hit = layer.layer_id
                break
        if hit:
            self._selected = hit
            self._drag_start = (event.x, event.y)
            layer = self._selected_layer()
            self._drag_orig = (layer.x, layer.y) if layer else None
            self._update_props_panel()
            self._rebuild_layer_list()
        else:
            self._drag_start = None
            self._drag_orig  = None
        self._redraw()

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if not self._drag_start or not self._drag_orig or not self._selected:
            return
        dx = (event.x - self._drag_start[0]) / self.CANVAS_W
        dy = (event.y - self._drag_start[1]) / self.CANVAS_H
        new_x = max(0.0, min(1.0, self._drag_orig[0] + dx))
        new_y = max(0.0, min(1.0, self._drag_orig[1] + dy))
        layer = self._selected_layer()
        if layer:
            layer.x = new_x
            layer.y = new_y
        self._schedule_redraw()

    def _on_canvas_release(self, _event: tk.Event) -> None:
        self._drag_start = None
        self._drag_orig  = None
        self._canvas_info_var.set(
            "Layer moved. Use the Timing panel to set when this text appears.")

    # ── Background frame rendering ────────────────────────────────────────────

    def _refresh_bg(self) -> None:
        """Load media frame for the selected clip as canvas background."""
        if not Image or not ImageTk:
            return
        p = self.controller.project
        clip_label = self._clip_var.get()
        asset = None
        if clip_label != "All clips":
            idx = next((i for i, c in enumerate(p.selected_storyboard or [])
                        if (p.assets and i < len(p.assets) and
                            f"Clip {i+1}" == clip_label)), None)
            if idx is not None and idx < len(p.selected_storyboard):
                card = p.selected_storyboard[idx]
                asset = next((a for a in p.assets if a.asset_id == card.asset_id), None)
        elif p.selected_storyboard and p.assets:
            card = p.selected_storyboard[0]
            asset = next((a for a in p.assets if a.asset_id == card.asset_id), None)

        if asset:
            preview_path = (asset.analysis.preview_path or
                            (asset.path if asset.media_type == "image" else ""))
            if preview_path and Path(preview_path).exists():
                try:
                    with Image.open(preview_path) as img:
                        img = img.convert("RGB").resize(
                            (self.CANVAS_W, self.CANVAS_H), Image.LANCZOS)
                        self._bg_pil = img.copy()
                        self._bg_image = ImageTk.PhotoImage(img)
                    return
                except Exception:
                    pass
        # Dark placeholder
        try:
            bg = Image.new("RGB", (self.CANVAS_W, self.CANVAS_H), (20, 20, 20))
            if ImageDraw:
                d = ImageDraw.Draw(bg)
                d.text((20, 20), "No media frame", fill=(80, 80, 80))
            self._bg_pil = bg
            self._bg_image = ImageTk.PhotoImage(bg)
        except Exception:
            self._bg_pil = None
            self._bg_image = None

    def _schedule_redraw(self) -> None:
        if self._redraw_job:
            try:
                self.after_cancel(self._redraw_job)
            except Exception:
                pass
        self._redraw_job = self.after(40, self._redraw)

    def _redraw(self) -> None:
        """Repaint the canvas: background frame + all text layers."""
        c = self._canvas
        c.delete("all")

        # Background
        if self._bg_image:
            c.create_image(0, 0, anchor="nw", image=self._bg_image)
        else:
            c.create_rectangle(0, 0, self.CANVAS_W, self.CANVAS_H,
                                fill="#111111", outline="")

        # Grid lines (subtle)
        for pct in [0.33, 0.67]:
            gx = int(pct * self.CANVAS_W)
            gy = int(pct * self.CANVAS_H)
            c.create_line(gx, 0, gx, self.CANVAS_H, fill="#222222", dash=(4, 8))
            c.create_line(0, gy, self.CANVAS_W, gy, fill="#222222", dash=(4, 8))

        # Platform safe zone shading
        safe_top = int(0.12 * self.CANVAS_H)
        safe_bot = int(0.20 * self.CANVAS_H)
        c.create_rectangle(0, 0, self.CANVAS_W, safe_top,
                            fill="#6030aa", stipple="gray25", outline="")
        c.create_rectangle(0, self.CANVAS_H - safe_bot, self.CANVAS_W, self.CANVAS_H,
                            fill="#6030aa", stipple="gray25", outline="")
        c.create_line(0, safe_top, self.CANVAS_W, safe_top,
                      fill="#9966ff", width=1, dash=(6, 4))
        c.create_line(0, self.CANVAS_H - safe_bot, self.CANVAS_W, self.CANVAS_H - safe_bot,
                      fill="#9966ff", width=1, dash=(6, 4))

        # Text layers
        for layer in self._layers:
            cx, cy = self._frac_to_canvas(layer.x, layer.y)
            is_sel = layer.layer_id == self._selected

            text = layer.text.upper() if layer.uppercase else layer.text
            font_size = max(8, min(layer.font_size, 120))
            bold_flag = "bold" if layer.bold else ""
            italic_flag = "italic" if layer.italic else ""
            style_str = f"{bold_flag} {italic_flag}".strip() or "normal"
            tk_font = ("Arial", font_size, style_str)

            # Background box
            if layer.bg_color:
                alpha_frac = layer.bg_alpha / 255.0
                try:
                    r = int(int(layer.bg_color[1:3], 16) * alpha_frac)
                    g = int(int(layer.bg_color[3:5], 16) * alpha_frac)
                    b = int(int(layer.bg_color[5:7], 16) * alpha_frac)
                    bg_fill = f"#{r:02x}{g:02x}{b:02x}"
                except Exception:
                    bg_fill = "#000000"
                est_w = len(text) * font_size * 0.55
                est_h = font_size * 1.4
                c.create_rectangle(
                    cx - 8, cy - est_h * 0.1,
                    cx + est_w + 8, cy + est_h,
                    fill=bg_fill, outline="")

            # Text outline
            if layer.outline:
                for ox, oy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    c.create_text(cx + ox, cy + oy,
                                  text=text, font=tk_font,
                                  fill=layer.outline_color,
                                  anchor="sw" if layer.align == "left" else
                                        "s" if layer.align == "center" else "se")

            # Main text
            anchor = "sw" if layer.align == "left" else "s" if layer.align == "center" else "se"
            c.create_text(cx, cy, text=text, font=tk_font,
                          fill=layer.color, anchor=anchor)

            # Selection handle
            if is_sel:
                c.create_rectangle(cx - 10, cy - font_size - 6,
                                   cx + 10 + len(text) * font_size * 0.5,
                                   cy + 8,
                                   outline=ED["red"], width=2, dash=(4, 3))
                c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5,
                              fill=ED["red"], outline="")

        # Animation label on selected layer
        layer = self._selected_layer()
        if layer and layer.animation != "None":
            c.create_text(6, self.CANVAS_H - 6,
                          text=f"▶ {layer.animation}  {layer.anim_start:.1f}s→"
                               f"{'end' if layer.anim_end==0 else f'{layer.anim_end:.1f}s'}",
                          fill=ED["gold"], anchor="sw",
                          font=("Arial", 9, "bold"))

    # ── Push layers to project caption events ─────────────────────────────────

    def _push_to_caption_events(self) -> None:
        """Convert all canvas TextLayers to CaptionEvents on the selected card."""
        p = self.controller.project
        idx = getattr(p, "selected_storyboard_index", 0)
        if not p.selected_storyboard or idx < 0 or idx >= len(p.selected_storyboard):
            idx = 0
        if not p.selected_storyboard:
            self.controller.app.set_status("No storyboard loaded. Generate drafts first.")
            return
        card = p.selected_storyboard[idx]
        card.caption_events.clear()
        for layer in self._layers:
            evt = CaptionEvent(
                text=layer.text,
                start_sec=layer.anim_start,
                end_sec=layer.anim_end,
                position="Custom XY",
                style="ED Clean Lower Third",
                emphasis="Standard",
                font_family=layer.font_family,
            )
            # Store custom XY on the card
            card.text_position_x = layer.x
            card.text_position_y = layer.y
            card.caption_events.append(evt)
        p.automation_notes.append(
            f"Canvas editor: {len(self._layers)} text layer(s) applied to clip {idx+1}.")
        self.controller.app.set_status(
            f"✓ {len(self._layers)} text layer(s) saved to clip {idx+1}. "
            "Proceed to Export when ready.")

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        p = self.controller.project
        # Rebuild clip dropdown
        clips = ["All clips"]
        if p.selected_storyboard:
            clips += [f"Clip {i+1}" for i in range(len(p.selected_storyboard))]
        try:
            self._clip_combo.configure(values=clips)
            if self._clip_var.get() not in clips:
                self._clip_var.set("All clips")
        except Exception:
            pass
        self._refresh_bg()
        # Seed layers from project hook/title/CTA if empty
        if not self._layers and (p.hook_text or p.title_text or p.cta_text):
            if p.hook_text:
                self._layers.append(TextLayer(text=p.hook_text, x=0.08, y=0.82,
                                               font_size=54, bold=True, color="#ffffff"))
            if p.cta_text:
                self._layers.append(TextLayer(text=p.cta_text, x=0.08, y=0.92,
                                               font_size=38, color=ED["gold"],
                                               anim_start=0.0))
            if self._layers:
                self._selected = self._layers[0].layer_id
        self._rebuild_layer_list()
        self._update_props_panel()
        self._redraw()



class WorkflowApp(TkBase):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — {APP_VERSION}")
        self.geometry("1550x980")
        self.minsize(1280, 860)
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self._configure_brand_theme()

        self.controller = AppController(self)
        self.screen_order = [
            ("choose_outcome", "1. Choose Goal"),
            ("drop_files",     "2. Add Media"),
            ("draft_gallery",  "3. Review Drafts"),
            ("quick_refine",   "4. Quick Changes"),
            ("canvas_editor",  "5. Text Composer"),
            ("export",         "6. Export"),
        ]
        self._build_shell()
        self._refresh_dependency_diagnostics()
        write_dependency_diagnostics_file()
        self.controller.drain_worker_queue()


    def _configure_brand_theme(self) -> None:
        bg       = ED["bg_root"]
        panel    = ED["bg_panel"]
        card     = ED["bg_card"]
        inp      = ED["bg_input"]
        fg       = ED["txt_primary"]
        muted    = ED["txt_secondary"]
        dim      = ED["txt_dim"]
        accent   = ED["red"]
        ahover   = ED["red_hover"]
        border   = ED["border"]
        sel      = ED["selected"]

        try:
            self.configure(bg=bg)
        except Exception:
            pass

        # Global Tk option database — affects all native tk.* widgets
        self.option_add("*Background",              bg)
        self.option_add("*Foreground",              fg)
        self.option_add("*Text.background",         inp)
        self.option_add("*Text.foreground",         fg)
        self.option_add("*Text.insertBackground",   fg)
        self.option_add("*Text.selectBackground",   sel)
        self.option_add("*Text.selectForeground",   fg)
        self.option_add("*Listbox.background",      inp)
        self.option_add("*Listbox.foreground",      fg)
        self.option_add("*Listbox.selectBackground", accent)
        self.option_add("*Listbox.selectForeground", "#ffffff")
        self.option_add("*Listbox.highlightThickness", "0")
        self.option_add("*Entry.background",        inp)
        self.option_add("*Entry.foreground",        fg)
        self.option_add("*Entry.insertBackground",  fg)
        self.option_add("*Button.background",       card)
        self.option_add("*Button.foreground",       fg)
        self.option_add("*Button.activeBackground", ED["bg_hover"])
        self.option_add("*Button.activeForeground", fg)
        self.option_add("*Button.relief",           "flat")
        self.option_add("*Canvas.background",       bg)
        self.option_add("*Spinbox.background",         inp)
        self.option_add("*Spinbox.foreground",         fg)
        self.option_add("*Spinbox.insertBackground",   fg)
        self.option_add("*Spinbox.buttonBackground",   card)
        self.option_add("*Spinbox.relief",             "flat")
        self.option_add("*Spinbox.readonlyBackground", inp)
        self.option_add("*Spinbox.disabledForeground", "#666666")
        self.option_add("*Spinbox.selectForeground",   fg)
        self.option_add("*Spinbox.selectBackground",   "#8b2d2d")
        self.option_add("*Entry.readonlyBackground",   inp)
        self.option_add("*Entry.disabledForeground",   "#666666")
        self.option_add("*Frame.background",        bg)
        self.option_add("*Label.background",        bg)
        self.option_add("*Label.foreground",        fg)

        style = self.style
        style.configure(".",              background=bg, foreground=fg,
                         troughcolor=inp, selectbackground=sel,
                         selectforeground=fg)
        style.configure("TFrame",         background=bg)
        style.configure("Card.TFrame",    background=card)
        style.configure("Panel.TFrame",   background=panel)

        style.configure("TLabel",         background=bg, foreground=fg,
                         font=("Arial", 10))
        style.configure("ED.Header.TLabel",
                         background=bg, foreground=fg,
                         font=("Arial", 20, "bold"))
        style.configure("ED.Subhead.TLabel",
                         background=bg, foreground=muted,
                         font=("Arial", 10))
        style.configure("ED.SectionTitle.TLabel",
                         background=bg, foreground=fg,
                         font=("Arial", 12, "bold"))
        style.configure("ED.Helper.TLabel",
                         background=bg, foreground=dim,
                         font=("Arial", 9))

        style.configure("TLabelframe",
                         background=card, foreground=muted,
                         bordercolor=border, relief="solid",
                         borderwidth=1, lightcolor=border, darkcolor=border)
        style.configure("TLabelframe.Label",
                         background=card, foreground=muted,
                         font=("Arial", 9, "bold"))

        style.configure("TButton",
                         background=card, foreground=fg,
                         bordercolor=border, lightcolor=border, darkcolor=border,
                         relief="flat", font=("Arial", 10), padding=(10, 7))
        style.map("TButton",
                  background=[("active", ED["bg_hover"]), ("pressed", inp)],
                  foreground=[("disabled", dim)])

        style.configure("ED.Primary.TButton",
                         background=accent, foreground="#ffffff",
                         bordercolor=accent, relief="flat",
                         font=("Arial", 10, "bold"), padding=(12, 9))
        style.map("ED.Primary.TButton",
                  background=[("active", ahover), ("pressed", ahover),
                               ("disabled", "#5a2f2f")],
                  foreground=[("disabled", "#d7c8c8")])

        style.configure("ED.Secondary.TButton",
                         background=card, foreground=fg,
                         bordercolor=border, relief="flat",
                         font=("Arial", 10), padding=(10, 7))
        style.map("ED.Secondary.TButton",
                  background=[("active", ED["bg_hover"]), ("pressed", inp),
                               ("disabled", panel)],
                  foreground=[("disabled", dim)])

        style.configure("ED.Nav.TButton",
                         background=panel, foreground=muted,
                         bordercolor=border, relief="flat",
                         font=("Arial", 10), padding=(10, 7))
        style.map("ED.Nav.TButton",
                  background=[("active", card)])

        style.configure("TEntry",
                         fieldbackground=inp, foreground=fg,
                         insertcolor=fg, bordercolor=border,
                         lightcolor=border, darkcolor=border)
        style.map("TEntry",
                  fieldbackground=[("readonly", inp)],
                  foreground=[("readonly", fg)])

        style.configure("TCombobox",
                         fieldbackground=inp, background=card,
                         foreground=fg, arrowcolor=muted,
                         bordercolor=border, lightcolor=border, darkcolor=border)
        style.map("TCombobox",
                  fieldbackground=[("readonly", inp)],
                  foreground=[("readonly", fg)])

        style.configure("TScrollbar",
                         background=card, troughcolor=inp,
                         bordercolor=border, lightcolor=border, darkcolor=border,
                         arrowcolor=muted, relief="flat")
        style.map("TScrollbar",
                  background=[("active", ED["bg_hover"])])

        style.configure("TProgressbar",
                         background=accent, troughcolor=inp,
                         bordercolor=border, lightcolor=accent, darkcolor=accent)

        # Intake-specific progress styles
        _tc = inp
        style.configure("ED.IntakeIdle.Horizontal.TProgressbar",
                         troughcolor=_tc, background=dim,
                         bordercolor=_tc, lightcolor=dim, darkcolor=dim)
        style.configure("ED.IntakeProcessing.Horizontal.TProgressbar",
                         troughcolor=_tc, background=ED["blue"],
                         bordercolor=_tc, lightcolor=ED["blue"], darkcolor=ED["blue"])
        style.configure("ED.IntakeComplete.Horizontal.TProgressbar",
                         troughcolor=_tc, background=ED["green"],
                         bordercolor=_tc, lightcolor=ED["green"], darkcolor=ED["green"])
        style.configure("ED.IntakeError.Horizontal.TProgressbar",
                         troughcolor=_tc, background=ED["red_lite"],
                         bordercolor=_tc, lightcolor=ED["red_lite"], darkcolor=ED["red_lite"])


    def _build_shell(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ── Sidebar ─────────────────────────────────────────────────────────
        self.sidebar = tk.Frame(self, bg=ED["bg_panel"], padx=14, pady=14, width=280)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)

        # Branding
        tk.Label(self.sidebar, text="ENORMOUS DOOR",
                 bg=ED["bg_panel"], fg=ED["red"],
                 font=("Arial", 13, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(self.sidebar, text="Content Wizard",
                 bg=ED["bg_panel"], fg=ED["txt_primary"],
                 font=("Arial", 11), anchor="w").grid(row=1, column=0, sticky="ew")
        tk.Label(self.sidebar,
                 text="Punch, clarity, and weight that survives every platform.",
                 bg=ED["bg_panel"], fg=ED["txt_secondary"],
                 font=("Arial", 8), wraplength=250, justify="left").grid(
                     row=2, column=0, sticky="ew", pady=(4, 10))

        tk.Frame(self.sidebar, bg=ED["border"], height=1).grid(
            row=3, column=0, sticky="ew", pady=(0, 8))

        # Step nav listbox
        tk.Label(self.sidebar, text="YOUR WORKFLOW",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold"), anchor="w").grid(row=4, column=0, sticky="ew")
        self.step_list = tk.Listbox(
            self.sidebar, height=len(self.screen_order),
            exportselection=False,
            bg=ED["bg_card"], fg=ED["txt_secondary"],
            selectbackground=ED["red"], selectforeground="#ffffff",
            activestyle="none", font=("Arial", 10),
            bd=0, highlightthickness=1,
            highlightbackground=ED["border"],
            highlightcolor=ED["border_hi"],
            relief="flat")
        self.step_list.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        for _, label in self.screen_order:
            self.step_list.insert("end", f"  {label}")
        self.step_list.bind("<<ListboxSelect>>", self._on_step_select)

        tk.Frame(self.sidebar, bg=ED["border"], height=1).grid(
            row=6, column=0, sticky="ew", pady=(10, 8))

        # Project actions
        tk.Label(self.sidebar, text="PROJECT",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold"), anchor="w").grid(row=7, column=0, sticky="ew")

        actions = tk.Frame(self.sidebar, bg=ED["bg_panel"])
        actions.grid(row=8, column=0, sticky="ew", pady=(4, 0))
        for c in range(2):
            actions.columnconfigure(c, weight=1)

        def _sb(text, cmd, row, col, primary=False, padx=(0, 4), pady=(0, 4)):
            bg  = ED["red"]    if primary else ED["bg_card"]
            fg  = "#ffffff"    if primary else ED["txt_primary"]
            abg = ED["red_hover"] if primary else ED["bg_hover"]
            b = tk.Button(actions, text=text, command=cmd,
                          bg=bg, fg=fg, activebackground=abg, activeforeground=fg,
                          font=("Arial", 9), relief="flat", bd=0,
                          padx=6, pady=5, cursor="hand2")
            b.grid(row=row, column=col, sticky="ew", padx=padx, pady=pady)
            return b

        _sb("New Build",    self.controller.new_project,              0, 0)
        _sb("Save",         self.controller.save_project,             0, 1, primary=True, padx=(4, 0))
        _sb("Load",         self.controller.load_project,             1, 0)
        _sb("Save As",      self.controller.save_project_as,          1, 1, padx=(4, 0))
        _sb("Continue Last",self.controller.continue_last_project,    2, 0)
        _sb("Open Folder",  self.controller.open_current_project_folder, 2, 1, padx=(4, 0))

        # Current project file
        proj_box = tk.Frame(self.sidebar, bg=ED["bg_card"],
                            highlightbackground=ED["border"], highlightthickness=1)
        proj_box.grid(row=9, column=0, sticky="ew", pady=(10, 0))
        proj_box.columnconfigure(0, weight=1)
        tk.Label(proj_box, text="CURRENT PROJECT FILE",
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold"), anchor="w",
                 padx=8, pady=4).grid(row=0, column=0, sticky="ew")
        self.project_path_var = tk.StringVar(value="Not saved yet")
        self.save_feedback_var = tk.StringVar(value="")
        tk.Entry(proj_box, textvariable=self.project_path_var, state="readonly",
                 bg=ED["bg_input"], fg=ED["txt_secondary"],
                 readonlybackground=ED["bg_input"],
                 relief="flat", bd=0, font=("Arial", 8),
                 highlightthickness=0).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        path_act = tk.Frame(proj_box, bg=ED["bg_card"])
        path_act.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 6))
        path_act.columnconfigure(0, weight=1)
        path_act.columnconfigure(1, weight=1)

        def _path_btn(text, cmd, col):
            tk.Button(path_act, text=text, command=cmd,
                      bg=ED["bg_card"], fg=ED["txt_secondary"],
                      activebackground=ED["bg_hover"], activeforeground=ED["txt_primary"],
                      font=("Arial", 8), relief="flat", bd=0,
                      padx=6, pady=4, cursor="hand2").grid(
                          row=0, column=col, sticky="ew",
                          padx=(0, 3) if col == 0 else (3, 0))

        _path_btn("Copy Path",   self.controller.copy_current_project_path,       0)
        _path_btn("Open Folder", self.controller.open_current_project_folder,      1)
        tk.Label(proj_box, textvariable=self.save_feedback_var,
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 7), wraplength=240, justify="left",
                 padx=8, pady=4).grid(row=3, column=0, sticky="w")

        # Guided mode
        mode_box = tk.Frame(self.sidebar, bg=ED["bg_card"],
                            highlightbackground=ED["border"], highlightthickness=1)
        mode_box.grid(row=10, column=0, sticky="ew", pady=(10, 0))
        mode_box.columnconfigure(0, weight=1)
        tk.Label(mode_box, text="WORKFLOW MODE",
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold"), anchor="w",
                 padx=8, pady=4).grid(row=0, column=0, sticky="ew")
        self.mode_summary_var = tk.StringVar(value="Simple Mode on — recommended settings auto-applied.")
        tk.Label(mode_box, textvariable=self.mode_summary_var,
                 bg=ED["bg_card"], fg=ED["txt_secondary"],
                 font=("Arial", 8), wraplength=240, justify="left",
                 padx=8).grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.mode_toggle_btn = tk.Button(
            mode_box, text="Switch to Advanced Mode",
            command=self.controller.toggle_advanced_mode,
            bg=ED["bg_card"], fg=ED["txt_secondary"],
            activebackground=ED["bg_hover"], activeforeground=ED["txt_primary"],
            font=("Arial", 9), relief="flat", bd=0, padx=8, pady=5, cursor="hand2")
        self.mode_toggle_btn.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))

        # System status
        status_box = tk.Frame(self.sidebar, bg=ED["bg_card"],
                              highlightbackground=ED["border"], highlightthickness=1)
        status_box.grid(row=11, column=0, sticky="ew", pady=(10, 0))
        tk.Label(status_box, text="SYSTEM STATUS",
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold"), anchor="w",
                 padx=8, pady=4).grid(row=0, column=0, sticky="ew")
        self.status_dep_labels = {}
        for idx, dep in enumerate(["PIL", "numpy", "moviepy", "imageio_ffmpeg",
                                    "pytesseract", "whisper", "tkinterdnd2", "audioop"], start=1):
            ok = OPTIONAL_MODULES.get(dep, False)
            lbl = tk.Label(status_box,
                           text=f"{'✓' if ok else '✗'} {dep}",
                           bg=ED["bg_card"],
                           fg=ED["green"] if ok else ED["txt_dim"],
                           font=("Arial", 8), anchor="w", padx=8)
            lbl.grid(row=idx, column=0, sticky="w")
            self.status_dep_labels[dep] = lbl

        diag_box = tk.Frame(self.sidebar, bg=ED["bg_card"],
                            highlightbackground=ED["border"], highlightthickness=1)
        diag_box.grid(row=12, column=0, sticky="nsew", pady=(10, 0))
        diag_box.columnconfigure(0, weight=1)
        diag_box.rowconfigure(1, weight=1)
        tk.Label(diag_box, text="DIAGNOSTICS",
                 bg=ED["bg_card"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold"), anchor="w",
                 padx=8, pady=4).grid(row=0, column=0, sticky="ew")
        self.diagnostics_text = tk.Text(
            diag_box, height=6, wrap="word",
            bg=ED["bg_input"], fg=ED["txt_secondary"],
            insertbackground=ED["txt_primary"],
            relief="flat", bd=0, font=("Courier", 7),
            highlightthickness=0, padx=8, pady=6)
        self.diagnostics_text.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.diagnostics_text.configure(state="disabled")
        # Keep compat aliases
        self.status_box = status_box
        self.diagnostics_box = diag_box

        # ── Main content area ────────────────────────────────────────────────
        self.main = tk.Frame(self, bg=ED["bg_root"])
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(2, weight=1)

        # Top bar
        topbar = tk.Frame(self.main, bg=ED["bg_panel"], pady=8, padx=14)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.columnconfigure(1, weight=1)
        tk.Label(topbar, text="PROJECT",
                 bg=ED["bg_panel"], fg=ED["txt_dim"],
                 font=("Arial", 8, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.project_name_var = tk.StringVar(value=self.controller.project.project_name)
        tk.Entry(topbar, textvariable=self.project_name_var,
                 bg=ED["bg_input"], fg=ED["txt_primary"],
                 insertbackground=ED["txt_primary"],
                 relief="flat", bd=0, font=("Arial", 11),
                 highlightthickness=1,
                 highlightbackground=ED["border"],
                 highlightcolor=ED["red"]).grid(row=0, column=1, sticky="ew", padx=(0, 14))
        self.project_name_var.trace_add("write", self._on_project_name_change)
        self.header_var = tk.StringVar(value=self.screen_order[0][1])
        self.header_label = tk.Label(topbar, textvariable=self.header_var,
                                     bg=ED["bg_panel"], fg=ED["txt_secondary"],
                                     font=("Arial", 10))
        self.header_label.grid(row=0, column=2, sticky="e")

        # Step breadcrumb bar
        crumb_bar = tk.Frame(self.main, bg=ED["bg_panel"], pady=5, padx=14)
        crumb_bar.grid(row=1, column=0, sticky="ew")
        self._step_crumb_labels: List[tk.Label] = []
        for idx, (_, label) in enumerate(self.screen_order):
            if idx > 0:
                tk.Label(crumb_bar, text=" › ",
                         bg=ED["bg_panel"], fg=ED["txt_dim"],
                         font=("Arial", 9)).pack(side="left")
            lbl = tk.Label(crumb_bar, text=label,
                           bg=ED["bg_panel"], fg=ED["txt_dim"],
                           font=("Arial", 9, "bold"), padx=6, pady=2,
                           cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, key=self.screen_order[idx][0]: self.show_screen(key))
            self._step_crumb_labels.append(lbl)
        tk.Frame(self.main, bg=ED["border_hi"], height=1).grid(
            row=1, column=0, sticky="sew")

        # Body (screen stack)
        self.body = tk.Frame(self.main, bg=ED["bg_root"])
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)

        self.screens: Dict[str, BaseScreen] = {
            "choose_outcome": ChooseOutcomeScreen(self.body, self.controller),
            "drop_files":     DropFilesScreen(self.body, self.controller),
            "draft_gallery":  DraftGalleryScreen(self.body, self.controller),
            "quick_refine":   QuickRefineScreen(self.body, self.controller),
            "canvas_editor":  CanvasEditorScreen(self.body, self.controller),
            "export":         ExportScreen(self.body, self.controller),
        }
        self.drop_files_screen = self.screens["drop_files"]
        self.export_screen = self.screens["export"]
        for screen in self.screens.values():
            screen.grid(row=0, column=0, sticky="nsew")

        # Footer
        footer = tk.Frame(self.main, bg=ED["bg_panel"], pady=7, padx=14)
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(footer, textvariable=self.status_var,
                 bg=ED["bg_panel"], fg=ED["txt_secondary"],
                 font=("Arial", 9)).grid(row=0, column=0, sticky="w")
        nav = tk.Frame(footer, bg=ED["bg_panel"])
        nav.grid(row=0, column=1, sticky="e")

        self.back_nav_btn = tk.Button(
            nav, text="← Back", command=self.prev_screen,
            bg=ED["bg_card"], fg=ED["txt_primary"],
            activebackground=ED["bg_hover"], activeforeground=ED["txt_primary"],
            font=("Arial", 10), relief="flat", bd=0, padx=14, pady=6, cursor="hand2")
        self.back_nav_btn.pack(side="left", padx=(0, 6))

        self.next_nav_btn = tk.Button(
            nav, text="Next →", command=self.next_screen,
            bg=ED["red"], fg="#ffffff",
            activebackground=ED["red_hover"], activeforeground="#ffffff",
            font=("Arial", 10, "bold"), relief="flat", bd=0,
            padx=14, pady=6, cursor="hand2")
        self.next_nav_btn.pack(side="left")

        self.current_screen_key = "choose_outcome"
        self.show_screen("choose_outcome")

    def _on_project_name_change(self, *_args) -> None:
        self.controller.project.project_name = self.project_name_var.get().strip() or "Untitled Project"

    def _on_step_select(self, _event=None) -> None:
        selection = self.step_list.curselection()
        if selection:
            self.show_screen(self.screen_order[selection[0]][0])

    def _update_step_crumbs(self, active_key: str) -> None:
        active_idx = next(i for i, (k, _) in enumerate(self.screen_order) if k == active_key)
        for idx, lbl in enumerate(self._step_crumb_labels):
            if idx == active_idx:
                lbl.configure(bg=ED["red"], fg="#ffffff")
            elif idx < active_idx:
                lbl.configure(bg=ED["bg_panel"], fg=ED["green"])
            else:
                lbl.configure(bg=ED["bg_panel"], fg=ED["txt_dim"])

    def show_screen(self, key: str) -> None:
        self.current_screen_key = key
        index = next(i for i, (k, _) in enumerate(self.screen_order) if k == key)
        self.header_var.set(self.screen_order[index][1])
        self.screens[key].tkraise()
        self.step_list.selection_clear(0, "end")
        self.step_list.selection_set(index)
        self.step_list.activate(index)
        self._update_step_crumbs(key)
        self._update_nav_buttons()
        self.refresh_all_screens()

    def _update_nav_buttons(self) -> None:
        index = next(i for i, (k, _) in enumerate(self.screen_order)
                     if k == self.current_screen_key)
        try:
            self.back_nav_btn.configure(
                state="normal" if index > 0 else "disabled",
                fg=ED["txt_primary"] if index > 0 else ED["txt_dim"])
        except Exception:
            pass
        try:
            self.next_nav_btn.configure(
                state="normal" if index < len(self.screen_order) - 1 else "disabled")
        except Exception:
            pass

    def prev_screen(self) -> None:
        index = next(i for i, (k, _) in enumerate(self.screen_order) if k == self.current_screen_key)
        if index > 0:
            self.show_screen(self.screen_order[index - 1][0])

    def next_screen(self) -> None:
        index = next(i for i, (k, _) in enumerate(self.screen_order) if k == self.current_screen_key)
        if index < len(self.screen_order) - 1:
            self.show_screen(self.screen_order[index + 1][0])

    def _update_nav_buttons(self) -> None:
        if not hasattr(self, "next_nav_btn"):
            return
        if self.current_screen_key == "export":
            try:
                self.next_nav_btn.configure(text="Render Export", command=self.controller.export_project)
            except Exception:
                pass
        else:
            try:
                self.next_nav_btn.configure(text="Next", command=self.next_screen)
            except Exception:
                pass

    def _set_simple_sidebar_visibility(self) -> None:
        show_advanced = bool(self.controller.advanced_mode_enabled)
        for panel_name in ("status_box", "diagnostics_box"):
            panel = getattr(self, panel_name, None)
            if panel is None:
                continue
            try:
                if show_advanced:
                    panel.grid()
                else:
                    panel.grid_remove()
            except Exception:
                pass

    def _apply_brand_to_widget_tree(self, root_widget) -> None:
        def style_widget(widget):
            try:
                cls = widget.winfo_class()
            except Exception:
                cls = ""
            try:
                if cls in {"Text", "Listbox"}:
                    widget.configure(bg="#111111", fg="#f3efe6", insertbackground="#f3efe6",
                                     selectbackground="#8b2d2d", selectforeground="#f3efe6",
                                     highlightbackground="#3a3a3a", highlightcolor="#8b2d2d")
                elif cls == "Canvas":
                    widget.configure(bg="#111111", highlightbackground="#2a2a2a")
                elif cls == "Frame":
                    widget.configure(bg="#111111")
                elif cls == "Label":
                    widget.configure(bg="#111111", fg="#f3efe6")
                elif cls == "Button":
                    widget.configure(bg="#8b2d2d", fg="#f3efe6", activebackground="#a53a3a", activeforeground="#f3efe6")
                elif cls == "Listbox":
                    widget.configure(bg="#111111", fg="#f3efe6")
            except Exception:
                pass
            try:
                for child in widget.winfo_children():
                    style_widget(child)
            except Exception:
                pass
        style_widget(root_widget)


    def refresh_all_screens(self) -> None:
        self._update_nav_buttons()
        if self.project_name_var.get() != self.controller.project.project_name:
            self.project_name_var.set(self.controller.project.project_name)
        if hasattr(self, "project_path_var"):
            current_path = str(self.controller.current_project_path) \
                           if self.controller.current_project_path else "Not saved yet"
            self.project_path_var.set(current_path)
        if hasattr(self, "save_feedback_var"):
            self.save_feedback_var.set(
                "Saved. Use Save As to copy." if self.controller.current_project_path
                else "Not saved yet — click Save.")
        if self.controller.advanced_mode_enabled:
            self.mode_summary_var.set("Advanced Mode on — full controls visible.")
            try:
                self.mode_toggle_btn.configure(text="Return to Simple Mode")
            except Exception:
                pass
        else:
            self.mode_summary_var.set("Simple Mode on — recommended settings auto-applied.")
            try:
                self.mode_toggle_btn.configure(text="Switch to Advanced Mode")
            except Exception:
                pass
        self._set_simple_sidebar_visibility()
        for screen in self.screens.values():
            screen.refresh()
        self._refresh_dependency_diagnostics()

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.update_idletasks()

    def _refresh_dependency_diagnostics(self) -> None:
        summary = dependency_diagnostics_summary()
        if hasattr(self, "status_dep_labels"):
            for dep, lbl in self.status_dep_labels.items():
                ok = OPTIONAL_MODULES.get(dep, False)
                try:
                    lbl.configure(
                        text=f"{'✓' if ok else '✗'} {dep}",
                        fg=ED["green"] if ok else ED["txt_dim"])
                except Exception:
                    pass
        if hasattr(self, "diagnostics_text"):
            self.diagnostics_text.configure(state="normal")
            self.diagnostics_text.delete("1.0", "end")
            self.diagnostics_text.insert("1.0", summary)
            self.diagnostics_text.configure(state="disabled")
        write_dependency_diagnostics_file()


def main() -> None:
    app = WorkflowApp()
    app.mainloop()


if __name__ == "__main__":
    main()


# =============================================================================
#  TextLayer — a single styled, animated text element on the canvas
# =============================================================================

