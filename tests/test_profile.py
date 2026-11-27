"""Tests for household profile validation and vulnerability ordering."""

import dataclasses

import pytest

from src.profile import (
    ALLOWED_CITIES,
    MAX_AGE,
    MAX_MEMBERS,
    MAX_NAME_LENGTH,
    CommuteMode,
    HomeType,
    Household,
    InvalidBudgetError,
    InvalidCityError,
    InvalidCommuteModeError,
    InvalidHomeTypeError,
    InvalidMemberError,
    InvalidSensitivityError,
    Member,
    Sensitivity,
    effective_commute_mode,
    has_sensitive_member,
    most_vulnerable_member,
)


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


def test_persona_household_is_accepted():
    household = Household(
        city="Delhi",
        members=(
            make_member("Rohit", 38, Sensitivity.HEALTHY_ADULT, CommuteMode.TWO_WHEELER),
            make_member("Neha", 35, Sensitivity.HEALTHY_ADULT, CommuteMode.WORK_FROM_HOME),
            make_member("Aarav", 7, Sensitivity.CHILD),
            make_member("Dadi", 68, Sensitivity.ASTHMATIC),
        ),
        commute_mode=CommuteMode.CAR,
        home_type=HomeType.APARTMENT,
        budget_inr=500,
    )

    assert household.city == "Delhi"
    assert len(household.members) == 4
    assert household.budget_inr == 500
    assert household.has_sensitive_member


def test_household_requires_at_least_one_member():
    with pytest.raises(InvalidMemberError):
        make_household(members=())


def test_household_rejects_a_non_list_of_members():
    with pytest.raises(InvalidMemberError):
        make_household(members="Rohit")


def test_household_rejects_too_many_members():
    members = tuple(make_member(f"Person {index}") for index in range(MAX_MEMBERS + 1))

    with pytest.raises(InvalidMemberError):
        make_household(members=members)


def test_household_accepts_the_largest_allowed_number_of_members():
    members = tuple(make_member(f"Person {index}") for index in range(MAX_MEMBERS))

    assert len(make_household(members=members).members) == MAX_MEMBERS


def test_household_rejects_two_members_with_the_same_name():
    members = (make_member("Rohit"), make_member("rohit"))

    with pytest.raises(InvalidMemberError):
        make_household(members=members)


@pytest.mark.parametrize("city", ["Mumbai", "Jaipur", "Delhi rural", "Noida extension"])
def test_household_rejects_cities_outside_delhi_ncr(city):
    with pytest.raises(InvalidCityError):
        make_household(city=city)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Delhi", "Delhi"),
        ("delhi", "Delhi"),
        ("NOIDA", "Noida"),
        ("Greater Noida", "Greater Noida"),
        ("greater noida", "Greater Noida"),
        ("Gurugram", "Gurugram"),
        ("gurgaon", "Gurugram"),
        ("Gurgaon", "Gurugram"),
        ("Ghaziabad", "Ghaziabad"),
        ("Faridabad", "Faridabad"),
        ("  Delhi  ", "Delhi"),
    ],
)
def test_city_is_normalised_to_the_canonical_name(given, expected):
    assert make_household(city=given).city == expected


def test_every_allowed_city_is_accepted():
    for city in ALLOWED_CITIES:
        assert make_household(city=city).city == city


def test_household_rejects_an_empty_city():
    with pytest.raises(InvalidCityError):
        make_household(city="   ")


def test_household_rejects_a_very_long_city():
    with pytest.raises(InvalidCityError):
        make_household(city="D" * 200)


def test_member_rejects_an_empty_name():
    with pytest.raises(InvalidMemberError):
        make_member(name="")


def test_member_rejects_a_name_that_is_only_whitespace():
    with pytest.raises(InvalidMemberError):
        make_member(name="   \t  ")


def test_member_rejects_a_name_that_is_too_long():
    with pytest.raises(InvalidMemberError):
        make_member(name="N" * (MAX_NAME_LENGTH + 1))


def test_member_accepts_a_name_at_the_length_limit():
    member = make_member(name="N" * MAX_NAME_LENGTH)

    assert len(member.name) == MAX_NAME_LENGTH


def test_member_rejects_control_characters_in_a_name():
    with pytest.raises(InvalidMemberError):
        make_member(name="Rohit\x00")


def test_member_normalises_whitespace_in_a_name():
    assert make_member(name="  Rohit   Sharma ").name == "Rohit Sharma"


@pytest.mark.parametrize("age", [-1, MAX_AGE + 1, 150])
def test_member_rejects_an_impossible_age(age):
    with pytest.raises(InvalidMemberError):
        make_member(age=age)


@pytest.mark.parametrize("age", [True, False, "38", 38.5, None])
def test_member_rejects_an_age_that_is_not_a_whole_number(age):
    with pytest.raises(InvalidMemberError):
        make_member(age=age)


@pytest.mark.parametrize("age", [0, 7, 38, 68, MAX_AGE])
def test_member_accepts_a_sensible_age(age):
    assert make_member(age=age).age == age


def test_member_rejects_an_unknown_sensitivity():
    with pytest.raises(InvalidSensitivityError):
        make_member(sensitivity="super_sensitive")


def test_member_accepts_a_sensitivity_written_as_text():
    member = make_member(sensitivity="child")

    assert member.sensitivity is Sensitivity.CHILD


def test_household_rejects_an_unknown_commute_mode():
    with pytest.raises(InvalidCommuteModeError):
        Household(
            city="Delhi",
            members=(make_member(),),
            commute_mode="hovercraft",
            home_type=HomeType.APARTMENT,
            budget_inr=0,
        )


def test_household_rejects_an_unknown_home_type():
    with pytest.raises(InvalidHomeTypeError):
        Household(
            city="Delhi",
            members=(make_member(),),
            commute_mode=CommuteMode.CAR,
            home_type="igloo",
            budget_inr=0,
        )


def test_household_rejects_a_negative_budget():
    with pytest.raises(InvalidBudgetError):
        make_household(budget=-1)


@pytest.mark.parametrize("budget", [True, False, "500", 500.5, None])
def test_household_rejects_a_budget_that_is_not_a_whole_number(budget):
    with pytest.raises(InvalidBudgetError):
        make_household(budget=budget)


def test_household_accepts_a_zero_budget():
    household = make_household(budget=0)

    assert household.budget_inr == 0


def test_household_accepts_a_very_large_budget():
    household = make_household(budget=10**12)

    assert household.budget_inr == 10**12


def test_household_is_frozen():
    household = make_household()

    with pytest.raises(dataclasses.FrozenInstanceError):
        household.budget_inr = 1


def test_members_are_stored_as_a_tuple():
    household = make_household(members=[make_member()])

    assert isinstance(household.members, tuple)


def test_most_vulnerable_member_is_the_one_with_asthma():
    members = (
        make_member("Rohit", 38, Sensitivity.HEALTHY_ADULT),
        make_member("Aarav", 7, Sensitivity.CHILD),
        make_member("Dadi", 68, Sensitivity.ASTHMATIC),
    )

    assert most_vulnerable_member(members).name == "Dadi"


def test_most_vulnerable_member_prefers_a_child_over_an_older_adult():
    members = (
        make_member("Dadi", 68, Sensitivity.ELDERLY),
        make_member("Aarav", 7, Sensitivity.CHILD),
    )

    assert most_vulnerable_member(members).name == "Aarav"


def test_most_vulnerable_member_breaks_a_tie_towards_the_youngest_child():
    members = (
        make_member("Older sibling", 11, Sensitivity.CHILD),
        make_member("Youngest sibling", 4, Sensitivity.CHILD),
    )

    assert most_vulnerable_member(members).name == "Youngest sibling"


def test_most_vulnerable_member_is_none_for_an_empty_household():
    assert most_vulnerable_member(()) is None


def test_has_sensitive_member():
    assert has_sensitive_member((make_member(sensitivity=Sensitivity.CHILD),))
    assert has_sensitive_member((make_member(sensitivity=Sensitivity.ELDERLY),))
    assert has_sensitive_member((make_member(sensitivity=Sensitivity.ASTHMATIC),))
    assert not has_sensitive_member((make_member(sensitivity=Sensitivity.HEALTHY_ADULT),))


def test_effective_commute_mode_uses_the_member_override():
    household = make_household()
    member = make_member(commute=CommuteMode.TWO_WHEELER)

    assert effective_commute_mode(member, household) is CommuteMode.TWO_WHEELER


def test_effective_commute_mode_falls_back_to_the_household():
    household = make_household()
    member = make_member(commute=None)

    assert effective_commute_mode(member, household) is CommuteMode.CAR
