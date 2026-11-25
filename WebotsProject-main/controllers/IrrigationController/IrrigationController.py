from controller import Supervisor
from pathlib import Path
from datetime import datetime
import csv
import json
import joblib
import pandas as pd

# Read the shared settings file.
project_folder = Path(__file__).resolve().parents[2]
settings_path = project_folder / "simulation_settings.json"

with settings_path.open("r", encoding="utf-8-sig") as settings_file:
    settings = json.load(settings_file)

MODE = settings["mode"]

if MODE not in ("AI", "FIXED"):
    raise ValueError(
        'The settings file must specify "mode": "AI" or "mode": "FIXED".'
    )

# ---------- Experiment settings ----------
RUN_DURATION_SECONDS = 120.0
FIXED_PERIOD_SECONDS = 20.0
FIXED_ON_SECONDS = 4.0

# Chosen simulation flow rate, not a measured physical flow.
SIMULATED_FLOW_L_PER_MIN = 1.0

# Illustrative plant-condition rules.
STRESS_SOIL_INDEX = 600.0
EARLY_STRESS_SECONDS = 5.0
HIGH_STRESS_SECONDS = 15.0
RECOVERY_RATE = 2.0
# -----------------------------------------

supervisor = Supervisor()
timestep = int(supervisor.getBasicTimeStep())
step_seconds = timestep / 1000.0


def duration_to_steps(seconds):
    steps = round(seconds / step_seconds)

    if abs(steps * step_seconds - seconds) > 0.000001:
        raise ValueError("Experiment timing must align with the timestep.")

    return steps


run_steps = duration_to_steps(RUN_DURATION_SECONDS)
period_steps = duration_to_steps(FIXED_PERIOD_SECONDS)
on_steps = duration_to_steps(FIXED_ON_SECONDS)

# Load the existing AI model.
model_package = joblib.load(
    project_folder / "greenhouse_irrigation_model.joblib"
)
irrigation_model = model_package["model"]
input_columns = model_package["input_columns"]

# Find the sensors.
environment_sensor = supervisor.getFromDef("GREENHOUSE_SENSOR")
soil_sensor = supervisor.getFromDef("SOIL_SENSOR")

if environment_sensor is None or soil_sensor is None:
    raise RuntimeError("Check the sensors' DEF names.")

environment_data = environment_sensor.getBaseNodeField("customData")
soil_data = soil_sensor.getBaseNodeField("customData")

if environment_data is None or soil_data is None:
    raise RuntimeError("Could not access sensor customData.")

# Find the pump indicator.
pump_appearance = supervisor.getFromDef("PUMP_APPEARANCE")

if pump_appearance is None:
    raise RuntimeError("Could not find PUMP_APPEARANCE in the world.")

pump_color = pump_appearance.getField("baseColor")
pump_emission = pump_appearance.getField("emissiveColor")

if pump_color is None or pump_emission is None:
    raise RuntimeError("Could not access the pump indicator fields.")

# Find the existing demonstration plant.
plant = supervisor.getFromDef("PLANT_1")

if plant is None:
    raise RuntimeError(
        "Could not find PLANT_1. "
        "Save its DEF name in the world before reopening."
    )

plant_leaf_color = plant.getField("leavesColor")

if plant_leaf_color is None:
    raise RuntimeError("PLANT_1 does not expose a leavesColor field.")

# Preserve the original green leaf texture at startup.
plant_leaf_color.setSFColor([1.0, 1.0, 1.0])


def set_pump_state(is_on):
    """Send the watering command and update the visible pump indicator."""
    supervisor.setCustomData(f"pump_on={int(is_on)}")

    if is_on:
        pump_color.setSFColor([0.0, 0.45, 1.0])
        pump_emission.setSFColor([0.0, 0.15, 0.35])
    else:
        pump_color.setSFColor([0.3, 0.3, 0.3])
        pump_emission.setSFColor([0.0, 0.0, 0.0])


def update_plant(soil_index, seconds_passed, stress_load):
    """Update an illustrative condition approximately once per second."""
    if soil_index < STRESS_SOIL_INDEX:
        stress_load += seconds_passed
    else:
        stress_load = max(
            0.0,
            stress_load - RECOVERY_RATE * seconds_passed
        )

    if stress_load >= HIGH_STRESS_SECONDS:
        color = [1.0, 0.35, 0.1]
    elif stress_load >= EARLY_STRESS_SECONDS:
        color = [1.0, 0.65, 0.25]
    else:
        color = [1.0, 1.0, 1.0]

    if soil_index >= STRESS_SOIL_INDEX and stress_load > 0.0:
        state = "RECOVERING"
    elif stress_load >= HIGH_STRESS_SECONDS:
        state = "STRESSED"
    elif stress_load >= EARLY_STRESS_SECONDS:
        state = "EARLY STRESS"
    else:
        state = "NORMAL"

    plant_leaf_color.setSFColor(color)

    return stress_load, state


# Prepare a separate log for this run.
logs_folder = project_folder / "logs"
logs_folder.mkdir(exist_ok=True)

run_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
log_path = logs_folder / f"irrigation_{MODE.lower()}_{run_name}.csv"

pump_on = MODE == "FIXED"
set_pump_state(pump_on)

commanded_on_time = 0.0
previous_time = supervisor.getTime()
start_time = previous_time
previous_plant_time = start_time

elapsed_ms = 0
step_count = 0
finished = False

stress_load = 0.0
plant_state = "NORMAL"

print("[Irrigation] Settings loaded:", settings_path)
print(f"[Irrigation] Mode: {MODE}")
print(f"[Irrigation] Duration: {RUN_DURATION_SECONDS} simulated seconds")
print("[Irrigation] Uncalibrated soil index; demonstration dynamics.")
print("[Irrigation] Demo convention: AI code 1 = ON, 0 = OFF.")
print("[Irrigation] Original dataset label mapping is unverified.")
print("[Plant] Leaf states are illustrative, not calibrated crop health.")
print(
    "[Water] Assumed simulated flow:",
    SIMULATED_FLOW_L_PER_MIN,
    "L/min"
)
print("[Irrigation] Log:", log_path)

with log_path.open("x", newline="", encoding="utf-8") as log_file:
    writer = csv.writer(log_file)
    writer.writerow([
        "simulation_time_s",
        "controller_mode",
        "temperature_c",
        "air_humidity_percent",
        "soil_index",
        "ai_code",
        "pump_command_on",
        "cumulative_commanded_on_time_s",
        "fixed_period_s",
        "fixed_on_s",
        "demo_plant_state",
        "demo_stress_load_s",
        "cumulative_applied_on_time_s",
        "simulated_flow_l_per_min",
        "estimated_simulated_water_l"
    ])
    log_file.flush()

    while supervisor.step(timestep) != -1:
        step_count += 1

        current_time = supervisor.getTime()
        time_passed = current_time - previous_time
        previous_time = current_time
        elapsed_time = current_time - start_time

        # Count time spent under the previous watering command.
        if pump_on:
            commanded_on_time += time_passed

        finished = step_count >= run_steps
        elapsed_ms += timestep
        record_now = elapsed_ms >= 1000 or finished

        if MODE == "FIXED":
            pump_on = (step_count % period_steps) < on_steps

        predicted_code = ""

        if record_now:
            elapsed_ms = 0

            environment_text = environment_data.getSFString()
            soil_text = soil_data.getSFString()

            if not environment_text or not soil_text:
                raise RuntimeError("A sensor has not supplied its reading.")

            readings = {}

            for item in (environment_text + ";" + soil_text).split(";"):
                name, value = item.split("=", 1)
                readings[name] = float(value)

            temperature = readings["temperature"]
            humidity = readings["humidity"]
            soil_index = readings["soil_moisture"]

            # Use watering time reported by the soil controller.
            applied_on_time = readings["applied_on_time_s"]

            # Convert applied seconds to minutes, then multiply by flow.
            estimated_water_l = (
                applied_on_time / 60.0
            ) * SIMULATED_FLOW_L_PER_MIN

            # Update the existing plant's illustrative condition.
            plant_time_passed = current_time - previous_plant_time
            previous_plant_time = current_time

            stress_load, plant_state = update_plant(
                soil_index,
                plant_time_passed,
                stress_load
            )

            # All three environmental inputs go into the AI model.
            if MODE == "AI" and not finished:
                model_inputs = pd.DataFrame(
                    [{
                        "Soil Moisture": soil_index,
                        "Temperature": temperature,
                        "Air Humidity": humidity
                    }]
                )

                predicted_code = int(
                    irrigation_model.predict(
                        model_inputs[input_columns]
                    )[0]
                )

                if predicted_code not in (0, 1):
                    raise RuntimeError("Unexpected AI prediction code.")

                pump_on = predicted_code == 1

        if finished:
            pump_on = False

        set_pump_state(pump_on)

        if record_now:
            pump_status = "ON" if pump_on else "OFF"

            # On-screen information, updated approximately once per second.
            display_lines = [
                (
                    f"{MODE} WATERING: {pump_status}",
                    0x00FF00 if pump_on else 0xFFFFFF
                ),
                (
                    f"Time: {elapsed_time:.1f}s | "
                    f"Applied pump ON: {applied_on_time:.2f}s",
                    0xFFFFFF
                ),
                (
                    f"Temperature: {temperature:.1f} C | "
                    f"Air humidity: {humidity:.1f}%",
                    0xFFFFFF
                ),
                (
                    f"Soil input index: {soil_index:.1f} "
                    f"(uncalibrated)",
                    0xFFFFFF
                ),
                (
                    f"DEMO PLANT: {plant_state} | "
                    f"Stress load: {stress_load:.1f}",
                    0xFFFFFF
                ),
                (
                    f"Estimated simulated water: {estimated_water_l:.3f} L",
                    0x00CCFF
                ),
                (
                    f"Assumed flow: {SIMULATED_FLOW_L_PER_MIN:.1f} L/min",
                    0xFFFFFF
                )
            ]

            for label_id, (message, color) in enumerate(display_lines):
                supervisor.setLabel(
                    label_id,
                    message,
                    0.02,
                    0.02 + label_id * 0.10,
                    0.075,
                    color
                )
            

            writer.writerow([
                round(elapsed_time, 3),
                MODE,
                temperature,
                humidity,
                soil_index,
                predicted_code,
                int(pump_on),
                round(commanded_on_time, 3),
                FIXED_PERIOD_SECONDS if MODE == "FIXED" else "",
                FIXED_ON_SECONDS if MODE == "FIXED" else "",
                plant_state,
                round(stress_load, 3),
                round(applied_on_time, 6),
                SIMULATED_FLOW_L_PER_MIN,
                round(estimated_water_l, 6)
            ])
            log_file.flush()

            print(
                f"[{MODE}] Time: {elapsed_time:.1f}s | "
                f"Soil: {soil_index:.1f} | "
                f"Watering: {pump_status} | "
                f"Plant demo: {plant_state} | "
                f"Estimated simulated water: {estimated_water_l:.3f} L"
            )

        if finished:
            break

if finished:
    print(f"[Irrigation] {MODE} run complete. Log saved:", log_path)

    supervisor.setLabel(
        0,
        f"{MODE} RUN COMPLETE - reopen world before another run",
        0.02, 0.02, 0.04, 0xFFFFFF
    )

    supervisor.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)
    supervisor.step(0)

    while supervisor.step(timestep) != -1:
        set_pump_state(False)
        supervisor.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)
        supervisor.step(0)