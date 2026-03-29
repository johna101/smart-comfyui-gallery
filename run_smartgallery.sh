#!/bin/bash


# --- CONFIGURATION ---
# REPLACE these paths with your actual folders.
export BASE_OUTPUT_PATH="/Volumes/Titan/Files/comfyui-images/arch-comfyui-output-2025-01-16"
export BASE_INPUT_PATH="/Volumes/Titan/Files/comfyui-images/"
export BASE_SMARTGALLERY_PATH="/Volumes/Titan/Files/comfyui-images/smart-gallerysmart-gallery"
export FFPROBE_MANUAL_PATH="/usr/bin/ffprobe"
export SERVER_HOST="192.168.1.10"
export SERVER_PORT=8189

# --- START ---
python run.py
