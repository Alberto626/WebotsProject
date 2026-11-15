
from controller import Robot
import math

robot = Robot()
timestep = int(robot.getBasicTimeStep())

# Baseline conditions
base_temperature = 25.0  # degrees Celsius
base_humidity = 60.0     # relative humidity, percent

# Simulate changing environmental conditions
elapsed_time = 0.0

while robot.step(timestep) != -1:
    # Gradual temperature variation
    temperature = (
        base_temperature
        + 4.0 * math.sin(elapsed_time / 30.0)
    )

    # Humidity decreases as temperature rises
    humidity = (
        base_humidity
        - 10.0 * math.sin(elapsed_time / 30.0)
    )

    # Keep humidity within valid percentage bounds
    humidity = max(0.0, min(100.0, humidity))

    # Publish readings to the Webots console
    print(
        f"Temperature: {temperature:.1f} C | "
        f"Humidity: {humidity:.1f}% RH"
    )

    # Store the latest readings in the Robot's customData field
    robot.setCustomData(
        f"temperature={temperature:.1f};humidity={humidity:.1f}"
    )

    elapsed_time += timestep / 1000.0
