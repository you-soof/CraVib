import cv2
import numpy as np
import tflite_runtime.interpreter as tflite
from gpiozero import Buzzer, Button, OutputDevice
import time
import threading
from azure.storage.blob import BlobServiceClient
import os
import json
import board
import busio
import adafruit_adxl34x
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from datetime import datetime
import logging
from contextlib import contextmanager
import signal
import sys
import os

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- CONFIGURATIONS ---
from config.config import (
    AZURE_CONNECTION_STRING,
    VIBRATION_THRESHOLD,
    CRACK_THRESHOLD,
    LOG_INTERVAL,
    BUZZER_PIN,
    BUTTON_PIN,
    LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7,
    IMAGE_SIZE,
    IMAGE_DIR
)

# Local aliases — keep these so the rest of the file works unchanged
AZURE_CONN_STR = AZURE_CONNECTION_STRING
IMG_SIZE = IMAGE_SIZE

# LCD Commands (hardware constants — not user-configurable)
LCD_CLEAR = 0x01
LCD_HOME = 0x02
LCD_ENTRY_MODE = 0x06
LCD_DISPLAY_CONTROL = 0x0C
LCD_FUNCTION_SET = 0x28
LCD_SET_DDRAM = 0x80

# File-specific constants
VIBRATION_BLOB_NAME = "anomaly_vibrations.json"
CRACK_LOG_FILE = "crack_log.json"
VIBRATION_LOG_FILE = "local_vibration_log.json"
WINDOW_SIZE = 14


# --- LCD CONTROLLER CLASS ---
class LCDController:
    def __init__(self):
        self.rs = None
        self.enable = None
        self.d4 = None
        self.d5 = None
        self.d6 = None
        self.d7 = None
        self.backlight = None
        self.initialized = False
        
    def initialize(self):
        """Initialize LCD pins and setup"""
        try:
            # Initialize GPIO pins
            self.rs = OutputDevice(LCD_RS)
            self.enable = OutputDevice(LCD_E)
            self.d4 = OutputDevice(LCD_D4)
            self.d5 = OutputDevice(LCD_D5)
            self.d6 = OutputDevice(LCD_D6)
            self.d7 = OutputDevice(LCD_D7)
            
            
            # Initialize LCD in 4-bit mode
            time.sleep(0.05)  # Wait for LCD to power up
            
            # Initial setup sequence for 4-bit mode
            self._write_4bits(0x03)
            time.sleep(0.0041)
            self._write_4bits(0x03)
            time.sleep(0.001)
            self._write_4bits(0x03)
            time.sleep(0.001)
            self._write_4bits(0x02)  # Set to 4-bit mode
            
            # Configure LCD
            self._write_command(LCD_FUNCTION_SET)  # 4-bit, 2 lines, 5x8 font
            self._write_command(LCD_DISPLAY_CONTROL)  # Display on, cursor off, blink off
            self._write_command(LCD_CLEAR)  # Clear display
            time.sleep(0.002)
            self._write_command(LCD_ENTRY_MODE)  # Increment cursor, no shift
            
            self.initialized = True
            logger.info("LCD initialized successfully")
            
            # Display startup message
            self.display_message("System Starting", "Please wait...")
            time.sleep(2)
            self.clear()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize LCD: {e}")
            self.cleanup()
            return False
    
    def _pulse_enable(self):
        """Pulse the enable pin"""
        self.enable.off()
        time.sleep(0.001)
        self.enable.on()
        time.sleep(0.001)
        self.enable.off()
        time.sleep(0.001)
    
    def _write_4bits(self, data):
        """Write 4 bits to LCD"""
        self.d4.value = (data >> 0) & 1
        self.d5.value = (data >> 1) & 1
        self.d6.value = (data >> 2) & 1
        self.d7.value = (data >> 3) & 1
        self._pulse_enable()
    
    def _write_byte(self, data):
        """Write a byte to LCD in 4-bit mode"""
        self._write_4bits(data >> 4)  # High nibble
        self._write_4bits(data & 0x0F)  # Low nibble
    
    def _write_command(self, command):
        """Write command to LCD"""
        if not self.initialized:
            return
        self.rs.off()  # Command mode
        self._write_byte(command)
        time.sleep(0.002)
    
    def _write_data(self, data):
        """Write data to LCD"""
        if not self.initialized:
            return
        self.rs.on()  # Data mode
        self._write_byte(data)
        time.sleep(0.005)
    
    def clear(self):
        """Clear LCD display"""
        if not self.initialized:
            return
        self._write_command(LCD_CLEAR)
        time.sleep(0.002)
    
    def set_cursor(self, row, col):
        """Set cursor position (row: 0-1, col: 0-15)"""
        if not self.initialized:
            return
        if row == 0:
            address = 0x80 + col
        else:
            address = 0xC0 + col
        self._write_command(address)
    
    def write_string(self, text):
        """Write string to LCD at current cursor position"""
        if not self.initialized:
            return
        for char in text:
            self._write_data(ord(char))
    
    def display_message(self, line1, line2=""):
        """Display message on LCD (2 lines)"""
        if not self.initialized:
            return
        
        try:
            self.clear()
            
            # Line 1
            self.set_cursor(0, 0)
            # Truncate to 16 characters
            line1 = line1[:16]
            self.write_string(line1)
            
            # Line 2
            if line2:
                self.set_cursor(1, 0)
                line2 = line2[:16]
                self.write_string(line2)
                
            logger.info(f"LCD Display: '{line1}' | '{line2}'")
            
        except Exception as e:
            logger.error(f"LCD display error: {e}")
    
    def display_timed_message(self, line1, line2="", duration=3):
        """Display message for specified duration then clear"""
        if not self.initialized:
            return
        
        self.display_message(line1, line2)
        
        def clear_after_delay():
            time.sleep(duration)
            if self.initialized:
                self.clear()
        
        threading.Thread(target=clear_after_delay, daemon=True).start()
    
    def cleanup(self):
        """Clean up LCD resources"""
        try:
            if self.initialized:
                self.clear()
                if self.backlight:
                    self.backlight.off()
            
            # Close all GPIO pins
            for pin in [self.rs, self.enable, self.d4, self.d5, self.d6, self.d7, self.backlight]:
                if pin:
                    pin.close()
                    
            logger.info("LCD cleanup complete")
            
        except Exception as e:
            logger.error(f"LCD cleanup error: {e}")

# --- GLOBAL STATE ---
class SystemState:
    def __init__(self):
        self.silenced = False
        self.running = True
        self.crack_alert = False
        self.vibration_alert = False
        self.lock = threading.Lock()
    
    def set_silenced(self, value):
        with self.lock:
            self.silenced = value
    
    def is_silenced(self):
        with self.lock:
            return self.silenced
    
    def set_alerts(self, crack=None, vibration=None):
        with self.lock:
            if crack is not None:
                self.crack_alert = crack
            if vibration is not None:
                self.vibration_alert = vibration
    
    def should_buzz(self):
        with self.lock:
            return not self.silenced and (self.crack_alert or self.vibration_alert)
    
    def stop(self):
        with self.lock:
            self.running = False
    
    def is_running(self):
        with self.lock:
            return self.running

system_state = SystemState()

# --- RESOURCE MANAGEMENT ---
class ResourceManager:
    def __init__(self):
        self.buzzer = None
        self.button = None
        self.cam = None
        self.accelerometer = None
        self.blob_service_client = None
        self.crack_container_client = None
        self.vibration_container_client = None
        self.lcd = LCDController()
        
    def initialize(self):
        """Initialize all resources with proper error handling"""
        try:
            # Setup directories
            os.makedirs(IMAGE_DIR, exist_ok=True)
            
            # Initialize LCD first
            if not self.lcd.initialize():
                logger.warning("LCD initialization failed, continuing without LCD")
            
            # GPIO Setup
            self.buzzer = Buzzer(BUZZER_PIN)
            self.button = Button(BUTTON_PIN)
            self.button.when_pressed = self.handle_button_press
            
            # Accelerometer setup
            i2c = busio.I2C(board.SCL, board.SDA)
            self.accelerometer = adafruit_adxl34x.ADXL345(i2c)
            
            # Camera setup
            self.cam = cv2.VideoCapture(0)
            if not self.cam.isOpened():
                raise IOError("Cannot open webcam")
            
            # Test camera
            ret, _ = self.cam.read()
            if not ret:
                raise IOError("Cannot read from webcam")
            
            # Azure setup
            if AZURE_CONN_STR:
                self.blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONN_STR)
                self.crack_container_client = self.blob_service_client.get_container_client("crack")
                self.vibration_container_client = self.blob_service_client.get_container_client("vibration")
                logger.info("Azure storage clients initialized")
            
            # Load and test TensorFlow Lite model
            if not os.path.exists("crack_binary_classifier.tflite"):
                raise FileNotFoundError("TensorFlow Lite model file not found")
            
            self.interpreter = tflite.Interpreter(model_path="crack_binary_classifier.tflite")
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            
            logger.info("All resources initialized successfully")
            
            # Display ready message on LCD
            self.lcd.display_message("System Ready", "Monitoring...")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize resources: {e}")
            self.cleanup()
            return False
    
    def handle_button_press(self):
        """Handle button press to toggle system state"""
        system_state.set_silenced(not system_state.is_silenced())
        
        # Always turn off buzzer immediately when button is pressed
        if self.buzzer:
            try:
                self.buzzer.off()
            except Exception as e:
                logger.error(f"Error turning off buzzer: {e}")
        
        if system_state.is_silenced():
            logger.info("System silenced by button press")
            self.lcd.display_timed_message("System", "SILENCED", 2)
        else:
            logger.info("System re-armed")
            self.lcd.display_timed_message("System", "ACTIVE", 2)
    
    def manage_buzzer(self):
        """Centralized buzzer management"""
        if not self.buzzer:
            return
            
        try:
            if system_state.should_buzz():
                self.buzzer.on()
            else:
                self.buzzer.off()
        except Exception as e:
            logger.error(f"Buzzer control error: {e}")
    
    def cleanup(self):
        """Clean up all resources"""
        logger.info("Cleaning up resources...")
        
        if self.buzzer:
            try:
                self.buzzer.off()
                self.buzzer.close()
            except Exception as e:
                logger.error(f"Error cleaning up buzzer: {e}")
        
        if self.button:
            try:
                self.button.close()
            except Exception as e:
                logger.error(f"Error cleaning up button: {e}")
        
        if self.cam:
            try:
                self.cam.release()
            except Exception as e:
                logger.error(f"Error cleaning up camera: {e}")
        
        # Cleanup LCD
        self.lcd.cleanup()
        
        cv2.destroyAllWindows()
        logger.info("Resource cleanup complete")

resources = ResourceManager()

# --- CLEANUP FUNCTIONS ---
def clear_local_logs():
    """Clear all local log files and images"""
    try:
        # Clear JSON log files
        for log_file in [CRACK_LOG_FILE, VIBRATION_LOG_FILE]:
            if os.path.exists(log_file):
                os.remove(log_file)
                logger.info(f"Deleted local log file: {log_file}")
        
        # Clear image directory
        if os.path.exists(IMAGE_DIR):
            for filename in os.listdir(IMAGE_DIR):
                file_path = os.path.join(IMAGE_DIR, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted image file: {filename}")
        
        logger.info("Local logs cleared successfully")
        
    except Exception as e:
        logger.error(f"Error clearing local logs: {e}")

def clear_azure_logs():
    """Clear all Azure blob storage logs"""
    if not resources.blob_service_client:
        logger.warning("Azure not configured, skipping Azure log cleanup")
        return
    
    try:
        # Clear crack detection images
        if resources.crack_container_client:
            try:
                blob_list = resources.crack_container_client.list_blobs()
                for blob in blob_list:
                    resources.crack_container_client.delete_blob(blob.name)
                    logger.info(f"Deleted Azure crack blob: {blob.name}")
                logger.info("Azure crack container cleared")
            except Exception as e:
                logger.error(f"Error clearing crack container: {e}")
        
        # Clear vibration logs
        if resources.vibration_container_client:
            try:
                blob_list = resources.vibration_container_client.list_blobs()
                for blob in blob_list:
                    resources.vibration_container_client.delete_blob(blob.name)
                    logger.info(f"Deleted Azure vibration blob: {blob.name}")
                logger.info("Azure vibration container cleared")
            except Exception as e:
                logger.error(f"Error clearing vibration container: {e}")
        
        logger.info("Azure logs cleared successfully")
        
    except Exception as e:
        logger.error(f"Error clearing Azure logs: {e}")

def clear_all_previous_logs():
    """Clear all previous logs (local and Azure) before starting new session"""
    logger.info("🧹 Clearing all previous logs...")
    clear_local_logs()
    clear_azure_logs()
    logger.info("✅ All previous logs cleared")

# --- UTILITY FUNCTIONS ---
def upload_file_to_azure(container_client, blob_name, file_path):
    """Upload file to Azure with error handling"""
    if not container_client:
        logger.warning("Azure container client not available")
        return
        
    try:
        with open(file_path, "rb") as data:
            container_client.upload_blob(name=blob_name, data=data, overwrite=True)
            logger.info(f"Uploaded to Azure: {blob_name}")
    except Exception as e:
        logger.error(f"Azure upload error: {e}")

def append_json_to_file(json_path, new_entry):
    """Append entry to JSON file with error handling"""
    try:
        if os.path.exists(json_path):
            with open(json_path, "r") as f:
                data = json.load(f)
        else:
            data = []
        data.append(new_entry)
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error writing to {json_path}: {e}")

def append_vibration_log_to_azure_json(new_entry_dict):
    """Append vibration data to Azure JSON blob"""
    if not resources.vibration_container_client:
        return
        
    try:
        blob_client = resources.vibration_container_client.get_blob_client(VIBRATION_BLOB_NAME)
        try:
            existing_blob = blob_client.download_blob().content_as_text()
            data = json.loads(existing_blob) if existing_blob.strip() else []
        except:
            data = []
        data.append(new_entry_dict)
        blob_client.upload_blob(json.dumps(data, indent=2), overwrite=True)
        logger.info("Vibration anomaly appended to Azure JSON blob")
    except Exception as e:
        logger.error(f"Failed to upload JSON to Azure: {e}")

# --- MONITORING CLASSES ---
class VibrationMonitor:
    def __init__(self):
        self.x_data = []
        self.y_data = []
        self.z_data = []
        self.last_log_time = 0
    
    def update(self, frame):
        """Update vibration monitoring"""
        if not resources.accelerometer or not system_state.is_running():
            return self.get_plot_data()
        
        try:
            # Get accelerometer data
            x, y, z = resources.accelerometer.acceleration
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            
            # Update data arrays
            self.x_data.append(x)
            self.y_data.append(y)
            self.z_data.append(z)
            
            vib_entry = {
                    "timestamp": timestamp,
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "z": round(z, 2),
                }
            append_json_to_file(VIBRATION_LOG_FILE, vib_entry)
            threading.Thread(
                target=append_vibration_log_to_azure_json, 
                args=(vib_entry,), 
                daemon=True
            ).start()
            
            # Maintain window size
            if len(self.x_data) > WINDOW_SIZE:
                self.x_data = self.x_data[-WINDOW_SIZE:]
                self.y_data = self.y_data[-WINDOW_SIZE:]
                self.z_data = self.z_data[-WINDOW_SIZE:]
            
            # Check for vibration threshold
            max_vibration = max(abs(x), abs(y), abs(z))
            vibration_alert = max_vibration > VIBRATION_THRESHOLD
            
            # Update system state
            system_state.set_alerts(vibration=vibration_alert)
            
            # Log vibration events (throttled)
            current_time = time.time()
            if vibration_alert and (current_time - self.last_log_time) >= LOG_INTERVAL:
                self.last_log_time = current_time
                logger.warning(f"VIBRATION ALERT! Max: {max_vibration:.2f} m/s²")
                
                # Display on LCD
                resources.lcd.display_timed_message(
                    "Vibration Alert!", 
                    "Sent to Azure", 
                    5
                )
                

            
            # Manage buzzer
            resources.manage_buzzer()
            
        except Exception as e:
            logger.error(f"Vibration monitoring error: {e}")
        
        return self.get_plot_data()
    
    def get_plot_data(self):
        """Return data for plotting"""
        return (
            (range(len(self.x_data)), self.x_data),
            (range(len(self.y_data)), self.y_data),
            (range(len(self.z_data)), self.z_data)
        )

class CrackDetector:
    def __init__(self):
        self.last_detection_time = 0
    
    def process_frame(self):
        """Process camera frame for crack detection"""
        if not resources.cam or not system_state.is_running():
            return None, False
        
        try:
            ret, frame = resources.cam.read()
            if not ret:
                logger.warning("Camera read failed")
                return None, False
            
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            
            # Preprocess for crack detection model
            gray_model = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray_model, (IMG_SIZE, IMG_SIZE))
            normalized = resized / 255.0
            input_data = np.expand_dims(normalized, axis=(0, -1)).astype(np.float32)
            
            # Run crack detection inference
            resources.interpreter.set_tensor(resources.input_details[0]['index'], input_data)
            resources.interpreter.invoke()
            crack_score = resources.interpreter.get_tensor(resources.output_details[0]['index'])[0][0]
            crack_detected = crack_score > CRACK_THRESHOLD
            
            # Update system state
            system_state.set_alerts(crack=crack_detected)
            
            # Process crack detection
            if crack_detected:
                self._handle_crack_detection(frame, crack_score, timestamp)
            
            # Add overlays to frame
            self._add_overlays(frame, crack_detected, crack_score)
            
            # Manage buzzer
            resources.manage_buzzer()
            
            return frame, crack_detected
            
        except Exception as e:
            logger.error(f"Crack detection error: {e}")
            return None, False
    
    def _handle_crack_detection(self, frame, crack_score, timestamp):
        """Handle crack detection event"""
        current_time = time.time()
        if (current_time - self.last_detection_time) < LOG_INTERVAL:
            return  # Throttle logging
        
        self.last_detection_time = current_time
        logger.warning(f"CRACK DETECTED! Score: {crack_score:.3f}")
        
        # Display on LCD
        resources.lcd.display_timed_message(
            "Crack Detected!", 
            "Sent to Azure", 
            5
        )
        
        # Highlight crack regions
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
        
        # Save crack image and log
        try:
            crack_img_filename = f"{IMAGE_DIR}/crack_{timestamp}.jpg"
            cv2.imwrite(crack_img_filename, frame)
            
            crack_entry = {
                "timestamp": timestamp,
                "crack_score": round(crack_score, 3),
                "image": crack_img_filename
            }
            append_json_to_file(CRACK_LOG_FILE, crack_entry)
            
            # Upload to Azure in background
            threading.Thread(
                target=upload_file_to_azure,
                args=(resources.crack_container_client, os.path.basename(crack_img_filename), crack_img_filename),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"Error saving crack data: {e}")
    
    def _add_overlays(self, frame, crack_detected, crack_score):
        """Add text overlays to frame"""
        label = f"{'CRACK DETECTED' if crack_detected else 'NO CRACK'} ({crack_score:.2f})"
        color = (0, 0, 255) if crack_detected else (0, 255, 0)
        
        system_status = "SILENCED" if system_state.is_silenced() else "ACTIVE"
        status_color = (0, 165, 255) if system_state.is_silenced() else (255, 255, 255)
        
        cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        cv2.putText(frame, f"System: {system_status}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        cv2.putText(frame, f"Threshold: {CRACK_THRESHOLD}", (10, frame.shape[0] - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "Press 'q' to quit", (10, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

# --- PLOTTING SETUP ---
vibration_monitor = VibrationMonitor()
crack_detector = CrackDetector()

# Fixed subplot creation
fig, ax1 = plt.subplots(figsize=(12, 8))

# Vibration plot setup
line_x, = ax1.plot([], [], label='X', color='red')
line_y, = ax1.plot([], [], label='Y', color='green') 
line_z, = ax1.plot([], [], label='Z', color='blue')
ax1.set_ylim(-2, 15)
ax1.set_xlim(0, WINDOW_SIZE)
ax1.set_title('Live Vibration Monitor (m/s²)')
ax1.set_xlabel('Samples')
ax1.set_ylabel('Acceleration')
ax1.legend()
ax1.grid(True)

def update_plot(frame):
    """Update the vibration plot"""
    if not system_state.is_running():
        return line_x, line_y, line_z
    
    # Get vibration data
    (x_range, x_data), (y_range, y_data), (z_range, z_data) = vibration_monitor.update(frame)
    
    # Update plot lines
    line_x.set_data(x_range, x_data)
    line_y.set_data(y_range, y_data)
    line_z.set_data(z_range, z_data)
    
    # Update x-axis limits
    if len(x_data) > 0:
        ax1.set_xlim(max(0, len(x_data) - WINDOW_SIZE), max(WINDOW_SIZE, len(x_data)))
    
    return line_x, line_y, line_z

# --- CAMERA PROCESSING THREAD ---
def camera_loop():
    """Camera processing loop running in separate thread"""
    logger.info("Starting camera feed...")
    
    # Small delay to ensure camera is ready
    time.sleep(1)
    
    while system_state.is_running():
        try:
            frame, crack_detected = crack_detector.process_frame()
            
            if frame is not None:
                # Display the frame
                cv2.imshow("Live Crack Detection Feed", frame)
                
                # Check for quit command (non-blocking)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    logger.info("Camera feed stopped by user")
                    system_state.stop()
                    break
            else:
                time.sleep(0.1)  # Brief pause if frame processing failed
                
        except KeyboardInterrupt:
            logger.info("Camera thread interrupted")
            system_state.stop()
            break
        except Exception as e:
            logger.error(f"Camera thread error: {e}")
            time.sleep(0.1)
    
    logger.info("Camera thread ended")

# --- SIGNAL HANDLING ---
def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Shutdown signal received")
    system_state.stop()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# --- MAIN EXECUTION ---
def main():
    """Main execution function"""
    logger.info("Initializing Combined Crack Detection and Vibration Monitor...")
    
    # Initialize resources
    if not resources.initialize():
        logger.error("Failed to initialize system")
        return 1
    
    # Clear all previous logs before starting
    clear_all_previous_logs()
    
    try:
        # Start camera thread
        camera_thread = threading.Thread(target=camera_loop, daemon=True)
        camera_thread.start()
        
        # Start animation
        ani = animation.FuncAnimation(fig, update_plot, interval=100, blit=False)
        
        logger.info("🚀 System Started Successfully")
        logger.info("📊 Matplotlib window: Vibration monitoring")
        logger.info("🎥 OpenCV window: Crack detection camera feed")
        logger.info("🖥️  LCD Display: Real-time alerts and status")
        logger.info("📱 Press button to silence/re-arm system")
        logger.info("❌ Press 'q' in camera window or Ctrl+C to exit")
        
        # Show plot (this blocks until window is closed)
        plt.show()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        system_state.stop()
        
        # Wait for camera thread to finish
        if 'camera_thread' in locals():
            camera_thread.join(timeout=2)
        
        # Display shutdown message on LCD
        resources.lcd.display_message("System", "Shutting Down...")
        time.sleep(2)
        
        # Cleanup resources
        resources.cleanup()
        logger.info("System shutdown complete")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
