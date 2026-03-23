
import numpy as np

import sharppy.sharptab.profile as profile

from urllib.request import urlopen
from urllib.error import HTTPError
import certifi
import ssl
import time
from datetime import datetime
import glob
import os
import importlib.util
import logging

class abstract(object):
    def __init__(self, func):
        self._func = func

    def __call__(self, *args, **kwargs):
        raise NotImplementedError("Function or method '%s' is abstract.  Override it in a subclass!" % self._func.__name__)

# Comment this file

HOME_DIR = os.path.join(os.path.expanduser("~"), ".sharppy", "decoders")
_decoders = {}

def findDecoders():
    global _decoders

    built_ins = [ 'buf_decoder', 'spc_decoder', 'pecan_decoder', 'arw_decoder', 'uwyo_decoder', 'nucaps_decoder' ] # JTS - Added NUCAPS.
    io = __import__('sharppy.io', globals(), locals(), built_ins, 0)

    for dec in built_ins:
        # Load build-in decoders
        logging.debug("Loading decoder '%s'." % dec)
        dec_imp = getattr(io, dec)

        dec_name = dec_imp.__classname__
        fmt_name = dec_imp.__fmtname__

        _decoders[fmt_name] = getattr(dec_imp, dec_name)

    custom = glob.glob(os.path.join(HOME_DIR, '*.py'))

    for dec in custom:
        # Find and load custom decoders
        dec_mod_name = os.path.basename(dec)[:-3]
        logging.debug("Found custom decoder '%s'." % dec_mod_name)
        spec = importlib.util.spec_from_file_location(dec_mod_name, dec)
        dec_imp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dec_imp)

        dec_name = dec_imp.__classname__
        fmt_name = dec_imp.__fmtname__

        _decoders[fmt_name] = getattr(dec_imp, dec_name)

def getDecoder(dec_name):
    return getDecoders()[dec_name]

def getDecoders():
    if _decoders == {}:
        findDecoders()

    return _decoders

class Decoder(object):
    def __init__(self, file_name):
        self._file_name = file_name
        self._prof_collection = self._parse()

    @abstract
    def _parse(self):
        pass

    def _downloadFile(self):
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        f = None
        try:
            f = urlopen(self._file_name, context=ssl_ctx, timeout=20)
        except HTTPError as http_err:
            if http_err.code in (503, 429, 502, 504):
                # Transient server error — wait briefly and retry once
                logging.warning("HTTP %d for %s, retrying in 3s..." % (http_err.code, self._file_name))
                time.sleep(3)
                try:
                    f = urlopen(self._file_name, context=ssl_ctx, timeout=20)
                except Exception:
                    raise IOError("Server temporarily unavailable (HTTP %d): %s" % (http_err.code, self._file_name))
            else:
                raise IOError("HTTP error %d fetching '%s'" % (http_err.code, self._file_name))
        except (ValueError, IOError):
            try:
                fname = self._file_name[7:] if self._file_name.startswith('file://') else self._file_name
                f = open(fname, 'rb')
            except IOError:
                raise IOError("File '%s' cannot be found" % self._file_name)
        file_data = f.read()
        return file_data.decode('utf-8')

    def getProfiles(self, indexes=None):
        '''
            Returns a list of profile objects generated from the
            file that was read in.

            Parameters
            ----------
            prof_idxs : list (optional)
                A list of indices corresponding to the profiles to be returned.
                Default is to return the full list of profiles

        '''
        prof_col = self._prof_collection
        if indexes is not None:
            prof_col = prof_col.subset(indexes)
        return prof_col

    def getStnId(self):
        return self._prof_collection.getMeta('loc')

if __name__ == "__main__":
    print("Creating bufkit decoder ...")
    bd = BufDecoder()
