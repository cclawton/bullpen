from pathlib import Path

from scripts.bullpen_runtime.opencode_pipeline import (
    PIPELINE_STAGES,
    _prompt,
    load_stage_routes,
    run_pipeline,
    run_stage,
)

MARKER = "<!-- === PIPELINE NOTES — NOT FOR PUBLICATION === -->"


def _article(tmp_path: Path) -> Path:
    article = tmp_path / "article"
    article.mkdir()
    (article / "research.md").write_text("# Research\n\nA sourced claim.\n")
    (article / "draft.md").write_text(
        "---\ntags: [status/draft]\n---\n\n# Draft\n\nBody.\n\n"
        + MARKER
        + "\n\n## Pipeline Notes (not published)\n"
    )
    return article


def test_policy_resolves_a_model_mixture():
    root = Path(__file__).resolve().parents[1]
    routes = load_stage_routes(root / "config/model-policy.example.yaml")
    assert routes["research"][0]["model"] == "openai/gpt-5.4-mini"
    assert routes["draft"][0]["model"] == "openrouter/z-ai/glm-5.2"
    assert routes["trimmer"][0]["model"] == "openrouter/z-ai/glm-5-turbo"
    assert "claude" in routes["safety"][0]["model"]


def test_prompt_resolves_profile_override_without_private_hardcoding(tmp_path):
    root = tmp_path / "repo"
    profile = root / "profiles/example/agents"
    profile.mkdir(parents=True)
    (root / "profiles/example/profile.yaml").write_text(
        "agents:\n  drafter:\n    override_prompt: agents/example-writer.md\n"
    )
    (profile / "example-writer.md").write_text("GENERIC PERSONA")
    article = _article(tmp_path)
    prompt = _prompt("draft", article, "example", root)
    assert "GENERIC PERSONA" in prompt
    assert "the-linkedin-writer" not in prompt


def test_pipeline_uses_one_resolved_route_set_per_stage(tmp_path, monkeypatch):
    article = _article(tmp_path)
    seen = []

    def fake_stage(stage, **kwargs):
        seen.append((stage, kwargs["routes"][0]["model"]))
        return {"stage": stage}

    monkeypatch.setattr("scripts.bullpen_runtime.opencode_pipeline.run_stage", fake_stage)
    root = Path(__file__).resolve().parents[1]
    result = run_pipeline(article, profile="example-blog", repo=root)
    assert result["completed"] == list(PIPELINE_STAGES)
    assert len({model for _, model in seen}) >= 3


def test_stage_falls_back_after_primary_repeatedly_fails_validation(tmp_path, monkeypatch):
    article = _article(tmp_path)
    root = Path(__file__).resolve().parents[1]
    calls = []

    def fake_invoke(route, **kwargs):
        calls.append(route["model"])
        if route["model"] == "primary-model":
            body = "---\ntags: [status/draft]\n---\n\nBad — dash.\n\n"
        else:
            body = "---\ntags: [status/draft]\n---\n\nClean fallback.\n\n"
        body += MARKER + "\n\n## Pipeline Notes (not published)\n"
        return f"<<<WR_OUTPUT>>>\n{body}<<<END_WR_OUTPUT>>>", False

    monkeypatch.setattr(
        "scripts.bullpen_runtime.opencode_pipeline._invoke_route", fake_invoke
    )
    result = run_stage(
        "draft",
        article_dir=article,
        profile="example-blog",
        timeout=5,
        routes=[
            {"provider": "openrouter", "model": "primary-model"},
            {"provider": "openrouter", "model": "fallback-model"},
        ],
        repo=root,
    )
    assert result["model"] == "fallback-model"
    assert calls == ["primary-model", "primary-model", "fallback-model"]
