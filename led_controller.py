from multiprocessing import Process, Queue, Value
from pin_to_pin import AVAILABLE_PINS
from neopixel import NeoPixel
import user_pref
import queue
import numpy as np
import colorsys
from matplotlib.colors import rgb_to_hsv, hsv_to_rgb
from time import perf_counter
import copy

QUEUE_WAIT_TIMEOUT_S = 0.1
MAJOR_CHANGE_SAMPLE_TIME_S = 1
SHUTOFF_TIMEOUT_S = 3 * 60
LERP_PARAMETER = 0.3
MAJOR_CHANGE_DELTA = 0.45
SHUTOFF_DEBOUCE_TIME_S = 10

class LEDController:
    def __init__(self, shouldExit: Value, colorQueue: Queue):
        self._colorQueue = colorQueue
        self._shouldExit = shouldExit

    def run(self):
        print("Starting LED Controller Process...")
        self._read_user_prefs()
        self._setup_leds()
        self._isOff = False
        self._shutoff = False
        self._shutoffTime = 0
        # Stored in HSV
        self._prevColors = {
            "top": [[0, 0, 0] for _ in range(0, len(self._ledIndices["top"]))],
            "bottom": [[0, 0, 0] for _ in range(0, len(self._ledIndices["bottom"]))],
            "left": [[0, 0, 0] for _ in range(0, len(self._ledIndices["left"]))],
            "right": [[0, 0, 0] for _ in range(0, len(self._ledIndices["right"]))],
        }

        self._lastMajorColor = {
            "top": [[0, 0, 0] for _ in range(0, len(self._ledIndices["top"]))],
            "bottom": [[0, 0, 0] for _ in range(0, len(self._ledIndices["bottom"]))],
            "left": [[0, 0, 0] for _ in range(0, len(self._ledIndices["left"]))],
            "right": [[0, 0, 0] for _ in range(0, len(self._ledIndices["right"]))],
        }
        self._lastMajorSampleTs = 0
        self._lastMajorChangeTs = perf_counter()

        while self._shouldExit.value == 0:
            self._process_colors()
            self._signal_shutoff_if_needed()

        self._teardown_leds()

    def _process_colors(self):
        try:
            imgColors = self._colorQueue.get(block=True,
                                             timeout=QUEUE_WAIT_TIMEOUT_S)

            diffs = []
            for side, imgColor in imgColors.items():
                imgHsv = rgb_to_hsv(np.divide(imgColor, 255))
                prevHsv = self._prevColors[side]
                newHsv = np.add(
                    np.multiply(prevHsv, 1 - LERP_PARAMETER),
                    np.multiply(imgHsv, LERP_PARAMETER)
                )
                newRgb = np.rint(np.multiply(hsv_to_rgb(newHsv), 255)).astype(np.uint8)
                self._prevColors[side] = newHsv

                if not self._shutoff:
                    self._isOff = False
                    for colorIdx, ledIdx in enumerate(self._ledIndices[side]):
                        self._leds[ledIdx] = newRgb[colorIdx]
                elif not self._isOff:
                    for ledIdx in self._ledIndices[side]:
                        self._leds[ledIdx] = [0, 0, 0]
            self._leds.show()
            self._isOff = self._shutoff
            # print(np.max(diffs))

        except queue.Empty:
            # Empty Queue, do nothing.
            pass

    def _signal_shutoff_if_needed(self):
        if perf_counter() - self._lastMajorSampleTs >= MAJOR_CHANGE_SAMPLE_TIME_S:
                self._lastMajorSampleTs = perf_counter()
                diffs = []

                for side, currColor in self._prevColors.items():
                    lastMajorColor = self._lastMajorColor[side]
                    diff = np.subtract(currColor, lastMajorColor)
                    diffs.append(np.max(np.abs(diff)))
                maxDiff = np.max(diffs)

                if maxDiff >= MAJOR_CHANGE_DELTA:
                    # print(maxDiff)
                    self._lastMajorColor = copy.deepcopy(self._prevColors)
                    self._lastMajorChangeTs = perf_counter()
                    if perf_counter() - self._shutoffTime >= SHUTOFF_DEBOUCE_TIME_S:
                        self._shutoff = False
                elif not self._shutoff and perf_counter() - self._lastMajorChangeTs >= SHUTOFF_TIMEOUT_S:
                    self._shutoff = True
                    self._shutoffTime = perf_counter()


    def _read_user_prefs(self):
        ledConfig = user_pref.read_led_info()
        self._pin = AVAILABLE_PINS[ledConfig["pin"]]

        order = ledConfig["order"]
        counts = ledConfig["counts"]
        ledIndices = {}
        totalLedsSeen = 0
        for side in order:
            sideCount = counts[side]
            ledIndices[side] = list(range(totalLedsSeen,
                                          totalLedsSeen + sideCount))
            totalLedsSeen += sideCount

        for side, naturalOrientation in ledConfig["orientation"].items():
            if not naturalOrientation:
                ledIndices[side] = ledIndices[side][::-1]

        self._numLeds = totalLedsSeen
        self._ledIndices = ledIndices


    def _setup_leds(self):
        self._leds = NeoPixel(self._pin, self._numLeds, auto_write=False, brightness=0.5)

    def _teardown_leds(self):
        self._leds.deinit()



class LEDInterface():
    def __init__(self):
        self._shouldExit = Value('b', 0, lock=False)
        self._colorQueue = Queue()

        self._ledController = LEDController(self._shouldExit, self._colorQueue)

    def __enter__(self):
        self._ledControllerProcess = Process(target=LEDController.run,
                                             args=[self._ledController])
        self._ledControllerProcess.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._shouldExit.value = True
        self._ledControllerProcess.join()
        self._colorQueue.close()

    def set_colors(self, colors):
        try:
            self._colorQueue.get_nowait()
        except queue.Empty:
            pass

        self._colorQueue.put(colors)
