"""Entry point for the Urban Air Quality Assistant.

The user interface arrives in Phase 3, as a Streamlit app. Until then this
module is a placeholder: it keeps the entry point in place, states plainly
what is and is not built yet, and points at the parts that are.

The decisions themselves already work and can be used from Python today:

    from src.profile import Household, Member
    from src.rules import build_plan

    household = Household(
        city="Delhi",
        members=(Member(name="Dadi", age=68, sensitivity="asthmatic"),),
        commute_mode="car",
        home_type="apartment",
        budget_inr=500,
    )
    plan = build_plan(412, household)
"""

from __future__ import annotations

from src import DISCLAIMER, __version__

PLANNED_UI = "The Streamlit interface lands in Phase 3 of the build."


def main() -> None:
    """Print what the application can do today."""
    print(f"Urban Air Quality Assistant, version {__version__}")
    print()
    print("Built so far:")
    print("  - CPCB AQI band classification (src/aqi.py)")
    print("  - Household profile validation (src/profile.py)")
    print("  - The rules engine that makes the decisions (src/rules.py)")
    print("  - Plain-language impact lines and assumptions (src/impact.py)")
    print("  - Budget-aware ranking of the recommendations (src/budget.py)")
    print()
    print(f"Still to come: {PLANNED_UI}")
    print("The Gemini personalisation layer arrives in Phase 2.")
    print()
    print(f"Note: {DISCLAIMER}")


if __name__ == "__main__":
    main()
