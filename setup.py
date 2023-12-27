import cv2
from datetime import datetime
import v4l2py
from v4l2py.device import BufferType, PixelFormat
import re
from os import path, mkdir


V4L2_DEVICE_PATTERN = r"^\/dev\/(video\d+)$"
V4L2_DEVICE_REGEX = re.compile(V4L2_DEVICE_PATTERN)

CONFIG_PATH = "config"
DEVICE_PREF = "v4l2_device.txt"
RESOLUTION_PREF = "resolution.txt"

IMG_OUTPUT_PATH = "/tmp"

def get_device_name(v4l2Node: str) -> str:
    with v4l2py.Device(v4l2Node) as cam:
        if len(cam.info.card) == 0:
            return "UNKNOWN DEVICE"
        else:
            return cam.info.card



def get_connected_devices():
    connectedDevices = []
    for device in v4l2py.iter_video_capture_devices():
        deviceNode = str(device.filename)
        deviceName = get_device_name(deviceNode)
        connectedDevices.append((deviceNode, deviceName))

    return connectedDevices


def choose_from_connected_devices(connectedDevices):
    if (len(connectedDevices) == 0):
        print("ERROR: No connected V4L2 devices found. "
              "Please connect a USB webcam and try again.")
        exit(1)

    print("Found the following device:")
    for idx, device in enumerate(connectedDevices):
        print(f"    [{idx + 1}] : {device[0]}  -->  {device[1]}")
    print()
    inp = 0
    while inp <= 0 or inp > len(connectedDevices):
        inp = input(f"Choose a device[1..{len(connectedDevices)}]: ")
        inp = int(inp)

    choiceIdx = inp - 1
    return connectedDevices[choiceIdx]


def save_chosen_device(device):
    selfPath = path.dirname(__file__)
    configPath = path.join(selfPath, CONFIG_PATH)
    prefPath = path.join(configPath, DEVICE_PREF)

    if not path.exists(configPath):
        print(f"{configPath} does not exist. Creating now.")
        mkdir(configPath)

    print(f"Writing {device[0]} to {prefPath}")
    with open(prefPath, "w") as prefFile:
        prefFile.write(device[0])
    print()


def choose_resolution(devicePath):
    availableResolutions = set()
    with v4l2py.Device(devicePath) as cam:
        for frameSize in cam.info.frame_sizes:
            pixelFormat = frameSize.pixel_format
            if (pixelFormat != PixelFormat.MJPEG):
                continue
            resolution = (frameSize.width, frameSize.height)
            availableResolutions.add(resolution)

    if len(availableResolutions) == 0:
        print(f"ERROR: No valid MJPEG resolutions found for device: "
              f"{devicePath}. Please select another device and try again.")
        exit(1)

    print("Found the following resolutions:")
    availableResolutions = sorted(availableResolutions)
    availableResolutions = availableResolutions[::-1]
    for idx, resolution in enumerate(availableResolutions):
        print(f"    [{idx + 1}] : {resolution}")

    inp = 0
    while inp <= 0 or inp > len(availableResolutions):
        inp = input(f"Choose a resolution[1..{len(availableResolutions)}]: ")
        inp = int(inp)

    choiceIdx = inp - 1
    return availableResolutions[choiceIdx]


def save_chosen_resolution(resolution):
    selfPath = path.dirname(__file__)
    configPath = path.join(selfPath, CONFIG_PATH)
    prefPath = path.join(configPath, RESOLUTION_PREF)

    if not path.exists(configPath):
        print(f"{configPath} does not exist. Creating now.")
        mkdir(configPath)

    print(f"Writing {resolution} to {prefPath}")
    with open(prefPath, "w") as prefFile:
        prefFile.writelines([str(resolution[0]), "\n", str(resolution[1])])
    print()


def draw_one_frame_from_device(devicePath, resolution):
    cam = cv2.VideoCapture(devicePath, cv2.CAP_V4L2)
    if not cam.isOpened():
        print(f"ERROR: Could not open {devicePath} to capture images. "
              "Please choose another device and try again.")
        exit(1)

    cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])

    print("Capturing 10 frames to let camera settle.")
    for i in range(1, 10):
        ret, frame = cam.read()
        if not ret:
            print(f"ERROR: Failed to get image from {devicePath}. "
                "Please choose another device and try again.")
            exit(1)

    currTime = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")
    imageFileName = f"capture-{currTime}.png"
    imageFilePath = path.join(IMG_OUTPUT_PATH, imageFileName)
    cv2.imwrite(imageFilePath, frame)
    print(f"Wrote file {imageFilePath}")

    cam.release()
    cv2.destroyAllWindows()



if __name__ == "__main__":
    connectedDevices = get_connected_devices()
    # chosenDevice = connectedDevices[1]
    chosenDevice = choose_from_connected_devices(connectedDevices)
    save_chosen_device(chosenDevice)
    devicePath = chosenDevice[0]

    # resolution = (1920, 1080)
    resolution = choose_resolution(devicePath)
    save_chosen_resolution(resolution)

    draw_one_frame_from_device(devicePath, resolution)
