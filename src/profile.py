"""Validated household profile data for the Urban Air Quality Assistant.

The profile describes *who* the advice is for: the city they live in, the
people in the household, how they travel, the kind of home they live in, and
how much money they can spend. Every value that can come from a person is
validated here, once, so that the rules engine can assume clean data.

All dataclasses are frozen: a household profile is a description of a real
family, and it must not change halfway through producing a plan.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

MAX_NAME_LENGTH: Final[int] = 60
"""Longest accepted member name, to bound memory and screen width."""

MAX_MEMBERS: Final[int] = 12
"""Largest household we will plan for."""

MAX_AGE: Final[int] = 120
"""Oldest accepted age, in years."""

MAX_CITY_LENGTH: Final[int] = 60
"""Longest accepted city string, before it is matched against the city list."""

ALLOWED_CITIES: Final[tuple[str, ...]] = (
    "Delhi",
    "Noida",
    "Greater Noida",
    "Gurugram",
    "Ghaziabad",
    "Faridabad",
)
"""Delhi NCR cities this application supports."""

_CITY_LOOKUP: Final[dict[str, str]] = {city.casefold(): city for city in ALLOWED_CITIES}
_CITY_LOOKUP.update(
    {
        "new delhi": "Delhi",
        "delhi ncr": "Delhi",
        "gurgaon": "Gurugram",
        "gr noida": "Greater Noida",
        "greater noida (noida)": "Greater Noida",
    }
)
"""Case insensitive city lookup, including the spellings people actually use."""


class ProfileError(ValueError):
    """Base class for household profile validation problems."""


class InvalidCityError(ProfileError):
    """Raised when the city is not one of the supported Delhi NCR cities."""


class InvalidMemberError(ProfileError):
    """Raised when a member entry is missing required information."""


class InvalidSensitivityError(ProfileError):
    """Raised when a sensitivity value is not a known category."""


class InvalidCommuteModeError(ProfileError):
    """Raised when a commute mode is not a known category."""


class InvalidHomeTypeError(ProfileError):
    """Raised when a home type is not a known category."""


class InvalidBudgetError(ProfileError):
    """Raised when the budget is not a non-negative whole number of rupees."""


class Sensitivity(StrEnum):
    """How strongly a person is affected by poor air.

    The value also carries the practical meaning: what the person does during
    a normal day, which is what the rules engine needs to plan for.
    """

    CHILD = "child"
    ELDERLY = "elderly"
    ASTHMATIC = "asthmatic"
    HEALTHY_ADULT = "healthy_adult"


class CommuteMode(StrEnum):
    """How a person travels to work or school on a normal day."""

    TWO_WHEELER = "two_wheeler"
    CAR = "car"
    METRO = "metro"
    BUS = "bus"
    WALK = "walk"
    WORK_FROM_HOME = "work_from_home"


class HomeType(StrEnum):
    """The kind of home the household lives in."""

    APARTMENT = "apartment"
    HOUSE = "house"
    VILLA = "villa"
    OTHER = "other"


SENSITIVITY_LABELS: Final[Mapping[Sensitivity, str]] = {
    Sensitivity.CHILD: "a child",
    Sensitivity.ELDERLY: "an older adult",
    Sensitivity.ASTHMATIC: "a person with asthma",
    Sensitivity.HEALTHY_ADULT: "a healthy adult",
}
"""Short human readable labels, used to explain a decision in plain words."""

VULNERABILITY_ORDER: Final[Mapping[Sensitivity, int]] = {
    Sensitivity.ASTHMATIC: 4,
    Sensitivity.CHILD: 3,
    Sensitivity.ELDERLY: 2,
    Sensitivity.HEALTHY_ADULT: 1,
}
"""Ranking used to find the household member the smog hits hardest.

Asthma is treated as the strongest signal, then a child, then an older adult.
The order is a stated assumption of the product, not a medical claim.
"""


@dataclass(frozen=True, slots=True)
class Member:
    """One person in the household.

    Attributes:
        name: The person's name, used to address advice to them.
        age: Age in years.
        sensitivity: How strongly polluted air affects this person.
        commute_mode: Optional override of the household commute mode, for a
            household where different people travel differently. When it is
            None the household commute mode applies.
    """

    name: str
    age: int
    sensitivity: Sensitivity
    commute_mode: CommuteMode | None = None

    def __post_init__(self) -> None:
        """Validate and normalise the member details."""
        object.__setattr__(self, "name", _validate_name(self.name))
        object.__setattr__(self, "age", _validate_age(self.age))
        object.__setattr__(self, "sensitivity", _coerce_sensitivity(self.sensitivity))
        if self.commute_mode is not None:
            object.__setattr__(self, "commute_mode", _coerce_commute_mode(self.commute_mode))

    @property
    def sensitivity_label(self) -> str:
        """Short human readable description of this person's sensitivity."""
        return SENSITIVITY_LABELS[self.sensitivity]

    @property
    def vulnerability_rank(self) -> int:
        """Rank of this person within the vulnerability ordering."""
        return VULNERABILITY_ORDER[self.sensitivity]

    @property
    def is_sensitive(self) -> bool:
        """True when this person is more affected by smoke than an average adult."""
        return self.sensitivity is not Sensitivity.HEALTHY_ADULT


@dataclass(frozen=True, slots=True)
class Household:
    """The family the plan is built for.

    Attributes:
        city: One of :data:`ALLOWED_CITIES`.
        members: The people in the household. At least one is required.
        commute_mode: The default way this household travels.
        home_type: The kind of home they live in.
        budget_inr: Money available for this plan, in whole rupees.
    """

    city: str
    members: tuple[Member, ...]
    commute_mode: CommuteMode
    home_type: HomeType
    budget_inr: int

    def __post_init__(self) -> None:
        """Validate and normalise the household details."""
        object.__setattr__(self, "city", _validate_city(self.city))
        object.__setattr__(self, "members", _validate_members(self.members))
        object.__setattr__(self, "commute_mode", _coerce_commute_mode(self.commute_mode))
        object.__setattr__(self, "home_type", _coerce_home_type(self.home_type))
        object.__setattr__(self, "budget_inr", _validate_budget(self.budget_inr))

    @property
    def has_sensitive_member(self) -> bool:
        """True when at least one member is more affected by smoke."""
        return any(member.is_sensitive for member in self.members)

    @property
    def most_vulnerable_member(self) -> Member:
        """The member the smog hits hardest, and whose advice sets the tone.

        Ties are broken towards the youngest child, and towards the oldest
        adult, so that the same household always produces the same plan.

        Raises:
            ProfileError: If the household somehow has no members.
        """
        return most_vulnerable_member(self.members)


def most_vulnerable_member(members: Iterable[Member]) -> Member | None:
    """Return the member the smog hits hardest.

    Args:
        members: The household members to compare.

    Returns:
        The most vulnerable member, or None when there are no members.
    """
    ranked = sorted(members, key=_vulnerability_sort_key)
    return ranked[0] if ranked else None


def has_sensitive_member(members: Iterable[Member]) -> bool:
    """Report whether any member is more affected by smoke.

    Args:
        members: The household members to inspect.

    Returns:
        True when at least one member is a child, an older adult, or has asthma.
    """
    return any(member.is_sensitive for member in members)


def effective_commute_mode(member: Member, household: Household) -> CommuteMode:
    """Return how a member actually travels.

    Args:
        member: The member to check.
        household: The household that supplies the default commute mode.

    Returns:
        The member's own commute mode when they have one, otherwise the
        household default.
    """
    return member.commute_mode or household.commute_mode


def _vulnerability_sort_key(member: Member) -> tuple[int, int, str]:
    """Sort key ordering members from most to least vulnerable."""
    age_tiebreak = member.age if member.sensitivity is Sensitivity.CHILD else -member.age
    return (-member.vulnerability_rank, age_tiebreak, member.name)


def _validate_name(name: object) -> str:
    """Validate and normalise a member name.

    Args:
        name: The candidate name.

    Returns:
        The name with surrounding and repeated whitespace collapsed.

    Raises:
        InvalidMemberError: If the name is not usable.
    """
    if not isinstance(name, str):
        raise InvalidMemberError("Member name must be text.")
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidMemberError("Member name must not be empty.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise InvalidMemberError(f"Member name must be at most {MAX_NAME_LENGTH} characters.")
    if any(ord(character) < 32 or ord(character) == 127 for character in cleaned):
        raise InvalidMemberError("Member name must not contain control characters.")
    return cleaned


def _validate_age(age: object) -> int:
    """Validate an age in years.

    Args:
        age: The candidate age.

    Returns:
        The age unchanged.

    Raises:
        InvalidMemberError: If the age is not a whole number within range.
    """
    if isinstance(age, bool) or not isinstance(age, int):
        raise InvalidMemberError("Age must be a whole number of years.")
    if age < 0 or age > MAX_AGE:
        raise InvalidMemberError(f"Age must be between 0 and {MAX_AGE} years.")
    return age


def _validate_city(city: object) -> str:
    """Validate a city against the supported Delhi NCR cities.

    Args:
        city: The candidate city name.

    Returns:
        The canonical city name.

    Raises:
        InvalidCityError: If the city is not supported.
    """
    if not isinstance(city, str):
        raise InvalidCityError("City must be text.")
    text = " ".join(city.split())
    if not text:
        raise InvalidCityError("City must not be empty.")
    if len(text) > MAX_CITY_LENGTH:
        raise InvalidCityError(f"City must be at most {MAX_CITY_LENGTH} characters.")
    canonical = _CITY_LOOKUP.get(text.casefold())
    if canonical is None:
        supported = ", ".join(ALLOWED_CITIES)
        raise InvalidCityError(f"City must be one of: {supported}.")
    return canonical


def _validate_members(members: object) -> tuple[Member, ...]:
    """Validate the member list of a household.

    Args:
        members: The candidate members, as any iterable of :class:`Member`.

    Returns:
        The members as a tuple.

    Raises:
        InvalidMemberError: If the list is empty, too long, contains a
            non-member, or contains two people with the same name.
    """
    if isinstance(members, (Member, str)):
        raise InvalidMemberError("Members must be a list of household members.")
    try:
        collected = tuple(members)  # type: ignore[arg-type]
    except TypeError:
        raise InvalidMemberError("Members must be a list of household members.") from None
    if not collected:
        raise InvalidMemberError("Add at least one household member.")
    if len(collected) > MAX_MEMBERS:
        raise InvalidMemberError(f"A household can have at most {MAX_MEMBERS} members.")
    for member in collected:
        if not isinstance(member, Member):
            raise InvalidMemberError("Members must be a list of household members.")
    seen: set[str] = set()
    for member in collected:
        key = member.name.casefold()
        if key in seen:
            raise InvalidMemberError("Two household members cannot share the same name.")
        seen.add(key)
    return collected


def _validate_budget(budget: object) -> int:
    """Validate the available budget in rupees.

    Args:
        budget: The candidate budget.

    Returns:
        The budget unchanged.

    Raises:
        InvalidBudgetError: If the budget is not a non-negative whole number.
    """
    if isinstance(budget, bool) or not isinstance(budget, int):
        raise InvalidBudgetError("Budget must be a whole number of rupees.")
    if budget < 0:
        raise InvalidBudgetError("Budget must not be negative.")
    return budget


def _coerce_sensitivity(value: object) -> Sensitivity:
    """Return a :class:`Sensitivity` for a supplied value.

    Args:
        value: A Sensitivity, or the text of one.

    Returns:
        The matching sensitivity.

    Raises:
        InvalidSensitivityError: If the value is not a known sensitivity.
    """
    if isinstance(value, Sensitivity):
        return value
    if isinstance(value, str):
        try:
            return Sensitivity(value.strip().lower())
        except ValueError:
            pass
    supported = ", ".join(sensitivity.value for sensitivity in Sensitivity)
    raise InvalidSensitivityError(f"Sensitivity must be one of: {supported}.")


def _coerce_commute_mode(value: object) -> CommuteMode:
    """Return a :class:`CommuteMode` for a supplied value.

    Args:
        value: A CommuteMode, or the text of one.

    Returns:
        The matching commute mode.

    Raises:
        InvalidCommuteModeError: If the value is not a known commute mode.
    """
    if isinstance(value, CommuteMode):
        return value
    if isinstance(value, str):
        try:
            return CommuteMode(value.strip().lower())
        except ValueError:
            pass
    supported = ", ".join(mode.value for mode in CommuteMode)
    raise InvalidCommuteModeError(f"Commute mode must be one of: {supported}.")


def _coerce_home_type(value: object) -> HomeType:
    """Return a :class:`HomeType` for a supplied value.

    Args:
        value: A HomeType, or the text of one.

    Returns:
        The matching home type.

    Raises:
        InvalidHomeTypeError: If the value is not a known home type.
    """
    if isinstance(value, HomeType):
        return value
    if isinstance(value, str):
        try:
            return HomeType(value.strip().lower())
        except ValueError:
            pass
    supported = ", ".join(home.value for home in HomeType)
    raise InvalidHomeTypeError(f"Home type must be one of: {supported}.")
