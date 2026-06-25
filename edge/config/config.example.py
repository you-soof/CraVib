# CraVib Configuration Template
# Copy this file to config.py and fill in your values
# Never commit config.py to version control

# Azure Blob Storage
AZURE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=YOUR_ACCOUNT_NAME;AccountKey=YOUR_ACCOUNT_KEY;EndpointSuffix=core.windows.net"

# Detection thresholds
VIBRATION_THRESHOLD = 13       # m/s² — adjust based on your structure
CRACK_THRESHOLD = 0.5          # CNN confidence score (0.0 – 1.0)

# Logging
LOG_INTERVAL = 5               # seconds between vibration readings
VIBRATION_UPLOAD_INTERVAL = 10 # batch size before uploading to Azure

# GPIO pin assignments (Raspberry Pi)
BUZZER_PIN = 18
BUTTON_PIN = 17
LCD_RS = 26
LCD_E  = 19
LCD_D4 = 13
LCD_D5 = 6
LCD_D6 = 5
LCD_D7 = 22

# Model
TFLITE_MODEL_PATH = "models/crack_binary_classifier.tflite"
IMAGE_SIZE = 128               # pixels — must match training dimensions
IMAGE_DIR  = "images"          # local directory for captured crack images