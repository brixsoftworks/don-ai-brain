"""tools/media/tools.py — media tools: yt-dlp downloads, RSS/podcasts.

yt-dlp handles 1000+ sites keyless. feedparser for RSS aggregation.
See docs/component-5 §7.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from langchain_core.tools import tool

log = logging.getLogger("don.tools.media")


@tool
def yt_download(
    url: str,
    format: str = "best",
    output_dir: str = "~/jarvishome/media",
) -> str:
    """Download a video/audio from YouTube or other sites via yt-dlp.

    Args:
        url: video/audio URL (YouTube, Vimeo, etc.).
        format: download format (best, worst, audio, or specific format code).
        output_dir: directory to save the file.
    """
    try:
        import yt_dlp

        output_dir = os.path.expanduser(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        ydl_opts = {
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        if format == "audio":
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            ydl_opts["format"] = format

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "unknown")
            filename = ydl.prepare_filename(info)
            return f"[downloaded: {title} → {filename}]"
    except ImportError:
        return "[yt-dlp not installed. pip install yt-dlp]"
    except Exception as exc:  # noqa: BLE001
        log.error("yt_download failed: %s", exc)
        return f"[yt-dlp error: {exc}]"


@tool
def yt_info(
    url: str,
) -> str:
    """Get metadata about a video without downloading.

    Args:
        url: video URL.
    """
    try:
        import yt_dlp

        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return json.dumps({
                "title": info.get("title"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "description": (info.get("description") or "")[:500],
                "view_count": info.get("view_count"),
            }, indent=2, ensure_ascii=False)
    except ImportError:
        return "[yt-dlp not installed]"
    except Exception as exc:  # noqa: BLE001
        log.error("yt_info failed: %s", exc)
        return f"[yt-dlp error: {exc}]"


@tool
def rss_read(
    feed_url: str,
    max_entries: int = 10,
) -> str:
    """Read an RSS/Atom feed and return recent entries.

    Args:
        feed_url: RSS or Atom feed URL.
        max_entries: maximum entries to return.
    """
    try:
        import feedparser

        feed = feedparser.parse(feed_url)
        entries = feed.entries[:max_entries]
        lines = []
        for entry in entries:
            title = entry.get("title", "untitled")
            link = entry.get("link", "")
            summary = entry.get("summary", "")[:200]
            published = entry.get("published", "")
            lines.append(f"- [{title}]({link})\n  {published}\n  {summary}")
        return "\n\n".join(lines) if lines else f"No entries in {feed_url}"
    except ImportError:
        return "[feedparser not installed. pip install feedparser]"
    except Exception as exc:  # noqa: BLE001
        log.error("rss_read failed: %s", exc)
        return f"[rss error: {exc}]"


TOOLS = [yt_download, yt_info, rss_read]
