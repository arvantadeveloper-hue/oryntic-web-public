"""CSV writer that neutralizes spreadsheet formula injection (CWE-1236).
Any string cell starting with = + - @ tab or CR is prefixed with an apostrophe so
spreadsheets treat it as text, not a live formula."""
import csv

_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(v):
    if isinstance(v, str) and v and v[0] in _FORMULA_PREFIX:
        return "'" + v
    return v


class SafeWriter:
    def __init__(self, fileobj, **kw):
        self._w = csv.writer(fileobj, **kw)

    def writerow(self, row):
        self._w.writerow([sanitize_cell(c) for c in row])

    def writerows(self, rows):
        for r in rows:
            self.writerow(r)
