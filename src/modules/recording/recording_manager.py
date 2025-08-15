import os
import subprocess
import threading
import time
import glob
from queue import Queue
from logger_setup import logger
from utils import check_create_directory


class RecordingManager:
    """
    RecordingManager Module Class.
    Handles the recording of video streams from cameras, in sub-class StreamRecording.
    Handles the recording of motion events, in sub-class MotionRecording.
    Provides methods rquired for all sub-classes.
    Uses FFmpeg.
    """

    # Class Variables for all instances
    enabled = False
    output_dir = None
    max_days_to_save = None
    encode_to_h264 = None
    h264_encoder = None
    bitrate = None
    
    def __init__(self, camera_name: str, camera_name_norm: str, target_fps: int, max_queue_size: int = 100):
        """
        Initializes the RecordingManafer with config parameters.
        """
        self.camera_name = camera_name
        self.camera_name_norm = camera_name_norm
        self.target_fps = target_fps

        # Set output directory for this camera
        self.output_dir = os.path.abspath(os.path.join(self.output_dir, self.camera_name_norm))
        check_create_directory(self.output_dir)

        # Recording Manager Thread Parameters
        self._recorder_thread = threading.Thread(
            target=self._run,
            daemon=True
        )
        self._recorder_stop_event = threading.Event()
        self._ffmpeg_process = None
        self._current_file_path = None

        # Initialize recording encoded frames queue 
        self.rec_queue = Queue(maxsize=max_queue_size)
    
    @classmethod
    def setClassConfig(cls, enabled: bool, output_dir: str = None, 
                       max_days_to_save: int = None, encode_to_h264: int = None,
                       h264_encoder: str = None, bitrate: int = None):
        """
        Set the shared configs across all instances of this sub-class.
        To be called before any instance is created.
        """
        cls.enabled = enabled
        cls.output_dir = output_dir
        cls.max_days_to_save = max_days_to_save
        cls.encode_to_h264 = encode_to_h264
        cls.h264_encoder = h264_encoder
        cls.bitrate = bitrate

    def write(self, frame: bytes):
        """
        Writes a encoded frame to the recording queue, if enabled is enabled.
        If the queue is full, the frame is dropped.
        """
        if self.enabled:
            try:
                self.rec_queue.put_nowait(frame)
            except:
                pass  # Drop frame if queue is full 
    
    def start(self):
        """
        Starts the recording manager thread, if enabled is enabled.
        """
        if self.enabled:
            self._recorder_thread.start()
    
    def stop(self):
        """
        Stops the recording manager thread, if enabled is enabled.
        """
        if self.enabled:
            self._recorder_stop_event.set()
            self._recorder_thread.join()
            self._clear_queue()
    
    def _start_ffmpeg(self):
        """
        Starts the FFmpeg process to record the video stream.
        It records the frames encoded in MJPG format (recived from stream thread) to an .avi file or
        encodes the frames encoded in MJPG format (recived from stream thread) to h264 and then records to an .mp4 file.
        FFmpeg Process receives frames from stdin Pipeline, which is opened here.
        """
        logger.info(f"Camera '{self.camera_name}': Starting FFmpeg process for recording file '{self._current_file_path}'.")
        if self.encode_to_h264 in [0, 1]: # MJPG .avi for current hour file
            cmd = [
                'ffmpeg',
                '-hide_banner', # hide ffmpeg log prints
                '-loglevel', 'error', # hide ffmpeg log prints except error
                '-y', # overwrite output file if exists (needed as we are continuously writing to the same file within the same hour)
                '-f', 'mjpeg', # input format of frames (we are piping JPEG-encoded frames)
                '-framerate', str(self.target_fps), # input frame rate
                '-i', 'pipe:0', # input comes from STDIN (pipe:0 = standard input)
                '-r', str(self.target_fps), # output frame rate
                '-c:v', 'copy', # copy the video stream "as is" (no re-encoding) (for this case it is supported in .avi file)
                self._current_file_path
            ]
        else: # encode to h264 for current hour file
            if self.h264_encoder == 'h264_vaapi':
                cmd = [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-y',
                    '-f', 'mjpeg',
                    '-framerate', str(self.target_fps),
                    '-i', 'pipe:0',
                    '-vaapi_device', '/dev/dri/renderD128', # required for h264_vaapi encoder
                    '-vf', 'format=nv12,hwupload', # required for h264_vaapi encoder
                    '-r', str(self.target_fps),
                    '-c:v', self.h264_encoder, # encode to h264
                    '-b:v', f'{self.bitrate}k', # output bitrate
                    #'-movflags', 'frag_keyframe+empty_moov+default_base_moof', # for fragmented-mp4 (fmp4)
                    self._current_file_path
                ]
            elif self.h264_encoder == 'h264_v4l2m2m':
                cmd = [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-y',
                    '-f', 'mjpeg',
                    '-framerate', str(self.target_fps),
                    '-i', 'pipe:0',
                    '-pix_fmt', 'yuv420p', # pixel format required for h264_v4l2m2m
                    '-r', str(self.target_fps),
                    '-c:v', self.h264_encoder, # encode to h264
                    '-b:v', f'{self.bitrate}k',
                    #'-movflags', 'frag_keyframe+empty_moov+default_base_moof', # for fragmented-mp4 (fmp4)
                    self._current_file_path
                ]
            elif self.h264_encoder == 'h264_qsv':
                cmd = [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-y',
                    '-f', 'mjpeg',
                    '-framerate', str(self.target_fps),
                    '-i', 'pipe:0',
                    '-r', str(self.target_fps),
                    '-c:v', self.h264_encoder, # encode to h264
                    '-preset', 'veryfast', # h264_qsv does not support ultrafast preset
                    '-b:v', f'{self.bitrate}k',
                    #'-movflags', 'frag_keyframe+empty_moov+default_base_moof', # for fragmented-mp4 (fmp4)
                    self._current_file_path
                ]
            else:
                cmd = [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-y',
                    '-f', 'mjpeg',
                    '-framerate', str(self.target_fps),
                    '-i', 'pipe:0',
                    '-r', str(self.target_fps),
                    '-c:v', self.h264_encoder, # encode to h264
                    '-preset', 'ultrafast', # to reduce CPU/GPU usage
                    '-b:v', f'{self.bitrate}k',
                    #'-movflags', 'frag_keyframe+empty_moov+default_base_moof', # for fragmented-mp4 (fmp4)
                    self._current_file_path
                ]
        self._ffmpeg_process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    
    def _stop_ffmpeg(self):
        """
        Stops the FFmpeg process if it is running. 
        Sets `self._ffmpeg_process` to None.
        """
        if self._ffmpeg_process:
            try:
                self._ffmpeg_process.stdin.close()
                self._ffmpeg_process.wait(timeout=5)
                logger.info(f"Camera '{self.camera_name}': FFmpeg process stopped successfully ('{self._current_file_path}').")
            except Exception as e:
                logger.error(f"Error in camera '{self.camera_name}': Error stopping FFmpeg process ('{self._current_file_path}'): {e}")
            self._ffmpeg_process = None

    def _convert_to_h264(self, avi_path: str):
        """
        To be ran in seperate Thread.
        Converts the .avi MJPEG encoded to .mp4 h264 encoded, using ffmpeg.
        """
        mp4_path = avi_path.rsplit('.', 1)[0] + '.mp4' # to convert to mp4
        logger.info(f"Camera '{self.camera_name}': Starting converting to h264 from '{avi_path}' to '{mp4_path}'")
        if self.h264_encoder == 'h264_vaapi':
            cmd = [
                'ffmpeg',
                '-hide_banner',
                '-loglevel', 'error',
                '-i', avi_path,
                '-vaapi_device', '/dev/dri/renderD128',
                '-vf', 'format=nv12,hwupload',
                '-c:v', self.h264_encoder,
                '-b:v', f'{self.bitrate}k',
                '-movflags', '+faststart',
                mp4_path
            ]
        elif self.h264_encoder == 'h264_v4l2m2m':
            cmd = [
                'ffmpeg',
                '-hide_banner',
                '-loglevel', 'error',
                '-i', avi_path,
                '-pix_fmt', 'yuv420p',
                '-c:v', self.h264_encoder,
                '-b:v', f'{self.bitrate}k',
                '-movflags', '+faststart',
                mp4_path
            ]
        elif self.h264_encoder == 'h264_qsv':
            cmd = [
                'ffmpeg',
                '-hide_banner',
                '-loglevel', 'error',
                '-i', avi_path,
                '-c:v', self.h264_encoder,
                '-preset', 'veryfast', # h264_qsv does not support ultrafast preset
                '-b:v', f'{self.bitrate}k',
                '-movflags', '+faststart',
                mp4_path
            ]
        else:
            cmd = [
                'ffmpeg',
                '-hide_banner',
                '-loglevel', 'error',
                '-i', avi_path,
                '-c:v', self.h264_encoder,
                '-preset', 'ultrafast', # to reduce CPU/GPU usage
                '-b:v', f'{self.bitrate}k',
                '-movflags', '+faststart',
                mp4_path
            ]
        try:
            subprocess.run(cmd, check=True)
            logger.info(f"Camera '{self.camera_name}': Converted '{avi_path}' to '{mp4_path}'")
            os.remove(avi_path)
            logger.info(f"Camera '{self.camera_name}': Removed avi file '{avi_path}'")
        except Exception as e:
            logger.error(f"Error in camera '{self.camera_name}': Failed converting {avi_path} to mp4: {e}")
    
    def _check_file_name(self, filename: str):
        """
        Checks if filename already exists. If yes, adds a (1) before .ext.
        If name with (1) already exists it increments to (2), ....
        Sets the `self._current_file_path` to the new file path.
        """
        base_name, ext = os.path.splitext(filename)
        filepath = os.path.join(self.output_dir, filename)
        index = 1
        while os.path.exists(filepath):
            new_filename = f"{base_name}({index}){ext}"
            filepath = os.path.join(self.output_dir, new_filename)
            index += 1
        self._current_file_path = filepath

    def _clean_old_files(self):
        """
        To be ran in seperate thread.
        Deletes recordig files older than threshold defined by `self.max_days_to_save`.
        """
        cutoff = time.time() - self.max_days_to_save * 86400
        for ext in ['avi', 'mp4', '.mkv', '.ts']:
            pattern = os.path.join(self.output_dir, f"*.{ext}")
            for f in glob.glob(pattern):
                if os.path.getmtime(f) < cutoff:
                    try:
                        os.remove(f)
                        logger.info(f"Camera '{self.camera_name}': Deleted old recording '{f}'")
                    except Exception as e:
                        logger.error(f"Error in camera '{self.camera_name}': Failed to delete old file '{f}': {e}")
    
    def _clear_queue(self):
        """
        Clears queue.
        """
        while not self.rec_queue.empty():
            try:
                self.rec_queue.get_nowait()
            except Exception:
                break