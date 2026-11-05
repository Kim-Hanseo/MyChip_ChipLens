"""Generic table reader: preview_file (auto-guess + preview) and read_table (options -> RawTable)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.models import (
    PREVIEW_HEAD_ROWS,
    PREVIEW_RAW_ROWS,
    ColumnInfo,
    FileKind,
    Notice,
    RawTable,
    ReadOptions,
    TablePreview,
    WarningCode,
)

from .headers import build_column_info, is_time_like
from .readers import (
    Grid,
    decode_text,
    file_kind,
    guess_delimiter,
    guess_header,
    read_xlsx_grid,
    text_grid,
)

TIME_DUP_RTOL = 1e-9  # repeated wrdata time columns are "the same" within this relative tolerance


@dataclass
class _Parsed:
    kind: FileKind
    options: ReadOptions
    sheets: list[str]
    grid: Grid
    columns: list[ColumnInfo]
    frame: pd.DataFrame
    head_rows: list[list[str]]
    notices: list[Notice]


def _to_float(cells: tuple[str, ...]) -> np.ndarray:
    try:
        arr = np.array(cells, dtype=np.float64)
    except ValueError:
        parsed = pd.to_numeric(pd.Series(cells, dtype=object), errors="coerce")
        arr = np.array(parsed, dtype=np.float64)  # writable copy (CoW views are read-only)
    if arr.size:
        arr[~np.isfinite(arr)] = np.nan
    return arr


def _is_numeric(cells: tuple[str, ...], arr: np.ndarray) -> bool:
    n_nonempty = sum(1 for c in cells if c != "")
    n_num = int(np.count_nonzero(np.isfinite(arr)))
    return n_num > 0 and 2 * n_num >= n_nonempty


def _unique_names(raw: list[str]) -> list[str]:
    used: set[str] = set()
    out: list[str] = []
    for name in raw:
        cand, k = name, 1
        while cand in used:
            k += 1
            cand = f"{name}_{k}"
        used.add(cand)
        out.append(cand)
    return out


def _same_values(a: np.ndarray, b: np.ndarray) -> bool:
    if a.shape != b.shape:
        return False
    na, nb = np.isnan(a), np.isnan(b)
    if not np.array_equal(na, nb):
        return False
    va, vb = a[~na], b[~nb]
    if va.size == 0:
        return True
    tol = TIME_DUP_RTOL * max(float(np.max(np.abs(va))), float(np.max(np.abs(vb))))
    return bool(np.all(np.abs(va - vb) <= tol))


def _strictly_increasing(arr: np.ndarray) -> bool:
    v = arr[np.isfinite(arr)]
    return v.size >= 2 and bool(np.all(np.diff(v) > 0))


def _load_grid(
    data: bytes, file_name: str, options: ReadOptions | None
) -> tuple[FileKind, Grid, list[str], str | None, str | None, str | None, list[Notice]]:
    if not data:
        raise ValueError("빈 파일입니다.")
    kind = file_kind(file_name)
    if kind is FileKind.XLSX:
        sheets, sheet, grid = read_xlsx_grid(data, options.sheet if options else None)
        return kind, grid, sheets, sheet, None, None, []
    text, encoding, notices = decode_text(data, options.encoding if options else None)
    lines = text.splitlines()
    delimiter = options.delimiter if options is not None and options.delimiter else guess_delimiter(lines)
    return kind, text_grid(lines, delimiter), [], None, encoding, delimiter, notices


def _parse(data: bytes, file_name: str, options: ReadOptions | None) -> _Parsed:
    kind, grid, sheets, sheet, encoding, delimiter, notices = _load_grid(data, file_name, options)
    if not any(c != "" for row in grid for c in row):
        raise ValueError("파일(시트)에 내용이 없습니다.")

    if options is None:
        header_row, data_start = guess_header(grid)
        default_start = header_row + 1 if header_row is not None else 0
        resolved = ReadOptions(
            encoding=encoding,
            delimiter=delimiter,
            sheet=sheet,
            header_row=header_row,
            data_start_row=None if data_start == default_start else data_start,
        )
    else:
        header_row = options.header_row
        data_start = (
            options.data_start_row
            if options.data_start_row is not None
            else (header_row + 1 if header_row is not None else 0)
        )
        resolved = options.model_copy(update={"encoding": encoding, "delimiter": delimiter, "sheet": sheet})
    if header_row is not None and header_row >= len(grid):
        raise ValueError(f"헤더 행 {header_row}이(가) 파일 행 수({len(grid)})를 넘습니다.")

    header_cells = list(grid[header_row]) if header_row is not None else []
    body = [r for r in grid[data_start:] if any(c != "" for c in r)]
    ncols = max([len(header_cells)] + [len(r) for r in body])
    if ncols == 0:
        raise ValueError("표에서 열을 찾지 못했습니다. 헤더 행·구분자를 확인해 주세요.")
    header_cells += [""] * (ncols - len(header_cells))
    rows = [r if len(r) == ncols else r + [""] * (ncols - len(r)) for r in body]
    col_cells: list[tuple[str, ...]] = list(zip(*rows, strict=True)) if rows else [()] * ncols

    # drop columns that are empty in the header and in every data row (e.g. trailing delimiters)
    idx = [i for i in range(ncols) if header_cells[i] != "" or any(c != "" for c in col_cells[i])]
    names = _unique_names([header_cells[i] or f"col{i}" for i in idx])
    arrays = {i: _to_float(col_cells[i]) for i in idx}
    infos = {
        i: build_column_info(name, header_cells[i], _is_numeric(col_cells[i], arrays[i]))
        for i, name in zip(idx, names, strict=True)
    }

    # ngspice wrdata: the time column header repeats once per vector -> drop identical repeats
    drop: set[int] = set()
    groups: dict[str, list[int]] = {}
    for i in idx:
        key = header_cells[i].strip().lower()
        if key and is_time_like(infos[i]):
            groups.setdefault(key, []).append(i)
    for members in groups.values():
        first = members[0]
        for i in members[1:]:
            if infos[first].numeric and infos[i].numeric and _same_values(arrays[first], arrays[i]):
                drop.add(i)
            else:
                notices.append(
                    Notice(
                        code=WarningCode.TIME_COLUMN_MISMATCH,
                        message=(
                            f"반복된 시간 열 '{infos[i].name}'의 값이 첫 시간 열 '{infos[first].name}'과 "
                            "달라 별도 열로 남겼습니다."
                        ),
                    )
                )
    kept = [i for i in idx if i not in drop]

    columns = [infos[i] for i in kept]
    frame = pd.DataFrame(
        {
            infos[i].name: (arrays[i] if infos[i].numeric else pd.Series(list(col_cells[i]), dtype="str"))
            for i in kept
        }
    )
    if frame.shape[1] != len(columns):  # pragma: no cover - names are unique by construction
        raise ValueError("열 이름이 중복되었습니다.")
    head_rows = [[r[i] for i in kept] for r in rows[:PREVIEW_HEAD_ROWS]]
    return _Parsed(kind, resolved, sheets, grid, columns, frame, head_rows, notices)


def _time_candidates(columns: list[ColumnInfo], frame: pd.DataFrame) -> list[str]:
    numeric = [c for c in columns if c.numeric]
    out = [c.name for c in numeric if c.si_unit == "s"]
    out += [c.name for c in numeric if c.name not in out and is_time_like(c)]
    out += [
        c.name
        for c in numeric
        if c.name not in out and _strictly_increasing(frame[c.name].to_numpy(dtype=np.float64))
    ]
    return out


def preview_file(data: bytes, file_name: str, options: ReadOptions | None = None) -> TablePreview:
    """Upload step: guess (or apply) read options and return a preview for the mapping UI.

    options=None -> encoding, delimiter, sheet, header row are all guessed. Raises ValueError
    (Korean message) for unsupported or unreadable files.
    """
    p = _parse(data, file_name, options)
    return TablePreview(
        file_name=file_name,
        kind=p.kind,
        options=p.options,
        sheets=p.sheets,
        raw_rows=[list(r) for r in p.grid[:PREVIEW_RAW_ROWS]],
        columns=p.columns,
        time_candidates=_time_candidates(p.columns, p.frame),
        head_rows=p.head_rows,
        notices=p.notices,
    )


def read_table(data: bytes, file_name: str, options: ReadOptions) -> RawTable:
    """Read the whole table with the given options. Values are RAW (no unit scaling)."""
    p = _parse(data, file_name, options)
    return RawTable(file_name=file_name, options=p.options, columns=p.columns, data=p.frame, notices=p.notices)
