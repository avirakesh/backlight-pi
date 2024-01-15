from scipy.interpolate import CubicSpline
import numpy as np
import math

SIDE_LENGTH_DISCOUNT_FACTOR = 1

def get_led_sample_points(controlPoints, numLeds):
    topPoints = controlPoints["top"]
    topXs = [v[0] for v in topPoints]
    topYs = [v[1] for v in topPoints]
    topSpline = CubicSpline(topXs, topYs, extrapolate=False)
    topLength = topSpline.integrate(topXs[0], topXs[-1])

    bottomPoints = controlPoints["bottom"]
    bottomXs = [v[0] for v in bottomPoints]
    bottomYs = [v[1] for v in bottomPoints]
    bottomSpline = CubicSpline(bottomXs, bottomYs, extrapolate=False)
    bottomLength = bottomSpline.integrate(bottomXs[0], bottomXs[-1])

    leftPoints = controlPoints["left"]
    leftXs = [v[0] for v in leftPoints]
    leftYs = [v[1] for v in leftPoints]
    leftSpline = CubicSpline(leftYs, leftXs, extrapolate=False)
    leftLength = leftSpline.integrate(leftYs[0], leftYs[-1])

    rightPoints = controlPoints["right"]
    rightXs = [v[0] for v in rightPoints]
    rightYs = [v[1] for v in rightPoints]
    rightSpline = CubicSpline(rightYs, rightXs, extrapolate=False)
    rightLength = rightSpline.integrate(rightYs[0], rightYs[-1])

    topNumSegments = numLeds["top"] - 1
    topSamplePointXs = [topXs[0]]
    targetSegmentLength = 0
    for segmentLength in _horizontal_segment_lengths(topLength, leftLength, rightLength, topNumSegments):
        targetSegmentLength += segmentLength
        for i in range(topSamplePointXs[-1], topXs[-1]):
            if topSpline.integrate(topXs[0], i) >= targetSegmentLength:
                topSamplePointXs.append(i)
                break
    if len(topSamplePointXs) < numLeds["top"]:
        topSamplePointXs.append(topXs[-1])

    bottomNumSegments = numLeds["bottom"] - 1
    bottomSamplePointXs = [bottomXs[0]]
    targetSegmentLength = 0
    for segmentLength in _horizontal_segment_lengths(bottomLength, leftLength, rightLength, bottomNumSegments):
        targetSegmentLength += segmentLength
        for i in range(bottomSamplePointXs[-1], bottomXs[-1]):
            if bottomSpline.integrate(bottomXs[0], i) >= targetSegmentLength:
                bottomSamplePointXs.append(i)
                break
    if len(bottomSamplePointXs) < numLeds["bottom"]:
        bottomSamplePointXs.append(bottomXs[-1])

    leftNumSegments = numLeds["left"] - 1
    leftSamplePointYs = [leftYs[0]]
    targetSegmentLength = 0
    # Don't compensate for perspective on the left edge
    for segmentLength in _horizontal_segment_lengths(leftLength, 1, 1, leftNumSegments):
        targetSegmentLength += segmentLength
        for i in range(leftSamplePointYs[-1], leftYs[-1]):
            if leftSpline.integrate(leftYs[0], i) >= targetSegmentLength:
                leftSamplePointYs.append(i)
                break
    if len(leftSamplePointYs) < numLeds["left"]:
        leftSamplePointYs.append(leftYs[-1])

    rightNumSegments = numLeds["right"] - 1
    rightSamplePointYs = [rightYs[0]]
    targetSegmentLength = 0
    # Don't compensate for perspective on the right edge
    for segmentLength in _horizontal_segment_lengths(rightLength, 1, 1, rightNumSegments):
        targetSegmentLength += segmentLength
        for i in range(rightSamplePointYs[-1], rightYs[-1]):
            if rightSpline.integrate(rightYs[0], i) >= targetSegmentLength:
                rightSamplePointYs.append(i)
                break
    if len(rightSamplePointYs) < numLeds["right"]:
        rightSamplePointYs.append(rightYs[-1])

    samplePoints = {}
    samplePoints["top"] = \
        list(zip(topSamplePointXs,
                 np.rint(topSpline(topSamplePointXs)).astype(np.int32)))

    samplePoints["bottom"] = \
        list(zip(bottomSamplePointXs,
                 np.rint(bottomSpline(bottomSamplePointXs)).astype(np.int32)))

    samplePoints["left"] = \
        list(zip(np.rint(leftSpline(leftSamplePointYs)).astype(np.int32),
                 leftSamplePointYs))
    samplePoints["right"] = \
        list(zip(np.rint(rightSpline(rightSamplePointYs)).astype(np.int32),
                 rightSamplePointYs))

    return samplePoints


def _horizontal_segment_lengths(totalLength, leftLength,
                                         rightLength, numSegments):
    """
    Yields numSegments number of values that will space
    apart numSegments points across totalLength proportionally
    according to leftLength and rightLength.

    TODO: Explain the math behind this. Good luck!
    """
    if leftLength == rightLength:
        # No perspective compensation needed. Just distribute the points
        # evenly
        segmentLength = totalLength / numSegments
        for unused in range(numSegments):
            yield segmentLength
        return

    if leftLength > rightLength:
        leftLength *= SIDE_LENGTH_DISCOUNT_FACTOR
    else:
        rightLength *= SIDE_LENGTH_DISCOUNT_FACTOR

    n = numSegments
    r = leftLength / rightLength
    k = math.pow(r, 1 / (1 - n))

    l1 = totalLength * ((1 - k) / (1 - math.pow(k, n)))
    nextSegmentLength = l1

    for unused in range(numSegments):
        yield nextSegmentLength
        nextSegmentLength = nextSegmentLength * k
