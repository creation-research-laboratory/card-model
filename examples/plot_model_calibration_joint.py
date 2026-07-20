"""
Model calibration plot (joint solve): secular age vs. young-age age for two
flood-only calibration scenarios, solving for BOTH lambda_F and k_F.

Unlike plot_model_calibration.py (which fixes k_F and solves lambda_F on the
Flood pair only), here each scenario's two paired dates give two equations in
two unknowns, so both calibration points are honored exactly:

    forward_age(flood_ybp)   = 541 Ma
    forward_age(ice_age_ybp) = 12 ka

All young ages are in years before present (YBP).
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import fsolve

from plot_model_calibration import (FLOOD_SECULAR, ICE_AGE_SECULAR,
                                    build_model)

SCENARIOS = {
    'Scenario 1': {'flood_ybp': 5324, 'ice_age_ybp': 4200, 'color': '#e34948'},
    'Scenario 2': {'flood_ybp': 4374, 'ice_age_ybp': 3500, 'color': '#2a78d6'},
}


def solve_lambda_F_and_k_F(flood_ybp: float, ice_age_ybp: float):
    """Solve the 2x2 system for (lambda_F, k_F) in log10 space so both
    paired calibration dates are honored exactly."""
    def residuals(x):
        lambda_F, k_F = 10.0 ** x[0], 10.0 ** x[1]
        model = build_model(flood_ybp, k_F, lambda_F)
        return [
            np.log10(model.forward_age(flood_ybp) / FLOOD_SECULAR),
            np.log10(model.forward_age(ice_age_ybp) / ICE_AGE_SECULAR),
        ]

    # Initial guess from the fixed-k_F calibration (lambda_F ~ 1e6.8, k_F ~ 1e-2)
    x0 = np.array([6.8, -2.0])
    solution = fsolve(residuals, x0, xtol=1e-12)
    return 10.0 ** solution[0], 10.0 ** solution[1]


def main():
    fig, ax = plt.subplots(figsize=(9, 5.5), layout='tight')

    young_ages = np.linspace(1, 6000, 800)

    for name, sc in SCENARIOS.items():
        lambda_F, k_F = solve_lambda_F_and_k_F(sc['flood_ybp'],
                                               sc['ice_age_ybp'])
        model = build_model(sc['flood_ybp'], k_F, lambda_F)

        secular = np.array([model.forward_age(t) for t in young_ages])

        print(f"{name}: Flood {sc['flood_ybp']} YBP, "
              f"Ice Age end {sc['ice_age_ybp']} YBP")
        print(f"  solved lambda_F = {lambda_F:.4g} "
              f"(log10 = {np.log10(lambda_F):.4f})")
        print(f"  solved k_F      = {k_F:.4g} yr^-1 "
              f"(log10 = {np.log10(k_F):.4f})")
        print(f"  Flood check:   {model.forward_age(sc['flood_ybp']):.6g} yr "
              f"(target {FLOOD_SECULAR:.4g})")
        print(f"  Ice Age check: {model.forward_age(sc['ice_age_ybp']):.6g} yr "
              f"(target {ICE_AGE_SECULAR:.4g})")

        label = (f"{name}: Flood {sc['flood_ybp']} YBP, "
                 f"$k_F$ = {k_F:.4f}, "
                 f"$\\lambda_F$ = {lambda_F:.3g}")
        ax.semilogy(young_ages, secular, color=sc['color'], linewidth=2,
                    label=label)

        # Both calibration points are honored exactly in the joint solve
        ax.plot(sc['flood_ybp'], FLOOD_SECULAR, 'o', color=sc['color'],
                markersize=9, markeredgecolor='white', markeredgewidth=1.5,
                zorder=5)
        ax.plot(sc['ice_age_ybp'], ICE_AGE_SECULAR, 's', color=sc['color'],
                markersize=9, markeredgecolor='white', markeredgewidth=1.5,
                zorder=5)

    # 1:1 reference: constant background decay (secular age = young age)
    ax.semilogy(young_ages, young_ages, color='gray', linestyle='--',
                linewidth=1.5, label='Constant decay rate (1:1)')

    # Horizontal guides at the target secular ages of the calibration events
    for y_target, label in [(FLOOD_SECULAR, 'Flood (541 Ma)'),
                            (ICE_AGE_SECULAR, 'Ice Age end (12 ka)')]:
        ax.axhline(y_target, color='0.8', linestyle=':', linewidth=1, zorder=1)
        ax.text(120, y_target * 1.35, label, fontsize=9, color='0.35',
                ha='left', va='bottom')

    ax.set_xlabel('Young-age age (years before present)')
    ax.set_ylabel('Secular age (years)')
    ax.set_title('Model calibration (joint solve for $\\lambda_F$ and $k_F$)')
    ax.set_xlim(0, 6000)
    ax.set_ylim(1, 5e9)
    ax.grid(True, which='major', alpha=0.3)
    ax.legend(loc='lower right', fontsize=9)

    out_file = 'model_calibration_joint_plot.png'
    fig.savefig(out_file, dpi=300)
    print(f"\nSaved: {out_file}")


if __name__ == '__main__':
    main()
