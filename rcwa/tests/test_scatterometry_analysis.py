"""Tests for the example scatterometry image pipeline."""

import json

import numpy as np

from analyze_scatterometry import (
    _log10_image,
    _peak_prominence,
    _subtract_background,
    detect_spots,
    estimate_background_map,
    load_config,
    Spot,
    spots_to_signal,
    strip_projections,
    synthetic_image,
)


def test_log_image_replaces_nonpositive_values_with_minimum_positive():
    image = np.array([[-5.0, 0.0, 0.01, 1.0, 100.0]])

    logged = _log10_image(image)

    assert np.all(np.isfinite(logged))
    assert np.allclose(logged, [[-2.0, -2.0, -2.0, 0.0, 2.0]])


def test_peak_prominence_stops_at_higher_peak_and_uses_higher_base():
    peak = _peak_prominence(np.array([0.0, 1.0, 0.0, 3.0, 1.0, 2.0, 0.0]), 5)

    assert peak.left_base == 4
    assert peak.right_base == 6
    assert peak.contour_height == 1.0
    assert peak.prominence == 1.0


def test_background_subtraction_clips_negative_residuals():
    corrected = _subtract_background(
        np.array([[2.0, 5.0, 9.0]]),
        np.array([[3.0, 5.0, 7.0]]),
    )

    assert np.array_equal(corrected, [[0.0, 0.0, 2.0]])


def test_synthetic_pattern_yields_five_ordered_spots():
    spots, mask, background = detect_spots(synthetic_image(), threshold_sigma=6.0)
    orders, signal = spots_to_signal(spots)

    assert len(spots) == 5
    assert np.array_equal(orders, [-2, -1, 0, 1, 2])
    assert np.all(np.diff([spot.x for spot in spots]) > 0)
    assert np.isclose(signal.sum(), 1.0)
    assert np.argmax(signal) == 2
    assert mask.dtype == bool
    assert background.shape == synthetic_image().shape
    assert 75.0 < background.mean() < 95.0


def test_polynomial_background_recovers_curved_surface_and_peak_signal():
    yy, xx = np.mgrid[:120, :180]
    expected = 20.0 + 0.03 * xx + 0.0008 * (xx - 90) ** 2 + 0.002 * (yy - 60) ** 2
    image = expected + 200.0 * np.exp(-((xx - 90) ** 2 + (yy - 60) ** 2) / (2 * 5.0**2))

    background, _ = estimate_background_map(image, polynomial_degree=2)
    spots, _, _ = detect_spots(image, threshold_sigma=4.0, min_area=10, signal_metric="peak")

    assert np.mean(np.abs(background - expected)) < 0.1
    assert len(spots) == 1
    assert np.isclose(spots[0].signal, 200.0, rtol=0.02)


def test_log_domain_fit_recovers_multiplicative_background():
    yy, xx = np.mgrid[:100, :160]
    log_background = 1.5 + 0.002 * xx + 0.00001 * (xx - 80) ** 2 + 0.00002 * (yy - 50) ** 2
    expected = 10.0**log_background
    image = expected + 300.0 * np.exp(-((xx - 80) ** 2 + (yy - 50) ** 2) / (2 * 4.0**2))

    background, _ = estimate_background_map(
        image,
        fit_domain="log10",
        polynomial_degree=2,
        iterations=6,
    )

    assert np.mean(np.abs(background - expected) / expected) < 0.01


def test_background_fit_supports_degree_above_five():
    yy, xx = np.mgrid[-1.0:1.0:50j, -1.0:1.0:70j]
    expected = 40.0 + 3.0 * xx**6 + 2.0 * yy**4

    background, _ = estimate_background_map(
        expected,
        polynomial_degree=6,
        iterations=2,
    )

    assert np.allclose(background, expected, atol=1e-8)


def test_strip_projections_exclude_pixels_outside_blob_strips():
    background = np.full((8, 10), 10.0)
    image = background.copy()
    image[3:5, 4:6] += 7.0
    image[0, :] += 1000.0  # Unrelated signal outside the horizontal strip.
    spot = Spot(x=4.5, y=3.5, signal=28.0, area=4, peak=7.0, bbox=(4, 3, 6, 5))

    raw_x, corrected_x, raw_y, corrected_y, y_mask, x_mask = strip_projections(
        image, background, [spot], padding=0
    )

    assert np.array_equal(y_mask, [False, False, False, True, True, False, False, False])
    assert np.array_equal(x_mask, [False, False, False, False, True, True, False, False, False, False])
    assert np.allclose(corrected_x[4:6], 14.0)
    assert corrected_x.sum() == 28.0
    # The vertical strip includes the unrelated top-row signal by design, but
    # excludes noise in all columns outside the detected blob's x strip.
    assert corrected_y[0] == 2000.0
    assert np.allclose(corrected_y[3:5], 14.0)


def test_config_paths_are_relative_to_config_file(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps({"image_path": "images/data.png", "use_demo_image": False}),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.image_path == tmp_path / "images/data.png"
    assert config.threshold_sigma == 6.0
    assert config.normalization == "sum"
