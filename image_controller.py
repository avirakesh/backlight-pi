from led_controller import LEDInterface
from turbojpeg import TurboJPEG, TJFLAG_FASTDCT, TJFLAG_FASTUPSAMPLE, TJPF_RGB
from utils import get_led_sample_points
from v4l2py import Device
from v4l2py.device import BufferType
import cv2
import numpy as np
import queue, threading
import user_pref


class ImageController:
    def __init__(self):
        pass


    def __enter__(self):
        self._setup_sample_points()
        self._setup_camera()
        self._frameQueue = queue.Queue(1)
        self._stopThread = threading.Event()
        self._cameraThread = threading.Thread(target=ImageController._camera_thread_loop, args=[self])
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stopThread.set()
        self._cameraThread.join()
        self._cam.close()


    def set_led_interface(self, ledInterface: LEDInterface):
        self._ledInterface = ledInterface


    def start_capture_and_processing(self):
        # self.start_timer = perf_counter()
        # self.num_frames_processed = 0

        self._cameraThread.start()
        while not self._stopThread.is_set():
            frame = self._frameQueue.get()
            rgbFrame = self.jpegDecoder.decode(bytes(frame),
                                               pixel_format=TJPF_RGB,
                                               flags=TJFLAG_FASTUPSAMPLE|TJFLAG_FASTDCT)
            self._process_one_frame(rgbFrame)
            # self.num_frames_processed += 1
            # if self.num_frames_processed % 10 == 0:
            #     fps = self.num_frames_processed / (perf_counter() - self.start_timer)
            #     print(f"FPS: {fps}")

            # if (self.num_frames_processed == 100):
            #     self.start_timer = perf_counter()
            #     self.num_frames_processed = 0


    def _camera_thread_loop(self):
        for frame in self._cam:
            if self._stopThread.is_set():
                break

            try:
                self._frameQueue.get_nowait()
            except queue.Empty:
                pass
            self._frameQueue.put(frame)


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
            rows = (poi[0] - 2, poi[0] + 2)
            cols = (poi[1] - 2, poi[1] + 2)
            frame[rows[0]:rows[1], cols[0]:cols[1]] = \
                cv2.GaussianBlur(frame[rows[0]:rows[1], cols[0]:cols[1]],
                                 (5, 5), 5)

        for poi in self._bottomIdx.T:
            rows = (poi[0] - 2, poi[0] + 2)
            cols = (poi[1] - 2, poi[1] + 2)
            frame[rows[0]:rows[1], cols[0]:cols[1]] = \
                cv2.GaussianBlur(frame[rows[0]:rows[1], cols[0]:cols[1]],
                                 (5, 5), 3)

        for poi in self._leftIdx.T:
            rows = (poi[0] - 2, poi[0] + 2)
            cols = (poi[1] - 2, poi[1] + 2)
            frame[rows[0]:rows[1], cols[0]:cols[1]] = \
                cv2.GaussianBlur(frame[rows[0]:rows[1], cols[0]:cols[1]],
                                 (5, 5), 3)

        for poi in self._rightIdx.T:
            rows = (poi[0] - 2, poi[0] + 2)
            cols = (poi[1] - 2, poi[1] + 2)
            frame[rows[0]:rows[1], cols[0]:cols[1]] = \
                cv2.GaussianBlur(frame[rows[0]:rows[1], cols[0]:cols[1]],
                                 (5, 5), 3)

        return frame


    def _setup_sample_points(self):
        controlPoints = user_pref.read_calibration_data()
        pointCounts = user_pref.read_led_counts()

        topPoints = get_led_sample_points(controlPoints["top"],
                                          pointCounts["top"],
                                          independentAxis="x")
        self._topIdx = [[v[1], v[0]] for v in topPoints]
        self._topIdx = np.transpose(self._topIdx)

        bottomPoints = get_led_sample_points(controlPoints["bottom"],
                                             pointCounts["bottom"],
                                             independentAxis="x")
        self._bottomIdx = [[v[1], v[0]] for v in bottomPoints]
        self._bottomIdx = np.transpose(self._bottomIdx)

        leftPoints = get_led_sample_points(controlPoints["left"],
                                           pointCounts["left"],
                                           independentAxis="y")
        self._leftIdx = [[v[1], v[0]] for v in leftPoints]
        self._leftIdx = np.transpose(self._leftIdx)

        rightPoints = get_led_sample_points(controlPoints["right"],
                                            pointCounts["right"],
                                            independentAxis="y")
        self._rightIdx = [[v[1], v[0]] for v in rightPoints]
        self._rightIdx = np.transpose(self._rightIdx)


    def _setup_camera(self):
        (cameraPath, resolution) = user_pref.read_device_prefs()
        self._cam = Device(cameraPath)
        self._cam.open()
        self._cam.set_format(BufferType.VIDEO_CAPTURE, resolution[0], resolution[1], "MJPG")
        self._cam.controls.auto_exposure.value = 1
        self._cam.close()

        # close and reopen to make sure auto_exposure value is set before
        # setting exposure_time_absolute value
        self._cam.open()
        self._cam.set_format(BufferType.VIDEO_CAPTURE, resolution[0], resolution[1], "MJPG")
        self._cam.set_fps(BufferType.VIDEO_CAPTURE, 30)
        self._cam.controls.auto_exposure.value = 1
        self._cam.controls.brightness.value = 0
        self._cam.controls.saturation.value = 60
        self._cam.controls.exposure_time_absolute.value = 157
        self.jpegDecoder = TurboJPEG()
