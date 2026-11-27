"""Tests for the impact wording and the disclaimer.

These tests guard the promise that the application makes: every step
explains what it changes, names what it assumes, and never invents a
statistic to sound convincing.
"""

import re

import pytest

from src.impact import (
    DISCLAIMER,
    FALLBACK_IMPACT,
    IMPACT_TEMPLATES,
    impact_for,
    safe_format,
)
from src.rules import RULE_TABLE

_ALLOWED_DIGITS = {"95", "2"}
"""The only numbers allowed in the wording: the respirator class names."""


def all_templates():
    return [*IMPACT_TEMPLATES.values(), FALLBACK_IMPACT]


def test_every_rule_has_its_own_impact_wording():
    for rule in RULE_TABLE:
        assert rule.rule_id in IMPACT_TEMPLATES, rule.rule_id


def test_no_wording_exists_without_a_rule():
    known = {rule.rule_id for rule in RULE_TABLE}

    assert set(IMPACT_TEMPLATES) == known


def test_every_impact_and_assumption_is_written_out():
    for template in all_templates():
        assert template.impact.strip()
        assert template.assumption.strip()


def test_every_impact_names_its_assumption():
    for template in all_templates():
        assert "Assumes" in template.assumption


def test_the_wording_contains_no_percentages():
    for template in all_templates():
        for text in (template.impact, template.assumption):
            assert "%" not in text
            assert "percent" not in text.lower()


def test_the_wording_contains_no_particle_measurements():
    for template in all_templates():
        for text in (template.impact, template.assumption):
            lowered = text.lower()
            assert "microgram" not in lowered
            assert "ug/m" not in lowered
            assert "mg/m" not in lowered


def test_the_wording_contains_no_numbers_but_the_respirator_class_names():
    for template in all_templates():
        for text in (template.impact, template.assumption):
            numbers = set(re.findall(r"\d+", text))
            assert numbers <= _ALLOWED_DIGITS, text


def test_an_unknown_rule_falls_back_instead_of_raising():
    note = impact_for("a.rule.that.does.not.exist", {"name": "Dadi"})

    assert note.impact == FALLBACK_IMPACT.impact
    assert note.assumption == FALLBACK_IMPACT.assumption


def test_the_wording_is_formatted_with_the_person_it_is_for():
    note = impact_for("sensitive.windows_closed", {"name": "Dadi", "city": "Delhi"})

    assert "Dadi" in note.impact


def test_an_unknown_placeholder_is_left_alone():
    assert safe_format("Hello {name}", {}) == "Hello {name}"
    assert safe_format("Hello {name}", {"name": "Dadi"}) == "Hello Dadi"


def test_a_broken_template_does_not_break_the_plan():
    assert safe_format("Hello {name", {"name": "Dadi"}) == "Hello {name"


def test_the_disclaimer_is_visible_and_says_what_it_is():
    assert "not medical advice" in DISCLAIMER
    assert len(DISCLAIMER) < 200


@pytest.mark.parametrize("rule_id", sorted(IMPACT_TEMPLATES))
def test_every_template_formats_without_error(rule_id):
    context = {"name": "Dadi", "city": "Delhi", "aqi": "412", "band": "Severe"}

    note = impact_for(rule_id, context)

    assert "{" not in note.impact
    assert "{" not in note.assumption
