import cv2
import threading
import time
import socket
from queue import Queue
from flask import Flask, Response
from modules.recording import RecordingManager
from logger_setup import logger

class StreamServer:
    """
    Stream Module Class.
    Handles streaming of frames from the camera to a specified port.
    Designed to be used with Flask for web streaming.
    Feeds encoded frames to RecordingManager Module.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, port: int, target_fps: int, stream_quality: int):
        """
        Initializes the StreamServer with required parameters.
        """
        self.camera_name = camera_name
        self.port = port
        self.target_fps = target_fps
        self.stream_quality = stream_quality

        # Stream Thread
        self._stream_thread = threading.Thread(
            target=self._run,
            daemon=True
        )

        # Initialize stream raw frames queue 
        max_stream_queue_size = 10  # Allow some buffer for frames for stream (lower this if RAM usage is too high) (raw frames are heavy)
        self.frame_queue = Queue(maxsize=max_stream_queue_size)

        # Initialize variables for stream frame queue reader tread
        self._latest_frame = None
        self._latest_frame_lock = threading.Lock()
        self._frame_dispatcher_thread = threading.Thread(
            target=self._frame_dispatcher,
            daemon=True
        )

        # Initialize RecordingManager Class Module
        self.recording_manager = RecordingManager(
            camera_name=camera_name,
            camera_name_norm=camera_name_norm,
            target_fps=target_fps
        )
    
    def write(self, frame: bytes):
        """
        Writes a raw frame to the stream queue.
        If the queue is full, the frame is dropped.
        """
        try:
            self.frame_queue.put_nowait(frame)
        except:
            pass  # Drop frame if queue is full 
                    # (Might be a good idea to relpace frame by oldest instead of dropping it, 
                    # should reduce latency build up in spike scenarios)

    def start(self):
        """
        Starts the stream server thread and encoded frame dispatcher thread.
        """
        self._frame_dispatcher_thread.start()
        self._stream_thread.start()
    
    def _frame_dispatcher(self):
        """
        Seperate thread loop to read raw frame from queue, encoding it to jpeg and serve it to all clients and Recorfing Manger Class Module.
        """
        while True:
            frame = self.frame_queue.get()
            if frame is None:
                 continue
            
            # Encode frame as JPEG
            ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.stream_quality])
            if not ret:
                continue

            # JPEG NumPy array to bytes
            jpeg_bytes = jpeg.tobytes()

            # Save for clients
            with self._latest_frame_lock:
                self._latest_frame = jpeg_bytes

            # Feed Encoded frame to RecordingManager
            self.recording_manager.write(jpeg_bytes)

    def _run(self):
        """
        Run Flask app in a seperate thread.
        """
        logger.info(f"Starting Flask stream server for {self.camera_name} on port {self.port} (http://{self._get_local_ip()}:{self.port}).")
        self.recording_manager.start()  # Start recording manager thread
        app = Flask(__name__)

        def generate():
            """
            Called for each client.
            """
            frame_interval = 1.0 / self.target_fps
            while True:
                start = time.time()
                with self._latest_frame_lock:
                    jpeg_bytes = self._latest_frame
                if jpeg_bytes is None:
                        continue

                # Return frame as part of a multipart response
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    jpeg_bytes + b'\r\n'
                )
                time.sleep(max(0, frame_interval - (time.time() - start)))

        @app.route('/')
        def video_feed():
            return Response(
                generate(),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )

        try:
            app.run(host='0.0.0.0', 
                    port=self.port, 
                    threaded=True, # Allows Flask to handle multiple requests concurrently by using internal threads
                    use_reloader=False # Prevent duplicate threads or errors when running Flask in a background thread
                    )
        except Exception as e:
            logger.error(f'Error running flask app for camera {self.camera_name}: {e}')
    
    def _get_local_ip(self):
        """
        Returns the local IP address of the machine.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return 'localhost'