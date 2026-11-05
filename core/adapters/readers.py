"""Low-level readers: bytes -> grid of cell strings (delimited text or xlsx) + format guesses."""

from __future__ import annotations

import csv
import io
import math
from collections import Counter
from datetime import date, datetime, time
from pathlib import PurePath

from core.models import FileKind, Notice, WarningCode

CANDIDATE_DELIMITERS: tuple[str, ...] = (",", "\t", ";", " ")  # " " = any whitespace run
AUTO_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp949")
DELIMITER_SAMPLE_LINES = 400
HEADER_SCAN_ROWS = 2000
_CP949_NAMES = frozenset({"cp949", "ms949", "euc-kr", "euckr", "euc_kr", "uhc"})

Grid = list[list[str]]


def file_kind(file_name: str) -> FileKind:
    """File kind from the (lower-cased) extension. `.xls` is rejected."""
    ext = PurePath(file_name).suffix.lower()
    if ext == ".xls":
        raise ValueError("구형 엑셀(.xls) 파일은 지원하지 않습니다. 엑셀에서 .xlsx로 저장한 뒤 다시 올려 주세요.")
    if ext == ".csv":
        return FileKind.CSV
    if ext in (".xlsx", ".xlsm"):
        return FileKind.XLSX
    return FileKind.TEXT


def decode_text(data: bytes, encoding: str | None = None) -> tuple[str, str, list[Notice]]:
    """Decode bytes. Auto: UTF-8 (BOM allowed), then cp949 with an ENCODING_FALLBACK notice.

    Returns (text, encoding_used, notices).
    """
    if encoding:
        try:
            text = data.decode(encoding)
        except LookupError as exc:
            raise ValueError(f"알 수 없는 인코딩입니다: '{encoding}'") from exc
        except UnicodeDecodeError as exc:
            raise ValueError(f"'{encoding}' 인코딩으로 파일을 읽을 수 없습니다. 다른 인코딩을 선택해 주세요.") from exc
        used = encoding
        text = text.lstrip("﻿")
    else:
        try:
            text, used = data.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            try:
                text, used = data.decode("cp949"), "cp949"
            except UnicodeDecodeError as exc:
                raise ValueError("파일 인코딩을 알 수 없습니다 (UTF-8, CP949 모두 실패).") from exc
    notices: list[Notice] = []
    if used.lower() in _CP949_NAMES:
        notices.append(
            Notice(
                code=WarningCode.ENCODING_FALLBACK,
                message="UTF-8로 읽을 수 없어 CP949(한글 Windows) 인코딩으로 읽었습니다.",
            )
        )
    return text, used, notices


def split_line(line: str, delimiter: str) -> list[str]:
    """Split one line into stripped cells. " " splits on any whitespace run."""
    if delimiter == " ":
        return line.split()
    if '"' in line:
        row = next(csv.reader([line], delimiter=delimiter), [])
        return [c.strip() for c in row]
    return [c.strip() for c in line.split(delimiter)]


def text_grid(lines: list[str], delimiter: str) -> Grid:
    """One row per line (blank lines kept so row indices equal line indices)."""
    return [split_line(line, delimiter) for line in lines]


def guess_delimiter(lines: list[str]) -> str:
    """Pick the candidate giving the most lines with the same (>= 2) field count; ties -> earlier candidate."""
    sample = [ln for ln in lines if ln.strip()][:DELIMITER_SAMPLE_LINES]
    best, best_score = ",", (0, 0)
    for d in CANDIDATE_DELIMITERS:
        counts = Counter(len(split_line(ln, d)) for ln in sample)
        if not counts:
            continue
        width, freq = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
        if width < 2:
            continue
        score = (freq, width)
        if score > best_score:
            best, best_score = d, score
    return best


def is_number(cell: str) -> bool:
    """True if the cell parses as a finite float."""
    if not cell:
        return False
    try:
        return math.isfinite(float(cell))
    except ValueError:
        return False


def _row_is_numeric(row: list[str]) -> bool:
    cells = [c for c in row if c != ""]
    if not cells:
        return False
    n_num = sum(1 for c in cells if is_number(c))
    return n_num > len(cells) - n_num


def guess_header(grid: Grid) -> tuple[int | None, int]:
    """(header_row, data_start_row), both 0-based grid indices.

    Data = the longest run of consecutive numeric rows (first one on ties); header = the row just
    before it if that row is non-empty, else no header. No numeric rows -> header 0, data from 1.
    """
    flags = [_row_is_numeric(r) for r in grid[:HEADER_SCAN_ROWS]]
    best_start, best_len = -1, 0
    i = 0
    while i < len(flags):
        if not flags[i]:
            i += 1
            continue
        j = i
        while j < len(flags) and flags[j]:
            j += 1
        if j - i > best_len:
            best_start, best_len = i, j - i
        i = j
    if best_start < 0:
        return 0, 1
    if best_start == 0:
        return None, 0
    prev = grid[best_start - 1]
    if any(c != "" for c in prev):
        return best_start - 1, best_start
    return None, best_start


def _cell_text(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return repr(v) if math.isfinite(v) else ""
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return str(v).strip()


def read_xlsx_grid(data: bytes, sheet: str | None = None) -> tuple[list[str], str, Grid]:
    """(sheet names in workbook order, sheet used, grid). Merged ranges keep the value only in the
    top-left cell; formulas give their cached values."""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), data_only=True)
    except Exception as exc:  # openpyxl raises many types for corrupt files
        raise ValueError(f"엑셀 파일을 열 수 없습니다: {exc}") from exc
    try:
        sheets = list(wb.sheetnames)
        if not sheets:
            raise ValueError("엑셀 파일에 시트가 없습니다.")
        name = sheet if sheet is not None else sheets[0]
        if name not in sheets:
            raise ValueError(f"시트 '{name}'이(가) 없습니다. 시트 목록: {', '.join(sheets)}")
        ws = wb[name]
        grid = [[_cell_text(v) for v in row] for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    return sheets, name, grid
