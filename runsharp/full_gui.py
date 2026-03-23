import os
from qtpy.QtGui import *
from qtpy.QtCore import *
from qtpy.QtWidgets import *
import threading
from sutils.utils import patch_qt6_mouse_events
patch_qt6_mouse_events()
try:
    # These attributes were removed in Qt6; ignore if not present or deprecated
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
except Exception:
    pass
from sharppy.viz.map import MapWidget
import argparse
import traceback
from sutils.config import Config
from os.path import expanduser
import cProfile
from functools import wraps, partial
import datetime as date

from sutils.progress import progress
from sutils.async_threads import AsyncThreads
from sutils.ver_updates import check_latest
from datasources import data_source
from sharppy.io.arw_decoder import ARWDecoder
from sharppy.io.decoder import getDecoders
import sharppy.sharptab.profile as profile
from sharppy.viz.preferences import PrefDialog
from sharppy.viz.SPCWindow import SPCWindow
from sharppy._version import get_versions
import sys
import glob as glob
import numpy as np
import warnings
import sutils.frozenutils as frozenutils
import logging
import qtpy
import platform

HOME_DIR = os.path.join(os.path.expanduser("~"), ".sharppy")
NUCAPS_times_file = os.path.join(HOME_DIR, "datasources", "nucapsTimes.txt") # JTS
LOG_FILE = os.path.join(HOME_DIR, 'sharppy.log')
if not os.path.isdir(HOME_DIR):
    os.mkdir(HOME_DIR)

if os.path.exists(LOG_FILE):
    log_file_size = os.path.getsize(LOG_FILE)
    MAX_FILE_SIZE = 1024 * 1024
    if log_file_size > MAX_FILE_SIZE:
        # Delete the log file as it's grown too large
        os.remove(LOG_FILE)

HEADER = '\033[95m'
OKBLUE = '\033[94m'
OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'

# Start the logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(pathname)s %(funcName)s Line #: %(lineno)d %(levelname)-8s %(message)s',
                    filename=LOG_FILE,
                    filemode='w')
console = logging.StreamHandler()
# set a format which is simpler for console use
formatter = logging.Formatter(
    '%(asctime)s %(pathname)s %(funcName)s Line #: %(lineno)d %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)

if len(sys.argv) > 1 and '--debug' in sys.argv:
    debug = True
    sys.path.insert(0, os.path.normpath(os.getcwd() + "/.."))
    console.setLevel(logging.DEBUG)
else:
    console.setLevel(logging.CRITICAL)
    debug = False
    np.seterr(all='ignore')
    warnings.simplefilter('ignore')

if frozenutils.isFrozen():
    if not os.path.exists(HOME_DIR):
        os.makedirs(HOME_DIR)
    BINARY_VERSION = True
    outfile = open(os.path.join(HOME_DIR, 'sharppy-out.txt'), 'w')
    console.setLevel(logging.DEBUG)
    sys.stdout = outfile
    sys.stderr = outfile
else:
    BINARY_VERSION = False

__version__ = get_versions()['version']
ver = get_versions()
del get_versions

logging.info('Started logging output for SHARPpy')
logging.info('SHARPpy version: ' + str(__version__))
logging.info('numpy version: ' + str(np.__version__))
logging.info('qtpy version: ' + str(qtpy.__version__))
logging.info("Python version: " + str(platform.python_version()))
logging.info("Qt version: " + str(qtpy.QtCore.__version__))
logging.info("OS version: " + str(platform.platform()))
# from sharppy._version import __version__#, __version_name__

if BINARY_VERSION:
    logging.info("This is a binary version of SHARPpy.")

__version_name__ = 'Andover'
try:
    from netCDF4 import Dataset
    has_nc = True
except ImportError:
    has_nc = False
    logging.info("No netCDF4 Python install detected.")


def versioning_info(include_sharppy=False):
    txt = ""
    if include_sharppy is True:
        txt += "SHARPpy version: " + str(__version__) + '\n'
    txt += "Numpy version: " + str(np.__version__) + '\n'
    txt += "Python version: " + str(platform.python_version()) + '\n'
    txt += "PySide/Qt version: " + str(qtpy.QtCore.__version__)
    return txt

class crasher(object):
    def __init__(self, **kwargs):
        self._exit = kwargs.get('exit', False)

    def __get__(self, obj, cls):
        return partial(self.__call__, obj)

    def __call__(self, func):
        def doCrasher(*args, **kwargs):
            try:
                ret = func(*args, **kwargs)
            except Exception as e:
                ret = None
                msg = "Well, this is embarrassing.\nSHARPpy broke. This is probably due to an issue with one of the data source servers, but if it keeps happening, send the detailed information to the developers."
                data = "SHARPpy v%s %s\n" % (__version__, __version_name__) + \
                       "Crash time: %s\n" % str(date.datetime.now()) + \
                       traceback.format_exc()
                logging.exception(e)
                print("Exception:", e)
                # HERE IS WHERE YOU CAN CATCH A DATAQUALITYEXCEPTION
                if frozenutils.isFrozen():
                    msg1, msg2 = msg.split("\n")

                    msgbox = QMessageBox()
                    msgbox.setText(msg1)
                    msgbox.setInformativeText(msg2)
                    msgbox.setDetailedText(data)
                    msgbox.setIcon(QMessageBox.Icon.Critical)
                    msgbox.exec()
                else:
                    print()
                    print(msg)
                    print()
                    print("Detailed Information:")
                    print(data)

                # Check the flag that indicates if the program should exit when it crashes
                if self._exit:
                    sys.exit(1)
            return ret
        return doCrasher


class Calendar(QCalendarWidget):
    def __init__(self, *args, **kwargs):
        dt_earliest = kwargs.pop('dt_earliest', date.datetime(1946, 1, 1))
        dt_avail = kwargs.pop('dt_avail', date.datetime.now(date.timezone.utc).replace(tzinfo=None).replace(
            minute=0, second=0, microsecond=0))
        self.max_date = dt_avail.date()
        super(Calendar, self).__init__(*args, **kwargs)

        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.SingleLetterDayNames)
        self.setEarliestAvailable(dt_earliest)
        self.setLatestAvailable(dt_avail)

        weekend_color = QColor('#7aa2f7')
        for day in [Qt.DayOfWeek.Sunday, Qt.DayOfWeek.Saturday]:
            txt_fmt = self.weekdayTextFormat(day)
            txt_fmt.setForeground(QBrush(weekend_color))
            self.setWeekdayTextFormat(day, txt_fmt)

    def paintCell(self, painter, rect, date):
        QCalendarWidget.paintCell(self, painter, rect, date)
        if date.toPython() > self.max_date or date.toPython() < self.min_date:
            color = QColor('#808080')
            color.setAlphaF(0.5)
            painter.fillRect(rect, color)

    def setLatestAvailable(self, dt_avail):
        qdate_avail = QDate(dt_avail.year, dt_avail.month, dt_avail.day)
        #self.setMaximumDate(qdate_avail)
        self.max_date = qdate_avail.toPython()
        #if self.selectedDate().toPython() > qdate_avail.toPython():
        ##    self.setSelectedDate(qdate_avail)
        #else:
        self.setSelectedDate(self.selectedDate())

    def setEarliestAvailable(self, dt_earliest):
        qdate_earliest = QDate(dt_earliest.year, dt_earliest.month, dt_earliest.day)
        self.min_date = dt_earliest.date()
        #self.setMinimumDate(qdate_earliest)


class Picker(QWidget):
    date_format = "%Y-%m-%d %HZ"
    run_format = "%d %B %Y / %H%M UTC"

    async_obj = AsyncThreads(2, debug)

    def __init__(self, config, **kwargs):
        """
        Construct the main picker widget: a means for interactively selecting
        which sounding profile(s) to view.
        """
        super(Picker, self).__init__(**kwargs)
        self.data_sources = data_source.loadDataSources()
        self.config = config
        self.skew = None

        # default the sounding location to OUN because obviously I'm biased
        self.loc = None
        # the index of the item in the list that corresponds
        # to the profile selected from the list
        self.prof_idx = []
        # set the default profile type to Observed
        self.model = "Observed"
        # Generate the time list locally — no network call at startup.
        # Just compute the last 100 12-hourly cycles from now.
        _now = date.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        _cur = _now.replace(hour=(_now.hour // 12) * 12)
        self.all_times = sorted([_cur - date.timedelta(hours=12 * i) for i in range(100)])
        self.run = [t for t in self.all_times if t.hour in [0, 12]][-1]

        # Assume connected optimistically; verify in background so the GUI appears immediately.
        self.has_connection = True
        self.strictQC = True

        # JTS - list all overpass times for the selected day
        self.nucaps_daily_times = []

        # Force Mercator projection for unified globe view
        # Clear saved position if switching from a different projection
        if ('map', 'proj') not in self.config or self.config['map', 'proj'] != 'merc':
            for key in ['proj', 'std_lon', 'scale', 'center_x', 'center_y']:
                if ('map', key) in self.config:
                    self.config._cfg.remove_option('map', key)
        self.config['map', 'proj'] = 'merc'

        # initialize the UI
        self.__initUI()

        # Ping connectivity check in background — updates the map banner if offline
        def _ping_check():
            urls = data_source.pingURLs(self.data_sources)
            connected = any(urls.values())
            QMetaObject.invokeMethod(self, "_on_ping_done",
                                     Qt.QueuedConnection,
                                     Q_ARG(bool, connected))

        threading.Thread(target=_ping_check, daemon=True).start()

    def __initUI(self):
        self.layout = QHBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.view = self.create_map_view()
        self.view.hasInternet(self.has_connection)

        # ── LEFT: map + top strip ─────────────────────────────────
        map_container = QWidget()
        mc = QVBoxLayout()
        mc.setSpacing(0)
        mc.setContentsMargins(0, 0, 0, 0)
        map_container.setLayout(mc)

        top_strip = QWidget()
        top_strip.setObjectName("topStrip")
        top_strip.setFixedHeight(46)
        ts = QHBoxLayout()
        ts.setContentsMargins(14, 0, 14, 0)
        ts.setSpacing(10)
        top_strip.setLayout(ts)

        # Source / model selector
        src_label = QLabel("Source")
        src_label.setObjectName("topLabel")
        ts.addWidget(src_label)
        models = sorted(self.data_sources.keys())
        self.model_dropdown = self.dropdown_menu(models)
        self.model_dropdown.setCurrentIndex(models.index(self.model))
        self.model_dropdown.activated.connect(self.get_model)
        self.model_dropdown.setFixedWidth(170)
        ts.addWidget(self.model_dropdown)

        ts.addStretch(1)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search station…")
        self.search_box.setFixedWidth(220)
        self.search_box.returnPressed.connect(self.search_station)
        ts.addWidget(self.search_box)

        mc.addWidget(top_strip)
        mc.addWidget(self.view, 1)
        self.layout.addWidget(map_container, 1)

        # ── RIGHT: contextual side panel ──────────────────────────
        self.side_panel = QWidget()
        self.side_panel.setObjectName("sidePanel")
        self.side_panel.setFixedWidth(310)
        sp = QVBoxLayout()
        sp.setContentsMargins(20, 20, 20, 20)
        sp.setSpacing(0)
        self.side_panel.setLayout(sp)

        # Station header + close button
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        self.stn_name_label = QLabel("")
        self.stn_name_label.setObjectName("stnName")
        self.stn_name_label.setWordWrap(True)
        hdr.addWidget(self.stn_name_label, 1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closePanelBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("Close panel")
        close_btn.clicked.connect(self._close_panel)
        hdr.addWidget(close_btn, 0, Qt.AlignTop)
        sp.addLayout(hdr)

        self.stn_info_label = QLabel("")
        self.stn_info_label.setObjectName("stnInfo")
        sp.addWidget(self.stn_info_label)

        sp.addSpacing(16)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("panelSep")
        sp.addWidget(sep)

        sp.addSpacing(16)

        # Date section
        date_lbl = QLabel("DATE")
        date_lbl.setObjectName("sectionLabel")
        sp.addWidget(date_lbl)
        sp.addSpacing(6)

        date_row = QHBoxLayout()
        date_row.setSpacing(4)
        self.prev_day_btn = QPushButton("◀")
        self.prev_day_btn.setFixedSize(34, 34)
        self.prev_day_btn.setToolTip("Previous day")
        self.prev_day_btn.clicked.connect(self._prev_day)
        qdate = QDate(self.run.year, self.run.month, self.run.day)
        self.date_edit = QDateEdit(qdate)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd d MMM yyyy")
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._on_date_changed)
        self.cal_date = self.date_edit.date()
        self.next_day_btn = QPushButton("▶")
        self.next_day_btn.setFixedSize(34, 34)
        self.next_day_btn.setToolTip("Next day")
        self.next_day_btn.clicked.connect(self._next_day)
        date_row.addWidget(self.prev_day_btn)
        date_row.addWidget(self.date_edit, 1)
        date_row.addWidget(self.next_day_btn)
        sp.addLayout(date_row)

        sp.addSpacing(14)

        # Time section
        time_lbl = QLabel("TIME")
        time_lbl.setObjectName("sectionLabel")
        sp.addWidget(time_lbl)
        sp.addSpacing(6)

        filt_times = [t for t in self.all_times
                      if t.day == self.cal_date.day()
                      and t.year == self.cal_date.year()
                      and t.month == self.cal_date.month()]
        self.run_dropdown = self.dropdown_menu(
            [t.strftime(Picker.run_format) for t in filt_times])
        try:
            self.run_dropdown.setCurrentIndex(filt_times.index(self.run))
        except ValueError:
            pass
        self.run_dropdown.activated.connect(self.get_run)
        sp.addWidget(self.run_dropdown)

        sp.addSpacing(14)

        # Forecast hours section (hidden for observed)
        self.forecast_section = QWidget()
        fs = QVBoxLayout()
        fs.setContentsMargins(0, 0, 0, 0)
        fs.setSpacing(6)
        self.forecast_section.setLayout(fs)
        fcst_lbl = QLabel("FORECAST HOURS")
        fcst_lbl.setObjectName("sectionLabel")
        fs.addWidget(fcst_lbl)
        self.select_flag = False
        self.profile_list = QListWidget()
        self.profile_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.profile_list.setDisabled(True)
        self.profile_list.setMaximumHeight(180)
        self.profile_list.itemSelectionChanged.connect(self._update_generate_btn)
        fs.addWidget(self.profile_list)
        self.all_profs = QPushButton("Select All")
        self.all_profs.setDisabled(True)
        self.all_profs.clicked.connect(self.select_all)
        fs.addWidget(self.all_profs)
        self.forecast_section.setVisible(False)
        sp.addWidget(self.forecast_section)

        sp.addStretch(1)

        # Status hint
        self.status_bar = QLabel("")
        self.status_bar.setObjectName("statusText")
        self.status_bar.setWordWrap(True)
        sp.addWidget(self.status_bar)

        sp.addSpacing(10)

        # Generate button
        self.button = QPushButton("Generate")
        self.button.setObjectName("generateBtn")
        self.button.setFixedHeight(44)
        self.button.clicked.connect(self.complete_name)
        self.button.setDisabled(True)
        sp.addWidget(self.button)

        self.side_panel.setVisible(False)
        self.layout.addWidget(self.side_panel)

        # Hidden legacy widgets still needed by update_list / get_model logic
        self.date_label = QLabel()
        self.date_label.setVisible(False)
        self.run_label = QLabel()

    def _prev_day(self):
        self.date_edit.setDate(self.date_edit.date().addDays(-1))

    def _next_day(self):
        if self.date_edit.date() < QDate.currentDate():
            self.date_edit.setDate(self.date_edit.date().addDays(1))

    def _on_date_changed(self, qdate):
        self.cal_date = qdate
        self.update_from_cal(qdate)

    def _close_panel(self):
        """Close the side panel and deselect the current station."""
        self.side_panel.setVisible(False)
        self.loc = None
        self.disp_name = None
        self.button.setText("Generate")
        self.button.setDisabled(True)
        self.view.clicked_stn = None
        self.view.drawMap()
        self.view.update()

    def _update_generate_btn(self):
        """Update generate button state and text based on current selections."""
        has_station = self.loc and hasattr(self, 'disp_name') and self.disp_name
        has_valid_time = self.run != date.datetime(1700, 1, 1, 0, 0, 0)
        is_model = False
        try:
            is_model = self.data_sources[self.model].getForecastHours() != [0]
        except Exception:
            pass

        # For model data, require at least one forecast hour selected
        has_fcst = True
        if is_model and has_station and has_valid_time:
            has_fcst = len(self.profile_list.selectedItems()) > 0

        can_generate = has_station and has_valid_time and has_fcst

        if has_station and has_valid_time:
            run_str = self.run.strftime("%d %b %H%MZ")
            self.button.setText(f"Generate  {self.disp_name}  ·  {run_str}")
        else:
            self.button.setText("Generate")

        self.button.setEnabled(can_generate and self.has_connection)
        self._update_status_hint()

    def _update_status_hint(self):
        """Show contextual hint text at the bottom of the side panel."""
        if not self.side_panel.isVisible():
            return

        has_valid_time = self.run != date.datetime(1700, 1, 1, 0, 0, 0)
        is_model = False
        try:
            is_model = self.data_sources[self.model].getForecastHours() != [0]
        except Exception:
            pass

        if not has_valid_time:
            self.set_status("No data available for this date.", "#e06c75")
        elif is_model and len(self.profile_list.selectedItems()) == 0:
            self.set_status("Select forecast hours to continue.", "#e5c07b")
        elif self.button.isEnabled():
            self.set_status(f"Ready to generate.", "#98c379")
        else:
            self.set_status("Choose a date and time above.")

    def _update_profiles_visibility(self):
        try:
            is_obs = (self.data_sources[self.model].getForecastHours() == [0])
        except Exception:
            is_obs = True
        self.forecast_section.setVisible(not is_obs)

    @Slot(bool)
    def _on_ping_done(self, connected):
        self.has_connection = connected
        self.view.hasInternet(connected)

    def create_map_view(self):
        """
        Create a clickable map that will be displayed in the GUI.
        Will eventually be re-written to be more general.

        Returns
        -------
        view : QWebView object
        """

        # minimumWidth=800, minimumHeight=500,
        view = MapWidget(
            self.data_sources[self.model], self.run, self.async_obj, cfg=self.config)
        view.clicked.connect(self.map_link)

        return view

    def set_status(self, msg, color="#888888"):
        self.status_bar.setText(msg)
        self.status_bar.setStyleSheet(
            f"QLabel#statusText {{ color: {color}; font-size: 11px; }}")

    def search_station(self):
        """Search for a station by ID, ICAO, IATA, or name and select it on the map."""
        query = self.search_box.text().strip().upper()
        if not query:
            return
        points = getattr(self.view, 'points', [])
        if not points:
            self.set_status("No stations loaded yet.", "#e06c75")
            return

        match = None
        # Exact match first: srcid, icao, iata
        for p in points:
            if (p.get('srcid', '').upper() == query or
                    p.get('icao', '').upper() == query or
                    p.get('iata', '').upper() == query):
                match = p
                break
        # Partial match on icao or name if no exact match
        if match is None:
            for p in points:
                if (query in p.get('icao', '').upper() or
                        query in p.get('name', '').upper()):
                    match = p
                    break

        if match:
            self.view.selectStation(match)
            self.search_box.clear()
            label = match.get('icao', '') or match.get('iata', '') or match.get('srcid', '')
            self.set_status(f"Selected: {label.upper()}", "#98c379")
        else:
            self.set_status(f"Station '{query}' not found.", "#e06c75")

    def dropdown_menu(self, item_list):
        """
        Create and return a dropdown menu containing items in item_list.

        Params
        ------
        item_list : a list of strings for the contents of the dropdown menu

        Returns
        -------
        dropdown : a QtGui.QComboBox object
        """
        logging.debug("Calling full_gui.dropdown_menu")
        # create the dropdown menu
        dropdown = QComboBox()
        # set the text as editable so that it can have centered text
        dropdown.setEditable(True)
        dropdown.lineEdit().setReadOnly(True)
        dropdown.lineEdit().setAlignment(Qt.AlignCenter)

        # add each item in the list to the dropdown
        for item in item_list:
            dropdown.addItem(item)

        return dropdown

    def update_from_cal(self, dt, updated_model=False):
        """
        Update the dropdown list and the forecast times list if a new date
        is selected in the calendar app.
        """

        self.update_run_dropdown(updated_model=updated_model)

        self.view.setDataSource(self.data_sources[self.model], self.run)
        self.update_list()

    def update_list(self):
        """
        Update the list with new forecast times.

        :param list:
        :return:
        """
        logging.debug("Calling full_gui.update_list")
        if self.select_flag:
            self.select_all()
        self.profile_list.clear()
        self.prof_idx = []
        timelist = []

        # If the run is outside the available times.
        if self.run == date.datetime(1700, 1, 1, 0, 0, 0):
            self.profile_list.setDisabled(True)
            self.all_profs.setDisabled(True)
            self.date_label.setDisabled(True)
        else:
            fcst_hours = self.data_sources[self.model].getForecastHours()
            if fcst_hours != [0]:
                self.profile_list.setEnabled(True)
                self.all_profs.setEnabled(True)
                self.date_label.setEnabled(True)
                for fh in fcst_hours:
                    fcst_str = (self.run + date.timedelta(hours=fh)
                                ).strftime(Picker.date_format) + "   (F%03d)" % fh
                    timelist.append(fcst_str)
            else:
                self.profile_list.setDisabled(True)
                self.all_profs.setDisabled(True)
                self.date_label.setDisabled(True)

        # Loop throught the timelist and each string to the list
        for item in timelist:
            self.profile_list.addItem(item)

        self.profile_list.update()
        self.all_profs.setText("Select All")
        self.select_flag = False
        self._update_generate_btn()

    def update_datasource_dropdown(self, selected="Observed"):
        """
        Updates the dropdown menu that contains the available
        data sources
        :return:
        """
        logging.debug("Calling full_gui.update_datasource_dropdown")

        for i in range(self.model_dropdown.count()):
            self.model_dropdown.removeItem(0)

        self.data_sources = data_source.loadDataSources()
        models = sorted(self.data_sources.keys())
        for model in models:
            self.model_dropdown.addItem(model)

        self.model_dropdown.setCurrentIndex(models.index(selected))
        self.get_model(models.index(selected))

    def _set_observed_times(self, times_for_date):
        """Populate the run dropdown with the given list of datetimes."""
        current_run = self.run
        self.run_dropdown.clear()
        if times_for_date:
            for t in times_for_date:
                self.run_dropdown.addItem(t.strftime(Picker.run_format))
            # Restore previous selection if still present, else pick most recent synoptic
            if current_run in times_for_date:
                self.run = current_run
            else:
                try:
                    synoptic_times = [3, 15] if times_for_date[0] < date.datetime(1957, 5, 1) else [0, 12]
                    self.run = [t for t in times_for_date if t.hour in synoptic_times][-1]
                except IndexError:
                    self.run = times_for_date[-1]
            self.run_dropdown.setCurrentIndex(times_for_date.index(self.run))
            self.run_dropdown.setEnabled(True)
        else:
            self.run_dropdown.addItem("- No obs available -")
            self.run_dropdown.setCurrentIndex(0)
            self.run_dropdown.setEnabled(False)
            self.run = date.datetime(1700, 1, 1, 0, 0, 0)
        self.run_dropdown.update()
        self._update_generate_btn()

    def _update_observed_dropdown(self):
        """
        Update the run dropdown for observed soundings.
        Shows 0Z and 12Z — the standard global radiosonde times.
        """
        selected = self.cal_date
        sel_dt = date.datetime(selected.year(), selected.month(), selected.day())
        now = date.datetime.utcnow()

        # Standard synoptic times — show these immediately
        times_for_date = []
        for hour in [0, 12]:
            t = sel_dt.replace(hour=hour)
            if t <= now:
                times_for_date.append(t)

        self._set_observed_times(times_for_date)


    def update_run_dropdown(self, updated_model=False):
        """
        Updates the dropdown menu that contains the model run
        information.
        :return:
        """
        logging.debug("Calling full_gui.update_run_dropdown")

        self.cal_date = self.date_edit.date()

        # Fast path for Observed: no network call needed, just offer 0Z and 12Z
        if self.model == "Observed":
            self._update_observed_dropdown()
            return

        if self.model.startswith("Local"):
            url = self.data_sources[self.model].getURLList(
                outlet="Local")[0].replace("file://", "")

            def getTimes():
                return self.data_sources[self.model].getAvailableTimes(url)
        else:
            def getTimes():
                return self.data_sources[self.model].getAvailableTimes(dt=self.cal_date)

        # Function to update the times.
        def update(times):
            self.run_dropdown.clear()  # Clear all of the items from the dropdown
            times = times[0]
            time_span = self.data_sources[self.model].updateTimeSpan()
            for outlet in time_span:
                if np.asarray(outlet).all() == None:
                    span = True
                else:
                    dt_earliest = outlet[0]
                    dt_avail = outlet[1]
                    span = False
            if span is True and len(times) > 0:
                dt_avail = max(times)
                dt_earliest = min(times)
            self.date_edit.setMaximumDate(QDate(dt_avail.year, dt_avail.month, dt_avail.day))
            self.date_edit.setMinimumDate(QDate(dt_earliest.year, dt_earliest.month, dt_earliest.day))
            self.cal_date = self.date_edit.date()
            self.date_edit.update()

            # Filter out only times for the specified date.
            filtered_times = []
            for i, data_time in enumerate(times):
                if data_time.day == self.cal_date.day() and data_time.year == self.cal_date.year() and data_time.month == self.cal_date.month():
                    self.run_dropdown.addItem(data_time.strftime(Picker.run_format))
                    filtered_times.append(i)

            if len(filtered_times) > 0:
                filtered_times = np.sort(np.asarray(filtered_times))
                times = times[filtered_times.min(): filtered_times.max()+1]
                # Pick the index for which to highlight
                if self.model == "Observed":
                    try:
                        # Try to grab the 0 or 12 UTC data for this day (or 3 or 15 if before 5/1/1957)
                        if self.cal_date.toPython() >= date.datetime(1957,5,1).date():
                            synoptic_times = [0,12]
                        else:
                            synoptic_times = [3,15]
                        self.run = [t for t in times if t.hour in synoptic_times and t.day == self.cal_date.day(
                        ) and t.month == self.cal_date.month() and t.year == self.cal_date.year()][-1]
                    except Exception as e:
                        logging.exception(e)
                        self.run = times[-1]
                else:
                    self.run = times[-1]
            else:
                self.run = date.datetime(1700, 1, 1, 0, 0, 0)
            self.run_dropdown.update()

            if len(filtered_times) > 0:
                # JTS -  Handle how real-time and off-line NUCAPS data is displayed.
                if self.model == "NUCAPS Case Study NOAA-20" \
                    or self.model == "NUCAPS Case Study Suomi-NPP" \
                    or self.model == "NUCAPS Case Study Aqua" \
                    or self.model == "NUCAPS Case Study MetOp-A" \
                    or self.model == "NUCAPS Case Study MetOp-B" \
                    or self.model == "NUCAPS Case Study MetOp-C":
                    self.run_dropdown.clear()
                    self.run_dropdown.addItem(self.tr("- Viewing archived data - "))
                    self.run_dropdown.setCurrentIndex(0)
                    self.run_dropdown.update()
                    self.run_dropdown.setEnabled(False)
                elif self.model == "NUCAPS CONUS NOAA-20" \
                    or self.model == "NUCAPS CONUS Suomi-NPP" \
                    or self.model == "NUCAPS CONUS Aqua" \
                    or self.model == "NUCAPS CONUS MetOp-A" \
                    or self.model == "NUCAPS CONUS MetOp-B" \
                    or self.model == "NUCAPS CONUS MetOp-C" \
                    or self.model == "NUCAPS Caribbean NOAA-20" \
                    or self.model == "NUCAPS Caribbean Suomi-NPP" \
                    or self.model == "NUCAPS Caribbean Aqua" \
                    or self.model == "NUCAPS Caribbean MetOp-A" \
                    or self.model == "NUCAPS Caribbean MetOp-B" \
                    or self.model == "NUCAPS Caribbean MetOp-C" \
                    or self.model == "NUCAPS Alaska NOAA-20" \
                    or self.model == "NUCAPS Alaska Suomi-NPP" \
                    or self.model == "NUCAPS Alaska Aqua" \
                    or self.model == "NUCAPS Alaska MetOp-A" \
                    or self.model == "NUCAPS Alaska MetOp-B" \
                    or self.model == "NUCAPS Alaska MetOp-C":

                    # Load the empty csv for days that have no data and refresh the map.
                    self.data_sources = data_source.loadDataSources()
                    self.run_dropdown.setCurrentIndex(times.index(self.run))
                    self.run_dropdown.update()
                    self.run_dropdown.setEnabled(True)

                    # Re-acquire the list of available times for the newly-selected data source.
                    self.nucaps_daily_times = times
                else:
                    self.run_dropdown.setCurrentIndex(times.index(self.run))
                    self.run_dropdown.update()
                    self.run_dropdown.setEnabled(True)
            elif len(filtered_times) == 0:
                if self.model == "Observed" \
                    or self.model == "NUCAPS Case Study NOAA-20" \
                    or self.model == "NUCAPS Case Study Suomi-NPP" \
                    or self.model == "NUCAPS Case Study Aqua" \
                    or self.model == "NUCAPS Case Study MetOp-A" \
                    or self.model == "NUCAPS Case Study MetOp-B" \
                    or self.model == "NUCAPS Case Study MetOp-C":
                    string = "obs"
                elif self.model == "NUCAPS CONUS NOAA-20" \
                    or self.model == "NUCAPS CONUS Suomi-NPP" \
                    or self.model == "NUCAPS CONUS Aqua" \
                    or self.model == "NUCAPS CONUS MetOp-A" \
                    or self.model == "NUCAPS CONUS MetOp-B" \
                    or self.model == "NUCAPS CONUS MetOp-C" \
                    or self.model == "NUCAPS Caribbean NOAA-20" \
                    or self.model == "NUCAPS Caribbean Suomi-NPP" \
                    or self.model == "NUCAPS Caribbean Aqua" \
                    or self.model == "NUCAPS Caribbean MetOp-A" \
                    or self.model == "NUCAPS Caribbean MetOp-B" \
                    or self.model == "NUCAPS Caribbean MetOp-C" \
                    or self.model == "NUCAPS Alaska NOAA-20" \
                    or self.model == "NUCAPS Alaska Suomi-NPP" \
                    or self.model == "NUCAPS Alaska Aqua" \
                    or self.model == "NUCAPS Alaska MetOp-A" \
                    or self.model == "NUCAPS Alaska MetOp-B" \
                    or self.model == "NUCAPS Alaska MetOp-C":
                    # Load the empty csv for days that have no data and refresh the map.
                    string = "obs"
                    self.data_sources = data_source.loadDataSources()
                else:
                    string = "runs"
                self.run_dropdown.addItem(self.tr("- No " + string + " available - "))
                self.run_dropdown.setCurrentIndex(0)
                self.run_dropdown.update()
                self.run_dropdown.setEnabled(False)

        # Post the getTimes to update.  This will re-write the list of times in the dropdown box that
        # match the date selected in the calendar.
        async_id = self.async_obj.post(getTimes, update)
        self.async_obj.join(async_id)

    def map_link(self, point):
        """
        Handle station selection from the map.
        """
        logging.debug("Calling full_gui.map_link")

        if point is None:
            self.loc = None
            self.disp_name = None
            self.button.setText("Generate")
            self.button.setDisabled(True)
            self.stn_name_label.setText("")
            self.stn_info_label.setText("")
            self.side_panel.setVisible(False)
        elif self.model == "Local WRF-ARW":
            self.loc = point
            self.disp_name = "User Selected"
            self.stn_name_label.setText("User Selected Point")
            self.stn_info_label.setText(f"{point[1]:.3f}°, {point[0]:.3f}°")
            self.side_panel.setVisible(True)
            self.areal_lon, self.areal_y = point
            self._update_generate_btn()
        elif not isinstance(point, dict):
            return
        else:
            self.loc = point
            if point.get('icao', '') != "":
                self.disp_name = point['icao']
            elif point.get('iata', '') != "":
                self.disp_name = point['iata']
            else:
                self.disp_name = point.get('srcid', '???').upper()

            # Update side panel header
            name = point.get('name', self.disp_name)
            if name == '' or name == self.disp_name:
                self.stn_name_label.setText(self.disp_name.upper())
            else:
                self.stn_name_label.setText(name)

            info_parts = []
            if point.get('icao', ''):
                info_parts.append(point['icao'].upper())
            if point.get('state', ''):
                info_parts.append(point['state'])
            elif point.get('country', ''):
                info_parts.append(point['country'])
            try:
                lat, lon = float(point['lat']), float(point['lon'])
                info_parts.append(f"{lat:.2f}°, {lon:.2f}°")
            except (ValueError, KeyError):
                pass
            self.stn_info_label.setText("  ·  ".join(info_parts))

            self.side_panel.setVisible(True)
            self._update_generate_btn()


    @crasher(exit=False)
    def complete_name(self):
        """
        Handles what happens when the user clicks a point on the map
        """
        logging.debug("Calling full_gui.complete_name")
        self.set_status("Loading…", "#e5c07b")
        if self.loc is None:
            return
        else:
            self.prof_idx = []
            selected = self.profile_list.selectedItems()
            for item in selected:
                idx = self.profile_list.indexFromItem(item).row()
                if idx in self.prof_idx:
                    continue
                else:
                    self.prof_idx.append(idx)

            fcst_hours = self.data_sources[self.model].getForecastHours()

            if fcst_hours != [0] and len(self.prof_idx) > 0 or fcst_hours == [0]:
                self.prof_idx.sort()
                n_tries = 0
                while True:
                    try:
                        self.skewApp(ntry=n_tries)
                    except data_source.DataSourceError:
                        # All outlets exhausted with no successful fetch.
                        if self.skew is not None:
                            self.skew.closeIfEmpty()
                        self.set_status("Failed to load data.", "#e06c75")
                        raise IOError("No data found for this station and time.")
                    except (IOError, OSError) as e:
                        # Fetch/network error — try the next outlet.
                        logging.warning("Outlet %d failed: %s", n_tries, e)
                        n_tries += 1
                    else:
                        self.set_status(f"Loaded {self.disp_name}.", "#98c379")
                        break

    def get_model(self, index):
        """
        Get the user's model selection
        """
        logging.debug("Calling full_gui.get_model")

        self.model = self.model_dropdown.currentText()

        self.update_from_cal(None, updated_model=True)
        self.date_edit.setEnabled(True)
        self._update_profiles_visibility()

    def get_run(self, index):
        """
        Get the user's run hour selection for the model
        """
        logging.debug("Calling full_gui.get_run")

        # JTS - The region and satID strings will be used to construct the dynamic path to the csv files in data_source.py.
        if self.model == "NUCAPS CONUS NOAA-20":
            region = 'conus'
            satID = 'j01'
        elif self.model == "NUCAPS CONUS Aqua":
            region = 'conus'
            satID = 'aq0'
        elif self.model == "NUCAPS CONUS MetOp-A":
            region = 'conus'
            satID = 'm02'
        elif self.model == "NUCAPS CONUS MetOp-B":
            region = 'conus'
            satID = 'm01'
        elif self.model == "NUCAPS CONUS MetOp-C":
            region = 'conus'
            satID = 'm03'
        elif self.model == "NUCAPS Caribbean NOAA-20":
            region = 'caribbean'
            satID = 'j01'
        elif self.model == "NUCAPS Alaska NOAA-20":
            region = 'alaska'
            satID = 'j01'

        # Write the data source, region, satellite ID, year, month, day and time info to a temporary text file.
        if self.model.startswith("NUCAPS"):
            nucaps_year = self.cal_date.year()
            nucaps_month = None
            nucaps_day = None

            if self.cal_date.month() < 10:
                nucaps_month = f'0{self.cal_date.month()}'
            else:
                nucaps_month = self.cal_date.month()
            if self.cal_date.day() < 10:
                nucaps_day = f'0{self.cal_date.day()}'
            else:
                nucaps_day = self.cal_date.day()

            nucaps_time = self.run_dropdown.currentText()[-8:-4]
            selected_ds = self.model
            overpass_string = self.run_dropdown.currentText()

            nucapsTimesList = []
            nucapsTimesList.append(f'{selected_ds},{region},{satID},{nucaps_year},{nucaps_month},{nucaps_day},{nucaps_time}')
            file = open(NUCAPS_times_file, "w")
            for line in nucapsTimesList:
                file.write(f'{line}')
            file.close()

            # Hack to get the screen to refresh and display the points.
            # Auto-update the map
            self.update_from_cal(None, updated_model=False)

            # Convert overpass_string to a datetime object.
            self.run = date.datetime.strptime(overpass_string, Picker.run_format)

            # Change the run_dropdown back to the user-selected overpass.
            self.run_dropdown.setCurrentIndex(self.nucaps_daily_times.index(self.run))

            self.view.setCurrentTime(self.run)

            # Cleanup - remove temporary file once data source has been reloaded.
            if os.path.isfile(NUCAPS_times_file):
                os.remove(NUCAPS_times_file)
        else:
            self.run = date.datetime.strptime(self.run_dropdown.currentText(), Picker.run_format)
            self.view.setCurrentTime(self.run)
            self.update_list()
            self._update_generate_btn()

    def get_map(self):
        pass  # replaced by set_projection()

    def save_view(self):
        """
        Save the map projection to the config file
        """
        self.view.saveProjection(self.config)

    def select_all(self):
        logging.debug("Calling full_gui.select_all")
        items = self.profile_list.count()
        if not self.select_flag:
            for i in range(items):
                if self.profile_list.item(i).text() in self.prof_idx:
                    continue
                else:
                    self.profile_list.item(i).setSelected(True)
            self.all_profs.setText("Deselect All")
            self.select_flag = True
        else:
            for i in range(items):
                self.profile_list.item(i).setSelected(False)
            self.all_profs.setText("Select All")
            self.select_flag = False

    def skewApp(self, filename=None, ntry=0):
        logging.debug("Calling full_gui.skewApp")

        """
        Create the SPC style SkewT window, complete with insets
        and magical funtimes.
        :return:
        """
        logging.debug("Calling full_gui.skewApp")

        failure = False

        exc = ""

        # if the profile is an archived file, load the file from
        # the hard disk
        if filename is not None:
            logging.info("Trying to load file from local disk...")

            model = "Archive"
            prof_collection, stn_id = self.loadArchive(filename)
            logging.info(
                "Successfully loaded the profile collection for this file...")
            disp_name = stn_id
            observed = True
            fhours = None

            # Determine if the dataset passed was from a model or is observed
            if len(prof_collection._dates) > 1:
                prof_idx = self.prof_idx
                fhours = ["F%03d" % fh for idx, fh in enumerate(
                    self.data_sources[self.model].getForecastHours()) if idx in prof_idx]
                observed = False
            else:
                fhours = None
                observed = True

            run = prof_collection.getCurrentDate()

        else:
            # otherwise, download with the data thread
            logging.info("Loading a real-time data stream...")
            prof_idx = self.prof_idx
            disp_name = self.disp_name
            run = self.run
            model = self.model
            observed = self.data_sources[model].isObserved()

            if self.data_sources[model].getForecastHours() == [0]:
                prof_idx = [0]

            logging.info("Program is going to load the data...")
            ret = loadData(
                self.data_sources[model], self.loc, run, prof_idx, ntry=ntry)

            # failure variable makes sure the data actually exists online.
            if isinstance(ret[0], Exception):
                exc = ret[0]
                failure = True
                logging.info(
                    "There was a problem with loadData() in obtaining the data from the Internet.")
            else:
                logging.info("Data was found and successfully decoded!")
                prof_collection = ret[0]

            fhours = ["F%03d" % fh for idx, fh in enumerate(self.data_sources[self.model].getForecastHours()) if
                      idx in prof_idx]

        # If the observed or model profile (not Archive) successfully loaded)
        if not failure:
            prof_collection.setMeta('model', model)
            prof_collection.setMeta('run', run)
            prof_collection.setMeta('loc', disp_name)
            prof_collection.setMeta('fhour', fhours)
            prof_collection.setMeta('observed', observed)

            if not prof_collection.getMeta('observed'):
                # If it's not an observed profile, then generate profile objects in background.
                prof_collection.setAsync(Picker.async_obj)

            if self.skew is None:
                logging.debug("Constructing SPCWindow")
                # If the SPCWindow isn't shown, set it up.
                self.skew = SPCWindow(parent=self.parent(), cfg=self.config)
                self.parent().config_changed.connect(self.skew.centralWidget().updateConfig)
                self.skew.closed.connect(self.skewAppClosed)
                self.skew.show()

            logging.debug("Focusing on the SkewApp")
            self.focusSkewApp()
            logging.debug("Adding the profile collection to SPCWindow")
            self.skew.addProfileCollection(prof_collection, check_integrity=self.strictQC)
        else:
            print("There was an exception:", exc)

            raise exc

    def skewAppClosed(self):
        """
        Handles the user closing the SPC window.
        """
        self.skew = None

    def focusSkewApp(self):
        if self.skew is not None:
            self.skew.activateWindow()
            self.skew.setFocus()
            self.skew.raise_()

    def keyPressEvent(self, e):
        if e.key() == 61 or e.key() == 45:
            self.view.keyPressEvent(e)

    def loadArchive(self, filename):
        """
        Get the archive sounding based on the user's selections.
        Also reads it using the Decoders and gets both the stationID and the profile objects
        for that archive sounding.  Tries a variety of decoders available to the program.
        """
        logging.debug(
            "Looping over all decoders to find which one to use to decode User Selected file.")
        for decname, deccls in getDecoders().items():
            try:
                dec = deccls(filename)
                break
            except Exception as e:
                logging.exception(e)
                dec = None
                continue

        if dec is None:
            raise IOError(
                "Could not figure out the format of '%s'!" % filename)
        # Returns the set of profiles from the file that are from the "Profile" class.
        logging.debug('Get the profiles from the decoded file.')
        profs = dec.getProfiles()
        stn_id = dec.getStnId()
        return profs, stn_id

    def hasConnection(self):
        return self.has_connection

    def setStrictQC(self, val):
        self.strictQC = val

@progress(Picker.async_obj)
def loadData(data_source, loc, run, indexes, ntry=0, __text__=None, __prog__=None):
    """
    Loads the data from a remote source. Has hooks for progress bars.
    """
    if __text__ is not None:
        __text__.emit("Decoding File")

    if data_source.getName() == "Local WRF-ARW":
        url = data_source.getURLList(outlet="Local")[0].replace("file://", "")
        decoder = ARWDecoder
        dec = decoder((url, loc[0], loc[1]))
    else:
        decoder, url = data_source.getDecoderAndURL(loc, run, outlet_num=ntry)
        logging.info("Using decoder: " + str(decoder))
        logging.info("Data URL: " + url)
        dec = decoder(url)

    if __text__ is not None:
        __text__.emit("Creating Profiles")

    profs = dec.getProfiles(indexes=indexes)
    return profs


class Main(QMainWindow):
    config_changed = Signal(Config)

    HOME_DIR = os.path.join(os.path.expanduser("~"), ".sharppy")
    cfg_file_name = os.path.join(HOME_DIR, 'sharppy.ini')

    def __init__(self):
        """
        Initializes the window and reads in the configuration from the file.
        """
        super(Main, self).__init__()

        # All of these variables get set/reset by the various menus in the GUI
#       self.config = ConfigParser.RawConfigParser()
#       self.config.read(Main.cfg_file_name)
#       if not self.config.has_section('paths'):
#           self.config.add_section('paths')
#           self.config.set('paths', 'load_txt', expanduser('~'))
        self.config = Config(Main.cfg_file_name)
        paths_init = {('paths', 'load_txt'): expanduser("~")}
        self.config.initialize(paths_init)

        PrefDialog.initConfig(self.config)

        self.__initUI()

    def closeEvent(self, event):
        Picker.async_obj.clearQueue()
        event.accept()

    def __initUI(self):
        """
        Puts the user inteface together
        """
        self.picker = Picker(self.config, parent=self)
        self.setCentralWidget(self.picker)
        self.createMenuBar()

        # set the window title
        window_title = 'SHARPpy Sounding Picker'
        self.setWindowTitle(window_title)

        self.show()
        self.raise_()
        #import time
        #time.sleep(3)
        #self.grab().save('./screenshot.png', 'png')

    def createMenuBar(self):
        bar = self.menuBar()
        filemenu = bar.addMenu("File")

        opendata = QAction("Open", self, shortcut=QKeySequence("Ctrl+O"))
        opendata.triggered.connect(self.openFile)
        filemenu.addAction(opendata)

        save_view = QAction("Save Map View", self)
        save_view.triggered.connect(self.picker.save_view)
        filemenu.addAction(save_view)

        filemenu.addSeparator()

        pref = QAction("Preferences", self)
        pref.setMenuRole(QAction.MenuRole.NoRole)
        filemenu.addAction(pref)
        pref.triggered.connect(self.preferencesbox)

        filemenu.addSeparator()

        exit = QAction("Exit", self, shortcut=QKeySequence("Ctrl+Q"))
        exit.triggered.connect(self.exitApp)
        filemenu.addAction(exit)

        helpmenu = bar.addMenu("Help")
        about = QAction("About", self)
        about.triggered.connect(self.aboutbox)
        helpmenu.addAction(about)

    def exitApp(self):
        self.close()

    @crasher(exit=False)
    def openFile(self):
        """
        Opens a file on the local disk.
        """
        path = self.config['paths', 'load_txt']

        link, _ = QFileDialog.getOpenFileNames(self, 'Open file', path)

        if len(link) == 0 or link[0] == '':
            return

        path = os.path.dirname(link[0])
        self.config['paths', 'load_txt'] = path

        # Loop through all of the files selected and load them into the SPCWindow
        if link[0].endswith("nc") and has_nc:
            ncfile = Dataset(link[0])

            xlon1 = ncfile.variables["XLONG"][0][:, 0]
            xlat1 = ncfile.variables["XLAT"][0][:, 0]

            xlon2 = ncfile.variables["XLONG"][0][:, -1]
            xlat2 = ncfile.variables["XLAT"][0][:, -1]

            xlon3 = ncfile.variables["XLONG"][0][0, :]
            xlat3 = ncfile.variables["XLAT"][0][0, :]

            xlon4 = ncfile.variables["XLONG"][0][-1, :]
            xlat4 = ncfile.variables["XLAT"][0][-1, :]

            delta = ncfile.variables["XTIME"][1] / 60.
            maxt = ncfile.variables["XTIME"][-1] / 60.

            # write the CSV file
            csvfile = open(HOME_DIR + "/datasources/wrf-arw.csv", 'w')
            csvfile.write(
                "icao,iata,synop,name,state,country,lat,lon,elev,priority,srcid\n")

            for idx, val in np.ndenumerate(xlon1):
                lat = xlat1[idx]
                lon = xlon1[idx]
                csvfile.write(",,,,,," + str(lat) + "," + str(lon) +
                              ",0,,LAT" + str(lat) + "LON" + str(lon) + "\n")
            for idx, val in np.ndenumerate(xlon2):
                lat = xlat2[idx]
                lon = xlon2[idx]
                csvfile.write(",,,,,," + str(lat) + "," + str(lon) +
                              ",0,,LAT" + str(lat) + "LON" + str(lon) + "\n")
            for idx, val in np.ndenumerate(xlon3):
                lat = xlat3[idx]
                lon = xlon3[idx]
                csvfile.write(",,,,,," + str(lat) + "," + str(lon) +
                              ",0,,LAT" + str(lat) + "LON" + str(lon) + "\n")
            for idx, val in np.ndenumerate(xlon4):
                lat = xlat4[idx]
                lon = xlon4[idx]
                csvfile.write(",,,,,," + str(lat) + "," + str(lon) +
                              ",0,,LAT" + str(lat) + "LON" + str(lon) + "\n")
            csvfile.close()

            # write the xml file
            xmlfile = open(HOME_DIR + "/datasources/wrf-arw.xml", 'w')
            xmlfile.write(
                '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n')
            xmlfile.write('<sourcelist>\n')
            xmlfile.write(
                '    <datasource name="Local WRF-ARW" ensemble="false" observed="false">\n')
            xmlfile.write('        <outlet name="Local" url="file://' +
                          link[0] + '" format="wrf-arw">\n')
            xmlfile.write('            <time range="' + str(int(maxt)) + '" delta="' +
                          str(int(delta)) + '" offset="0" delay="0" cycle="24" archive="1"/>\n')
            xmlfile.write('            <points csv="wrf-arw.csv" />\n')
            xmlfile.write('        </outlet>\n')
            xmlfile.write('    </datasource>\n')
            xmlfile.write('</sourcelist>\n')
            xmlfile.close()

            self.picker.update_datasource_dropdown(selected="Local WRF-ARW")
        else:
            for l in link:
                self.picker.skewApp(filename=l)

    def aboutbox(self):
        """
        Creates and shows the "about" box.
        """
        cur_year = date.datetime.now(date.timezone.utc).replace(tzinfo=None).year
        msgBox = QMessageBox()
        documentationButton = msgBox.addButton(self.tr("Online Docs"), QMessageBox.ButtonRole.ActionRole)
        bugButton = msgBox.addButton(self.tr("Report Bug"), QMessageBox.ButtonRole.ActionRole)
        githubButton = msgBox.addButton(self.tr("Github"), QMessageBox.ButtonRole.ActionRole)
        msgBox.addButton(QMessageBox.StandardButton.Close)
#        closeButton = msgBox.addButton(self.tr("Close"), QMessageBox.ButtonRole.RejectRole)
        msgBox.setDefaultButton(QMessageBox.StandardButton.Close)
        txt = "SHARPpy v%s %s\n\n" % (__version__, __version_name__)
        txt += "Sounding and Hodograph Analysis and Research Program for Python\n\n"
        txt += "(C) 2014-%d by Patrick Marsh, John Hart, Kelton Halbert, Greg Blumberg, and Tim Supinie." % cur_year
        desc = "\n\nSHARPpy is a collection of open source sounding and hodograph analysis routines, a sounding " + \
               "plotting package, and an interactive application " + \
               "for analyzing real-time soundings all written in " + \
               "Python. It was developed to provide the " + \
               "atmospheric science community a free and " + \
               "consistent source of routines for analyzing sounding data. SHARPpy is constantly updated and " + \
               "vetted by professional meteorologists and " + \
               "climatologists within the scientific community to " + \
               "help maintain a standard source of sounding routines.\n\n"
        txt += desc
        txt += versioning_info()
        #txt += "PySide version: " + str(PySide.__version__) + '\n'
        #txt += "Numpy version: " + str(np.__version__) + '\n'
        #txt += "Python version: " + str(platform.python_version()) + '\n'
        #txt += "Qt version: " + str(PySide.QtCore.__version__)
        txt += "\n\nContribute: https://github.com/sharppy/SHARPpy/"
        msgBox.setText(txt)
        msgBox.exec()

        if msgBox.clickedButton() == documentationButton:
            QDesktopServices.openUrl(QUrl('http://sharppy.github.io/SHARPpy/'))
        elif msgBox.clickedButton() == githubButton:
            QDesktopServices.openUrl(QUrl('https://github.com/sharppy/SHARPpy'))
        elif msgBox.clickedButton() == bugButton:
            QDesktopServices.openUrl(QUrl('https://github.com/sharppy/SHARPpy/issues'))

    def preferencesbox(self):
        pref_dialog = PrefDialog(self.config, parent=self)
        pref_dialog.exec()
        self.config_changed.emit(self.config)

    def keyPressEvent(self, e):
        """
        Handles key press events sent to the picker window.
        """
        if e.matches(QKeySequence.Open):
            self.openFile()

        if e.matches(QKeySequence.Quit):
            self.exitApp()

        if e.key() == Qt.Key_W:
            self.picker.focusSkewApp()

    def closeEvent(self, e):
        """
        Handles close events (gets called when the window closes).
        """
        # JTS - Cleanup; Remove nucapsTimes.txt when main GUI closes.
        if os.path.isfile(NUCAPS_times_file):
            os.remove(NUCAPS_times_file)

        self.config.toFile()

def newerRelease(latest):
    #msgBox = QMessageBox()
    txt = "A newer version of SHARPpy (" + latest[1] + ") was found.\n\n"
    txt += "Do you want to launch a web browser to download the new version from Github?  "
    txt += "(if you downloaded from pip or conda you may want to use those commands instead.)"
    ret_code = QMessageBox.information(None, "New SHARPpy Version!", txt, QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)
    if ret_code == QMessageBox.StandardButton.Yes:
        QDesktopServices.openUrl(QUrl(latest[2]))

@crasher(exit=True)
def createWindow(file_names, collect=False, close=True, output='./', strictQC=False):
    main_win = Main()
    for fname in file_names:
        txt = OKGREEN + "Creating image for '%s' ..." + ENDC
        print(txt % fname)
        main_win.picker.setStrictQC(strictQC)
        main_win.picker.skewApp(filename=fname)
        if not collect:
            fpath, fbase = os.path.split(fname)

            if '.' in fbase:
                img_base = ".".join(fbase.split(".")[:-1] + ['png'])
            else:
                img_base = fbase + '.png'

            img_name = os.path.join(fpath, img_base)
            main_win.picker.skew.spc_widget.pixmapToFile(output + img_name)
            if fname != file_names[-1] or close:
                main_win.picker.skew.close()

    if collect:
        main_win.picker.skew.spc_widget.toggleCollectObserved()
        img_name = collect[0]
        main_win.picker.skew.spc_widget.pixmapToFile(output + img_name)
        if close:
            main_win.picker.skew.close()

    return main_win

@crasher(exit=False)
def search_and_plotDB(model, station, datetime, close=True, output='./'):
    main_win = Main()
    main_win.picker.prof_idx = [0]
    main_win.picker.run = datetime
    main_win.picker.model = model
    main_win.picker.loc = main_win.picker.data_sources[model].getPoint(station)
    main_win.picker.disp_name = main_win.picker.loc['icao']
    try:
        main_win.picker.skewApp()
    except data_source.DataSourceError as e:
        logging.exception(e)
        print(FAIL + "Couldn't find data for the requested time and location." + ENDC)
        return main_win

    string = OKGREEN + "Creating image for station %s using data source %s at time %s ..." + ENDC
    print( string % (station, model, datetime.strftime('%Y%m%d/%H%M')))
    main_win.picker.skew.spc_widget.pixmapToFile(output + datetime.strftime('%Y%m%d.%H%M_' + model + '.png'))
    if close:
        main_win.picker.skew.close()
    return main_win

def test(fn):
    # Run the binary and output a test profile
    if QApplication.instance() is None:
        app = QApplication([])
    else:
        app = QApplication.instance()
    win = createWindow(fn, strictQC=False)
    win.close()

def parseArgs():
    desc = """This binary launches the SHARPpy Picker and GUI from the command line.  When
           run from the command line without arguments, this binary simply launches the Picker
           and loads in the various datasets within the user's ~/.sharppy directory.  When the
           --debug flag is set, the GUI is run in debug mode.

           When a set of files are passed as a command line argument, the program will
           generate images of the SHARPpy GUI for each sounding.  Soundings can be overlaid
           on top of one another if the collect flag is set.  In addition, data from the
           datasources can be plotted using the datasource, station, and datetime arguments."""
    data_sources = [key for key in data_source.loadDataSources().keys()]
    ep = "Available Datasources: " + ', '.join(data_sources)
    ap = argparse.ArgumentParser(description=desc, epilog=ep)

    ap.add_argument('file_names', nargs='*',
                    help='a list of files to read and plot')
    ap.add_argument('--debug', dest='debug', action='store_true',
                    help='turns on debug mode for the GUI')
    ap.add_argument('--version', dest='version', action='store_true',
                    help="print out versioning information")
    ap.add_argument('--collect', dest='collect', action='store_true',
                    help="overlay profiles from filename on top of one another in GUI image")
    #ap.add_argument('--noclose', dest='close', action='store_false',
    #                help="do not close the GUI after viewing the image")
    group = ap.add_argument_group("datasource access arguments")

    group.add_argument('--datasource', dest='ds', type=str,
                    help="the name of the datasource to search")
    group.add_argument('--station', dest='stn', type=str,
                    help="the name of the station to plot (ICAO, IATA)")
    group.add_argument('--datetime', dest='dt', type=str,
                    help="the date/time of the data to plot (YYYYMMDD/HH)")
    ap.add_argument('--output', dest='output', type=str,
                    help="the output directory to store the images", default='./')
    args = ap.parse_args()

    # Print out versioning information and quit
    if args.version is True:
        ap.exit(0, versioning_info(True) + '\n')

    # Catch invalid data source
    if args.ds is not None and args.ds not in data_sources:
        txt = FAIL + "Invalid data source passed to the program.  Exiting." + ENDC
        ap.error(txt)

    # Catch invalid datetime format
    if args.dt is not None:
        try:
            date.datetime.strptime(args.dt , '%Y%m%d/%H')
        except:
            txt = FAIL + "Invalid datetime passed to the program. Exiting." + ENDC
            ap.error(txt)

    return args

def main():
    args = parseArgs()

    # Create an application
    #app = QApplication([])
    #app.setAttribute(Qt.AA_EnableHighDpiScaling)
    #app.setAttribute(Qt.AA_UseHighDpiPixmaps)
#
    #app.setStyle("fusion")
    if QApplication.instance() is None:
        app = QApplication([])
    else:
        app = QApplication.instance()

    app.setStyle("Fusion")
    app.setStyleSheet("""
        * {
            font-family: -apple-system, "Segoe UI", "Helvetica Neue", sans-serif;
            font-size: 13px;
        }
        QWidget {
            background-color: #0a0a0a;
            color: #c8c8c8;
        }
        QMainWindow, QDialog {
            background-color: #0a0a0a;
        }

        /* ── Top strip ───────────────────────── */
        QWidget#topStrip {
            background-color: #101010;
            border-bottom: 1px solid #1a1a1a;
        }
        QLabel#topLabel {
            color: #505050;
            font-size: 11px;
            font-weight: 600;
        }

        /* ── Side panel ──────────────────────── */
        QWidget#sidePanel {
            background-color: #101010;
            border-left: 1px solid #1a1a1a;
        }
        QLabel#stnName {
            color: #f0f0f0;
            font-size: 18px;
            font-weight: 700;
        }
        QLabel#stnInfo {
            color: #606060;
            font-size: 11px;
            font-weight: 500;
        }
        QLabel#sectionLabel {
            color: #484848;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.5px;
        }
        QFrame#panelSep {
            color: #1a1a1a;
            max-height: 1px;
        }
        QLabel#statusText {
            color: #505050;
            font-size: 11px;
        }
        QPushButton#closePanelBtn {
            background: transparent;
            border: none;
            color: #404040;
            font-size: 14px;
            font-weight: bold;
            border-radius: 14px;
        }
        QPushButton#closePanelBtn:hover {
            color: #e0e0e0;
            background-color: #1e1e1e;
        }

        /* ── Buttons ─────────────────────────── */
        QPushButton {
            background-color: #161616;
            color: #b0b0b0;
            border: 1px solid #222222;
            border-radius: 8px;
            padding: 6px 14px;
            min-height: 24px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #1c1c1c;
            border-color: #4a90d9;
            color: #d8d8d8;
        }
        QPushButton:pressed {
            background-color: #111111;
        }
        QPushButton:disabled {
            background-color: #0e0e0e;
            color: #2a2a2a;
            border-color: #161616;
        }
        QPushButton#generateBtn {
            background-color: #2563eb;
            color: #ffffff;
            border: none;
            border-radius: 10px;
            font-weight: 700;
            font-size: 13px;
            min-height: 44px;
            padding: 0 24px;
            letter-spacing: 0.3px;
        }
        QPushButton#generateBtn:hover {
            background-color: #3b82f6;
        }
        QPushButton#generateBtn:pressed {
            background-color: #1d4ed8;
        }
        QPushButton#generateBtn:disabled {
            background-color: #111827;
            color: #374151;
        }

        /* ── Dropdowns ───────────────────────── */
        QComboBox {
            background-color: #141414;
            color: #c8c8c8;
            border: 1px solid #222222;
            border-radius: 8px;
            padding: 6px 12px;
            min-height: 26px;
        }
        QComboBox:hover {
            border-color: #4a90d9;
        }
        QComboBox:focus {
            border-color: #4a90d9;
        }
        QComboBox::drop-down {
            border: none;
            width: 26px;
        }
        QComboBox::down-arrow {
            width: 0; height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid #555555;
        }
        QComboBox::down-arrow:disabled { border-top-color: #222; }
        QComboBox QAbstractItemView {
            background-color: #141414;
            color: #c8c8c8;
            border: 1px solid #222222;
            selection-background-color: #1e3a5f;
            outline: none;
            padding: 2px;
        }

        /* ── Text inputs ─────────────────────── */
        QLineEdit {
            background-color: #141414;
            color: #c8c8c8;
            border: 1px solid #222222;
            border-radius: 8px;
            padding: 6px 12px;
            min-height: 26px;
        }
        QLineEdit:focus {
            border-color: #4a90d9;
        }
        QLineEdit::placeholder {
            color: #3a3a3a;
        }
        QDateEdit {
            background-color: #141414;
            color: #c8c8c8;
            border: 1px solid #222222;
            border-radius: 8px;
            padding: 6px 12px;
            min-height: 26px;
        }
        QDateEdit:hover { border-color: #4a90d9; }
        QDateEdit::drop-down { border: none; width: 24px; }
        QDateEdit::down-arrow {
            width: 0; height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid #555555;
        }

        /* ── Profile list ────────────────────── */
        QListWidget {
            background-color: #0e0e0e;
            color: #b0b0b0;
            border: 1px solid #1e1e1e;
            border-radius: 8px;
            padding: 2px;
        }
        QListWidget::item {
            padding: 5px 10px;
            border-radius: 4px;
            margin: 1px 2px;
        }
        QListWidget::item:selected {
            background-color: #1e3a5f;
            color: #ffffff;
        }
        QListWidget::item:hover:!selected {
            background-color: #161616;
        }

        /* ── Menu bar ────────────────────────── */
        QMenuBar {
            background-color: #0a0a0a;
            color: #909090;
            border-bottom: 1px solid #161616;
            padding: 2px 0;
            font-size: 12px;
        }
        QMenuBar::item { padding: 4px 10px; background: transparent; }
        QMenuBar::item:selected { background-color: #1a1a1a; border-radius: 4px; }
        QMenu {
            background-color: #141414;
            color: #c8c8c8;
            border: 1px solid #222222;
            border-radius: 8px;
            padding: 4px 0;
        }
        QMenu::item { padding: 6px 24px 6px 14px; border-radius: 4px; margin: 1px 4px; }
        QMenu::item:selected { background-color: #1e3a5f; }
        QMenu::separator { height: 1px; background: #1e1e1e; margin: 4px 8px; }

        /* ── Scrollbars ──────────────────────── */
        QScrollBar:vertical {
            background-color: transparent; width: 6px; margin: 0;
        }
        QScrollBar::handle:vertical {
            background-color: #252525; border-radius: 3px; min-height: 24px;
        }
        QScrollBar::handle:vertical:hover { background-color: #4a90d9; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal { background-color: transparent; height: 6px; }
        QScrollBar::handle:horizontal { background-color: #252525; border-radius: 3px; }

        /* ── Dialogs / misc ──────────────────── */
        QProgressDialog, QMessageBox { background-color: #141414; }
        QLabel { color: #c8c8c8; background-color: transparent; }
        QFrame { background-color: transparent; }

        /* ── Calendar popup ──────────────────── */
        QCalendarWidget QWidget { background-color: #141414; color: #c8c8c8; }
        QCalendarWidget QToolButton {
            background-color: transparent; color: #c8c8c8;
            border: none; border-radius: 4px; padding: 4px 10px;
        }
        QCalendarWidget QToolButton:hover { background-color: #1e1e1e; }
        QCalendarWidget QToolButton::menu-indicator { image: none; }
        QCalendarWidget QAbstractItemView:enabled {
            background-color: #0e0e0e; color: #c8c8c8;
            selection-background-color: #1e3a5f; selection-color: #ffffff;
        }
        QCalendarWidget QAbstractItemView:disabled { color: #2a2a2a; }
        QCalendarWidget #qt_calendar_navigationbar {
            background-color: #141414; border-bottom: 1px solid #1a1a1a; padding: 4px;
        }
    """)

    #win = createWindow(args.file_names, collect=args.collect, close=False)
    # Check to see if there's a newer version of SHARPpy on Github Releases
#     latest = check_latest()

#     if latest[0] is False:
#         logging.info("A newer release of SHARPpy was found on Github Releases.")
#     else:
#         logging.info("This is the most recent version of SHARPpy.")

    # Alert the user that there's a newer version on Github (and by extension through CI also on pip and conda)
    # if latest[0] is False:
    #     newerRelease(latest)

    if args.dt is not None and args.ds is not None and args.stn is not None:
        dt = date.datetime.strptime(args.dt, "%Y%m%d/%H")
        win = search_and_plotDB(args.ds, args.stn, dt, args.output)
        win.close()
    elif args.file_names != []:
        win = createWindow(args.file_names, collect=args.collect, close=True, output=args.output)
        win.close()
    else:
        main_win = Main()
        #app.exec()
        sys.exit(app.exec())

if __name__ == '__main__':
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    main()