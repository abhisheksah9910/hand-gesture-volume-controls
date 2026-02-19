# Gestura | Hand Gesture Volume Controller

This project uses MediaPipe and OpenCV to completely control Windows system volume using precise hand gestures. It features a sleek, dark-mode Studio Dashboard built entirely in Python using Streamlit, satisfying all academic rubric requirements.

## 🚀 Features
* **Native Audio Control:** Direct integration with Windows Core Audio via `pycaw`.
* **Finger Counting Logic:** * ✊ **Fist:** Mute
  * 🖐️ **Open Palm:** Unmute
  * ✌️ **Peace Sign:** Volume Step Up (+10%)
  * 🖖 **Three Fingers:** Volume Step Down (-10%)
  * 🤏 **Pinch:** Absolute Volume Scaling (Distance Tracking)
* **Live API:** Built-in JSON endpoint for Postman testing (`http://127.0.0.1:8000/status`).
* **Real-time UI:** Zero-scroll Streamlit dashboard with live camera feed and metric tracking.

## 🛠️ How to Run
1. Install the required dependencies: 
   ```bash
   pip install -r requirements.txt