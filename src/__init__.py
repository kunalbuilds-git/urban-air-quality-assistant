"""Urban Air Quality Assistant.

A GenAI-powered assistant that helps families in Delhi NCR make decisions on
severe winter smog days: what to change in the daily routine, what to do
about the air indoors, and which lower emission alternatives are worth
switching to.

The package is organised so that the decisions never depend on a language
model:

* :mod:`src.aqi` turns an AQI reading into a CPCB band.
* :mod:`src.profile` validates the household the advice is for.
* :mod:`src.rules` makes the decisions, as a table of rules.
* :mod:`src.impact` explains each decision in plain words.
* :mod:`src.budget` fits the decisions into the money available.
"""

from src.impact import DISCLAIMER

__all__ = ["DISCLAIMER", "__version__"]

__version__ = "0.1.0"
"""Version of the application package."""
