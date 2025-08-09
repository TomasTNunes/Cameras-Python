import cv2
import time
import threading
from queue import Queue
from modules.stream import StreamServer
from modules.recording import RecordingManager
from logger_setup import logger

class CameraReader:
    """
    Camera Module Class.
    Handles camera initialization, frame reading and jpeg encoding, and continiously feeding it to Stream, RecordingManager and Motion Modules.
    Also provides methods to draw clock and FPS on frames.
    Frame Reading using time-based throttling, reading all frames but displaying at a fixed rate.
    Designed to be used with OpenCV.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, camera: str, 
                 target_fps: int, port: int, stream_quality: int, show_fps: bool, 
                 source_format: str = None, width: int = None, height: int = None, 
                 source_fps: int = None):
        """
        Initializes the CameraReader with camera parameters.
        """
        self.camera_name = camera_name
        self.target_fps = target_fps
        self.show_fps = show_fps
        self.stream_quality = stream_quality

        # Camera Thread
        self._camera_thread = threading.Thread(
            target=self._run,
            daemon=True
        )
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
        
        # Initialize raw frames queue 
        max_stream_queue_size = 10  # Allow some buffer for frames for stream (lower this if RAM usage is too high) (raw frames are heavy)
        self.frame_queue = Queue(maxsize=max_stream_queue_size)

        # Frame dispatcher Thread
        self._frame_dispatcher_thread = threading.Thread(
            target=self._frame_dispatcher,
            daemon=True
        )
        self._frame_dispatcher_stop_event = threading.Event()


        # Initialize StreamServer Class Module
        self.stream_server = StreamServer(
            camera_name=camera_name, 
            camera_name_norm=camera_name_norm, 
            port=port, 
            target_fps=target_fps
        )

        # Initialize RecordingManager Class Module
        self.recording_manager = RecordingManager(
            camera_name=camera_name,
            camera_name_norm=camera_name_norm,
            target_fps=target_fps
        )
    
    def start(self):
        """
        Starts the camera threads.
        """ 
        self._frame_dispatcher_thread.start() # Start frame dispatcher thread
        self._camera_thread.start() # Start Camera reader thread
        self.stream_server.start() # Start streaming thread
        self.recording_manager.start() # Start recording thread
    
    def stop(self):
        """
        Stops the camera reader thread, and child threads (stream, motion, etc).
        """
        self.recording_manager.stop() # Stop recording manager thread
        self._frame_dispatcher_stop_event.set()
        self._camera_stop_event.set()
        self._frame_dispatcher_thread.join()
        self._camera_thread.join()
        logger.info(f"Camera '{self.camera_name}' thread stopped.")
    
    def _close_camera_reader(self):
        """
        Releases the camera and closes correspondant OpenCV windows.
        """
        if self.cap.isOpened():
            self.cap.release()
            logger.info(f"Camera '{self.camera_name}' released.")

    def _run(self):
        """
        To be ran in a separate thread.
        Reads all frames from the camera, but only feeds the targeted frames to the processing and stream modules (respective queues).
        Starts Stream Thread and Motion Process.
        Uses time-based throttling.
        """
        # Get camera actual info
        actual_fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
        actual_fmt = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
        source_fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        logger.info(f"Starting camera '{self.camera_name}' frame reader thread. \
(Source_Format: {actual_fmt}, Source_FPS: {source_fps}, \
Target_FPS: {self.target_fps}, Width: {int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))}, \
Height: {int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})")

        # Compute sleep time based on source FPS
        if source_fps and source_fps >= 1:
            sleep_time = 1 / source_fps / 2  # Sleep half the time to allow for processing
        else:
            sleep_time = 0.005 # Sleep 5ms (default) to prevent high CPU usage (for 30 fps camera new frames are available every ~33ms)
        
        # fps computation variables
        if self.show_fps:
            throttle_frame_count = 0
            throttle_start_time = time.time()
            current_fps = 0.0

        # Time-based throttling control variable
        target_frame_interval = 1.0 / self.target_fps
        next_display_time = time.time()

        # Camera Thread Loop
        while not self._camera_stop_event.is_set():
            # Read frame from camera (always read in BGR, independent from source format)
            ret, frame = self.cap.read()
            if not ret:
                logger.error(f"Camera '{self.camera_name}' read failed.")
                break
            now = time.time()
            
            # Time-based throttling
            if now >= next_display_time:

                # Update Time-based throttling control variable for next iterations
                next_display_time += target_frame_interval
                
                # Compute fps
                if self.show_fps:
                    throttle_frame_count += 1
                    elapsed = now - throttle_start_time
                    if elapsed >= 1:
                        current_fps = throttle_frame_count / elapsed
                        throttle_frame_count = 0
                        throttle_start_time = now

                    # Draw name, time-stamps and fps into frame
                    frame = self._draw_frame_info(frame, now, current_fps)
                else:
                    # Draw name and time-stamps
                    frame = self._draw_frame_info(frame, now)

                # Write raw frame to frame queue
                self._write(frame)
            
            time.sleep(sleep_time)  # Sleep to reduce CPU usage

        # Close camera and release resources
        self._close_camera_reader()
    
    def _write(self, frame: bytes):
        """
        Writes a raw frame to the frame queue.
        If the queue is full, the frame is dropped.
        """
        try:
            self.frame_queue.put_nowait(frame)
        except:
            pass  # Drop frame if queue is full 
                    # (Might be a good idea to relpace frame by oldest instead of dropping it, 
                    # should reduce latency build up in spike scenarios)
    
    def _frame_dispatcher(self):
        """
        Seperate thread loop to read raw frame from queue and encoding it to jpeg.
        It will then serve encoded frame to Stream Class Module and RecordingManager Class Module.
        It will serve a tuple (raw, encoded) frames to Motion Class Module.
        """
        while not self._frame_dispatcher_stop_event.is_set():
            frame = self.frame_queue.get()
            if frame is None:
                 continue
            
            # Encode frame as JPEG
            ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.stream_quality])
            if not ret:
                continue

            # JPEG NumPy array to bytes
            jpeg_bytes = jpeg.tobytes()

            # Feed Encoded frame to Stream
            self.stream_server.write(jpeg_bytes)

            # Feed Encoded frame to RecordingManager
            self.recording_manager.write(jpeg_bytes)

    def _draw_frame_info(self, frame: bytes, now: float, fps: float = None):
        """
        Draws the date and time (with milliseconds) in the bottom-right corner,
        and the camera name in the top-left corner, styled like a vigilance system.
        Draws fps in top-right corner, if given.
        """
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 2
        
        # Colors: bright green with black shadow for vigilance style
        text_color = (0, 255, 0)  # bright green
        shadow_color = (0, 0, 0)  # black shadow
        
        # Get current time with milliseconds
        local_time = time.localtime(now)
        millis = int((now - int(now)) * 1000)
        
        date_str = time.strftime("%d-%m-%Y", local_time)
        time_str = time.strftime(f"%H:%M:%S.{millis:03d}", local_time)
        
        # Get text sizes
        (date_w, date_h), _ = cv2.getTextSize(date_str, font, font_scale, thickness)
        (time_w, time_h), _ = cv2.getTextSize(time_str, font, font_scale, thickness)
        (name_w, name_h), _ = cv2.getTextSize(self.camera_name, font, font_scale, thickness)
        
        h, w = frame.shape[:2]
        
        # Draw shadow for better visibility
        def draw_text_with_shadow(img: bytes, text: str, pos: int):
            x, y = pos
            # shadow offset by 1 px right and down
            cv2.putText(img, text, (x+1, y+1), font, font_scale, shadow_color, thickness, cv2.LINE_AA)
            cv2.putText(img, text, (x, y), font, font_scale, text_color, thickness, cv2.LINE_AA)
        
        # Bottom-right corner for date and time
        draw_text_with_shadow(frame, date_str, (w - date_w - 10, h - time_h * 2 - 10))
        draw_text_with_shadow(frame, time_str, (w - time_w - 10, h - 10))
        
        # Top-left corner for camera name
        draw_text_with_shadow(frame, self.camera_name, (10, name_h + 10))

        # Top-right corner for FPS
        if fps:
            fps_str = f"{fps:.2f} fps"
            (fps_w, fps_h), _ = cv2.getTextSize(fps_str, font, font_scale, thickness)
            draw_text_with_shadow(frame, fps_str, (w - fps_w - 10, fps_h + 10))
        
        return frame