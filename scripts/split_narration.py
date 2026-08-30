"""Split one continuous voice recording into the nine narration tracks.

Record the whole script in a single take, leaving a clear pause between numbered sections.
This finds those pauses and cuts there, so the take drops straight into the existing edit:

    .venv/bin/python scripts/split_narration.py ~/Desktop/narration.m4a

Anything ffmpeg reads works (m4a, wav, mp3, aiff). The nine pieces land in video/assets as
vo-1-... through vo-9-..., replacing the synthesized ones, and the old files are kept in
video/assets/_tts-backup in case the take turns out worse than the robot.

Shot lengths in assemble_video.py come from these files, so picture re-times to your read
automatically. The only hard constraint is the total: the video must come in under 4:00.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "video/assets"
BACKUP = A / "_tts-backup"
FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
FF = str(FULL) if FULL.exists() else "ffmpeg"
# rsplit, not replace: the directory is called ffmpeg-full too, and replacing every
# occurrence points at a bin/ffprobe inside a non-existent ffprobe-full.
FP = "ffprobe".join(FF.rsplit("ffmpeg", 1))

# A pause has to be this quiet for this long to count as a section break. Tuned against the
# first real take: a phone recording in a normal room has a noise floor around -19 dB mean, so
# -34 dB never triggers and nothing splits. Verify a change by checking that section lengths
# still track the word counts in the script, not just that the count comes out at nine.
SILENCE_DB = -25
SILENCE_MIN = 0.9
LIMIT = 240.0


def names() -> list[str]:
    """The nine track names, taken from the script so they always match the edit."""
    text = (ROOT / "docs/video-script.md").read_text()
    out = []
    for m in re.finditer(r"^### (\d)\. ([^\n(]+)", text, re.MULTILINE):
        out.append(f"vo-{m.group(1)}-{m.group(2).strip().lower().replace(' ', '-')}")
    return out


def duration(p: Path) -> float:
    return float(subprocess.run([FP, "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=False).stdout.strip())


def silences(src: Path) -> list[tuple[float, float]]:
    r = subprocess.run([FF, "-i", str(src), "-af",
                        f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-f", "null", "-"],
                       capture_output=True, text=True, check=False)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends, strict=False))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: split_narration.py <recording>")
    src = Path(sys.argv[1]).expanduser()
    if not src.exists():
        raise SystemExit(f"no such file: {src}")

    want = names()
    total = duration(src)
    gaps = silences(src)
    print(f"{src.name}: {total:.1f}s, {len(gaps)} pauses found\n")

    # Cut in the middle of each pause, so every piece keeps a little air at both ends.
    cuts = [0.0] + [(a + b) / 2 for a, b in gaps] + [total]
    # Drop a leading or trailing pause: those are the room, not a section break.
    segs = [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)
            if cuts[i + 1] - cuts[i] > 2.0]

    if len(segs) != len(want):
        print(f"Found {len(segs)} sections but the script has {len(want)}.\n")
        for i, (a, b) in enumerate(segs, 1):
            print(f"  {i:>2}. {a:7.1f} -> {b:7.1f}  ({b - a:5.1f}s)")
        print("\nRe-record leaving a clearer pause between sections, or adjust SILENCE_DB /"
              "\nSILENCE_MIN at the top of this script and run it again. Nothing was written.")
        raise SystemExit(1)

    BACKUP.mkdir(parents=True, exist_ok=True)
    for old in A.glob("vo-*.mp3"):
        shutil.copy2(old, BACKUP / old.name)

    run_total = 0.0
    for (a, b), name in zip(segs, want, strict=True):
        dest = A / f"{name}.mp3"
        subprocess.run([FF, "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
                        "-i", str(src), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-ar", "48000", "-ac", "1", "-b:a", "192k", str(dest)],
                       check=True)
        d = duration(dest)
        run_total += d
        print(f"  {name:<38} {d:5.1f}s")

    print(f"\n  {'TOTAL':<38} {run_total:5.1f}s = {int(run_total // 60)}:{run_total % 60:04.1f}")
    if run_total > LIMIT:
        print(f"  OVER the 4:00 limit by {run_total - LIMIT:.0f}s. Trim the script or re-read"
              "\n  a little quicker; the originals are in video/assets/_tts-backup.")
    else:
        print(f"  {LIMIT - run_total:.0f}s under the 4:00 limit.")
    print("\nNow rebuild:  .venv/bin/python scripts/assemble_video.py")


if __name__ == "__main__":
    main()
