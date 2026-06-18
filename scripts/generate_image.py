#!/usr/bin/env python3
"""Generate a header image for an article.

Reads image specs from the active profile and generates via
FLUX 2 Pro, GPT Image, or Ideogram.

Usage:
    python scripts/generate_image.py --profile example-newsletter --slug fuel-reserve
    python scripts/generate_image.py --profile example-newsletter --slug fuel-reserve --engine openai
    python scripts/generate_image.py --prompt "A direct prompt..." --engine flux
"""

import os
import base64
from pathlib import Path

import click
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

load_dotenv()
console = Console()


def generate_with_flux(prompt: str, width: int, height: int, negative_prompt: str = "") -> str | None:
    """Generate image using FLUX 2 Pro via fal.ai."""
    api_key = os.getenv("FAL_API_KEY")
    if not api_key:
        console.print("[red]FAL_API_KEY not set in .env[/red]")
        return None

    response = requests.post(
        "https://queue.fal.run/fal-ai/flux-pro/v1.1",
        headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
        json={
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "num_images": 1,
            "enable_safety_checker": True,
        },
    )

    if response.status_code == 200:
        return response.json().get("images", [{}])[0].get("url")
    console.print(f"[red]FLUX API error: {response.status_code} {response.text}[/red]")
    return None


def generate_with_openai(prompt: str, width: int, height: int) -> str | None:
    """Generate image using GPT Image via OpenAI API."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]OPENAI_API_KEY not set in .env[/red]")
        return None

    # Map to closest supported size
    if width > height:
        size = "1536x1024"
    elif height > width:
        size = "1024x1536"
    else:
        size = "1024x1024"

    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "gpt-image-1", "prompt": prompt, "n": 1, "size": size, "quality": "high"},
    )

    if response.status_code == 200:
        result = response.json()
        b64_data = result["data"][0].get("b64_json")
        if b64_data:
            output_path = Path("cache") / "header-image.png"
            output_path.write_bytes(base64.b64decode(b64_data))
            console.print(f"[green]Image saved to {output_path}[/green]")
            return str(output_path)
        return result["data"][0].get("url")
    console.print(f"[red]OpenAI API error: {response.status_code} {response.text}[/red]")
    return None


def generate_with_ideogram(prompt: str, width: int, height: int) -> str | None:
    """Generate image using Ideogram v3 API."""
    api_key = os.getenv("IDEOGRAM_API_KEY")
    if not api_key:
        console.print("[red]IDEOGRAM_API_KEY not set in .env[/red]")
        return None

    # Determine aspect ratio
    ratio = width / height
    if abs(ratio - 16 / 9) < 0.1:
        aspect = "ASPECT_16_9"
    elif abs(ratio - 1.91) < 0.1:
        aspect = "ASPECT_16_9"  # closest available
    else:
        aspect = "ASPECT_1_1"

    response = requests.post(
        "https://api.ideogram.ai/generate",
        headers={"Api-Key": api_key, "Content-Type": "application/json"},
        json={"image_request": {"prompt": prompt, "aspect_ratio": aspect, "model": "V_3", "style_type": "DESIGN"}},
    )

    if response.status_code == 200:
        return response.json().get("data", [{}])[0].get("url")
    console.print(f"[red]Ideogram API error: {response.status_code} {response.text}[/red]")
    return None


ENGINES = {
    "flux": generate_with_flux,
    "openai": generate_with_openai,
    "ideogram": generate_with_ideogram,
}


def download_image(url: str, output_dir: Path, filename: str = "header-image.png") -> Path:
    """Download image from URL."""
    output_path = output_dir / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url)
    output_path.write_bytes(response.content)
    return output_path


@click.command()
@click.option("--profile", type=str, help="Profile ID for image specs")
@click.option("--slug", type=str, help="Article slug (reads image-brief from cache/Obsidian)")
@click.option("--article", type=click.Path(exists=True), help="Direct article path")
@click.option("--prompt", type=str, help="Direct image prompt")
@click.option("--engine", type=click.Choice(list(ENGINES.keys())), default="flux")
@click.option("--output", type=str, default="header-image.png")
def generate(profile: str, slug: str, article: str, prompt: str, engine: str, output: str):
    """Generate a header image for an article."""

    # Get image dimensions from profile or defaults
    width, height = 1456, 816
    if profile:
        import yaml
        from scripts.obsidian import load_profile
        prof = load_profile(profile)
        image_specs = prof.get("platform", {}).get("image_specs", {})
        width = image_specs.get("width", width)
        height = image_specs.get("height", height)

    if not prompt:
        # Try to find image brief
        brief_path = None
        if slug and profile:
            brief_path = Path(f"cache/{profile}/articles/{slug}/image-brief.md")
        elif article:
            brief_path = Path(article).parent / "image-brief.md"

        if brief_path and brief_path.exists():
            image_brief = brief_path.read_text()
            console.print(Panel(image_brief, title="Image Brief", border_style="magenta"))

            # Extract prompt from code block
            lines = image_brief.split("\n")
            in_block = False
            prompt_lines = []
            for line in lines:
                if "```" in line and in_block:
                    in_block = False
                    continue
                if in_block:
                    prompt_lines.append(line)
                if "```" in line and not in_block:
                    in_block = True

            if prompt_lines:
                prompt = "\n".join(prompt_lines).strip()
            else:
                console.print("[yellow]Couldn't extract prompt. Paste it:[/yellow]")
                prompt = input("> ")
        else:
            console.print("[red]No image brief found. Provide --prompt, --slug, or --article[/red]")
            return

    console.print(f"\n[bold]Generating with {engine}...[/bold]")
    console.print(f"Dimensions: {width}x{height}")
    console.print(f"[dim]Prompt: {prompt[:100]}...[/dim]\n")

    if not Confirm.ask("Generate image?"):
        return

    generate_fn = ENGINES[engine]
    # flux and ideogram support width/height; openai maps internally
    if engine == "flux":
        result = generate_fn(prompt, width, height)
    elif engine == "openai":
        result = generate_fn(prompt, width, height)
    else:
        result = generate_fn(prompt, width, height)

    if result:
        if result.startswith("http"):
            output_dir = Path(f"cache/{profile}/articles/{slug}") if (profile and slug) else Path("cache")
            local_path = download_image(result, output_dir, output)
            console.print(f"[bold green]Image saved to {local_path}[/bold green]")
        else:
            console.print(f"[bold green]Image ready: {result}[/bold green]")
    else:
        console.print("[red]Image generation failed.[/red]")


if __name__ == "__main__":
    generate()
