from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised when PyYAML absent
    yaml = None


class ModelPolicyError(ValueError):
    """Raised when model-policy.yaml is structurally invalid."""


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.isdigit():
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _load_simple_yaml_mapping(text: str) -> dict[str, Any]:
    """Parse the small mapping/list subset used by config/model-policy.yaml.

    This keeps validation usable on a fresh machine before project dependencies are
    installed. It is intentionally narrow; PyYAML remains the preferred parser when
    available.
    """
    tokens: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        tokens.append((indent, raw_line.strip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(tokens):
            return {}, index
        first_indent, first_text = tokens[index]
        if first_indent < indent:
            return {}, index
        if first_text.startswith("- "):
            items: list[Any] = []
            while index < len(tokens):
                current_indent, text = tokens[index]
                if current_indent != indent or not text.startswith("- "):
                    break
                item = text[2:]
                if ":" in item:
                    key, value = item.split(":", 1)
                    mapping: dict[str, Any] = {}
                    if value.strip():
                        mapping[key.strip()] = _parse_scalar(value)
                        index += 1
                    else:
                        index += 1
                        child, index = parse_block(index, indent + 2)
                        mapping[key.strip()] = child
                    # Collect following indented key/value lines that belong to
                    # this list item, e.g. "- provider: ..." then "model: ...".
                    while index < len(tokens):
                        next_indent, next_text = tokens[index]
                        if next_indent <= current_indent:
                            break
                        if next_text.startswith("- "):
                            break
                        if ":" not in next_text:
                            raise ModelPolicyError(
                                f"simple YAML parser cannot parse line: {next_text}"
                            )
                        subkey, subvalue = next_text.split(":", 1)
                        if subvalue.strip():
                            mapping[subkey.strip()] = _parse_scalar(subvalue)
                            index += 1
                        else:
                            index += 1
                            child, index = parse_block(index, next_indent + 2)
                            mapping[subkey.strip()] = child
                    items.append(mapping)
                else:
                    items.append(_parse_scalar(item))
                    index += 1
            return items, index

        mapping: dict[str, Any] = {}
        while index < len(tokens):
            current_indent, text = tokens[index]
            if current_indent != indent or text.startswith("- "):
                break
            if ":" not in text:
                raise ModelPolicyError(f"simple YAML parser cannot parse line: {text}")
            key, value = text.split(":", 1)
            key = key.strip()
            value = value.strip()
            index += 1
            if value:
                mapping[key] = _parse_scalar(value)
            else:
                child, index = parse_block(index, indent + 2)
                mapping[key] = child
        return mapping, index

    data, index = parse_block(0, tokens[0][0] if tokens else 0)
    if index != len(tokens):
        raise ModelPolicyError("simple YAML parser did not consume all lines")
    if not isinstance(data, dict):
        raise ModelPolicyError("model policy must parse to a mapping")
    return data


REQUIRED_ROLES = {
    "orchestrator",
    "researcher",
    "drafter",
    "trimmer",
    "safety-reviewer",
}


def load_model_policy(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) if yaml is not None else _load_simple_yaml_mapping(text)
    if not isinstance(data, dict):
        raise ModelPolicyError("model policy must be a mapping")
    return data


def validate_model_policy(policy: dict[str, Any]) -> None:
    providers = policy.get("providers")
    roles = policy.get("roles")
    if not isinstance(providers, dict) or not providers:
        raise ModelPolicyError("model policy requires providers mapping")
    if not isinstance(roles, dict) or not roles:
        raise ModelPolicyError("model policy requires roles mapping")

    missing_roles = sorted(REQUIRED_ROLES - set(roles))
    if missing_roles:
        raise ModelPolicyError(f"missing required roles: {', '.join(missing_roles)}")

    provider_names = set(providers)
    for role_name, role_config in roles.items():
        if not isinstance(role_config, dict):
            raise ModelPolicyError(f"role {role_name} must be a mapping")
        for route_name in ("primary", "fallback", "escalation", "last_resort"):
            route = role_config.get(route_name)
            if route is None:
                continue
            if isinstance(route, list):
                routes = route
            else:
                routes = [route]
            for item in routes:
                if not isinstance(item, dict):
                    raise ModelPolicyError(f"role {role_name}.{route_name} must be mapping(s)")
                provider = item.get("provider")
                if provider not in provider_names:
                    raise ModelPolicyError(
                        f"role {role_name}.{route_name} references unknown provider {provider!r}"
                    )
