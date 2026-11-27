"""CPCB AQI band classification for the Urban Air Quality Assistant.

This module owns exactly one responsibility: turning a numeric AQI reading
into an Indian CPCB band and describing that band. It performs no I/O, holds
no household logic, and never invents a value.

The bands follow the CPCB National Air Quality Index categories:

===========  =========================
Band         Range
===========  =========================
Good         0 - 50
Satisfactory  51 - 100
Moderate     101 - 200
Poor         201 - 300
Very Poor    301 - 400
Severe       401 - 500
===========  =========================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

MIN_AQI: Final[float] = 0.0
"""Lowest AQI value the application accepts."""

MAX_AQI: Final[float] = 500.0
"""Highest AQI value the application accepts."""


class AQIError(ValueError):
    """Base class for problems with an AQI reading."""


class InvalidAQIScoreError(AQIError):
    """Raised when an AQI reading is not a number within the accepted range."""


class AQIBand(StrEnum):
    """The six CPCB AQI bands, ordered from best to worst."""

    GOOD = "good"
    SATISFACTORY = "satisfactory"
    MODERATE = "moderate"
    POOR = "poor"
    VERY_POOR = "very_poor"
    SEVERE = "severe"


@dataclass(frozen=True, slots=True)
class AQIBandSpec:
    """Static description of one CPCB AQI band.

    Attributes:
        band: The band identifier.
        label: Human readable band name, for example "Very Poor".
        lower: Inclusive lower bound of the band.
        upper: Inclusive upper bound of the band.
        severity: Rank of the band from 0 (best) to 5 (worst). Rules compare
            severity instead of band names so that thresholds stay readable.
    """

    band: AQIBand
    label: str
    lower: int
    upper: int
    severity: int


BAND_SPECS: Final[tuple[AQIBandSpec, ...]] = (
    AQIBandSpec(AQIBand.GOOD, "Good", 0, 50, 0),
    AQIBandSpec(AQIBand.SATISFACTORY, "Satisfactory", 51, 100, 1),
    AQIBandSpec(AQIBand.MODERATE, "Moderate", 101, 200, 2),
    AQIBandSpec(AQIBand.POOR, "Poor", 201, 300, 3),
    AQIBandSpec(AQIBand.VERY_POOR, "Very Poor", 301, 400, 4),
    AQIBandSpec(AQIBand.SEVERE, "Severe", 401, 500, 5),
)
"""The CPCB band table, ordered from the cleanest band to the worst."""


@dataclass(frozen=True, slots=True)
class AQIReading:
    """A validated AQI reading together with its band.

    Attributes:
        value: The numeric reading as supplied, after validation.
        band: The CPCB band the value falls into.
        spec: The static description of that band.
    """

    value: float
    band: AQIBand
    spec: AQIBandSpec

    @property
    def severity(self) -> int:
        """Rank of the band from 0 (best) to 5 (worst)."""
        return self.spec.severity

    @property
    def display_value(self) -> str:
        """The reading rounded for display, for example "412"."""
        return str(round(self.value))


def _round_to_whole(number: float) -> int:
    """Round a reading to the nearest whole number, rounding halves up.

    AQI is reported as a whole number, and the band boundaries are whole
    numbers, so a fractional reading such as 50.6 is placed in the band it
    rounds to.

    Args:
        number: The validated reading.

    Returns:
        The reading as a whole number.
    """
    return math.floor(number + 0.5)


def all_bands() -> tuple[AQIBandSpec, ...]:
    """Return every band specification from cleanest to worst."""
    return BAND_SPECS


def band_spec(band: AQIBand) -> AQIBandSpec:
    """Return the specification for a band.

    Args:
        band: The band to describe.

    Returns:
        The matching :class:`AQIBandSpec`.

    Raises:
        AQIError: If the band is not one of the six CPCB bands.
    """
    for spec in BAND_SPECS:
        if spec.band == band:
            return spec
    raise AQIError("Unknown AQI band.")


def classify_aqi(value: int | float | str) -> AQIBand:
    """Return the CPCB band for a numeric AQI reading.

    Args:
        value: The reading. May be an int, a float, or a string holding a
            number. Numeric strings are accepted because a person may type
            the AQI by hand.

    Returns:
        The matching :class:`AQIBand`.

    Raises:
        InvalidAQIScoreError: If the value is not a number, is not finite, or
            falls outside the accepted range of 0 to 500.
    """
    number = _coerce_aqi(value)
    whole = _round_to_whole(number)
    for spec in BAND_SPECS:
        if spec.lower <= whole <= spec.upper:
            return spec.band
    raise InvalidAQIScoreError("AQI must be a number between 0 and 500.")


def read_aqi(value: int | float | str) -> AQIReading:
    """Validate a reading and return it together with its band.

    Args:
        value: The reading to validate.

    Returns:
        An :class:`AQIReading` holding the value, its band, and the band spec.

    Raises:
        InvalidAQIScoreError: If the value cannot be accepted.
    """
    number = _coerce_aqi(value)
    band = classify_aqi(number)
    return AQIReading(value=number, band=band, spec=band_spec(band))


def is_valid_aqi(value: object) -> bool:
    """Report whether a value can be accepted as an AQI reading.

    Args:
        value: The candidate value, of any type.

    Returns:
        True when the value is a finite number within 0 to 500.
    """
    try:
        _coerce_aqi(value)  # type: ignore[arg-type]
    except InvalidAQIScoreError:
        return False
    return True


def _coerce_aqi(value: object) -> float:
    """Validate a raw value and return it as a float.

    The error messages deliberately state the expected format and never echo
    the supplied value back, so that unexpected input cannot be reflected
    into a message shown to a user or written to a log.

    Args:
        value: The candidate value, of any type.

    Returns:
        The value as a float.

    Raises:
        InvalidAQIScoreError: If the value is not an acceptable AQI reading.
    """
    if isinstance(value, bool):
        raise InvalidAQIScoreError("AQI must be a number between 0 and 500.")

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise InvalidAQIScoreError("AQI must be a number between 0 and 500.")
        try:
            number = float(text)
        except ValueError:
            raise InvalidAQIScoreError("AQI must be a number between 0 and 500.") from None
    elif isinstance(value, int | float):
        number = float(value)
    else:
        raise InvalidAQIScoreError("AQI must be a number between 0 and 500.")

    if math.isnan(number) or math.isinf(number):
        raise InvalidAQIScoreError("AQI must be a number between 0 and 500.")

    if not MIN_AQI <= number <= MAX_AQI:
        raise InvalidAQIScoreError("AQI must be a number between 0 and 500.")

    return number
