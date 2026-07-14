# CLAUDE.md — Bullpen

## What This Is

A profile-driven content pipeline with bounded OpenCode stages and optional Claude Code compatibility. The human editor-in-chief decides what happens. AI agents each have distinct roles. Personality, voice, and model routes are configured rather than hardcoded.

## Architecture

The production-style runner launches research, draft, trimmer, and safety as separate bounded processes. OpenCode agents live in `.opencode/agent/`; the model policy lives in `config/model-policy.example.yaml`. A deterministic Python runner validates model output and owns file writes. The original `.claude/agents/*.md` workflow remains available for interactive use.

### Profiles

Each content instance (newsletter, blog, column, LinkedIn feed, etc.) is a **profile** in `profiles/<id>/profile.yaml`. The profile defines:
- Voice (tone, register, spelling, banned words)
- Content constraints (word count, structure, link density)
- Platform (Substack, blog, LinkedIn, etc.)
- Pipeline (which agents run and in what order)
- Agent personality overrides (optional rich persona files)
- Obsidian vault paths (where content lives)
- Idea sources (which platforms to mine for ideas)

### Subagents

| Agent | File | Role |
|---|---|---|
| **orchestrator** | `.claude/agents/orchestrator.md` | Manages articles, delegates, syncs Obsidian |
| **researcher** | `.claude/agents/researcher.md` | Research & primary source gathering |
| **drafter** | `.claude/agents/drafter.md` | Article drafting |
| **structure-analyst** | `.claude/agents/structure-analyst.md` | Logical structure, coherence, thesis tracking (long-form). Analysis only. |
| **rhythm-polisher** | `.claude/agents/rhythm-polisher.md` | Rhythm, alliteration, cadence |
| **trimmer** | `.claude/agents/trimmer.md` | Cut fat, enforce word count |
| **humour-polisher** | `.claude/agents/humour-polisher.md` | Humour & satire |
| **safety-reviewer** | `.claude/agents/safety-reviewer.md` | Legal/defamation/employer risk |
| **image-prompter** | `.claude/agents/image-prompter.md` | Image prompt generation |
| **idea-miner** | `.claude/agents/idea-miner.md` | Idea mining from notes & comments |

Each generic agent reads the active profile YAML at runtime and adapts its behaviour. Profiles can optionally provide personality-rich override prompts in `profiles/<id>/agents/` that agents read for persona, cultural references, and voice.

### Example profiles

| Profile | Use case | Format |
|---|---|---|
| **example-blog** | Long-form reflective essays | 800–1500 word blog posts, full pipeline including structure analyst |
| **example-newsletter** | Short-form opinion pieces | 400–600 word newsletter articles, lean pipeline |

Use these as templates. Copy one, edit `profile.yaml`, and you have a new content instance.

**Hard rule: personas do not cross profiles.** If a profile has personality override prompts in `profiles/<id>/agents/`, those files belong to that profile only. The orchestrator enforces this by reading `override_prompt` only from the active profile's directory. This is what keeps multiple profiles with distinct voices from contaminating each other.

### State Storage

All article content lives in **Obsidian** (via the Local REST API), with a **local git-tracked cache** in `cache/` for audit trail.

```
Obsidian vault (source of truth):
  <vault_base>/articles/<slug>/todo.md, research.md, notes.md, draft.md, structure-analysis.md, image-brief.md
  <vault_base>/ideas/backlog.md

Local cache (git-tracked mirror):
  cache/<profile>/articles/<slug>/...
  cache/<profile>/ideas/...
```

The orchestrator is the sole Obsidian proxy — it reads/writes via curl, passes content to agents, and syncs results back.

## Bounded OpenCode runtime

```bash
python3 -m scripts.bullpen_runtime.opencode_pipeline \
  "/absolute/path/to/article-directory" \
  --profile example-blog
```

Normal runs use the configured role-specific model routes. `--model` deliberately overrides the policy for every stage and is intended only for runtime experiments.

Runtime invariants:

- one fresh process per stage;
- output-only model contract with sentinels;
- transactional writes and rollback on rejection;
- one bounded correction retry followed by policy fallback;
- exactly one publication marker and one note per Trimmer/Safety stage;
- no model-led filesystem exploration.

## Legacy Claude Code runtime

```bash
# Start the orchestrator
claude --agent orchestrator

# The orchestrator reads WRITERS_ROOM_PROFILE env var, or asks which profile to use.
# Set it before launching:
export WRITERS_ROOM_PROFILE=example-blog
claude --agent orchestrator

# Scripts (all profile-aware)
python scripts/mine_ideas.py --profile example-blog
python scripts/publish.py --profile example-newsletter --slug my-article --title "Title"
python scripts/generate_image.py --profile example-blog --slug my-article

# Obsidian helper CLI
python scripts/obsidian.py read "path/in/vault/note.md"
python scripts/obsidian.py write "path/in/vault/note.md" --input local-file.md
python scripts/obsidian.py list "path/in/vault/folder/"
```

## Creating a New Profile

1. Copy an existing profile directory: `cp -r profiles/example-blog profiles/my-new-profile`
2. Edit `profiles/my-new-profile/profile.yaml`:
   - Change `id`, `name`, `description`
   - Set `voice` for your target tone and audience
   - Set `content` for word count, structure, format
   - Set `platform` for your publishing target
   - Set `pipeline` — disable agents you don't need
   - Set `obsidian.vault_base` to your vault folder
3. Optionally add personality override prompts in `profiles/my-new-profile/agents/`
4. Create the Obsidian folder structure in your vault

## Key Design Decisions

- **Profile-driven, not hardcoded**: Voice, constraints, and pipeline are config — not baked into agent prompts.
- **Generic agents + personality overrides**: Each agent has a generic version that reads the profile. Profiles can optionally provide rich personality files that override the generic behaviour.
- **Obsidian as state store**: All content lives in Obsidian. The git repo tracks code and config, not articles.
- **Local cache for audit trail**: Every agent step is cached locally and git-committed. Full revert history.
- **Orchestrator as Obsidian proxy**: Only the orchestrator touches the Obsidian API. Agents work on local files.
- **No fixed pipeline**: The orchestrator suggests a default order but the editor controls flow.
- **Git as version control for cache**: Every agent step is committed for revertability.

## Agent Prompt Guidelines

When modifying subagent prompts:
- Keep generic agents personality-free — they adapt via the profile
- Personality override files in `profiles/<id>/agents/` can be as vivid as you like
- All polishing agents must preserve hyperlinks
- The trimmer should never ADD words
- The structure analyst is analysis-only — it diagnoses, it doesn't rewrite
- The safety reviewer checks are driven by profile config (employer, jurisdiction)

## Permissions & Flow Control

**Auto-approve (never prompt the editor):**
- All web searches and web fetches
- All file reads, writes, edits, glob/grep
- All git operations on cache
- All Obsidian API reads and writes
- Updating todo.md, creating directories

**Once a subagent is launched, it runs uninterrupted to completion.**

**Always pause and ask the editor before:**
- Launching any subagent
- Moving to the next pipeline step
- Publishing or generating images

## Environment

Needs `.env` only for optional integrations:
- `ANTHROPIC_API_KEY` when a selected route uses the Anthropic API directly
- `OBSIDIAN_REST_API_URL`, `OBSIDIAN_REST_API_KEY` for optional Obsidian state
- Platform-specific keys for publishing, image generation, or idea sources

OpenCode provider authentication is configured with `opencode auth login`.

See `.env.example` for the full list.

Also used:
- `WRITERS_ROOM_PROFILE` — active profile id for the interactive Claude Code session
