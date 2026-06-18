#!/usr/bin/env python3
"""Migrate an existing article folder into the writers' room system.

Copies all files from a source folder into:
1. Obsidian vault at <profile.vault_base>/articles/<slug>/ (source of truth)
2. Local cache at cache/<profile>/articles/<slug>/ (git-tracked audit trail)

Handles both markdown and binary files (images, scripts).

Usage:
    python scripts/migrate_article.py --profile example-newsletter \\
        --source /path/to/output/my-article --slug my-article
"""

import mimetypes
import shutil
from pathlib import Path

import click
from rich.console import Console

from scripts.obsidian import ObsidianClient, load_profile, get_vault_path

console = Console()


def detect_content_type(filename: str) -> tuple[str, bool]:
    """Return (content_type, is_text) for a filename."""
    name = filename.lower()
    if name.endswith(".md") or name.endswith(".txt"):
        return "text/markdown", True
    if name.endswith(".py"):
        return "text/x-python", True
    if name.endswith(".png"):
        return "image/png", False
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return "image/jpeg", False
    guessed, _ = mimetypes.guess_type(name)
    if guessed and guessed.startswith("text/"):
        return guessed, True
    return guessed or "application/octet-stream", False


@click.command()
@click.option("--profile", required=True, help="Profile ID (e.g., example-newsletter)")
@click.option("--source", "source_path", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--slug", required=True, help="Target slug for the article")
@click.option("--dry-run", is_flag=True, help="Show what would be copied without doing it")
def migrate(profile: str, source_path: str, slug: str, dry_run: bool):
    """Migrate an article folder into Obsidian + local cache."""

    source = Path(source_path)
    prof = load_profile(profile)
    articles_folder = prof["obsidian"]["folders"]["articles"]

    # Target paths
    vault_article_path = get_vault_path(prof, articles_folder, slug)
    cache_article_dir = Path(f"cache/{profile}/articles/{slug}")

    console.print(f"[bold]Migrating:[/bold] {source}")
    console.print(f"  -> Obsidian: {vault_article_path}/")
    console.print(f"  -> Cache:    {cache_article_dir}/")

    files = sorted(f for f in source.iterdir() if f.is_file() and not f.name.startswith("."))
    console.print(f"  Files: {len(files)}")

    if dry_run:
        for f in files:
            ct, is_text = detect_content_type(f.name)
            console.print(f"    {f.name} ({ct}, {'text' if is_text else 'binary'}, {f.stat().st_size} bytes)")
        return

    # Ensure cache dir exists
    cache_article_dir.mkdir(parents=True, exist_ok=True)

    client = ObsidianClient()
    success = 0
    failed = []

    for f in files:
        content_type, is_text = detect_content_type(f.name)
        vault_path = f"{vault_article_path}/{f.name}"

        # Copy to cache first (always works)
        cache_target = cache_article_dir / f.name
        shutil.copy2(f, cache_target)

        # Upload to Obsidian
        if is_text:
            content = f.read_text()
            ok = client.write_note(vault_path, content)
        else:
            data = f.read_bytes()
            ok = client.write_binary(vault_path, data, content_type)

        if ok:
            success += 1
            console.print(f"  [green]OK[/green]  {f.name}")
        else:
            failed.append(f.name)
            console.print(f"  [red]FAIL[/red] {f.name}")

    console.print(f"\n[bold]Done:[/bold] {success}/{len(files)} uploaded to Obsidian")
    console.print(f"All {len(files)} files cached locally at {cache_article_dir}")
    if failed:
        console.print(f"[red]Failed: {', '.join(failed)}[/red]")


if __name__ == "__main__":
    migrate()
