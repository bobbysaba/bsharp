from qtpy import QtGui


FONT_FAMILY = "Helvetica"
HEADER_POINT_SIZE = 8


def point_size(size, minimum=1, maximum=None):
    size = int(round(float(size)))
    size = max(minimum, size)
    if maximum is not None:
        size = min(maximum, size)
    return size


def font(size, bold=False, minimum=1, maximum=None):
    qfont = QtGui.QFont(FONT_FAMILY, point_size(size, minimum=minimum, maximum=maximum))
    qfont.setBold(bold)
    return qfont


def scaled_font(height, ratio, minimum=7, maximum=12, bold=False):
    return font(float(height) * ratio, bold=bold, minimum=minimum, maximum=maximum)


def fit_font(text, width, start_size, minimum=6, maximum=None, bold=False):
    size = point_size(start_size, minimum=minimum, maximum=maximum)
    while size > minimum:
        candidate = font(size, bold=bold)
        if QtGui.QFontMetrics(candidate).horizontalAdvance(text) <= width:
            return candidate
        size -= 1
    return font(minimum, bold=bold)
