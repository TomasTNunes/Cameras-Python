import threading
from logger_setup import logger
from modules.config import Config
from modules.camera import CameraReader
from modules.recording import RecordingManager

logger.info('Script Running.')

# Load Config from config file
CONFIG = Config(config_file='config.yaml')

# Set RecordingManager Class Config
RecordingManager.setClassConfig(
    save_recording=CONFIG.recordings['save'],
    output_dir=CONFIG.recordings.get('directory', None),
    max_days_to_save=CONFIG.recordings.get('max_days_to_save', None)
)

# Initialize Cameras from Config
CAMERAS = {}
for cam_id, cam_cfg in CONFIG.cameras.items():
    try:
        CAMERA = CameraReader(
            camera_name=cam_cfg['name'],
            camera_name_norm=cam_cfg['normalized_name'],
            camera=cam_cfg['camera'],
            width=cam_cfg['width'],
            height=cam_cfg['height'],
            target_fps=cam_cfg['target_fps'],
            port=cam_cfg['port']
        )
        camera_thread = threading.Thread(
            target=CAMERA.start,
            daemon=True
        )
        camera_thread.start()
        CAMERAS[cam_id] = (CAMERA, camera_thread)
    except Exception as e:
        logger.error(f"{e}")

# Run the main loop to keep the script alive
while True:
    # Close all cameras if 'exit' is input
    command = input()
    if command=='exit' or command=='q':
        logger.info("Manually closing all cameras.")
        for cam_id, (cam, _) in CAMERAS.items():
            cam.stop()
        for cam_id, (_, thread) in CAMERAS.items():
            thread.join()
        break

