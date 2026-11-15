
from controller import Robot
import random

robot = Robot()
timestep = int(robot.getBasicTimeStep())

# Simulated soil moisture range
min_moisture = 0.0
max_moisture = 100.0

# Start with moderately moist soil
moisture = 45.0

# Update the reading every second
elapsed_ms = 0

while robot.step(timestep) != -1:
    elapsed_ms += timestep

    if elapsed_ms >= 1000:
        elapsed_ms = 0

        # Simulate small moisture changes
        moisture += random.uniform(-1.0, 1.0)
        moisture = max(min_moisture,
                       min(max_moisture, moisture))

        # Make the reading available as text
        robot.setCustomData(
            f"soil_moisture={moisture:.1f}"
        )

        print(f"Soil Moisture: {moisture:.1f}%")
