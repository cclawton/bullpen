# Bullpen

A profile-driven AI writing pipeline with bounded OpenCode stages, role-specific model routing, and optional Claude Code compatibility.

Multiple specialist agents collaborate under a profile-driven workflow. The production-style OpenCode runner executes research, drafting, trimming, and safety as separate bounded processes. A deterministic Python layer owns validation and file writes, while `config/model-policy.example.yaml` chooses a model for each role. The original Claude Code agents remain available for interactive use.

The metaphor is a baseball bullpen: specialist relievers sitting ready, called in by the manager when the situation demands them.

## How it works

```
                    ┌──────────────┐
                    │  Orchestrator │  ← talks to the editor
                    └──────┬───────┘
                           │
       ┌─────────┬─────────┼─────────┬─────────┬─────────┐
       ▼         ▼         ▼         ▼         ▼         ▼
  Researcher  Drafter   Structure  Rhythm    Trimmer   Safety
                       Analyst   Polisher              Reviewer
       │         │         │         │         │         │
       ▼         ▼         ▼         ▼         ▼         ▼
   research.md draft.md  analysis  draft.md  draft.md  draft.md
```

Each model receives only the context for one stage and returns a complete replacement between bounded sentinels. The runner validates the result and applies it transactionally. Models never independently explore or edit the filesystem.

The bounded runner uses a fixed four-stage safety sequence. The legacy interactive orchestrator remains editor-directed.

## Quick start

```bash
git clone <this-repo>
cd bullpen

# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment and provider authentication
cp .env.example .env
# edit .env with any Obsidian or publishing credentials you use
# configure OpenCode providers with: opencode auth login

# 3. Set up Obsidian
# Install the "Local REST API" plugin in Obsidian and create an API key.
# Create the folder in your vault: Content/example-blog/articles/

# 4. Create an article directory containing research.md and draft.md,
# then run the bounded mixture-of-models pipeline
python3 -m scripts.bullpen_runtime.opencode_pipeline \
  "/absolute/path/to/article-directory" \
  --profile example-blog
```

The example policy routes research, drafting, trimming, and safety to role-appropriate models with ordered fallbacks. Copy it to `config/model-policy.yaml`, customise it, and pass `--policy config/model-policy.yaml`. Use `--model <provider/model>` only for deliberate single-model experiments.

For the legacy interactive workflow:

```bash
export WRITERS_ROOM_PROFILE=example-blog
claude --agent orchestrator
```

## OpenCode pipeline safety contract

- Every stage runs in a fresh process.
- OpenCode emits machine-readable JSON text events.
- The runner accepts only content between `<<<WR_OUTPUT>>>` and `<<<END_WR_OUTPUT>>>`.
- Invalid output is rolled back and receives one bounded correction retry.
- The next stage starts only after the target digest changes and invariants pass.
- The publication marker and internal stage notes are validated before acceptance.

## The agents

| Agent | Role |
|---|---|
| **orchestrator** | Coordinates everything. The only agent that talks to the editor, Obsidian, and git. |
| **researcher** | Gathers primary sources, statistics, and clickable URLs into a research brief. |
| **drafter** | Turns the research brief and editor's notes into a draft. |
| **structure-analyst** | Diagnoses logical structure, thesis tracking, section flow, and coverage gaps. Analysis only — never rewrites. |
| **rhythm-polisher** | Enhances cadence, alliteration, and parallel structure without changing meaning. |
| **trimmer** | Cuts every word that doesn't earn its place. Only subtracts. |
| **humour-polisher** | Adds humour or satire that serves the argument. Style adapts to the profile. |
| **safety-reviewer** | Checks for defamation risk, employment sensitivity, and factual accuracy. |
| **image-prompter** | Generates header image prompts for the published piece. |
| **idea-miner** | Mines Obsidian notes and comments for article ideas, deduplicated against the backlog. |

Bounded OpenCode agents live in `.opencode/agent/`; interactive Claude agents live in `.claude/agents/`. Both are generic and adapt to the active profile at runtime.

## Profiles

A profile is a content instance: one newsletter, one blog, one column. Each lives in `profiles/<id>/profile.yaml` and defines:

- **Voice**: tone, register, spelling, banned words, style notes
- **Content constraints**: word count, structure, link density
- **Platform**: blog, Substack, LinkedIn, etc.
- **Pipeline**: which agents run, in what order, and which are enabled
- **Agent overrides**: optional richer persona prompts in `profiles/<id>/agents/`
- **Obsidian integration**: vault paths
- **Idea sources**: which Obsidian folders to scan

Two example profiles ship with the repo:

- **`example-blog`** — long-form reflective essays (800–1500 words). Full pipeline with the structure analyst enabled.
- **`example-newsletter`** — short-form opinion pieces (400–600 words). Lean pipeline; structure analyst disabled.

### Creating your own profile

1. Copy an example: `cp -r profiles/example-blog profiles/my-profile`
2. Edit `profiles/my-profile/profile.yaml`:
   - Change `id`, `name`, `description`
   - Adjust `voice` for your target tone
   - Set `content` for your word count and structure
   - Configure `pipeline` — disable agents you don't need
   - Set `obsidian.vault_base` to your vault folder
3. (Optional) Add personality overrides in `profiles/my-profile/agents/`
4. Create the Obsidian folders: `<vault_base>/ideas/` and `<vault_base>/articles/`
5. Run: `export WRITERS_ROOM_PROFILE=my-profile && claude --agent orchestrator`

## State storage

All article content lives in your Obsidian vault (via the Local REST API plugin), with a git-tracked cache in `cache/` for full audit history. Every agent step is committed.

```
<vault_base>/articles/<slug>/
  todo.md
  research.md
  notes.md
  draft.md
  structure-analysis.md
  image-brief.md

cache/<profile-id>/articles/<slug>/  ← mirror of the above, git-tracked
```

## Scripts

| Script | Purpose |
|---|---|
| `scripts/mine_ideas.py` | Idea mining from Obsidian notes and comment platforms |
| `scripts/obsidian.py` | CLI helper for Obsidian vault read/write/list |
| `scripts/generate_image.py` | Image generation via FAL/OpenAI/Ideogram |
| `scripts/publish.py` | Publishing workflow |
| `scripts/migrate_article.py` | Article migration utility |
| `scripts/bullpen_runtime/opencode_pipeline.py` | Bounded multi-model OpenCode pipeline |

## Requirements

- [OpenCode](https://opencode.ai/) (CLI) for the bounded multi-model pipeline
- [Claude Code](https://claude.com/claude-code) (optional legacy interactive workflow)
- [Obsidian](https://obsidian.md) with the [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) plugin
- Python 3.10+
- Provider authentication configured through OpenCode (requirements depend on your model policy)
- Optional API keys:
  - Anthropic (only if your chosen route uses the Anthropic API)
  - Image generation (optional — FAL, OpenAI, or Ideogram)
  - Substack credentials (optional — only for Substack publishing)

## License

MIT. See `LICENSE`.

## Architecture notes

For implementation details, design decisions, and conventions for modifying agent prompts, see `CLAUDE.md`.

## Part of a connected stack

Bullpen is the creative output layer. The [supervisor](https://github.com/cclawton/supervisor) can monitor completed draft output through the filesystem, classify it, and signal the author. The systems share files without sharing code or calling each other directly.

Related projects: [hexapla](https://github.com/cclawton/hexapla), [music21-mcp](https://github.com/cclawton/music21-mcp), [reascript-mcp](https://github.com/cclawton/reascript-mcp), [asian-sentry-techniques](https://github.com/cclawton/asian-sentry-techniques), and [podcastindex-mcp-server](https://github.com/cclawton/podcastindex-mcp-server).
