# 🎛️ Gestura | Studio Controller

Gestura is an advanced, AI-powered hand gesture recognition system that allows you to control your computer's system audio without touching your mouse or keyboard. Originally built as an internship project, it has evolved into a full-featured studio controller with a beautiful web UI, real-time analytics, and a live local API.

## ✨ Key Features

* **🤖 AI Vision Engine:** Uses Google's MediaPipe and OpenCV for lightning-fast, high-accuracy hand landmark detection.
* **🎨 Dynamic Web UI:** A custom-styled Streamlit interface featuring a dynamic Light/Dark mode toggle and a responsive layout.
* **📊 Real-Time SVG Analytics:** Live tracking graphs showing Distance vs. Volume mapping and a Volume History timeline.
* **📡 Live Local API:** A built-in HTTP server (running on port 8000) that broadcasts live gesture and volume states, ready to be consumed by Postman or other applications.
* **⚙️ Calibration Studio:** Easily calibrate your minimum (closed) and maximum (open) pinch distances directly from the sidebar.

## 🛠️ Tech Stack

* **Python 3.x**
* **Computer Vision:** `opencv-python`, `mediapipe`
* **System Control:** `pycaw` (Windows Audio), `pyautogui` (Keystrokes)
* **Frontend/UI:** `streamlit`

## 🖐️ Gesture Guide

Gestura maps specific hand signs to intuitive audio controls:

| Gesture | Action | Description |
| :--- | :--- | :--- |
| **Pinch** (Index & Thumb) | **Dynamic Volume** | Spread fingers to increase volume, pinch together to decrease. |
| **Peace Sign** (2 Fingers) | **Volume Step Up** | Increases volume by a set percentage step. |
| **Three Fingers** | **Volume Step Down** | Decreases volume by a set percentage step. |
| **Fist** (0 Fingers) | **Mute / Unmute** | Instantly toggles system audio mute. |
| **Open Palm** (5 Fingers) | **Mute / Unmute** | Hold for 15 frames to toggle mute state. |

## 🚀 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/abhisheksah9910/hand-gesture-volume-controls.git](https://github.com/abhisheksah9910/hand-gesture-volume-controls.git)
   cd hand-gesture-volume-controls
