"""pull_creative_transcripts.py — transcription Whisper des créas vidéo Meta → dim_creative.transcript.

Flow par créa (video_id non null, transcript null) :
  1. GET graph.facebook.com/{video_id}?fields=source,permalink_url
     `source` est silencieusement omis par Meta avec le token System User actuel
     (permission page manquante) → fallback : download du reel public via yt-dlp
     sur https://www.facebook.com{permalink_url}
  2. Download mp4 en /tmp ; si >24MB (limite upload Whisper = 25MB), extraction audio ffmpeg
     (mono 16kHz 32kbps mp3 — largement suffisant pour de la voix)
  3. POST OpenAI /v1/audio/transcriptions (whisper-1, fr)
  4. UPDATE dim_creative SET transcript, transcribed_at

Usage:
  python -m pipelines.pull_creative_transcripts [--limit 50] [--force]

Env :
  META_ACCESS_TOKEN, SUPABASE_* (.env.local) · OPENAI_API_KEY (~/.env)

Idempotent : ne retraite jamais un transcript non-null sauf --force.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from pipelines.lib.db import sb
from pipelines.lib.meta_client import MetaClient, MetaError

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")
load_dotenv(Path.home() / ".env")  # OPENAI_API_KEY

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
MAX_UPLOAD_BYTES = 24 * 1024 * 1024  # limite Whisper = 25MB, marge de sécu


def fetch_video_meta(meta: MetaClient, video_id: str) -> dict:
    """{source?, permalink_url?} — `source` est souvent omis (permission page manquante)."""
    try:
        return meta.get(video_id, {"fields": "source,permalink_url"})
    except MetaError as e:
        print(f"[creatives] WARN video {video_id}: {e}", file=sys.stderr)
        return {}


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)


def download_via_ytdlp(permalink_url: str, dest: Path) -> bool:
    """Reel public Facebook → mp4 via yt-dlp. True si le fichier existe à la fin."""
    url = f"https://www.facebook.com{permalink_url}"
    r = subprocess.run(
        ["yt-dlp", "-q", "--no-warnings", "-f", "b[ext=mp4]/b", "-o", str(dest), url],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"[creatives] WARN yt-dlp {url}: {r.stderr.strip()[:200]}", file=sys.stderr)
    return dest.exists()


def extract_audio(mp4: Path) -> Path:
    """mp4 → mp3 mono 16kHz pour passer sous la limite d'upload Whisper."""
    mp3 = mp4.with_suffix(".mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(mp3)],
        check=True, capture_output=True,
    )
    return mp3


def transcribe(path: Path, api_key: str) -> str:
    with open(path, "rb") as f:
        resp = requests.post(
            WHISPER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (path.name, f, "application/octet-stream")},
            data={"model": "whisper-1", "language": "fr"},
            timeout=300,
        )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=50, help="max vidéos à traiter")
    p.add_argument("--force", action="store_true", help="retraite aussi les transcripts existants")
    args = p.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[creatives] OPENAI_API_KEY manquante (~/.env)", file=sys.stderr)
        return 1

    q = sb().table("dim_creative").select("creative_id, video_id").not_.is_("video_id", "null")
    if not args.force:
        q = q.is_("transcript", "null")
    # dim_ad n'a ni status ni creative_id → pas de filtre "ads actives" possible, on traite tout
    todo = q.limit(args.limit).execute().data
    print(f"[creatives] {len(todo)} créas à transcrire (limit {args.limit}, force={args.force})")

    meta = MetaClient()
    done, skipped, errors = 0, 0, 0

    for row in todo:
        cid, vid = row["creative_id"], row["video_id"]
        vmeta = fetch_video_meta(meta, vid)
        source, permalink = vmeta.get("source"), vmeta.get("permalink_url")
        if not source and not permalink:
            skipped += 1
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="crea_") as tmp:
                mp4 = Path(tmp) / f"{vid}.mp4"
                if source:
                    download(source, mp4)
                elif not download_via_ytdlp(permalink, mp4):
                    skipped += 1
                    continue
                audio = extract_audio(mp4) if mp4.stat().st_size > MAX_UPLOAD_BYTES else mp4
                text = transcribe(audio, api_key)
            if not text:
                print(f"[creatives] WARN transcript vide pour {cid} (video {vid})", file=sys.stderr)
                skipped += 1
                continue
            sb().table("dim_creative").update({
                "transcript": text,
                "transcribed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("creative_id", cid).execute()
            done += 1
            print(f"[creatives] ok {cid} — {len(text)} chars")
        except Exception as e:
            errors += 1
            print(f"[creatives] ERROR {cid} (video {vid}): {e}", file=sys.stderr)
        time.sleep(1)

    print(f"[creatives] {done} transcrits · {skipped} skipped · {errors} erreurs")
    return 0 if errors == 0 else (0 if done else 1)


if __name__ == "__main__":
    raise SystemExit(main())
