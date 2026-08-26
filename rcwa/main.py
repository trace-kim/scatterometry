# """
# Example: 40-pair Mo/Si multilayer EUV mask simulation at 13.5nm wavelength.
# """
# import numpy as np

# from rcwa import (
#     Lattice,
#     IncidentWave,
#     ExternalRegion,
#     Layer,
#     RCWASettings,
#     RCWAProblem,
#     RCWASolver,
#     HomogeneousPattern,
#     nk_to_eps,
# )


# if __name__ == "__main__":
#     # --- Lattice: irrelevant for homogeneous stack, but required by the API ---
#     lat = Lattice(Lx=200e-9, Ly=200e-9)

#     # --- Incident: EUV mask is typically used near 6 degrees incidence ---
#     inc = IncidentWave(
#         wavelength=13.5e-9,
#         theta=np.deg2rad(6.0),
#         phi=0.0,
#         pTE=1.0,   # s-pol
#         pTM=0.0
#     )

#     # --- External regions ---
#     reg_ref = ExternalRegion(eps_r=1.0 + 0j, mu_r=1.0 + 0j)  # vacuum

#     # Substrate (very simplified): Si bulk.
#     # Using the same Si n,k at 13.5 nm as a first approximation.
#     n_Si, k_Si = 0.99900154, 0.0018265
#     eps_Si = nk_to_eps(n_Si, k_Si)
#     reg_trn = ExternalRegion(eps_r=eps_Si, mu_r=1.0 + 0j)

#     # --- Multilayer materials (CXRO values commonly used in EUV mask modeling) ---
#     n_Mo, k_Mo = 0.923791, 0.0064358
#     eps_Mo = nk_to_eps(n_Mo, k_Mo)

#     # Optional Ru cap (common EUV mask cap material; values also cited in same source)
#     n_Ru, k_Ru = 0.8864, 0.017066
#     eps_Ru = nk_to_eps(n_Ru, k_Ru)

#     # --- Typical thicknesses for a 6.9 nm period Mo/Si ML ---
#     t_Mo = 2.8e-9
#     t_Si = 4.1e-9
#     N_PAIRS = 40

#     # Optional cap thickness (pick a reasonable nominal value for a first test)
#     t_Ru_cap = 2.5e-9

#     layers = []

#     # If you want a Ru cap on top:
#     layers.append(Layer(thickness=t_Ru_cap, pattern=HomogeneousPattern(eps_Ru), mu_r=1.0 + 0j))

#     # Build 40 Mo/Si pairs.
#     # Convention here: top-most (closest to vacuum) after Ru is Si then Mo repeating downward.
#     # If your reference stack uses the opposite order, just swap the two appends below.
#     for _ in range(N_PAIRS):
#         layers.append(Layer(thickness=t_Si, pattern=HomogeneousPattern(eps_Si), mu_r=1.0 + 0j))
#         layers.append(Layer(thickness=t_Mo, pattern=HomogeneousPattern(eps_Mo), mu_r=1.0 + 0j))

#     # --- Settings: homogeneous stack needs only the 0th order ---
#     settings = RCWASettings(
#         Nx=11, Ny=0,
#         grid_Nx=64, grid_Ny=32,   # grid irrelevant for homogeneous, but keep valid
#         debug=True
#     )

#     prob = RCWAProblem(
#         lattice=lat,
#         inc=inc,
#         region_ref=reg_ref,
#         region_trn=reg_trn,
#         layers=layers,
#         settings=settings
#     )

#     res = RCWASolver().solve(prob)
#     print("R_total:", res["power"]["R_total"])
#     print("T_total:", res["power"]["T_total"])
#     print("R+T:", res["power"]["RT_total"])
#     print("A (1-R-T):", res["power"]["A_total"])




"""
Example: 40-pair Mo/Si multilayer EUV mask simulation at 13.5nm wavelength,
with a patterned absorber (1D line/space) on top.
"""
import numpy as np

from rcwa import (
    Lattice,
    IncidentWave,
    ExternalRegion,
    Layer,
    RCWASettings,
    RCWAProblem,
    RCWASolver,
    HomogeneousPattern,
    BinaryLinespace1D,
    nk_to_eps,
)

import matplotlib.pyplot as plt

def perR_to_angle_efficiency(perR: dict, wavelength: float, pitch: float, theta_inc_rad: float, n_ref: float = 1.0):
    """
    Convert per-order reflectance dict {(m,n): R_mn} to (diffraction_angle_deg, R_mn) for 1D in-plane (n=0).

    Uses the sign convention consistent with your RCWA wavevector expansion:
    Kx(m) = n_ref*sin(theta_inc) - m*(wavelength/pitch)

    Propagating condition: |Kx| <= n_ref.
    Diffraction angle: theta_m = arcsin(Kx/n_ref) [deg], measured from surface normal.
    """
    sin_t = np.sin(theta_inc_rad)
    angles = []
    effs = []
    orders = []

    for (m, n), Rmn in perR.items():
        if n != 0:
            continue

        Kx = n_ref * sin_t - m * (wavelength / pitch)

        # Only plot propagating orders
        if np.abs(Kx) <= n_ref * (1.0 + 1e-12):
            arg = np.clip(np.real(Kx / n_ref), -1.0, 1.0)
            theta_m = np.degrees(np.arcsin(arg))
            angles.append(theta_m)
            effs.append(float(np.real(Rmn)))
            orders.append(int(m))

    angles = np.array(angles, dtype=float)
    effs = np.array(effs, dtype=float)
    orders = np.array(orders, dtype=int)

    idx = np.argsort(angles)
    return angles[idx], effs[idx], orders[idx]


def interpolate_angle_efficiency(
    angles_deg: np.ndarray,
    eff: np.ndarray,
    angle_min: float = -6.0,
    angle_max: float = 90.0,
    angle_step: float = 0.1,
    method: str = "linear",
    fill_value: float = 0.0,
):
    """
    Interpolate diffraction efficiency in angle space onto a uniform grid.

    Parameters
    ----------
    angles_deg : (N,) array
        Diffraction angles in degrees (can be unsorted).
    eff : (N,) array
        Corresponding efficiencies (same length as angles_deg).
    angle_min, angle_max : float
        Output angle range [deg]. Inclusive of endpoints (within floating tolerance).
    angle_step : float
        Output spacing [deg].
    method : {"linear", "nearest"}
        Interpolation method. (Pure NumPy implementation.)
    fill_value : float
        Value used outside the convex hull of input angles (extrapolation is not performed).

    Returns
    -------
    grid_angles : (M,) array
        Uniform angle grid in degrees.
    grid_eff : (M,) array
        Interpolated efficiencies on the grid.
    """
    angles_deg = np.asarray(angles_deg, dtype=float)
    eff = np.asarray(eff, dtype=float)
    if angles_deg.ndim != 1 or eff.ndim != 1 or angles_deg.size != eff.size:
        raise ValueError("angles_deg and eff must be 1D arrays of the same length.")

    # Sort by angle
    idx = np.argsort(angles_deg)
    x = angles_deg[idx]
    y = eff[idx]

    # Remove duplicates (keep last by default)
    # If you prefer averaging duplicates, replace this block accordingly.
    uniq_x, uniq_idx = np.unique(x, return_index=True)
    x = uniq_x
    y = y[uniq_idx]

    # Build uniform grid
    n_steps = int(np.floor((angle_max - angle_min) / angle_step + 1e-12)) + 1
    grid_angles = angle_min + angle_step * np.arange(n_steps, dtype=float)

    # Interpolate
    if method == "linear":
        grid_eff = np.interp(grid_angles, x, y, left=fill_value, right=fill_value)
    elif method == "nearest":
        # Nearest-neighbor interpolation (no SciPy)
        # For each grid point, pick closest x.
        # Efficiently done by locating insertion indices.
        inds = np.searchsorted(x, grid_angles, side="left")
        inds = np.clip(inds, 0, x.size - 1)

        # Compare neighbor on the left if it exists
        left = np.clip(inds - 1, 0, x.size - 1)
        choose_left = (np.abs(grid_angles - x[left]) <= np.abs(grid_angles - x[inds]))
        nn = np.where(choose_left, left, inds)

        grid_eff = y[nn]

        # Apply fill outside range
        grid_eff = np.where((grid_angles < x[0]) | (grid_angles > x[-1]), fill_value, grid_eff)
    else:
        raise ValueError("method must be 'linear' or 'nearest'.")

    return grid_angles, grid_eff

def detector_measurement_rect(
    theta_lines_deg: np.ndarray,   # diffracted angles θ_m (deg)
    R_lines: np.ndarray,           # corresponding efficiencies R_m
    theta_scan_deg: np.ndarray,    # scan angles where detector is pointed (deg)
    fwhm_deg: float = 0.5,         # full acceptance width (deg)
    normalize: bool = False,       # if True, divide by window width (gives average density)
) -> np.ndarray:
    """
    Measured signal at each scan angle = sum of diffraction efficiencies within acceptance window.
    """
    theta_lines_deg = np.asarray(theta_lines_deg, float)
    R_lines = np.asarray(R_lines, float)
    theta_scan_deg = np.asarray(theta_scan_deg, float)

    half = 0.5 * fwhm_deg
    # broadcasting: (Nscan, Nlines)
    dtheta = theta_lines_deg[None, :] - theta_scan_deg[:, None]
    mask = np.abs(dtheta) <= half
    meas = np.sum(R_lines[None, :] * mask, axis=1)

    if normalize:
        meas = meas / max(fwhm_deg, 1e-30)

    return meas

if __name__ == "__main__":
    # --- Lattice: must match absorber pitch in x for a 1D periodic pattern ---
    pitch = 110e-9
    lat = Lattice(Lx=pitch, Ly=200e-9)  # Ly arbitrary for 1D (Ny=0)



    # --- External regions ---
    reg_ref = ExternalRegion(eps_r=1.0 + 0j, mu_r=1.0 + 0j)  # vacuum

    # Substrate (very simplified): Si bulk (same n,k used for Si film)
    n_Si, k_Si = 0.99900154, 0.0018265
    eps_Si = nk_to_eps(n_Si, k_Si)
    reg_trn = ExternalRegion(eps_r=eps_Si, mu_r=1.0 + 0j)

    # --- Multilayer materials (example CXRO-based values at 13.5 nm) ---
    n_Mo, k_Mo = 0.923791, 0.0064358
    eps_Mo = nk_to_eps(n_Mo, k_Mo)

    # Optional Ru cap
    n_Ru, k_Ru = 0.8864, 0.017066
    eps_Ru = nk_to_eps(n_Ru, k_Ru)

    # --- Typical Mo/Si period ---
    t_Mo = 2.71e-9
    t_Si = 4.18e-9
    N_PAIRS = 40

    # Ru cap thickness
    t_Ru_cap = 2.5e-9

    # --------------------------
    # NEW: Patterned absorber layer (on top of Ru cap)
    # --------------------------
    absorber_thickness = 60e-9  # adjust to your mask spec

    # Placeholder absorber optical constants at 13.5 nm:
    # Replace with your TaBN/TaBO/TaN choice.
    # IMPORTANT: your convention requires loss -> negative imaginary in epsilon,
    # and nk_to_eps() should implement n_complex = n - i k.
    n_abs, k_abs = 0.92599, 0.04363
    eps_abs = nk_to_eps(n_abs, k_abs)

    # Space region is vacuum (or can be an overcoat, etc.)
    eps_space = 1.0 + 0j

    CD = 60e-9
    absorber_pattern = BinaryLinespace1D(
        pitch=pitch,
        CD=CD,
        eps_line=eps_abs,
        eps_space=eps_space,
        center=True
    )

    layers = []

    # Add absorber FIRST (top-most, closest to vacuum)
    layers.append(Layer(thickness=absorber_thickness, pattern=absorber_pattern, mu_r=1.0 + 0j))

    # Then Ru cap (homogeneous)
    layers.append(Layer(thickness=t_Ru_cap, pattern=HomogeneousPattern(eps_Ru), mu_r=1.0 + 0j))

    # Then 40 Mo/Si pairs
    for _ in range(N_PAIRS):
        layers.append(Layer(thickness=t_Si, pattern=HomogeneousPattern(eps_Si), mu_r=1.0 + 0j))
        layers.append(Layer(thickness=t_Mo, pattern=HomogeneousPattern(eps_Mo), mu_r=1.0 + 0j))

    # --- Settings ---
    # With a patterned layer, grid is NOT irrelevant.
    # Must satisfy grid_Nx >= 4*Nx + 1 (minimum), and in practice much larger for binary patterns.
    settings = RCWASettings(
        Nx=11, Ny=0,
        grid_Nx=512, grid_Ny=1,
        debug=True
    )




    SOURCE_DIVERGENCE = 0.5 # degrees
    TARGET_ANGLE_INCIDENCE = 6. # degrees
    SUPERGAUSSIAN_ORDER = 8

    inc_angles = np.arange(11)*0.1 + 5.5
    angles = []
    Rs = []
    for inc_ang in inc_angles:

        # --- Incident: EUV mask is typically used near 6 degrees incidence ---
        inc = IncidentWave(
            wavelength=13.5e-9,
            theta=np.deg2rad(inc_ang),
            phi=0.0,
            pTE=1.0,   # s-pol
            pTM=1.0
        )

        prob = RCWAProblem(
            lattice=lat,
            inc=inc,
            region_ref=reg_ref,
            region_trn=reg_trn,
            layers=layers,
            settings=settings
        )

        res = RCWASolver().solve(prob)
        print("R_total:", res["power"]["R_total"])
        print("T_total:", res["power"]["T_total"])
        print("R+T:", res["power"]["RT_total"])
        print("A (1-R-T):", res["power"]["A_total"])

        # Optional: print a few diffraction orders (m,0) for quick sanity check
        perR = res["efficiencies"]["per_order_R"]
        perT = res["efficiencies"]["per_order_T"]
        for m in range(-3, 4):
            print(f"Order (m={m}, n=0): R={perR.get((m,0), 0.0):.6e}, T={perT.get((m,0), 0.0):.6e}")


        wavelength = 13.5e-9
        pitch = 110e-9
        inc_theta = np.deg2rad(inc_ang)
        n_ref = 1.0  # vacuum reflection region

        angles_deg, Rvals, orders = perR_to_angle_efficiency(perR, wavelength, pitch, inc_theta, n_ref)
        
        # Apply super-Gaussian beam profile
        input_power = np.exp(-abs((inc_ang - TARGET_ANGLE_INCIDENCE)/SOURCE_DIVERGENCE)**SUPERGAUSSIAN_ORDER)
        Rvals *= input_power

        angles += angles_deg.tolist()
        Rs += Rvals.tolist()


    theta_scan = np.linspace(-6.0, 90.0, int(96 //0.2))
    meas_rect = detector_measurement_rect(angles, Rs, theta_scan, fwhm_deg=0.5) / 5

    plt.figure()
    plt.scatter(angles, Rs)
    plt.plot(theta_scan, meas_rect, marker='x', label="Rect acceptance (0.5°)")
    plt.xlabel("Diffraction angle (deg)")
    plt.ylabel("Reflected diffraction efficiency (power)")
    plt.title("Diffraction efficiency vs diffraction angle (reflection, n=0)")
    plt.grid(True)

    # annotate each point by diffraction order m
    for a, r, m in zip(angles_deg, Rvals, orders):
        plt.annotate(f"m={m}", (a, r), textcoords="offset points", xytext=(0, 6), ha="center")

    plt.show()

    input_power = np.exp(-abs((inc_angles - TARGET_ANGLE_INCIDENCE)/SOURCE_DIVERGENCE)**SUPERGAUSSIAN_ORDER)

    plt.figure()
    plt.plot(inc_angles, input_power)
    plt.xlabel("Incidence angle (deg)")
    plt.ylabel("Input power")
    plt.title("Input power vs incidence angle")
    plt.grid(True)
    plt.show()