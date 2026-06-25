import cv2
import numpy as np
import tflite_runtime.interpreter as tflite
from gpiozero import Buzzer, Button
import time
import os
import csv
from datetime import datetime

import board
import busio
import adafruit_adxl34x
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- CONFIG ---
BUZZER_PIN = 18
IMG_SIZE = 128
THRESHOLD = 0.5  # Minimum confidence score to classify as crack
IMAGE_DIR = "images"
LOG_FILE = "crack_log.csv"


BUTTON_PIN = 17
V_THRESHOLD = 12  # m/s^2
LOG_INTERVAL = 5  # seconds
WINDOW_SIZE = 25  # plot points

# --- GPIO SETUP ---
buzzer = Buzzer(BUZZER_PIN)
button = Button(BUTTON_PIN)
silenced = False  # System starts armed

# --- TOGGLE SYSTEM STATE ON BUTTON PRESS ---
def handle_button_press():
    global silenced
    silenced = not silenced
    buzzer.off()
    print("Alarm silenced." if silenced else "System re-armed.")

button.when_pressed = handle_button_press

# --- ACCELEROMETER SETUP ---
i2c = busio.I2C(board.SCL, board.SDA)
accelerometer = adafruit_adxl34x.ADXL345(i2c)

# --- LOGGING SETUP ---
csv_file = open("shm_log.csv", mode='a', newline='')
csv_writer = csv.writer(csv_file)
csv_writer.writerow(["Timestamp", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)"])

# --- PLOTTING SETUP ---
x_data, y_data, z_data = [], [], []

fig, ax = plt.subplots()
line_x, = ax.plot([], [], label='X')
line_y, = ax.plot([], [], label='Y')
line_z, = ax.plot([], [], label='Z')
ax.set_ylim(-5, 15)
ax.set_xlim(0, WINDOW_SIZE)
ax.set_title('Live Vibration Monitor (m/s²)')
ax.set_xlabel('Samples')
ax.set_ylabel('Acceleration')
ax.legend()

# --- MAIN DATA COLLECTION LOOP ---
def update_plot(frame):
    global x_data, y_data, z_data

    x, y, z = accelerometer.acceleration
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    # Append to data lists
    x_data.append(x)
    y_data.append(y)
    z_data.append(z)
    if len(x_data) > WINDOW_SIZE:
        x_data = x_data[-WINDOW_SIZE:]
        y_data = y_data[-WINDOW_SIZE:]
        z_data = z_data[-WINDOW_SIZE:]

    # Update plot lines
    line_x.set_data(range(len(x_data)), x_data)
    line_y.set_data(range(len(y_data)), y_data)
    line_z.set_data(range(len(z_data)), z_data)
    
    
    # Log data
    csv_writer.writerow([timestamp, round(x, 2), round(y, 2), round(z, 2)])
    csv_file.flush()

    # Trigger alert
    if max(abs(x), abs(y), abs(z)) > V_THRESHOLD and not silenced:
        buzzer.on()
        time.sleep(0.5)
        buzzer.off()
        print(f"Vibration Alert! [{timestamp}] X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
    else:
        buzzer.off()
        if silenced:
            print("System is silenced — no alerts.")

    print(f"[{timestamp}] X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
    time.sleep(LOG_INTERVAL)
    return line_x, line_y, line_z

ani = animation.FuncAnimation(fig, update_plot, interval=100)

"""try:
    plt.show()
except KeyboardInterrupt:
    print("Exiting...")
finally:
    buzzer.off()
    cam.release()
    csv_file.close()"""


# --- TFLITE SETUP ---
os.makedirs(IMAGE_DIR, exist_ok=True)

# Initialize buzzer
#buzzer = Buzzer(BUZZER_PIN)

# Load TFLite model
interpreter = tflite.Interpreter(model_path="crack_binary_classifier.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# Prepare CSV log file
log_exists = os.path.isfile(LOG_FILE)
with open(LOG_FILE, mode='a', newline='') as f:
    log_writer = csv.writer(f)
    if not log_exists:
        log_writer.writerow(["Timestamp", "Prediction Score", "Image Filename"])

# Start camera
cam = cv2.VideoCapture(0)
if not cam.isOpened():
    raise IOError("Cannot open webcam")

print("Model loaded. Starting real-time detection...")

 
try:
    while True:
        plt.show() 
        ret, frame = cam.read()
        if not ret:
            continue

        # Preprocess for model
        gray_model = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray_model, (IMG_SIZE, IMG_SIZE))
        normalized = resized / 255.0
        input_data = np.expand_dims(normalized, axis=(0, -1)).astype(np.float32)

        # Run inference
        interpreter.set_tensor(input_details[0]['index'], input_data)
        interpreter.invoke()
        prediction = interpreter.get_tensor(output_details[0]['index'])[0][0]

        # Determine label and color
        is_crack = prediction > THRESHOLD
        label = f"{'Cracked' if is_crack else 'Non-cracked'} ({prediction:.2f})"
        color = (0, 0, 255) if is_crack else (0, 255, 0)

        if is_crack:
            # Highlight possible cracks
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)

            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                if cv2.contourArea(cnt) > 500:
                    x, y, w, h = cv2.boundingRect(cnt)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                    cv2.putText(frame, 'Crack Region', (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # Trigger buzzer
            buzzer.on()

            # Save image and log
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            image_filename = f"{IMAGE_DIR}/crack_{timestamp}.jpg"
            cv2.imwrite(image_filename, frame)

            with open(LOG_FILE, mode='a', newline='') as f:
                log_writer = csv.writer(f)
                log_writer.writerow([timestamp, f"{prediction:.2f}", image_filename])
        else:
            buzzer.off()

        # Display result
        cv2.putText(frame, label, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        cv2.imshow("Crack Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("Exiting...")

finally:
    cam.release()
    buzzer.off()
    csv_file.close()
    cv2.destroyAllWindows()
    print("Detection stopped.")