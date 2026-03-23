
def total_seconds(td):
    return td.days * 3600 * 24 + td.seconds + td.microseconds * 1e-6

def patch_qt6_mouse_events():
    """
    In Qt6 (PySide6), QMouseEvent.pos(), .x(), .y() were removed.
    This patches them back in for compatibility with code written for Qt5.
    Safe to call on Qt5 — it does nothing if the methods already exist.
    """
    try:
        from qtpy.QtGui import QMouseEvent
        if not hasattr(QMouseEvent, 'x'):
            QMouseEvent.x = lambda self: int(self.position().x())
            QMouseEvent.y = lambda self: int(self.position().y())
        if not hasattr(QMouseEvent, 'pos'):
            QMouseEvent.pos = lambda self: self.position().toPoint()
    except ImportError:
        pass
