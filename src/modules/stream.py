import cv2
import threading
import time
import socket
from flask import Flask, Response
from logger_setup import logger

class StreamServer:
    """
    Stream Module Class.
    Handles streaming of frames from the camera to a specified port.
    Designed to be used with Flask for web streaming.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, port: int, target_fps: int):
        """
        Initializes the StreamServer with required parameters.
        """
        self.camera_name = camera_name
        self.camera_name_norm = camera_name_norm
        self.port = port
        self.target_fps = target_fps

        # Stream Thread
        self._stream_thread = threading.Thread(
            target=self._run,
            daemon=True
        )

        # Latest frame control variables
        self._latest_frame_lock = threading.Lock()
        self._latest_frame = None
    
    def write(self, frame: bytes):
        """
        Updates latest frame.
        """
        with self._latest_frame_lock:
            self._latest_frame = frame

    def start(self):
        """
        Starts the stream server thread.
        """
        self._stream_thread.start()

    def _run(self):
        """
        Run Flask app in a seperate thread.
        """
        logger.info(f"Starting Flask stream server for {self.camera_name} on port {self.port} (http://{self._get_local_ip()}:{self.port}).")
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
    
    @staticmethod
    def _get_local_ip():
        """
        Returns the local IP address of the machine.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return 'localhost'