#!/usr/bin/env python
"""
bsharp — Render a sounding figure from an SPC-format file.

Usage:
    bsharp <input_file> [-o <output_file>]

The input file must be in SPC format (%TITLE% / %RAW% / %END%).
"""

import argparse
import sys
import os
import warnings

# Prefer PySide6 — must be set before any qtpy import
os.environ.setdefault('QT_API', 'pyside6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_LOGGING_RULES', 'qt.qpa.*=false')
warnings.filterwarnings("ignore")

from bsharp.utils import patch_qt6_mouse_events
patch_qt6_mouse_events()

from qtpy.QtWidgets import QApplication
from qtpy.QtCore import QTimer

from bsharp.config import Config
from bsharp.viz.SPCWindow import SPCWidget
from bsharp.viz.preferences import PrefDialog
from bsharp.io.spc_decoder import SPCDecoder

HOME_DIR = os.path.join(os.path.expanduser("~"), ".bsharp")
CFG_FILE = os.path.join(HOME_DIR, "bsharp.cfg")


def main():
    parser = argparse.ArgumentParser(
        description='Render a sounding figure from an SPC-format file.'
    )
    parser.add_argument('input_file', help='Path to SPC-format sounding file')
    parser.add_argument(
        '-o', '--output', default=None,
        help='Output image path (default: <YYYYMMDD_HHMM>_<station>.png)',
    )
    parser.add_argument(
        '--credit', default=None, metavar='NAME',
        help='Name to include in the "Created" annotation (e.g. "Bobby Saba")',
    )
    parser.add_argument(
        '--prelim', action='store_true',
        help='Add "PRELIM. DATA NOAA/OAR/NSSL" annotation to the image',
    )
    args = parser.parse_args()

    os.makedirs(HOME_DIR, exist_ok=True)
    app = QApplication(sys.argv)

    # Load config, filling in any missing keys with defaults.
    config = Config(CFG_FILE)
    PrefDialog.initConfig(config)

    # Build the SPCWidget standalone — no picker parent needed.
    widget = SPCWidget(cfg=config)
    widget.setGeometry(0, 0, 1180, 800)
    widget.show()

    # Load the sounding.
    dec = SPCDecoder(args.input_file)
    prof_col = dec.getProfiles()
    stn_id = dec.getStnId()
    date = prof_col.getCurrentDate()

    # The viz layer expects 'run' and 'model' metadata that SPCDecoder doesn't set.
    prof_col.setMeta('run', prof_col.getMeta('base_time'))
    prof_col.setMeta('model', 'Observed')

    output = args.output if args.output else (
        date.strftime('%Y%m%d_%H%M') + '_' + stn_id + '.png'
    )

    widget.addProfileCollection(prof_col, stn_id)

    # Build optional annotation dict — only populated when at least one flag is used.
    annotations = None
    if args.credit or args.prelim:
        import datetime as _dt
        from datetime import timezone as _tz
        import numpy.ma as _ma

        annotations = {}

        # Location label: station ID + lat/lon if available in the profile
        lat = prof_col.getMeta('latitude')
        lon = prof_col.getMeta('longitude')
        lat = None if _ma.is_masked(lat) else lat
        lon = None if _ma.is_masked(lon) else lon
        if lat is not None and lon is not None:
            annotations['location'] = f"{stn_id} ({lat:.3f}, {lon:.3f})"
        else:
            annotations['location'] = stn_id

        # Bottom-left: created timestamp + optional credit name
        utcnow = _dt.datetime.now(_tz.utc).strftime('%d %b %Y %H:%M:%S')
        credit_str = f'   ({args.credit})' if args.credit else ''
        annotations['bottom_left'] = f'Created: {utcnow} UTC{credit_str}'

        # Bottom-right: prelim text
        if args.prelim:
            annotations['bottom_right'] = 'PRELIM. DATA NOAA/OAR/NSSL'

    # Let Qt finish all pending paint events before grabbing.
    def grab_and_exit():
        app.processEvents()
        widget.pixmapToFile(output, annotations=annotations)
        print(f"Saved: {output}")
        app.quit()

    QTimer.singleShot(500, grab_and_exit)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
