#!/usr/bin/env python3
"""Mine ideas from comments across platforms.

Scrapes the user's recent comments from configured platforms and saves them
for the idea-miner agent to analyse.

Usage:
    python scripts/mine_ideas.py --profile example-newsletter
    python scripts/mine_ideas.py --profile example-newsletter --disqus-only
    python scripts/mine_ideas.py --profile example-newsletter --since 2026-03-01
    python scripts/mine_ideas.py --profile example-newsletter --from-file comments.txt
"""

import os
import sys
import json
import re
from datetime import datetime
from pathlib import Path

import click
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()
console = Console()


def scrape_disqus_comments(username: str, limit: int = 50) -> list[dict]:
    """Fetch comments from Disqus public API."""
    api_key = os.getenv("DISQUS_API_KEY")
    comments = []

    if api_key:
        url = "https://disqus.com/api/3.0/users/listPosts.json"
        params = {
            "api_key": api_key,
            "user": f"username:{username}",
            "limit": limit,
            "related": "thread",
        }
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for post in data.get("response", []):
                    thread = post.get("thread", {})
                    comments.append({
                        "platform": "disqus",
                        "text": _strip_html(post.get("raw_message", post.get("message", ""))),
                        "date": post.get("createdAt", ""),
                        "article_title": thread.get("title", "Unknown"),
                        "article_url": thread.get("link", ""),
                        "likes": post.get("likes", 0),
                        "forum": post.get("forum", ""),
                    })
                console.print(f"[green]Fetched {len(comments)} comments from Disqus API[/green]")
                return comments
        except Exception as e:
            console.print(f"[yellow]Disqus API failed: {e}[/yellow]")

    console.print("[yellow]No Disqus API key or API failed. Using cached data if available.[/yellow]")
    cache_path = Path("cache/disqus-comments.txt")
    if cache_path.exists():
        comments = _parse_cached_comments(cache_path, "disqus")
    return comments


def scrape_substack_activity(cookies_path: str, limit: int = 50) -> list[dict]:
    """Fetch comment activity from Substack using session cookies."""
    comments = []

    if not Path(cookies_path).exists():
        console.print("[yellow]No Substack cookies found. Using cached data.[/yellow]")
        cache_path = Path("cache/substack-comments.txt")
        if cache_path.exists():
            comments = _parse_cached_comments(cache_path, "substack")
        return comments

    try:
        with open(cookies_path) as f:
            cookies_data = json.load(f)

        cookie_dict = {c["name"]: c["value"] for c in cookies_data}

        session = requests.Session()
        session.cookies.update(cookie_dict)
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        response = session.get(
            "https://substack.com/api/v1/reader/activity_feed",
            params={"limit": limit, "types": "comment"},
            timeout=15,
        )

        if response.status_code == 200:
            data = response.json()
            for item in data.get("items", []):
                comment_body = item.get("body", "") or item.get("comment", {}).get("body", "")
                comments.append({
                    "platform": "substack",
                    "text": _strip_html(comment_body),
                    "date": item.get("date", ""),
                    "article_title": item.get("post", {}).get("title", "Unknown"),
                    "article_url": item.get("post", {}).get("canonical_url", ""),
                    "likes": item.get("reactions", {}).get("\u2764", 0),
                })
            console.print(f"[green]Fetched {len(comments)} comments from Substack[/green]")
        else:
            console.print(f"[yellow]Substack API returned {response.status_code}[/yellow]")

    except Exception as e:
        console.print(f"[yellow]Substack scrape failed: {e}[/yellow]")
        cache_path = Path("cache/substack-comments.txt")
        if cache_path.exists():
            comments = _parse_cached_comments(cache_path, "substack")

    return comments


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    clean = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", clean).strip()


def _parse_cached_comments(path: Path, platform: str) -> list[dict]:
    """Parse a cached plain-text comment dump."""
    comments = []
    content = path.read_text()

    for block in content.split("---"):
        block = block.strip()
        if not block:
            continue

        comment = {"platform": platform, "text": "", "article_title": "", "date": "", "likes": 0}
        text_lines = []
        for line in block.split("\n"):
            if line.startswith("Article:"):
                comment["article_title"] = line.split(":", 1)[1].strip()
            elif line.startswith("Date:"):
                comment["date"] = line.split(":", 1)[1].strip()
            elif line.startswith("Likes:"):
                try:
                    comment["likes"] = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("URL:"):
                comment["article_url"] = line.split(":", 1)[1].strip()
            else:
                text_lines.append(line)

        comment["text"] = "\n".join(text_lines).strip()
        if comment["text"]:
            comments.append(comment)

    return comments


def format_comments(comments: list[dict]) -> str:
    """Format comments for the idea-miner agent."""
    if not comments:
        return "No comments found."

    output = []
    for i, c in enumerate(comments, 1):
        likes_str = f" ({c.get('likes', 0)} likes)" if c.get("likes") else ""
        output.append(
            f"### Comment {i} [{c['platform'].upper()}]{likes_str}\n"
            f"**On**: {c.get('article_title', 'Unknown')}\n"
            f"**Date**: {c.get('date', 'Unknown')}\n"
            f"**Comment**: {c['text']}\n"
        )

    return "\n---\n".join(output)


@click.command()
@click.option("--profile", required=True, help="Profile ID")
@click.option("--disqus-only", is_flag=True)
@click.option("--substack-only", is_flag=True)
@click.option("--from-file", type=click.Path(exists=True), help="Load comments from file")
@click.option("--since", type=str, default=None, help="Only comments after date (YYYY-MM-DD)")
@click.option("--limit", type=int, default=50)
@click.option("--output", type=str, default=None, help="Output file (default: cache/<profile>/ideas/mined-ideas.md)")
def mine(profile: str, disqus_only: bool, substack_only: bool, from_file: str, since: str, limit: int, output: str):
    """Mine article ideas from comments across platforms."""
    import yaml
    from scripts.obsidian import load_profile

    prof = load_profile(profile)
    idea_sources = prof.get("idea_sources", {})
    comment_sources = idea_sources.get("comment_mining", [])

    if not comment_sources and not from_file:
        console.print(f"[yellow]No comment sources configured for profile '{profile}'.[/yellow]")
        return

    console.print(Panel(f"Writers' Room — Idea Mining ({profile})", style="bold yellow"))

    all_comments = []

    if from_file:
        platform = "disqus" if "disqus" in from_file.lower() else "substack"
        all_comments = _parse_cached_comments(Path(from_file), platform)
        console.print(f"[green]Loaded {len(all_comments)} comments from {from_file}[/green]")
    else:
        for source in comment_sources:
            platform = source.get("platform", "")
            if disqus_only and platform != "disqus":
                continue
            if substack_only and platform != "substack":
                continue

            if platform == "disqus":
                username = source.get("username", os.getenv("DISQUS_USERNAME", ""))
                if username:
                    console.print("[bold]Checking Disqus...[/bold]")
                    all_comments.extend(scrape_disqus_comments(username, limit))
            elif platform == "substack":
                cookies = os.getenv("SUBSTACK_COOKIES_PATH", "./cookies.json")
                console.print("[bold]Checking Substack...[/bold]")
                all_comments.extend(scrape_substack_activity(cookies, limit))

    if not all_comments:
        console.print("[red]No comments found.[/red]")
        return

    # Date filter
    if since:
        since_date = datetime.strptime(since, "%Y-%m-%d")
        filtered = []
        for c in all_comments:
            try:
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d %b %Y"]:
                    try:
                        if datetime.strptime(c["date"][:10], fmt) >= since_date:
                            filtered.append(c)
                            break
                    except ValueError:
                        continue
                else:
                    filtered.append(c)
            except Exception:
                filtered.append(c)
        all_comments = filtered

    console.print(f"\n[bold]Found {len(all_comments)} comments to analyse[/bold]\n")

    comments_text = format_comments(all_comments)

    output_path = Path(output) if output else Path(f"cache/{profile}/ideas/mined-ideas.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# Writers' Room — Scraped Comments ({profile})\n\n"
        f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"> Comments scraped: {len(all_comments)}\n\n"
    )
    output_path.write_text(header + comments_text)
    console.print(f"\n[green]Comments saved to {output_path}[/green]")
    console.print(f"[dim]Use the orchestrator or idea-miner agent to analyse these.[/dim]")


if __name__ == "__main__":
    mine()
