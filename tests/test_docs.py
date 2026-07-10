"""Tests for executable documentation examples."""

import json
from pathlib import Path

from kingdom.config import validate_config


def test_config_full_example_is_valid() -> None:
    docs_path = Path(__file__).parents[1] / "docs" / "config.md"
    full_example = docs_path.read_text(encoding="utf-8").split("## Full example", 1)[1]
    json_block = full_example.split("```json", 1)[1].split("```", 1)[0]

    validate_config(json.loads(json_block))
