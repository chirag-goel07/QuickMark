"""Excel (.xlsx) downloads."""
import io
import re

from flask import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from services.csvutil import _safe

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_BAD_TITLE = re.compile(r"[\[\]:*?/\\]")


def _title(name, used):
    base = (_BAD_TITLE.sub(" ", str(name)).strip() or "Sheet")[:28]
    t, n = base, 2
    while t.lower() in used:
        t = f"{base[:25]} {n}"; n += 1
    used.add(t.lower())
    return t


def xlsx_response(filename, sheets, highlight_low=None):
    """sheets = [(title, headers, rows)]. Cells are made safe against formula injection (a name like =CMD() stays text).
    highlight_low = (column_header, threshold): that column's numbers below the threshold are shown in red."""
    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    head_fill = PatternFill("solid", fgColor="1F3A68")
    for title, headers, rows in sheets:
        ws = wb.create_sheet(_title(title, used))
        ws.append(list(headers))
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = head_fill; c.alignment = Alignment(vertical="center", wrap_text=True)
        for r in rows:
            ws.append([_safe(c) for c in r])
        ws.freeze_panes = "A2"
        for i, h in enumerate(headers, start=1):
            longest = max([len(str(h))] + [len(str(r[i - 1])) for r in rows if i - 1 < len(r) and r[i - 1] is not None] or [8])
            ws.column_dimensions[get_column_letter(i)].width = min(40, max(9, longest + 2))
        if highlight_low and highlight_low[0] in headers:
            col = list(headers).index(highlight_low[0]) + 1
            for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                for c in row:
                    if isinstance(c.value, (int, float)) and c.value < highlight_low[1]:
                        c.font = Font(color="C0392B", bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), mimetype=MIME, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
