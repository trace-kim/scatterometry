"""Detect diffraction spots in a scatterometry image and extract a 1D signal.

The script deliberately uses only NumPy and Matplotlib.  It is intended as a
transparent starting point: inspect the diagnostic figure, then tune the
threshold and area limits for a particular camera and exposure.

Edit ``scatterometry_config.json``, then run::

    python analyze_scatterometry.py
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np


# The script intentionally accepts no command-line arguments. Relative paths in
# the JSON file are resolved relative to the JSON file itself.
CONFIG_PATH = Path(__file__).with_name("scatterometry_config.json")


@dataclass(frozen=True)
class AnalysisConfig:
    """User-adjustable values loaded from the JSON configuration file."""

    image_path: Path | None
    use_demo_image: bool
    threshold_sigma: float
    min_area: int
    max_area: int | None
    background_mode: str
    background_polynomial_degree: int
    background_iterations: int
    background_clip_sigma: float
    signal_metric: str
    zero_order_x: float | None
    normalization: str
    csv_output: Path | None
    figure_output: Path | None
    show_figure: bool


def load_config(path: str | Path = CONFIG_PATH) -> AnalysisConfig:
    """Load settings and resolve input/output paths relative to the config."""
    path = Path(path).resolve()
    with path.open(encoding="utf-8") as stream:
        values = json.load(stream)

    def optional_path(key: str) -> Path | None:
        value = values.get(key)
        if value is None:
            return None
        candidate = Path(value)
        return candidate if candidate.is_absolute() else path.parent / candidate

    normalization = str(values.get("normalization", "sum"))
    if normalization not in {"sum", "max", "none"}:
        raise ValueError("config normalization must be 'sum', 'max', or 'none'")
    background_mode = str(values.get("background_mode", "polynomial"))
    if background_mode not in {"polynomial", "uniform"}:
        raise ValueError("config background_mode must be 'polynomial' or 'uniform'")
    signal_metric = str(values.get("signal_metric", "integral"))
    if signal_metric not in {"integral", "peak"}:
        raise ValueError("config signal_metric must be 'integral' or 'peak'")
    return AnalysisConfig(
        image_path=optional_path("image_path"),
        use_demo_image=bool(values.get("use_demo_image", False)),
        threshold_sigma=float(values.get("threshold_sigma", 6.0)),
        min_area=int(values.get("min_area", 12)),
        max_area=None if values.get("max_area") is None else int(values["max_area"]),
        background_mode=background_mode,
        background_polynomial_degree=int(values.get("background_polynomial_degree", 2)),
        background_iterations=int(values.get("background_iterations", 5)),
        background_clip_sigma=float(values.get("background_clip_sigma", 3.0)),
        signal_metric=signal_metric,
        zero_order_x=None if values.get("zero_order_x") is None else float(values["zero_order_x"]),
        normalization=normalization,
        csv_output=optional_path("csv_output"),
        figure_output=optional_path("figure_output"),
        show_figure=bool(values.get("show_figure", True)),
    )


@dataclass(frozen=True)
class Spot:
    """A detected diffraction spot and its background-corrected signal."""

    x: float
    y: float
    signal: float
    area: int
    peak: float
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1 (exclusive)


def load_grayscale(path: str | Path) -> np.ndarray:
    """Read a Matplotlib-supported image and return float grayscale data."""
    image = np.asarray(plt.imread(path), dtype=float)
    if image.ndim == 2:
        return image
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError(f"Expected a grayscale or RGB image, got {image.shape}")
    # Do not average an alpha channel into the intensity.
    return image[..., :3] @ np.array([0.2126, 0.7152, 0.0722])


def robust_background(image: np.ndarray) -> tuple[float, float]:
    """Return robust background level and noise scale (median and MAD)."""
    finite = image[np.isfinite(image)]
    if finite.size == 0:
        raise ValueError("Image contains no finite pixels")
    level = float(np.median(finite))
    sigma = float(1.4826 * np.median(np.abs(finite - level)))
    if sigma <= np.finfo(float).eps:
        sigma = float(np.std(finite))
    return level, max(sigma, np.finfo(float).eps)


def _polynomial_terms(x: np.ndarray, y: np.ndarray, degree: int) -> np.ndarray:
    """Build terms x**i * y**j for all i+j <= degree."""
    return np.column_stack(
        [(x**i) * (y**j) for total in range(degree + 1) for i in range(total + 1) for j in [total - i]]
    )


def estimate_background_map(
    image: np.ndarray,
    mode: str = "polynomial",
    polynomial_degree: int = 2,
    iterations: int = 5,
    clip_sigma: float = 3.0,
) -> tuple[np.ndarray, float]:
    """Estimate a uniform or smoothly varying background and residual noise.

    Polynomial fitting uses normalized image coordinates and iterative sigma
    clipping. Pixels above the smooth surface are excluded on each iteration,
    preventing bright diffraction blobs from pulling the fitted background up.
    This model is intended for broad illumination/camera-background shapes, not
    background features as narrow as the diffraction spots themselves.
    """
    image = np.asarray(image, dtype=float)
    if image.ndim != 2:
        raise ValueError("estimate_background_map expects a 2D image")
    level, initial_noise = robust_background(image)
    if mode == "uniform":
        return np.full_like(image, level), initial_noise
    if mode != "polynomial":
        raise ValueError("background mode must be 'polynomial' or 'uniform'")
    if polynomial_degree < 0 or polynomial_degree > 5:
        raise ValueError("background_polynomial_degree must be between 0 and 5")

    height, width = image.shape
    yy, xx = np.mgrid[-1.0:1.0:complex(height), -1.0:1.0:complex(width)]
    design = _polynomial_terms(xx.ravel(), yy.ravel(), polynomial_degree)
    values = image.ravel()
    valid = np.isfinite(values)
    model = np.full_like(values, level)
    noise = initial_noise
    for _ in range(max(1, iterations)):
        if valid.sum() < design.shape[1]:
            raise ValueError("Too few background pixels for polynomial fit")
        coefficients, *_ = np.linalg.lstsq(design[valid], values[valid], rcond=None)
        model = design @ coefficients
        residual = values - model
        residual_level, noise = robust_background(residual[valid])
        # Reject both extreme defects and bright spots, while allowing a small
        # residual offset caused by the current fit.
        valid = np.isfinite(values) & (np.abs(residual - residual_level) <= clip_sigma * noise)
    return model.reshape(image.shape), noise


def _components(mask: np.ndarray) -> list[np.ndarray]:
    """Find 8-connected components without requiring SciPy."""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[np.ndarray] = []
    for y0, x0 in np.argwhere(mask):
        if visited[y0, x0]:
            continue
        stack = [(int(y0), int(x0))]
        visited[y0, x0] = True
        pixels: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            for yy in range(max(0, y - 1), min(height, y + 2)):
                for xx in range(max(0, x - 1), min(width, x + 2)):
                    if mask[yy, xx] and not visited[yy, xx]:
                        visited[yy, xx] = True
                        stack.append((yy, xx))
        components.append(np.asarray(pixels, dtype=int))
    return components


def detect_spots(
    image: np.ndarray,
    threshold_sigma: float = 6.0,
    min_area: int = 12,
    max_area: int | None = None,
    background_mode: str = "polynomial",
    background_polynomial_degree: int = 2,
    background_iterations: int = 5,
    background_clip_sigma: float = 3.0,
    signal_metric: str = "integral",
) -> tuple[list[Spot], np.ndarray, np.ndarray]:
    """Detect bright components and integrate their excess above background.

    The threshold is ``median + threshold_sigma * MAD_sigma``.  Signal is the
    sum of positive, background-subtracted pixels over each thresholded blob.
    This is deliberately simple and works best with a reasonably flat camera
    background and separated diffraction spots.
    """
    image = np.asarray(image, dtype=float)
    if image.ndim != 2:
        raise ValueError("detect_spots expects a 2D grayscale image")
    if signal_metric not in {"integral", "peak"}:
        raise ValueError("signal_metric must be 'integral' or 'peak'")
    background, noise = estimate_background_map(
        image,
        mode=background_mode,
        polynomial_degree=background_polynomial_degree,
        iterations=background_iterations,
        clip_sigma=background_clip_sigma,
    )
    corrected = np.nan_to_num(image - background, nan=0.0)
    threshold = threshold_sigma * noise
    mask = corrected > threshold
    spots: list[Spot] = []
    for pixels in _components(mask):
        area = len(pixels)
        if area < min_area or (max_area is not None and area > max_area):
            continue
        ys, xs = pixels[:, 0], pixels[:, 1]
        weights = np.maximum(corrected[ys, xs], 0.0)
        integral = float(weights.sum())
        peak = float(np.max(corrected[ys, xs]))
        signal = integral if signal_metric == "integral" else peak
        if integral <= 0.0:
            continue
        spots.append(
            Spot(
                x=float(np.sum(xs * weights) / signal),
                y=float(np.sum(ys * weights) / signal),
                signal=signal,
                area=area,
                peak=peak,
                bbox=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
            )
        )
    return sorted(spots, key=lambda spot: spot.x), mask, background


def spots_to_signal(
    spots: list[Spot], zero_order_x: float | None = None, normalize: str = "sum"
) -> tuple[np.ndarray, np.ndarray]:
    """Assign integer orders along x and return normalized spot intensities."""
    if not spots:
        return np.empty(0, dtype=int), np.empty(0)
    values = np.asarray([spot.signal for spot in spots], dtype=float)
    if zero_order_x is None:
        zero_index = int(np.argmax(values))
    else:
        zero_index = int(np.argmin([abs(spot.x - zero_order_x) for spot in spots]))
    orders = np.arange(len(spots), dtype=int) - zero_index
    if normalize == "sum":
        values /= values.sum()
    elif normalize == "max":
        values /= values.max()
    elif normalize != "none":
        raise ValueError("normalize must be 'sum', 'max', or 'none'")
    return orders, values


def save_csv(path: str | Path, spots: list[Spot], orders: np.ndarray, signal: np.ndarray) -> None:
    """Write the extracted signal and spot metadata."""
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["order", "signal", "x_pixel", "y_pixel", "raw_integral", "area", "peak"])
        for spot, order, value in zip(spots, orders, signal):
            writer.writerow([order, value, spot.x, spot.y, spot.signal, spot.area, spot.peak])


def diagnostic_figure(
    image: np.ndarray,
    mask: np.ndarray,
    background: np.ndarray,
    spots: list[Spot],
    orders: np.ndarray,
    signal: np.ndarray,
) -> plt.Figure:
    """Show background processing, detections, projections, and final signal."""
    fig, axes = plt.subplots(3, 3, figsize=(17, 13), constrained_layout=True)
    axes[0, 0].imshow(image, cmap="gray", origin="upper")
    axes[0, 0].set_title("Input image")

    finite_min = float(np.nanmin(image))
    positive_image = np.maximum(image - finite_min, 0.0)
    positive_scale = max(float(np.nanmax(positive_image)), 1.0)
    log_image = np.log10(1.0 + positive_image / positive_scale)
    axes[0, 1].imshow(log_image, cmap="gray", origin="upper")
    axes[0, 1].set_title("Input image (log10 scale)")

    background_view = axes[0, 2].imshow(background, cmap="viridis", origin="upper")
    axes[0, 2].set_title("Estimated background map")
    fig.colorbar(background_view, ax=axes[0, 2], shrink=0.8)

    corrected_signed = image - background
    corrected_view = axes[1, 0].imshow(corrected_signed, cmap="gray", origin="upper")
    axes[1, 0].set_title("Background-subtracted image")
    fig.colorbar(corrected_view, ax=axes[1, 0], shrink=0.8)

    axes[1, 1].imshow(mask, cmap="gray", origin="upper")
    axes[1, 1].set_title("Detection threshold mask")

    axes[1, 2].imshow(corrected_signed, cmap="gray", origin="upper")
    axes[1, 2].contour(mask.astype(float), levels=[0.5], colors="cyan", linewidths=0.8)
    for spot, order in zip(spots, orders):
        x0, y0, x1, y1 = spot.bbox
        axes[1, 2].add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor="lime"))
        axes[1, 2].plot(spot.x, spot.y, "r+", ms=8)
        axes[1, 2].text(spot.x + 3, spot.y, f"m={order}", color="yellow", fontsize=9)
    axes[1, 2].set_title(f"Detections on corrected image ({len(spots)} spots)")

    corrected = np.maximum(image - background, 0.0)
    x_projection = corrected.sum(axis=0)
    axes[2, 0].plot(x_projection, color="black", lw=1)
    for spot, order in zip(spots, orders):
        axes[2, 0].axvline(spot.x, color="tab:red", alpha=0.45)
        axes[2, 0].text(spot.x, x_projection.max() * 0.93, str(order), ha="center", va="top")
    axes[2, 0].set(title="Background-corrected x projection", xlabel="x pixel", ylabel="summed intensity")

    y_projection = corrected.sum(axis=1)
    axes[2, 1].plot(y_projection, np.arange(image.shape[0]), color="black", lw=1)
    for spot, order in zip(spots, orders):
        axes[2, 1].axhline(spot.y, color="tab:red", alpha=0.35)
    axes[2, 1].invert_yaxis()
    axes[2, 1].set(
        title="Background-corrected y projection",
        xlabel="summed intensity",
        ylabel="y pixel",
    )

    markerline, stemlines, baseline = axes[2, 2].stem(orders, signal)
    plt.setp(markerline, markersize=6)
    plt.setp(stemlines, linewidth=2)
    plt.setp(baseline, color="0.5")
    axes[2, 2].set(title="Extracted diffraction signal", xlabel="assigned order m", ylabel="normalized intensity")
    axes[2, 2].grid(alpha=0.25)
    return fig


def synthetic_image(seed: int = 4) -> np.ndarray:
    """Make a small noisy image for testing and parameter demonstrations."""
    rng = np.random.default_rng(seed)
    height, width = 300, 700
    yy, xx = np.mgrid[:height, :width]
    image = 80.0 + 0.015 * xx + rng.normal(0.0, 2.0, (height, width))
    for x, y, amplitude, sigma in [
        (100, 152, 150, 8), (220, 149, 310, 10), (350, 151, 800, 12),
        (480, 153, 270, 10), (605, 150, 115, 8),
    ]:
        image += amplitude * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2))
    return image


def main() -> None:
    config = load_config()
    if config.use_demo_image:
        image = synthetic_image()
        base = CONFIG_PATH.parent / "scatterometry_demo"
    elif config.image_path is not None:
        image = load_grayscale(config.image_path)
        base = config.image_path.with_suffix("")
    else:
        raise ValueError("Set image_path or enable use_demo_image in the config file")

    spots, mask, background = detect_spots(
        image,
        threshold_sigma=config.threshold_sigma,
        min_area=config.min_area,
        max_area=config.max_area,
        background_mode=config.background_mode,
        background_polynomial_degree=config.background_polynomial_degree,
        background_iterations=config.background_iterations,
        background_clip_sigma=config.background_clip_sigma,
        signal_metric=config.signal_metric,
    )
    orders, signal = spots_to_signal(spots, config.zero_order_x, config.normalization)
    csv_path = config.csv_output or base.with_name(base.name + "_signal.csv")
    figure_path = config.figure_output or base.with_name(base.name + "_debug.png")
    save_csv(csv_path, spots, orders, signal)
    fig = diagnostic_figure(image, mask, background, spots, orders, signal)
    fig.savefig(figure_path, dpi=160)
    print(
        f"Detected {len(spots)} spots; background range="
        f"[{background.min():.6g}, {background.max():.6g}]"
    )
    print(f"Saved signal: {csv_path}")
    print(f"Saved diagnostics: {figure_path}")
    if config.show_figure:
        plt.show()
    else:
        plt.close(fig)


if __name__ == "__main__":
    main()
