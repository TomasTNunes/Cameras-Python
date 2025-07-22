from queue import Queue
from flask import Flask, Response
import cv2
from logger_setup import logger
import socket
from modules.recording import RecordingManager
import threading

class StreamServer:
    """
    Stream Module Class.
    Handles streaming of frames from the camera to a specified port.
    Designed to be used with Flask for web streaming.
    Feeds encoded frames to RecordingManager Module.
    """

    def __init__(self, camera_name: str, camera_name_norm: str, port: int):
        """
        Initializes the StreamServer with required parameters.
        """
        self.camera_name = camera_name
        self.port = port

        # Stream Thread Parameters
        self._stream_thread = threading.Thread(
            target=self._run,
            daemon=True
        )

        # RecordingManager Class Module and Thread
        self.recorder = RecordingManager(camera_name, camera_name_norm)
        if self.recorder.save_recording:
            self.recorder_thread = threading.Thread(target=self.recorder.start, daemon=True)

        # Initialize stream raw frames queue 
        max_stream_queue_size = 10  # Allow some buffer for frames for stream (lower this if RAM usage is too high) (raw frames are heavy)
        self.frame_queue = Queue(maxsize=max_stream_queue_size)
    
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
        Starts the stream server thread.
        """
        self._stream_thread.start()

    def _run(self):
        """
        Run Flask app in a seperate thread.
        """
        logger.info(f"Starting stream server for {self.camera_name} on port {self.port} (http://{self._get_local_ip()}:{self.port}).")
        app = Flask(__name__)

        def generate():
            while True:
                frame = self.frame_queue.get()
                if frame is None:
                    continue

                # Encode frame as JPEG
                ret, jpeg = cv2.imencode('.jpg', frame)
                if not ret:
                    continue

                # Return frame as part of a multipart response
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    jpeg.tobytes() + b'\r\n'
                )

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