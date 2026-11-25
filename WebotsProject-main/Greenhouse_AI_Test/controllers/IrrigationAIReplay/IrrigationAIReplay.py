"""Replay dataset inputs through the trained model inside Webots.

Integration test only: rows are independent records, not a physical time series.
Pump codes are intentionally not mapped to ON/OFF. No watering is simulated.
"""
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import sys

import joblib
import pandas as pd
import sklearn
from controller import Supervisor


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ["Soil Moisture", "Temperature", "Air Humidity"]
INTERVAL_SECONDS = 1.0


def main():
    robot = Supervisor()
    timestep = int(robot.getBasicTimeStep())
    print(f"[AI TEST] Python: {sys.executable}", flush=True)
    print(f"[AI TEST] scikit-learn: {sklearn.__version__}", flush=True)
    if sklearn.__version__ != "1.6.1":
        raise RuntimeError("Use the project environment with scikit-learn 1.6.1.")

    package = joblib.load(ROOT / "greenhouse_irrigation_model.joblib")
    if package["input_columns"] != INPUTS:
        raise ValueError("The saved model input columns do not match this controller.")
    model = package["model"]
    data = pd.read_csv(ROOT / "data" / "irrigation_training.csv")
    required = INPUTS + ["Pump Data"]
    if data.empty or not set(required).issubset(data.columns):
        raise ValueError("The dataset is empty or missing required columns.")
    data[required] = data[required].apply(pd.to_numeric, errors="raise")
    if not data[required].map(lambda x: float('-inf') < x < float('inf')).all().all():
        raise ValueError("Dataset contains missing or non-finite values.")
    if not data["Pump Data"].isin([0, 1]).all():
        raise ValueError("Expected dataset pump labels 0 or 1.")

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    log_path = log_dir / f"ai_replay_{stamp}.csv"
    print(f"[AI TEST] Log: {log_path}", flush=True)
    print("[AI TEST] DATASET REPLAY ONLY. Pump-code meanings unverified. No watering physics.", flush=True)
    robot.setLabel(0, "AI INTEGRATION TEST - DATASET REPLAY", 0.02, 0.02, 0.055, 0xFFFFFF)
    robot.setLabel(1, "Soil units and pump ON/OFF mapping are unverified.", 0.02, 0.08, 0.04, 0xFFFF00)

    fields = ["simulation_time_s", "dataset_row", *INPUTS, "dataset_pump_code", "predicted_pump_code", "mode"]
    index = 0
    next_update = 0.0
    with log_path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        while robot.step(timestep) != -1:
            now = robot.getTime()
            if now + 1e-9 < next_update:
                continue
            if index >= len(data):
                robot.setLabel(2, f"Replay complete: {len(data)} rows. See CSV log.", 0.02, 0.15, 0.05, 0xFFFFFF)
                print("[AI TEST] Replay complete. Reset the simulation to replay again.", flush=True)
                break
            inputs = data.iloc[[index]][INPUTS]
            prediction = int(model.predict(inputs)[0])
            if prediction not in (0, 1):
                raise ValueError(f"Unexpected pump code: {prediction}")
            actual = int(data.iloc[index]["Pump Data"])
            values = {key: float(inputs.iloc[0][key]) for key in INPUTS}
            record = {
                "simulation_time_s": round(now, 3),
                "dataset_row": index + 1,
                **values,
                "dataset_pump_code": actual,
                "predicted_pump_code": prediction,
                "mode": "dataset_replay",
            }
            writer.writerow(record)
            stream.flush()
            robot.setCustomData(json.dumps(record))
            lines = [
                f"Dataset row: {index + 1}/{len(data)}",
                f"Soil reading: {values['Soil Moisture']:.1f} (dataset units)",
                f"Temperature: {values['Temperature']:.1f}",
                f"Air humidity: {values['Air Humidity']:.1f}",
                f"AI pump code: {prediction} | Dataset code: {actual}",
                "No simulated watering in this test.",
            ]
            for label_id, text in enumerate(lines, start=2):
                robot.setLabel(label_id, text, 0.02, 0.15 + (label_id - 2) * 0.06, 0.045, 0xFFFFFF)
            print(
                f"[AI TEST] Row {index + 1} | Soil {values['Soil Moisture']:.1f} | "
                f"Temp {values['Temperature']:.1f} | Humidity {values['Air Humidity']:.1f} | "
                f"AI code {prediction} | Dataset code {actual}",
                flush=True,
            )
            index += 1
            next_update = now + INTERVAL_SECONDS
        while index >= len(data) and robot.step(timestep) != -1:
            pass


if __name__ == "__main__":
    main()
