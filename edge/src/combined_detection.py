import time
import csv
import cv2
import board
import busio
import adafruit_adxl34x
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from datetime import datetime
from gpiozero import Buzzer, Button

# --- CONFIGURATIONS ---
BUZZER_PIN = 18
BUTTON_PIN = 17
THRESHOLD = 12  # m/s^2
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
    if silenced:
        buzzer.off()
        print("🛑 System silenced by button press.")
    else:
        print("✅ System re-armed.")

button.when_pressed = handle_button_press

# --- ACCELEROMETER SETUP ---
i2c = busio.I2C(board.SCL, board.SDA)
accelerometer = adafruit_adxl34x.ADXL345(i2c)

# --- CAMERA SETUP ---
cam = cv2.VideoCapture(0)

# --- LOGGING SETUP ---
csv_file = open("shm_log.csv", mode='a', newline='')
csv_writer = csv.writer(csv_file)
csv_writer.writerow(["Timestamp", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)", "Image Filename"])

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

    # Capture image
    ret, frame_img = cam.read()
    if ret:
        image_filename = f"images/crack_{timestamp}.jpg"
        cv2.imwrite(image_filename, frame_img)
    else:
        image_filename = "capture_failed"

    # Log data
    csv_writer.writerow([timestamp, round(x, 2), round(y, 2), round(z, 2), image_filename])
    csv_file.flush()

    # Trigger alert
    if max(abs(x), abs(y), abs(z)) > THRESHOLD and not silenced:
        buzzer.on()
        time.sleep(0.5)
        buzzer.off()
        print(f"🚨 Vibration Alert! [{timestamp}] X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
    else:
        buzzer.off()
        if silenced:
            print("🔇 System is silenced — no alerts.")

    print(f"[{timestamp}] X={x:.2f}, Y={y:.2f}, Z={z:.2f} | Image: {image_filename}")
    time.sleep(LOG_INTERVAL)
    return line_x, line_y, line_z

ani = animation.FuncAnimation(fig, update_plot, interval=100)

try:
    plt.show()
except KeyboardInterrupt:
    print("Exiting...")
finally:
    buzzer.off()
    cam.release()
    csv_file.close()
