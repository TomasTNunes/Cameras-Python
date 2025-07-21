from queue import Queue
from flask import Flask, Response
import cv2
from logger_setup import logger
import socket

class StreamServer:
    """
    Stream Module Class.
    Handles streaming of frames from the camera to a specified port.
    Designed to be used with Flask for web streaming.
    """

    def __init__(self, camera_name: str, frame_queue: Queue, port: int):
        """
        Initializes the StreamServer with required parameters.
        """
        self.camera_name = camera_name
        self.frame_queue = frame_queue
        self.port = port

    def start(self):
        """
        Starts the stream server.
        Run Flask app in a seperate thread.
        """
        logger.info(f"Starting stream server for {self.camera_name} on port {self.port} (http://{self.get_local_ip()}:{self.port}).")
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
    
    def get_local_ip(self):
        """
        Returns the local IP address of the machine.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return 'localhost'