import os
from queue import Queue
from logger_setup import logger
from utils import check_create_directory

class RecordingManager:
    """
    RecordingManager Module Class.
    Handles video recording from the camera.
    Also manages file rotation and cleanup of old recordings.
    """

    # Class Variables for all instances
    save_recording = False
    output_dir = None
    max_days_to_save = None

    def __init__(self, camera_name: str, camera_name_norm: str):
        """
        Initializes the VideoRecorder with config parameters.
        """
        self.camera_name = camera_name
        self.camera_name_norm = camera_name_norm

        # If save_recording is enabled
        if self.save_recording:

            # Set output directory for this camera
            self.output_dir = os.path.join(self.output_dir, self.camera_name_norm)
            check_create_directory(self.output_dir)

            # Initialize recording encoded frames queue 
            max_rec_queue_size = 100  # Allow some buffer for frames for stream (lower this if RAM usage is too high) (encoded frames are lite)
            self.rec_queue = Queue(maxsize=max_rec_queue_size)
    
    @classmethod
    def setClassConfig(cls, save_recording: bool, output_dir: str = None, max_days_to_save: int = None):
        """
        Set the shared configs across all instances of this class.
        To be called before any instance is created.
        """
        cls.save_recording = save_recording
        cls.output_dir = output_dir
        cls.max_days_to_save = max_days_to_save
    
    def write(self, frame: bytes):
        """
        Writes a encoded frame to the recording queue, if save_recording is enabled.
        If the queue is full, the frame is dropped.
        """
        if self.save_recording:
            try:
                self.rec_queue.put_nowait(frame)
            except:
                pass  # Drop frame if queue is full 
    
    def start(self):
        """
        """
        logger.info(f"Starting recording thread for camera '{self.camera_name}' on '{self.output_dir}'.")


    def stop(self):
        """
        """
        pass
    
    def _rotate_file(self):
        """
        """
        pass

    def _clean_old_files(self):
        """
        """



