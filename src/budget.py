"""Budget-aware ranking of recommended actions.

A family rarely has money for everything, so the plan has to answer "what
should we actually spend on?". This module ranks the actions produced by the
rules engine by benefit per rupee and fits them into the available budget.

The benefit scores used here are relative judgements made by this project,
not medical findings. They exist to put steps in a sensible order against
each other, and every one of them is listed as an assumption in the README.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol


class CostTier(IntEnum):
    """The cost bands a recommendation can fall into, in whole rupees.

    The tiers are deliberately coarse. A family thinks "can we spend anything
    at all", "can we spend a few hundred", or "can we spend on the big fix",
    and the plan has to speak in those terms rather than in exact prices.
    """

    FREE = 0
    LOW = 500
    HIGH = 10000

    @property
    def label(self) -> str:
        """Short human readable description of the tier."""
        return {
            CostTier.FREE: "No cost",
            CostTier.LOW: "About Rs 500",
            CostTier.HIGH: "About Rs 10,000",
        }[self]


class RankableAction(Protocol):
    """The part of an action that the budget planner needs.

    Declared as a protocol so that this module does not need to import the
    rules engine, and the rules engine does not need to import this one.
    """

    rule_id: str
    benefit_score: float
    safety_critical: bool
    priority: int

    @property
    def cost_inr(self) -> int:
        """Cost of the action in whole rupees."""
        ...


@dataclass(frozen=True, slots=True)
class BudgetPlan:
    """The result of fitting actions into a budget.

    Attributes:
        selected: Actions that fit within the budget, free ones first.
        deferred: Actions that did not fit.
        total_cost_inr: Total cost of the selected actions.
        remaining_inr: Money left over after the selected actions.
        notes: Plain-language notes, for example about a safety critical step
            that could not be afforded.
    """

    selected: tuple[RankableAction, ...]
    deferred: tuple[RankableAction, ...]
    total_cost_inr: int
    remaining_inr: int
    notes: tuple[str, ...]

    @property
    def fits_everything(self) -> bool:
        """True when no action had to be left out."""
        return not self.deferred


def benefit_per_rupee(action: RankableAction) -> float:
    """Return the benefit score of an action per rupee it costs.

    Args:
        action: The action to score.

    Returns:
        The ratio, or infinity for a free action, which is always at least as
        good value as a paid one.
    """
    cost = action.cost_inr
    if cost <= 0:
        return math.inf
    return action.benefit_score / cost


def rank_actions(actions: Sequence[RankableAction]) -> tuple[RankableAction, ...]:
    """Order actions by value, best first.

    Free actions come first, then paid actions by benefit per rupee. Steps
    that protect the person the smog hits hardest win the ties, and the rule
    id is the final tie breaker so that the order is stable between runs.

    Args:
        actions: The actions to rank.

    Returns:
        The actions in ranked order.
    """
    free = sorted(
        (action for action in actions if action.cost_inr <= 0),
        key=_free_order,
    )
    paid = sorted(
        (action for action in actions if action.cost_inr > 0),
        key=_value_order,
    )
    return (*free, *paid)


def build_budget_plan(
    actions: Sequence[RankableAction],
    budget_inr: int,
) -> BudgetPlan:
    """Fit actions into a budget.

    Free actions are always taken. Paid actions are taken in order of value,
    with safety critical actions for the most vulnerable member considered
    first, so that a limited budget still protects the person who needs it
    most.

    Args:
        actions: The candidate actions.
        budget_inr: Money available, in whole rupees. Negative values are
            treated as zero.

    Returns:
        A :class:`BudgetPlan` describing what was selected and what was not.
    """
    budget = max(0, int(budget_inr))
    selected: list[RankableAction] = []
    deferred: list[RankableAction] = []
    remaining = budget

    free = sorted(
        (action for action in actions if action.cost_inr <= 0),
        key=_free_order,
    )
    selected.extend(free)

    paid = [action for action in actions if action.cost_inr > 0]
    protected = sorted(
        (action for action in paid if action.safety_critical),
        key=_value_order,
    )
    regular = sorted(
        (action for action in paid if not action.safety_critical),
        key=_value_order,
    )

    for action in (*protected, *regular):
        cost = action.cost_inr
        if cost <= remaining:
            selected.append(action)
            remaining -= cost
        else:
            deferred.append(action)

    total = sum(action.cost_inr for action in selected)
    return BudgetPlan(
        selected=tuple(selected),
        deferred=tuple(deferred),
        total_cost_inr=total,
        remaining_inr=remaining,
        notes=_build_notes(deferred, budget),
    )


def _value_order(action: RankableAction) -> tuple[float, int, float, str]:
    """Sort key ordering paid actions by value, best first.

    Value comes first. When two steps are worth the same per rupee, the one
    that protects the person the smog hits hardest is chosen first.
    """
    return (
        -benefit_per_rupee(action),
        -action.priority,
        -action.benefit_score,
        action.rule_id,
    )


def _free_order(action: RankableAction) -> tuple[float, int, str]:
    """Sort key ordering free actions, best first."""
    return (-action.benefit_score, -action.priority, action.rule_id)


def _build_notes(deferred: Sequence[RankableAction], budget: int) -> tuple[str, ...]:
    """Build the plain-language notes that explain a constrained plan."""
    if not deferred:
        if budget == 0:
            return ("No money was set for this plan, so only the free steps are listed.",)
        return ("Everything in this plan fits the budget.",)

    titles = ", ".join(_title_of(action) for action in deferred)
    safety_critical = [action for action in deferred if action.safety_critical]
    notes: list[str] = []
    if safety_critical:
        protected_titles = ", ".join(_title_of(action) for action in safety_critical)
        notes.append(
            "Not affordable with this budget, and it protects the person most "
            f"affected by smog: {protected_titles}."
        )
    notes.append(f"Left out because of the budget: {titles}.")
    notes.append("The free steps above still apply and cost nothing.")
    return tuple(notes)


def _title_of(action: RankableAction) -> str:
    """Return a readable title for an action, falling back to its rule id."""
    title = getattr(action, "title", None)
    if isinstance(title, str) and title:
        return title
    return action.rule_id
