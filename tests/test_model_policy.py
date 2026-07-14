from pathlib import Path

from scripts.bullpen_runtime.model_policy import load_model_policy, validate_model_policy


def test_public_policy_is_valid_and_contains_no_private_paths():
    root = Path(__file__).resolve().parents[1]
    policy_path = root / "config/model-policy.example.yaml"
    policy = load_model_policy(policy_path)
    validate_model_policy(policy)
    text = policy_path.read_text()
    assert "/Users/" not in text
    assert "craig" not in text.lower()
    assert policy["roles"]["researcher"]["primary"]["model"] == "openai/gpt-5.4-mini"
