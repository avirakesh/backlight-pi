from datetime import datetime
from math import floor
from os import path
from pin_to_pin import AVAILABLE_PINS
from scipy.interpolate import CubicSpline
from time import perf_counter, sleep
import board
import cv2
import json
import neopixel
import numpy as np
import sys
import threading
import user_pref
from v4l2py.device import Device, BufferType
from turbojpeg import TurboJPEG, TJFLAG_FASTUPSAMPLE, TJFLAG_FASTDCT

IMG_OUTPUT_PATH = "/tmp"
DEFAULT_RECORDING_WAIT_TIME_S = 10

def _capture_frame(waitTimeSec = DEFAULT_RECORDING_WAIT_TIME_S):
    device, resolution = user_pref.read_device_prefs()
    print(device, resolution)

    with Device(device) as cam:
        cam.set_format(BufferType.VIDEO_CAPTURE, resolution[0], resolution[1], "MJPG")
        cam.set_fps(BufferType.VIDEO_CAPTURE, 30)
        cam.controls.auto_exposure.value = 1
        # reopen device to ensure that auto_exposure_value is reflected when
        # setting exposure_time_absolute value

    with Device(device) as cam:
        cam.set_format(BufferType.VIDEO_CAPTURE, resolution[0], resolution[1], "MJPG")
        cam.set_fps(BufferType.VIDEO_CAPTURE, 30)
        cam.controls.auto_exposure.value = 1
        cam.controls.brightness.value = 0
        cam.controls.saturation.value = 60
        cam.controls.exposure_time_absolute.value = 157
        jpegDecoder = TurboJPEG()

        print(f"Running camera stream for ~{waitTimeSec}s before capturing "
                "frame")

        start_time = perf_counter()
        diff = perf_counter() - start_time
        prev_diff = floor(diff)
        for f in cam:
            jpegFrame = f
            if floor(diff) != prev_diff:
                prev_diff = floor(diff)
                print(f"{prev_diff}", end="..", flush=True)
            diff = perf_counter() - start_time
            if diff >= waitTimeSec:
                break
        print()
        print("Capturing frame.")
        frame = jpegDecoder.decode(bytes(jpegFrame), flags=TJFLAG_FASTUPSAMPLE|TJFLAG_FASTDCT)

    return frame


def capture_frame_for_calibration():
    print("Grabbing Frame for calibration")
    print("-------------------------------")
    frame = _capture_frame()
    currTime = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")
    imageFileName = f"calibration-capture-{currTime}.png"
    imageFilePath = path.join(IMG_OUTPUT_PATH, imageFileName)
    cv2.imwrite(imageFilePath, frame)
    print(f"Wrote calibration image: {imageFilePath}")


def display_calibrated_frame():
    print("Displaying a calibrated frame")
    print("-----------------------------")
    controlPoints = user_pref.read_calibration_data()
    topX = [c[0] for c in controlPoints["top"]]
    topY = [c[1] for c in controlPoints["top"]]
    topSpline = CubicSpline(topX, topY)

    bottomX = [c[0] for c in controlPoints["bottom"]]
    bottomY = [c[1] for c in controlPoints["bottom"]]
    bottomSpline = CubicSpline(bottomX, bottomY)

    leftX = [c[0] for c in controlPoints["left"]]
    leftY = [c[1] for c in controlPoints["left"]]
    leftSpline = CubicSpline(leftY, leftX)

    rightX = [c[0] for c in controlPoints["right"]]
    rightY = [c[1] for c in controlPoints["right"]]
    rightSpline = CubicSpline(rightY, rightX)

    frame = _capture_frame(waitTimeSec=5)

    topXs = [x for x in range(topX[0], topX[-1])]
    topYs = np.rint(topSpline(topXs)).astype(np.int32)
    frame[topYs, topXs] = [0, 0, 255]

    bottomXs = [x for x in range(bottomX[0], bottomX[-1])]
    bottomYs = np.rint(bottomSpline(bottomXs)).astype(np.int32)
    frame[bottomYs, bottomXs] = [0, 0, 255]

    leftYs = [y for y in range(leftY[0], leftY[-1])]
    leftXs = np.rint(leftSpline(leftYs)).astype(np.int32)
    frame[leftYs, leftXs] = [0, 0, 255]

    rightYs = [y for y in range(rightY[0], rightY[-1])]
    rightXs = np.rint(rightSpline(rightYs)).astype(np.int32)
    frame[rightYs, rightXs] = [0, 0, 255]

    currTime = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")
    imageFileName = f"calibration-show-{currTime}.png"
    imageFilePath = path.join(IMG_OUTPUT_PATH, imageFileName)
    cv2.imwrite(imageFilePath, frame)
    print(f"Wrote calibration image: {imageFilePath}")


def get_int_from_user(message, conditional = lambda x: True):
    while(True):
        try:
            raw_val = input(f"{message}: ")
            val = int(raw_val)

            if conditional(val):
                return val
            else:
                print(f"ERROR: '{val}' is invalid. Please try again.\n")
        except ValueError:
            print(f"ERROR: '{raw_val}' is invalid. Please try again.\n")


def get_str_from_user(message, conditional = lambda s: True):
    while True:
        userInput = input(f"{message}: ")
        if (conditional(userInput)):
            return userInput
        else:
            print(f"ERROR: {userInput} is not a valid option.\n")


def get_strip_order_from_user():
    order = []

    validOptions = {"top", "right", "left", "bottom"}

    optionsString = "|".join(validOptions)
    userInput = get_str_from_user(f"First Strip [{optionsString}]",
                                     lambda s: s in validOptions)
    order.append(userInput)
    validOptions.remove(userInput)

    optionsString = "|".join(validOptions)
    userInput = get_str_from_user(f"Second Strip [{optionsString}]",
                                     lambda s: s in validOptions)
    order.append(userInput)
    validOptions.remove(userInput)


    optionsString = "|".join(validOptions)
    userInput = get_str_from_user(f"Third Strip [{optionsString}]")
    order.append(userInput)
    validOptions.remove(userInput)

    userInput = list(validOptions)[0]
    print(f"Assuming fourth strip is '{userInput}'.")
    order.append(userInput)

    return order


def wave_leds(strip, ledIdxes, sentinel):
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    colorIdx = -1
    while not sentinel.is_set():
        colorIdx = (colorIdx + 1) % len(colors)
        prevLedIdx = ledIdxes[-1]
        for ledIdx in ledIdxes:
            strip[prevLedIdx] = (0, 0, 0)
            strip[ledIdx] = colors[colorIdx]
            strip.show()
            prevLedIdx = ledIdx
        strip[prevLedIdx] = (0, 0, 0)


def get_strip_orientation_from_user(drivingPin, stripOrder, stripSizes):
    stripOrientation = {}
    pin = AVAILABLE_PINS[drivingPin]
    sideToLedIdx = {}
    totalLedsSeen = 0
    for side in stripOrder:
        numLeds = stripSizes[side]
        sideToLedIdx[side] = list(range(totalLedsSeen, totalLedsSeen + numLeds))
        totalLedsSeen += numLeds

    print("Testing LED strip orientation.")
    print("------------------------------")
    print("Watch for LEDs lighting up!")
    print()

    with neopixel.NeoPixel(pin, totalLedsSeen) as strip:
        sentinel = threading.Event()


        print("Testing TOP:")
        sentinel.clear()
        ledThread = threading.Thread(target=wave_leds,
                                    args=[strip, sideToLedIdx["top"],
                                          sentinel])
        ledThread.start()
        lToR = get_str_from_user("    Are the LED lighting up from left to "
                                 "right?[y|n]",
                                 lambda s: s in {"y", "n"})
        stripOrientation["top"] = lToR == "y"
        sentinel.set()
        ledThread.join()
        print()

        print("Testing BOTTOM:")
        sentinel.clear()
        ledThread = threading.Thread(target=wave_leds,
                                    args=[strip, sideToLedIdx["bottom"],
                                          sentinel])
        ledThread.start()
        lToR = get_str_from_user("    Are the LED lighting up from left to "
                                 "right?[y|n]",
                                 lambda s: s in {"y", "n"})
        stripOrientation["bottom"] = lToR == "y"
        sentinel.set()
        ledThread.join()
        print()

        print("Testing LEFT:")
        sentinel.clear()
        ledThread = threading.Thread(target=wave_leds,
                                    args=[strip, sideToLedIdx["left"],
                                          sentinel])
        ledThread.start()
        tToB = get_str_from_user("    Are the LED lighting up from top to "
                                 "bottom?[y|n]",
                                 lambda s: s in {"y", "n"})
        stripOrientation["left"] = tToB == "y"
        sentinel.set()
        ledThread.join()
        print()

        print("Testing RIGHT:")
        sentinel.clear()
        ledThread = threading.Thread(target=wave_leds,
                                     args=[strip, sideToLedIdx["right"],
                                           sentinel])
        ledThread.start()
        tToB = get_str_from_user("    Are the LED lighting up from top to "
                                 "bottom?[y|n]",
                                 lambda s: s in {"y", "n"})
        stripOrientation["right"] = tToB == "y"
        sentinel.set()
        ledThread.join()

    return stripOrientation


def get_led_information_from_user():
    print("Setting up LED Strips")
    print("---------------------")
    print("The following prompts will collect information "
          "about the LED strips.")
    print()

    drivingPin = get_int_from_user("GPIO Pin driving the LED Strip",
                                   lambda x: x in AVAILABLE_PINS.keys())
    print()

    print("Count the number of LEDs on the strip on the sides of the "
          "monitor.")
    numLedTop = get_int_from_user("    Number of LEDs on the TOP edge",
                                  lambda x: x > 0 and x <= 512)
    numLedBottom = get_int_from_user("    Number of LEDs on the BOTTOM edge",
                                     lambda x: x > 0 and x <= 512)
    numLedLeft = get_int_from_user("    Number of LEDs on the LEFT edge",
                                   lambda x: x > 0 and x <= 512)
    numLedRight = get_int_from_user("    Number of LEDs on the RIGHT edge",
                                    lambda x: x > 0 and x <= 512)
    stripSizes = {
        "top": numLedTop,
        "bottom": numLedBottom,
        "left": numLedLeft,
        "right": numLedRight
    }
    print()

    stripOrder = get_strip_order_from_user()
    print()

    stripOrientation = get_strip_orientation_from_user(drivingPin, stripOrder,
                                                       stripSizes)
    print()

    powerPin = get_int_from_user("Pin to turn LEDs on and off",
                                    lambda x: x in AVAILABLE_PINS.keys())

    ledInfo = {
        "pin": drivingPin,
        "counts": stripSizes,
        "order": stripOrder,
        "orientation": stripOrientation,
        "power_pin": powerPin
    }

    configPath = path.join(user_pref.CONFIG_PATH)
    if not path.exists(configPath):
        print(f"ERROR: {configPath} does not exist. Run setup.py first!")
        exit(1)

    ledFilePath = path.join(configPath, user_pref.LED_INFO_FILE)
    with open(ledFilePath, "w") as ledFile:
        json.dump(ledInfo, ledFile, indent=4)


def run_full_calibration():
    while True:
        capture_frame_for_calibration()
        calibrationPath = path.join(user_pref.CONFIG_PATH,
                                    user_pref.CALIBRATION_FILE)
        print()
        input(f"Please fill out {calibrationPath} and press any key.")
        calibrationPath = path.join(user_pref.CONFIG_PATH,
                                    user_pref.CALIBRATION_FILE)
        if not path.exists(calibrationPath):
            print(f"{calibrationPath} does not exist. Retrying.")
            print()
            continue
        print()
        display_calibrated_frame()
        print("Does the calibration frame look right?")
        userInput = get_str_from_user("'y' to continue, 'n' to retry",
                                      lambda s: s in {"y", "n"})
        if (userInput == "y"):
            break

    get_led_information_from_user()
    print("All calibration done. Backlight Pi should be good to go!")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        run_full_calibration()
        exit(0)

    if (len(sys.argv) > 2):
        print("Invalid args. Usage:")
        print(f"    python {sys.argv[0]} [set-control|get-control|set-led]")
        print(f"    Args: ")
        print(f"        set-control : Get a frame to get control points from")
        print(f"        get-control : Show bounds as set by control points")
        print(f"        set-led     : Setup LED strip information")
        exit(1)

    elif sys.argv[1] == "set-control":
        capture_frame_for_calibration()
    elif sys.argv[1] == "get-control":
        display_calibrated_frame()
    elif sys.argv[1] == "set-led":
        get_led_information_from_user()
    else:
        print("Invalid args. Usage:")
        print(f"    python {sys.argv[0]} [set-control|get-control|set-led]")
        print(f"    Args: ")
        print(f"        set-control : Get a frame to get control points from")
        print(f"        get-control : Show bounds as set by control points")
        print(f"        set-led     : Setup LED strip information")
        exit(1)
