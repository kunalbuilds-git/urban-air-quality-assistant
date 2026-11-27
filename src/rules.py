"""The deterministic rules engine behind the Urban Air Quality Assistant.

This is where the decisions are made. The engine reads an AQI reading and a
household profile and produces a plan: what each person should do today,
what the household should do to the air inside the home, and what lower
emission alternatives are worth switching to.

Two design rules shape the module:

* **Data, not branches.** Every recommendation lives as a row in
  :data:`RULE_TABLE` with its own condition, wording, cost tier and benefit
  score. Adding a rule means adding a row, not editing a long if-chain.
* **The most vulnerable member sets the tone.** The strictness of the plan is
  raised for households that include a child, an older adult, or someone with
  asthma, and a member's advice replaces softer household-wide advice rather
  than sitting next to it.

Nothing here talks to a network or to a language model. The engine produces
the same plan for the same inputs, every time.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from src.aqi import AQIReading, read_aqi
from src.budget import CostTier
from src.impact import impact_for, safe_format
from src.profile import (
    CommuteMode,
    Household,
    Member,
    Sensitivity,
    effective_commute_mode,
    most_vulnerable_member,
)


class ActionCategory(StrEnum):
    """The three kinds of step a plan can contain."""

    DAILY_ROUTINE = "daily_routine"
    INDOOR_AIR = "indoor_air"
    SUSTAINABLE_ALTERNATIVES = "sustainable_alternatives"


class Audience(StrEnum):
    """Who a rule is written for."""

    MEMBER = "member"
    HOUSEHOLD = "household"


class Strictness(StrEnum):
    """How firm the advice is.

    Strictness starts from the air quality band and is raised by one step for
    households that include someone the smog hits hardest.
    """

    ADVISORY = "advisory"
    CAUTION = "caution"
    STRICT = "strict"
    SEVERE = "severe"


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a rule is allowed to look at.

    Attributes:
        reading: The validated AQI reading for today.
        household: The household the plan is for.
        strictness: The strictness derived from the band and the household.
        member: The member the rule is being evaluated for, or None for
            household-wide rules.
    """

    reading: AQIReading
    household: Household
    strictness: Strictness
    member: Member | None


@dataclass(frozen=True, slots=True)
class Action:
    """One recommendation in a plan.

    Attributes:
        rule_id: Identifier of the rule that produced this action.
        category: Which of the three kinds of step this is.
        title: Short name of the step.
        detail: What to do, in plain words.
        member_name: Who this step is for, or None when it is for everyone.
        cost_tier: The cost band of the step.
        benefit_score: Relative benefit score, used for budget ranking.
        safety_critical: True when the step protects the person in the
            household who is most affected by smog.
        impact: What the step changes, in plain words.
        assumption: What the step assumes to be true.
        replaces: Rule ids whose advice this step has replaced.
        priority: How important this step is to this household. Higher wins
            when two steps cost the same and protect the same amount.
    """

    rule_id: str
    category: ActionCategory
    title: str
    detail: str
    member_name: str | None
    cost_tier: CostTier
    benefit_score: float
    safety_critical: bool
    impact: str
    assumption: str
    replaces: tuple[str, ...] = ()
    priority: int = 0

    @property
    def cost_inr(self) -> int:
        """Cost of the step in whole rupees."""
        return int(self.cost_tier)

    @property
    def cost_label(self) -> str:
        """Short human readable description of what the step costs."""
        return self.cost_tier.label


@dataclass(frozen=True, slots=True)
class ActionPlan:
    """The full plan for one household on one day.

    Attributes:
        reading: The AQI reading the plan was built from.
        household: The household the plan is for.
        strictness: The strictness that was applied.
        actions: Every recommended step, in display order.
        summary: One sentence describing the day, in plain words.
    """

    reading: AQIReading
    household: Household
    strictness: Strictness
    actions: tuple[Action, ...]
    summary: str

    def by_category(self, category: ActionCategory) -> tuple[Action, ...]:
        """Return the steps of one category, in display order.

        Args:
            category: The category to filter by.

        Returns:
            The matching actions.
        """
        return tuple(action for action in self.actions if action.category == category)

    def for_member(self, name: str) -> tuple[Action, ...]:
        """Return the steps written for one person.

        Args:
            name: The member's name.

        Returns:
            The matching actions.
        """
        return tuple(action for action in self.actions if action.member_name == name)

    def household_actions(self) -> tuple[Action, ...]:
        """Return the steps written for everyone rather than one person."""
        return tuple(action for action in self.actions if action.member_name is None)


Predicate = Callable[[RuleContext], bool]
"""A condition a rule uses to decide whether it applies."""

BenefitScore = float | Callable[[RuleContext], float]
"""A fixed benefit score, or one that depends on the household."""

SafetyCritical = bool | Callable[[RuleContext], bool]
"""A fixed safety flag, or one that depends on the household."""


@dataclass(frozen=True, slots=True)
class Rule:
    """One row of the rule table.

    Attributes:
        rule_id: Stable identifier, also used to look up the impact wording.
        category: Which kind of step this rule produces.
        title: Short name of the step. May use the ``name``, ``city``,
            ``aqi`` and ``band`` placeholders.
        detail: What to do, in plain words. Uses the same placeholders.
        audience: Whether the rule is evaluated per member or once per
            household.
        condition: Decides whether the rule applies.
        cost_tier: The cost band of the step.
        benefit_score: Relative benefit score, used for budget ranking.
        safety_critical: Whether the step protects the most vulnerable member.
        overrides: Rule ids whose advice this rule replaces when it applies.
        focus_most_vulnerable: Whether the rule is about the household's most
            vulnerable member even though it is written for the household.
    """

    rule_id: str
    category: ActionCategory
    title: str
    detail: str
    audience: Audience
    condition: Predicate
    cost_tier: CostTier
    benefit_score: BenefitScore
    safety_critical: SafetyCritical = False
    overrides: tuple[str, ...] = ()
    focus_most_vulnerable: bool = False


_STRICTNESS_BY_SEVERITY: Final[Mapping[int, Strictness]] = {
    0: Strictness.ADVISORY,
    1: Strictness.ADVISORY,
    2: Strictness.CAUTION,
    3: Strictness.STRICT,
    4: Strictness.SEVERE,
    5: Strictness.SEVERE,
}
"""Strictness before the household is taken into account."""

_STRICTNESS_ORDER: Final[tuple[Strictness, ...]] = (
    Strictness.ADVISORY,
    Strictness.CAUTION,
    Strictness.STRICT,
    Strictness.SEVERE,
)
"""Strictness levels, from softest to firmest."""

_CATEGORY_ORDER: Final[Mapping[ActionCategory, int]] = {
    ActionCategory.DAILY_ROUTINE: 0,
    ActionCategory.INDOOR_AIR: 1,
    ActionCategory.SUSTAINABLE_ALTERNATIVES: 2,
}
"""Display order of the three categories."""

HOUSEHOLD_PRIORITY: Final[int] = 50
"""Priority of a step that is written for the household as a whole."""

MEMBER_PRIORITY_BASE: Final[int] = 100
"""Base priority of a step written for one person.

A member's priority is this base plus their vulnerability rank, so that when
two steps cost the same, the one protecting the person the smog hits hardest
is chosen first.
"""


def severity_at_least(minimum: int) -> Predicate:
    """Build a condition that checks the AQI band severity.

    Args:
        minimum: The lowest severity that satisfies the condition.

    Returns:
        A predicate for use in a rule.
    """

    def predicate(context: RuleContext) -> bool:
        return context.reading.severity >= minimum

    return predicate


def member_with_sensitivity(*sensitivities: Sensitivity) -> Predicate:
    """Build a condition that checks the sensitivity of the current member.

    Args:
        sensitivities: The sensitivities that satisfy the condition.

    Returns:
        A predicate for use in a rule.
    """
    wanted = frozenset(sensitivities)

    def predicate(context: RuleContext) -> bool:
        return context.member is not None and context.member.sensitivity in wanted

    return predicate


def member_commutes(*modes: CommuteMode) -> Predicate:
    """Build a condition that checks how the current member travels.

    Args:
        modes: The commute modes that satisfy the condition.

    Returns:
        A predicate for use in a rule.
    """
    wanted = frozenset(modes)

    def predicate(context: RuleContext) -> bool:
        if context.member is None:
            return False
        return effective_commute_mode(context.member, context.household) in wanted

    return predicate


def all_of(*predicates: Predicate) -> Predicate:
    """Build a condition that requires every given condition to hold.

    Args:
        predicates: The conditions to combine.

    Returns:
        A predicate for use in a rule.
    """

    def predicate(context: RuleContext) -> bool:
        return all(check(context) for check in predicates)

    return predicate


def _purifier_benefit(context: RuleContext) -> float:
    """Return the benefit score for the purifier rule, based on who it is for."""
    target = most_vulnerable_member(context.household.members)
    if target is None:
        return 6.0
    if target.sensitivity is Sensitivity.ASTHMATIC:
        return 9.0
    if target.sensitivity in (Sensitivity.CHILD, Sensitivity.ELDERLY):
        return 8.0
    return 6.0


def _purifier_is_safety_critical(context: RuleContext) -> bool:
    """Report whether the purifier protects someone more affected by smog."""
    target = most_vulnerable_member(context.household.members)
    return target is not None and target.is_sensitive


RULE_TABLE: Final[tuple[Rule, ...]] = (
    # -- Daily routine -----------------------------------------------------
    Rule(
        rule_id="child.outdoor_activity.moderate",
        category=ActionCategory.DAILY_ROUTINE,
        title="Move {name}'s outdoor play indoors",
        detail=(
            "Keep the school run and playtime indoors on days like this, and "
            "save the outdoor time for a cleaner hour."
        ),
        audience=Audience.MEMBER,
        condition=all_of(member_with_sensitivity(Sensitivity.CHILD), severity_at_least(2)),
        cost_tier=CostTier.FREE,
        benefit_score=7.0,
    ),
    Rule(
        rule_id="child.outdoor_activity.severe",
        category=ActionCategory.DAILY_ROUTINE,
        title="Keep {name} indoors today",
        detail=(
            "No outdoor PT or play today. Move it indoors, and treat the "
            "missed outdoor time as one to make up on a cleaner day."
        ),
        audience=Audience.MEMBER,
        condition=all_of(member_with_sensitivity(Sensitivity.CHILD), severity_at_least(4)),
        cost_tier=CostTier.FREE,
        benefit_score=9.0,
        overrides=("child.outdoor_activity.moderate", "sensitive.outdoor_mask"),
    ),
    Rule(
        rule_id="sensitive.windows_closed",
        category=ActionCategory.DAILY_ROUTINE,
        title="Keep {name}'s room windows shut",
        detail=(
            "Keep {name}'s room windows shut through the morning and evening "
            "peaks, and keep the rest of the house shut at the same time. Air "
            "the rooms only when the outdoor air is better."
        ),
        audience=Audience.MEMBER,
        condition=all_of(
            member_with_sensitivity(
                Sensitivity.CHILD,
                Sensitivity.ELDERLY,
                Sensitivity.ASTHMATIC,
            ),
            severity_at_least(3),
        ),
        cost_tier=CostTier.FREE,
        benefit_score=9.0,
        safety_critical=True,
        overrides=("household.ventilation.moderate", "household.ventilation.poor"),
    ),
    Rule(
        rule_id="sensitive.outdoor_mask",
        category=ActionCategory.DAILY_ROUTINE,
        title="Give {name} a fitted N95/FFP2 respirator",
        detail=(
            "If {name} has to go out, use a properly fitted N95/FFP2-type "
            "respirator with a good seal on the face. A loose cloth or "
            "surgical mask does not seal the same way."
        ),
        audience=Audience.MEMBER,
        condition=all_of(
            member_with_sensitivity(
                Sensitivity.CHILD,
                Sensitivity.ELDERLY,
                Sensitivity.ASTHMATIC,
            ),
            severity_at_least(3),
        ),
        cost_tier=CostTier.LOW,
        benefit_score=8.0,
        safety_critical=True,
    ),
    Rule(
        rule_id="sensitive.walk.shift",
        category=ActionCategory.DAILY_ROUTINE,
        title="Move {name}'s morning walk",
        detail=(
            "Do the walk after the sun is up and after the morning peak has "
            "passed, not at 6 am. If the air stays bad, keep it indoors."
        ),
        audience=Audience.MEMBER,
        condition=all_of(
            member_with_sensitivity(Sensitivity.ELDERLY, Sensitivity.ASTHMATIC),
            severity_at_least(3),
        ),
        cost_tier=CostTier.FREE,
        benefit_score=8.0,
    ),
    Rule(
        rule_id="sensitive.walk.skip",
        category=ActionCategory.DAILY_ROUTINE,
        title="Skip {name}'s walk today",
        detail=(
            "On the worst days, keep {name} indoors and move gently inside "
            "instead. The walk can wait for a cleaner day."
        ),
        audience=Audience.MEMBER,
        condition=all_of(
            member_with_sensitivity(Sensitivity.ELDERLY, Sensitivity.ASTHMATIC),
            severity_at_least(5),
        ),
        cost_tier=CostTier.FREE,
        benefit_score=9.0,
        overrides=("sensitive.walk.shift",),
    ),
    Rule(
        rule_id="commute.two_wheeler.mask",
        category=ActionCategory.DAILY_ROUTINE,
        title="Wear a fitted N95/FFP2 respirator on the ride",
        detail=(
            "For {name}'s two-wheeler ride, wear a properly fitted "
            "N95/FFP2-type respirator for the whole trip, and check that it "
            "seals on the face before leaving."
        ),
        audience=Audience.MEMBER,
        condition=all_of(member_commutes(CommuteMode.TWO_WHEELER), severity_at_least(2)),
        cost_tier=CostTier.LOW,
        benefit_score=8.0,
    ),
    Rule(
        rule_id="commute.walk.shift",
        category=ActionCategory.DAILY_ROUTINE,
        title="Walk in the cleaner part of the day",
        detail=(
            "Shift {name}'s walk away from the morning and evening peaks, and "
            "take the route with less traffic."
        ),
        audience=Audience.MEMBER,
        condition=all_of(member_commutes(CommuteMode.WALK), severity_at_least(3)),
        cost_tier=CostTier.FREE,
        benefit_score=7.0,
    ),
    Rule(
        rule_id="worker.work_from_home.indoor_air",
        category=ActionCategory.DAILY_ROUTINE,
        title="Keep {name}'s work room closed at the peaks",
        detail=(
            "Keep the work room windows shut through the peaks while {name} "
            "is sitting still for hours, and air it once the outdoor air "
            "improves."
        ),
        audience=Audience.MEMBER,
        condition=all_of(
            member_commutes(CommuteMode.WORK_FROM_HOME),
            severity_at_least(2),
        ),
        cost_tier=CostTier.FREE,
        benefit_score=7.0,
    ),
    # -- Indoor air --------------------------------------------------------
    Rule(
        rule_id="household.ventilation.moderate",
        category=ActionCategory.INDOOR_AIR,
        title="Close the windows at the peaks",
        detail=(
            "Keep the windows shut through the morning and evening peaks, and "
            "air the house in the middle of the day when the air is usually "
            "better."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(2),
        cost_tier=CostTier.FREE,
        benefit_score=7.0,
    ),
    Rule(
        rule_id="household.ventilation.poor",
        category=ActionCategory.INDOOR_AIR,
        title="Ventilate only in the cleanest hour",
        detail=(
            "Keep the windows shut all day except a short airing at the "
            "cleanest hour, and check the AQI before you open them."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(3),
        cost_tier=CostTier.FREE,
        benefit_score=8.0,
        overrides=("household.ventilation.moderate",),
    ),
    Rule(
        rule_id="household.ventilation.severe",
        category=ActionCategory.INDOOR_AIR,
        title="Keep the house closed except for a brief airing",
        detail=(
            "Keep every window shut except one brief airing at the cleanest "
            "hour of the day, and leave the purifier running if you have one."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(5),
        cost_tier=CostTier.FREE,
        benefit_score=9.0,
        overrides=("household.ventilation.poor",),
    ),
    Rule(
        rule_id="household.purifier.placement",
        category=ActionCategory.INDOOR_AIR,
        title="Put one purifier in {name}'s room",
        detail=(
            "If you can buy one purifier, put it in {name}'s room, where they "
            "spend most of the day, and run it while the windows are shut. "
            "Spend the money on the one room, not on the whole flat."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(3),
        cost_tier=CostTier.HIGH,
        benefit_score=_purifier_benefit,
        safety_critical=_purifier_is_safety_critical,
        focus_most_vulnerable=True,
    ),
    Rule(
        rule_id="household.dust.wet_clean",
        category=ActionCategory.INDOOR_AIR,
        title="Damp clean instead of dry sweeping",
        detail=(
            "Mop floors and wipe surfaces with a damp cloth in the early "
            "morning. Dry sweeping puts the dust back into the air."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(2),
        cost_tier=CostTier.FREE,
        benefit_score=5.0,
    ),
    Rule(
        rule_id="household.no_smoking_indoors",
        category=ActionCategory.INDOOR_AIR,
        title="Keep smoke and fumes out of the house",
        detail=(
            "No incense, agarbatti, tobacco smoke or deep-frying smoke "
            "indoors today, and open the kitchen window only when the "
            "outdoor air is better."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(2),
        cost_tier=CostTier.FREE,
        benefit_score=6.0,
    ),
    Rule(
        rule_id="household.seal.gaps",
        category=ActionCategory.INDOOR_AIR,
        title="Close the gaps around doors and windows",
        detail=(
            "Push cloth or tape into the gaps around doors and windows so "
            "that less of the outside air gets in, and keep the windows shut."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(4),
        cost_tier=CostTier.FREE,
        benefit_score=6.0,
    ),
    # -- Sustainable alternatives ------------------------------------------
    Rule(
        rule_id="commute.two_wheeler.reduce_ride",
        category=ActionCategory.SUSTAINABLE_ALTERNATIVES,
        title="Take metro or bus for {name}'s ride",
        detail=(
            "On the worst days, take the metro or bus for {name}'s trip, or "
            "share a ride with someone going the same way."
        ),
        audience=Audience.MEMBER,
        condition=all_of(member_commutes(CommuteMode.TWO_WHEELER), severity_at_least(4)),
        cost_tier=CostTier.FREE,
        benefit_score=8.0,
    ),
    Rule(
        rule_id="household.no_waste_burning",
        category=ActionCategory.SUSTAINABLE_ALTERNATIVES,
        title="Do not burn leaves or garbage",
        detail=(
            "Do not burn dry leaves, garden waste or garbage, and ask the "
            "neighbours not to either. Ask for green-waste collection "
            "instead."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(2),
        cost_tier=CostTier.FREE,
        benefit_score=7.0,
    ),
    Rule(
        rule_id="household.no_firecrackers",
        category=ActionCategory.SUSTAINABLE_ALTERNATIVES,
        title="Skip the firecrackers",
        detail=(
            "Skip firecrackers this season, and choose noise-free options if "
            "the family celebrates. The smoke and dust reach every lane, "
            "yours included."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(3),
        cost_tier=CostTier.FREE,
        benefit_score=6.0,
    ),
    Rule(
        rule_id="household.no_idling",
        category=ActionCategory.SUSTAINABLE_ALTERNATIVES,
        title="No idling near the house",
        detail=(
            "Do not leave the vehicle idling at the gate or in the lane. "
            "Switch the engine off at red lights and as soon as you are home."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(2),
        cost_tier=CostTier.FREE,
        benefit_score=5.0,
    ),
    Rule(
        rule_id="household.public_transport",
        category=ActionCategory.SUSTAINABLE_ALTERNATIVES,
        title="Use public transport for the worst days",
        detail=(
            "If a metro or bus route works for you, use it on the worst days. "
            "More people in fewer vehicles means less smoke on the street and "
            "less of it on the way."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(3),
        cost_tier=CostTier.FREE,
        benefit_score=6.0,
    ),
    Rule(
        rule_id="household.green_waste_collection",
        category=ActionCategory.SUSTAINABLE_ALTERNATIVES,
        title="Give dry leaves to green-waste collection",
        detail=(
            "Hand dry leaves and garden waste to the colony's green-waste "
            "collection or compost them, so they are not burnt nearby."
        ),
        audience=Audience.HOUSEHOLD,
        condition=severity_at_least(2),
        cost_tier=CostTier.FREE,
        benefit_score=6.0,
    ),
)
"""Every recommendation the application can make, as data."""


def derive_strictness(reading: AQIReading, household: Household) -> Strictness:
    """Return how firm the advice should be today.

    The band sets the baseline. A household that includes a child, an older
    adult, or someone with asthma is guided one step stricter from the
    Moderate band upward, because the same air is a different problem for
    them.

    Args:
        reading: The validated AQI reading for today.
        household: The household the plan is for.

    Returns:
        The strictness to apply.
    """
    baseline = _STRICTNESS_BY_SEVERITY[reading.severity]
    if reading.severity >= 2 and household.has_sensitive_member:
        return _next_strictness(baseline)
    return baseline


def build_plan(aqi_value: int | float | str, household: Household) -> ActionPlan:
    """Build the full plan for a household on one day.

    Args:
        aqi_value: The AQI reading for today.
        household: The household the plan is for.

    Returns:
        An :class:`ActionPlan` holding every recommended step.

    Raises:
        InvalidAQIScoreError: If the AQI reading cannot be accepted.
    """
    reading = read_aqi(aqi_value)
    strictness = derive_strictness(reading, household)
    candidates = _collect_candidates(reading, household, strictness)
    actions = _apply_overrides(candidates)
    summary = _build_summary(reading, household, strictness, actions)
    return ActionPlan(
        reading=reading,
        household=household,
        strictness=strictness,
        actions=actions,
        summary=summary,
    )


def _collect_candidates(
    reading: AQIReading,
    household: Household,
    strictness: Strictness,
) -> list[tuple[Rule, Action]]:
    """Evaluate every rule and build the actions that apply.

    Args:
        reading: The validated AQI reading for today.
        household: The household the plan is for.
        strictness: The strictness derived from the band and the household.

    Returns:
        The matching rule and action pairs, before overrides are applied.
    """
    candidates: list[tuple[Rule, Action]] = []
    for rule in RULE_TABLE:
        for member in _audience_members(rule, household):
            context = RuleContext(
                reading=reading,
                household=household,
                strictness=strictness,
                member=member,
            )
            if rule.condition(context):
                candidates.append((rule, _build_action(rule, context)))
    return candidates


def _audience_members(rule: Rule, household: Household) -> tuple[Member | None, ...]:
    """Return the members a rule is evaluated against."""
    if rule.audience is Audience.MEMBER:
        return household.members
    return (None,)


def _build_action(rule: Rule, context: RuleContext) -> Action:
    """Turn a rule and a context into a finished action."""
    values = _format_context(context)
    member_name = context.member.name if context.member else None
    if rule.focus_most_vulnerable and member_name is None:
        target = most_vulnerable_member(context.household.members)
        member_name = target.name if target else None

    note = impact_for(rule.rule_id, values)
    benefit = rule.benefit_score
    if callable(benefit):
        benefit = benefit(context)
    safety_critical = rule.safety_critical
    if callable(safety_critical):
        safety_critical = safety_critical(context)

    return Action(
        rule_id=rule.rule_id,
        category=rule.category,
        title=safe_format(rule.title, values),
        detail=safe_format(rule.detail, values),
        member_name=member_name,
        cost_tier=rule.cost_tier,
        benefit_score=float(benefit),
        safety_critical=bool(safety_critical),
        impact=note.impact,
        assumption=note.assumption,
        priority=_priority_for(rule, context, member_name),
    )


def _priority_for(rule: Rule, context: RuleContext, member_name: str | None) -> int:
    """Return how important an action is to this household.

    A step written for one person ranks above a household-wide step, and
    within the people, the person the smog hits hardest ranks first.

    Args:
        rule: The rule that produced the action.
        context: The context the rule was evaluated in.
        member_name: Who the action is for, or None when it is for everyone.

    Returns:
        The priority of the action, higher meaning more important.
    """
    if member_name is None:
        return HOUSEHOLD_PRIORITY
    target = most_vulnerable_member(context.household.members)
    if rule.focus_most_vulnerable and target is not None:
        return MEMBER_PRIORITY_BASE + target.vulnerability_rank
    for member in context.household.members:
        if member.name == member_name:
            return MEMBER_PRIORITY_BASE + member.vulnerability_rank
    return MEMBER_PRIORITY_BASE


def _apply_overrides(candidates: Sequence[tuple[Rule, Action]]) -> tuple[Action, ...]:
    """Remove the advice that a stronger rule replaces.

    A member rule replaces household advice for the whole household, because
    the household has to follow the stricter advice once one member needs it.
    A member rule replaces another member rule only for the same person.

    Args:
        candidates: The rule and action pairs before overrides are applied.

    Returns:
        The surviving actions, in display order.
    """
    suppressed: set[tuple[str, str | None]] = set()
    replaced_by_rule: dict[int, list[str]] = {}

    for index, (rule, action) in enumerate(candidates):
        for target_id in rule.overrides:
            for target_rule, target_action in candidates:
                if target_rule.rule_id != target_id:
                    continue
                same_person = target_action.member_name == action.member_name
                if target_rule.audience is Audience.HOUSEHOLD or same_person:
                    suppressed.add((target_rule.rule_id, target_action.member_name))
                    replaced_by_rule.setdefault(index, []).append(target_rule.rule_id)

    final: list[Action] = []
    for index, (rule, action) in enumerate(candidates):
        if (rule.rule_id, action.member_name) in suppressed:
            continue
        replaces = tuple(sorted(set(replaced_by_rule.get(index, []))))
        final.append(replace(action, replaces=replaces))

    return tuple(sorted(final, key=_action_sort_key))


def _action_sort_key(action: Action) -> tuple[int, str, str]:
    """Sort key ordering actions for display."""
    return (
        _CATEGORY_ORDER[action.category],
        action.member_name or "",
        action.rule_id,
    )


def _format_context(context: RuleContext) -> dict[str, object]:
    """Build the values used to fill in the placeholders in the wording."""
    target = most_vulnerable_member(context.household.members)
    if context.member is not None:
        name = context.member.name
    elif target is not None:
        name = target.name
    else:
        name = "the family"
    return {
        "name": name,
        "city": context.household.city,
        "aqi": context.reading.display_value,
        "band": context.reading.spec.label,
    }


def _next_strictness(current: Strictness) -> Strictness:
    """Return the next stricter level, without going past the firmest."""
    index = _STRICTNESS_ORDER.index(current)
    return _STRICTNESS_ORDER[min(index + 1, len(_STRICTNESS_ORDER) - 1)]


def _build_summary(
    reading: AQIReading,
    household: Household,
    strictness: Strictness,
    actions: Sequence[Action],
) -> str:
    """Build the one-line description of the day."""
    lead = f"AQI {reading.display_value} ({reading.spec.label}) in {household.city}."
    reason = _strictness_reason(strictness, household)
    if not actions:
        return f"{lead} {reason} No special steps are needed today."
    people = len(household.members)
    people_word = "person" if people == 1 else "people"
    steps = len(actions)
    step_word = "step" if steps == 1 else "steps"
    return f"{lead} {reason} {steps} {step_word} ready for {people} {people_word}."


def _strictness_reason(strictness: Strictness, household: Household) -> str:
    """Explain, in plain words, why the advice is as firm as it is."""
    target = most_vulnerable_member(household.members)
    if target is None or target.sensitivity is Sensitivity.HEALTHY_ADULT:
        return {
            Strictness.ADVISORY: "Normal precautions are enough today.",
            Strictness.CAUTION: "Take the usual care steps.",
            Strictness.STRICT: (
                "The air itself is bad enough that the whole household needs to be strict."
            ),
            Strictness.SEVERE: "This is the worst band, so every step in the plan matters.",
        }[strictness]
    return {
        Strictness.ADVISORY: "Normal precautions are enough today.",
        Strictness.CAUTION: "Take the usual care steps.",
        Strictness.STRICT: (
            f"Advice is one step stricter because {target.name} is {target.sensitivity_label}."
        ),
        Strictness.SEVERE: (
            f"Advice is at its strictest because {target.name} is {target.sensitivity_label}."
        ),
    }[strictness]
