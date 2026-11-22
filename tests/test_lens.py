"""Contract tests for the lens-flare helpers.

The tests use normalized screen UV, normalized intensity/color values and
an absolute tolerance of ``1e-6``.  They are intentionally read-only:
the repository's task is to fix ``flare/lens.py``, not the tests.
"""

import pytest

from flare.lens import (
    FlareError,
    aperture_mask,
    chroma_split,
    falloff,
    flare_batch,
    ghost_positions,
    halo_position,
    validate,
    visible_source,
)

TOL = 1e-6

BASE_CONFIG = {
    "count": 4,
    "spread": 0.8,
    "blades": 4,
    "power": 2.0,
    "radius": 0.75,
    "rgb": (0.2, 0.4, 0.6),
    "amount": 0.1,
    "depth_map": [[0.0, 0.0], [0.0, 0.0]],
}


def test_01_ghosts_are_centrosymmetric():
    """Ghosts must span both sides of the image center, not hug the source."""
    ghosts = ghost_positions((0.8, 0.4), 5, 0.8)

    assert ghosts == pytest.approx(
        [
            (0.26, 0.58),
            (0.38, 0.54),
            (0.50, 0.50),
            (0.62, 0.46),
            (0.74, 0.42),
        ],
        abs=TOL,
        rel=0,
    )
    assert any(u < 0.5 for u, _ in ghosts)
    assert any(u > 0.5 for u, _ in ghosts)


def test_02_offscreen_ghosts_are_culled():
    """Candidates outside the canvas must not be returned for drawing."""
    ghosts = ghost_positions((0.1, 0.5), 4, 1.5)

    assert ghosts == pytest.approx([(0.7, 0.5), (0.3, 0.5)], abs=TOL, rel=0)
    assert len(ghosts) == 2
    assert all(0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 for u, v in ghosts)


def test_03_occlusion_uses_depth_not_brightness():
    """A dark, empty background must stay visible; an occluder must hide it."""
    clear = [[0.0, 0.0], [0.0, 0.0]]
    assert visible_source((0.25, 0.25), clear) is True
    assert visible_source((0.75, 0.75), clear) is True

    wall = [[0.2, 0.0], [0.0, 0.0]]
    assert visible_source((0.25, 0.25), wall) is False
    assert visible_source((0.75, 0.75), wall) is True


def test_04_chroma_channels_split_in_opposite_directions():
    """Red and blue must move opposite ways and remain clamped to 0..1."""
    assert chroma_split((0.3, 0.3, 0.3), 0.2) == pytest.approx(
        (0.5, 0.3, 0.1), abs=TOL, rel=0
    )
    assert chroma_split((0.95, 0.5, 0.05), 0.2) == pytest.approx(
        (1.0, 0.5, 0.0), abs=TOL, rel=0
    )

    red, green, blue = chroma_split((0.3, 0.3, 0.3), 0.2)
    assert red > 0.3
    assert green == pytest.approx(0.3, abs=TOL, rel=0)
    assert blue < 0.3


def test_05_aperture_mask_is_polygonal():
    """A four-blade aperture is a diamond, not its circumscribed circle."""
    assert aperture_mask((0.5, 0.5), 4) == pytest.approx(1.0, abs=TOL, rel=0)
    assert aperture_mask((0.9, 0.5), 4) == pytest.approx(1.0, abs=TOL, rel=0)
    assert aperture_mask((0.75, 0.75), 4) == pytest.approx(1.0, abs=TOL, rel=0)

    # Distance from center is only 0.3677 (< radius 0.5), but the point is
    # outside the diamond whose edge satisfies |du| + |dv| == 0.5.
    assert aperture_mask((0.76, 0.76), 4) == pytest.approx(0.0, abs=TOL, rel=0)


def test_06_halo_is_opposite_the_source():
    """The halo center is the point reflection of the source through center."""
    assert halo_position((0.8, 0.2), (0.5, 0.5)) == pytest.approx(
        (0.2, 0.8), abs=TOL, rel=0
    )
    assert halo_position((0.5, 0.5), (0.5, 0.5)) == pytest.approx(
        (0.5, 0.5), abs=TOL, rel=0
    )


def test_07_falloff_is_smooth_and_reaches_zero():
    """Falloff follows (1 - d/r) ** power, not a linear ramp."""
    assert falloff(0.0, 2.0, 2.0) == pytest.approx(1.0, abs=TOL, rel=0)
    assert falloff(1.0, 2.0, 2.0) == pytest.approx(0.25, abs=TOL, rel=0)
    assert falloff(1.9, 2.0, 2.0) == pytest.approx(0.0025, abs=TOL, rel=0)
    assert falloff(2.0, 2.0, 2.0) == pytest.approx(0.0, abs=TOL, rel=0)
    assert falloff(2.5, 2.0, 2.0) == pytest.approx(0.0, abs=TOL, rel=0)


def test_08_out_of_range_intensity_is_rejected():
    """Over-bright sources must not be rendered above the valid range."""
    with pytest.raises(FlareError):
        flare_batch([{"uv": (0.5, 0.5), "intensity": 1.5}], BASE_CONFIG)

    assert "intensity out of range" in validate((0.5, 0.5), 4, 1.5)
    assert "intensity out of range" in validate((0.5, 0.5), 4, -0.1)


def test_09_batch_does_not_share_ghost_lists():
    """Each source owns its own ghost list; one source cannot pollute another."""
    sources = [
        {"uv": (0.2, 0.5), "intensity": 0.8},
        {"uv": (0.8, 0.5), "intensity": 0.6},
    ]
    result = flare_batch(sources, BASE_CONFIG)

    assert result[0]["ghosts"] is not result[1]["ghosts"]
    assert result[0]["ghosts"] == pytest.approx(
        [(0.74, 0.5), (0.58, 0.5), (0.42, 0.5), (0.26, 0.5)],
        abs=TOL,
        rel=0,
    )
    assert result[1]["ghosts"] == pytest.approx(
        [(0.26, 0.5), (0.42, 0.5), (0.58, 0.5), (0.74, 0.5)],
        abs=TOL,
        rel=0,
    )

    result[0]["ghosts"].append((0.5, 0.5))
    assert len(result[1]["ghosts"]) == 4


def test_10_nonpositive_count_is_a_validation_error():
    """Zero and negative counts are reported instead of dividing by zero."""
    assert validate((0.5, 0.5), 0, 0.5) == ["count must be a positive integer"]
    assert validate((0.5, 0.5), -2, 0.5) == ["count must be a positive integer"]
    assert validate((0.5, 0.5), 4, 0.5) == []

    assert validate((-0.1, 0.5), 0, 1.2) == [
        "uv out of range",
        "count must be a positive integer",
        "intensity out of range",
    ]


def test_11_center_source_keeps_ghosts_at_center():
    """A source at the optical center produces ghosts at that same center."""
    ghosts = ghost_positions((0.5, 0.5), 4, 0.9)

    assert ghosts == pytest.approx([(0.5, 0.5)] * 4, abs=TOL, rel=0)


def test_12_zero_intensity_produces_zero_weights():
    """A zero-intensity source keeps geometry but contributes zero light."""
    result = flare_batch([{"uv": (0.25, 0.75), "intensity": 0.0}], BASE_CONFIG)
    record = result[0]

    assert record["intensity"] == pytest.approx(0.0, abs=TOL, rel=0)
    assert record["ghost_weights"] == pytest.approx(
        [0.0] * len(record["ghosts"]), abs=TOL, rel=0
    )
    assert record["halo_weight"] == pytest.approx(0.0, abs=TOL, rel=0)
    assert record["chroma"] == pytest.approx((0.0, 0.0, 0.0), abs=TOL, rel=0)
    assert record["aperture"] == pytest.approx(0.0, abs=TOL, rel=0)
    assert record["falloff"] == pytest.approx(0.0, abs=TOL, rel=0)


def test_13_empty_source_list_returns_empty_mapping():
    """No sources means no per-source records."""
    assert flare_batch([], BASE_CONFIG) == {}


def test_14_zero_count_raises_flare_error():
    """A zero ghost count is a hard error, both directly and in a batch."""
    with pytest.raises(FlareError):
        ghost_positions((0.5, 0.5), 0, 0.5)

    with pytest.raises(FlareError):
        flare_batch(
            [{"uv": (0.5, 0.5), "intensity": 0.5}],
            dict(BASE_CONFIG, count=0),
        )


def test_15_successful_batch_preserves_source_order():
    """Successful records are keyed by index in the original source order."""
    sources = [
        {"uv": (0.2, 0.2), "intensity": 0.4},
        {"uv": (0.5, 0.5), "intensity": 0.7},
        {"uv": (0.8, 0.8), "intensity": 1.0},
    ]
    result = flare_batch(sources, BASE_CONFIG)

    assert isinstance(result, dict)
    assert list(result.keys()) == [0, 1, 2]
    for index, source in enumerate(sources):
        assert result[index]["uv"] == source["uv"]
        assert result[index]["intensity"] == pytest.approx(
            source["intensity"], abs=TOL, rel=0
        )
