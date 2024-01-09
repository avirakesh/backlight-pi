from flask import Flask, render_template, Response, request
from camera_controller import CameraController
import json

app = Flask("camera_control.playground", template_folder="templates")


cameraController = CameraController()
cameraController.open()

@app.route("/camera_feed")
def camera_feed():
    return Response(cameraController.stream_camera_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/get_control_bounds")
def get_control_bounds():
    return cameraController.get_control_bounds()

@app.route("/set_camera_control", methods=["POST"])
def set_camera_control():
    cameraController.set_camera_controls(request.json)
    return ""

@app.route("/")
def index():
    return render_template("index.html")

app.run(host="0.0.0.0", port=8081)
