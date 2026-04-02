
import numpy as np

import bsharp.sharptab.profile as profile

from urllib.request import urlopen
from urllib.error import HTTPError
import certifi
import ssl
import time
import logging

class abstract(object):
    def __init__(self, func):
        self._func = func

    def __call__(self, *args, **kwargs):
        raise NotImplementedError("Function or method '%s' is abstract.  Override it in a subclass!" % self._func.__name__)

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
        prof_col = self._prof_collection
        if indexes is not None:
            prof_col = prof_col.subset(indexes)
        return prof_col

    def getStnId(self):
        return self._prof_collection.getMeta('loc')
