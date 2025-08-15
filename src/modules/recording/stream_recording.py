import os
import threading
import datetime
from queue import Empty
from modules.recording.recording_manager import RecordingManager
from logger_setup import logger

class StreamRecording(RecordingManager):
    """
    StreamRecording  Sub-Class. Child of RecordingManager.
    Handles video recording from the camera.
    Also manages file rotation and cleanup of old recordings.
    Video Files are saved for every hour.
    The video for the current hour is saved in .avi encoded in MJPG format or .mp4 encoded in h264.
    Afer every hour this .avi file can be converted to .mp4 encoded in h264 format, if config given.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, target_fps: int):
        """
        Initializes the StreamRecording with config parameters.
        """
        # If recording is disabled, skip initialization
        if not self.enabled:
            return

        # Initialize the parent class with config parameters
        super().__init__(camera_name=camera_name,
                         camera_name_norm=camera_name_norm,
                         target_fps=target_fps,
        )

        # StreamRecording Manager Thread Parameters
        self._current_hour = None
    
    def stop(self):
        """
        Stops the StreamRecording manager thread, if enabled is enabled.
        """
        # Call parent stop method
        super().stop()
        if self.enabled:
            logger.info(f"Camera '{self.camera_name}' StreamRecording Manager thread stopped.")
    
    def _run(self):
        """
        To be ran in a separate thread.
        Reads the encoded frames bytes receives from the stream server thread.
        Write the encoded frames bytes to the FFmpeg process stdin Pipe.
        Checks if the file rotation is met.
        """
        logger.info(f"Starting StreamRecording thread for camera '{self.camera_name}' on '{self.output_dir}'.")
        while not self._recorder_stop_event.is_set():

            # Check file rotation condition
            if self._check_file_rotation():
                self._rotate_file()
                threading.Thread(target=self._clean_old_files, daemon=True).start() # Thread to delete old files

            try:
                frame_bytes = self.rec_queue.get(timeout=1) # Encoded frame in JPEG bytes
            except Empty:
                continue
            
            # Write the frame to the FFmpeg process stdin pipe
            if self._ffmpeg_process:
                try:
                    self._ffmpeg_process.stdin.write(frame_bytes)
                except BrokenPipeError:
                    logger.error(f"Error in camera '{self.camera_name}': FFmpeg process pipe broken")
                    self._stop_ffmpeg()
        
        # Clean up on stop
        self._stop_ffmpeg()
    
    def _check_file_rotation(self):
        """
        Checks if the condition for file rotation is met. Returns True if yes.
        Updates `self._current_hour` to current hour if condition is met.
        Condition: Rotate file every new hour.
        """
        now = datetime.datetime.now()
        hour = now.replace(minute=0, second=0, microsecond=0)
        if self._current_hour != hour:
            self._current_hour = hour
            return True
        return False

    def _rotate_file(self):
        """
        Rotates the recording file for the current hour.
        Stops the current FFmpeg process, starts a new one for the next hour.
        Starts Thread to encode the previous file to h264 in .mp4, if required.
        """
        self._stop_ffmpeg()

        # New Filename `name_norm_HHi_HHf_DD_MM_YYYY.ext`
        previous_file_path = self._current_file_path
        next_hour = (self._current_hour.hour + 1) % 24
        if self.encode_to_h264 in [0, 1]:
            ext = 'avi'
        else:
            ext = 'mp4'
        filename = f"{self.camera_name_norm}_{self._current_hour.hour:02d}-{next_hour:02d}_{self._current_hour.day:02d}-{self._current_hour.month:02d}-{self._current_hour.year}.{ext}"
        self._check_file_name(filename)
        logger.info(f"Camera '{self.camera_name}': Rotating recording file for new hour '{self._current_hour}' in '{self._current_file_path}'.")

        # Start new ffmpeg process for current hour file
        self._start_ffmpeg()

        # If previous file exists and config to encode to h264 (=1), convert it to .mp4 in different thread
        if self.encode_to_h264 == 1 and previous_file_path and os.path.exists(previous_file_path):
            # Considering changing daemon to False to ensure conversion completes before exiting app
            threading.Thread(target=self._convert_to_h264, args=(previous_file_path,), daemon=True).start()