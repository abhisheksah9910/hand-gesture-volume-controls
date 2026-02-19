import os
import sys
import streamlit.web.cli as stcli
import streamlit.runtime.scriptrunner.magic_funcs 

# --- FORCE PYINSTALLER TO BUNDLE THESE DEPENDENCIES ---
import cv2
import numpy
import pyautogui
import mediapipe
import pycaw
import comtypes
# ------------------------------------------------------

if __name__ == "__main__":
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, "app.py")
    
    # Fake the command line arguments to start Streamlit
    sys.argv = ["streamlit", "run", app_path, "--global.developmentMode=false"]
    
    # Launch the Streamlit server
    sys.exit(stcli.main())