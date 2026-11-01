def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return value
    return value
