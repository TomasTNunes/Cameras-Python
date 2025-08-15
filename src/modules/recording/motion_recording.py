import os
import threading
import time
from queue import Empty
from modules.recording.recording_manager import RecordingManager
from utils import convert_time_to_datetime
from logger_setup import logger

class MotionRecording(RecordingManager):
    """

    `self.enabled`is always set to True in all MotionRecording instances because this instance is only created
    if motion for the respective camera is enabled.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, target_fps: int, frames_buffer: int):
        """
        Initializes the MotionRecording with config parameters.
        """
        # Check if max_queue_size has to be increased based on frames_buffer
        frames_buffer += 20 # give a margin of at least 20 frames
        max_queue_size = frames_buffer if frames_buffer > 100 else 100

        # Initialize the parent class with config parameters
        super().__init__(camera_name=camera_name,
                         camera_name_norm=camera_name_norm,
                         target_fps=target_fps,
                            max_queue_size=max_queue_size
        )
    
    @property
    def _event(self):
        """
        Returns the if in event.
        """
        return self._ffmpeg_process
    
    def stop(self):
        """
        Stops the MotionRecording manager thread, if enabled is enabled.
        """
        # Call parent stop method
        super().stop()
        if self.enabled:
            logger.info(f"Camera '{self.camera_name}' MotionRecording Manager thread stopped.")

    def start_event(self, frame_time: float):
        """
        Starts a new MotionRecording Event.
        It sets the filename and starts the FFmpeg process.
        """
        if not self._event:
            logger.info(f"Starting Motion Event in camera '{self.camera_name}'.")
            # Get Filename
            if self.encode_to_h264 in [0, 1]:
                ext = 'avi'
            else:
                ext = 'mp4'
            date_str, time_str = convert_time_to_datetime(frame_time)
            filename = f"{self.camera_name_norm}_{date_str}_{time_str}.{ext}"

            # Set `self._current_file_path`
            self._check_file_name(filename)

            # Start FFmpeg process. Open pipe to FFmpeg stdin.
            self._start_ffmpeg()

    def stop_event(self):
        """
        Stops the current MotionRecording Event.
        Waits for dump of the queue to FFmpeg process in _run Thread.
        It stops the FFmpeg process.
        Converts the file to h264 format if configured.
        This method blocks Motion Thread until its fnished, so that no new frames are added to the queue.
        """
        if self._event:
            # Wait to dump the queue to FFmpeg process in _run Thread
            i = 0
            max_timeout = 10 # seconds, avoid infinite loop
            max_index = max_timeout * 10 # 10 iterations per second
            while not self.rec_queue.empty() and i < max_index:
                time.sleep(0.1)
                i+=1
            
            # Warn if queue was not fully dumped and max_timeout was reached
            if not self.rec_queue.empty():
                logger.warning(f"MotionRecording queue was not fully dumped in event '{self._current_file_path}' in camera '{self.camera_name}'. Motion Event might be imcomplete. (Max timeout reached)")
                # Clear the queue, for case it wasn't fully dumped
                self._clear_queue()
            
            # Stop FFmpeg process
            self._stop_ffmpeg()
            logger.info(f"End Motion Event in camera '{self.camera_name}'.")

            # If file exists and config to encode to h264 (=1), convert it to .mp4 in different thread
            if self.encode_to_h264 == 1 and self._current_file_path and os.path.exists(self._current_file_path):
                # Considering changing daemon to False to ensure conversion completes before exiting app
                threading.Thread(target=self._convert_to_h264, args=(self._current_file_path,), daemon=True).start()

    def _run(self):
        """
        To be ran in a separate thread.
        Reads the encoded frames bytes receives from the motion thread.
        Write the encoded frames bytes to the FFmpeg process stdin Pipe.
        """
        logger.info(f"Starting MotionRecording thread for camera '{self.camera_name}' on '{self.output_dir}'.")
        while not self._recorder_stop_event.is_set():
            
            # Read MJPG encoded frame bytes from queue
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