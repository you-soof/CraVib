# CraVib — IoT-Based Structural Health Monitoring System

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![TensorFlow Lite](https://img.shields.io/badge/TFLite-2.x-orange.svg)](https://tensorflow.org/lite)
[![Unity](https://img.shields.io/badge/Unity-2022.3_LTS-black.svg)](https://unity.com)
[![Azure](https://img.shields.io/badge/Azure-Blob_Storage-0089D6.svg)](https://azure.microsoft.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> A real-time, low-cost Structural Health Monitoring system integrating IoT edge computing, computer vision, cloud storage, and a live digital twin — built on a Raspberry Pi 5.

---

## What Is CraVib?

CraVib monitors structural walls for two types of defects:

- **Cracks** — detected in real time using a TensorFlow Lite CNN running on-device via a USB camera
- **Abnormal vibrations** — detected using an ADXL345 3-axis accelerometer with threshold-based alerting

All data is streamed to Microsoft Azure Blob Storage and visualised through a Unity WebGL digital twin that updates the 3D structural model in real time. A companion mobile app (CraVib App) provides remote access to alerts, live plots, and detection history.

The system was developed at the International Hellenic University as part of the Erasmus Mundus SMACCs programme (Smart Cities and Communities).

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PHYSICAL STRUCTURE                       │
│                     (wall specimen / building)                  │
└───────────────────┬──────────────────────┬──────────────────────┘
                    │                      │
              USB Camera              ADXL345 Accelerometer
                    │                      │
                    ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     RASPBERRY PI 5 (Edge)                       │
│                                                                 │
│  ┌─────────────────────┐    ┌───────────────────────────────┐   │
│  │   Crack Detection   │    │    Vibration Monitoring       │   │
│  │                     │    │                               │   │
│  │  OpenCV → preprocess│    │  ADXL345 → X, Y, Z m/s²       │   │
│  │  TFLite CNN → infer │    │  Threshold: 13 m/s²           │   │
│  │  Confidence score   │    │  Anomaly flag if exceeded     │   │
│  │  Crack image saved  │    │  Logged to JSON               │   │
│  └──────────┬──────────┘    └───────────────┬───────────────┘   │
│             │                               │                   │
│             └───────────────┬───────────────┘                   │
│                             │                                   │
│              ┌──────────────▼──────────────┐                    │
│              │      Alert & I/O Layer      │                    │
│              │  Buzzer · LCD display       │                    │
│              │  Button (silence/re-arm)    │                    │
│              └──────────────┬──────────────┘                    │
└─────────────────────────────┼───────────────────────────────────┘
                              │ MQTT / HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   MICROSOFT AZURE BLOB STORAGE                  │
│                                                                 │
│  realtime_vibrations.json   anomaly_vibrations.json             │
│  crack_log.json             images/ (timestamped JPGs)          │
└──────────────────┬──────────────────────────────────────────────┘
                   │                        │
         ┌─────────▼──────────┐   ┌─────────▼───────────┐
         │  Unity WebGL       │   │  CraVib Mobile App  │
         │  Digital Twin      │   │                     │
         │  3D wall model     │   │  Crack alerts       │
         │  Live vibration    │   │  Vibration alerts   │
         │  chart + alerts    │   │  Real-time plots    │
         │  Crack overlays    │   │  Historical data    │
         └────────────────────┘   └─────────────────────┘
```

---

## Repository Structure

```
CraVib/
│
├── README.md                          ← You are here
├── LICENSE
├── .gitignore
│
├── edge/                              ← Raspberry Pi pipeline
│   ├── README.md
│   ├── requirements.txt
│   ├── src/
│   │   ├── main.py                    ← Production entry point (Full_code.py)
│   │   ├── crack_detection.py         ← CNN-only crack detection
│   │   ├── vibration_monitor.py       ← Accelerometer-only monitoring
│   │   ├── combined_detection.py      ← Dual-stream (crack + vibration)
│   │   ├── azure_uploader.py          ← Azure Blob upload utilities
│   │   └── lcd_controller.py          ← LCD 16x2 display driver
│   ├── models/
│   │   └── crack_binary_classifier.tflite   ← Quantised TFLite model
│   ├── logs/
│   │   ├── crack_log_sample.json      ← Example crack detection log
│   │   └── vibration_log_sample.json  ← Example vibration log
│   └── config/
│       └── config.example.py         ← Config template (no credentials)
│
├── ml/                                ← Model training
│   ├── README.md
│   ├── Crack_Detection_CNN.ipynb      ← Training notebook (Keras)
│   └── requirements.txt
│
├── digital-twin/                      ← Unity WebGL digital twin
│   ├── README.md                      ← Detailed DT documentation
│   └── docs/
│       └── screenshots/
│
├── mobile/                            ← CraVib mobile application
│   └── README.md
│
└── docs/
    ├── hardware-setup.md              ← Wiring diagram + component guide
    ├── cloud-setup.md                 ← Azure configuration guide
    ├── architecture.md                ← Full system architecture detail
    └── images/
        └── system_diagram.png
```

---

## Hardware

| Component | Purpose | Notes |
|---|---|---|
| Raspberry Pi 5 | Edge controller | 4GB RAM recommended |
| ADXL345 Accelerometer | Vibration detection | I2C, range: ±16g |
| USB Camera | Image capture for crack detection | 720p minimum |
| LCD1602 Display | On-device status display | 4-bit mode, GPIO |
| Buzzer | Audible alert | GPIO pin 18 |
| Push Button | Silence/re-arm toggle | GPIO pin 17 |
| Breadboard + GPIO ribbon cable | Wiring | See `/docs/hardware-setup.md` |

---

## Detection Approach

### Crack Detection
- Camera captures frames at a configurable interval
- Each frame is converted to grayscale, resized to 128×128, and normalised
- A TensorFlow Lite CNN (binary classifier) runs inference on-device — no cloud round-trip required
- If the confidence score exceeds 0.5, the frame is saved to disk and uploaded to Azure with a timestamp
- Canny edge detection highlights crack regions on the output frame for visual feedback

### Vibration Monitoring
- ADXL345 reads X, Y, Z acceleration in m/s² via I2C
- Readings are logged every 5 seconds to a local JSON file
- If the resultant magnitude exceeds the configured threshold (default: 13 m/s²), an anomaly flag is set and the buzzer is triggered
- Anomalous readings are uploaded to Azure immediately; non-anomalous readings are batched (every 10 readings)

---

## Quickstart

### 1. Clone the repository
```bash
git clone https://github.com/your-username/CraVib.git
cd CraVib/edge
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Azure credentials
```bash
cp config/config.example.py config/config.py
# Edit config/config.py and add your Azure connection string
```

> ⚠️ **Never commit `config.py` to version control.** It is listed in `.gitignore`. Use environment variables in production.

### 4. Run the system
```bash
python src/main.py
```

### 5. View the digital twin
Open the hosted WebGL build in any modern browser. See [`/digital-twin/README.md`](digital-twin/README.md) for deployment instructions.

---

## Dependencies

### Edge (Raspberry Pi)
```
tflite-runtime>=2.13
opencv-python>=4.8
adafruit-circuitpython-adxl34x
gpiozero
azure-storage-blob>=12.0
numpy
matplotlib
```

### ML Training
```
tensorflow>=2.12
keras
numpy
matplotlib
scikit-learn
Pillow
```

---

## Results

| Metric | Value |
|---|---|
| Crack detection accuracy | > 90% on test set |
| Vibration threshold exceedance detection | 100% (threshold-based) |
| End-to-end pipeline latency | ~2–5 seconds (edge → cloud → twin) |
| On-device inference time | ~120ms per frame (TFLite, Pi 5) |
| Integration status | Full pipeline demonstrated |

---

## Limitations

- Vibration detection is threshold-based — no frequency-domain analysis or ML model
- Crack classification is binary (crack / no-crack) — no severity grading
- System validated on a wall specimen only — not yet deployed on real infrastructure
- Azure polling introduces 2–10 second latency in the digital twin

See the [Recommendations section of the project poster](docs/) for the proposed upgrade roadmap.

---

## Authors

**Y. O. Shuaib** — International Hellenic University  
syusuf@ihu.edu.gr

**R. A. Ibrahim** — International Hellenic University  
ribrahim@ihu.edu.gr

Developed as part of the **Erasmus Mundus SMACCs Joint Master's Programme**  
(Smart Cities and Communities · ICT Systems · Smart Energy)

---

## Citation

If you use CraVib in your research or project, please cite:

```bibtex
@misc{cravib2025,
  author = {Shuaib, Y.O. and Ibrahim, R.A.},
  title  = {CraVib: IoT-Digital Twin-Based Crack and Vibration Detection in Structural Walls},
  year   = {2025},
  institution = {International Hellenic University},
  note   = {Erasmus Mundus SMACCs Programme}
}
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
