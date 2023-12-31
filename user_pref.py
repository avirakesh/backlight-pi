from os import path
import json

CONFIG_PATH = "config"
IGNORED_NODE_FILE = "ignored_nodes.txt"
DEVICE_FILE = "v4l2_device.txt"
RESOLUTION_FILE = "resolution.txt"
CALIBRATION_FILE = "calibration.json"
LED_INFO_FILE = "led.json"


def read_ignored_nodes():
    configPath = path.join(path.dirname(__file__), CONFIG_PATH)
    if not path.exists(configPath):
        return set()

    ignoredNodesPath = path.join(configPath, IGNORED_NODE_FILE)
    if not path.exists(ignoredNodesPath):
        return set()

    ignoredNodes = set()
    with open(ignoredNodesPath, "r") as f:
        for line in f:
            l = line.strip()
            if l:
                ignoredNodes.add(l)

    return ignoredNodes


def _read_device(configPath):
    devicePrefPath = path.join(configPath, DEVICE_FILE)
    if not path.exists(devicePrefPath):
        print(f"ERROR: {devicePrefPath} does not exist. Run setup.py first!")
        exit(1)

    with open(devicePrefPath, "r") as f:
        devices = f.readlines()
        if len(devices) == 0:
            print(f"ERROR: No device found in {devicePrefPath}. "
                  "Run setup.py first!")
            exit(1)

        if len(devices) > 1:
            print(f"ERROR: More than one device found in {devicePrefPath}. "
                  "Run setup.py first!")
            exit(1)

        device = devices[0].strip()
        if len(device) == 0:
            print(f"ERROR: No device found in {devicePrefPath}. "
                  "Run setup.py first!")
            exit(1)

        return device


def _read_resolution(configPath):
    resolutionPrefPath = path.join(configPath, RESOLUTION_FILE)
    if not path.exists(resolutionPrefPath):
        print(f"ERROR: {resolutionPrefPath} does not exist. Run setup.py first!")
        exit(1)

    with open(resolutionPrefPath, "r") as f:
        resolution = f.readlines()
        if len(resolution) != 2:
            print(f"ERROR: Invalid resolution in {resolutionPrefPath}. "
                  "Run setup.py first!")
            exit(1)

        selectedResolution = (int(resolution[0].strip()),
                              int(resolution[1].strip()))

        return selectedResolution


def read_device_prefs():
    configPath = path.join(path.dirname(__file__), CONFIG_PATH)
    if not path.exists(configPath):
        print(f"ERROR: {configPath} does not exist. Run setup.py first!")
        exit(1)

    device = _read_device(configPath)
    resolution = _read_resolution(configPath)
    return (device, resolution)


def read_calibration_data():
    configPath = path.join(path.dirname(__file__), CONFIG_PATH)
    if not path.exists(configPath):
        print(f"ERROR: {configPath} does not exist. Run setup.py first!")
        exit(1)

    calibrationFilePath = path.join(configPath, CALIBRATION_FILE)
    if not path.exists(calibrationFilePath):
        print(f"ERROR: {calibrationFilePath} does not exist. Please populate "
              f"{CALIBRATION_FILE} from the calibration frame.")
        exit(1)

    with open(calibrationFilePath, "r") as calibrationFile:
        rawJson = json.load(calibrationFile)

    if not rawJson:
        print(f"ERROR: {calibrationFilePath} does not contain the calibration "
              f"data. Please populate {calibrationFilePath} from the "
              "calibration frame.")
        exit(1)

    topRaw = rawJson["top"]
    if len(topRaw) < 4:
        print("ERROR: Top edge does not have enough control points. "
              "Please provide at least 2 control points")
        exit(1)

    bottomRaw = rawJson["bottom"]
    if len(bottomRaw) < 4:
        print("ERROR: Bottom edge does not have enough control points. "
              "Please provide at least 2 control points")
        exit(1)

    leftRaw = rawJson["left"]
    if len(leftRaw) < 4:
        print("ERROR: Left edge does not have enough control points. "
              "Please provide at least 2 control points")
        exit(1)

    rightRaw = rawJson["right"]
    if len(rightRaw) < 4:
        print("ERROR: Top edge does not have enough control points. "
              "Please provide at least 2 control points")
        exit(1)

    topControlPoints = [(topRaw[i], topRaw[i+1]) \
                            for i in range(0, len(topRaw), 2)]
    bottomControlPoints = [(bottomRaw[i], bottomRaw[i+1]) \
                            for i in range(0, len(bottomRaw), 2)]
    leftControlPoints = [(leftRaw[i], leftRaw[i+1]) \
                            for i in range(0, len(leftRaw), 2)]
    rightControlPoints = [(rightRaw[i], rightRaw[i+1]) \
                            for i in range(0, len(rightRaw), 2)]

    return {
        "top": topControlPoints,
        "bottom": bottomControlPoints,
        "left": leftControlPoints,
        "right": rightControlPoints
    }

def read_led_counts():
    configPath = path.join(path.dirname(__file__), CONFIG_PATH)
    if not path.exists(configPath):
        print(f"ERROR: {configPath} does not exist. Run setup.py first!")
        exit(1)

    ledInfoFilePath = path.join(configPath, LED_INFO_FILE)
    if not path.exists(ledInfoFilePath):
        print(f"ERROR: {ledInfoFilePath} does not exist. Run setup.py first!")
        exit(1)

    with open(ledInfoFilePath, "r") as ledInfoFile:
        rawJson = json.load(ledInfoFile)

    return rawJson["counts"]

def read_led_info():
    configPath = path.join(path.dirname(__file__), CONFIG_PATH)
    if not path.exists(configPath):
        print(f"ERROR: {configPath} does not exist. Run setup.py first!")
        exit(1)

    ledInfoFilePath = path.join(configPath, LED_INFO_FILE)
    if not path.exists(ledInfoFilePath):
        print(f"ERROR: {ledInfoFilePath} does not exist. Run setup.py first!")
        exit(1)

    with open(ledInfoFilePath, "r") as ledInfoFile:
        rawJson = json.load(ledInfoFile)

    return rawJson
