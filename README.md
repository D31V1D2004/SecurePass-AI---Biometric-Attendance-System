# 🎯 SecurePass AI — Biometric Attendance System

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-4.8-green?logo=opencv&logoColor=white)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-5-red?logo=raspberrypi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-lightblue?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-Academic-yellow)

**A real-time, fraud-resistant attendance system using sensor fusion between a 2D camera and a 3D LiDAR sensor.**

[Features](#-features) · [Architecture](#-architecture) · [Demo](#-demo) · [Setup](#-setup) · [How it works](#-how-it-works) · [Tech Stack](#-tech-stack)

</div>

---

## 🚀 Overview

SecurePass AI solves a concrete problem in academic environments: **attendance fraud**. Traditional facial recognition systems can be trivially bypassed by holding up a photo on a phone screen. This system adds a second layer of verification using a **rotating LiDAR sensor** that detects whether the object in front of the camera has real 3D depth — something a flat photo never will.

The system runs across two devices communicating over a local network:
- A **Raspberry Pi 5** reads the LiDAR sensor and streams processed point cloud data over TCP
- A **laptop** handles facial recognition, fuses both signals, and records attendance in real time

> Built as a Bachelor's thesis project at the Faculty of Informatics, West University of Timișoara.

---

## ✨ Features

- 🔍 **Real-time facial recognition** using LBPH (Local Binary Pattern Histograms) via OpenCV
- 📡 **Live LiDAR radar** — polar plot visualization of the real LD06 point cloud at ~10Hz
- 🛡️ **Anti-spoofing via liveness detection** — statistical depth classifier (σ) distinguishes real faces from flat photos/screens
- 🌐 **Distributed architecture** — Raspberry Pi 5 as edge sensor node, laptop as processing client
- 🔗 **Custom binary protocol parser** — LD06 47-byte packets decoded from scratch with CRC-8 validation
- 👨‍🏫 **Professor dashboard** — session management, live video + LiDAR feed, event log
- 🎓 **Student portal** — attendance history, self-service face enrollment
- 💾 **Local-first** — all data stored in SQLite, no cloud dependency (GDPR-friendly)
- 🔄 **Auto-reconnect** — LidarEngine client reconnects automatically if network drops

---

## 🏗️ Architecture

```
┌─────────────────────────────┐         ┌──────────────────────────────────────┐
│       Raspberry Pi 5        │         │              Laptop                  │
│                             │         │                                      │
│  LD06 LiDAR                 │         │  ┌─────────────┐  ┌──────────────┐  │
│  (GPIO/UART 230400 baud)    │         │  │ VisionEngine│  │ LidarEngine  │  │
│         │                   │  TCP    │  │    (LBPH)   │  │ (TCP Client) │  │
│  lidar_server.py            │◄───────►│  └──────┬──────┘  └──────┬───────┘  │
│  ┌──────────────────────┐   │  :65432 │         │                │           │
│  │ • Parse LD06 packets │   │  JSON   │         └────────┬───────┘           │
│  │ • CRC-8 validation   │   │  ~10Hz  │                  ▼                   │
│  │ • Liveness σ calc    │   │         │         Sensor Fusion                │
│  │ • TCP broadcast      │   │         │         distance ∈ [0.2, 1.0]m       │
│  └──────────────────────┘   │         │              AND σ ≥ 15mm            │
│                             │         │                  │                   │
└─────────────────────────────┘         │                  ▼                   │
                                        │            SQLite INSERT             │
                                        │          (attendance record)         │
                                        │                                      │
                                        │    CustomTkinter UI (main.py)        │
                                        └──────────────────────────────────────┘
```

---

## 🎬 Demo

<div align="center">

| RGB Camera Feed | LiDAR Radar (real-time) |
|:---:|:---:|
| Face detected + LBPH identity | ~12,000 points per rotation |
| Bounding box + name overlay | Polar plot, color-coded by distance |

**System status when student is present:**
```
✓ ATTENDANCE RECORDED — DAVID.POP04
LiDAR: 0.44m  σ=16.4mm — VALID (LIVE)
```

**System status when a photo is shown instead:**
```
! DAVID.POP04 — FLAT SURFACE DETECTED (SPOOFING BLOCKED)
LiDAR: 0.41m  σ=1.3mm — FLAT SURFACE
```

</div>

---

## 🔬 How It Works

### Liveness Detection via Depth Standard Deviation

The core anti-spoofing mechanism computes the **standard deviation (σ) of depth values** from the nearest point cluster in the LiDAR's frontal cone (±20°):

$$\mu = \frac{1}{N}\sum_{i=1}^{N} d_i \qquad \sigma = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(d_i - \mu)^2}$$

| Object | σ value | Decision |
|--------|---------|----------|
| Real human face (3D relief: nose closer, cheeks further) | σ ≥ 15mm | ✅ VALID |
| Flat surface (phone screen / printed photo) | σ < 10mm | ❌ BLOCKED |

> **Key implementation detail:** σ is computed only on the **nearest cluster** (points within 10cm of the minimum detected distance), not the entire field of view. An early version computed σ across the full 40° sector, which produced values of 900–1200mm due to background objects (walls, furniture) — rendering the classifier useless. Cluster isolation fixed this.

### LD06 Binary Protocol (Parsed from Scratch)

The LD06 sensor transmits 47-byte binary packets at 230,400 baud over UART:

```
Byte  0     : Start byte (0x54)
Byte  1     : Data length (0x2C)
Bytes 2-3   : Rotation speed (little-endian uint16, ÷100 → deg/s)
Bytes 4-5   : Start angle (little-endian uint16, ÷100 → degrees)
Bytes 6-41  : 12 × 3-byte points (uint16 distance mm + uint8 intensity)
Bytes 42-43 : End angle
Bytes 44-45 : Timestamp (ms)
Byte  46    : CRC-8 checksum (polynomial 0x4D)
```

No external library was used for parsing — the full decoder was implemented from scratch, including CRC-8 table generation and full-rotation detection via angle wraparound.

---

## 🛠️ Setup

### Prerequisites

- Python 3.10+
- Raspberry Pi 5 with Raspberry Pi OS
- LD06 LiDAR sensor connected via GPIO UART (TX → Pin 10 / GPIO15)
- Both devices on the same local network

### Raspberry Pi — Server Setup

**1. Enable UART & disable Bluetooth**

```bash
sudo raspi-config
# Interface Options → Serial Port → No login shell → Yes hardware enabled

sudo nano /boot/firmware/config.txt
# Add at the end:
# enable_uart=1
# dtoverlay=disable-bt

sudo reboot
```

**2. Install dependencies & copy server**

```bash
pip3 install pyserial --break-system-packages
# Copy lidar_server.py to the Pi via scp or git clone
```

**3. Verify sensor connection**

```bash
python3 -c "
import serial
s = serial.Serial('/dev/ttyAMA0', 230400, timeout=2)
data = s.read(100)
print('Bytes received:', len(data))  # Should be 100
s.close()
"
```

**4. Start the server**

```bash
python3 lidar_server.py
# [LIDAR-SERVER] Serial opened: /dev/ttyAMA0 @ 230400 baud
# [LIDAR-SERVER] First scan received: ~12000 points
# [LIDAR-SERVER] TCP server started on 0.0.0.0:65432
```

### Laptop — Client Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Set the Raspberry Pi IP**

In `lidar_engine.py`:
```python
LIDAR_SERVER_IP = "192.168.x.x"  # Run `hostname -I` on the Pi
```

**3. Add student photos to dataset**

```
dataset/
  student.email@e-uvt.ro/
    1.jpg   ← 10-20 front-facing photos recommended
    2.jpg
    ...
```

**4. Run the application**

```bash
python main.py
```

---

## 📁 Project Structure

```
.
├── main.py              # Desktop application entry point (CustomTkinter UI)
├── vision_core.py       # Facial detection (Haar Cascade) + recognition (LBPH)
├── lidar_engine.py      # TCP client — receives LiDAR data from Raspberry Pi
├── lidar_server.py      # TCP server — parses LD06 binary stream, computes σ
├── requirements.txt
├── README.md
└── dataset/             # Training images, one subfolder per student (email)
```

---

## 🧰 Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3 | Consistent across both devices |
| Computer Vision | OpenCV + LBPH | Works offline, no GPU required |
| UI Framework | CustomTkinter | Modern dark-mode desktop UI |
| Database | SQLite3 | Local-first, zero config, GDPR-friendly |
| Networking | TCP Sockets | Guaranteed delivery — a lost packet = wrong decision |
| Serial | pyserial | UART communication with LD06 |
| Edge Device | Raspberry Pi 5 | Low-cost ARM board for sensor processing |
| Sensor | LDROBOT LD06 | 2D rotating LiDAR, 12K points/rotation |

---

## 📊 Results

| Metric | Value |
|--------|-------|
| LiDAR points per full rotation | ~12,000 |
| Sensor rotation speed | ~36°/sec |
| TCP broadcast frequency | 10 Hz |
| TCP latency (RPi → laptop, local Wi-Fi) | < 100ms |
| σ — real face | 16.4mm |
| σ — phone screen (spoof attempt) | < 10mm |
| Validation distance range | 0.2m – 1.0m |

---

## 🔮 Future Work

- [ ] **Blink-based liveness detection** — additional temporal anti-spoofing layer
- [ ] **Deep learning face recognition** — replace LBPH with FaceNet/MobileFaceNet
- [ ] **Multi-student enrollment UI** — enroll directly from the application
- [ ] **PDF/CSV export** — attendance reports per session
- [ ] **Multi-person simultaneous detection** — sequential flow limitation

---

## 👤 Author

**Pop David** — Computer Science, West University of Timișoara


---

<div align="center">
<sub>Built with Python, OpenCV, and a real LiDAR sensor 📡</sub>
</div>
