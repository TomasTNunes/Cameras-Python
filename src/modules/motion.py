import cv2
import threading
from queue import Queue, Empty
#from multiprocessing import Process, Event, Queue
from logger_setup import logger

class Motion:
    """
    Motion Module Class.
    Detect motion events from camera and records it in h264 encoded mp4.

    Motion Event:
        - Starts after motion is detected `minimum_motion_frames` in a row.
        - Saves `pre_capture` frames before motion is detected (care RAM usage).
        - Saves `post_capture` frames after no motion is detected.
        - After `post_capture` wait `event_gap` with no motion to end event,
          if there is motion in this interval (considereing `minimum_motion_frames`),
          this new motion will be saved in the same motion event file.
        - Ends if during `event_gap` no  motion is detected.
    
        NOTE: This Module is supposed to be running in a different Process (Multiprocessing), 
              however due to several issues it will be ran, for now, only in another thread.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, enabled: bool,
                 noise_level: int = None, threshold: int = None):
        """
        """
        self.camera_name = camera_name
        self.camera_name_norm = camera_name_norm
        self.enabled = enabled
        self.noise_level = noise_level
        self.threshold = threshold

        # Processed Frame Resolution variables
        self._max_w = 640 # max width for processed frame
        self._max_h = 480 # max height for processed frame
        self._res = (None, None) # (width, height)
        self._need_resize = None

        # Initialize tupple (raw, encoded) frames queue
        max_motion_queue_size = 15 # Allow some buffer for frames (lower this if RAM usage is too high) (raw frames are heavy)
        self.motion_queue = Queue(maxsize=max_motion_queue_size)

        # # Motion Process
        # self._motion_process = Process(
        #     target=self._run,
        #     daemon=True
        # )
        # self._motion_process_stop_event = Event()
        
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
            # # Process
            # self._motion_process.join(timeout=5)
            # if self._motion_process.is_alive():
            #     self._motion_process.terminate()
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
        # Process
        # self.motion_queue.cancel_join_thread()
        # self.motion_queue.close()

    def _run(self):
        """
        To be ran in a separate process.
        """
        logger.info(f"Starting motion process for camera '{self.camera_name}'.")

        # Initialize motion variables
        previous_frame = None # takes previous processed frame

        while not self._motion_process_stop_event.is_set():

            # Get raw and encoded frame from queue
            try:
                raw_frame, encoded_frame = self.motion_queue.get(timeout=1)
            except:
                continue # avoid blocks when exiting
            if raw_frame is None:
                continue

            self._set_processed_resolution(raw_frame)

            # Preprocess
            processed_frame = self._preprocess(raw_frame)

            # Set previous frame for first iteration
            if previous_frame is None:
                previous_frame = processed_frame
                continue

            # Frame differencing
            dilated_diff = self._frame_diff(previous_frame, processed_frame)
            
            cv2.imshow("Motion", dilated_diff)
            cv2.waitKey(1)

            # Update Previous Frame
            previous_frame = processed_frame
    
    def _set_processed_resolution(self, frame: bytes):
        """
        Set the processed frame resolution, while keeping original frame aspect ratio.
        Scale it to max (w,h) if frame has higher resolution, otherwise leave it.
        Should only run on the first iteration of motion loop.
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
            print(self._need_resize)
    
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

    # To avoid encode two time maybe try to find solution to communaicate this module with recordingManager 
    # so I can record frames directly encoded from there
    # I need to make it someway that i can match frame from this thread with frame from that thread.

    # Do i need to create another recording manager?    