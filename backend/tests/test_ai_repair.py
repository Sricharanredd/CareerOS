from __future__ import annotations

import json

import pytest

from app.ai.base import ProviderInvalidOutput
from app.ai.repair import validate_or_repair


def _valid() -> str:
    return json.dumps(
        {
            "score": 74,
            "summary": "Good core-stack overlap; Kubernetes is not evidenced.",
            "alignment_explanation": "Python and MySQL appear in both documents.",
            "findings": [
                {
                    "kind": "resume_evidence",
                    "category": "matched_skill",
                    "label": "Python APIs",
                    "detail": "The resume shows production Python API work.",
                }
            ],
        }
    )


class Recorder:
    """Stands in for the adapter's regenerate call and records the hints it received."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.hints: list[str] = []

    def __call__(self, hint: str) -> str:
        self.hints.append(hint)
        return self.responses.pop(0)


def test_valid_output_is_not_repaired():
    regenerate = Recorder([])
    output = validate_or_repair(_valid(), regenerate, provider_name="stub", max_repairs=1)
    assert output.score == 74
    assert regenerate.hints == []


def test_invalid_output_is_repaired_with_a_field_hint():
    regenerate = Recorder([_valid()])
    output = validate_or_repair(
        '{"score": 200}', regenerate, provider_name="stub", max_repairs=1
    )
    assert output.score == 74
    assert len(regenerate.hints) == 1
    assert "score" in regenerate.hints[0]


def test_adapters_default_to_no_repair():
    regenerate = Recorder([_valid()])
    with pytest.raises(ProviderInvalidOutput):
        validate_or_repair("not json", regenerate, provider_name="stub")
    assert regenerate.hints == []


def test_a_second_failure_raises_invalid_output():
    regenerate = Recorder(["still not json"])
    with pytest.raises(ProviderInvalidOutput) as error:
        validate_or_repair("not json", regenerate, provider_name="stub", max_repairs=1)
    assert "structure" in error.value.message
    assert len(regenerate.hints) == 1


def test_fenced_json_is_still_accepted():
    raw = "```json\n" + _valid() + "\n```"
    output = validate_or_repair(raw, Recorder([]), provider_name="stub")
    assert output.score == 74
