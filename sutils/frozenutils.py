import sys, os
import platform

import multiprocessing

_env_frozen = 'frozen'
_env_frozen_path = '_MEIPASS'
_env_mp_frozen_path = _env_frozen_path + '2'

def isFrozen():
    return getattr(sys, _env_frozen, False)

def frozenPath():
    return getattr(sys, _env_frozen_path, None)

def freezeSupport():
    if platform.system() == "Windows" and isFrozen():
        multiprocessing.freeze_support()

if isFrozen():
    # The custom _Popen is only needed when running as a PyInstaller frozen bundle
    # to pass the _MEIPASS path to child processes.
    if platform.system() == "Windows":
        import multiprocessing.popen_spawn_win32 as forking
    else:
        import multiprocessing.popen_fork as forking

    class _Popen(forking.Popen):
        def __init__(self, *args, **kw):
            os.putenv(_env_mp_frozen_path, frozenPath() + os.sep)
            try:
                super(_Popen, self).__init__(*args, **kw)
            finally:
                if hasattr(sys, 'frozen'):
                    if hasattr(os, 'unsetenv'):
                        os.unsetenv(_env_mp_frozen_path)
                    else:
                        os.putenv(_env_mp_frozen_path, '')

    class Process(multiprocessing.Process):
        _Popen = _Popen
else:
    # Not frozen — use standard multiprocessing with the platform default start method.
    # On macOS with Python 3.8+, the default is 'spawn', which avoids fork-after-Qt deadlocks.
    Process = multiprocessing.Process

Queue = multiprocessing.Queue
