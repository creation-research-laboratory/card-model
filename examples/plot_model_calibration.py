"""
Model calibration plot: secular age vs. young-age age for two flood-only
calibration scenarios.

Each scenario pins the Flood and the end of the Ice Age to paired
secular / young-age dates. With lambda_c = lambda_bg = 1 the model reduces
to the flood-only limit of the General model, and with k_F specified the
single unknown lambda_F is solved so the Flood pair is honored exactly.
The Ice Age pair is then a check on the calibration; the script prints
the residual.

All young ages are in years before present (YBP).
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import brentq

from card.decay_solver import AGE_OF_EARTH, GeneralModel, GeneralModelParams

# Paired calibration dates (secular age, YBP) shared by both scenarios
FLOOD_SECULAR = 541e6    # Precambrian-Cambrian boundary
ICE_AGE_SECULAR = 12e3   # End of the Ice Age

SCENARIOS = {
    'Scenario 1': {'flood_ybp': 5324, 'ice_age_ybp': 4200, 'k_F': 0.0097,
                   'color': '#e34948'},
    'Scenario 2': {'flood_ybp': 4374, 'ice_age_ybp': 3500, 'k_F': 0.0124,
                   'color': '#2a78d6'},
}


def build_model(flood_ybp: float, k_F: float, lambda_F: float) -> GeneralModel:
    """Flood-only limit of the General model: no Creation-week acceleration,
    instantaneous Flood (t_F == t_F2) at the scenario's Flood time."""
    t_flood = AGE_OF_EARTH - flood_ybp  # years after Creation
    params = GeneralModelParams(
        lambda_c=1.0,
        lambda_F=lambda_F,
        lambda_bg=1.0,
        k_c=1.0,     # irrelevant: lambda_c == lambda_bg
        k_F=k_F,
        t_c=1.0,
        t_F=t_flood,
        t_F2=t_flood,
    )
    return GeneralModel(params)


def solve_lambda_F(flood_ybp: float, k_F: float) -> float:
    """Solve for lambda_F such that a rock formed at the Flood has the
    target secular age. Root-find in log10 space (monotonic in lambda_F)."""
    def residual(log10_lambda_F):
        model = build_model(flood_ybp, k_F, 10.0 ** log10_lambda_F)
        return model.forward_age(flood_ybp) - FLOOD_SECULAR

    log10_lambda_F = brentq(residual, 2.0, 12.0, xtol=1e-12)
    return 10.0 ** log10_lambda_F


def main():
    fig, ax = plt.subplots(figsize=(9, 5.5), layout='tight')

    young_ages = np.linspace(1, 6000, 800)

    for name, sc in SCENARIOS.items():
        lambda_F = solve_lambda_F(sc['flood_ybp'], sc['k_F'])
        model = build_model(sc['flood_ybp'], sc['k_F'], lambda_F)

        secular = np.array([model.forward_age(t) for t in young_ages])
        ice_age_pred = model.forward_age(sc['ice_age_ybp'])

        print(f"{name}: Flood {sc['flood_ybp']} YBP, k_F = {sc['k_F']}")
        print(f"  solved lambda_F = {lambda_F:.4g} "
              f"(log10 = {np.log10(lambda_F):.4f})")
        print(f"  Flood check: {model.forward_age(sc['flood_ybp']):.4g} yr "
              f"(target {FLOOD_SECULAR:.4g})")
        print(f"  Ice Age end at {sc['ice_age_ybp']} YBP -> secular "
              f"{ice_age_pred:.4g} yr (target {ICE_AGE_SECULAR:.4g}, "
              f"residual {100 * (ice_age_pred / ICE_AGE_SECULAR - 1):+.1f}%)")

        label = (f"{name}: Flood {sc['flood_ybp']} YBP, "
                 f"$k_F$ = {sc['k_F']}, "
                 f"$\\lambda_F$ = {lambda_F:.3g}")
        ax.semilogy(young_ages, secular, color=sc['color'], linewidth=2,
                    label=label)

        # Calibration points: Flood (exact) and Ice Age end (check)
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
    ax.set_title('Model calibration: secular age vs. young-age age')
    ax.set_xlim(0, 6000)
    ax.set_ylim(1, 5e9)
    ax.grid(True, which='major', alpha=0.3)
    ax.legend(loc='lower right', fontsize=9)

    out_file = 'model_calibration_plot.png'
    fig.savefig(out_file, dpi=300)
    print(f"\nSaved: {out_file}")


if __name__ == '__main__':
    main()
