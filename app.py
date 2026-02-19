import streamlit as st
import cv2
import numpy as np
import pyautogui
import time
import threading
import json
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

# --- 1. POSTMAN API SERVER (Runs in background) ---
api_state = {"volume": 0, "gesture": "None", "distance_mm": 0, "finger_count": 0, "mute_status": "Active"}

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
        pass # Suppress terminal spam

def run_api():
    server = HTTPServer(('127.0.0.1', 8000), StatusHandler)
    server.serve_forever()

if "api_thread" not in st.session_state:
    threading.Thread(target=run_api, daemon=True).start()
    st.session_state.api_thread = True

# --- 2. CONFIG & CSS ---
st.set_page_config(page_title="Gestura | Studio", layout="wide", initial_sidebar_state="expanded")
CoInitialize()

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { overflow: hidden !important; background-color: #0a0a0c !important; }
    .block-container { padding: 1rem 2rem 0rem 2rem !important; max-width: 100% !important; }
    header, footer { display: none !important; }
    [data-testid="stVerticalBlock"] { gap: 0 !important; }
    div[data-testid="stImage"] { border-radius: 12px; overflow: hidden; border: 1px solid #26262f; box-shadow: 0 10px 40px rgba(0,0,0,0.6); margin-top: 5px; }
    .app-brand { font-family: -apple-system, sans-serif; font-size: 1.4rem; font-weight: 800; color: #ededed; margin-bottom: 10px; display: flex; align-items: center; }
    .app-brand span { color: #8a8a93; font-weight: 400; font-size: 0.9rem; margin-left: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 3. SIDEBAR CALIBRATION ---
with st.sidebar:
    st.markdown("### ⚙️ Calibration Settings")
    st.markdown("Adjust to fit your hand size and camera distance.")
    min_dist = st.slider("Min Pinch Distance (mm)", 10, 50, 20)
    max_dist = st.slider("Max Pinch Distance (mm)", 50, 200, 100)
    step_vol = st.slider("Volume Step % (Peace/3-Finger)", 2, 20, 10)
    st.markdown("---")
    st.success("📡 **Postman API Live:**\n\n`GET http://127.0.0.1:8000/status`")

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
    # 1. Thumb (Compare tip distance vs knuckle distance to palm base)
    thumb_tip_dist = hypot(hand[4].x - hand[17].x, hand[4].y - hand[17].y)
    thumb_mcp_dist = hypot(hand[2].x - hand[17].x, hand[2].y - hand[17].y)
    fingers.append(1 if thumb_tip_dist > thumb_mcp_dist else 0)
    
    # 2. Index, Middle, Ring, Pinky (Compare tip Y to knuckle Y)
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

with col_center:
    controls_col1, controls_col2 = st.columns([1,1])
    with controls_col1:
        run_camera = st.toggle("⚡ Power On Vision System", value=False)
    with controls_col2:
        st.markdown("<div style='text-align: right; color: #8a8a93; font-size: 0.8rem; margin-top: 10px;'>✌️ Step + | 🖖 Step - | ✊ Mute | 🖐️ Unmute | 🤏 Scale</div>", unsafe_allow_html=True)
    video_placeholder = st.empty()

# --- 5. MAIN LOOP ---
if run_camera:
    cap = cv2.VideoCapture(0)
    
    last_mute_time = 0
    last_gesture_time = 0
    open_palm_counter = 0
    smoothed_dist = 0  
    active_master_label = "None"
    prev_frame_time = time.time()

    while run_camera:
        success, frame = cap.read()
        if not success: break
            
        new_frame_time = time.time()
        fps = int(1 / (new_frame_time - prev_frame_time)) if (new_frame_time - prev_frame_time) > 0 else 0
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
        
        current_vol_percent = round(system_audio.GetMasterVolumeLevelScalar() * 100)
        is_muted = system_audio.GetMute()
        mute_status = "Muted" if is_muted else "Active"

        if result.hand_landmarks:
            hand_count_str = f"{len(result.hand_landmarks)} Detected"
            visible_hands = []
            hand_data_dict = {}
            
            for hand, handedness in zip(result.hand_landmarks, result.handedness):
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
            cv2.putText(frame, f"MASTER: {display_label}", (x4, y4-30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 210, 255), 2)

            # --- RUBRIC: FINGER COUNTING & GESTURE RECOGNITION ---
            fingers = get_finger_state(master_hand)
            finger_count = sum(fingers)
            current_distance_mm = int(hypot(x8 - x4, y8 - y4) * 0.5)

            if finger_count == 0:
                rubric_gesture = "Fist"
            elif finger_count == 5:
                rubric_gesture = "Open Palm"
            elif fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0:
                rubric_gesture = "Peace Sign"
            elif fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 1 and fingers[4] == 0:
                rubric_gesture = "Three Fingers"
            elif fingers[0] == 1 and finger_count == 1:
                rubric_gesture = "Thumb Up"
            elif current_distance_mm <= max_dist and finger_count <= 2:
                rubric_gesture = "Pinch"

            # --- RUBRIC: ACTION EXECUTION ---
            
            # 1. Mute (Fist)
            if rubric_gesture == "Fist" and now - last_mute_time > 1.0:
                if mute_status == "Active":
                    pyautogui.press('volumemute')
                    last_mute_time = now

            # 2. Unmute (Open Palm with 15-frame debounce)
            if rubric_gesture == "Open Palm":
                open_palm_counter += 1
                if open_palm_counter >= 15:
                    if mute_status == "Muted":
                        pyautogui.press('volumemute')
                    open_palm_counter = 0
            else:
                open_palm_counter = 0

            # 3. Step Up (Peace Sign)
            if rubric_gesture == "Peace Sign" and now - last_gesture_time > 0.8:
                steps = step_vol // 2
                pyautogui.press('volumeup', presses=steps)
                last_gesture_time = now

            # 4. Step Down (Three Fingers)
            if rubric_gesture == "Three Fingers" and now - last_gesture_time > 0.8:
                steps = step_vol // 2
                pyautogui.press('volumedown', presses=steps)
                last_gesture_time = now

            # 5. Absolute Mapping (Pinch)
            if rubric_gesture == "Pinch":
                if smoothed_dist == 0: smoothed_dist = current_distance_mm
                else: smoothed_dist = (0.35 * current_distance_mm) + (0.65 * smoothed_dist)
                
                target_vol = int(np.interp(smoothed_dist, [min_dist, max_dist], [0, 100]))
                diff = target_vol - current_vol_percent
                
                if abs(diff) >= 2:
                    steps = abs(diff) // 2  
                    if diff > 0: pyautogui.press('volumeup', presses=steps)
                    else: pyautogui.press('volumedown', presses=steps)
                    current_vol_percent = round(system_audio.GetMasterVolumeLevelScalar() * 100)

            cv2.line(frame, (x4, y4), (x8, y8), (200, 0, 200), 3)
            cv2.putText(frame, f"{current_distance_mm}mm", ((x4+x8)//2, (y4+y8)//2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        else:
            active_master_label = "None"
            smoothed_dist = 0
            open_palm_counter = 0

        # --- UPDATE API ---
        api_state["volume"] = current_vol_percent
        api_state["gesture"] = rubric_gesture
        api_state["distance_mm"] = current_distance_mm
        api_state["finger_count"] = finger_count
        api_state["mute_status"] = mute_status

        # --- RENDER HUD ---
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        video_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)
        
        mute_bg = "#ef444420" if mute_status == "Muted" else "#10b98120"
        mute_border = "#ef4444" if mute_status == "Muted" else "#10b981"
        mute_color = "#ef4444" if mute_status == "Muted" else "#10b981"
        mute_text = "AUDIO MUTED" if mute_status == "Muted" else "AUDIO ACTIVE"
        vol_bar_color = "#3f3f46" if mute_status == "Muted" else "linear-gradient(to right, #10b981, #34d399)"

        left_html = f"""
        <div style="background-color: #121216; border: 1px solid #26262f; border-radius: 12px; padding: 25px; height: 80vh; display: flex; flex-direction: column; font-family: sans-serif;">
            <div style="font-size: 0.75rem; color: #8a8a93; letter-spacing: 1px; font-weight: 600; margin-bottom: 15px;">AI ENGINE</div>
            <div style="background: #0a0a0c; border: 1px solid #26262f; border-radius: 8px; padding: 15px; margin-bottom: 10px; display: flex; justify-content: space-between;">
                <span style="color: #8a8a93; font-size: 0.9rem;">Detection</span><span style="color: #fff; font-weight: 600;">{hand_count_str}</span>
            </div>
            <div style="background: #0a0a0c; border: 1px solid #26262f; border-radius: 8px; padding: 15px; margin-bottom: 30px; display: flex; justify-content: space-between;">
                <span style="color: #8a8a93; font-size: 0.9rem;">Active Hand</span><span style="color: #00d2ff; font-weight: 700;">{display_label}</span>
            </div>
            <div style="flex-grow: 1; display: flex; flex-direction: column;">
                <div style="font-size: 0.75rem; color: #8a8a93; letter-spacing: 1px; font-weight: 600; margin-bottom: 15px;">MASTER OUTPUT</div>
                <div style="background: #0a0a0c; border: 1px solid #26262f; border-radius: 8px; padding: 25px 20px; flex-grow: 1; display: flex; flex-direction: column; justify-content: center; align-items: center;">
                    <div style="font-size: 3rem; color: #fff; font-weight: 700; font-family: monospace; line-height: 1;">{current_vol_percent}%</div>
                    <div style="width: 100%; height: 8px; background: #1e1e24; border-radius: 4px; margin: 20px 0; overflow: hidden;">
                        <div style="width: {current_vol_percent}%; height: 100%; background: {vol_bar_color}; transition: width 0.1s;"></div>
                    </div>
                    <div style="width: 100%; text-align: center; padding: 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; letter-spacing: 1px; background: {mute_bg}; border: 1px solid {mute_border}; color: {mute_color};">{mute_text}</div>
                </div>
            </div>
        </div>
        """.replace('\n', '')
        left_panel_ph.markdown(left_html, unsafe_allow_html=True)

        # Dynamic distance bar scale based on user's calibrated max_dist
        fill_pct = min((current_distance_mm / max_dist) * 100, 100) if max_dist > 0 else 0
        
        right_html = f"""
        <div style="background-color: #121216; border: 1px solid #26262f; border-radius: 12px; padding: 25px; height: 80vh; display: flex; flex-direction: column; font-family: sans-serif;">
            <div style="font-size: 0.75rem; color: #8a8a93; letter-spacing: 1px; font-weight: 600; margin-bottom: 15px;">DISTANCE TRACKER</div>
            <div style="background: #0a0a0c; border: 1px solid #26262f; border-radius: 8px; padding: 25px 20px; text-align: center; margin-bottom: 25px;">
                <div style="font-size: 3.5rem; color: #8a2be2; font-weight: 700; line-height: 1;">{current_distance_mm}</div>
                <div style="font-size: 0.75rem; color: #8a8a93; letter-spacing: 2px; margin-top: 5px; margin-bottom: 20px;">MILLIMETERS</div>
                <div style="width: 100%; height: 6px; background: #1e1e24; border-radius: 3px; overflow: hidden;">
                    <div style="width: {fill_pct}%; height: 100%; background: linear-gradient(90deg, #8a2be2, #a855f7); transition: width 0.1s;"></div>
                </div>
            </div>
            <div style="flex-grow: 1;">
                <div style="font-size: 0.75rem; color: #8a8a93; letter-spacing: 1px; font-weight: 600; margin-bottom: 15px;">ACTIVE GESTURE</div>
                <div style="background: rgba(138, 43, 226, 0.15); border: 1px solid #8a2be2; border-radius: 8px; padding: 15px; text-align: center; margin-bottom: 15px; box-shadow: 0 0 15px rgba(138,43,226,0.2);">
                    <span style="color: #fff; font-weight: 800; font-size: 1.5rem; text-transform: uppercase;">{rubric_gesture}</span>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <span style="background: #1e1e24; border: 1px solid #26262f; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; color: #94a3b8; font-weight: 600;">✌️ +{step_vol}% Vol</span>
                    <span style="background: #1e1e24; border: 1px solid #26262f; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; color: #94a3b8; font-weight: 600;">🖖 -{step_vol}% Vol</span>
                    <span style="background: #1e1e24; border: 1px solid #26262f; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; color: #94a3b8; font-weight: 600;">✊ Mute</span>
                    <span style="background: #1e1e24; border: 1px solid #26262f; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; color: #94a3b8; font-weight: 600;">🖐️ Unmute</span>
                    <span style="background: #1e1e24; border: 1px solid #26262f; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; color: #94a3b8; font-weight: 600;">🤏 Scale</span>
                </div>
            </div>
            <div style="border-top: 1px solid #26262f; padding-top: 15px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 0.75rem; color: #8a8a93; font-weight: 600;">SYSTEM FPS</span><span style="color: #00d2ff; font-weight: 700; font-family: monospace; font-size: 1.1rem;">{fps}</span>
            </div>
        </div>
        """.replace('\n', '')
        right_panel_ph.markdown(right_html, unsafe_allow_html=True)

    cap.release()
else:
    video_placeholder.info("System Standby. Enable the toggle above to begin.")