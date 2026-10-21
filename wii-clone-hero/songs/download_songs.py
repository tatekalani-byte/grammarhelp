"""Download the charts in setlist.json from Chorus Encore into Clone Hero's Songs folder.

Each chart is one .sng file, which Clone Hero reads directly. Songs that are
already in the folder are skipped, so it's safe to stop (Ctrl+C) and run again.

    python download_songs.py                 # every song in the list
    python download_songs.py --from 60       # start at song 60
    python download_songs.py --official-only # only official Guitar Hero / Rock Band charts
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHART_URL = "https://files.enchor.us/{md5}{suffix}.sng"
FOLDER_NAME = "This is what I sound like"
PAUSE_BETWEEN_DOWNLOADS = 0.5


def documents_folder() -> Path:
    """The real Documents folder, which OneDrive often moves."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        csidl_personal = 5
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl_personal, None, 0, buf) == 0:
            return Path(buf.value)
    return Path.home() / "Documents"


def find_songs_folder(given: str | None) -> Path:
    if given:
        return Path(given.strip().strip('"'))
    default = documents_folder() / "Clone Hero" / "Songs"
    if default.is_dir():
        return default
    print(f"Couldn't find Clone Hero's Songs folder at {default}.")
    print("Clone Hero's settings list your song folders if you're not sure where it is.")
    answer = input("Paste the Songs folder path here (or drag the folder onto this window) and press Enter: ")
    return Path(answer.strip().strip('"'))


def safe_filename(artist: str, title: str) -> str:
    name = f"{artist} - {title}"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return name[:150] + ".sng"


def download(md5: str, destination: Path) -> int:
    """Save one chart, preferring the smaller no-video version. Returns bytes written."""
    part = destination.with_suffix(".part")
    last_error = None
    for suffix in ("_novideo", ""):  # _novideo only exists for charts with a video
        request = urllib.request.Request(CHART_URL.format(md5=md5, suffix=suffix),
                                         headers={"User-Agent": "clone-hero-setlist-downloader"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, open(part, "wb") as out:
                expected = int(response.headers.get("Content-Length") or 0)
                shutil.copyfileobj(response, out, 1024 * 1024)
            size = part.stat().st_size
            if expected and size != expected:
                raise OSError(f"download was cut off ({size} of {expected} bytes)")
            part.replace(destination)
            return size
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 404:
                break
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            break
        finally:
            if part.exists():
                part.unlink()
    raise OSError(str(last_error))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="start", type=int, default=1, help="song number to start at")
    parser.add_argument("--official-only", action="store_true", help="only official GH / Rock Band charts")
    parser.add_argument("--songs-folder", help="Clone Hero's Songs folder (found automatically if left out)")
    args = parser.parse_args(argv)

    setlist = json.loads((HERE / "setlist.json").read_text(encoding="utf-8"))
    songs = [s for s in setlist["songs"] if s["n"] >= args.start and (s["official"] or not args.official_only)]
    if not songs:
        print("No songs match those choices.")
        return 1

    target = find_songs_folder(args.songs_folder) / FOLDER_NAME
    target.mkdir(parents=True, exist_ok=True)
    todo = [s for s in songs if not (target / safe_filename(s["artist"], s["title"])).exists()]
    print(f"Saving to: {target}")
    print(f"{len(songs)} songs chosen, {len(songs) - len(todo)} already there, {len(todo)} to download.")
    if not todo:
        print("Nothing to do. Rescan your songs in Clone Hero's settings to see them.")
        return 0

    free_gb = shutil.disk_usage(target).free / 1e9
    print(f"Songs are usually 5-30 MB each. Free space on that drive: {free_gb:.1f} GB.")
    if free_gb < len(todo) * 0.03:
        print("That may not be enough for all of them. It will stop if the drive fills up.")
    print("Press Ctrl+C to stop at any time; running it again carries on where it left off.\n")

    failed = []
    total = 0
    for i, song in enumerate(todo, 1):
        name = safe_filename(song["artist"], song["title"])
        print(f"[{i}/{len(todo)}] #{song['n']} {song['artist']} - {song['title']} ... ", end="", flush=True)
        try:
            size = download(song["md5"], target / name)
        except OSError as exc:
            print(f"failed ({exc})")
            failed.append(song)
            if "No space left" in str(exc) or getattr(exc, "errno", None) == 28:
                break
            continue
        total += size
        print(f"{size / 1e6:.0f} MB")
        time.sleep(PAUSE_BETWEEN_DOWNLOADS)

    print(f"\nDownloaded {len(todo) - len(failed)} songs ({total / 1e9:.1f} GB) into {target}")
    if failed:
        print(f"{len(failed)} failed. Run this again to retry them:")
        for song in failed:
            print(f"  #{song['n']} {song['artist']} - {song['title']}")
    print("Now open Clone Hero and rescan your songs from its settings menu.")
    return 0 if not failed else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped. Run it again to carry on where you left off.")
        sys.exit(130)
