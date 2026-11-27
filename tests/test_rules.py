"""Tests for the deterministic rules engine.

These tests cover the decisions the product makes: who gets which advice,
how strict the advice is, and which advice replaces which.
"""

import pytest

from src.aqi import InvalidAQIScoreError
from src.profile import (
    CommuteMode,
    HomeType,
    Household,
    Member,
    Sensitivity,
)
from src.rules import (
    RULE_TABLE,
    ActionCategory,
    Strictness,
    build_plan,
    derive_strictness,
)

pytestmark = pytest.mark.persona


def make_member(name="Rohit", age=38, sensitivity=Sensitivity.HEALTHY_ADULT, commute=None):
    return Member(name=name, age=age, sensitivity=sensitivity, commute_mode=commute)


def make_household(members=None, budget=5000, city="Delhi"):
    return Household(
        city=city,
        members=members if members is not None else (make_member(),),
        commute_mode=CommuteMode.CAR,
        home_type=HomeType.APARTMENT,
        budget_inr=budget,
    )


def sharma_household(budget=500):
    return Household(
        city="Delhi",
        members=(
            make_member("Rohit", 38, Sensitivity.HEALTHY_ADULT, CommuteMode.TWO_WHEELER),
            make_member("Neha", 35, Sensitivity.HEALTHY_ADULT, CommuteMode.WORK_FROM_HOME),
            make_member("Aarav", 7, Sensitivity.CHILD),
            make_member("Dadi", 68, Sensitivity.ASTHMATIC),
        ),
        commute_mode=CommuteMode.CAR,
        home_type=HomeType.APARTMENT,
        budget_inr=budget,
    )


def rule_ids(plan):
    return {action.rule_id for action in plan.actions}


ANY_MEMBER = object()


def action_for(plan, rule_id, member_name=ANY_MEMBER):
    for action in plan.actions:
        if action.rule_id != rule_id:
            continue
        if member_name is ANY_MEMBER or action.member_name == member_name:
            return action
    raise AssertionError(f"no action {rule_id} for {member_name} in the plan")


def has_action_for(plan, rule_id, member_name):
    return any(
        action.rule_id == rule_id and action.member_name == member_name for action in plan.actions
    )


def test_persona_plan_covers_all_three_categories():
    plan = build_plan(412, sharma_household())

    assert plan.by_category(ActionCategory.DAILY_ROUTINE)
    assert plan.by_category(ActionCategory.INDOOR_AIR)
    assert plan.by_category(ActionCategory.SUSTAINABLE_ALTERNATIVES)


def test_persona_plan_is_read_in_plain_words():
    plan = build_plan(412, sharma_household())

    assert "Severe" in plan.summary
    assert "Delhi" in plan.summary
    assert "Dadi" in plan.summary


def test_a_severe_day_keeps_the_child_indoors():
    plan = build_plan(412, sharma_household())

    assert "child.outdoor_activity.severe" in rule_ids(plan)
    assert "child.outdoor_activity.moderate" not in rule_ids(plan)


def test_a_moderate_day_only_moves_the_child_indoors():
    plan = build_plan(150, sharma_household())

    assert "child.outdoor_activity.moderate" in rule_ids(plan)
    assert "child.outdoor_activity.severe" not in rule_ids(plan)


def test_the_asthmatic_member_skips_the_walk_on_a_severe_day():
    plan = build_plan(412, sharma_household())

    assert "sensitive.walk.skip" in rule_ids(plan)
    assert "sensitive.walk.shift" not in rule_ids(plan)


def test_the_asthmatic_member_shifts_the_walk_on_a_poor_day():
    plan = build_plan(250, sharma_household())

    assert "sensitive.walk.shift" in rule_ids(plan)
    assert "sensitive.walk.skip" not in rule_ids(plan)


def test_the_two_wheeler_commuter_is_told_to_use_a_fitted_respirator():
    plan = build_plan(250, sharma_household())

    action = action_for(plan, "commute.two_wheeler.mask", "Rohit")

    assert "N95" in action.detail
    assert "FFP2" in action.detail
    assert "fitted" in action.detail
    assert "respirator" in action.detail


def test_mask_guidance_never_suggests_a_plain_mask():
    plan = build_plan(412, sharma_household())

    for action in plan.actions:
        if "mask" in action.rule_id:
            wording = " ".join((action.title, action.detail, action.impact, action.assumption))
            assert "N95/FFP2" in wording
            assert "fitted" in wording
            assert "loose cloth or surgical mask does not seal" in wording


def test_a_member_override_does_not_reach_the_other_members():
    plan = build_plan(412, sharma_household())

    # Aarav is told to stay indoors, so his respirator advice is dropped.
    assert "sensitive.outdoor_mask" in rule_ids(plan)
    assert not has_action_for(plan, "sensitive.outdoor_mask", "Aarav")

    # Dadi still gets hers, because she is not the one being kept indoors.
    dadi_mask = action_for(plan, "sensitive.outdoor_mask", "Dadi")
    assert dadi_mask.member_name == "Dadi"


def test_vulnerable_member_advice_replaces_soft_household_advice():
    healthy_only = make_household()
    with_vulnerable = make_household(
        members=(
            make_member("Rohit", 38, Sensitivity.HEALTHY_ADULT, CommuteMode.CAR),
            make_member("Dadi", 68, Sensitivity.ASTHMATIC),
        )
    )

    healthy_plan = build_plan(250, healthy_only)
    vulnerable_plan = build_plan(250, with_vulnerable)

    # Without a vulnerable member, the household keeps the softer advice.
    assert "household.ventilation.poor" in rule_ids(healthy_plan)
    assert "sensitive.windows_closed" not in rule_ids(healthy_plan)

    # With one, the member's advice replaces it.
    assert "household.ventilation.poor" not in rule_ids(vulnerable_plan)
    assert "household.ventilation.moderate" not in rule_ids(vulnerable_plan)
    assert "sensitive.windows_closed" in rule_ids(vulnerable_plan)

    # And the replacement is recorded, so the UI can explain what changed.
    replacing = action_for(vulnerable_plan, "sensitive.windows_closed", "Dadi")
    assert "household.ventilation.poor" in replacing.replaces
    assert "household.ventilation.moderate" in replacing.replaces


def test_the_strictness_is_bumped_for_a_vulnerable_household():
    healthy_only = make_household()
    with_vulnerable = make_household(
        members=(
            make_member("Rohit", 38, Sensitivity.HEALTHY_ADULT, CommuteMode.CAR),
            make_member("Dadi", 68, Sensitivity.ASTHMATIC),
        )
    )

    assert build_plan(250, healthy_only).strictness is Strictness.STRICT
    assert build_plan(250, with_vulnerable).strictness is Strictness.SEVERE


def test_the_strictness_bump_starts_at_the_moderate_band():
    healthy_only = make_household()
    with_vulnerable = make_household(
        members=(
            make_member("Rohit", 38, Sensitivity.HEALTHY_ADULT, CommuteMode.CAR),
            make_member("Dadi", 68, Sensitivity.ASTHMATIC),
        )
    )

    assert build_plan(150, healthy_only).strictness is Strictness.CAUTION
    assert build_plan(150, with_vulnerable).strictness is Strictness.STRICT


def test_there_is_no_strictness_bump_when_the_air_is_clean():
    with_vulnerable = make_household(
        members=(
            make_member("Rohit", 38, Sensitivity.HEALTHY_ADULT, CommuteMode.CAR),
            make_member("Dadi", 68, Sensitivity.ASTHMATIC),
        )
    )

    assert build_plan(40, with_vulnerable).strictness is Strictness.ADVISORY
    assert build_plan(80, with_vulnerable).strictness is Strictness.ADVISORY


def test_derive_strictness_matches_the_plan():
    from src.aqi import read_aqi

    household = sharma_household()
    reading = read_aqi(250)

    assert derive_strictness(reading, household) is build_plan(250, household).strictness


def test_the_purifier_is_placed_in_the_most_vulnerable_room():
    plan = build_plan(250, sharma_household())

    action = action_for(plan, "household.purifier.placement")

    assert action.member_name == "Dadi"
    assert "Dadi" in action.title
    assert action.cost_inr == 10000
    assert action.safety_critical


def test_household_actions_cover_burning_idling_and_firecrackers():
    plan = build_plan(412, sharma_household())

    assert "household.no_waste_burning" in rule_ids(plan)
    assert "household.no_idling" in rule_ids(plan)
    assert "household.no_firecrackers" in rule_ids(plan)


def test_no_recommendation_mentions_stubble_burning():
    plan = build_plan(412, sharma_household())

    for action in plan.actions:
        assert "stubble" not in action.detail.lower()
        assert "stubble" not in action.impact.lower()


def test_firecrackers_are_only_raised_once_the_air_is_bad():
    plan = build_plan(150, sharma_household())

    assert "household.no_firecrackers" not in rule_ids(plan)


def test_every_action_carries_an_impact_and_an_assumption():
    plan = build_plan(412, sharma_household())

    for action in plan.actions:
        assert action.impact.strip()
        assert action.assumption.strip()


def test_every_action_is_addressed_to_somebody():
    plan = build_plan(412, sharma_household())

    names = {member.name for member in plan.household.members}
    for action in plan.actions:
        if action.member_name is not None:
            assert action.member_name in names


def test_the_same_inputs_always_produce_the_same_plan():
    first = build_plan(412, sharma_household())
    second = build_plan(412, sharma_household())

    assert first.summary == second.summary
    assert [action.rule_id for action in first.actions] == [
        action.rule_id for action in second.actions
    ]
    assert [action.member_name for action in first.actions] == [
        action.member_name for action in second.actions
    ]


def test_a_clean_day_needs_no_special_steps():
    plan = build_plan(30, sharma_household())

    assert plan.actions == ()
    assert "No special steps" in plan.summary


def test_the_plan_rejects_an_impossible_aqi():
    with pytest.raises(InvalidAQIScoreError):
        build_plan(501, sharma_household())


def test_every_rule_has_a_unique_id():
    ids = [rule.rule_id for rule in RULE_TABLE]

    assert len(ids) == len(set(ids))


def test_no_rule_overrides_a_rule_that_does_not_exist():
    known = {rule.rule_id for rule in RULE_TABLE}

    for rule in RULE_TABLE:
        for target in rule.overrides:
            assert target in known
