"""Bounded OpenCode runner for the Bullpen editorial pipeline.

Each editorial stage gets a fresh OpenCode process. A stalled stage cannot consume
or falsely complete the rest of the pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.bullpen_runtime.model_policy import (
    load_model_policy,
    validate_model_policy,
)
from scripts.publication import MARKER

PIPELINE_STAGES = ("research", "draft", "trimmer", "safety")
STAGE_ROLES = {
    "research": "researcher",
    "draft": "drafter",
    "trimmer": "trimmer",
    "safety": "safety-reviewer",
}
class PipelineError(RuntimeError):
    """Raised when a stage fails or does not produce its required artefact."""


def load_stage_routes(policy_path: str | Path) -> dict[str, list[dict[str, str]]]:
    """Resolve ordered primary/fallback routes for each bounded stage."""
    policy = load_model_policy(policy_path)
    validate_model_policy(policy)
    resolved: dict[str, list[dict[str, str]]] = {}
    for stage, role in STAGE_ROLES.items():
        config = policy["roles"][role]
        routes: list[dict[str, str]] = []
        for route_name in ("primary", "fallback", "escalation", "last_resort"):
            route = config.get(route_name)
            if not route:
                continue
            candidates = route if isinstance(route, list) else [route]
            for candidate in candidates:
                item = {
                    "provider": str(candidate["provider"]),
                    "model": str(candidate["model"]),
                }
                if item not in routes:
                    routes.append(item)
        if not routes:
            raise PipelineError(f"model policy has no route for {role}")
        resolved[stage] = routes
    return resolved


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stage_target(article_dir: Path, stage: str) -> Path:
    return article_dir / ("research.md" if stage == "research" else "draft.md")


def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _override_prompt(profile_text: str, role: str) -> str | None:
    """Return a role's profile-relative override prompt without full YAML deps."""
    agents = re.search(r"(?ms)^agents:\s*\n(?P<body>(?:^[ \t]+.*\n?)*)", profile_text)
    if not agents:
        return None
    section = re.search(
        rf"(?ms)^  {re.escape(role)}:\s*\n(?P<body>(?:^    .*\n?)*)",
        agents.group("body"),
    )
    if not section:
        return None
    match = re.search(
        r"(?m)^\s{4}override_prompt:\s*['\"]?([^'\"#\n]+)",
        section.group("body"),
    )
    return match.group(1).strip() if match else None


def _contained_path(root: Path, relative_path: str, *, label: str) -> Path:
    """Resolve a configured path and require it to remain below root."""
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise PipelineError(f"{label} must be relative to {root}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise PipelineError(f"{label} escapes {resolved_root}") from exc
    return resolved


def _prompt(stage: str, article_dir: Path, profile: str, repo: Path) -> str:
    profiles_root = (repo / "profiles").resolve()
    profile_dir = _contained_path(profiles_root, profile, label="profile")
    profile_text = _read_optional(profile_dir / "profile.yaml")
    research_text = _read_optional(article_dir / "research.md")
    draft_text = _read_optional(article_dir / "draft.md")
    drafter_override = _override_prompt(profile_text, "drafter")
    safety_override = _override_prompt(profile_text, "safety")
    persona = (
        _read_optional(_contained_path(profile_dir, drafter_override, label="drafter override"))
        if drafter_override
        else ""
    )
    safety = (
        _read_optional(_contained_path(profile_dir, safety_override, label="safety override"))
        if safety_override
        else ""
    )
    target_text = research_text if stage == "research" else draft_text
    instructions = {
        "research": "Verify claim/source discipline and append a concise dated verification note.",
        "draft": (
            "Revise the draft using the research, profile and persona. Preserve frontmatter, links, "
            "the exact publication marker, and existing pipeline notes."
        ),
        "trimmer": (
            "Trim public copy above the marker. Preserve facts, links, frontmatter and marker. "
            "Leave zero em-dashes and exactly one ### Trimmer subsection with before/after counts."
        ),
        "safety": (
            "Apply employer/publication-risk corrections. Attribute vendor claims. Preserve frontmatter, "
            "links and marker. Leave exactly one ### Safety subsection with risk, edits and blockers."
        ),
    }[stage]
    return f"""Execute ONE STAGE ONLY: {stage}.
Do not call tools. Do not read or write files. All required input is included below.
Return the complete replacement contents for the target file between these exact sentinels:
<<<WR_OUTPUT>>>
<complete file>
<<<END_WR_OUTPUT>>>
Do not include commentary outside the sentinels. Never publish.

STAGE INSTRUCTIONS
{instructions}

PROFILE
{profile_text}

PERSONA
{persona if stage == 'draft' else ''}

SAFETY OVERRIDE
{safety if stage == 'safety' else ''}

RESEARCH
{research_text}

CURRENT TARGET
{target_text}
"""


def _extract_text_events(output: str) -> str:
    chunks = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            text = event.get("part", {}).get("text")
            if text:
                chunks.append(text)
    return "".join(chunks)


def _extract_replacement(output: str, *, json_output: bool) -> str:
    text = _extract_text_events(output) if json_output else output
    match = re.search(r"<<<WR_OUTPUT>>>\s*(.*?)\s*<<<END_WR_OUTPUT>>>", text, re.S)
    if not match:
        raise PipelineError("stage returned no bounded replacement output")
    return match.group(1).rstrip() + "\n"


def _invoke_route(
    route: dict[str, str],
    *,
    stage: str,
    prompt: str,
    repo: Path,
    timeout: int,
) -> tuple[str, bool]:
    provider = route["provider"]
    model = route["model"]
    if provider == "claude-pro-sidecar":
        command = ["claude", "-p", "--model", model, prompt]
        json_output = False
    elif provider in {"openrouter", "openai-chatgpt", "anthropic-api"}:
        command = [
            "opencode",
            "run",
            "--format",
            "json",
            "--agent",
            f"bullpen-{stage}",
            "--model",
            model,
            prompt,
        ]
        json_output = True
    else:
        raise PipelineError(f"unsupported provider runtime: {provider}")
    try:
        result = subprocess.run(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(f"{provider}/{model} timed out after {timeout}s") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1000:]
        raise PipelineError(f"{provider}/{model} failed ({result.returncode}): {detail}")
    return result.stdout, json_output


def _verify_stage(article_dir: Path, stage: str, before: str) -> None:
    target = _stage_target(article_dir, stage)
    if not target.exists() or _digest(target) == before:
        raise PipelineError(f"{stage} produced no verified file change: {target}")
    text = target.read_text(encoding="utf-8")
    if stage != "research":
        if text.count(MARKER) != 1:
            raise PipelineError(f"{stage} damaged the publication marker")
        if text.split(MARKER, 1)[0].count("—"):
            raise PipelineError(f"{stage} left em-dashes in public copy")
    if stage == "trimmer" and text.count("### Trimmer") != 1:
        raise PipelineError("trimmer must leave exactly one Trimmer note")
    if stage == "safety" and text.count("### Safety") != 1:
        raise PipelineError("safety must leave exactly one Safety note")


def run_stage(
    stage: str,
    *,
    article_dir: Path,
    profile: str,
    timeout: int,
    routes: list[dict[str, str]],
    repo: Path,
) -> dict[str, Any]:
    if stage not in PIPELINE_STAGES:
        raise PipelineError(f"unsupported stage: {stage}")
    target = _stage_target(article_dir, stage)
    if not target.exists():
        raise PipelineError(f"missing stage target: {target}")
    before = _digest(target)
    original = target.read_text(encoding="utf-8")
    base_prompt = _prompt(stage, article_dir, profile, repo)
    route_errors: list[str] = []
    for route in routes:
        last_error = ""
        for _attempt in range(2):
            prompt = base_prompt
            if last_error:
                prompt += (
                    f"\nPREVIOUS OUTPUT WAS REJECTED: {last_error}\n"
                    "Correct it and return the full file again.\n"
                )
            try:
                output, json_output = _invoke_route(
                    route,
                    stage=stage,
                    prompt=prompt,
                    repo=repo,
                    timeout=timeout,
                )
                replacement = _extract_replacement(output, json_output=json_output)
                target.write_text(replacement, encoding="utf-8")
                _verify_stage(article_dir, stage, before)
                return {
                    "stage": stage,
                    "provider": route["provider"],
                    "model": route["model"],
                    "stdout": "bounded output applied",
                }
            except PipelineError as exc:
                target.write_text(original, encoding="utf-8")
                last_error = str(exc)
        route_errors.append(f"{route['provider']}/{route['model']}: {last_error}")
    raise PipelineError(f"{stage} exhausted model routes: {'; '.join(route_errors)}")


def run_pipeline(
    article_dir: str | Path,
    *,
    profile: str,
    timeout: int = 180,
    model: str | None = None,
    policy_path: str | Path | None = None,
    repo: str | Path | None = None,
) -> dict[str, Any]:
    article = Path(article_dir).expanduser().resolve()
    root = Path(repo).resolve() if repo else Path(__file__).resolve().parents[2]
    if model:
        stage_routes = {
            stage: [{"provider": "openrouter", "model": model}]
            for stage in PIPELINE_STAGES
        }
    else:
        policy = (
            Path(policy_path).resolve()
            if policy_path
            else root / "config/model-policy.example.yaml"
        )
        stage_routes = load_stage_routes(policy)
    completed = []
    results = []
    for stage in PIPELINE_STAGES:
        results.append(
            run_stage(
                stage,
                article_dir=article,
                profile=profile,
                timeout=timeout,
                routes=stage_routes[stage],
                repo=root,
            )
        )
        completed.append(stage)
    return {"completed": completed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article_dir", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--model",
        help="Override the policy and use one OpenCode model for every stage",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        help="Model policy path (default: config/model-policy.example.yaml)",
    )
    args = parser.parse_args()
    try:
        result = run_pipeline(
            args.article_dir,
            profile=args.profile,
            timeout=args.timeout,
            model=args.model,
            policy_path=args.policy,
        )
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
