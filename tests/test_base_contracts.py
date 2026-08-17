from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    BaseRecordMetadata,
    PosteriorMixin,
    TemporalValidityMixin,
    ValidTimeInterval,
)


def test_valid_time_is_half_open(now):
    interval = ValidTimeInterval(start=now, end=now + timedelta(seconds=10))
    assert interval.contains(now)
    assert interval.contains(now + timedelta(seconds=9))
    assert not interval.contains(now + timedelta(seconds=10))


def test_adjacent_valid_times_do_not_overlap(now):
    first = ValidTimeInterval(start=now, end=now + timedelta(seconds=10))
    second = ValidTimeInterval(
        start=now + timedelta(seconds=10), end=now + timedelta(seconds=20)
    )
    assert not first.overlaps(second)


def test_invalid_or_naive_valid_time_is_rejected(now):
    with pytest.raises(ValidationError):
        ValidTimeInterval(start=now, end=now)
    with pytest.raises(ValidationError):
        ValidTimeInterval(start=datetime(2026, 8, 10, 8, 0))


def test_observed_time_must_be_aware(interval):
    with pytest.raises(ValidationError):
        TemporalValidityMixin(
            valid_time=interval,
            observed_time=datetime(2026, 8, 10, 8, 0),
        )


def test_base_metadata_has_no_reliability_or_posterior_fields():
    properties = BaseRecordMetadata.model_json_schema()["properties"]
    assert "evidence_reliability" not in properties
    assert "posterior_probability" not in properties


def test_posterior_probability_is_bounded():
    with pytest.raises(ValidationError):
        PosteriorMixin(posterior_probability=1.01, normalization_group="location")

