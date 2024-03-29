from copy import deepcopy
from led_controller import LEDInterface
from turbojpeg import TurboJPEG, TJFLAG_FASTDCT, TJFLAG_FASTUPSAMPLE, TJPF_RGB
from utils import get_led_sample_points
from v4l2py import Device
from v4l2py.device import BufferType
import cv2
import numpy as np
import queue, threading
import user_pref

FRAME_GET_TIMEOUT_S = 0.1
BLUR_WINDOW_SIZE = 9
BLUR_WINDOW_OFFSET = BLUR_WINDOW_SIZE // 2

class ImageController:
    def __init__(self):
        pass


    def __enter__(self):
        self._setup_sample_points()
        self.jpegDecoder = TurboJPEG()
        self._frameQueue = queue.Queue(1)
        self._stopThread = threading.Event()
        self._cameraThread = None
        self._frameThread = None

        self._open_camera()
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_capture_and_processing()


    def set_led_interface(self, ledInterface: LEDInterface):
        self._ledInterface = ledInterface


    def start_capture_and_processing(self):
        self._stopThread.clear()
        self._cameraThread = threading.Thread(
                target=ImageController._camera_thread_loop, args=[self])
        self._cameraThread.start()

        # self.start_timer = perf_counter()
        # self.num_frames_processed = 0
        while self._ledInterface.update_and_get_power_state():
            try:
                frame = self._frameQueue.get(timeout=FRAME_GET_TIMEOUT_S)
                try:
                    rgbFrame = self.jpegDecoder.decode(frame,
                                                    pixel_format=TJPF_RGB,
                                                    flags=TJFLAG_FASTUPSAMPLE|TJFLAG_FASTDCT)
                    self._process_one_frame(rgbFrame)
                except OSError as e:
                    print("WARN: OSError while decoding JPEG. Skipping.")
                    print(e)

                # self.num_frames_processed += 1
                # if self.num_frames_processed % 10 == 0:
                #     fps = self.num_frames_processed / (perf_counter() - self.start_timer)
                #     print(f"FPS: {fps}")

                # if (self.num_frames_processed == 100):
                #     self.start_timer = perf_counter()
                #     self.num_frames_processed = 0
            except queue.Empty:
                pass

    def stop_capture_and_processing(self):
        self._stopThread.set()
        if self._cameraThread is not None:
            self._cameraThread.join()


    def _camera_thread_loop(self):
        """
        Immediately consumes the available camera frame. Makes the latest frame
        available to _frameQueue and drops any previously saved frames.
        """
        for frame in self._cam:
            if self._stopThread.is_set():
                break

            try:
                self._frameQueue.get_nowait()
            except queue.Empty:
                pass
            self._frameQueue.put(deepcopy(bytes(frame)))


    def _process_one_frame(self, frame):
        frame = self._smooth_frame(frame)

        topColors = frame[self._topIdx[0], self._topIdx[1]]
        bottomColors = frame[self._bottomIdx[0], self._bottomIdx[1]]
        leftColors = frame[self._leftIdx[0], self._leftIdx[1]]
        rightColors = frame[self._rightIdx[0], self._rightIdx[1]]
        colors = {
            "top": topColors,
            "bottom": bottomColors,
            "left": leftColors,
            "right": rightColors
        }

        self._ledInterface.set_colors(colors)


    def _smooth_frame(self, frame):

        for poi in self._topIdx.T:
            rows = (poi[0] - BLUR_WINDOW_OFFSET, poi[0] + BLUR_WINDOW_OFFSET)
            cols = (poi[1] - BLUR_WINDOW_OFFSET, poi[1] + BLUR_WINDOW_OFFSET)
            frame[rows[0]:rows[1], cols[0]:cols[1]] = \
                cv2.GaussianBlur(frame[rows[0]:rows[1], cols[0]:cols[1]],
                                 (BLUR_WINDOW_SIZE, BLUR_WINDOW_SIZE), 3)

        for poi in self._bottomIdx.T:
            rows = (poi[0] - BLUR_WINDOW_OFFSET, poi[0] + BLUR_WINDOW_OFFSET)
            cols = (poi[1] - BLUR_WINDOW_OFFSET, poi[1] + BLUR_WINDOW_OFFSET)
            frame[rows[0]:rows[1], cols[0]:cols[1]] = \
                cv2.GaussianBlur(frame[rows[0]:rows[1], cols[0]:cols[1]],
                                 (BLUR_WINDOW_SIZE, BLUR_WINDOW_SIZE), 3)

        for poi in self._leftIdx.T:
            rows = (poi[0] - BLUR_WINDOW_OFFSET, poi[0] + BLUR_WINDOW_OFFSET)
            cols = (poi[1] - BLUR_WINDOW_OFFSET, poi[1] + BLUR_WINDOW_OFFSET)
            frame[rows[0]:rows[1], cols[0]:cols[1]] = \
                cv2.GaussianBlur(frame[rows[0]:rows[1], cols[0]:cols[1]],
                                 (BLUR_WINDOW_SIZE, BLUR_WINDOW_SIZE), 3)

        for poi in self._rightIdx.T:
            rows = (poi[0] - BLUR_WINDOW_OFFSET, poi[0] + BLUR_WINDOW_OFFSET)
            cols = (poi[1] - BLUR_WINDOW_OFFSET, poi[1] + BLUR_WINDOW_OFFSET)
            frame[rows[0]:rows[1], cols[0]:cols[1]] = \
                cv2.GaussianBlur(frame[rows[0]:rows[1], cols[0]:cols[1]],
                                 (BLUR_WINDOW_SIZE, BLUR_WINDOW_SIZE), 3)

        return frame


    def _setup_sample_points(self):
        controlPoints = user_pref.read_calibration_data()
        pointCounts = user_pref.read_led_counts()

        sampledPoints = get_led_sample_points(controlPoints, pointCounts)
        topPoints = sampledPoints["top"]
        self._topIdx = [[v[1], v[0]] for v in topPoints]
        self._topIdx = np.transpose(self._topIdx)

        bottomPoints = sampledPoints["bottom"]
        self._bottomIdx = [[v[1], v[0]] for v in bottomPoints]
        self._bottomIdx = np.transpose(self._bottomIdx)

        leftPoints = sampledPoints["left"]
        self._leftIdx = [[v[1], v[0]] for v in leftPoints]
        self._leftIdx = np.transpose(self._leftIdx)

        rightPoints = sampledPoints["right"]
        self._rightIdx = [[v[1], v[0]] for v in rightPoints]
        self._rightIdx = np.transpose(self._rightIdx)


    def _open_camera(self):
        (cameraPath, resolution) = user_pref.read_device_prefs()
        self._cam = Device(cameraPath)
        self._cam.open()
        self._cam.set_format(BufferType.VIDEO_CAPTURE, resolution[0], resolution[1], "MJPG")
        self._cam.controls.auto_exposure.value = 1
        self._cam.controls.white_balance_automatic.value = False
        self._cam.close()

        # close and reopen to make sure auto_exposure value is set before
        # setting exposure_time_absolute value
        self._cam.open()
        self._cam.set_format(BufferType.VIDEO_CAPTURE, resolution[0], resolution[1], "MJPG")
        self._cam.set_fps(BufferType.VIDEO_CAPTURE, 30)
        self._cam.controls.auto_exposure.value = 1
        self._cam.controls.white_balance_automatic.value = False
        self._cam.controls.brightness.value = -64
        self._cam.controls.contrast.value = 0
        self._cam.controls.saturation.value = 80
        self._cam.controls.hue.value = 0
        self._cam.controls.gamma.value = 100
        self._cam.controls.gain.value = 100
        self._cam.controls.white_balance_temperature.value = 4100
        self._cam.controls.exposure_time_absolute.value = 128
