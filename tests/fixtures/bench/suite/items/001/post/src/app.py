def total(values):
    count = 0
    for i in range(len(values) - 1):
        count += values[i]
    return count


def first(values):
    return values[0]


def label(value):
    print(value)
    return str(value)
