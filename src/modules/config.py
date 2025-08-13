import yaml
import cv2
import subprocess
from types import MappingProxyType
from logger_setup import setup_logger_file, logger
from utils import check_create_directory

class Config:
    """
    Loads the configuration from a YAML file and provides access to the configuration values.
    Also configures the logger based on the configuration.
    Before setup_logger() is called, logs are only shown in terminal.
    """

    def __init__(self, config_file: str):
        """
        Initializes the Config class with the path to the configuration file.
        """
        self.config_file = config_file
        self.config = self._load_config()
        logger.info('Config File Loaded.')
        self._configure_logger()
        self._cameras = {}
        self._recordings = {}
        self._motion = {}
        self._validate_cameras_config()
        self._validate_recordings_config()
        self._validate_motion_config()
    
    @property
    def cameras(self):
        """
        Returns the read-only cameras configuration.
        """
        return MappingProxyType(self._cameras)
    
    @property
    def recordings(self):
        """
        Returns the read-only recordings configuration.
        """
        return MappingProxyType(self._recordings)
    
    @property
    def motion(self):
        """
        Returns the read-only motion configuration.
        """
        return MappingProxyType(self._motion)

    def _load_config(self):
        """
        Load the configuration from the YAML file.
        """
        with open(self.config_file, 'r') as file:
            try:
                return yaml.safe_load(file)
            except yaml.YAMLError as e:
                logger.error(f"Error loading configuration file: {e}")
                raise(f"Error loading configuration file: {e}")
                
    def _configure_logger(self):
        """
        Configure the logger based on the loaded configuration.
        Validates Logs configuration from cofig file.
        """
        # Validate Logs config
        logs_cfg = self.config.get('Logs', {})

        if 'save' not in logs_cfg:
            raise ValueError("'save' key is missing in Logs config.")
        
        save_flag = logs_cfg['save']
        if not isinstance(save_flag, bool):
            raise TypeError("'save' in Logs config must be a boolean")

        if not save_flag:
            logger.warning("Logs saving is disabled.")
            return
        
        log_dir = logs_cfg.get('directory')
        max_size = logs_cfg.get('max_size')
        max_files = logs_cfg.get('max_files')

        if not isinstance(log_dir, str):
            raise TypeError("'directory' in Logs config must be a string.")

        if not isinstance(max_size, int) or max_size < 1 or isinstance(max_size, bool):
            raise ValueError("'max_size' must be an integer >= 1.")

        if not isinstance(max_files, int) or max_files < 1 or isinstance(max_files, bool):
            raise ValueError("'max_files' must be an integer >= 1.")

        check_create_directory(log_dir)
        setup_logger_file(log_dir, max_size, max_files)
        logger.info('----------------------------------------------------------------------') # first log to be written in log file after StartUp, if logs saving is enabled
        logger.info('---------------------- Application Initiated -------------------------')
        logger.info('----------------------------------------------------------------------')
        logger.info('Logs saving is enabled.')
    
    def _validate_cameras_config(self):
        """
        Validate the Cameras configuration from cofig file.
        """
        # Validate Cameras
        cameras = self.config.get('Cameras', {})
        if not cameras:
            logger.warning("No camera configurations found.")
            return

        seen_names = []
        seen_ports = []

        for cam_id, cam_cfg in cameras.items():
            try:
                required_fields = ['camera', 'name', 'target_fps', 'port', 'stream_quality', 'show_fps']
                for field in required_fields:
                    if field not in cam_cfg:
                        raise ValueError(f"Missing required field '{field}'")

                name = cam_cfg['name']
                if not isinstance(name, str):
                    raise TypeError("'name' must be a string")
                if name in seen_names:
                    raise ValueError(f"Duplicate camera name: '{name}'")
                seen_names.append(name)

                for field in ['target_fps', 'port']:
                    value = cam_cfg[field]
                    if not isinstance(value, int) or value <= 0 or isinstance(value, bool):
                        raise ValueError(f"'{field}' must be a positive integer")

                port = cam_cfg['port']
                if port in seen_ports:
                    raise ValueError(f"Duplicate port number: {port}")
                seen_ports.append(port)

                stream_quality = cam_cfg['stream_quality']
                if not isinstance(stream_quality, int) or stream_quality < 0 or stream_quality > 100 or isinstance(stream_quality, bool):
                    raise ValueError(f"'stream_quality' must be an integer between 0 and 100.")

                show_fps = cam_cfg['show_fps']
                if not isinstance(show_fps, bool):
                    raise TypeError("'show_fps' must be a boolean")

                cam_path = cam_cfg['camera']
                if not isinstance(cam_path, str) and not isinstance(cam_path, int):
                    raise TypeError("'camera' must be a string or int")
                
                try:
                    cap = cv2.VideoCapture(cam_path)
                    if not cap.isOpened():
                        raise ValueError(f"Cannot open camera device '{cam_path}'")
                    
                    # Optional Parameters
                    if 'source_format' in cam_cfg:
                        fmt = cam_cfg['source_format']
                        if not isinstance(fmt, str) or len(fmt) != 4:
                            raise TypeError("'source_format' must be a 4-character string")
                        fourcc_code = cv2.VideoWriter_fourcc(*fmt)
                        cap.set(cv2.CAP_PROP_FOURCC, fourcc_code)
                        actual_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
                        actual_fmt = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
                        if actual_fmt != fmt:
                            raise ValueError(f"'source_format' '{fmt}' not supported by camera")
                    
                    for dim in ['width', 'height']:
                        if dim in cam_cfg:
                            val = cam_cfg[dim]
                            if not isinstance(val, int) or val <= 0 or isinstance(val, bool):
                                raise ValueError(f"'{dim}' must be a positive integer")
                            prop = cv2.CAP_PROP_FRAME_WIDTH if dim == 'width' else cv2.CAP_PROP_FRAME_HEIGHT
                            cap.set(prop, val)
                            actual = int(cap.get(prop))
                            if actual != val:
                                raise ValueError(f"'{dim}' '{val}' not supported by camera")
                    
                    if 'source_fps' in cam_cfg:
                        fps = cam_cfg['source_fps']
                        if not isinstance(fps, int) or fps <= 0 or isinstance(fps, bool):
                            raise ValueError("'source_fps' must be a positive integer")
                        cap.set(cv2.CAP_PROP_FPS, fps)
                        actual_fps = cap.get(cv2.CAP_PROP_FPS)
                        if actual_fps != fps:
                            raise ValueError(f"'source_fps' '{fps}' not supported by camera")
                        if actual_fps < 1:
                            logger.warning(f"Camera '{name}' may not report FPS correctly (got {actual_fps}). Continuing anyway.")
                        elif abs(actual_fps - fps) > 1:
                            raise ValueError(f"'source_fps' '{fps}' not supported by camera")
                finally:
                    cap.release()

                self._cameras[cam_id] = cam_cfg
                self._cameras[cam_id]['normalized_name'] = name.lower().replace(' ', '_')
                logger.info(f"Camera '{cam_cfg['name']}' successfully loaded.")

            except Exception as e:
                logger.error(f"Error in camera with id '{cam_id}': {e}.")
                logger.warning(f"Camera with id '{cam_id}' will not be loaded.")

    def _validate_recordings_config(self):
        """
        Validate the Recordings configuration from cofig file.
        """
        # Validate Recordings
        rec_cfg = self.config.get('Recordings', {})
        
        if 'save' not in rec_cfg:
            logger.error("'save' key is missing in Recordings config.")
            raise ValueError("'save' key is missing in Recordings config.")
        
        save_flag = rec_cfg['save']
        if not isinstance(save_flag, bool):
            logger.error("'save' in Recordings config must be a boolean.")
            raise TypeError("'save' in Recordings config must be a boolean")

        self._recordings['save'] = save_flag

        if not save_flag:
            logger.warning("Cameras recordings are disabled.")
        else:
            rec_dir = rec_cfg.get('directory')
            max_days = rec_cfg.get('max_days_to_save')
            encode_to_h264 = rec_cfg.get('encode_to_h264')

            if not isinstance(rec_dir, str):
                logger.error("'directory' must be a string in Recordings config.")
                raise TypeError("'directory' must be a string in Recordings config.")
            self._recordings['directory'] = rec_dir

            if not isinstance(max_days, int) or max_days < 1 or isinstance(max_days, bool):
                logger.error("'max_days_to_save' must be an integer >= 1 in Recordings config.")
                raise ValueError("'max_days_to_save' must be an integer >= 1 in Recordings config.")
            self._recordings['max_days_to_save'] = max_days
            
            if not isinstance(encode_to_h264, int) or encode_to_h264 not in [0,1,2] or isinstance(encode_to_h264, bool):
                logger.error("'encode_to_h264' must be an integer equal to 0, 1, or 2 in Recordings config.")
                raise ValueError("'encode_to_h264' must be an integer equal to 0, 1, or 2 in Recordings config.")
            self._recordings['encode_to_h264'] = encode_to_h264
            
            if encode_to_h264 in [1, 2]:
                h264_encoder = rec_cfg.get('h264_encoder')
                bitrate = rec_cfg.get('bitrate')

                if not isinstance(h264_encoder, str):
                    logger.error("'h264_encoder' must be a string in Recordings config.")
                    raise TypeError("'h264_encoder' must be a string in Recordings config.")
                self._test_h264_encoder(h264_encoder)
                self._recordings['h264_encoder'] = h264_encoder

                if not isinstance(bitrate, int) or bitrate < 1 or isinstance(bitrate, bool):
                    logger.error("'bitrate' must be an integer >= 1 in Recordings config.")
                    raise ValueError("'bitrate' must be an integer >= 1 in Recordings config.")
                self._recordings['bitrate'] = bitrate

            check_create_directory(rec_dir)
            logger.info("Cameras recordings are enabled.")
    
    def _validate_motion_config(self):
        """
        Validate the Motion configuration from cofig file.
        """
        # Validate Motion
        motion_cfg = self.config.get('Motion', {})

        # Get Motion config keys list
        motion_keys = list(motion_cfg.keys())

        # Get loaded cameras id list
        loaded_cameras_id = list(self._cameras.keys())

        # Iterate over loaded cameras id list
        for camid in loaded_cameras_id:
            camera_name = self._cameras[camid]['name']
            if camid not in motion_keys:
                logger.warning(f"Motion config not found for camera '{camera_name}'. Motion will be disabled for this camera.")
            else:
                try:
                    cam_motion_cfg = motion_cfg.get(camid, {})

                    if 'enabled' not in cam_motion_cfg:
                        raise ValueError("'enabled' key is missing")
                    enabled_flag = cam_motion_cfg['enabled']
                    if not isinstance(enabled_flag, bool):
                        raise TypeError("'enabled' must be a boolean")
                    
                    if not enabled_flag:
                        logger.warning(f"Motion for camera '{camera_name}' is disabled.")
                        continue

                    noise_level = cam_motion_cfg.get('noise_level')
                    pixel_threshold = cam_motion_cfg.get('pixel_threshold')
                    object_threshold = cam_motion_cfg.get('object_threshold')
                    minimum_motion_frames = cam_motion_cfg.get('minimum_motion_frames')
                    pre_capture = cam_motion_cfg.get('pre_capture')
                    post_capture = cam_motion_cfg.get('post_capture')
                    event_gap = cam_motion_cfg.get('event_gap')

                    if not isinstance(noise_level, int) or noise_level < 1 or noise_level > 255 or isinstance(noise_level, bool):
                        raise ValueError("'noise_level' must be an integer between 1-255")
                    
                    if not isinstance(pixel_threshold, float) or pixel_threshold <= 0 or pixel_threshold >= 100 or isinstance(pixel_threshold, bool):
                        raise ValueError("'pixel_threshold' must be a float between 0 and 100 %.")
                    
                    if not isinstance(object_threshold, float) or object_threshold <= 0 or object_threshold >= 100 or isinstance(object_threshold, bool):
                        raise ValueError("'object_threshold' must be a float between 0 and 100 %.")
                    
                    if not isinstance(minimum_motion_frames, int) or minimum_motion_frames < 1 or isinstance(minimum_motion_frames, bool):
                        raise ValueError("'minimum_motion_frames' must be a positive integer.")

                    if not isinstance(pre_capture, int) or pre_capture < 0 or isinstance(pre_capture, bool):
                        raise ValueError("'pre_capture' must be a non-negative integer.")

                    if not isinstance(post_capture, int) or post_capture < 0 or isinstance(post_capture, bool):
                        raise ValueError("'post_capture' must be a non-negative integer.")

                    if not isinstance(event_gap, int) or event_gap < 0 or isinstance(event_gap, bool):
                        raise ValueError("'event_gap' must be a non-negative integer.")

                    self._motion[camid] = cam_motion_cfg
                    logger.info(f"Motion for camera '{camera_name}' enabled.")
                except Exception as e:
                    logger.error(f"Error in motion config for camera '{camera_name}': {e}.")
                    logger.warning(f"Motion for camera '{camera_name}' will be disabled.")
                finally:
                    motion_keys.remove(camid)
        
        # Necessary motion configs if at least one motion is active
        required_fields = ['directory', 'max_days_to_save', 'encode_to_h264']
        [motion_keys.remove(k) for k in required_fields if k in motion_keys]
        [motion_keys.remove(k) for k in ['h264_encoder', 'bitrate'] if k in motion_keys]
        if self._motion:
            for field in required_fields:
                if field not in motion_cfg:
                    logger.error(f"Error in motion config: Missing required field '{field}'.")
                    raise ValueError(f"Error in motion config: Missing required field '{field}'.")
        
            # Check required fields
            motion_dir = motion_cfg.get('directory')
            max_days = motion_cfg.get('max_days_to_save')
            encode_to_h264 = motion_cfg.get('encode_to_h264')

            if not isinstance(motion_dir, str):
                logger.error("'directory' must be a string in Motion config.")
                raise TypeError("'directory' must be a string in Motion config.")
            self._motion['directory'] = motion_dir

            if not isinstance(max_days, int) or max_days < 1 or isinstance(max_days, bool):
                logger.error("'max_days_to_save' must be an integer >= 1 in Motion config.")
                raise ValueError("'max_days_to_save' must be an integer >= 1 in Motion config.")
            self._motion['max_days_to_save'] = max_days

            if not isinstance(encode_to_h264, int) or encode_to_h264 not in [0,1,2] or isinstance(encode_to_h264, bool):
                logger.error("'encode_to_h264' must be an integer equal to 0, 1, or 2 in Motion config.")
                raise ValueError("'encode_to_h264' must be an integer equal to 0, 1, or 2 in Motion config.")
            self._motion['encode_to_h264'] = encode_to_h264

            if encode_to_h264 in [1, 2]:
                h264_encoder = motion_cfg.get('h264_encoder')
                bitrate = motion_cfg.get('bitrate')

                if not isinstance(h264_encoder, str):
                    logger.error("'h264_encoder' must be a string in Motion config.")
                    raise TypeError("'h264_encoder' must be a string in Motion config.")
                self._test_h264_encoder(h264_encoder)
                self._motion['h264_encoder'] = h264_encoder

                if not isinstance(bitrate, int) or bitrate < 1 or isinstance(bitrate, bool):
                    logger.error("'bitrate' must be an integer >= 1 in Motion config.")
                    raise ValueError("'bitrate' must be an integer >= 1 in Motion config.")
                self._motion['bitrate'] = bitrate

            check_create_directory(motion_dir)
        
        # Give warning about motion config for cameras id that were not loaded
        for nonloadcamid in motion_keys:
            logger.warning(f"Motion config given for non-loaded camera with id '{nonloadcamid}'.")
    
    @staticmethod
    def _test_h264_encoder(h264_encoder: str):
        """
        Checks if h264 encoder is supported by the machine and test if it runs.
        Also indirectly checks if ffmpeg is installed or in PATH.
        """
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            if not any(h264_encoder in line and '(codec h264)' in line for line in result.stdout.splitlines()):
                raise ValueError(f"'{h264_encoder}' h264_encoder is not supported on this machine.")
        except FileNotFoundError:
            logger.error("ffmpeg is not installed or not in PATH.")
            raise
        except Exception as e:
            logger.error(f"Error in ffmpeg or 'h264_encoder': {e}")
            raise

        try:
            if h264_encoder == 'h264_vaapi':
                test_command = [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-f', 'lavfi',
                    '-i', 'testsrc=duration=1:size=256x144:rate=5',
                    '-vaapi_device', '/dev/dri/renderD128',
                    '-vf', 'format=nv12,hwupload',
                    '-c:v', h264_encoder,
                    '-f', 'null',
                    '-'
                ]
            else:
                test_command = [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-f', 'lavfi',
                    '-i', 'testsrc=duration=1:size=128x128:rate=5',
                    '-c:v', h264_encoder,
                    '-f', 'null',
                    '-'
                ]
            subprocess.run(test_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except Exception as e:
            logger.error(f"Error with h264_encoder '{h264_encoder}': {e}")
            raise