from adafruit_debouncer import Debouncer
from copy import deepcopy
from math import pi, cos
from matplotlib.colors import rgb_to_hsv, hsv_to_rgb
from multiprocessing import Process, Queue, Value
from neopixel import NeoPixel
from pin_to_pin import AVAILABLE_PINS
from time import sleep
import digitalio
import numpy as np
import queue
import user_pref

COS_120_DEG = cos((pi / 180) * 120)
LERP_PARAMETER = 0.5
MAX_ITERATIONS_SINCE_FRAME = 10
QUEUE_WAIT_TIMEOUT_S = 0.1

class LEDController:
    def __init__(self, shouldExit: Value, colorQueue: Queue, power: Value):
        self._colorQueue = colorQueue
        self._shouldExit = shouldExit
        self._power = power


    def run(self):
        print("Starting LED Controller Process...")
        self._read_user_prefs()
        self._setup_leds()
        self._isOff = False
        self._shutoff = False
        # Stored in HSV
        self._prevColors = {
            "top": np.array([[0, 0, 0] for _ in range(0, len(self._ledIndices["top"]))]),
            "bottom": np.array([[0, 0, 0] for _ in range(0, len(self._ledIndices["bottom"]))]),
            "left": np.array([[0, 0, 0] for _ in range(0, len(self._ledIndices["left"]))]),
            "right": np.array([[0, 0, 0] for _ in range(0, len(self._ledIndices["right"]))]),
        }
        self._targetColors = deepcopy(self._prevColors)
        self._iterationsSinceFrame = MAX_ITERATIONS_SINCE_FRAME + 1

        while self._shouldExit.value == 0:
            self._shutoff = not self._power.value
            self._process_colors()

        self._teardown_leds()


    def _process_colors(self):
        try:
            # Don't block if we can iterate on the color
            shouldBlock = self._iterationsSinceFrame > MAX_ITERATIONS_SINCE_FRAME
            imgColors = self._colorQueue.get(block=shouldBlock,
                                             timeout=QUEUE_WAIT_TIMEOUT_S)

            # Frame found, process new frame!
            self._targetColors = {
                side: rgb_to_hsv(np.divide(imgColor, 255)) \
                    for side, imgColor in imgColors.items()
            }
            self._iterationsSinceFrame = 1
            self._transition_to_target_colors()

        except queue.Empty:
            if (self._iterationsSinceFrame < MAX_ITERATIONS_SINCE_FRAME):
                self._iterationsSinceFrame += 1
                self._transition_to_target_colors()

        if self._shutoff and not self._isOff:
            for ledIndices in self._ledIndices.values():
                for ledIdx in ledIndices:
                    self._leds[ledIdx] = [0, 0, 0]
            self._leds.show()
        self._isOff = self._shutoff


    def _transition_to_target_colors(self):
        if self._isOff:
            return

        for side, imgHsv in self._targetColors.items():
            prevHsv = self._prevColors[side]
            hueDiff = np.subtract(imgHsv[:, 0], prevHsv[:, 0])
            goingCCW = np.greater(hueDiff, 0.5)
            goingCW = np.less(hueDiff, -0.5)
            prevHsv[:, 0] = np.where(goingCCW, prevHsv[:, 0], prevHsv[:, 0] + 1)
            prevHsv[:, 0] = np.where(goingCW, prevHsv[:, 0], prevHsv[:, 0] - 1)

            newHsv = np.add(
                np.multiply(prevHsv, 1 - LERP_PARAMETER),
                np.multiply(imgHsv, LERP_PARAMETER)
            )
            newHsv[:, 0] = np.mod(newHsv[:, 0], 1)
            newRgb = np.rint(np.multiply(hsv_to_rgb(newHsv), 255)).astype(np.uint8)
            self._prevColors[side] = newHsv

            for colorIdx, ledIdx in enumerate(self._ledIndices[side]):
                self._leds[ledIdx] = newRgb[colorIdx]

        self._leds.show()


    def _read_user_prefs(self):
        ledConfig = user_pref.read_led_info()
        self._controlPin = AVAILABLE_PINS[ledConfig["pin"]]
        self._powerPin = AVAILABLE_PINS[ledConfig["power_pin"]]

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
        self._leds = NeoPixel(self._controlPin, self._numLeds, auto_write=False, brightness=0.5)


    def _teardown_leds(self):
        self._leds.deinit()


class LEDInterface():
    def __init__(self):
        self._shouldExit = Value('b', 0, lock=False)
        self._power = Value('b', 0, lock=False)
        self._colorQueue = Queue()

        self._ledController = LEDController(self._shouldExit, self._colorQueue, self._power)

    def __enter__(self):
        self._setup_power_pin()
        self._ledControllerProcess = Process(target=LEDController.run,
                                             args=[self._ledController])
        self._ledControllerProcess.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._power.value = False
        self._shouldExit.value = True
        self._ledControllerProcess.join()
        self._colorQueue.close()

    def set_colors(self, colors):
        try:
            self._colorQueue.get_nowait()
        except queue.Empty:
            pass

        self._colorQueue.put(colors)


    def _setup_power_pin(self):
        ledConfig = user_pref.read_led_info();
        self._powerPin = AVAILABLE_PINS[ledConfig["power_pin"]]
        self._powerPin = digitalio.DigitalInOut(self._powerPin)
        self._powerPin.direction = digitalio.Direction.INPUT

    def update_and_get_power_state(self):
        self._power.value = self._powerPin.value
        return self._powerPin.value
