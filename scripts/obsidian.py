#!/usr/bin/env python3
"""Obsidian REST API helper module.

Provides read/write/list operations against the Obsidian Local REST API.
Used by all scripts and referenced by the orchestrator agent for curl patterns.

The Obsidian Local REST API plugin must be running:
https://github.com/coddingtonbear/obsidian-local-rest-api

Usage as CLI:
    python scripts/obsidian.py read "Content/example-newsletter/articles/slug/draft.md"
    python scripts/obsidian.py write "path/in/vault/file.md" --input local-file.md
    python scripts/obsidian.py list "Content/example-newsletter/articles/"
    python scripts/obsidian.py ensure-folder "Content/example-blog/articles/new-slug"

Usage as module:
    from scripts.obsidian import ObsidianClient
    client = ObsidianClient()
    content = client.read_note("path/to/note.md")
    client.write_note("path/to/note.md", "# Content here")
"""

import os
import sys
from pathlib import Path
from urllib.parse import quote

import click
import requests
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()


class ObsidianClient:
    """Client for the Obsidian Local REST API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.getenv("OBSIDIAN_REST_API_URL", "https://localhost:27124")).rstrip("/")
        self.api_key = api_key or os.getenv("OBSIDIAN_REST_API_KEY", "")
        if not self.api_key:
            raise ValueError("OBSIDIAN_REST_API_KEY not set. Check .env file.")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _vault_url(self, path: str) -> str:
        """Build the vault URL, encoding path segments.

        Preserves a trailing slash if present (required for folder listing).
        """
        trailing = "/" if path.endswith("/") else ""
        segments = path.strip("/").split("/")
        encoded = "/".join(quote(seg, safe="") for seg in segments)
        return f"{self.base_url}/vault/{encoded}{trailing}"

    def read_note(self, vault_path: str) -> str | None:
        """Read a note from the vault. Returns content or None if not found."""
        url = self._vault_url(vault_path)
        try:
            resp = requests.get(url, headers=self._headers(), verify=False, timeout=10)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 404:
                return None
            else:
                console.print(f"[red]Obsidian API error reading {vault_path}: {resp.status_code}[/red]")
                return None
        except requests.ConnectionError:
            console.print("[red]Cannot connect to Obsidian. Is the Local REST API plugin running?[/red]")
            return None

    def write_note(self, vault_path: str, content: str) -> bool:
        """Write (create or update) a note in the vault. Returns True on success."""
        url = self._vault_url(vault_path)
        try:
            resp = requests.put(
                url,
                headers={**self._headers(), "Content-Type": "text/markdown"},
                data=content.encode("utf-8"),
                verify=False,
                timeout=10,
            )
            if resp.status_code in (200, 204):
                return True
            else:
                console.print(f"[red]Obsidian API error writing {vault_path}: {resp.status_code}[/red]")
                return False
        except requests.ConnectionError:
            console.print("[red]Cannot connect to Obsidian. Is the Local REST API plugin running?[/red]")
            return False

    def write_binary(self, vault_path: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        """Write binary content (images, etc.) to the vault."""
        url = self._vault_url(vault_path)
        try:
            resp = requests.put(
                url,
                headers={**self._headers(), "Content-Type": content_type},
                data=data,
                verify=False,
                timeout=30,
            )
            if resp.status_code in (200, 204):
                return True
            console.print(f"[red]Obsidian API error writing binary {vault_path}: {resp.status_code}[/red]")
            return False
        except requests.ConnectionError:
            console.print("[red]Cannot connect to Obsidian.[/red]")
            return False

    def list_folder(self, vault_path: str) -> list[str] | None:
        """List files in a vault folder. Returns list of filenames or None on error."""
        url = self._vault_url(vault_path.rstrip("/") + "/")
        try:
            resp = requests.get(url, headers=self._headers(), verify=False, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # The API returns a dict with "files" key
                return data.get("files", [])
            elif resp.status_code == 404:
                return []
            else:
                console.print(f"[red]Obsidian API error listing {vault_path}: {resp.status_code}[/red]")
                return None
        except requests.ConnectionError:
            console.print("[red]Cannot connect to Obsidian. Is the Local REST API plugin running?[/red]")
            return None

    def ensure_folder(self, vault_path: str) -> bool:
        """Ensure a folder exists by writing a placeholder note if needed.

        Obsidian creates folders implicitly when you write a file into them.
        We write a minimal .gitkeep-style note to create the folder.
        """
        # Check if folder exists by listing it
        files = self.list_folder(vault_path)
        if files is not None and len(files) > 0:
            return True
        # Create folder by writing a placeholder
        placeholder_path = f"{vault_path.rstrip('/')}/.folder-created.md"
        return self.write_note(placeholder_path, "")

    def delete_note(self, vault_path: str) -> bool:
        """Delete a note from the vault."""
        url = self._vault_url(vault_path)
        try:
            resp = requests.delete(url, headers=self._headers(), verify=False, timeout=10)
            return resp.status_code in (200, 204, 404)
        except requests.ConnectionError:
            console.print("[red]Cannot connect to Obsidian.[/red]")
            return False


def load_profile(profile_id: str) -> dict:
    """Load a profile YAML by ID."""
    import yaml

    profile_path = Path(f"profiles/{profile_id}/profile.yaml")
    if not profile_path.exists():
        console.print(f"[red]Profile not found: {profile_path}[/red]")
        sys.exit(1)
    with open(profile_path) as f:
        return yaml.safe_load(f)


def get_vault_path(profile: dict, *subpaths: str) -> str:
    """Build a vault path from profile config and subpaths."""
    base = profile["obsidian"]["vault_base"]
    parts = [base] + list(subpaths)
    return "/".join(p.strip("/") for p in parts if p)


# ── CLI ───────────────────────────────────────────────────────────────────


@click.group()
def cli():
    """Obsidian vault operations via the Local REST API."""
    pass


@cli.command()
@click.argument("vault_path")
def read(vault_path: str):
    """Read a note from the vault."""
    client = ObsidianClient()
    content = client.read_note(vault_path)
    if content is not None:
        console.print(content)
    else:
        console.print(f"[yellow]Note not found: {vault_path}[/yellow]")
        sys.exit(1)


@cli.command()
@click.argument("vault_path")
@click.option("--input", "input_file", type=click.Path(exists=True), help="Read content from file")
@click.option("--content", "content_text", type=str, help="Content string to write")
def write(vault_path: str, input_file: str | None, content_text: str | None):
    """Write a note to the vault."""
    if input_file:
        content = Path(input_file).read_text()
    elif content_text:
        content = content_text
    else:
        content = sys.stdin.read()

    client = ObsidianClient()
    if client.write_note(vault_path, content):
        console.print(f"[green]Written: {vault_path}[/green]")
    else:
        sys.exit(1)


@cli.command("list")
@click.argument("vault_path")
def list_cmd(vault_path: str):
    """List files in a vault folder."""
    client = ObsidianClient()
    files = client.list_folder(vault_path)
    if files is not None:
        for f in files:
            console.print(f)
    else:
        sys.exit(1)


@cli.command("ensure-folder")
@click.argument("vault_path")
def ensure_folder_cmd(vault_path: str):
    """Ensure a folder exists in the vault."""
    client = ObsidianClient()
    if client.ensure_folder(vault_path):
        console.print(f"[green]Folder ready: {vault_path}[/green]")
    else:
        sys.exit(1)


if __name__ == "__main__":
    cli()
