"""Moods from the audio itself (Discogs-EffNet embeddings + MTG-Jamendo mood/theme classifier).

The preprocessing mirrors Essentia's TensorflowInputMusiCNN and TensorflowPredictEffnetDiscogs:
16 kHz mono, frames of 512 with hop 256 (first frame centred on sample 0), symmetric Hann window,
power spectrum, 96 Slaney mel bands, log10(1 + 10000 x), patches of 128 frames with hop 62.
The models (CC BY-NC-SA 4.0, Music Technology Group, UPF) are downloaded on first use.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from .i18n import tr

SAMPLE_RATE, FRAME, HOP, BANDS, PATCH, PATCH_HOP = 16000, 512, 256, 96, 128, 62
BATCH = 64
MIN_VALUE, MIN_LIFT, MAX_MOODS = 0.04, 1.2, 4

_BASE = "https://essentia.upf.edu/models"
EFFNET = "discogs-effnet-bsdynamic-1.onnx"
MOODHEAD = "mtg_jamendo_moodtheme-discogs-effnet-1.onnx"
MODELS: dict[str, tuple[str, str]] = {
    EFFNET: (f"{_BASE}/feature-extractors/discogs-effnet/{EFFNET}",
             "a280825b334797cf677939db8cd5762c0392aedd0ca6415dbc1cd083f045e43c"),
    MOODHEAD: (f"{_BASE}/classification-heads/mtg_jamendo_moodtheme/{MOODHEAD}",
               "7d6270acaa5f4bba4b115a0d6849aca05ed6bd153dcb6d9da4f6ab9f99ef10ff"),
}

# Output order of the classifier.
MOOD_CLASSES: tuple[str, ...] = (
    "action", "adventure", "advertising", "background", "ballad", "calm", "children", "christmas",
    "commercial", "cool", "corporate", "dark", "deep", "documentary", "drama", "dramatic", "dream",
    "emotional", "energetic", "epic", "fast", "film", "fun", "funny", "game", "groovy", "happy",
    "heavy", "holiday", "hopeful", "inspiring", "love", "meditative", "melancholic", "melodic",
    "motivational", "movie", "nature", "party", "positive", "powerful", "relaxing", "retro",
    "romantic", "sad", "sexy", "slow", "soft", "soundscape", "space", "sport", "summer", "trailer",
    "travel", "upbeat", "uplifting")

# Mean activation of each class over a mixed reference set of 122 songs (rock, metal, pop,
# acoustic). A mood only counts when a song clearly exceeds this level.
REFERENCE: dict[str, float] = {
    "action": 0.0409, "adventure": 0.0195, "advertising": 0.0194, "background": 0.0241,
    "ballad": 0.0412, "calm": 0.0151, "children": 0.0056, "christmas": 0.0131, "commercial": 0.0120,
    "cool": 0.0106, "corporate": 0.0207, "dark": 0.0553, "deep": 0.0051, "documentary": 0.0106,
    "drama": 0.0133, "dramatic": 0.0118, "dream": 0.0192, "emotional": 0.0347, "energetic": 0.1511,
    "epic": 0.0667, "fast": 0.0110, "film": 0.0252, "fun": 0.0146, "funny": 0.0133, "game": 0.0052,
    "groovy": 0.0069, "happy": 0.0447, "heavy": 0.0701, "holiday": 0.0089, "hopeful": 0.0192,
    "inspiring": 0.0320, "love": 0.1098, "meditative": 0.0522, "melancholic": 0.0235,
    "melodic": 0.1004, "motivational": 0.0306, "movie": 0.0122, "nature": 0.0077, "party": 0.0069,
    "positive": 0.0189, "powerful": 0.0242, "relaxing": 0.0428, "retro": 0.0054, "romantic": 0.0282,
    "sad": 0.0368, "sexy": 0.0032, "slow": 0.0127, "soft": 0.0196, "soundscape": 0.0109,
    "space": 0.0200, "sport": 0.0204, "summer": 0.0061, "trailer": 0.0044, "travel": 0.0075,
    "upbeat": 0.0159, "uplifting": 0.0321,
}

# Classifier class -> name in the MOOD tag. The other classes are topics or uses (film, trailer, ...).
MOOD_NAMES: dict[str, str] = {
    "action": "Action", "adventure": "Adventure", "ballad": "Ballad", "cool": "Cool", "deep": "Deep",
    "fast": "Fast", "funny": "Funny", "love": "Romantic", "melodic": "Melodic", "retro": "Retro", "slow": "Slow",
    "calm": "Calm", "dark": "Dark", "dramatic": "Dramatic", "dream": "Dreamy", "emotional": "Emotional",
    "energetic": "Energetic", "epic": "Epic", "fun": "Fun", "groovy": "Groovy", "happy": "Happy",
    "heavy": "Heavy", "hopeful": "Hopeful", "inspiring": "Uplifting", "meditative": "Meditative",
    "melancholic": "Melancholic", "motivational": "Uplifting", "party": "Party", "positive": "Upbeat",
    "powerful": "Powerful", "relaxing": "Relaxing", "romantic": "Romantic", "sad": "Sad", "sexy": "Sexy",
    "soft": "Mellow", "upbeat": "Upbeat", "uplifting": "Uplifting",
}


class MoodError(Exception):
    """The analysis cannot run at all (no ffmpeg, models unavailable)."""


def pick_moods(values: Sequence[float]) -> list[str]:
    """Mood names for one song: present (value) and above the reference level (lift)."""
    scored = []
    for name, value in zip(MOOD_CLASSES, values):
        label = MOOD_NAMES.get(name)
        if label is None:
            continue
        lift = float(value) / REFERENCE[name]
        if value >= MIN_VALUE and lift >= MIN_LIFT:
            scored.append((float(value) * lift, label))
    out: list[str] = []
    for _score, label in sorted(scored, key=lambda s: -s[0]):
        if label not in out:
            out.append(label)
        if len(out) == MAX_MOODS:
            break
    return out


# ---------------------------------------------------------------------------
# features

def _hz2mel(f: float) -> float:
    return f * 3 / 200.0 if f < 1000 else 15 + float(np.log(f / 1000.0)) * 27 / float(np.log(6.4))


def _mel2hz(m: float) -> float:
    return m * 200 / 3.0 if m < 15 else 1000 * float(np.exp((m - 15) * np.log(6.4) / 27))


def filterbank() -> np.ndarray:
    top = _hz2mel(SAMPLE_RATE / 2)
    edges = [_mel2hz(i * top / (BANDS + 1)) for i in range(BANDS + 2)]
    scale = (SAMPLE_RATE / 2) / (FRAME / 2)
    fb = np.zeros((BANDS, FRAME // 2 + 1), dtype=np.float32)
    for b in range(BANDS):
        lo, mid, hi = edges[b], edges[b + 1], edges[b + 2]
        step1, step2 = mid - lo, hi - mid
        for j in range(int(np.ceil(lo / scale)), int(np.floor(hi / scale + 1e-9)) + 1):
            f = j * scale
            fb[b, j] = max(0.0, (f - lo) / step1 if f < mid else (hi - f) / step2)
        fb[b] /= (step1 + step2) / 2               # theoretical triangle area ("unit_tri")
    return fb


_FB = filterbank()
_WINDOW = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(FRAME) / (FRAME - 1))).astype(np.float32)


def melspec(y: np.ndarray) -> np.ndarray | None:
    """(frames, 96) log-mel spectrogram; None if the audio is shorter than one patch."""
    y = np.concatenate([np.zeros(FRAME // 2, dtype=np.float32), y])
    n = 1 + (len(y) - FRAME) // HOP
    if n < PATCH:
        return None
    out = np.empty((n, BANDS), dtype=np.float32)
    for start in range(0, n, 4096):                # chunks keep the memory peak small
        idx = range(start, min(n, start + 4096))
        frames = np.stack([y[i * HOP:i * HOP + FRAME] for i in idx]) * _WINDOW
        power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
        out[start:start + len(idx)] = np.log10(1 + 10000 * (power @ _FB.T))
    return out


def patches(mel: np.ndarray) -> np.ndarray:
    return np.stack([mel[i:i + PATCH] for i in range(0, len(mel) - PATCH + 1, PATCH_HOP)])


# ---------------------------------------------------------------------------
# files

def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "PsyTags"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_models(folder: str, fetch: Callable[[str], bytes] | None = None) -> None:
    """Make sure the model files exist in ``folder``; download and verify the missing ones."""
    fetch = fetch or _download
    os.makedirs(folder, exist_ok=True)
    for name, (url, digest) in MODELS.items():
        path = os.path.join(folder, name)
        if os.path.exists(path) and _sha256(path) == digest:
            continue
        try:
            data = fetch(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise MoodError(tr("Modell {1} konnte nicht geladen werden: {2}", name, e)) from e
        if hashlib.sha256(data).hexdigest() != digest:
            raise MoodError(tr("Modell {1} ist beschädigt (Prüfsumme stimmt nicht).", name))
        part = path + ".part"
        with open(part, "wb") as fh:
            fh.write(data)
        os.replace(part, path)


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise MoodError(tr("ffmpeg wurde nicht gefunden. Für die Mood-Analyse muss es im PATH liegen."))
    return exe


def decode(path: str) -> np.ndarray:
    """The first audio stream as 16 kHz mono float32."""
    cmd = [_ffmpeg(), "-nostdin", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1",
           "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    p = subprocess.run(cmd, capture_output=True, check=True, creationflags=flags)
    return np.frombuffer(p.stdout, dtype=np.float32)


class Analyzer:
    """Holds the two models; ``moods`` may be called from several threads."""

    def __init__(self, folder: str):
        _ffmpeg()
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = 3
        so.inter_op_num_threads = 1
        providers = ["CPUExecutionProvider"]
        self.effnet = ort.InferenceSession(os.path.join(folder, EFFNET), so, providers=providers)
        self.head = ort.InferenceSession(os.path.join(folder, MOODHEAD), so, providers=providers)

    def song_values(self, path: str) -> np.ndarray | None:
        """Mean activation per class, or None if the audio is too short."""
        mel = melspec(decode(path))
        if mel is None:
            return None
        ps = patches(mel)
        emb = [self.effnet.run(["embeddings"], {"melspectrogram": ps[i:i + BATCH]})[0]
               for i in range(0, len(ps), BATCH)]
        return self.head.run(["activations"], {"embeddings": np.concatenate(emb)})[0].mean(axis=0)

    def moods(self, path: str) -> list[str] | None:
        values = self.song_values(path)
        return None if values is None else pick_moods(values.tolist())


@dataclass
class AnalysisResult:
    found: dict[str, list[str]] = field(default_factory=dict)
    empty: list[str] = field(default_factory=list)       # too short or nothing recognized
    failed: list[str] = field(default_factory=list)      # unreadable files


def analyze_files(paths: Sequence[str], moods_of: Callable[[str], list[str] | None],
                  on_progress: Callable[[int, int], None] | None = None,
                  should_stop: Callable[[], bool] | None = None,
                  workers: int = 4) -> AnalysisResult:
    """Run ``moods_of`` over all paths. A bad file is counted and the run continues;
    after ``should_stop`` the songs already finished are still returned."""
    result = AnalysisResult()
    lock = threading.Lock()
    done = [0]

    def work(path: str) -> None:
        if should_stop is not None and should_stop():
            return
        try:
            moods = moods_of(path)
        except Exception:
            moods, failed = None, True
        else:
            failed = False
        with lock:
            if failed:
                result.failed.append(path)
            elif moods:
                result.found[path] = moods
            else:
                result.empty.append(path)
            done[0] += 1
            if on_progress is not None:
                on_progress(done[0], len(paths))

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(work, paths))
    return result
