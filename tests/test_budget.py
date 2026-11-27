"""Tests for the budget-aware ranking of recommendations."""

from dataclasses import dataclass

import pytest

from src.budget import (
    BudgetPlan,
    CostTier,
    benefit_per_rupee,
    build_budget_plan,
    rank_actions,
)


@dataclass(frozen=True)
class StubAction:
    rule_id: str
    cost_inr: int
    benefit_score: float
    safety_critical: bool = False
    priority: int = 0
    title: str = ""


def stub(rule_id, cost, benefit, safety_critical=False, priority=0, title=None):
    return StubAction(
        rule_id=rule_id,
        cost_inr=cost,
        benefit_score=benefit,
        safety_critical=safety_critical,
        priority=priority,
        title=title if title is not None else rule_id,
    )


def test_cost_tiers_are_the_three_planned_amounts():
    assert CostTier.FREE == 0
    assert CostTier.LOW == 500
    assert CostTier.HIGH == 10000


def test_cost_tier_labels_are_plain_words():
    assert CostTier.FREE.label == "No cost"
    assert "500" in CostTier.LOW.label
    assert "10,000" in CostTier.HIGH.label


def test_free_actions_are_always_taken():
    actions = (stub("free", 0, 5.0), stub("paid", 500, 9.0))

    plan = build_budget_plan(actions, 0)

    assert [action.rule_id for action in plan.selected] == ["free"]
    assert [action.rule_id for action in plan.deferred] == ["paid"]
    assert plan.total_cost_inr == 0
    assert plan.remaining_inr == 0


def test_a_zero_budget_notes_that_only_free_steps_are_listed():
    actions = (stub("free", 0, 5.0), stub("paid", 500, 9.0))

    plan = build_budget_plan(actions, 0)

    assert any("free steps" in note for note in plan.notes)


def test_a_large_budget_buys_everything():
    actions = (stub("free", 0, 5.0), stub("paid", 500, 9.0), stub("big", 10000, 8.0))

    plan = build_budget_plan(actions, 10**9)

    assert plan.deferred == ()
    assert plan.total_cost_inr == 10500
    assert plan.remaining_inr == 10**9 - 10500
    assert plan.fits_everything


def test_a_budget_that_exactly_fits_is_used():
    actions = (stub("one", 500, 9.0), stub("two", 500, 8.0))

    plan = build_budget_plan(actions, 500)

    assert len(plan.selected) == 1
    assert plan.remaining_inr == 0


def test_actions_are_chosen_by_benefit_per_rupee():
    actions = (
        stub("expensive", 10000, 5.0),
        stub("cheap", 500, 4.0),
    )

    plan = build_budget_plan(actions, 500)

    assert [action.rule_id for action in plan.selected] == ["cheap"]
    assert [action.rule_id for action in plan.deferred] == ["expensive"]


def test_a_safety_critical_step_is_chosen_first():
    actions = (
        stub("better_value", 500, 9.0),
        stub("protects_the_vulnerable", 10000, 6.0, safety_critical=True),
    )

    plan = build_budget_plan(actions, 10000)

    assert plan.selected[0].rule_id == "protects_the_vulnerable"
    assert "better_value" in [action.rule_id for action in plan.deferred]


def test_the_most_vulnerable_person_wins_an_equal_price_tie():
    actions = (
        stub("mask_for_child", 500, 8.0, safety_critical=True, priority=103),
        stub("mask_for_asthmatic", 500, 8.0, safety_critical=True, priority=104),
    )

    plan = build_budget_plan(actions, 500)

    assert [action.rule_id for action in plan.selected] == ["mask_for_asthmatic"]


def test_a_deferred_safety_critical_step_is_called_out():
    actions = (
        stub("protects_the_vulnerable", 10000, 6.0, safety_critical=True, title="Buy a purifier"),
    )

    plan = build_budget_plan(actions, 500)

    assert any("protects the person most affected" in note for note in plan.notes)
    assert any("Buy a purifier" in note for note in plan.notes)


def test_deferred_steps_are_explained():
    actions = (stub("paid", 500, 9.0, title="Buy masks"),)

    plan = build_budget_plan(actions, 0)

    assert any("Buy masks" in note for note in plan.notes)
    assert any("cost nothing" in note for note in plan.notes)


def test_a_negative_budget_is_treated_as_no_budget():
    actions = (stub("free", 0, 5.0), stub("paid", 500, 9.0))

    plan = build_budget_plan(actions, -100)

    assert plan.total_cost_inr == 0
    assert [action.rule_id for action in plan.selected] == ["free"]


def test_benefit_per_rupee_is_infinite_for_a_free_action():
    assert benefit_per_rupee(stub("free", 0, 5.0)) == float("inf")
    assert benefit_per_rupee(stub("paid", 500, 5.0)) == pytest.approx(0.01)


def test_rank_actions_puts_free_steps_first():
    actions = (stub("paid", 500, 9.0), stub("free", 0, 1.0))

    ranked = rank_actions(actions)

    assert [action.rule_id for action in ranked] == ["free", "paid"]


def test_rank_actions_orders_paid_steps_by_value():
    actions = (
        stub("low_value", 10000, 5.0),
        stub("high_value", 500, 5.0),
    )

    ranked = rank_actions(actions)

    assert [action.rule_id for action in ranked] == ["high_value", "low_value"]


def test_the_budget_plan_is_empty_for_no_actions():
    plan = build_budget_plan((), 1000)

    assert isinstance(plan, BudgetPlan)
    assert plan.selected == ()
    assert plan.deferred == ()
    assert plan.remaining_inr == 1000
    assert plan.fits_everything
