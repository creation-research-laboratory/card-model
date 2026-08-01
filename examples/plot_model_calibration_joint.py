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

from card import solve_flood_only

# The same two secular targets plot_model_calibration.py uses.  They are
# repeated rather than imported from it: a sibling import only resolves when
# the script is run from inside examples/, and two float literals are a smaller
# hazard than a script that fails depending on the working directory.
FLOOD_SECULAR = 541e6    # Precambrian-Cambrian boundary
ICE_AGE_SECULAR = 12e3   # End of the Ice Age

SCENARIOS = {
    'Scenario 1': {'flood_ybp': 5324, 'ice_age_ybp': 4200, 'color': '#e34948'},
    'Scenario 2': {'flood_ybp': 4374, 'ice_age_ybp': 3500, 'color': '#2a78d6'},
}


def calibrate(flood_ybp: float, ice_age_ybp: float):
    """Joint flood-only calibration, via card.calibrate.

    Both matched date pairs are honored exactly.  The solve used to be a
    2-D fsolve seeded with a hand-tuned initial guess; the package version
    reduces it to nested bracketed 1-D solves, which need no guess and cannot
    wander out of the valid parameter range.
    """
    return solve_flood_only(flood_age=flood_ybp,
                            flood_secular_age=FLOOD_SECULAR,
                            second_age=ice_age_ybp,
                            second_secular_age=ICE_AGE_SECULAR)


def main():
    fig, ax = plt.subplots(figsize=(9, 5.5), layout='tight')

    young_ages = np.linspace(1, 6000, 800)

    for name, sc in SCENARIOS.items():
        result = calibrate(sc['flood_ybp'], sc['ice_age_ybp'])
        lambda_F, k_F, model = result.lambda_F, result.k_F, result.model

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
