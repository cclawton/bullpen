# Model routing

Bullpen separates editorial roles from provider selection. The bounded runner reads `config/model-policy.example.yaml`, resolves an ordered route list for each stage, and invokes one model at a time.

## Example mixture

| Stage | Example primary route | Why |
|---|---|---|
| Research | `openai/gpt-5.4-mini` | Source and context handling |
| Draft | `openrouter/z-ai/glm-5.2` | Long-form generation and voice work |
| Trim | `openrouter/z-ai/glm-5-turbo` | Constrained, lower-cost editing |
| Safety | `openrouter/anthropic/claude-opus-4.6` | Conservative publication judgement |

These are examples, not mandatory endorsements. Availability, identifiers, pricing, and provider terms change. Configure only routes you are authorised to use.

## Runtime boundaries

OpenCode stages are output-only. The Python runner:

1. reads the selected profile and current article files;
2. resolves profile-relative override prompts;
3. embeds only the required context in a stage prompt;
4. extracts bounded output from OpenCode JSON events;
5. validates publication invariants;
6. writes transactionally or restores the original;
7. retries once, then follows the policy fallback.

The model never receives credentials and never chooses which files to mutate.

## Custom policy

```bash
cp config/model-policy.example.yaml config/model-policy.yaml
# edit providers and models
python3 -m scripts.bullpen_runtime.opencode_pipeline \
  /path/to/article --profile example-blog \
  --policy config/model-policy.yaml
```

Do not commit API keys. OpenCode provider authentication is managed outside the policy file.
