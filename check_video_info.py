"""
Checks Video File info (fps, frames, duration)
Useful to Debug RecordingManager Class Module.
"""

import cv2

video_path = '/home/tomas/GitHub/Cameras-Python/data/recording/laptop/laptop_01_02_26_07_2025.mp4'

cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("Error: Cannot open video file.")
else:
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)

    duration = total_frames / fps if fps > 0 else 0

    print(f"FPS: {fps}")
    print(f"Total frames: {total_frames}")
    print(f"Duration: {duration:.2f} seconds ({int(duration//60)}m{duration%60:.2f}s)")

cap.release()
