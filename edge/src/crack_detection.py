import cv2
import numpy as np
import tflite_runtime.interpreter as tflite
from gpiozero import Buzzer
import time
import os
import csv
from datetime import datetime

# --- CONFIG ---
BUZZER_PIN = 18
IMG_SIZE = 128
THRESHOLD = 0.5  # Minimum confidence score to classify as crack
IMAGE_DIR = "images"
LOG_FILE = "crack_log.csv"

# --- SETUP ---
os.makedirs(IMAGE_DIR, exist_ok=True)

# Initialize buzzer
buzzer = Buzzer(BUZZER_PIN)

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

finally:
    cam.release()
    buzzer.off()
    cv2.destroyAllWindows()
    print("Detection stopped.")
