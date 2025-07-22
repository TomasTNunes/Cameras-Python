import cv2
from logger_setup import logger
import time
import threading
from queue import Queue
from modules.stream import StreamServer

class CameraReader:
    """
    Camera Module Class.
    Handles camera initialization, frame reading and continiously feeding it to Processing and Stream Modules.
    Also provides methods to draw clock and FPS on frames.
    Frame Reading using time-based throttling, reading all frames but displaying at a fixed rate.
    Designed to be used with OpenCV.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, camera: str, 
                 target_fps: int, port: int, source_format: str = None,
                 width: int = None, height: int = None, source_fps: int = None):
        """
        Initializes the CameraReader with camera parameters.
        """
        self.camera_name = camera_name
        self.target_fps = target_fps
        self.target_frame_interval = 1.0 / target_fps

        # Camera Thread Stop event
        self._camera_stop_event = threading.Event()

        # Initialize camera capture
        self.cap = cv2.VideoCapture(camera)
        if not self.cap.isOpened():
            raise(f"Could not open camera '{camera_name}'({camera}).")
        else:
            logger.info(f"Camera '{camera_name}' opened successfully.")
        if source_format:
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*source_format))
        if width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if source_fps:
            self.cap.set(cv2.CAP_PROP_FPS, source_fps)

        # Initialize StreamServer Class Module and Thread
        self.stream_server = StreamServer(camera_name, camera_name_norm, port)
        self.stream_thread = threading.Thread(target=self.stream_server.start, daemon=True)

        # Initialize motion frames queue
        # max_motion_queue_size = 10  # Allow some buffer for frames for stream (lower this if RAM usage is too high)
        # self.motion_frame_queue = Queue(maxsize=max_motion_queue_size)
    
    def start(self):
        """
        Reads all frames from the camera, but only feeds the targeted frames to the processing and stream modules (respective queues).
        Starts Stream Thread and Motion Process.
        Uses time-based throttling.
        """
        actual_fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
        actual_fmt = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
        source_fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        logger.info(f"Starting camera '{self.camera_name}' frame reader thread. \
(Source_Format: {actual_fmt}, Source_FPS: {source_fps}, \
Target_FPS: {self.target_fps}, Width: {int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))}, \
Height: {int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})")
        self.stream_thread.start() # Start streaming thread
        last_display_time = time.time()

        # Compute sleep time based on source FPS
        if source_fps and source_fps >= 1:
            sleep_time = 1 / source_fps / 2  # Sleep half the time to allow for processing
        else:
            sleep_time = 0.005 # Sleep 5ms (default) to prevent high CPU usage (for 30 fps camera new frames are available every ~33ms)
        
        while not self._camera_stop_event.is_set():
            # Read frame from camera (always read in BGR, independent from source format)
            ret, frame = self.cap.read()
            if not ret:
                logger.error(f"Camera '{self.camera_name}' read failed.")
                break
            now = time.time()
            
            # Time-based throttling
            if now - last_display_time >= self.target_frame_interval:
                last_display_time = now
                frame = self._draw_frame_info(frame)

                # Write raw frame to stream server queue
                self.stream_server.write(frame)
            
            time.sleep(sleep_time)  # Sleep to reduce CPU usage

        # Close camera and release resources
        self._close_camera_reader()
    
    def stop(self):
        """
        Stops the camera reader thread, and child threads (stream, motion, etc).
        """
        self._camera_stop_event.set()

    def _close_camera_reader(self):
        """
        Releases the camera and closes correspondant OpenCV windows.
        """
        if self.cap.isOpened():
            self.cap.release()
            logger.info(f"Camera '{self.camera_name}' released.")

    def _draw_frame_info(self, frame):
        """
        Draws the date and time (with milliseconds) in the bottom-right corner,
        and the camera name in the top-left corner, styled like a vigilance system.
        """
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 2
        
        # Colors: bright green with black shadow for vigilance style
        text_color = (0, 255, 0)  # bright green
        shadow_color = (0, 0, 0)  # black shadow
        
        # Get current time with milliseconds
        now = time.time()
        local_time = time.localtime(now)
        millis = int((now - int(now)) * 1000)
        
        date_str = time.strftime("%d-%m-%Y", local_time)
        time_str = time.strftime(f"%H:%M:%S.{millis:03d}", local_time)  # HH:MM:SS.mmm format
        
        # Get text sizes
        (date_w, date_h), _ = cv2.getTextSize(date_str, font, font_scale, thickness)
        (time_w, time_h), _ = cv2.getTextSize(time_str, font, font_scale, thickness)
        (name_w, name_h), _ = cv2.getTextSize(self.camera_name, font, font_scale, thickness)
        
        h, w = frame.shape[:2]
        
        # Draw shadow for better visibility
        def draw_text_with_shadow(img, text, pos):
            x, y = pos
            # shadow offset by 1 px right and down
            cv2.putText(img, text, (x+1, y+1), font, font_scale, shadow_color, thickness, cv2.LINE_AA)
            cv2.putText(img, text, (x, y), font, font_scale, text_color, thickness, cv2.LINE_AA)
        
        # Bottom-right corner for date and time
        draw_text_with_shadow(frame, date_str, (w - date_w - 10, h - time_h * 2 - 10))
        draw_text_with_shadow(frame, time_str, (w - time_w - 10, h - 10))
        
        # Top-left corner for camera name
        draw_text_with_shadow(frame, self.camera_name, (10, name_h + 10))
        
        return frame