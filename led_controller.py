from adafruit_debouncer import Debouncer
from matplotlib.colors import rgb_to_hsv, hsv_to_rgb
from multiprocessing import Process, Queue, Value
from neopixel import NeoPixel
from pin_to_pin import AVAILABLE_PINS
from time import sleep
import digitalio
import numpy as np
import queue
import user_pref
from math import pi, cos

QUEUE_WAIT_TIMEOUT_S = 0.1
MAJOR_CHANGE_SAMPLE_TIME_S = 1
SHUTOFF_TIMEOUT_S = 3 * 60
LERP_PARAMETER = 0.5
MAJOR_CHANGE_DELTA = 0.45
SHUTOFF_DEBOUCE_TIME_S = 10
COS_120_DEG = cos((pi / 180) * 120)

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
            "top": [[0, 0, 0] for _ in range(0, len(self._ledIndices["top"]))],
            "bottom": [[0, 0, 0] for _ in range(0, len(self._ledIndices["bottom"]))],
            "left": [[0, 0, 0] for _ in range(0, len(self._ledIndices["left"]))],
            "right": [[0, 0, 0] for _ in range(0, len(self._ledIndices["right"]))],
        }

        while self._shouldExit.value == 0:
            self._shutoff = not self._power.value
            self._process_colors()

        self._teardown_leds()


    def _process_colors(self):
        try:
            imgColors = self._colorQueue.get(block=True,
                                             timeout=QUEUE_WAIT_TIMEOUT_S)

            for side, imgColor in imgColors.items():
                imgHsv = rgb_to_hsv(np.divide(imgColor, 255))

                # Boost the saturation of colors that are close to
                # red.
                redComponent = np.multiply(imgHsv[:, 0], 2*pi)
                redComponent = np.cos(redComponent)
                redComponent = np.add(redComponent, COS_120_DEG + 1)
                redComponent = np.maximum(redComponent, 1) # clip all values < 1 to 1
                redComponent = np.power(redComponent, 3)
                imgHsv[:, 1] = np.multiply(imgHsv[:, 1], redComponent)
                imgHsv[:, 1] = np.minimum(imgHsv[:, 1], 1) # clips the max value to 1

                prevHsv = self._prevColors[side]
                newHsv = np.add(
                    np.multiply(prevHsv, 1 - LERP_PARAMETER),
                    np.multiply(imgHsv, LERP_PARAMETER)
                )
                newRgb = np.rint(np.multiply(hsv_to_rgb(newHsv), 255)).astype(np.uint8)
                self._prevColors[side] = newHsv

                if not self._isOff:
                    for colorIdx, ledIdx in enumerate(self._ledIndices[side]):
                        self._leds[ledIdx] = newRgb[colorIdx]

            self._leds.show()

        except queue.Empty:
            # Empty Queue, do nothing.
            pass

        if self._shutoff and not self._isOff:
            for ledIndices in self._ledIndices.values():
                for ledIdx in ledIndices:
                    self._leds[ledIdx] = [0, 0, 0]
            self._leds.show()
        self._isOff = self._shutoff


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
