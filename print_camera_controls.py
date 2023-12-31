from v4l2py.device import Device, MenuControl

cam = Device("/dev/video0")
cam.open()
for ctrl in cam.controls.values():
    print(ctrl)
    if isinstance(ctrl, MenuControl):
        for (index, name) in ctrl.items():
            print(f" - {index}: {name}")
