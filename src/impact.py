"""Plain-language impact lines and the assumptions behind them.

Every recommendation this application makes has to answer two questions:
"what does this actually change?" and "what are you assuming?". This module
owns that wording, so the rules engine only has to decide *whether* a step
applies, never how to explain it.

Two rules govern every line written here:

* No invented statistics. There are no percentages, no particle counts, and
  no numbers that were not supplied by the user. If a claim cannot be
  sourced, it is not made.
* Every line names its assumption, so a reader can tell advice from fact.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

DISCLAIMER: Final[str] = (
    "General guidance for everyday planning, not medical advice. "
    "For personal medical advice, speak to a doctor."
)
"""Short disclaimer shown with the plan wherever it is displayed."""


@dataclass(frozen=True, slots=True)
class ImpactNote:
    """The explanation attached to one recommendation.

    Attributes:
        impact: What the step changes, in plain words.
        assumption: What the step assumes to be true.
    """

    impact: str
    assumption: str


@dataclass(frozen=True, slots=True)
class ImpactTemplate:
    """The unformatted wording for one recommendation.

    Attributes:
        impact: Impact wording. May contain the placeholders ``name``,
            ``city``, ``aqi`` and ``band``.
        assumption: Assumption wording, with the same placeholders available.
    """

    impact: str
    assumption: str


IMPACT_TEMPLATES: Final[Mapping[str, ImpactTemplate]] = {
    # -- Daily routine -----------------------------------------------------
    "child.outdoor_activity.moderate": ImpactTemplate(
        impact=(
            "Keeps {name} away from the worst of the outdoor air and out of the "
            "traffic dust that settles around the school gate."
        ),
        assumption=(
            "Assumes indoor play can be arranged, and that the air outside at "
            "school time is no cleaner than the rest of the city."
        ),
    ),
    "child.outdoor_activity.severe": ImpactTemplate(
        impact=(
            "On the worst days, keeping {name} indoors removes most of that "
            "person's exposure for the day."
        ),
        assumption=(
            "Assumes school and play can be arranged indoors or postponed, and "
            "that the indoor air can be kept reasonably clean."
        ),
    ),
    "sensitive.windows_closed": ImpactTemplate(
        impact=(
            "Keeps the room {name} spends the most time in away from the "
            "outdoor spike, which matters most for lungs that react to smoke "
            "and dust."
        ),
        assumption=(
            "Assumes the room can be kept closed, and that the home has a way "
            "to keep indoor smoke and dust down."
        ),
    ),
    "sensitive.outdoor_mask": ImpactTemplate(
        impact=(
            "A properly fitted N95/FFP2-type respirator cuts the amount of "
            "fine particles {name} breathes when they have to be outside."
        ),
        assumption=(
            "Assumes the respirator is fitted to the face with a good seal and "
            "worn for the whole time outdoors. The fit, not the label, does "
            "the work."
        ),
    ),
    "sensitive.walk.shift": ImpactTemplate(
        impact=("Moves {name}'s walk to the cleaner part of the day instead of the dirtiest one."),
        assumption=(
            "Assumes winter air is usually cleaner in the middle of the day "
            "than at dawn. The cleanest hour changes from day to day."
        ),
    ),
    "sensitive.walk.skip": ImpactTemplate(
        impact=(
            "Skipping the walk on the worst day protects {name}, whose health "
            "risk is highest on bad-air days."
        ),
        assumption=("Assumes {name} can stay indoors and keep moving gently indoors instead."),
    ),
    "commute.two_wheeler.mask": ImpactTemplate(
        impact=(
            "A properly fitted N95/FFP2-type respirator filters the dust and "
            "fumes {name} rides through in traffic."
        ),
        assumption=(
            "Assumes the respirator is fitted to the face and worn for the "
            "whole ride. A loose cloth or surgical mask does not seal against "
            "the face in the same way."
        ),
    ),
    "commute.walk.shift": ImpactTemplate(
        impact=(
            "Walking in the cleaner part of the day gives {name} the same "
            "exercise with less smoke and dust."
        ),
        assumption=(
            "Assumes the timetable allows a shift, and that midday air is "
            "usually cleaner than early morning air."
        ),
    ),
    "worker.work_from_home.indoor_air": ImpactTemplate(
        impact=(
            "Keeping the work room closed through the peaks stops the dirtiest "
            "outdoor air coming in while {name} sits still for hours."
        ),
        assumption=(
            "Assumes {name} can keep the windows closed during work hours and "
            "air the room once the outdoor air improves."
        ),
    ),
    # -- Indoor air --------------------------------------------------------
    "household.ventilation.moderate": ImpactTemplate(
        impact=(
            "Airing the house at the better part of the day refreshes the "
            "rooms without pulling in the worst of the smog."
        ),
        assumption=(
            "Assumes outdoor air is worse at the morning and evening peaks "
            "than in the middle of the day."
        ),
    ),
    "household.ventilation.poor": ImpactTemplate(
        impact=(
            "Holding the windows shut through the peaks and airing only when "
            "the air is better keeps the indoor air from tracking the outdoor "
            "air."
        ),
        assumption=(
            "Assumes the home can be kept closed during the peaks, and that "
            "indoor smoke sources are reduced at the same time."
        ),
    ),
    "household.ventilation.severe": ImpactTemplate(
        impact=(
            "A short airing at the cleanest hour of the day gives the family "
            "fresh air without importing the smog peak into the house."
        ),
        assumption=(
            "Assumes a brief airing lowers indoor particles without bringing "
            "in much outdoor pollution, and that the rest of the day can "
            "stay closed."
        ),
    ),
    "household.purifier.placement": ImpactTemplate(
        impact=(
            "One purifier in {name}'s room helps the person most likely to be "
            "affected, instead of spreading a single purifier across the "
            "whole home."
        ),
        assumption=(
            "Assumes one purifier can meaningfully improve one closed room, "
            "and that {name} spends most of the day in it."
        ),
    ),
    "household.dust.wet_clean": ImpactTemplate(
        impact=(
            "Damp cleaning keeps the dust that is already inside the home "
            "from lifting back into the air."
        ),
        assumption=(
            "Assumes indoor dust is one of the main things settling in the "
            "rooms, and that a mop or damp cloth is available."
        ),
    ),
    "household.no_smoking_indoors": ImpactTemplate(
        impact=(
            "Removing smoke and strong fumes from indoors stops the family "
            "adding to the problem they are trying to escape outside."
        ),
        assumption=(
            "Assumes incense, tobacco, or cooking smoke are present in the "
            "home, and that the family can avoid them indoors."
        ),
    ),
    "household.seal.gaps": ImpactTemplate(
        impact=(
            "Closing the gaps around doors and windows cuts how much of the "
            "outside air gets in, so the indoor air stays cleaner for longer."
        ),
        assumption=(
            "Assumes the gaps are small enough to close with cloth or tape, "
            "and that the windows stay shut."
        ),
    ),
    # -- Sustainable alternatives ------------------------------------------
    "commute.two_wheeler.reduce_ride": ImpactTemplate(
        impact=(
            "Swapping the two-wheeler for a shared or public ride cuts both "
            "{name}'s roadside exposure and the pollution the family adds to "
            "the street."
        ),
        assumption=("Assumes a metro, bus, or shared ride is a realistic option for this trip."),
    ),
    "household.no_waste_burning": ImpactTemplate(
        impact=(
            "Not burning dry leaves or garbage keeps one of the strongest "
            "local sources of winter smoke away from the family's street."
        ),
        assumption=(
            "Assumes dry leaves and waste are burnt in the neighbourhood, and "
            "that the family can ask for green-waste collection instead."
        ),
    ),
    "household.no_firecrackers": ImpactTemplate(
        impact=(
            "Skipping firecrackers removes a spike of smoke and dust for the "
            "whole lane, including the family's own lungs."
        ),
        assumption=(
            "Assumes crackers would otherwise be used nearby, and that "
            "noise-free alternatives are acceptable to the family."
        ),
    ),
    "household.no_idling": ImpactTemplate(
        impact=(
            "Cutting engine idling near the home stops a concentrated plume "
            "of exhaust from settling right outside the door."
        ),
        assumption=(
            "Assumes vehicles idle in the lane or at the gate, and that the "
            "family controls when its own vehicle idles."
        ),
    ),
    "household.public_transport": ImpactTemplate(
        impact=(
            "Moving one or more trips to public transport puts more people in "
            "fewer vehicles, and keeps the family off the polluted roadside."
        ),
        assumption=(
            "Assumes a metro or bus route works for at least one of the household's regular trips."
        ),
    ),
    "household.green_waste_collection": ImpactTemplate(
        impact=(
            "Handing dry leaves to green-waste collection or compost keeps "
            "them from being burnt and turning into smoke near home."
        ),
        assumption=(
            "Assumes a green-waste collection or composting option is reachable in the colony."
        ),
    ),
}
"""Impact and assumption wording for every rule, keyed by rule id."""

FALLBACK_IMPACT: Final[ImpactTemplate] = ImpactTemplate(
    impact="Gives the family one concrete step to take on this air-quality day.",
    assumption=(
        "Assumes outdoor air is the main source of the family's exposure, and "
        "that indoor steps are possible."
    ),
)
"""Used when a rule has no wording of its own, so the plan never breaks."""


class _SafeContext(dict[str, object]):
    """A mapping that leaves unknown placeholders untouched when formatted."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def impact_for(rule_id: str, context: Mapping[str, object]) -> ImpactNote:
    """Return the impact note for a rule, formatted for display.

    Args:
        rule_id: Identifier of the rule the note belongs to.
        context: Values for the placeholders, for example ``name`` and ``city``.

    Returns:
        The formatted :class:`ImpactNote`. Unknown rule ids fall back to
        :data:`FALLBACK_IMPACT` rather than raising, so that a missing
        wording can never break the plan.
    """
    template = IMPACT_TEMPLATES.get(rule_id, FALLBACK_IMPACT)
    return ImpactNote(
        impact=safe_format(template.impact, context),
        assumption=safe_format(template.assumption, context),
    )


def safe_format(template: str, context: Mapping[str, object]) -> str:
    """Fill in the placeholders in a piece of user-facing wording.

    Unknown placeholders are left as they are, and a template that cannot be
    formatted is returned unchanged, so a wording problem can never break the
    plan.

    Args:
        template: The wording, with ``{name}`` style placeholders.
        context: The values for the placeholders.

    Returns:
        The formatted wording.
    """
    try:
        return template.format_map(_SafeContext(context))
    except (IndexError, KeyError, ValueError):
        return template
