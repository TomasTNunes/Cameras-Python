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
    max_days_to_save=CONFIG.recordings.get('max_days_to_save', None),
    encode_to_h264=CONFIG.recordings.get('encode_to_h264', None),
    h264_encoder=CONFIG.recordings.get('h264_encoder', None),
    bitrate=CONFIG.recordings.get('bitrate', None)
)

# Initialize Cameras from Config
CAMERAS = {}
for cam_id, cam_cfg in CONFIG.cameras.items():
    try:
        CAMERA = CameraReader(
            camera_name=cam_cfg['name'],
            camera_name_norm=cam_cfg['normalized_name'],
            camera=cam_cfg['camera'],
            target_fps=cam_cfg['target_fps'],
            port=cam_cfg['port'],
            stream_quality=cam_cfg['stream_quality'],
            show_fps=cam_cfg['show_fps'],
            source_format=cam_cfg.get('source_format', None),
            width=cam_cfg.get('width', None),
            height=cam_cfg.get('height', None),
            source_fps=cam_cfg.get('source_fps', None),
            motion_enabled=CONFIG.motion.get(cam_id, {}).get('enabled', None),
            noise_level=CONFIG.motion.get(cam_id, {}).get('noise_level', None),
            pixel_threshold_pct=CONFIG.motion.get(cam_id, {}).get('pixel_threshold', None),
            object_threshold_pct=CONFIG.motion.get(cam_id, {}).get('object_threshold', None),
            minimum_motion_frames=CONFIG.motion.get(cam_id, {}).get('minimum_motion_frames', None),
            pre_capture=CONFIG.motion.get(cam_id, {}).get('pre_capture', None),
            post_capture=CONFIG.motion.get(cam_id, {}).get('post_capture', None),
            event_gap=CONFIG.motion.get(cam_id, {}).get('event_gap', None)
        )
        CAMERA.start() # Start camera thread
        CAMERAS[cam_id] = CAMERA
    except Exception as e:
        logger.error(f"{e}")

# Run the main loop to keep the script alive
while True:
    # Close all cameras if 'exit' is input
    command = input()
    if command=='exit' or command=='q':
        logger.info("Manually closing all cameras.")
        for cam_id, cam in CAMERAS.items():
            cam.stop()
        break

