#!/usr/bin/env python3
"""Publish an article from the writers' room.

Reads the article from Obsidian (or local cache) and publishes to the
platform configured in the active profile.

Usage:
    python scripts/publish.py --profile example-newsletter --slug fuel-reserve --title "Title"
    python scripts/publish.py --profile example-newsletter --file cache/example-newsletter/articles/slug/draft.md --title "Title"
    python scripts/publish.py --profile example-newsletter --slug fuel-reserve --title "Title" --draft-only
"""

import os
import sys
import re
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Confirm

load_dotenv()
console = Console()


def markdown_to_substack_body(markdown_text: str) -> list[dict]:
    """Convert markdown text to Substack's ProseMirror document format."""
    body_parts = []
    lines = markdown_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line.startswith("#"):
            level = len(line.split(" ")[0])
            text = line.lstrip("#").strip()
            body_parts.append({
                "type": "heading",
                "attrs": {"level": min(level, 3)},
                "content": _parse_inline(text),
            })
        elif line in ("---", "***", "___"):
            body_parts.append({"type": "horizontal_rule"})
        elif line.startswith(">"):
            text = line.lstrip(">").strip()
            body_parts.append({
                "type": "blockquote",
                "content": [
                    {"type": "paragraph", "content": _parse_inline(text)}
                ],
            })
        else:
            para_lines = [line]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().startswith(("#", ">", "---", "***", "___")):
                i += 1
                para_lines.append(lines[i].strip())
            text = " ".join(para_lines)
            body_parts.append({
                "type": "paragraph",
                "content": _parse_inline(text),
            })

        i += 1

    return body_parts


def _parse_inline(text: str) -> list[dict]:
    """Parse inline markdown (bold, italic, links) into ProseMirror content nodes."""
    nodes = []
    remaining = text

    while remaining:
        bold_match = re.search(r"\*\*(.+?)\*\*", remaining)
        italic_match = re.search(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", remaining)
        link_match = re.search(r"\[(.+?)\]\((.+?)\)", remaining)

        matches = []
        if bold_match:
            matches.append(("bold", bold_match))
        if italic_match:
            matches.append(("italic", italic_match))
        if link_match:
            matches.append(("link", link_match))

        if not matches:
            if remaining:
                nodes.append({"type": "text", "text": remaining})
            break

        matches.sort(key=lambda m: m[1].start())
        match_type, match = matches[0]

        before = remaining[: match.start()]
        if before:
            nodes.append({"type": "text", "text": before})

        if match_type == "bold":
            nodes.append({
                "type": "text",
                "text": match.group(1),
                "marks": [{"type": "strong"}],
            })
        elif match_type == "italic":
            nodes.append({
                "type": "text",
                "text": match.group(1),
                "marks": [{"type": "em"}],
            })
        elif match_type == "link":
            nodes.append({
                "type": "text",
                "text": match.group(1),
                "marks": [{"type": "link", "attrs": {"href": match.group(2)}}],
            })

        remaining = remaining[match.end():]

    return nodes if nodes else [{"type": "text", "text": text}]


def publish_substack(content: str, title: str, subtitle: str, draft_only: bool, audience: str):
    """Publish to Substack using python-substack library."""
    pub_url = os.getenv("SUBSTACK_PUBLICATION_URL")
    cookies_path = os.getenv("SUBSTACK_COOKIES_PATH")
    user_id = os.getenv("SUBSTACK_USER_ID")

    if not all([pub_url, cookies_path, user_id]):
        console.print("[red]Missing Substack env vars. Check .env file.[/red]")
        console.print("Required: SUBSTACK_PUBLICATION_URL, SUBSTACK_COOKIES_PATH, SUBSTACK_USER_ID")
        return

    try:
        from substack import Api
        from substack.post import Post

        api = Api(email=None, password=None, publication_url=pub_url)
        api.cookies_path = cookies_path

        post = Post(title=title, subtitle=subtitle, user_id=user_id, audience=audience)
        body_parts = markdown_to_substack_body(content)
        for part in body_parts:
            post.add(part)

        draft = api.post_draft(post.get_draft())
        draft_id = draft.get("id")
        console.print(f"[green]Draft created: {draft_id}[/green]")
        console.print(f"Edit at: {pub_url}/publish/post/{draft_id}")

        if not draft_only:
            if Confirm.ask("Publish now?"):
                api.prepublish_draft(draft_id)
                api.publish_draft(draft_id)
                console.print("[bold green]Published![/bold green]")
            else:
                console.print("[yellow]Saved as draft.[/yellow]")

    except ImportError:
        console.print("[red]python-substack not installed. Run: pip install python-substack[/red]")
    except Exception as e:
        console.print(f"[red]Publishing failed: {e}[/red]")


def publish_linkedin(content: str, title: str):
    """LinkedIn publishing — currently copy-to-clipboard."""
    console.print("[bold]LinkedIn Post Preview:[/bold]\n")
    console.print(content)
    console.print("\n[yellow]LinkedIn API publishing not yet implemented.[/yellow]")
    console.print("[dim]Copy the text above and paste into LinkedIn.[/dim]")


@click.command()
@click.option("--profile", required=True, help="Profile ID (e.g., example-newsletter, example-blog)")
@click.option("--slug", type=str, help="Article slug (reads from Obsidian/cache)")
@click.option("--file", "filepath", type=click.Path(exists=True), help="Direct file path (overrides slug)")
@click.option("--title", required=True)
@click.option("--subtitle", default="")
@click.option("--draft-only", is_flag=True, help="Create draft without publishing")
@click.option("--audience", type=click.Choice(["everyone", "only_paid", "only_free"]), default="everyone")
def publish(profile: str, slug: str, filepath: str, title: str, subtitle: str, draft_only: bool, audience: str):
    """Publish an article using the configured platform."""
    import yaml
    from scripts.obsidian import load_profile, get_vault_path, ObsidianClient

    prof = load_profile(profile)
    platform_type = prof.get("platform", {}).get("type", "unknown")

    # Get content
    if filepath:
        content = Path(filepath).read_text()
    elif slug:
        # Try cache first, then Obsidian
        cache_path = Path(f"cache/{profile}/articles/{slug}/draft.md")
        if cache_path.exists():
            content = cache_path.read_text()
        else:
            client = ObsidianClient()
            vault_path = get_vault_path(prof, prof["obsidian"]["folders"]["articles"], slug, "draft.md")
            content = client.read_note(vault_path)
            if not content:
                console.print(f"[red]Article not found: {slug}[/red]")
                return
    else:
        console.print("[red]Provide --slug or --file[/red]")
        return

    word_count = len(content.split())
    console.print(f"[bold]Article: {title}[/bold]")
    console.print(f"Profile: {profile} ({platform_type})")
    console.print(f"Words: {word_count}")

    if not Confirm.ask("Proceed?"):
        return

    if platform_type == "substack":
        publish_substack(content, title, subtitle, draft_only, audience)
    elif platform_type == "linkedin":
        publish_linkedin(content, title)
    else:
        console.print(f"[yellow]Unknown platform: {platform_type}. Displaying content:[/yellow]")
        console.print(content)


if __name__ == "__main__":
    publish()
