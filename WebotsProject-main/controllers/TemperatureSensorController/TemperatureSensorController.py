from controller import Robot
from pathlib import Path
import json
import math

robot = Robot()
timestep = int(robot.getBasicTimeStep())

# Find the shared settings file in the main project folder.
project_folder = Path(__file__).resolve().parents[2]
settings_path = project_folder / "simulation_settings.json"

with settings_path.open("r", encoding="utf-8-sig") as settings_file:
    settings = json.load(settings_file)

# Read the baseline environmental conditions.
base_temperature = float(settings["base_temperature_c"])
base_humidity = float(settings["base_humidity_percent"])

if not math.isfinite(base_temperature):
    raise ValueError("Baseline temperature must be a finite number.")

if not math.isfinite(base_humidity) or not 0.0 <= base_humidity <= 100.0:
    raise ValueError("Baseline humidity must be between 0 and 100.")

print("[Environment] Settings loaded:", settings_path)
print(
    f"[Environment] Baseline temperature: {base_temperature:.1f} C | "
    f"Baseline humidity: {base_humidity:.1f}% RH"
)

elapsed_time = 0.0
elapsed_ms = 0

while robot.step(timestep) != -1:
    # Preserve the existing gradual environmental variation.
    variation = math.sin(elapsed_time / 30.0)

    temperature = base_temperature + 4.0 * variation
    humidity = base_humidity - 10.0 * variation

    # Keep humidity within valid percentage bounds.
    humidity = max(0.0, min(100.0, humidity))

    # Publish fresh readings every simulation step.
    robot.setCustomData(
        f"temperature={temperature:.1f};humidity={humidity:.1f}"
    )

    # Print approximately once per simulated second.
    elapsed_ms += timestep

    if elapsed_ms >= 1000:
        elapsed_ms = 0

        print(
            f"[Environment] Temperature: {temperature:.1f} C | "
            f"Humidity: {humidity:.1f}% RH"
        )

    elapsed_time += timestep / 1000.0