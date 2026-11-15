from flask import Response

from services import core


def _safe(cell):
    """Stops spreadsheet formula injection: a cell starting with = + - @ would be run by Excel. (C++: qm::sanitize_cell)"""
    return core.csv_safe(cell)


def csv_response(filename, headers, rows):
    data = core.csv_text(headers, rows)        # C++ qm::CsvWriter: quoting, BOM and formula safety for every text cell
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
