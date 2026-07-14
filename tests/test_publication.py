import pytest

from scripts.publication import MARKER, extract_public_copy


def test_extract_public_copy_removes_frontmatter_and_internal_notes():
    draft = (
        "---\ntags: [status/draft]\n---\n\n# Public title\n\nPublic body.\n\n"
        + MARKER
        + "\n\n## Pipeline Notes\n\n### Safety\nPrivate risk note.\n"
    )

    public = extract_public_copy(draft)

    assert public == "# Public title\n\nPublic body.\n"
    assert "status/draft" not in public
    assert "Private risk note" not in public
    assert MARKER not in public


def test_extract_public_copy_requires_exactly_one_marker():
    with pytest.raises(ValueError, match="exactly one"):
        extract_public_copy("# Draft without marker\n")
    with pytest.raises(ValueError, match="exactly one"):
        extract_public_copy(f"Body\n{MARKER}\n{MARKER}\n")


def test_extract_public_copy_rejects_malformed_frontmatter():
    with pytest.raises(ValueError, match="malformed"):
        extract_public_copy(f"---\ntags: [draft]\n# Missing close\n{MARKER}\n")
