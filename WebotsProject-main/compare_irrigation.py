from pathlib import Path
import pandas as pd

project_folder = Path(__file__).resolve().parent
logs_folder = project_folder / "logs"

# Chosen simulation setting, not a measured pump specification.
SIMULATED_FLOW_L_PER_MIN = 1.0

# Soil-response logs from the verified comparison runs.
files = {
    "AI": "soil_response_20261123_160839_730781.csv",
    "FIXED": "soil_response_20261123_161009_375123.csv"
}

results = []

for mode, filename in files.items():
    data = pd.read_csv(logs_folder / filename)

    first = data.iloc[0]
    last = data.iloc[-1]

    duration = float(
        last["soil_simulation_time_s"]
        - first["soil_simulation_time_s"]
    )

    applied_on_seconds = float(
        last["cumulative_applied_on_time_s"]
        - first["cumulative_applied_on_time_s"]
    )

    # Convert applied watering seconds to estimated litres.
    estimated_litres = (
        applied_on_seconds
        * SIMULATED_FLOW_L_PER_MIN
        / 60.0
    )

    results.append({
        "mode": mode,
        "duration_s": duration,
        "starting_soil_index": float(first["soil_index"]),
        "final_soil_index": float(last["soil_index"]),
        "applied_on_time_s": applied_on_seconds,
        "simulated_flow_l_per_min": SIMULATED_FLOW_L_PER_MIN,
        "estimated_simulated_water_l": estimated_litres
    })

summary = pd.DataFrame(results)

# Check that both runs cover the same duration and initial index.
if summary["duration_s"].max() - summary["duration_s"].min() > 0.000001:
    raise ValueError("Run durations do not match.")

if (
    summary["starting_soil_index"].max()
    - summary["starting_soil_index"].min()
    > 0.000001
):
    raise ValueError("Starting soil indices do not match.")

print("\nSIMULATED IRRIGATION COMPARISON")
print(summary.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

ai_water = summary.loc[
    summary["mode"] == "AI", "estimated_simulated_water_l"
].iloc[0]

fixed_water = summary.loc[
    summary["mode"] == "FIXED", "estimated_simulated_water_l"
].iloc[0]

if fixed_water > 0:
    reduction = 100.0 * (fixed_water - ai_water) / fixed_water
    print(f"\nRelative reduction versus FIXED: {reduction:.2f}%")

print("\nVolumes use a chosen simulated flow rate, not measured flow.")
print("The runs finish at different soil indices.")
print("Lower water use alone does not establish better performance.")

output_path = logs_folder / "comparison_summary.csv"
summary.to_csv(output_path, index=False)

print("\nSummary saved to:", output_path)