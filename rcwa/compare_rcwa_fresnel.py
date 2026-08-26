"""
Compare RCWA and Fresnel/TMM results for a homogeneous multilayer stack.

For homogeneous layers (no grating pattern), both methods should give identical results.
This script validates the RCWA implementation against the analytical Fresnel solution.
"""
import numpy as np

from rcwa import (
    # RCWA imports
    Lattice,
    IncidentWave,
    ExternalRegion,
    Layer,
    RCWASettings,
    RCWAProblem,
    RCWASolver,
    HomogeneousPattern,
    nk_to_eps,
    # Fresnel imports
    FresnelLayer,
    FresnelProblem,
    FresnelSolver,
    nk_to_n,
)


def compare_single_interface():
    """Compare for a single interface (no layers) - simplest case."""
    print("=" * 60)
    print("Test 0: Single interface air-glass (no absorption)")
    print("=" * 60)

    wavelength = 500e-9  # visible light
    theta = np.deg2rad(30.0)  # 30 degree incidence

    n_inc = 1.0  # air
    n_sub = 1.5  # glass (real, no absorption)

    # Analytical Fresnel for single interface
    cos_inc = np.cos(theta)
    sin_inc = np.sin(theta)
    cos_sub = np.sqrt(1 - (n_inc/n_sub * sin_inc)**2)

    # s-polarization
    r_s = (n_inc * cos_inc - n_sub * cos_sub) / (n_inc * cos_inc + n_sub * cos_sub)
    R_analytical = np.abs(r_s)**2

    # Fresnel solver (no layers)
    fresnel_prob = FresnelProblem(
        wavelength=wavelength,
        theta=theta,
        n_inc=n_inc,
        n_sub=n_sub,
        layers=[],  # No layers
        polarization='s',
    )
    fresnel_result = FresnelSolver().solve(fresnel_prob)

    print(f"\nAnalytical R_s = {R_analytical:.6f}")
    print(f"Fresnel    R_s = {fresnel_result['R']:.6f}")
    print(f"Difference: ΔR = {abs(R_analytical - fresnel_result['R']):.2e}")


def compare_normal_incidence():
    """Compare at normal incidence (theta=0) - no angle complications."""
    print("\n" + "=" * 60)
    print("Test 1: Normal incidence, 40-pair Mo/Si multilayer")
    print("=" * 60)

    wavelength = 13.5e-9
    theta = 0.0  # Normal incidence

    n_Si, k_Si = 0.99900154, 0.0018265
    n_Mo, k_Mo = 0.923791, 0.0064358
    n_Ru, k_Ru = 0.8864, 0.017066

    t_Mo = 2.8e-9
    t_Si = 4.1e-9
    t_Ru = 2.5e-9
    N_PAIRS = 40

    # Fresnel
    fresnel_layers = []
    fresnel_layers.append(FresnelLayer(thickness=t_Ru, n=nk_to_n(n_Ru, k_Ru)))
    for _ in range(N_PAIRS):
        fresnel_layers.append(FresnelLayer(thickness=t_Si, n=nk_to_n(n_Si, k_Si)))
        fresnel_layers.append(FresnelLayer(thickness=t_Mo, n=nk_to_n(n_Mo, k_Mo)))

    fresnel_prob = FresnelProblem(
        wavelength=wavelength,
        theta=theta,
        n_inc=1.0,
        n_sub=nk_to_n(n_Si, k_Si),
        layers=fresnel_layers,
        polarization='s',
    )
    fresnel_result = FresnelSolver().solve(fresnel_prob)

    # RCWA
    lat = Lattice(Lx=200e-9, Ly=200e-9)
    inc = IncidentWave(wavelength=wavelength, theta=theta, phi=0.0, pTE=1.0, pTM=0.0)
    reg_ref = ExternalRegion(eps_r=1.0, mu_r=1.0)
    reg_trn = ExternalRegion(eps_r=nk_to_eps(n_Si, k_Si), mu_r=1.0)

    rcwa_layers = []
    rcwa_layers.append(Layer(thickness=t_Ru, pattern=HomogeneousPattern(nk_to_eps(n_Ru, k_Ru)), mu_r=1.0))
    for _ in range(N_PAIRS):
        rcwa_layers.append(Layer(thickness=t_Si, pattern=HomogeneousPattern(nk_to_eps(n_Si, k_Si)), mu_r=1.0))
        rcwa_layers.append(Layer(thickness=t_Mo, pattern=HomogeneousPattern(nk_to_eps(n_Mo, k_Mo)), mu_r=1.0))

    settings = RCWASettings(Nx=0, Ny=0, grid_Nx=64, grid_Ny=1, debug=False)
    rcwa_prob = RCWAProblem(lattice=lat, inc=inc, region_ref=reg_ref, region_trn=reg_trn,
                            layers=rcwa_layers, settings=settings)
    rcwa_result = RCWASolver().solve(rcwa_prob)

    print(f"\n{'Method':<12} {'R':>12} {'T':>12} {'A':>12} {'R+T+A':>12}")
    print("-" * 60)
    print(f"{'Fresnel':<12} {fresnel_result['R']:>12.6f} {fresnel_result['T']:>12.6f} "
          f"{fresnel_result['A']:>12.6f} {fresnel_result['R']+fresnel_result['T']+fresnel_result['A']:>12.6f}")
    print(f"{'RCWA':<12} {rcwa_result['power']['R_total']:>12.6f} {rcwa_result['power']['T_total']:>12.6f} "
          f"{rcwa_result['power']['A_total']:>12.6f} {rcwa_result['power']['RT_total']+rcwa_result['power']['A_total']:>12.6f}")

    diff_R = abs(fresnel_result['R'] - rcwa_result['power']['R_total'])
    diff_T = abs(fresnel_result['T'] - rcwa_result['power']['T_total'])
    print(f"\nDifference: ΔR = {diff_R:.2e}, ΔT = {diff_T:.2e}")

    if diff_R < 1e-4 and diff_T < 1e-4:
        print("✓ Results match within tolerance!")
    else:
        print("✗ Results differ - investigating...")


def compare_oblique_incidence():
    """Compare at oblique incidence (theta=6 deg) - the typical EUV mask case."""
    print("\n" + "=" * 60)
    print("Test 2: Oblique incidence (6 deg), 40-pair Mo/Si multilayer")
    print("=" * 60)

    wavelength = 13.5e-9
    theta = np.deg2rad(6.0)

    n_Si, k_Si = 0.99900154, 0.0018265
    n_Mo, k_Mo = 0.923791, 0.0064358
    n_Ru, k_Ru = 0.8864, 0.017066

    t_Mo = 2.8e-9
    t_Si = 4.1e-9
    t_Ru = 2.5e-9
    N_PAIRS = 40

    # Fresnel
    fresnel_layers = []
    fresnel_layers.append(FresnelLayer(thickness=t_Ru, n=nk_to_n(n_Ru, k_Ru)))
    for _ in range(N_PAIRS):
        fresnel_layers.append(FresnelLayer(thickness=t_Si, n=nk_to_n(n_Si, k_Si)))
        fresnel_layers.append(FresnelLayer(thickness=t_Mo, n=nk_to_n(n_Mo, k_Mo)))

    fresnel_prob = FresnelProblem(
        wavelength=wavelength,
        theta=theta,
        n_inc=1.0,
        n_sub=nk_to_n(n_Si, k_Si),
        layers=fresnel_layers,
        polarization='s',
    )
    fresnel_result = FresnelSolver().solve(fresnel_prob)

    # RCWA
    lat = Lattice(Lx=200e-9, Ly=200e-9)
    inc = IncidentWave(wavelength=wavelength, theta=theta, phi=0.0, pTE=1.0, pTM=0.0)
    reg_ref = ExternalRegion(eps_r=1.0, mu_r=1.0)
    reg_trn = ExternalRegion(eps_r=nk_to_eps(n_Si, k_Si), mu_r=1.0)

    rcwa_layers = []
    rcwa_layers.append(Layer(thickness=t_Ru, pattern=HomogeneousPattern(nk_to_eps(n_Ru, k_Ru)), mu_r=1.0))
    for _ in range(N_PAIRS):
        rcwa_layers.append(Layer(thickness=t_Si, pattern=HomogeneousPattern(nk_to_eps(n_Si, k_Si)), mu_r=1.0))
        rcwa_layers.append(Layer(thickness=t_Mo, pattern=HomogeneousPattern(nk_to_eps(n_Mo, k_Mo)), mu_r=1.0))

    settings = RCWASettings(Nx=0, Ny=0, grid_Nx=64, grid_Ny=1, debug=False)
    rcwa_prob = RCWAProblem(lattice=lat, inc=inc, region_ref=reg_ref, region_trn=reg_trn,
                            layers=rcwa_layers, settings=settings)
    rcwa_result = RCWASolver().solve(rcwa_prob)

    print(f"\n{'Method':<12} {'R':>12} {'T':>12} {'A':>12} {'R+T+A':>12}")
    print("-" * 60)
    print(f"{'Fresnel':<12} {fresnel_result['R']:>12.6f} {fresnel_result['T']:>12.6f} "
          f"{fresnel_result['A']:>12.6f} {fresnel_result['R']+fresnel_result['T']+fresnel_result['A']:>12.6f}")
    print(f"{'RCWA':<12} {rcwa_result['power']['R_total']:>12.6f} {rcwa_result['power']['T_total']:>12.6f} "
          f"{rcwa_result['power']['A_total']:>12.6f} {rcwa_result['power']['RT_total']+rcwa_result['power']['A_total']:>12.6f}")

    diff_R = abs(fresnel_result['R'] - rcwa_result['power']['R_total'])
    diff_T = abs(fresnel_result['T'] - rcwa_result['power']['T_total'])
    print(f"\nDifference: ΔR = {diff_R:.2e}, ΔT = {diff_T:.2e}")

    if diff_R < 1e-3 and diff_T < 1e-3:
        print("✓ Results match within tolerance!")


def compare_visible_glass():
    """Compare for visible light on glass - simpler case without EUV complexities."""
    print("\n" + "=" * 60)
    print("Test 3: Visible light, thin film on glass (no absorption)")
    print("=" * 60)

    wavelength = 550e-9  # green light
    theta = np.deg2rad(0.0)  # normal incidence

    n_inc = 1.0  # air
    n_film = 1.38  # MgF2 antireflection coating
    n_sub = 1.52  # glass

    thickness = wavelength / (4 * n_film)  # quarter-wave thickness

    # Fresnel
    fresnel_prob = FresnelProblem(
        wavelength=wavelength,
        theta=theta,
        n_inc=n_inc,
        n_sub=n_sub,
        layers=[FresnelLayer(thickness=thickness, n=n_film)],
        polarization='s',
    )
    fresnel_result = FresnelSolver().solve(fresnel_prob)

    # RCWA
    lat = Lattice(Lx=1e-6, Ly=1e-6)
    inc = IncidentWave(wavelength=wavelength, theta=theta, phi=0.0, pTE=1.0, pTM=0.0)
    reg_ref = ExternalRegion(eps_r=n_inc**2, mu_r=1.0)
    reg_trn = ExternalRegion(eps_r=n_sub**2, mu_r=1.0)
    layers = [Layer(thickness=thickness, pattern=HomogeneousPattern(n_film**2), mu_r=1.0)]
    settings = RCWASettings(Nx=0, Ny=0, grid_Nx=64, grid_Ny=1, debug=False)
    rcwa_prob = RCWAProblem(lattice=lat, inc=inc, region_ref=reg_ref, region_trn=reg_trn,
                            layers=layers, settings=settings)
    rcwa_result = RCWASolver().solve(rcwa_prob)

    print(f"\n{'Method':<12} {'R':>12} {'T':>12} {'R+T':>12}")
    print("-" * 48)
    print(f"{'Fresnel':<12} {fresnel_result['R']:>12.6f} {fresnel_result['T']:>12.6f} "
          f"{fresnel_result['R']+fresnel_result['T']:>12.6f}")
    print(f"{'RCWA':<12} {rcwa_result['power']['R_total']:>12.6f} {rcwa_result['power']['T_total']:>12.6f} "
          f"{rcwa_result['power']['RT_total']:>12.6f}")

    diff_R = abs(fresnel_result['R'] - rcwa_result['power']['R_total'])
    diff_T = abs(fresnel_result['T'] - rcwa_result['power']['T_total'])
    print(f"\nDifference: ΔR = {diff_R:.2e}, ΔT = {diff_T:.2e}")

    # Expected R for quarter-wave AR coating: R ≈ ((n_inc - n_film²/n_sub)/(n_inc + n_film²/n_sub))²
    n_eff = n_film**2 / n_sub
    R_expected = ((n_inc - n_eff) / (n_inc + n_eff))**2
    print(f"\nExpected R for quarter-wave AR coating: {R_expected:.6f}")


if __name__ == "__main__":
    import sys
    import io

    print("Comparing RCWA vs Fresnel/TMM for homogeneous multilayer stacks")
    print("For homogeneous layers, both methods should give identical results.\n")

    # Test 0: Single interface (simplest case)
    compare_single_interface()

    # Test 1: Normal incidence multilayer (no angle complications)
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()  # Capture RCWA debug output
    sys.stdout = old_stdout
    compare_normal_incidence()

    # Test 2: Oblique incidence (EUV mask case)
    sys.stdout = io.StringIO()
    sys.stdout = old_stdout
    compare_oblique_incidence()

    # Test 3: Visible light case (simpler physics)
    sys.stdout = io.StringIO()
    sys.stdout = old_stdout
    compare_visible_glass()

    print("\n" + "=" * 60)
    print("Comparison complete!")
    print("=" * 60)
