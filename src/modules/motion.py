import cv2
import threading
import numpy as np
from queue import Queue, Empty
from collections import deque
from logger_setup import logger

class Motion:
    """
    Motion Module Class.
    Detect motion events from camera and records it in h264 encoded mp4.

    Motion Event:
        - Starts after motion is detected `minimum_motion_frames` in a row.
        - Saves `pre_capture` frames before motion is detected.
        - Saves `post_capture` frames after no motion is detected.
        - After `post_capture` wait `event_gap` with no motion to end event,
          if there is motion in this interval (considering `minimum_motion_frames`),
          this new motion will be saved in the same motion event file.
        - Ends if during `event_gap` no  motion is detected.
    
        NOTE: This Module is supposed to be running in a different Process (Multiprocessing), 
              however due to several issues it will be ran, for now, only in another thread.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, enabled: bool,
                 noise_level: int = None, pixel_threshold_pct: float = None,
                 object_threshold_pct: float = None, minimum_motion_frames: int = None,
                 pre_capture: int = None, post_capture: int = None, event_gap_frames: int = None):
        """
        Initializes the Motion with camera motion parameters.
        """
        self.camera_name = camera_name
        self.camera_name_norm = camera_name_norm
        self.enabled = enabled
        self.noise_level = noise_level
        self.pixel_threshold_pct = pixel_threshold_pct
        self.object_threshold_pct = object_threshold_pct
        self.minimum_motion_frames = minimum_motion_frames
        self.pre_capture = pre_capture
        self.post_capture = post_capture
        self.event_gap_frames = event_gap_frames

        # Processed Frame Resolution variables
        self._max_w = 640 # max width for processed frame
        self._max_h = 480 # max height for processed frame
        self._res = (None, None) # (width, height)
        self._need_resize = None
        self.pixel_threshold = None
        self.object_threshold = None

        # Initialize tupple (raw, encoded) frames queue
        max_motion_queue_size = 20 # Allow some buffer for frames (lower this if RAM usage is too high) (raw frames are heavy)
        self.motion_queue = Queue(maxsize=max_motion_queue_size)
        
        # Motion Thread
        self._motion_process = threading.Thread(
            target=self._run,
            daemon=True
        )
        self._motion_process_stop_event = threading.Event()

    def write(self, raw_frame: bytes, encoded_frame: bytes):
        """
        Writes a tupple (raw, encoded) frame to the motion queue, if motion is enabled.
        If the queue is full, the frame is dropped.
        """
        if self.enabled:
            try:
                self.motion_queue.put_nowait((raw_frame, encoded_frame))
            except:
                pass  # Drop frame if queue is full 

    def start(self):
        """
        Starts the motion process, if motion is enabled.
        """
        if self.enabled:
            self._motion_process.start()

    def stop(self):
        """
        Stops the motion process, if motion is enabled.
        """
        if self.enabled:
            self._motion_process_stop_event.set()
            self._motion_process.join()
            self._clear_queue()
            logger.info(f"Camera '{self.camera_name}' Motion process stopped.")
    
    def _clear_queue(self):
        """
        Clears queue.
        """
        while not self.motion_queue.empty():
            try:
                self.motion_queue.get_nowait()
            except Exception:
                break

    def _run(self):
        """
        To be ran in a separate process.
        """
        logger.info(f"Starting motion process for camera '{self.camera_name}'.")

        # Initialize motion variables
        previous_frame = None # takes previous processed frame
        motion_frame_count = 0 # number of frames with motion detected in a row
        idle_frame_count = 0 # number of frames with no motion detected in a row when in a event
        end_event_frames = self.post_capture + self.event_gap_frames # frames to end event after no motion detected
        in_event = False
        in_true_motion = False
        pre_capture_buffer = deque(maxlen=self.pre_capture) # buffer for pre_cature encoded frames
        minimum_motion_frames_buffer = deque(maxlen=self.minimum_motion_frames) # buffer for minimum motion frames

        while not self._motion_process_stop_event.is_set():

            # Get raw and encoded frame from queue
            try:
                raw_frame, encoded_frame = self.motion_queue.get(timeout=1)
            except Empty:
                continue # avoid blocks when exiting
            if raw_frame is None:
                continue

            # Set processed resolution for fisrt iteration
            self._set_processed_resolution(raw_frame)

            # Preprocess
            processed_frame = self._preprocess(raw_frame)

            # Set previous frame for first iteration
            if previous_frame is None:
                previous_frame = processed_frame
                continue

            # Frame differencing
            dilated_diff = self._frame_diff(previous_frame, processed_frame)

            # If Motion Detected
            if self._is_motion(dilated_diff):

                # If in True Motion
                if in_true_motion:

                    # Reset idle_frame_count
                    idle_frame_count = 0

                    # Add encoded frame to queue for recording
                    ###
                
                # If not in True Motion
                else:
                    
                    # Update motion_frame_count
                    motion_frame_count += 1

                    # Update idle_frame_count
                    idle_frame_count += 1

                    # Add encoded frame to minimum_motion_frames buffer
                    minimum_motion_frames_buffer.append(encoded_frame)

                    # Start a True Motion if minimum motion frames are met
                    if motion_frame_count >= self.minimum_motion_frames:
                        in_true_motion = True
                        motion_frame_count = 0

                        # Reset idle_frame_count
                        idle_frame_count = 0

                        # If not in event, Start a new event
                        if not in_event:
                            logger.info(f"Starting Motion Event in camera '{self.camera_name}'.")
                            in_event = True
                            # Call function inc recordingmanager to sart new even (create new pipeline for new file)
                            ###
                        
                        logger.info(f"True Motion Started in camera '{self.camera_name}'.")

                        # Dump pre_capture buffer and minimum_motion_frames buffer to queue for recording
                        # Clear minimum_motion_frames buffer and pre_capture buffer
                        ###
            
            # If No Motion is Detected
            else:

                # Reset motion_frame_count
                motion_frame_count = 0

                # Update idle_frame_count
                idle_frame_count += 1

                # If in True Motion
                if in_true_motion:

                    # End True Motion if idle_frame_count exceeds post_capture
                    if idle_frame_count > self.post_capture:
                        in_true_motion = False
                        logger.info(f"True Motion Ended in camera '{self.camera_name}'.")
                        # Add encoded frame to pre_capture buffer
                        pre_capture_buffer.append(encoded_frame)
                    else:
                        # Capture post_capture frames
                        # Add encoded frame to queue for recording
                        ###
                        pass
                
                # If not in True Motion
                else:
                    # Add encoded frame to pre_capture buffer
                    pre_capture_buffer.append(encoded_frame)
                
                # End event if idle_frame_count exceeds post_capture + event_gap and not in True Motion
                if not in_true_motion and in_event and idle_frame_count > end_event_frames:
                    logger.info(f"Ending Motion Event in camera '{self.camera_name}'.")
                    in_event = False
                    # Close recording pipeline in RecordingManager
                    ###
            cv2.imshow(self.camera_name_norm, dilated_diff)
            cv2.waitKey(1)

            # Update Previous Frame
            previous_frame = processed_frame
    
    def _set_processed_resolution(self, frame: bytes):
        """
        Set the processed frame resolution, while keeping original frame aspect ratio.
        Scale it to max (w,h) if frame has higher resolution, otherwise leave it.
        Should only run on the first iteration of motion loop.
        Set the pixel threshold based on processed resolution.
        Set the motion object threshold based on processed resolution.
        """
        if not all(self._res):
            h, w = frame.shape[:2]
            if w > self._max_w or h > self._max_h:
                scale_w = self._max_w / w
                scale_h = self._max_h / h
                scale = min(scale_w, scale_h)
                self._res = (int(w * scale), int(h * scale))
                self._need_resize = True
            else:
                self._res = (w, h)
                self._need_resize = False
            self.pixel_threshold = int(self._res[0] * self._res[1] * self.pixel_threshold_pct / 100)
            self.object_threshold = int(self._res[0] * self._res[1] * self.object_threshold_pct / 100)
    
    def _preprocess(self, frame: bytes):
        """
        Resize Frame if needed.
        Convert a BGR frame to a preprocessed grayscale image.
        Apply Gaussian blur to reduce noise and detail.
        """
        if self._need_resize:
            frame = cv2.resize(frame, self._res, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        return blurred
    
    def _frame_diff(self, prev_frame: bytes, frame: bytes):
        """
        Compute the difference between two preprocessed grayscale frames and highlight areas of motion by
        applying binary threshold to isolate significant changes (using given noise level config) and
        dilating the result to fill small gaps and strengthen detected regions.
        """
        diff = cv2.absdiff(prev_frame, frame)
        _, thresh = cv2.threshold(diff, self.noise_level, 255, cv2.THRESH_BINARY)
        dilated = cv2.dilate(thresh, None, iterations=2)
        return dilated
    
    def _is_motion(self, dilated: np.ndarray):
        """
        Check if motion is detected.
        First check if the number of pixels changed (in dilation) is above the given pixel thereshold.
        Then, checks if at least one area of motion is bigger than the given motion object threshold.
        """
        # Check if minimum pixel threshold is reached
        changed_pixels = cv2.countNonZero(dilated)
        if changed_pixels < self.pixel_threshold: return False

        # Check if at least one motion area is above object threshold
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(dilated)
        for i in range(1, num_labels): # index 0 is background label
            if stats[i, cv2.CC_STAT_AREA] >= self.object_threshold:
                return True
        return False

    # To avoid encode two time maybe try to find solution to communaicate this module with recordingManager 
    # so I can record frames directly encoded from there
    # I need to make it someway that i can match frame from this thread with frame from that thread.

    # Do i need to create another recording manager?