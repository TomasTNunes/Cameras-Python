import yaml
import os
import cv2
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
        self._validate_config()
    
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

        if not isinstance(max_size, int) or max_size < 1:
            raise ValueError("'max_size' must be an integer >= 1.")

        if not isinstance(max_files, int) or max_files < 1:
            raise ValueError("'max_files' must be an integer >= 1.")

        check_create_directory(log_dir)
        setup_logger_file(log_dir, max_size, max_files)
        logger.info('----------------------------------------------------------------------') # first log to be written in log file after StartUp, if logs saving is enabled
        logger.info('---------------------- Application Initiated -------------------------')
        logger.info('----------------------------------------------------------------------')
        logger.info('Logs saving is enabled.')
    
    def _validate_config(self):
        """
        Validate the configuration from cofig file.
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
                required_fields = ['camera', 'name', 'target_fps', 'port', 'show_fps']
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
                    if not isinstance(value, int) or value <= 0:
                        raise ValueError(f"'{field}' must be a positive integer")

                port = cam_cfg['port']
                if port in seen_ports:
                    raise ValueError(f"Duplicate port number: {port}")
                seen_ports.append(port)

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
                            if not isinstance(val, int) or val <= 0:
                                raise ValueError(f"'{dim}' must be a positive integer")
                            prop = cv2.CAP_PROP_FRAME_WIDTH if dim == 'width' else cv2.CAP_PROP_FRAME_HEIGHT
                            cap.set(prop, val)
                            actual = int(cap.get(prop))
                            if actual != val:
                                raise ValueError(f"'{dim}' '{val}' not supported by camera")
                    
                    if 'source_fps' in cam_cfg:
                        fps = cam_cfg['source_fps']
                        if not isinstance(fps, int) or fps <= 0:
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

            if not isinstance(rec_dir, str):
                logger.error("'directory' must be a string.")
                raise TypeError("'directory' must be a string")

            if not isinstance(max_days, int) or max_days < 1:
                logger.error("'max_days_to_save' must be an integer >= 1")
                raise ValueError("'max_days_to_save' must be an integer >= 1")

            check_create_directory(rec_dir)
            self._recordings['directory'] = rec_dir
            self._recordings['max_days_to_save'] = max_days
            logger.info("Cameras recordings are enabled.")
    
        
        