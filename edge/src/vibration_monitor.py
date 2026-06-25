import time
import csv
import cv2
from datetime import datetime
import board
import busio
import adafruit_adxl34x

# Initialize I2C and Accelerometer
i2c = busio.I2C(board.SCL, board.SDA)
accelerometer = adafruit_adxl34x.ADXL345(i2c)

# Initialize Camera
cam = cv2.VideoCapture(0)

# Prepare CSV file
csv_file = open("shm_log.csv", mode='a', newline='')
csv_writer = csv.writer(csv_file)
csv_writer.writerow(["Timestamp", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)", "Image Filename"])

print("Logging ADXL345 data and capturing images...")

try:
    while True:
        # Get timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

        # Read acceleration (already in m/s²)
        x, y, z = accelerometer.acceleration

        # Capture image
        ret, frame = cam.read()
        if ret:
            image_filename = f"images/crack_{timestamp}.jpg"
            cv2.imwrite(image_filename, frame)
        else:
            image_filename = "capture_failed"

        # Log to CSV
        csv_writer.writerow([timestamp, round(x, 2), round(y, 2), round(z, 2), image_filename])
        csv_file.flush()

        print(f"[{timestamp}] X={x:.2f}, Y={y:.2f}, Z={z:.2f} | Image: {image_filename}")
        time.sleep(5)

except KeyboardInterrupt:
    print("Stopped logging.")

finally:
    cam.release()
    csv_file.close()
