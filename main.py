import threading
from logger_setup import logger
from config import Config
from camera import CameraReader

logger.info('Script Running.')

# Load Config from config file
CONFIG = Config(config_file='config.yaml')

# Initialize Cameras from Config
CAMERAS = {}
for cam_id, cam_cfg in CONFIG.cameras.items():
    try:
        CAMERA = CameraReader(
            camera_name=cam_cfg['name'],
            camera=cam_cfg['camera'],
            width=cam_cfg['width'],
            height=cam_cfg['height'],
            target_fps=cam_cfg['target_fps'],
            port=cam_cfg['port']
        )
        camera_stop_event = threading.Event()
        camera_thread = threading.Thread(
            target=CAMERA.start,
            args=(camera_stop_event,),
            daemon=True
        )
        camera_thread.start()
        CAMERAS[cam_id] = (CAMERA, camera_thread, camera_stop_event)
    except Exception as e:
        logger.error(f"{e}")

# Run the main loop to keep the script alive
while True:
    # Close all cameras if 'exit' is input
    command = input()
    if command=='exit' or command=='q':
        logger.info("Manually closing all cameras.")
        for cam_id, (_, _, stop_event) in CAMERAS.items():
            stop_event.set()
        for cam_id, (_, thread, _) in CAMERAS.items():
            thread.join()
        break

