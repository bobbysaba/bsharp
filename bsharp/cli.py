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

    # Let Qt finish all pending paint events before grabbing.
    def grab_and_exit():
        app.processEvents()
        widget.pixmapToFile(output)
        print(f"Saved: {output}")
        app.quit()

    QTimer.singleShot(500, grab_and_exit)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
