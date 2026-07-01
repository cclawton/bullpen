# Bullpen

A profile-driven AI writing pipeline built on Claude Code subagents.

Multiple specialist agents — researcher, drafter, structure analyst, rhythm polisher, trimmer, humour polisher, safety reviewer, image prompter — collaborate under an orchestrator that talks to the human editor at every step. Each agent has one job. Personality and voice are configured per profile, not hardcoded into the agents.

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

Each agent reads the active profile, optionally adopts a personality override, does its job, and writes its output. The orchestrator syncs everything to Obsidian and commits to git.

The editor decides what runs next. There is no fixed pipeline.

## Quick start

```bash
git clone <this-repo>
cd bullpen

# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# edit .env with your Anthropic API key and Obsidian REST API credentials

# 3. Set up Obsidian
# Install the "Local REST API" plugin in Obsidian and create an API key.
# Create the folder in your vault: Content/example-blog/articles/

# 4. Pick a profile and launch
export WRITERS_ROOM_PROFILE=example-blog
claude --agent orchestrator
```

The orchestrator will greet you, show available profiles, and ask what you want to do.

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

All agents live in `.claude/agents/`. They're generic — they adapt to the active profile at runtime.

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

## Requirements

- [Claude Code](https://claude.com/claude-code) (CLI)
- [Obsidian](https://obsidian.md) with the [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) plugin
- Python 3.10+
- API keys:
  - Anthropic (required)
  - Image generation (optional — FAL, OpenAI, or Ideogram)
  - Substack credentials (optional — only for Substack publishing)

## License

MIT. See `LICENSE`.

## Architecture notes

For implementation details, design decisions, and conventions for modifying agent prompts, see `CLAUDE.md`.

## Part of a connected stack

bullpen is the creative output layer. The supervisor agent (github.com/cclawton/supervisor) monitors bullpen draft output via the filesystem — when all pipeline stages complete on a draft, the supervisor classifies it and signals the author. Two independent systems, one shared filesystem, no direct coupling. See also: hexapla (github.com/cclawton/hexapla), asian-sentry-techniques (github.com/cclawton/asian-sentry-techniques), podcastindex-mcp-server (github.com/cclawton/podcastindex-mcp-server)
