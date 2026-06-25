# CraVib — Digital Twin Platform

> A Unity WebGL digital twin synchronised with live Azure Blob Storage data — visualising structural crack detection and vibration anomalies in real time.

---

## Overview

The CraVib Digital Twin is the visualisation and decision-support layer of the CraVib SHM system. It maintains a continuously updated 3D replica of a monitored physical structure (a wall specimen) and reflects its current structural health state in real time.

Two data streams feed the twin:

- **Vibration data** — JSON uploaded to Azure Blob Storage by the Raspberry Pi edge device, polled on a configurable interval
- **Crack images** — JPEG files uploaded to Azure when a crack is detected; the twin probes for their existence by constructing timestamp-based URLs

When anomalies are detected, the 3D wall model changes material, physically animates, and an alert light flashes. A 2D UI panel shows live vibration readings, a scrollable crack log, and Acknowledge/Silence controls.

The platform is built in Unity and exported as WebGL — accessible through any modern browser without a native installation.

---

## Architecture

```
Physical Structure (wall specimen)
         │
         ▼
 ┌───────────────────────────────────┐
 │       Raspberry Pi 5 (Edge)       │
 │  ┌──────────────────────────────┐ │
 │  │  Vibration stream            │ │     ┌────────────────────────────┐
 │  │  ADXL345 → X, Y, Z m/s²     │─┼────▶│  realtime_vibrations.json  │
 │  │  Uploaded every N readings   │ │     │  anomaly_vibrations.json   │
 │  └──────────────────────────────┘ │     │  (Azure Blob Storage)      │
 │  ┌──────────────────────────────┐ │     │                            │
 │  │  Crack detection             │ │     │  crack_{timestamp}.jpg     │
 │  │  CNN → confidence score      │─┼────▶│  (Azure Blob — /crack/)    │
 │  │  Uploaded if crack detected  │ │     └────────────┬───────────────┘
 │  └──────────────────────────────┘ │                  │
 └───────────────────────────────────┘                  │ HTTP GET polling
                                                        ▼
                              ┌─────────────────────────────────────────┐
                              │         Unity WebGL Digital Twin         │
                              │                                          │
                              │  SHMManager.cs                          │
                              │  ├── UpdateLoop() — polls Azure          │
                              │  ├── FetchVibration() / FetchCurrentVibration()
                              │  ├── FetchCurrentCracks()                │
                              │  └── ProcessVibrationData()              │
                              │         │ fires SHMEvents                │
                              │         ▼                                │
                              │  SHMEvents.cs (event bus)               │
                              │  ├── OnVibrationDataReceived             │
                              │  ├── OnCrackDataReceived                 │
                              │  ├── OnDataError                        │
                              │  ├── OnSilenceToggled                   │
                              │  └── OnAlertAcknowledged                │
                              │         │ subscribed by                  │
                              │         ▼                                │
                              │  CrackDetectionUI.cs                    │
                              │  ├── Vibration status display            │
                              │  ├── Scrollable crack log               │
                              │  ├── Crack image popup (loaded from URL) │
                              │  ├── Status indicator (colour)           │
                              │  └── Acknowledge / Silence buttons       │
                              └─────────────────────────────────────────┘
```

---

## Scripts

### `SHMManager.cs`
The scene orchestrator. Runs a continuous `UpdateLoop()` coroutine that fires on a configurable interval (default: 5 seconds). On each cycle it:
1. Fetches vibration data from Azure — either via a direct blob URL (`FetchVibration`) or by constructing a timestamp-based filename (`FetchCurrentVibration`), controlled by the `useTimestampVibration` Inspector toggle
2. Probes for crack images by constructing timestamped URLs within the last `crackCheckRange` minutes (`FetchCurrentCracks`)
3. Parses results, fires events via `SHMEvents`, and drives the 3D wall state

Controls the physical wall object directly: swaps between `normalMat` and `alertMat`, runs the `Vibrate()` coroutine for wall movement, and runs `FlashLight()` for the alert light. Responds to Silence and Acknowledge events from the UI.

### `CrackDetectionUI.cs`
Subscribes to all `SHMEvents` data events and updates the 2D UI panel. Responsibilities:
- Displays real-time vibration magnitude (X, Y, Z + resultant) and timestamp
- Builds and clears the scrollable crack log list dynamically
- Loads and displays crack images in a popup via `UnityWebRequest.GetTexture()`
- Updates the status indicator colour based on `AlertStatus` (Normal → green, Warning → yellow, Critical → red, Silenced → gray)
- Fires `SHMEvents.OnAlertAcknowledged` and `SHMEvents.OnSilenceToggled` in response to button clicks

### `SHMEvents.cs`
A static event bus that decouples `SHMManager` (data layer) from `CrackDetectionUI` (presentation layer). All communication between the two passes through these events:

| Event | Type | Fired when |
|---|---|---|
| `OnVibrationDataReceived` | `Action<VibrationData[]>` | New vibration JSON parsed |
| `OnCrackDataReceived` | `Action<CrackData[]>` | Crack image probe cycle completes |
| `OnDataError` | `Action<string>` | Network or parse failure |
| `OnSilenceToggled` | `Action<bool>` | Silence button pressed |
| `OnAlertAcknowledged` | `Action` | Acknowledge button pressed |

### `SHMData.cs`
Serialisable data models used across the system:

**`VibrationData`** — deserialised from Azure JSON. Provides `Acceleration` (Vector3), `Magnitude` (float), and `Time` (DateTime parsed from `yyyy-MM-dd_HH-mm-ss` format).

**`CrackData`** — constructed locally in Unity when a crack image is found. Contains `timestamp`, `score`, and `image_url`. Exposes `IsCritical` (true if `score > 0.7`) and `Time` (DateTime).

**`AlertStatus`** enum — `Normal`, `Warning`, `Critical`, `Silenced`.

---

## Data Sources

### Vibration (Azure Blob: `realtime_vibrations.json`)
```json
[
  {
    "timestamp": "2025-06-13_12-24-01",
    "x": 1.23,
    "y": 0.87,
    "z": 9.82
  },
  {
    "timestamp": "2025-06-13_12-24-11",
    "x": 2.14,
    "y": 1.02,
    "z": 14.73
  }
]
```
The twin wraps this array in `{"vibrations": [...]}` before deserialising with `JsonUtility` into `VibrationDataArray`.

### Crack Images (Azure Blob: `/crack/crack_{timestamp}.jpg`)
Crack detection does not use a JSON manifest. Instead, the twin probes Azure directly by constructing timestamped filenames:

```
https://cravib.blob.core.windows.net/crack/crack_2025-06-13_15-30-00.jpg
```

For each minute within `crackCheckRange`, a `GET` request is sent. HTTP 200 = crack found; any other response = no crack at that timestamp. A `CrackData` object is then constructed locally.

> ⚠️ **Known gap:** The crack confidence score is not currently encoded in the filename or a sidecar JSON file. The Unity script assigns a random score between 0.5–1.0 as a placeholder. A future improvement would upload a companion JSON (e.g., `crack_2025-06-13_15-30-00.json`) with the model's confidence score, which the twin would fetch and parse.

---

## Alert State Machine

```
          ┌─────────────────────────────┐
          │          NORMAL             │
          │  normalMat · light off      │
          │  wall stationary            │
          └────────────┬────────────────┘
                       │ vibration > threshold
                       │ OR crack detected
                       ▼
          ┌─────────────────────────────┐
          │          CRITICAL           │
          │  alertMat · light flashing  │◀──────────────────┐
          │  wall vibrating             │                   │
          └──────┬──────────┬───────────┘                   │
                 │          │                               │
         Acknowledge      Silence                    unsilence
                 │          │                               │
                 ▼          ▼                               │
    wall stops  │   ┌──────────────────┐                   │
    light cont. │   │     SILENCED     │───────────────────▶┘
                │   │  light off       │
                │   │  wall stopped    │
                │   └──────────────────┘
                ▼
    ┌──────────────────────────┐
    │  CRITICAL (acknowledged) │
    │  alertMat · light on     │
    │  wall stationary         │
    │  resets to NORMAL after  │
    │  30 seconds              │
    └──────────────────────────┘
```

| Control | Effect on wall | Effect on light |
|---|---|---|
| No action (alert) | Vibrating | Flashing |
| Acknowledge | Stops immediately | Continues flashing |
| Silence | Stops immediately | Turns off |
| Unsilence | Resumes if still alerting | Resumes if still alerting |

---

## Inspector Configuration

All runtime parameters are exposed in the Unity Inspector on the `SHMManager` and `CrackDetectionUI` components.

**`SHMManager` (3D scene control)**

| Parameter | Default | Description |
|---|---|---|
| `updateInterval` | `5.0` | Seconds between Azure poll cycles |
| `vibrationThreshold` | `10.0` | m/s² — triggers Critical state |
| `flashRate` | `2.0` | Alert light flashes per second |
| `crackCheckRange` | `1` | Minutes back to probe for crack images (1–10) |
| `useTimestampVibration` | `false` | Toggle timestamp-based vibration polling |
| `vibrationURL` | *(Inspector)* | Direct URL to vibration JSON blob |
| `vibrationBaseURL` | *(Inspector)* | Base URL for timestamp-based vibration mode |
| `crackBaseURL` | `https://cravib.blob.core.windows.net/crack/` | Azure blob base URL for crack images |
| `normalMat` | *(Inspector)* | Wall material — healthy state |
| `alertMat` | *(Inspector)* | Wall material — critical state |
| `alertLight` | *(Inspector)* | Scene light to flash on alert |

**`CrackDetectionUI` (2D panel control)**

| Parameter | Default | Description |
|---|---|---|
| `vibrationThreshold` | `10.0` | Must match `SHMManager` threshold |
| `normalColor` | Green | Status indicator — normal |
| `warningColor` | Yellow | Status indicator — warning |
| `criticalColor` | Red | Status indicator — critical |
| `silencedColor` | Gray | Status indicator — silenced |

> ⚠️ `vibrationThreshold` is set independently in both components. Keep them in sync.

---

## Build & Deployment

### Prerequisites
- Unity 2022.3 LTS or later
- WebGL Build Support module installed
- Azure Blob Storage with CORS configured for your deployment domain

### Azure CORS
Configure CORS on the storage account in the Azure Portal:

| Allowed Origins | Allowed Methods | Allowed Headers | Max Age |
|---|---|---|---|
| Your domain (or `*` for dev) | `GET, OPTIONS` | `*` | `3600` |

CORS must cover **both** the vibration JSON container and the `/crack/` image container.

### Build Steps
1. Open the project in Unity 2022.3+
2. Set `File → Build Settings → Platform` to **WebGL**
3. In `Player Settings → Resolution and Presentation`, set canvas size (recommended: 1280 × 720)
4. Click **Build**
5. Host the output folder on any static web server (Azure Static Web Apps, GitHub Pages, Netlify)

---

## Limitations & Roadmap

| Limitation | Recommended fix |
|---|---|
| Crack score is randomly assigned (0.5–1.0) | Upload a companion `crack_{timestamp}.json` from the Pi with the CNN confidence score; fetch and parse in `CheckCrackImageWebGL` |
| Vibration detection is threshold-based only | Integrate frequency-domain anomaly detection (OMA or trained ML model) on the edge device |
| Crack classification is binary | Add severity grading (hairline / moderate / severe) and crack width estimation |
| Azure HTTP polling adds 2–10s latency | Replace with MQTT-to-browser (via WebSocket) for near-real-time data |
| Single wall structure scope | Extend to a multi-element scene graph with per-element state management |
| `crackToken` Inspector field is unused | Either wire it to a SAS token for authenticated blob access, or remove it |

---

## Related Components

| Component | Description | Location |
|---|---|---|
| Edge Pipeline | Raspberry Pi data acquisition + CNN inference | [`/edge`](../edge/README.md) |
| ML Model | CNN training notebook (Keras → TFLite) | [`/ml`](../ml/README.md) |
| Mobile App | CraVib app for alerts & remote monitoring | [`/mobile`](../mobile/README.md) |
| Cloud Setup | Azure Blob Storage schema & CORS guide | [`/docs/cloud-setup.md`](../docs/cloud-setup.md) |

---

*Part of the CraVib Structural Health Monitoring system — developed at the International Hellenic University as part of the Erasmus Mundus SMACCs programme.*
