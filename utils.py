from scipy.interpolate import CubicSpline
import numpy as np

def get_led_sample_points(controlPoints, numLeds, independentAxis="x"):
    controlX = [v[0] for v in controlPoints]
    controlY = [v[1] for v in controlPoints]

    if independentAxis == "x":
        independentControls = controlX
        dependentControls = controlY
    else:
        independentControls = controlY
        dependentControls = controlX

    spline = CubicSpline(independentControls, dependentControls,
                         extrapolate=False)
    length = spline.integrate(independentControls[0],
                              independentControls[-1])
    segmentLength = length / (numLeds - 1)
    ledPoints = [independentControls[0]]
    startPoint = independentControls[0]

    for i in range(0, numLeds - 2):
        targetLength = segmentLength * (i + 1)
        for testPoint in range(startPoint, independentControls[-1]):
            if spline.integrate(startPoint, testPoint) >= targetLength:
                ledPoints.append(testPoint)
                break
    ledPoints.append(independentControls[-1])

    if len(ledPoints) != numLeds:
        print(f"Could not determine {numLeds} points the spline. "
                f"Found {len(ledPoints)} points."
                " Are the control points valid?")
        exit(1)

    if independentAxis == "x":
        return list(zip(ledPoints,
                        np.rint(spline(ledPoints)).astype(np.int32)))
    else:
        return list(zip(np.rint(spline(ledPoints)).astype(np.int32),
                        ledPoints))
