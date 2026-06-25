import cv2
import numpy as np
import tflite_runtime.interpreter as tflite
from gpiozero import Buzzer, Button
import time
import os
import csv
import board
import busio
import adafruit_adxl34x
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from datetime import datetime

# --- CONFIGURATIONS ---
BUZZER_PIN = 18
BUTTON_PIN = 17
IMG_SIZE = 128
CRACK_THRESHOLD = 0.5  # Minimum confidence score to classify as crack
VIBRATION_THRESHOLD = 10  # m/s^2
LOG_INTERVAL = 5  # seconds
WINDOW_SIZE = 25  # plot points
IMAGE_DIR = "images"
CRACK_LOG_FILE = "crack_log.csv"
VIBRATION_LOG_FILE = "shm_log.csv"

# --- SETUP ---
os.makedirs(IMAGE_DIR, exist_ok=True)

# --- GPIO SETUP ---
buzzer = Buzzer(BUZZER_PIN)
button = Button(BUTTON_PIN)
system_silenced = False  # System starts armed

# --- TOGGLE SYSTEM STATE ON BUTTON PRESS ---
def handle_button_press():
    global system_silenced
    system_silenced = not system_silenced
    # Always turn off buzzer immediately when button is pressed
    try:
        buzzer.off()
    except:
        pass
    
    if system_silenced:
        print("🛑 System silenced by button press.")
    else:
        print("✅ System re-armed.")

button.when_pressed = handle_button_press

# --- ACCELEROMETER SETUP ---
i2c = busio.I2C(board.SCL, board.SDA)
accelerometer = adafruit_adxl34x.ADXL345(i2c)

# --- LOAD TFLITE MODEL ---
interpreter = tflite.Interpreter(model_path="crack_binary_classifier.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# --- CAMERA SETUP ---
cam = cv2.VideoCapture(0)
if not cam.isOpened():
    raise IOError("Cannot open webcam")

# --- LOGGING SETUP ---
# Crack detection log
crack_log_exists = os.path.isfile(CRACK_LOG_FILE)
with open(CRACK_LOG_FILE, mode='a', newline='') as f:
    crack_writer = csv.writer(f)
    if not crack_log_exists:
        crack_writer.writerow(["Timestamp", "Prediction Score", "Image Filename"])

# Vibration monitoring log
vibration_csv_file = open(VIBRATION_LOG_FILE, mode='a', newline='')
vibration_csv_writer = csv.writer(vibration_csv_file)
vibration_csv_writer.writerow(["Timestamp", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)", "Image Filename", "Crack Detected", "Crack Score"])

# --- PLOTTING SETUP ---
x_data, y_data, z_data = [], [], []

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

# Vibration plot
line_x, = ax1.plot([], [], label='X', color='red')
line_y, = ax1.plot([], [], label='Y', color='green') 
line_z, = ax1.plot([], [], label='Z', color='blue')
ax1.set_ylim(-5, 15)
ax1.set_xlim(0, WINDOW_SIZE)
ax1.set_title('Live Vibration Monitor (m/s²)')
ax1.set_xlabel('Samples')
ax1.set_ylabel('Acceleration')
ax1.legend()
ax1.grid(True)

# Status display
ax2.text(0.5, 0.5, 'System Status', ha='center', va='center', fontsize=16)
ax2.set_xlim(0, 1)
ax2.set_ylim(0, 1)
ax2.axis('off')
ax2.set_title('System Status')

# --- MAIN MONITORING LOOP ---
def update_system(frame):
    global x_data, y_data, z_data
    
    # Get accelerometer data
    x, y, z = accelerometer.acceleration
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    
    # Update vibration data
    x_data.append(x)
    y_data.append(y)
    z_data.append(z)
    if len(x_data) > WINDOW_SIZE:
        x_data = x_data[-WINDOW_SIZE:]
        y_data = y_data[-WINDOW_SIZE:]
        z_data = z_data[-WINDOW_SIZE:]
    
    # Update vibration plot
    line_x.set_data(range(len(x_data)), x_data)
    line_y.set_data(range(len(y_data)), y_data)
    line_z.set_data(range(len(z_data)), z_data)
    
# --- MAIN MONITORING LOOP ---
def update_system(frame):
    global x_data, y_data, z_data
    
    # Get accelerometer data
    x, y, z = accelerometer.acceleration
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    
    # Update vibration data
    x_data.append(x)
    y_data.append(y)
    z_data.append(z)
    if len(x_data) > WINDOW_SIZE:
        x_data = x_data[-WINDOW_SIZE:]
        y_data = y_data[-WINDOW_SIZE:]
        z_data = z_data[-WINDOW_SIZE:]
    
    # Update vibration plot
    line_x.set_data(range(len(x_data)), x_data)
    line_y.set_data(range(len(y_data)), y_data)
    line_z.set_data(range(len(z_data)), z_data)
    
    # Check for vibration threshold
    max_vibration = max(abs(x), abs(y), abs(z))
    vibration_alert = max_vibration > VIBRATION_THRESHOLD
    
    # Update status display
    ax2.clear()
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis('off')
    ax2.set_title('System Status')
    
    status_color = 'red' if vibration_alert and not system_silenced else 'green'
    status_text = f"🚨 VIBRATION ALERT! {max_vibration:.2f} m/s²" if vibration_alert and not system_silenced else "✅ Vibration Normal"
    
    if system_silenced:
        status_text = "🔇 System Silenced"
        status_color = 'orange'
    
    ax2.text(0.5, 0.8, status_text, ha='center', va='center', 
             fontsize=12, color=status_color, weight='bold')
    ax2.text(0.5, 0.6, f"Vibration: X={x:.1f}, Y={y:.1f}, Z={z:.1f}", 
             ha='center', va='center', fontsize=10)
    ax2.text(0.5, 0.4, f"Max Vibration: {max_vibration:.2f} m/s²", 
             ha='center', va='center', fontsize=10)
    ax2.text(0.5, 0.2, f"Threshold: {VIBRATION_THRESHOLD} m/s²", 
             ha='center', va='center', fontsize=9, style='italic')
    
    # Trigger vibration alert
    if vibration_alert and not system_silenced:
        try:
            buzzer.on()
            print(f"🚨 VIBRATION ALERT! [{timestamp}] Max: {max_vibration:.2f} m/s²")
        except Exception as e:
            print(f"⚠️ Buzzer error in vibration: {e}")
    else:
        # Only turn off buzzer if system is not silenced and no alerts
        if not system_silenced and not vibration_alert:
            try:
                buzzer.off()
            except:
                pass
    
    # Console output for vibration
    if system_silenced:
        print(f"🔇 [{timestamp}] System silenced - Vibration: {max_vibration:.2f}")
    elif not vibration_alert:
        print(f"✅ [{timestamp}] Vibration normal: {max_vibration:.2f}")
    
    time.sleep(LOG_INTERVAL)
    return line_x, line_y, line_z

# --- CAMERA PROCESSING LOOP (separate thread) ---
def camera_loop():
    global system_silenced
    
    print("🎥 Starting camera feed window...")
    
    # Add small delay to ensure camera is ready
    time.sleep(1)
    
    while True:
        try:
            ret, frame = cam.read()
            if not ret:
                print("⚠️ Camera read failed, retrying...")
                time.sleep(0.1)
                continue
            
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            
            # Preprocess for crack detection model
            gray_model = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray_model, (IMG_SIZE, IMG_SIZE))
            normalized = resized / 255.0
            input_data = np.expand_dims(normalized, axis=(0, -1)).astype(np.float32)
            
            # Run crack detection inference
            interpreter.set_tensor(input_details[0]['index'], input_data)
            interpreter.invoke()
            crack_score = interpreter.get_tensor(output_details[0]['index'])[0][0]
            crack_detected = crack_score > CRACK_THRESHOLD
            
            # Determine label and color for display
            label = f"{'CRACK DETECTED' if crack_detected else 'NO CRACK'} ({crack_score:.2f})"
            color = (0, 0, 255) if crack_detected else (0, 255, 0)
            
            # Add system status to display
            system_status = "SILENCED" if system_silenced else "ACTIVE"
            status_color = (0, 165, 255) if system_silenced else (255, 255, 255)
            
            if crack_detected:
                # Highlight possible crack regions
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blurred = cv2.GaussianBlur(gray, (5, 5), 0)
                edges = cv2.Canny(blurred, 50, 150)
                
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for cnt in contours:
                    if cv2.contourArea(cnt) > 500:
                        x_rect, y_rect, w, h = cv2.boundingRect(cnt)
                        cv2.rectangle(frame, (x_rect, y_rect), (x_rect + w, y_rect + h), (0, 0, 255), 2)
                        cv2.putText(frame, 'Crack Region', (x_rect, y_rect - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                # Trigger crack alert only if system is active
                if not system_silenced:
                    try:
                        buzzer.on()
                        print(f"🚨 CRACK DETECTED! [{timestamp}] Score: {crack_score:.2f}")
                    except Exception as e:
                        print(f"⚠️ Buzzer error: {e}")
                
                # Save crack image
                try:
                    image_filename = f"{IMAGE_DIR}/crack_{timestamp}.jpg"
                    cv2.imwrite(image_filename, frame)
                    
                    # Log crack detection
                    with open(CRACK_LOG_FILE, mode='a', newline='') as f:
                        crack_writer = csv.writer(f)
                        crack_writer.writerow([timestamp, f"{crack_score:.2f}", image_filename])
                except Exception as e:
                    print(f"⚠️ File save error: {e}")
            else:
                # Turn off buzzer only if system is active and no vibration alert
                if not system_silenced:
                    try:
                        buzzer.off()
                    except:
                        pass
            
            # Add overlays to frame
            cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
            cv2.putText(frame, f"System: {system_status}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
            cv2.putText(frame, f"Threshold: {CRACK_THRESHOLD}", (10, frame.shape[0] - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, "Press 'q' to quit", (10, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Display the frame
            cv2.imshow("Live Crack Detection Feed", frame)
            
            # Check for quit command (non-blocking)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("🛑 Camera feed stopped by user")
                break
                
        except KeyboardInterrupt:
            print("🛑 Camera thread interrupted")
            break
        except Exception as e:
            print(f"⚠️ Camera thread error: {e}")
            time.sleep(0.1)  # Brief pause before retrying
    
    print("🎥 Camera thread ended")

# --- START CAMERA THREAD ---
import threading
camera_thread = threading.Thread(target=camera_loop, daemon=True)
camera_thread.start()

# --- START ANIMATION ---
ani = animation.FuncAnimation(fig, update_system, interval=100, blit=False)

print("🚀 Combined Crack Detection and Vibration Monitor Started")
print("📊 Matplotlib window: Vibration monitoring and system status")
print("🎥 OpenCV window: High-speed crack detection camera feed")
print("📱 Press button to silence/re-arm system")
print("❌ Press 'q' in camera window or Ctrl+C to exit")

try:
    plt.show()
except KeyboardInterrupt:
    print("\n🛑 Shutting down...")
finally:
    buzzer.off()
    cam.release()
    vibration_csv_file.close()
    cv2.destroyAllWindows()
    print("✅ System shutdown complete.")