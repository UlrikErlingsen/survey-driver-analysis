"""Safe local survey input and portable evidence-pack exports."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from io import BytesIO
import json
import math
from pathlib import Path
import re
from typing import BinaryIO
import zipfile

import numpy as np
import pandas as pd

from .errors import MEMORY_MESSAGE, DataProblem
from .limits import check_table, check_upload_bytes, check_workbook_unpacked


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".json"}
# Locally there is no size, row or cell limit (memory is the limit); a public demo (SIGNAL_PUBLIC=1) applies the
# caps in limits.py. CSV is read in chunks so a demo cap stops early and numbers are stored compactly.
CSV_CHUNK_ROWS = 250_000
# Excel's own sheet limit (1,048,576 rows including the header); CSV and JSON exports always hold every row.
EXCEL_MAX_DATA_ROWS = 1_048_575
CSV_SNIFF_BYTES = 64 * 1024
ILLEGAL_XML_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class LoadedData:
    """Named tables read from one local source."""

    tables: dict[str, pd.DataFrame]
    source_name: str


def _unique_column_names(columns: list[object]) -> list[str]:
    result: list[str] = []
    used: set[str] = set()
    for index, column in enumerate(columns):
        base = str(column).strip() or f"column_{index + 1}"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}__{suffix}"
            suffix += 1
        used.add(candidate)
        result.append(candidate)
    return result


def _source_bytes(source: str | Path | bytes | BinaryIO) -> tuple[bytes, str]:
    if isinstance(source, (str, Path)):
        path = Path(source)
        return path.read_bytes(), path.name
    if isinstance(source, bytes):
        return source, "uploaded.csv"
    name = Path(getattr(source, "name", "uploaded.csv")).name
    if hasattr(source, "seek"):
        source.seek(0)
    return source.read(), name


def _sniff_delimiter(raw: bytes) -> str:
    """Detect the CSV delimiter from the first lines, so the fast C parser can read the whole file."""
    sample = raw[:CSV_SNIFF_BYTES].decode("utf-8-sig", errors="ignore")
    if len(raw) > CSV_SNIFF_BYTES and "\n" in sample:
        sample = sample[: sample.rfind("\n")]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def compact_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Store numbers in the smallest lossless dtype, in place: rating scales fit in int8 or float32."""
    for column in frame.columns:
        series = frame[column]
        kind = series.dtype.kind
        if kind in "iu":
            frame[column] = pd.to_numeric(series, downcast="integer")
        elif kind == "f" and series.dtype.itemsize > 4:
            values = series.to_numpy()
            narrow = values.astype(np.float32)
            if np.array_equal(narrow.astype(values.dtype), values, equal_nan=True):
                frame[column] = narrow
    return frame


def _read_csv(raw: bytes) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    rows = 0
    cells = 0
    reader = pd.read_csv(BytesIO(raw), sep=_sniff_delimiter(raw), chunksize=CSV_CHUNK_ROWS)
    with reader:
        for chunk in reader:
            rows += len(chunk)
            cells += int(chunk.shape[0] * chunk.shape[1])
            check_table(rows, cells)
            chunks.append(compact_frame(chunk))
    if not chunks:
        return pd.DataFrame()
    if len(chunks) == 1:
        return chunks[0]
    frame = pd.concat(chunks, ignore_index=True)
    chunks.clear()
    return compact_frame(frame)


def load_data(source: str | Path | bytes | BinaryIO, name: str | None = None) -> LoadedData:
    """Read CSV, Excel, or JSON without executing uploaded content."""
    raw, detected_name = _source_bytes(source)
    source_name = name or detected_name
    extension = Path(source_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DataProblem("Please use CSV, Excel, or JSON survey data.")
    check_upload_bytes(len(raw), json_file=extension == ".json")
    if not raw:
        raise DataProblem("This file is empty.")

    try:
        if extension == ".csv":
            tables = {"data": _read_csv(raw)}
        elif extension in {".xlsx", ".xls", ".xlsm"}:
            if extension in {".xlsx", ".xlsm"}:
                with zipfile.ZipFile(BytesIO(raw)) as workbook:
                    check_workbook_unpacked(sum(member.file_size for member in workbook.infolist()))
            tables = pd.read_excel(BytesIO(raw), sheet_name=None)
        else:
            payload = json.loads(raw.decode("utf-8-sig"))
            if isinstance(payload, list):
                tables = {"data": pd.DataFrame(payload)}
            elif isinstance(payload, dict) and all(isinstance(value, list) for value in payload.values()):
                record_tables = all(
                    not value or all(isinstance(record, dict) for record in value) for value in payload.values()
                )
                tables = (
                    {str(key): pd.DataFrame(value) for key, value in payload.items()}
                    if record_tables
                    else {"data": pd.DataFrame(payload)}
                )
            else:
                tables = {"data": pd.DataFrame(payload)}
            del payload
    except DataProblem:
        raise
    except MemoryError as exc:
        raise DataProblem(MEMORY_MESSAGE) from exc
    except Exception as exc:
        raise DataProblem(
            "The file could not be read. Check that it opens normally and that the first row contains column names."
        ) from exc

    clean: dict[str, pd.DataFrame] = {}
    total_cells = 0
    for table_name, frame in tables.items():
        if frame is None or (frame.empty and len(frame.columns) == 0):
            continue
        # The frames were created here, so they are renamed and compacted in place instead of copied.
        frame.columns = _unique_column_names(list(frame.columns))
        total_cells += int(frame.shape[0] * frame.shape[1])
        check_table(len(frame), total_cells)
        clean[str(table_name)] = compact_frame(frame) if extension != ".csv" else frame
    if not clean:
        raise DataProblem("No usable tables were found in this file.")
    return LoadedData(tables=clean, source_name=source_name)


def safe_for_spreadsheet(frame: pd.DataFrame) -> pd.DataFrame:
    """Neutralize strings that spreadsheet programs could interpret as formulas."""
    safe = frame.copy()

    def neutralize(value: object) -> object:
        if not isinstance(value, str):
            return value
        cleaned = ILLEGAL_XML_CHARACTERS.sub("", value)
        return "'" + cleaned if cleaned.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else cleaned

    safe.columns = _unique_column_names([neutralize(str(column)) for column in safe.columns])
    for column in safe.columns:
        dtype = safe[column].dtype
        if not (pd.api.types.is_object_dtype(dtype) or isinstance(dtype, (pd.CategoricalDtype, pd.StringDtype))):
            continue  # numbers, booleans and dates cannot carry a formula; millions of them need no per-cell pass
        series = safe[column].astype(object) if isinstance(dtype, pd.CategoricalDtype) else safe[column]
        safe[column] = series.map(neutralize)
    return safe


def results_to_excel(tables: dict[str, pd.DataFrame]) -> bytes:
    """Create an in-memory Excel evidence pack with readable sheets."""
    if not tables:
        raise DataProblem("There are no result tables to export.")
    output = BytesIO()
    used_names: set[str] = set()
    truncated: list[dict[str, object]] = []
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for raw_name, frame in tables.items():
            if len(frame) > EXCEL_MAX_DATA_ROWS:
                truncated.append(
                    {"sheet": str(raw_name), "rows_in_sheet": EXCEL_MAX_DATA_ROWS, "rows_in_table": len(frame)}
                )
                frame = frame.head(EXCEL_MAX_DATA_ROWS)
            base = re.sub(r"[\\/*?:\[\]]", "-", str(raw_name))[:31] or "Results"
            sheet_name = base
            suffix = 2
            while sheet_name in used_names:
                tail = f"_{suffix}"
                sheet_name = base[: 31 - len(tail)] + tail
                suffix += 1
            used_names.add(sheet_name)
            safe = safe_for_spreadsheet(frame)
            safe.to_excel(writer, sheet_name=sheet_name, index=False)
            sheet = writer.sheets[sheet_name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cells in sheet.columns:
                widths = [len(str(cell.value)) if cell.value is not None else 0 for cell in cells[:2000]]
                sheet.column_dimensions[cells[0].column_letter].width = min(max(widths, default=8) + 2, 44)
        if truncated:
            notes = pd.DataFrame(truncated)
            notes["note"] = "Excel holds at most 1,048,576 rows per sheet; the CSV and JSON exports hold every row."
            notes.to_excel(writer, sheet_name="Excel row limit", index=False)
    return output.getvalue()


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


JSON_STREAM_ROWS = 50_000


def results_to_json(tables: dict[str, pd.DataFrame], metadata: dict | None = None) -> bytes:
    """Serialize evidence tables and reproducibility metadata as UTF-8 JSON."""
    payload: dict[str, object] = {}
    large: dict[str, str] = {}
    for name, frame in tables.items():
        if len(frame) > JSON_STREAM_ROWS:
            # Millions of rows go straight from pandas' JSON writer into the document (same values: non-finite
            # numbers become null) instead of through Python objects, which would need gigabytes.
            marker = f"__driversignal_table_{len(large)}__"
            large[f'"{marker}"'] = frame.replace([np.inf, -np.inf], np.nan).to_json(orient="records", date_format="iso")
            payload[name] = marker
            continue
        records = json.loads(frame.to_json(orient="records", date_format="iso"))
        payload[name] = _json_safe(records)
    if metadata:
        payload["analysis_metadata"] = _json_safe(metadata)
    text = json.dumps(payload, indent=2, default=str, allow_nan=False)
    for marker, table_json in large.items():
        text = text.replace(marker, table_json, 1)
    return text.encode("utf-8")


def tables_to_csv_zip(tables: dict[str, pd.DataFrame]) -> bytes:
    """Package equivalent accessible CSV tables in one archive."""
    if not tables:
        raise DataProblem("There are no result tables to export.")
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for raw_name, frame in tables.items():
            filename = re.sub(r"[^A-Za-z0-9._-]+", "_", str(raw_name).strip()).strip("_") or "results"
            archive.writestr(f"{filename}.csv", safe_for_spreadsheet(frame).to_csv(index=False))
    return output.getvalue()
