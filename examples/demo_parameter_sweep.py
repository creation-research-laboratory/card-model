#!/usr/bin/env python3
"""
Demonstration script for the plot_general_model_parameter_sweep function.

This script shows how to use the new parameter sweep plotting function
to visualize multiple GeneralModel calculations with varied parameters.
"""

from card import GeneralModelParams, plot_general_model_parameter_sweep

def demo_parameter_sweep():
    """Demonstrate the parameter sweep plotting function."""

    print("Creating parameter sweep plots...")

    # Example 1: Vary lambda_F and k_PF
    print("\n1. Varying lambda_F and k_PF:")
    base_params = GeneralModelParams(
        lambda_c=1e3,
        lambda_F=1e5,  # This will be overridden by vary_params
        lambda_bg=1.0,
        k_c=1e-1,
        k_F=0.0,
        k_PF=8.04e-3,  # This will be overridden by vary_params
        t_c=1,
        t_F=1656,
        t_F2=1657
    )

    vary_params = {
        'lambda_F': [1e4, 1e5, 1e6],
        'k_PF': [1e-3, 8.04e-3, 1e-2]
    }

    plot_general_model_parameter_sweep(
        base_params=base_params,
        vary_params=vary_params,
        out_file="demo_sweep_lambdaF_kF.png",
        show=False
    )
    print("   Saved: demo_sweep_lambdaF_kF.png")

    # Example 2: Vary only lambda_F
    print("\n2. Varying only lambda_F:")
    vary_params_simple = {
        'lambda_F': [1e3, 1e4, 1e5, 1e6, 1e7]
    }

    plot_general_model_parameter_sweep(
        base_params=base_params,
        vary_params=vary_params_simple,
        out_file="demo_sweep_lambdaF_only.png",
        show=False
    )
    print("   Saved: demo_sweep_lambdaF_only.png")

    # Example 3: Vary decay constants
    print("\n3. Varying decay constants k_c and k_PF:")
    vary_params_decay = {
        'k_c': [1e-2, 1e-1, 1e0],
        'k_PF': [1e-4, 1e-3, 1e-2]
    }

    plot_general_model_parameter_sweep(
        base_params=base_params,
        vary_params=vary_params_decay,
        out_file="demo_sweep_decay_constants.png",
        show=False
    )
    print("   Saved: demo_sweep_decay_constants.png")

    print("\nAll demo plots created successfully!")
    print("Check the generated PNG files to see the parameter sweep visualizations.")

if __name__ == "__main__":
    demo_parameter_sweep()