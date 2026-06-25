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
import signal
import sys
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import queue
from config.config import (
    AZURE_CONNECTION_STRING,
    VIBRATION_THRESHOLD,
    CRACK_THRESHOLD,
    LOG_INTERVAL,
    VIBRATION_UPLOAD_INTERVAL,
    BUZZER_PIN,
    BUTTON_PIN,
    LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7,
    TFLITE_MODEL_PATH,
    IMAGE_SIZE,
    IMAGE_DIR
)

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('system.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# --- CONFIGURATIONS ---
CONFIG = {
    'pins': {'buzzer': BUZZER_PIN, 'button': BUTTON_PIN, 'lcd_rs': LCD_RS, 'lcd_e': LCD_E, 'lcd_d4': LCD_D4, 'lcd_d5': LCD_D5, 'lcd_d6': LCD_D6, 'lcd_d7': LCD_D7},
    'detection': {'img_size': IMAGE_SIZE, 'crack_threshold': CRACK_THRESHOLD, 'vibration_threshold': VIBRATION_THRESHOLD},
    'system': {'log_interval': LOG_INTERVAL, 'window_size': 14, 'image_dir': IMAGE_DIR, 'vibration_upload_interval': VIBRATION_UPLOAD_INTERVAL},
    'files': {'crack_log': "crack_log.json", 'vibration_log': "local_vibration_log.json", 'model': TFLITE_MODEL_PATH},
    'lcd': {'clear': 0x01, 'home': 0x02, 'entry_mode': 0x06, 'display_control': 0x0C, 'function_set': 0x28, 'set_ddram': 0x80},
    'azure': {
        'conn_str': AZURE_CONNECTION_STRING,
        'realtime_vibration_blob': "realtime_vibrations.json",
        'anomaly_vibration_blob': "anomaly_vibrations.json"
    }
}

# --- FUNCTIONAL UTILITIES ---
def safe_execute(func, default=None, log_error=True):
    """Execute function safely with error handling"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if log_error:
                logger.error(f"Error in {func.__name__}: {e}")
            return default
    return wrapper

def create_json_entry(timestamp, **kwargs):
    """Create standardized JSON entry"""
    return {"timestamp": timestamp, **{k: round(v, 3) if isinstance(v, float) else v for k, v in kwargs.items()}}

def write_json_file(file_path, new_entry):
    """Write JSON entry to file"""
    data = []
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            data = json.load(f)
    data.append(new_entry)
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

# --- LCD CONTROLLER (Fixed) ---
class LCDController:
    def __init__(self):
        self.pins = {}
        self.initialized = False
        self.display_queue = queue.Queue()
        self._stop_display_thread = False
        
    def initialize(self):
        """Initialize LCD with improved error handling"""
        try:
            # Initialize pins
            pin_names = ['rs', 'enable', 'd4', 'd5', 'd6', 'd7']
            pin_configs = ['lcd_rs', 'lcd_e', 'lcd_d4', 'lcd_d5', 'lcd_d6', 'lcd_d7']
            
            for name, config_key in zip(pin_names, pin_configs):
                self.pins[name] = OutputDevice(CONFIG['pins'][config_key])
            
            # LCD initialization sequence - Fixed timing
            time.sleep(0.1)  # Increased initial delay
            
            # Reset sequence for 4-bit mode
            for _ in range(3):
                self._write_4bits(0x03)
                time.sleep(0.005)  # Increased delay
            
            self._write_4bits(0x02)  # Set 4-bit mode
            time.sleep(0.005)
            
            # Configure LCD with proper delays
            commands = [
                (CONFIG['lcd']['function_set'], 0.001),    # 2 lines, 5x8 dots
                (CONFIG['lcd']['display_control'], 0.001), # Display on, cursor off
                (CONFIG['lcd']['clear'], 0.002),           # Clear display
                (CONFIG['lcd']['entry_mode'], 0.001)       # Increment cursor
            ]
            
            for cmd, delay in commands:
                self._write_command(cmd)
                time.sleep(delay)
            
            self.initialized = True
            logger.info("LCD initialized successfully")
            
            # Start display thread
            threading.Thread(target=self._display_worker, daemon=True).start()
            self.queue_message("System Starting", "Please wait...", 2)
            return True
            
        except Exception as e:
            logger.error(f"LCD initialization failed: {e}")
            self.cleanup()
            return False
    
    def _write_4bits(self, data):
        """Write 4 bits with proper timing"""
        # Set data bits
        for i, pin in enumerate(['d4', 'd5', 'd6', 'd7']):
            self.pins[pin].value = (data >> i) & 1
        
        # Pulse enable
        self._pulse_enable()
    
    def _pulse_enable(self):
        """Pulse enable pin with proper timing"""
        self.pins['enable'].off()
        time.sleep(0.001)    # Setup time
        self.pins['enable'].on()
        time.sleep(0.001)    # Pulse width
        self.pins['enable'].off()
        time.sleep(0.001)    # Hold time
    
    def _write_command(self, command):
        """Write command with proper setup"""
        if not self.initialized:
            return
        self.pins['rs'].off()  # Command mode
        self._write_byte(command)
        time.sleep(0.002)  # Command execution time
    
    def _write_byte(self, data):
        """Write byte in 4-bit mode"""
        self._write_4bits(data >> 4)    # High nibble
        self._write_4bits(data & 0x0F)  # Low nibble
    
    def _write_char(self, char):
        """Write character data"""
        if not self.initialized:
            return
        self.pins['rs'].on()  # Data mode
        self._write_byte(ord(char))
        time.sleep(0.001)
    
    def _display_text(self, line1, line2=""):
        """Display text with proper cursor positioning - FIXED"""
        if not self.initialized:
            return
        
        # Clear display
        self._write_command(CONFIG['lcd']['clear'])
        time.sleep(0.002)
        
        # Write line 1 - Set cursor to beginning of first line
        self._write_command(0x80)  # DDRAM address 0x00 (first line, first position)
        time.sleep(0.001)
        
        # Pad line1 to exactly 16 characters to ensure proper positioning
        line1_padded = (line1[:16]).ljust(16)
        for char in line1_padded:
            self._write_char(char)
        
        # Write line 2 if provided - Set cursor to beginning of second line
        if line2:
            self._write_command(0xC0)  # DDRAM address 0x40 (second line, first position)
            time.sleep(0.001)
            
            line2_padded = (line2[:16]).ljust(16)
            for char in line2_padded:
                self._write_char(char)
    
    def queue_message(self, line1, line2="", duration=0):
        """Queue message for display (thread-safe)"""
        self.display_queue.put((line1, line2, duration))
    
    def _display_worker(self):
        """Worker thread for LCD display"""
        while not self._stop_display_thread:
            try:
                line1, line2, duration = self.display_queue.get(timeout=1)
                self._display_text(line1, line2)
                logger.info(f"LCD: '{line1}' | '{line2}'")
                
                if duration > 0:
                    time.sleep(duration)
                    if self.display_queue.empty():  # Only clear if no new messages
                        self._write_command(CONFIG['lcd']['clear'])
                        
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"LCD display error: {e}")
    
    def cleanup(self):
        """Cleanup LCD resources"""
        self._stop_display_thread = True
        if self.initialized:
            safe_execute(lambda: self._write_command(CONFIG['lcd']['clear']))()
        
        for pin in self.pins.values():
            safe_execute(pin.close)()
        logger.info("LCD cleanup complete")

# --- SYSTEM STATE (Thread-safe) ---
class SystemState:
    def __init__(self):
        self._state = {'silenced': False, 'running': True, 'alerts': {'crack': False, 'vibration': False}}
        self._lock = threading.Lock()
    
    def update(self, **kwargs):
        """Update state atomically"""
        with self._lock:
            for key, value in kwargs.items():
                if key in self._state:
                    self._state[key] = value
                elif key in self._state['alerts']:
                    self._state['alerts'][key] = value
    
    def get(self, key):
        """Get state value safely"""
        with self._lock:
            return self._state.get(key, self._state['alerts'].get(key))
    
    def should_buzz(self):
        """Check if buzzer should be active"""
        with self._lock:
            return not self._state['silenced'] and any(self._state['alerts'].values())

# --- VIBRATION DATA MANAGER ---
class VibrationDataManager:
    def __init__(self):
        self.realtime_buffer = []
        self.upload_counter = 0
        self.lock = threading.Lock()
    
    def add_reading(self, entry, is_anomaly=False):
        """Add vibration reading to buffer"""
        with self.lock:
            self.realtime_buffer.append(entry)
            self.upload_counter += 1
            
            # Upload real-time data periodically
            if self.upload_counter >= CONFIG['system']['vibration_upload_interval']:
                if 'azure' in resources.components:
                    resources.executor.submit(self.upload_realtime_batch)
                self.upload_counter = 0
            
            # Upload anomaly immediately
            if is_anomaly and 'azure' in resources.components:
                resources.executor.submit(upload_anomaly_vibration_to_azure, entry)
    
    def upload_realtime_batch(self):
        """Upload batch of real-time vibration data to Azure"""
        with self.lock:
            if not self.realtime_buffer:
                return
            
            batch_to_upload = self.realtime_buffer.copy()
            self.realtime_buffer.clear()
        
        try:
            blob_client = resources.components['azure']['vibration'].get_blob_client(
                CONFIG['azure']['realtime_vibration_blob']
            )
            
            # Get existing data
            try:
                existing_data = json.loads(blob_client.download_blob().content_as_text())
            except:
                existing_data = []
            
            existing_data.extend(batch_to_upload)
            blob_client.upload_blob(json.dumps(existing_data, indent=2), overwrite=True)
            logger.info(f"Uploaded {len(batch_to_upload)} real-time vibration readings to Azure")
            
        except Exception as e:
            logger.error(f"Azure real-time vibration upload error: {e}")

# --- RESOURCE MANAGER ---
class ResourceManager:
    def __init__(self):
        self.components = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    def initialize(self):
        """Initialize all resources"""
        try:
            os.makedirs(CONFIG['system']['image_dir'], exist_ok=True)
            
            # Initialize components
            self.components.update({
                'lcd': LCDController(),
                'buzzer': Buzzer(CONFIG['pins']['buzzer']),
                'button': Button(CONFIG['pins']['button']),
                'camera': cv2.VideoCapture(0),
                'accelerometer': adafruit_adxl34x.ADXL345(busio.I2C(board.SCL, board.SDA)),
                'interpreter': tflite.Interpreter(model_path=CONFIG['files']['model'])
            })
            
            # Setup button callback
            self.components['button'].when_pressed = self.toggle_silence
            
            # Initialize TensorFlow Lite
            self.components['interpreter'].allocate_tensors()
            self.input_details = self.components['interpreter'].get_input_details()
            self.output_details = self.components['interpreter'].get_output_details()
            
            # Test camera
            if not self.components['camera'].isOpened() or not self.components['camera'].read()[0]:
                raise IOError("Camera initialization failed")
            
            # Initialize LCD
            if not self.components['lcd'].initialize():
                logger.warning("LCD initialization failed")
            
            # Azure setup
            if CONFIG['azure']['conn_str']:
                blob_client = BlobServiceClient.from_connection_string(CONFIG['azure']['conn_str'])
                self.components['azure'] = {
                    'crack': blob_client.get_container_client("crack"),
                    'vibration': blob_client.get_container_client("vibration")
                }
            
            logger.info("All resources initialized successfully")
            self.components['lcd'].queue_message("System Ready", "Monitoring...")
            return True
            
        except Exception as e:
            logger.error(f"Resource initialization failed: {e}")
            self.cleanup()
            return False
    
    def toggle_silence(self):
        """Toggle system silence state"""
        state.update(silenced=not state.get('silenced'))
        safe_execute(self.components['buzzer'].off)()
        
        status = "SILENCED" if state.get('silenced') else "ACTIVE"
        logger.info(f"System {status}")
        self.components['lcd'].queue_message("System", status, 2)
    
    def manage_buzzer(self):
        """Control buzzer based on system state"""
        if 'buzzer' not in self.components:
            return
        
        action = self.components['buzzer'].on if state.should_buzz() else self.components['buzzer'].off
        safe_execute(action)()
    
    def cleanup(self):
        """Cleanup all resources"""
        logger.info("Cleaning up resources...")
        self.executor.shutdown(wait=False)
        
        cleanup_funcs = [
            lambda: self.components.get('buzzer', {}).off() if 'buzzer' in self.components else None,
            lambda: self.components.get('camera', {}).release() if 'camera' in self.components else None,
            lambda: self.components.get('lcd', {}).cleanup() if 'lcd' in self.components else None
        ]
        
        for cleanup_func in cleanup_funcs:
            safe_execute(cleanup_func)()
        
        for component in self.components.values():
            if hasattr(component, 'close'):
                safe_execute(component.close)()
        
        cv2.destroyAllWindows()
        logger.info("Resource cleanup complete")

# --- MONITORING FUNCTIONS ---
def process_vibration_data():
    """Process accelerometer data with real-time logging"""
    if 'accelerometer' not in resources.components or not state.get('running'):
        return [], [], []
    
    try:
        x, y, z = resources.components['accelerometer'].acceleration
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        
        # Create entry for all readings
        entry = create_json_entry(timestamp, x=x, y=y, z=z)
        
        # Log locally
        safe_execute(lambda: write_json_file(CONFIG['files']['vibration_log'], entry))()
        
        # Check for anomaly
        max_vibration = max(abs(x), abs(y), abs(z))
        is_anomaly = max_vibration > CONFIG['detection']['vibration_threshold']
        state.update(vibration=is_anomaly)
        
        # Add to vibration manager (handles both real-time and anomaly uploads)
        vibration_manager.add_reading(entry, is_anomaly)
        
        if is_anomaly:
            logger.warning(f"VIBRATION ANOMALY! Max: {max_vibration:.2f} m/s²")
            resources.components['lcd'].queue_message("Vibration Alert!", "Anomaly Detected", 3)
        
        return x, y, z
        
    except Exception as e:
        logger.error(f"Vibration processing error: {e}")
        return 0, 0, 0

def process_crack_detection():
    """Process camera frame for crack detection"""
    if 'camera' not in resources.components or not state.get('running'):
        return None, False
    
    try:
        ret, frame = resources.components['camera'].read()
        if not ret:
            return None, False
        
        # Preprocess frame
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (CONFIG['detection']['img_size'], CONFIG['detection']['img_size']))
        normalized = np.expand_dims(resized / 255.0, axis=(0, -1)).astype(np.float32)
        
        # Run inference
        interpreter = resources.components['interpreter']
        interpreter.set_tensor(resources.input_details[0]['index'], normalized)
        interpreter.invoke()
        crack_score = interpreter.get_tensor(resources.output_details[0]['index'])[0][0]
        
        crack_detected = crack_score > CONFIG['detection']['crack_threshold']
        state.update(crack=crack_detected)
        
        if crack_detected:
            handle_crack_detection(frame, crack_score)
        
        add_frame_overlays(frame, crack_detected, crack_score)
        return frame, crack_detected
        
    except Exception as e:
        logger.error(f"Crack detection error: {e}")
        return None, False

def handle_crack_detection(frame, crack_score):
    """Handle crack detection event"""  
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    logger.warning(f"CRACK DETECTED! Score: {crack_score:.3f}")
    
    resources.components['lcd'].queue_message("Crack Detected!", "Saving Image...", 3)
    
    # Save image
    img_path = f"{CONFIG['system']['image_dir']}/crack_{timestamp}.jpg"
    cv2.imwrite(img_path, frame)
    
    # Log entry
    entry = create_json_entry(timestamp, crack_score=crack_score, image=img_path)
    safe_execute(lambda: write_json_file(CONFIG['files']['crack_log'], entry))()
    
    # Upload to Azure asynchronously (only anomaly cracks)
    if 'azure' in resources.components:
        resources.executor.submit(upload_crack_to_azure, img_path)

def add_frame_overlays(frame, crack_detected, crack_score):
    """Add overlays to camera frame"""
    label = f"{'CRACK DETECTED' if crack_detected else 'NO CRACK'} ({crack_score:.2f})"
    color = (0, 0, 255) if crack_detected else (0, 255, 0)
    
    status = "SILENCED" if state.get('silenced') else "ACTIVE"
    status_color = (0, 165, 255) if state.get('silenced') else (255, 255, 255)
    
    overlays = [
        (label, (10, 30), 1, color, 2),
        (f"System: {status}", (10, 70), 0.7, status_color, 2),
        (f"Threshold: {CONFIG['detection']['crack_threshold']}", (10, frame.shape[0] - 50), 0.5, (255, 255, 255), 1),
        ("Press 'q' to quit", (10, frame.shape[0] - 20), 0.5, (255, 255, 255), 1)
    ]
    
    for text, pos, scale, color, thickness in overlays:
        cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)

# --- AZURE UPLOAD FUNCTIONS ---
def upload_anomaly_vibration_to_azure(entry):
    """Upload anomaly vibration data to Azure"""
    if 'azure' not in resources.components:
        return
    
    try:
        blob_client = resources.components['azure']['vibration'].get_blob_client(
            CONFIG['azure']['anomaly_vibration_blob']
        )
        
        # Get existing anomaly data
        try:
            existing_data = json.loads(blob_client.download_blob().content_as_text())
        except:
            existing_data = []
        
        existing_data.append(entry)
        blob_client.upload_blob(json.dumps(existing_data, indent=2), overwrite=True)
        logger.info("Vibration anomaly uploaded to Azure")
        
    except Exception as e:
        logger.error(f"Azure anomaly vibration upload error: {e}")

def upload_crack_to_azure(img_path):
    """Upload crack image to Azure"""
    if 'azure' not in resources.components:
        return
    
    try:
        with open(img_path, "rb") as data:
            resources.components['azure']['crack'].upload_blob(
                name=os.path.basename(img_path), data=data, overwrite=True
            )
        logger.info(f"Crack image uploaded to Azure: {os.path.basename(img_path)}")
        
    except Exception as e:
        logger.error(f"Azure crack upload error: {e}")

# --- CLEANUP FUNCTIONS ---
def clear_logs():
    """Clear all local and Azure logs"""
    logger.info("🧹 Clearing all previous logs...")
    
    # Clear local files
    for log_file in [CONFIG['files']['crack_log'], CONFIG['files']['vibration_log']]:
        safe_execute(lambda f=log_file: os.remove(f) if os.path.exists(f) else None)()
    
    # Clear images
    if os.path.exists(CONFIG['system']['image_dir']):
        for filename in os.listdir(CONFIG['system']['image_dir']):
            safe_execute(lambda f=filename: os.remove(os.path.join(CONFIG['system']['image_dir'], f)))()
    
    # Clear Azure (if available)
    if 'azure' in resources.components:
        for container_name in ['crack', 'vibration']:
            container = resources.components['azure'][container_name]
            for blob in safe_execute(lambda: list(container.list_blobs()), default=[])():
                safe_execute(lambda b=blob: container.delete_blob(b.name))()
    
    logger.info("✅ All previous logs cleared")

# --- MAIN APPLICATION ---
class VibrationMonitor:
    def __init__(self):
        self.data = {'x': [], 'y': [], 'z': []}
    
    def update(self, frame):
        x, y, z = process_vibration_data()
        
        for axis, value in zip(['x', 'y', 'z'], [x, y, z]):
            self.data[axis].append(value)
            if len(self.data[axis]) > CONFIG['system']['window_size']:
                self.data[axis] = self.data[axis][-CONFIG['system']['window_size']:]
        
        resources.manage_buzzer()
        return [(range(len(self.data[axis])), self.data[axis]) for axis in ['x', 'y', 'z']]

def camera_loop():
    """Camera processing loop with proper window initialization"""
    logger.info("Initializing camera window...")
    
    # Create and configure the camera window
    window_name = "Live Crack Detection Feed"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 800, 600)
    
    # Move window to a visible position
    cv2.moveWindow(window_name, 100, 100)
    
    logger.info("Starting camera feed...")
    time.sleep(1)
    
    while state.get('running'):
        try:
            frame, _ = process_crack_detection()
            if frame is not None:
                # Display the frame
                cv2.imshow(window_name, frame)
                
                # Check for 'q' key press to quit
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    logger.info("Camera window 'q' pressed - shutting down")
                    state.update(running=False)
                    break
            else:
                # If no frame, wait a bit before trying again
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Camera thread error: {e}")
            time.sleep(0.1)
    
    # Cleanup camera window
    cv2.destroyWindow(window_name)
    logger.info("Camera window closed")

def setup_plot():
    """Setup vibration monitoring plot"""
    fig, ax = plt.subplots(figsize=(12, 8))
    lines = [ax.plot([], [], label=label, color=color)[0] 
             for label, color in [('X', 'red'), ('Y', 'green'), ('Z', 'blue')]]
    
    ax.set_ylim(-2, 15)
    ax.set_xlim(0, CONFIG['system']['window_size'])
    ax.set_title('Live Vibration Monitor (m/s²)')
    ax.set_xlabel('Samples')
    ax.set_ylabel('Acceleration')
    ax.legend()
    ax.grid(True)
    
    def update_plot(frame_num):
        if not state.get('running'):
            return lines
        
        data_sets = vibration_monitor.update(frame_num)
        for line, (x_range, y_data) in zip(lines, data_sets):
            line.set_data(x_range, y_data)
            if len(y_data) > 0:
                ax.set_xlim(max(0, len(y_data) - CONFIG['system']['window_size']), 
                          max(CONFIG['system']['window_size'], len(y_data)))
        return lines
    
    return fig, update_plot

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Shutdown signal received")
    state.update(running=False)

def main():
    """Main execution function"""
    global resources, state, vibration_monitor, vibration_manager
    
    # Initialize global objects
    resources = ResourceManager()
    state = SystemState()
    vibration_monitor = VibrationMonitor()
    vibration_manager = VibrationDataManager()
    
    # Setup signal handling
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Initializing Combined Crack Detection and Vibration Monitor...")
    
    if not resources.initialize():
        logger.error("Failed to initialize system")
        return 1
    
    clear_logs()
    
    try:
        # Start camera thread
        camera_thread = threading.Thread(target=camera_loop, daemon=True)
        camera_thread.start()
        
        # Give camera thread time to initialize window
        time.sleep(2)
        
        # Setup and start plot
        fig, update_func = setup_plot()
        ani = animation.FuncAnimation(fig, update_func, interval=100, blit=False)
        
        logger.info("🚀 System Started Successfully")
        logger.info("📊 Real-time vibration logging every 10 readings")
        logger.info("🚨 Anomaly vibration and crack photos logged immediately")
        logger.info("🖥️ LCD: Fixed text positioning | 📱 Button: silence/re-arm | ❌ 'q' or Ctrl+C: exit")
        logger.info("📹 Camera window should now be visible")
        
        plt.show()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        state.update(running=False)
        
        if 'camera_thread' in locals():
            camera_thread.join(timeout=2)
        
        resources.components['lcd'].queue_message("System", "Shutting Down...", 2)
        time.sleep(2)
        resources.cleanup()
        logger.info("System shutdown complete")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())