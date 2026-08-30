"""Cut the demo video: real UI footage, real captured output, narration, score, subtitles.

Picture comes from three honest sources and no others:
  clips/*.webm        Playwright recording of the live deployment, in motion
  docs/gallery/*.png  terminal frames captured from real runs against production
  architecture.png    original diagram

Audio is the Lyria score under the Gemini TTS narration. Subtitles are burned in, because the
rules require them and a sidecar file is easy for a judge to miss.

    .venv/bin/python scripts/assemble_video.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

# The default brew ffmpeg bottle ships without libass or libfreetype, so it has no subtitles,
# ass or drawtext filter at all. ffmpeg-full has both; prefer it, fall back to PATH.
FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
FF = str(FULL) if FULL.exists() else "ffmpeg"

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "video/assets"
CLIPS = A / "clips"
GAL = ROOT / "docs/gallery"
WORK = A / "_work"
OUT = ROOT / "video/concordat-demo.mp4"
FPS = 30

# (source, kind, start_in_source). Durations are computed from the narration, so picture and
# voice cannot drift: each shot lasts exactly as long as the line spoken over it.
SHOTS = [
    ("vo-1-cold-open",                 GAL / "01-cover.png",        "still", 0),
    ("vo-2-value-proposition",         CLIPS / "s2-dashboard.webm", "clip",  8),
    ("vo-3-intake-and-the-dead-end",   CLIPS / "s3-intake.webm",    "clip",  7),
    ("vo-4-the-negotiation",           CLIPS / "s4-negotiation.webm", "clip", 7),
    ("vo-5-clean-room-and-the-finding", CLIPS / "s5-finding.webm",  "clip",  7),
    ("vo-6-running-on-google-cloud",   None,                        "console", 0),
    ("vo-7-the-two-claims-you-can-check", None,                     "triple", 0),
    ("vo-8-architecture",              ROOT / "docs/architecture.png", "still", 0),
    ("vo-9-close",                     CLIPS / "s9-close.webm",     "clip",  7),
]
# shot 7 runs over the three proof frames in turn
TRIPLE = [GAL / "08-sovereignty.png", GAL / "09-privacy-floor.png", GAL / "10-injection.png"]

# Shot 6 walks the Cloud Console in the order the narration names the services. Recorded by
# scripts/record_console.py; without that footage the shot falls back to the captured gcloud
# frame so the cut still builds.
CONSOLE = ROOT / "video/assets/console"
CONSOLE_ORDER = ["run-services", "run-logs", "pubsub", "firestore", "bigquery",
                 "agent-engine", "iam"]

# This ffmpeg has neither libass nor libfreetype, so there is no subtitles, ass or drawtext
# filter to burn with. Pillow draws each caption to a transparent PNG instead and overlay
# composites it for exactly its own span, which needs no text support in ffmpeg at all.
# Styling lives in the .ass file rather than force_style=, because escaping a style string
# through ffmpeg's filter parser with no shell in the way is a losing game.
# name, font, size, primary, secondary, outline, back, b,i,u,s, scale x/y, spacing, angle,
# border 3 = opaque box, outline, shadow, align 2 = bottom centre, margins l/r/v, encoding
ASS_STYLE = ("Style: Default,Helvetica Neue,34,&H00FFFFFF,&H000000FF,&H00000000,&HB4000000,"
             "0,0,0,0,100,100,0,0,3,1.7,0,2,120,120,54,1")

FIT = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
       "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1")


def run(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True, check=False)
    if r.returncode:
        raise SystemExit(f"ffmpeg failed:\n{' '.join(args[:12])}...\n{r.stderr[-1500:]}")


def dur(path: Path) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=False).stdout.strip())


def still(src: Path, seconds: float, dest: Path, zoom: float = 1.08) -> None:
    """A slow push in, so a static frame still reads as a shot rather than a slide."""
    frames = int(seconds * FPS)
    run([FF, "-v", "error", "-y", "-loop", "1", "-i", str(src),
         "-vf", (f"{FIT},zoompan=z='min(1+({zoom}-1)*on/{frames},{zoom})'"
                 f":d={frames}:s=1920x1080:fps={FPS},format=yuv420p"),
         "-t", f"{seconds}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium",
         "-crf", "18", str(dest)])


def clip(src: Path, start: float, seconds: float, dest: Path) -> None:
    run([FF, "-v", "error", "-y", "-ss", str(start), "-i", str(src), "-t", f"{seconds}",
         "-vf", f"{FIT},format=yuv420p", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", str(dest)])


def srt_time(t: float) -> str:
    h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s%1)*1000):03}"


def narration_text() -> dict[str, str]:
    """Same source of truth the voice was generated from."""
    text = (ROOT / "docs/video-script.md").read_text()
    out = {}
    for m in re.finditer(r"^### (\d)\. ([^\n(]+).*?\n(.*?)(?=^### |\Z)", text,
                         re.DOTALL | re.MULTILINE):
        spoken = " ".join(ln.lstrip("> ").strip()
                          for ln in m.group(3).splitlines() if ln.startswith(">"))
        key = f"vo-{m.group(1)}-{m.group(2).strip().lower().replace(' ', '-')}"
        out[key] = re.sub(r"\s+", " ", spoken).strip()
    return out


def build_srt(spans: list[tuple[str, float, float]], texts: dict[str, str], dest: Path) -> None:
    """Split each narration block into sentences and spread them across its span by length.

    Not word-accurate timing, but it tracks the read closely and never drifts more than a
    sentence, which is what a judge reading along actually needs.
    """
    n, lines = 1, []
    for key, start, end in spans:
        body = texts.get(key, "")
        sentences = [s.strip() for s in re.split(r"(?<=[.:])\s+", body) if s.strip()]
        total = sum(len(s) for s in sentences) or 1
        t = start
        for s in sentences:
            span = (end - start) * len(s) / total
            lines.append(f"{n}\n{srt_time(t)} --> {srt_time(min(t + span, end))}\n"
                         + "\n".join(textwrap.wrap(s, 62)) + "\n")
            t += span; n += 1
    dest.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)

    texts = narration_text()
    segs, spans, t = [], [], 0.0

    for key, src, kind, start in SHOTS:
        vo = A / f"{key}.mp3"
        d = dur(vo)
        dest = WORK / f"{key}.mp4"
        if kind == "still":
            still(src, d, dest)
        elif kind == "clip":
            clip(src, start, d, dest)
        elif kind == "console":
            have = [CONSOLE / f"{n}.webm" for n in CONSOLE_ORDER
                    if (CONSOLE / f"{n}.webm").exists()]
            if not have:
                print("    no console footage yet -> using the gcloud frame instead")
                still(GAL / "11-projects.png", d, dest)
            else:
                parts = []
                for i, src2 in enumerate(have):
                    q = WORK / f"{key}-{i}.mp4"
                    clip(src2, 2.0, d / len(have), q)   # skip the Console settling in
                    parts.append(q)
                lst2 = WORK / f"{key}.txt"
                lst2.write_text("".join(f"file '{q}'\n" for q in parts))
                run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst2),
                     "-c", "copy", str(dest)])
        else:                                    # three proof frames sharing one line
            parts = []
            for i, img in enumerate(TRIPLE):
                p = WORK / f"{key}-{i}.mp4"
                still(img, d / len(TRIPLE), p, zoom=1.05)
                parts.append(p)
            lst = WORK / f"{key}.txt"
            lst.write_text("".join(f"file '{p}'\n" for p in parts))
            run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-c", "copy", str(dest)])
        segs.append(dest); spans.append((key, t, t + d)); t += d
        print(f"  {key:<36} {d:5.1f}s  -> {t:6.1f}s")

    # picture
    lst = WORK / "all.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in segs))
    silent = WORK / "picture.mp4"
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(silent)])

    # voice
    vlst = WORK / "vo.txt"
    vlst.write_text("".join(f"file '{A / (k + '.mp3')}'\n" for k, _, _ in spans))
    voice = WORK / "voice.wav"
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(vlst),
         "-ar", "48000", "-ac", "2", str(voice)])

    # score: tension under the problem, resolve under the payoff, both well under the voice
    score = WORK / "score.wav"
    run([FF, "-v", "error", "-y",
         "-stream_loop", "-1", "-i", str(A / "score-tension.wav"),
         "-stream_loop", "-1", "-i", str(A / "score-resolve.wav"),
         "-filter_complex",
         (f"[0:a]atrim=0:{t/2},afade=t=out:st={t/2-3}:d=3[a];"
          f"[1:a]atrim=0:{t/2+1},afade=t=in:d=3[b];"
          "[a][b]concat=n=2:v=0:a=1,volume=0.13[s]"),
         "-map", "[s]", "-ar", "48000", "-ac", "2", "-t", f"{t}", str(score)])

    mixed = WORK / "mix.wav"
    run([FF, "-v", "error", "-y", "-i", str(voice), "-i", str(score),
         "-filter_complex", ("[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[v];[v][1:a]amix=inputs=2:"
                             "duration=first:dropout_transition=0,alimiter=limit=0.95[m]"),
         "-map", "[m]", str(mixed)])

    srt = A / "concordat-demo.srt"
    build_srt(spans, texts, srt)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    ass = WORK / "subs.ass"
    run([FF, "-v", "error", "-y", "-i", str(srt), str(ass)])
    # ffmpeg writes the .ass with a 384x288 canvas, so every size in it gets scaled by 3.75
    # on a 1080p frame. Pin the canvas to the real frame first, then the style is literal.
    a_txt = ass.read_text()
    a_txt = re.sub(r"^PlayResX:.*$", "PlayResX: 1920", a_txt, flags=re.MULTILINE)
    a_txt = re.sub(r"^PlayResY:.*$", "PlayResY: 1080", a_txt, flags=re.MULTILINE)
    if "PlayResX" not in a_txt:
        a_txt = a_txt.replace("[Script Info]", "[Script Info]\nPlayResX: 1920\nPlayResY: 1080")
    ass.write_text(re.sub(r"^Style: Default,.*$", ASS_STYLE, a_txt, flags=re.MULTILINE))

    run([FF, "-v", "error", "-y", "-i", str(silent), "-i", str(mixed),
         "-vf", f"ass={ass}", "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(OUT)])
    print(f"\n{OUT}  {dur(OUT):.1f}s  {OUT.stat().st_size/1e6:.1f} MB")
    print(f"{srt}  (sidecar subtitles; also burned in via libass)")


if __name__ == "__main__":
    main()
