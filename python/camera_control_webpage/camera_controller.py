from scipy.interpolate import CubicSpline
from turbojpeg import TurboJPEG, TJFLAG_FASTUPSAMPLE, TJFLAG_FASTDCT
from v4l2py.device import Device, BufferType
import numpy as np
import os
import sys

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

import user_pref

class CameraController:
    def __init__(self):
        pass

    def open(self):
        device, resolution = user_pref.read_device_prefs()
        self._cam = Device(device)
        self._cam.open()
        self._cam.set_format(BufferType.VIDEO_CAPTURE, resolution[0], resolution[1], "MJPG")
        self._cam.set_fps(BufferType.VIDEO_CAPTURE, 30)
        self._cam.controls.auto_exposure.value = 1
        self._cam.controls.white_balance_automatic.value = False
        self._cam.close()

        self._cam.open()
        self._cam.set_format(BufferType.VIDEO_CAPTURE, resolution[0], resolution[1], "MJPG")
        self._cam.set_fps(BufferType.VIDEO_CAPTURE, 30)
        self._cam.controls.auto_exposure.value = 1
        self._cam.controls.white_balance_automatic.value = False

        controlPoints = user_pref.read_calibration_data()
        topX = [c[0] for c in controlPoints["top"]]
        topY = [c[1] for c in controlPoints["top"]]
        topSpline = CubicSpline(topX, topY)
        self._topXs = [x for x in range(topX[0], topX[-1])]
        self._topYs = np.rint(topSpline(self._topXs)).astype(np.int32)

        bottomX = [c[0] for c in controlPoints["bottom"]]
        bottomY = [c[1] for c in controlPoints["bottom"]]
        bottomSpline = CubicSpline(bottomX, bottomY)
        self._bottomXs = [x for x in range(bottomX[0], bottomX[-1])]
        self._bottomYs = np.rint(bottomSpline(self._bottomXs)).astype(np.int32)

        leftX = [c[0] for c in controlPoints["left"]]
        leftY = [c[1] for c in controlPoints["left"]]
        leftSpline = CubicSpline(leftY, leftX)
        self._leftYs = [y for y in range(leftY[0], leftY[-1])]
        self._leftXs = np.rint(leftSpline(self._leftYs)).astype(np.int32)

        rightX = [c[0] for c in controlPoints["right"]]
        rightY = [c[1] for c in controlPoints["right"]]
        rightSpline = CubicSpline(rightY, rightX)
        self._rightYs = [y for y in range(rightY[0], rightY[-1])]
        self._rightXs = np.rint(rightSpline(self._rightYs)).astype(np.int32)

        self._jpegDecoder = TurboJPEG()


    def get_control_bounds(self):
        # brightness
        brightness = {
            "min": self._cam.controls.brightness.minimum,
            "max": self._cam.controls.brightness.maximum,
            "step": self._cam.controls.brightness.step,
            "default": self._cam.controls.brightness.default,
            "value": self._cam.controls.brightness.value,
        }
        #contrast
        contrast = {
            "min": self._cam.controls.contrast.minimum,
            "max": self._cam.controls.contrast.maximum,
            "step": self._cam.controls.contrast.step,
            "default": self._cam.controls.contrast.default,
            "value": self._cam.controls.contrast.value,
        }
        # saturation
        saturation = {
            "min": self._cam.controls.saturation.minimum,
            "max": self._cam.controls.saturation.maximum,
            "step": self._cam.controls.saturation.step,
            "default": self._cam.controls.saturation.default,
            "value": self._cam.controls.saturation.value,
        }
        # hue
        hue = {
            "min": self._cam.controls.hue.minimum,
            "max": self._cam.controls.hue.maximum,
            "step": self._cam.controls.hue.step,
            "default": self._cam.controls.hue.default,
            "value": self._cam.controls.hue.value,
        }
        # gamma
        gamma = {
            "min": self._cam.controls.gamma.minimum,
            "max": self._cam.controls.gamma.maximum,
            "step": self._cam.controls.gamma.step,
            "default": self._cam.controls.gamma.default,
            "value": self._cam.controls.gamma.value,
        }
        # gain
        gain = {
            "min": self._cam.controls.gain.minimum,
            "max": self._cam.controls.gain.maximum,
            "step": self._cam.controls.gain.step,
            "default": self._cam.controls.gain.default,
            "value": self._cam.controls.gain.value,
        }
        # white_balance_temperature
        white_balance_temperature = {
            "min": self._cam.controls.white_balance_temperature.minimum,
            "max": self._cam.controls.white_balance_temperature.maximum,
            "step": self._cam.controls.white_balance_temperature.step,
            "default": self._cam.controls.white_balance_temperature.default,
            "value": self._cam.controls.white_balance_temperature.value,
        }
        # sharpness
        sharpness = {
            "min": self._cam.controls.sharpness.minimum,
            "max": self._cam.controls.sharpness.maximum,
            "step": self._cam.controls.sharpness.step,
            "default": self._cam.controls.sharpness.default,
            "value": self._cam.controls.sharpness.value,
        }
        # exposure_time_absolute
        exposure_time_absolute = {
            "min": self._cam.controls.exposure_time_absolute.minimum,
            "max": self._cam.controls.exposure_time_absolute.maximum,
            "step": self._cam.controls.exposure_time_absolute.step,
            "default": self._cam.controls.exposure_time_absolute.default,
            "value": self._cam.controls.exposure_time_absolute.value,
        }

        return {
            "brightness": brightness,
            "contrast": contrast,
            "saturation": saturation,
            "hue": hue,
            "gamma": gamma,
            "gain": gain,
            "white_balance_temperature": white_balance_temperature,
            "sharpness": sharpness,
            "exposure_time_absolute": exposure_time_absolute,
        }


    def set_camera_controls(self, controls):
        brightness = int(controls["brightness"])
        contrast = int(controls["contrast"])
        saturation = int(controls["saturation"])
        hue = int(controls["hue"])
        gamma = int(controls["gamma"])
        gain = int(controls["gain"])
        white_balance_temperature = int(controls["white_balance_temperature"])
        sharpness = int(controls["sharpness"])
        exposure_time_absolute = int(controls["exposure_time_absolute"])

        self._cam.controls.brightness.value = brightness
        self._cam.controls.contrast.value = contrast
        self._cam.controls.saturation.value = saturation
        self._cam.controls.hue.value = hue
        self._cam.controls.gamma.value = gamma
        self._cam.controls.gain.value = gain
        self._cam.controls.white_balance_temperature.value = white_balance_temperature
        self._cam.controls.sharpness.value = sharpness
        self._cam.controls.exposure_time_absolute.value = exposure_time_absolute



    def stream_camera_frames(self):
        for frame in self._cam:
            yield (b"--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n"
                   + self._draw_calibration_points_to_frame(frame)
                   + b"\r\n")

    def _draw_calibration_points_to_frame(self, jpegFrame):
        frame = self._jpegDecoder.decode(bytes(jpegFrame), flags=TJFLAG_FASTUPSAMPLE|TJFLAG_FASTDCT)
        frame[self._topYs, self._topXs] = [0, 0, 255]
        frame[self._bottomYs, self._bottomXs] = [0, 0, 255]
        frame[self._leftYs, self._leftXs] = [0, 0, 255]
        frame[self._rightYs, self._rightXs] = [0, 0, 255]
        return self._jpegDecoder.encode(frame, quality=100)
