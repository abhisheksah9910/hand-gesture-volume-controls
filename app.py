import streamlit as st
import cv2
import numpy as np
import pyautogui
import time
import threading
import json
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from math import hypot

from mediapipe import Image, ImageFormat
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL, CoInitialize
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# Disable PyAutoGUI delay for lightning-fast volume steps
pyautogui.PAUSE = 0 

# --- 1. POSTMAN API SERVER ---
api_state = {"volume": 0, "gesture": "None", "distance_mm": 0, "finger_count": 0, "mute_status": "Active", "raw_distance_state": "None"}

class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(api_state).encode())
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        pass

def run_api():
    server = HTTPServer(('127.0.0.1', 8000), StatusHandler)
    server.serve_forever()

if "api_thread" not in st.session_state:
    threading.Thread(target=run_api, daemon=True).start()
    st.session_state.api_thread = True

# --- 2. CONFIG, THEME ENGINE & SESSION STATE ---
st.set_page_config(page_title="Gestura | Studio", layout="wide", initial_sidebar_state="expanded")
CoInitialize()

if 'calib_min' not in st.session_state: st.session_state.calib_min = 20
if 'calib_max' not in st.session_state: st.session_state.calib_max = 100
if 'live_dist' not in st.session_state: st.session_state.live_dist = 50

# CAMERA & LOOP STATE CACHE
if 'camera_obj' not in st.session_state: st.session_state.camera_obj = None
if 'run_camera' not in st.session_state: st.session_state.run_camera = False

def set_min_calib():
    st.session_state.calib_min = min(max(st.session_state.live_dist, 10), 100)
def set_max_calib():
    st.session_state.calib_max = min(max(st.session_state.live_dist, 50), 300)

# Dynamic Sun & Moon Theme Toggle
if 'theme_toggle' not in st.session_state:
    st.session_state.theme_toggle = False

toggle_label = "☀️ Light Mode" if st.session_state.theme_toggle else "🌙 Dark Mode"
is_light_mode = st.sidebar.toggle(toggle_label, key="theme_toggle")

# Theme Dictionary
theme = {
    "bg_main": "#f3f4f6" if is_light_mode else "#0a0a0c",
    "bg_sidebar": "#ffffff" if is_light_mode else "#17171e",
    "bg_panel": "#ffffff" if is_light_mode else "#121216",
    "bg_card": "#f9fafb" if is_light_mode else "#0a0a0c",
    "border": "#e5e7eb" if is_light_mode else "#26262f",
    "text_main": "#111827" if is_light_mode else "#ffffff",
    "text_brand": "#111827" if is_light_mode else "#ededed",
    "text_muted": "#6b7280" if is_light_mode else "#8a8a93",
    "btn_bg": "#ffffff" if is_light_mode else "#171124", 
    "btn_border": "#8b5cf6" if is_light_mode else "#7c3aed",
    "btn_hover": "#7c3aed",
    "accent_blue": "#0284c7" if is_light_mode else "#00d2ff",
    "accent_purple": "#7e22ce" if is_light_mode else "#8a2be2",
    "accent_purple_grad": "#9333ea" if is_light_mode else "#a855f7",
    "success": "#059669" if is_light_mode else "#10b981",
    "success_bg": "rgba(5, 150, 105, 0.1)" if is_light_mode else "rgba(16, 185, 129, 0.15)",
    "danger": "#dc2626" if is_light_mode else "#ef4444",
    "danger_bg": "rgba(220, 38, 38, 0.1)" if is_light_mode else "rgba(239, 68, 68, 0.15)",
    "warning": "#d97706" if is_light_mode else "#f59e0b",
    "bar_bg": "#e5e7eb" if is_light_mode else "#1e1e24",
    "vol_bar": "#9ca3af" if is_light_mode else "#3f3f46",
    "shadow": "rgba(0,0,0,0.08)" if is_light_mode else "rgba(0,0,0,0.6)",
    "standby_text": "#64748b" if is_light_mode else "#94a3b8"
}

st.markdown(f"""
    <style>
    html, body, [data-testid="stAppViewContainer"] {{ background-color: {theme['bg_main']} !important; overflow: auto !important; }}
    [data-testid="stSidebar"] {{ background-color: {theme['bg_sidebar']} !important; }}
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, [data-testid="stWidgetLabel"] p {{ color: {theme['text_main']} !important; }}
    .block-container {{ padding: 1.5rem 2rem 2rem 2rem !important; max-width: 100% !important; }}
    [data-testid="stSidebarUserContent"] {{ padding-top: 1rem !important; }}
    footer {{ display: none !important; }}
    [data-testid="stHeader"] {{ background-color: transparent !important; }}
    #MainMenu {{visibility: hidden;}}
    [data-testid="stVerticalBlock"] {{ gap: 0 !important; }}
    div[data-testid="stImage"] {{ border-radius: 12px; overflow: hidden; border: 1px solid {theme['border']}; margin-top: 5px; box-shadow: 0 10px 40px {theme['shadow']}; }}
    .app-brand {{ font-family: -apple-system, sans-serif; font-size: 1.4rem; font-weight: 800; color: {theme['text_brand']}; margin-bottom: 10px; display: flex; align-items: center; }}
    .app-brand span {{ color: {theme['text_muted']}; font-weight: 400; font-size: 0.9rem; margin-left: 10px; }}
    
    /* Standard Start/Pause Buttons */
    div[data-testid="stButton"] button {{ width: 100% !important; border-radius: 6px !important; background-color: {theme['btn_bg']} !important; border: 1px solid {theme['btn_border']} !important; margin-bottom: 5px !important; box-shadow: 0 4px 6px {theme['shadow']} !important; transition: all 0.2s ease !important; padding: 0.25rem 0.5rem !important; font-size: 0.9rem !important; }}
    div[data-testid="stButton"] button p, div[data-testid="stButton"] button div, div[data-testid="stButton"] button span {{ color: {theme['text_main']} !important; transition: all 0.2s ease !important; }}
    div[data-testid="stButton"] button:hover {{ background-color: {theme['btn_hover']} !important; border: 1px solid {theme['btn_hover']} !important; transform: translateY(-2px); }}
    div[data-testid="stButton"] button:hover p, div[data-testid="stButton"] button:hover div, div[data-testid="stButton"] button:hover span {{ color: #ffffff !important; }}
    
    [data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"] {{ background-color: {theme['bg_card']} !important; border: 1px solid {theme['border']} !important; border-radius: 50% !important; box-shadow: 0 4px 12px {theme['shadow']} !important; transition: all 0.3s ease !important; }}
    [data-testid="stSidebarCollapseButton"]:hover, [data-testid="collapsedControl"]:hover {{ background-color: {theme['btn_hover']} !important; border-color: {theme['btn_hover']} !important; transform: scale(1.1) !important; }}
    [data-testid="stSidebarCollapseButton"] svg, [data-testid="collapsedControl"] svg {{ fill: {theme['text_main']} !important; color: {theme['text_main']} !important; transition: all 0.3s ease !important; }}
    [data-testid="stSidebarCollapseButton"]:hover svg, [data-testid="collapsedControl"]:hover svg {{ fill: #ffffff !important; color: #ffffff !important; }}
    </style>
""", unsafe_allow_html=True)

# --- MILESTONE 4 HELPER: Rounded Rectangles ---
def draw_rounded_rect(img, top_left, bottom_right, color, radius=12):
    x1, y1 = top_left
    x2, y2 = bottom_right
    cv2.circle(img, (x1 + radius, y1 + radius), radius, color, -1)
    cv2.circle(img, (x2 - radius, y1 + radius), radius, color, -1)
    cv2.circle(img, (x1 + radius, y2 - radius), radius, color, -1)
    cv2.circle(img, (x2 - radius, y2 - radius), radius, color, -1)
    cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
    cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)

# --- 3. THE PERMANENT SIDEBAR ---
with st.sidebar:
    st.markdown("### ⚙️ Calibration Settings")
    st.markdown("Adjust to fit your hand size and camera distance.")
    
    st.markdown(f"<div style='font-size: 0.8rem; color: {theme['text_muted']}; padding-bottom: 15px; margin-top: 15px; display: block;'>Auto-Calibrate: Hold hand in position & click</div>", unsafe_allow_html=True)
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("Set Min 🤏", on_click=set_min_calib, help="Set closed pinch distance")
    with btn_col2:
        st.button("Set Max 🖐️", on_click=set_max_calib, help="Set open pinch distance")
    
    min_dist = st.slider("Min Pinch Distance (mm)", 10, 100, key="calib_min")
    max_dist = st.slider("Max Pinch Distance (mm)", 50, 300, key="calib_max")
    step_vol = st.slider("Volume Step % (Peace/3-Finger)", 2, 20, 10)
    
    st.markdown("---")
    st.markdown(f"""
    <div style='background: {theme['success_bg']}; border: 1px solid {theme['success']}; border-radius: 8px; padding: 15px; margin-bottom: 15px;'>
        <div style='color: {theme['success']}; font-weight: 700; font-size: 0.9rem; margin-bottom: 5px;'>📡 Postman API Live</div>
        <div style='color: {theme['success']}; font-size: 0.75rem; font-family: monospace;'>GET http://127.0.0.1:8000/status</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🔴 Live API Output")
    api_display_ph = st.empty() 

# --- 4. MEDIAPIPE INIT & FINGER MATH ---
@st.cache_resource
def load_mediapipe_model():
    base_options = python.BaseOptions(model_asset_path="hand_landmarker.task")
    options = vision.HandLandmarkerOptions(base_options=base_options, num_hands=2)
    return vision.HandLandmarker.create_from_options(options)

def init_windows_audio():
    devices = AudioUtilities.GetSpeakers()
    try:
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except AttributeError:
        return devices.EndpointVolume.QueryInterface(IAudioEndpointVolume)

def get_finger_state(hand):
    fingers = []
    thumb_tip_dist = hypot(hand[4].x - hand[17].x, hand[4].y - hand[17].y)
    thumb_mcp_dist = hypot(hand[2].x - hand[17].x, hand[2].y - hand[17].y)
    fingers.append(1 if thumb_tip_dist > thumb_mcp_dist else 0)
    
    tips = [8, 12, 16, 20]
    pips = [6, 10, 14, 18]
    for tip, pip in zip(tips, pips):
        fingers.append(1 if hand[tip].y < hand[pip].y else 0)
    return fingers

detector = load_mediapipe_model()
system_audio = init_windows_audio()
HAND_CONNECTIONS = [(0,1), (1,2), (2,3), (3,4), (0,5), (5,6), (6,7), (7,8), (5,9), (9,10), (10,11), (11,12), (9,13), (13,14), (14,15), (15,16), (13,17), (17,18), (18,19), (19,20), (0,17)]

st.markdown("<div class='app-brand'>GESTURA <span>| Studio Controller</span></div>", unsafe_allow_html=True)
col_left, col_center, col_right = st.columns([1, 2.2, 1], gap="large")

with col_left: left_panel_ph = st.empty()
with col_right: right_panel_ph = st.empty()

# --- 5. CENTER COLUMN LAYOUT ---
with col_center:
    controls_col1, controls_col2 = st.columns([1, 1])
    with controls_col1:
        b1, b2 = st.columns(2)
        if b1.button("▶ Start", use_container_width=True):
            st.session_state.run_camera = True
            st.rerun()
        if b2.button("⏸ Pause", use_container_width=True):
            st.session_state.run_camera = False
            st.rerun()

    with controls_col2:
        st.markdown(f"<div style='text-align: right; color: {theme['text_muted']}; font-size: 0.8rem; margin-top: 10px;'>✌️ Step + | 🖖 Step - | ✊ Mute | 🖐️ Unmute | 🤏 Scale</div>", unsafe_allow_html=True)
    
    video_placeholder = st.empty()
    stats_placeholder = st.empty() 

# --- 6. MAIN LOOP ---
if st.session_state.run_camera:
    if st.session_state.camera_obj is None:
        st.session_state.camera_obj = cv2.VideoCapture(0)
    
    cap = st.session_state.camera_obj
    
    last_mute_time = 0
    last_gesture_time = 0
    open_palm_counter = 0
    smoothed_dist = 0  
    active_master_label = "None"
    prev_frame_time = time.time()
    
    frame_counter = 0
    vol_history = deque([0]*20, maxlen=20)

    while st.session_state.run_camera:
        success, frame = cap.read()
        if not success: break
            
        frame_counter += 1
        new_frame_time = time.time()
        frame_delta = new_frame_time - prev_frame_time
        fps = int(1 / frame_delta) if frame_delta > 0 else 0
        latency_ms = int(frame_delta * 1000)
        prev_frame_time = new_frame_time

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = Image(image_format=ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)

        hand_count_str = "Waiting..."
        display_label = "NONE"
        current_distance_mm = 0
        rubric_gesture = "None"
        finger_count = 0
        ui_gesture_state = "None"
        is_smoothing = False 
        accuracy_pct = 0  
        
        current_vol_percent = round(system_audio.GetMasterVolumeLevelScalar() * 100)
        is_muted = system_audio.GetMute()
        mute_status = "Muted" if is_muted else "Active"
        vol_history.append(current_vol_percent)

        if result.hand_landmarks:
            hand_count_str = f"{len(result.hand_landmarks)} Detected"
            visible_hands = []
            hand_data_dict = {}
            
            for hand, handedness in zip(result.hand_landmarks, result.handedness):
                accuracy_pct = int(handedness[0].score * 100)
                corrected_label = "Left" if handedness[0].category_name == "Right" else "Right"
                if corrected_label in hand_data_dict: corrected_label = f"{corrected_label}_2"
                visible_hands.append(corrected_label)
                hand_data_dict[corrected_label] = hand

                for p1, p2 in HAND_CONNECTIONS:
                    cv2.line(frame, (int(hand[p1].x*w), int(hand[p1].y*h)), (int(hand[p2].x*w), int(hand[p2].y*h)), (0, 255, 0), 2)
                for lm in hand:
                    cv2.circle(frame, (int(lm.x*w), int(lm.y*h)), 5, (0, 0, 255), -1)

            if active_master_label not in visible_hands:
                active_master_label = visible_hands[0]

            master_hand = hand_data_dict[active_master_label]
            x4, y4 = int(master_hand[4].x*w), int(master_hand[4].y*h)
            x8, y8 = int(master_hand[8].x*w), int(master_hand[8].y*h)
            now = time.time()

            display_label = active_master_label.replace("_2", "")

            fingers = get_finger_state(master_hand)
            finger_count = sum(fingers)
            current_distance_mm = int(hypot(x8 - x4, y8 - y4) * 0.5)
            
            st.session_state.live_dist = current_distance_mm

            if finger_count == 0: rubric_gesture = "Fist"
            elif finger_count == 5: rubric_gesture = "Open Palm"
            elif fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0: rubric_gesture = "Peace Sign"
            elif fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 1 and fingers[4] == 0: rubric_gesture = "Three Fingers"
            elif fingers[0] == 1 and finger_count == 1: rubric_gesture = "Thumb Up"
            elif current_distance_mm <= max_dist and finger_count <= 2: rubric_gesture = "Pinch"

            if current_distance_mm < 20: ui_gesture_state = "Closed"
            elif 20 <= current_distance_mm <= 80: ui_gesture_state = "Pinch"
            else: ui_gesture_state = "Open Hand"

            cv2.line(frame, (x4, y4), (x8, y8), (200, 0, 200), 3)
            cv2.putText(frame, f"{current_distance_mm}mm", ((x4+x8)//2, (y4+y8)//2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            if rubric_gesture == "Fist" and now - last_mute_time > 1.0:
                if mute_status == "Active":
                    pyautogui.press('volumemute')
                    last_mute_time = now

            if rubric_gesture == "Open Palm":
                open_palm_counter += 1
                if open_palm_counter >= 15:
                    if mute_status == "Muted": pyautogui.press('volumemute')
                    open_palm_counter = 0
            else: open_palm_counter = 0

            if rubric_gesture == "Peace Sign" and now - last_gesture_time > 0.8:
                pyautogui.press('volumeup', presses=step_vol // 2)
                last_gesture_time = now

            if rubric_gesture == "Three Fingers" and now - last_gesture_time > 0.8:
                pyautogui.press('volumedown', presses=step_vol // 2)
                last_gesture_time = now

            if rubric_gesture == "Pinch":
                is_smoothing = True
                if smoothed_dist == 0: smoothed_dist = current_distance_mm
                else: smoothed_dist = (0.35 * current_distance_mm) + (0.65 * smoothed_dist)
                
                target_vol = int(np.interp(smoothed_dist, [min_dist, max_dist], [0, 100]))
                diff = target_vol - current_vol_percent
                
                if abs(diff) >= 2:
                    steps = abs(diff) // 2  
                    if diff > 0: pyautogui.press('volumeup', presses=steps)
                    else: pyautogui.press('volumedown', presses=steps)
                    current_vol_percent = round(system_audio.GetMasterVolumeLevelScalar() * 100)

        else:
            active_master_label = "None"
            smoothed_dist = 0
            open_palm_counter = 0
            st.session_state.live_dist = 0

        pill_text = f"{ui_gesture_state} Gesture" if ui_gesture_state != "None" else "Waiting..."
        text_size = cv2.getTextSize(pill_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
        draw_rounded_rect(frame, (20, 20), (40 + text_size[0], 60), (35, 107, 255), radius=15)
        cv2.putText(frame, pill_text, (30, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        quality_color = (80, 200, 80) if accuracy_pct >= 85 else (80, 80, 200) 
        quality_text = "Good Detection" if accuracy_pct >= 85 else "Poor Detection"
        if hand_count_str == "Waiting...": quality_color, quality_text = (150, 150, 150), "No Hands"
        q_text_size = cv2.getTextSize(quality_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
        draw_rounded_rect(frame, (w - q_text_size[0] - 40, 20), (w - 20, 60), quality_color, radius=15)
        cv2.putText(frame, quality_text, (w - q_text_size[0] - 30, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        bar_x, bar_y, bar_w, bar_h = 20, int(h/2 - 100), 12, 200
        draw_rounded_rect(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (200, 200, 200), radius=5)
        vol_fill = int((current_vol_percent / 100) * bar_h)
        if vol_fill > 0:
            draw_rounded_rect(frame, (bar_x, bar_y + bar_h - vol_fill), (bar_x + bar_w, bar_y + bar_h), (35, 107, 255), radius=5)

        api_state["volume"] = current_vol_percent
        api_state["gesture"] = rubric_gesture
        api_state["distance_mm"] = current_distance_mm
        api_state["finger_count"] = finger_count
        api_state["mute_status"] = mute_status
        api_state["raw_distance_state"] = ui_gesture_state

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        video_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)
        
        if frame_counter % 3 == 0:
            api_display_ph.json(api_state) 
            
            mute_bg = theme['danger_bg'] if mute_status == "Muted" else theme['success_bg']
            mute_border = theme['danger'] if mute_status == "Muted" else theme['success']
            mute_color = theme['danger'] if mute_status == "Muted" else theme['success']
            mute_text = "AUDIO MUTED" if mute_status == "Muted" else "AUDIO ACTIVE"
            vol_bar_color = theme['vol_bar'] if mute_status == "Muted" else f"linear-gradient(to right, {theme['success']}, {theme['success']})"
            
            # --- SVG GRAPH VARIABLES ---
            graph_w, graph_h = 240, 90
            margin_x, margin_y = 25, 15
            x_max = max(max_dist * 1.1, 100) 
            
            def get_map_x(val): return margin_x + (min(max(val, 0), x_max) / x_max) * graph_w
            def get_map_y(val): return margin_y + graph_h - (min(max(val, 0), 100) / 100) * graph_h

            # ====== MAP 1: DISTANCE TO VOLUME MAPPING ======
            grids = ""
            for v in [0, 50, 100]:
                y_pos = get_map_y(v)
                grids += f'<line x1="{margin_x}" y1="{y_pos}" x2="{margin_x+graph_w}" y2="{y_pos}" stroke="{theme["border"]}" stroke-width="1" stroke-dasharray="4 4" />'
                grids += f'<text x="{margin_x-8}" y="{y_pos+3}" font-size="9" fill="{theme["text_muted"]}" text-anchor="end" font-weight="600">{v}</text>'

            step_x = 50 if x_max > 150 else 20
            for d in range(0, int(x_max) + 1, step_x):
                x_pos = get_map_x(d)
                grids += f'<line x1="{x_pos}" y1="{margin_y}" x2="{x_pos}" y2="{margin_y+graph_h}" stroke="{theme["border"]}" stroke-width="1" stroke-dasharray="4 4"/>'
                grids += f'<text x="{x_pos}" y="{margin_y+graph_h+12}" font-size="8" fill="{theme["text_muted"]}" text-anchor="middle">{d}</text>'

            x0, y0 = get_map_x(0), get_map_y(0)
            x1, y1 = get_map_x(min_dist), get_map_y(0)     
            x2, y2 = get_map_x(max_dist), get_map_y(100)   
            x3, y3 = get_map_x(x_max), get_map_y(100)      
            
            poly_points = f"{x0},{margin_y+graph_h} {x0},{y0} {x1},{y1} {x2},{y2} {x3},{y3} {x3},{margin_y+graph_h}"
            
            cx = get_map_x(current_distance_mm)
            cy = get_map_y(current_vol_percent)

            mapping_graph = f"""
            <div style="width: 100%; margin-bottom: 25px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; font-size: 0.7rem;">
                    <span style="color: {theme['text_muted']}; font-weight: 600;">📉 DISTANCE VS VOLUME MAP</span>
                    <div style="display: flex; gap: 8px;">
                        <span style="color: #4DB6AC; font-weight: 600;">▬ Vol %</span>
                        <span style="color: #ff5722; font-weight: 600;">● Pos</span>
                    </div>
                </div>
                <svg viewBox="0 0 {margin_x + graph_w + 10} {margin_y + graph_h + 20}" style="width: 100%; height: auto; display: block; overflow: visible;">
                    <defs>
                        <linearGradient id="mapGrad1" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#4DB6AC" stop-opacity="0.3" />
                            <stop offset="100%" stop-color="#4DB6AC" stop-opacity="0.0" />
                        </linearGradient>
                    </defs>
                    {grids}
                    <polygon points="{poly_points}" fill="url(#mapGrad1)" />
                    <polyline points="{x0},{y0} {x1},{y1} {x2},{y2} {x3},{y3}" fill="none" stroke="#4DB6AC" stroke-width="2.5" stroke-linejoin="round"/>
                    <circle cx="{x1}" cy="{y1}" r="2" fill="#4DB6AC" />
                    <circle cx="{x2}" cy="{y2}" r="2" fill="#4DB6AC" />
                    <circle cx="{cx}" cy="{cy}" r="4.5" fill="#ff5722" stroke="{theme['bg_card']}" stroke-width="1.5" />
                </svg>
            </div>
            """

            # ====== MAP 2: VOLUME HISTORY MAP ======
            hist_grids = ""
            for v in [0, 50, 100]:
                y_pos = get_map_y(v)
                hist_grids += f'<line x1="{margin_x}" y1="{y_pos}" x2="{margin_x+graph_w}" y2="{y_pos}" stroke="{theme["border"]}" stroke-width="1" stroke-dasharray="4 4" />'
                hist_grids += f'<text x="{margin_x-8}" y="{y_pos+3}" font-size="9" fill="{theme["text_muted"]}" text-anchor="end" font-weight="600">{v}</text>'

            for i in range(5):
                hx = margin_x + (i / 4) * graph_w
                hist_grids += f'<line x1="{hx}" y1="{margin_y}" x2="{hx}" y2="{margin_y+graph_h}" stroke="{theme["border"]}" stroke-width="1" stroke-dasharray="4 4"/>'

            hist_points = []
            hist_poly = [f"{margin_x},{margin_y+graph_h}"] 

            if len(vol_history) > 1:
                for i, v in enumerate(vol_history):
                    hx = margin_x + (i / (len(vol_history) - 1)) * graph_w
                    hy = margin_y + graph_h - (min(max(v, 0), 100) / 100) * graph_h
                    hist_points.append(f"{hx},{hy}")
                    hist_poly.append(f"{hx},{hy}")

                hist_poly.append(f"{margin_x+graph_w},{margin_y+graph_h}")
                
                hist_points_str = " ".join(hist_points)
                hist_poly_str = " ".join(hist_poly)
                
                last_hx = margin_x + graph_w
                last_hy = margin_y + graph_h - (min(max(vol_history[-1], 0), 100) / 100) * graph_h
                
                history_graph = f"""
                <div style="width: 100%; border-top: 1px dashed {theme['border']}; padding-top: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; font-size: 0.7rem;">
                        <span style="color: {theme['text_muted']}; font-weight: 600;">⏱️ VOLUME HISTORY MAP</span>
                        <div style="display: flex; gap: 8px;">
                            <span style="color: #4DB6AC; font-weight: 600;">▬ History</span>
                            <span style="color: #ff5722; font-weight: 600;">● Now</span>
                        </div>
                    </div>
                    <svg viewBox="0 0 {margin_x + graph_w + 10} {margin_y + graph_h + 10}" style="width: 100%; height: auto; display: block; overflow: visible;">
                        <defs>
                            <linearGradient id="mapGrad2" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" stop-color="#4DB6AC" stop-opacity="0.3" />
                                <stop offset="100%" stop-color="#4DB6AC" stop-opacity="0.0" />
                            </linearGradient>
                        </defs>
                        {hist_grids}
                        <polygon points="{hist_poly_str}" fill="url(#mapGrad2)" />
                        <polyline points="{hist_points_str}" fill="none" stroke="#4DB6AC" stroke-width="2.5" stroke-linejoin="round"/>
                        <circle cx="{last_hx}" cy="{last_hy}" r="4.5" fill="#ff5722" stroke="{theme['bg_card']}" stroke-width="1.5" />
                    </svg>
                </div>
                """
            else:
                history_graph = ""

            # --- LEFT PANEL: Distance Tracker ---
            fill_pct = min((current_distance_mm / max_dist) * 100, 100) if max_dist > 0 else 0
            smooth_badge_color = theme['success'] if is_smoothing else theme['standby_text']
            smooth_badge_text = "ACTIVE" if is_smoothing else "STANDBY"

            distance_tracker_html = f"""
            <div style="width: 100%; padding-top: 15px; border-top: 1px dashed {theme['border']}; margin-top: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <span style="font-size: 0.7rem; color: {theme['text_muted']}; letter-spacing: 1px; font-weight: 600;">📏 DISTANCE TRACKER</span>
                    <span style="font-size: 0.6rem; background: {theme['bg_main']}; border: 1px solid {smooth_badge_color}; color: {smooth_badge_color}; padding: 3px 6px; border-radius: 4px;">SMOOTHING: {smooth_badge_text}</span>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 2.5rem; color: {theme['accent_purple']}; font-weight: 700; line-height: 1;">{current_distance_mm}</div>
                    <div style="font-size: 0.65rem; color: {theme['text_muted']}; letter-spacing: 2px; margin-top: 5px; margin-bottom: 15px;">MILLIMETERS</div>
                    <div style="width: 100%; height: 6px; background: {theme['bar_bg']}; border-radius: 3px; overflow: hidden;">
                        <div style="width: {fill_pct}%; height: 100%; background: linear-gradient(90deg, {theme['accent_purple']}, {theme['accent_purple_grad']}); transition: width 0.1s;"></div>
                    </div>
                </div>
            </div>
            """

            left_html = f"""
            <div style="background-color: {theme['bg_panel']}; border: 1px solid {theme['border']}; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; font-family: sans-serif;">
                <div style="font-size: 0.75rem; color: {theme['text_muted']}; letter-spacing: 1px; font-weight: 600; margin-bottom: 15px;">AI ENGINE</div>
                <div style="background: {theme['bg_card']}; border: 1px solid {theme['border']}; border-radius: 8px; padding: 15px; margin-bottom: 10px; display: flex; justify-content: space-between;">
                    <span style="color: {theme['text_muted']}; font-size: 0.9rem;">Detection</span><span style="color: {theme['text_main']}; font-weight: 600;">{hand_count_str}</span>
                </div>
                <div style="background: {theme['bg_card']}; border: 1px solid {theme['border']}; border-radius: 8px; padding: 15px; margin-bottom: 30px; display: flex; justify-content: space-between;">
                    <span style="color: {theme['text_muted']}; font-size: 0.9rem;">Active Hand</span><span style="color: {theme['accent_blue']}; font-weight: 700;">{display_label}</span>
                </div>
                
                <div style="font-size: 0.75rem; color: {theme['text_muted']}; letter-spacing: 1px; font-weight: 600; margin-bottom: 15px;">MASTER OUTPUT</div>
                <div style="background: {theme['bg_card']}; border: 1px solid {theme['border']}; border-radius: 8px; padding: 25px 20px; display: flex; flex-direction: column; justify-content: center; align-items: center; margin-bottom: 25px;">
                    <div style="font-size: 3rem; color: {theme['text_main']}; font-weight: 700; font-family: monospace; line-height: 1;">{current_vol_percent}%</div>
                    <div style="width: 100%; height: 8px; background: {theme['bar_bg']}; border-radius: 4px; margin: 20px 0; overflow: hidden;">
                        <div style="width: {current_vol_percent}%; height: 100%; background: {vol_bar_color}; transition: width 0.1s;"></div>
                    </div>
                    <div style="width: 100%; text-align: center; padding: 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; letter-spacing: 1px; background: {mute_bg}; border: 1px solid {mute_border}; color: {mute_color}; margin-bottom: 15px;">{mute_text}</div>
                    
                    {distance_tracker_html}
                </div>
            </div>
            """.replace('\n', '')
            left_panel_ph.markdown(left_html, unsafe_allow_html=True)

            # ====== GESTURE RECOGNITION PILLS GENERATOR ======
            def get_gesture_pill(title, condition, emoji, icon_color, target_state, current_state):
                is_active = (current_state == target_state)
                # Give active rows a very subtle tinted background and a colored left border
                bg_color = f"rgba({int(icon_color[1:3], 16)}, {int(icon_color[3:5], 16)}, {int(icon_color[5:7], 16)}, 0.1)" if is_active else theme['bg_card']
                border_left = f"4px solid {icon_color}" if is_active else f"1px solid {theme['border']}"
                border_main = f"1px solid {theme['border']}"
                
                status_text = "Active" if is_active else "Inactive"
                status_color = icon_color if is_active else theme['text_muted']
                title_color = theme['text_main'] if is_active else theme['text_muted']
                
                return f"""
                <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 15px; border-radius: 8px; background: {bg_color}; border: {border_main}; border-left: {border_left}; margin-bottom: 10px; transition: all 0.2s;">
                    <div style="display: flex; align-items: center;">
                        <div style="width: 35px; height: 35px; border-radius: 50%; background: {icon_color}; display: flex; align-items: center; justify-content: center; color: white; margin-right: 15px; font-size: 1.1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            {emoji}
                        </div>
                        <div>
                            <div style="font-weight: 700; color: {title_color}; font-size: 0.95rem;">{title}</div>
                            <div style="font-size: 0.7rem; color: {theme['text_muted']}; margin-top: 2px;">{condition}</div>
                        </div>
                    </div>
                    <div style="font-weight: 700; font-size: 0.85rem; color: {status_color};">{status_text}</div>
                </div>
                """

            gesture_recognition_html = f"""
            <div style="margin-top: 20px; border-top: 1px dashed {theme['border']}; padding-top: 20px;">
                <div style="font-size: 0.75rem; font-weight: 600; color: {theme['text_muted']}; letter-spacing: 1px; margin-bottom: 15px; display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 1.1rem;">✋</span> GESTURE RECOGNITION
                </div>
                {get_gesture_pill("Open Hand", "Distance > 80mm", "✋", "#22c55e", "Open Hand", ui_gesture_state)}
                {get_gesture_pill("Pinch", "20mm &lt; Distance &lt; 80mm", "✌️", "#f59e0b", "Pinch", ui_gesture_state)}
                {get_gesture_pill("Closed", "Distance &lt; 20mm", "✊", "#ef4444", "Closed", ui_gesture_state)}
            </div>
            """

            # --- RIGHT PANEL HTML CONSTRUCTION ---
            right_html = f"""
            <div style="background-color: {theme['bg_panel']}; border: 1px solid {theme['border']}; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; font-family: sans-serif;">
                
                <div style="margin-bottom: 25px;">
                    <div style="font-size: 0.75rem; color: {theme['text_muted']}; letter-spacing: 1px; font-weight: 600; margin-bottom: 10px;">ACTIVE GESTURE</div>
                    <div style="background: {theme['btn_bg']}; border: 1px solid {theme['btn_border']}; border-radius: 10px; padding: 20px; text-align: center;">
                        <span style="color: {theme['text_main']}; font-weight: 800; font-size: 1.8rem; text-transform: uppercase;">{rubric_gesture}</span>
                    </div>
                </div>

                <div style="border-top: 1px dashed {theme['border']}; padding-top: 20px; margin-bottom: 5px;">
                    {mapping_graph}
                    
                    {history_graph}
                </div>

                {gesture_recognition_html}
                
            </div>
            """.replace('\n', '')
            right_panel_ph.markdown(right_html, unsafe_allow_html=True)
            
            stats_html = f"""
            <div style="background-color: {theme['bg_panel']}; border: 1px solid {theme['border']}; border-radius: 12px; padding: 20px 30px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 10px; font-family: sans-serif; box-shadow: 0 4px 6px {theme['shadow']};">
                <div style="text-align: center; background: {theme['bg_card']}; padding: 15px; border-radius: 8px; border: 1px solid {theme['border']};">
                    <div style="color: {theme['danger']}; font-weight: 700; font-size: 1.5rem;">{current_vol_percent}%</div>
                    <div style="font-size: 0.75rem; color: {theme['text_muted']}; font-weight: 600; margin-top: 5px;">Current Volume</div>
                </div>
                <div style="text-align: center; background: {theme['bg_card']}; padding: 15px; border-radius: 8px; border: 1px solid {theme['border']};">
                    <div style="color: {theme['danger']}; font-weight: 700; font-size: 1.5rem;">{current_distance_mm}mm</div>
                    <div style="font-size: 0.75rem; color: {theme['text_muted']}; font-weight: 600; margin-top: 5px;">Finger Distance</div>
                </div>
                <div style="text-align: center; background: {theme['bg_card']}; padding: 15px; border-radius: 8px; border: 1px solid {theme['border']};">
                    <div style="color: {theme['danger']}; font-weight: 700; font-size: 1.5rem;">{accuracy_pct if hand_count_str != 'Waiting...' else 0}%</div>
                    <div style="font-size: 0.75rem; color: {theme['text_muted']}; font-weight: 600; margin-top: 5px;">Accuracy</div>
                </div>
                <div style="text-align: center; background: {theme['bg_card']}; padding: 15px; border-radius: 8px; border: 1px solid {theme['border']};">
                    <div style="color: {theme['danger']}; font-weight: 700; font-size: 1.5rem;">{latency_ms}ms</div>
                    <div style="font-size: 0.75rem; color: {theme['text_muted']}; font-weight: 600; margin-top: 5px;">Response Time</div>
                </div>
            </div>
            """
            stats_placeholder.markdown(stats_html, unsafe_allow_html=True)

else:
    if st.session_state.camera_obj is not None:
        st.session_state.camera_obj.release()
        st.session_state.camera_obj = None
    video_placeholder.info("System Standby. Click '▶ Start' above to begin.")
