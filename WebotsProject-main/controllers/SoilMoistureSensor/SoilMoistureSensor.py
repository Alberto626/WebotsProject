from controller import Supervisor
from pathlib import Path
from datetime import datetime
import csv
import json

sensor = Supervisor()
timestep = int(sensor.getBasicTimeStep())

# Read the shared settings file.
project_folder = Path(__file__).resolve().parents[2]
settings_path = project_folder / "simulation_settings.json"

with settings_path.open("r", encoding="utf-8-sig") as settings_file:
    settings = json.load(settings_file)

# Demonstration settings, not calibrated soil physics.
minimum_index = 320.0
maximum_index = 980.0
moisture_index = float(settings["starting_soil_index"])

if not minimum_index <= moisture_index <= maximum_index:
    raise ValueError(
        f"starting_soil_index must be between "
        f"{minimum_index} and {maximum_index}."
    )

# Index units per simulated second.
drying_rate = 5.0
watering_rate = 25.0

# Find the coordinating Robot and its watering command.
irrigation_system = sensor.getFromDef("IRRIGATION_SYSTEM")

if irrigation_system is None:
    raise RuntimeError(
        "Could not find IRRIGATION_SYSTEM. Check its DEF name."
    )

pump_data = irrigation_system.getField("customData")

if pump_data is None:
    raise RuntimeError("Could not access the watering command.")

# Track the watering applied by this controller.
applied_on_time = 0.0
start_time = sensor.getTime()
previous_time = start_time
elapsed_ms = 0

# Create a separate soil-response log.
logs_folder = project_folder / "logs"
logs_folder.mkdir(exist_ok=True)

run_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
log_path = logs_folder / f"soil_response_{run_name}.csv"

# Publish the initial sensor state.
sensor.setCustomData(
    f"soil_moisture={moisture_index:.6f};"
    f"applied_on_time_s={applied_on_time:.6f};"
    f"soil_time_s=0.000000"
)

print("[Soil] Settings loaded:", settings_path)
print(f"[Soil] Starting index: {moisture_index:.1f}")
print("[Soil] Feedback simulation started.")
print("[Soil] Rates and index direction are demonstration assumptions.")
print("[Soil] Applied watering log:", log_path)

with log_path.open("x", newline="", encoding="utf-8") as log_file:
    writer = csv.writer(log_file)

    writer.writerow([
        "soil_simulation_time_s",
        "soil_index",
        "pump_command_applied",
        "cumulative_applied_on_time_s",
        "step_duration_s"
    ])

    # Initial state, before any soil updates.
    writer.writerow([0.0, moisture_index, 0, 0.0, 0.0])
    log_file.flush()

    while sensor.step(timestep) != -1:
        current_time = sensor.getTime()
        dt_seconds = current_time - previous_time
        previous_time = current_time
        elapsed_time = current_time - start_time

        # Read the latest command available to this controller.
        command = pump_data.getSFString()
        pump_on = command == "pump_on=1"

        # Apply drying during this discrete simulation update.
        moisture_index -= drying_rate * dt_seconds

        # Count exactly the ON duration used for the watering effect.
        if pump_on:
            moisture_index += watering_rate * dt_seconds
            applied_on_time += dt_seconds

        moisture_index = max(
            minimum_index,
            min(maximum_index, moisture_index)
        )

        # Publish the reading, applied time, and its timestamp.
        sensor.setCustomData(
            f"soil_moisture={moisture_index:.6f};"
            f"applied_on_time_s={applied_on_time:.6f};"
            f"soil_time_s={elapsed_time:.6f}"
        )

        # Record every simulation step to capture short watering pulses.
        writer.writerow([
            round(elapsed_time, 6),
            round(moisture_index, 6),
            int(pump_on),
            round(applied_on_time, 6),
            round(dt_seconds, 6)
        ])
        log_file.flush()

        # Keep console messages to approximately once per second.
        elapsed_ms += timestep

        if elapsed_ms >= 1000:
            elapsed_ms = 0
            status = "ON" if pump_on else "OFF"

            print(
                f"[Soil] Time: {elapsed_time:.1f}s | "
                f"Index: {moisture_index:.1f} | "
                f"Applied command: {status} | "
                f"Total applied ON: {applied_on_time:.3f}s"
            )