"""Tests for the CPCB AQI band classification."""

import math
from itertools import pairwise

import pytest

from src.aqi import (
    BAND_SPECS,
    AQIBand,
    InvalidAQIScoreError,
    all_bands,
    band_spec,
    classify_aqi,
    is_valid_aqi,
    read_aqi,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, AQIBand.GOOD),
        (1, AQIBand.GOOD),
        (50, AQIBand.GOOD),
        (51, AQIBand.SATISFACTORY),
        (100, AQIBand.SATISFACTORY),
        (101, AQIBand.MODERATE),
        (200, AQIBand.MODERATE),
        (201, AQIBand.POOR),
        (300, AQIBand.POOR),
        (301, AQIBand.VERY_POOR),
        (400, AQIBand.VERY_POOR),
        (401, AQIBand.SEVERE),
        (500, AQIBand.SEVERE),
    ],
)
def test_classify_aqi_band_boundaries(value, expected):
    assert classify_aqi(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (50.4, AQIBand.GOOD),
        (50.6, AQIBand.SATISFACTORY),
        (412.4, AQIBand.SEVERE),
        (412.6, AQIBand.SEVERE),
    ],
)
def test_classify_aqi_rounds_fractional_readings(value, expected):
    assert classify_aqi(value) is expected


@pytest.mark.parametrize(
    "value",
    [
        -1,
        -0.5,
        501,
        1000,
        "abc",
        "",
        "   ",
        "12,5",
        None,
        True,
        False,
        float("nan"),
        float("inf"),
        float("-inf"),
        [],
        {},
        object(),
    ],
)
def test_classify_aqi_rejects_unusable_values(value):
    with pytest.raises(InvalidAQIScoreError):
        classify_aqi(value)


def test_classify_aqi_rejects_values_outside_the_scale():
    with pytest.raises(InvalidAQIScoreError):
        classify_aqi(501)
    with pytest.raises(InvalidAQIScoreError):
        classify_aqi(-1)


def test_classify_aqi_error_does_not_echo_the_input():
    with pytest.raises(InvalidAQIScoreError) as error:
        classify_aqi("secret value that should not be repeated")

    message = str(error.value)
    assert "secret value" not in message
    assert "0 and 500" in message


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("412", AQIBand.SEVERE),
        ("  150  ", AQIBand.MODERATE),
        ("0", AQIBand.GOOD),
        ("500", AQIBand.SEVERE),
    ],
)
def test_classify_aqi_accepts_numeric_strings(value, expected):
    assert classify_aqi(value) is expected


def test_is_valid_aqi():
    assert is_valid_aqi(0)
    assert is_valid_aqi(500)
    assert is_valid_aqi("250")
    assert not is_valid_aqi(501)
    assert not is_valid_aqi("abc")
    assert not is_valid_aqi(None)
    assert not is_valid_aqi(True)


def test_read_aqi_returns_value_band_and_spec():
    reading = read_aqi(412)

    assert reading.value == 412
    assert reading.band is AQIBand.SEVERE
    assert reading.spec.label == "Severe"
    assert reading.severity == 5
    assert reading.display_value == "412"


def test_read_aqi_rejects_invalid_values():
    with pytest.raises(InvalidAQIScoreError):
        read_aqi(501)


def test_band_specs_cover_the_whole_scale_without_gaps():
    assert all_bands() == BAND_SPECS
    assert BAND_SPECS[0].lower == 0
    assert BAND_SPECS[-1].upper == 500
    for current, following in pairwise(BAND_SPECS):
        assert current.upper + 1 == following.lower


def test_band_specs_have_strictly_increasing_severity():
    severities = [spec.severity for spec in BAND_SPECS]
    assert severities == sorted(severities)
    assert len(set(severities)) == len(severities)


def test_band_spec_looks_up_a_band():
    spec = band_spec(AQIBand.POOR)

    assert spec.label == "Poor"
    assert spec.lower == 201
    assert spec.upper == 300


def test_band_values_are_stable_strings():
    assert AQIBand.VERY_POOR.value == "very_poor"
    assert AQIBand.GOOD == "good"


def test_display_value_rounds_for_display():
    assert read_aqi(412.4).display_value == "412"
    assert read_aqi(412.6).display_value == "413"
    assert math.isfinite(read_aqi(100).value)
