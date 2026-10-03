"""Safe local survey input and portable evidence-pack exports."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
from typing import BinaryIO
import zipfile

import numpy as np
import pandas as pd

from .errors import DataProblem


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".json"}
DEFAULT_MAX_UPLOAD_MB = 1000


def _configured_upload_mb() -> int:
    """Read the launcher's upload cap so the in-code check matches Streamlit's own limit."""
    try:
        return max(1, int(os.getenv("DRIVERSIGNAL_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))))
    except ValueError:
        return DEFAULT_MAX_UPLOAD_MB


# One byte limit for every format (CSV, Excel, JSON); Streamlit's maxUploadSize applies the same cap.
MAX_UPLOAD_MB = _configured_upload_mb()
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
# Zip-bomb guard for workbooks: the unpacked XML of a legitimate sheet is several times its file size.
MAX_UNCOMPRESSED_EXCEL_BYTES = 4 * MAX_UPLOAD_BYTES
# Respondent rows and cells held in memory. Scoring and summaries are vectorized; the driver model and alpha
# bootstrap sample above their own documented sizes (see drivers.MODEL_MAX_ROWS and reliability.py).
MAX_TABLE_ROWS = 5_000_000
MAX_TOTAL_CELLS = 300_000_000
CSV_CHUNK_ROWS = 250_000
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
            if rows > MAX_TABLE_ROWS or cells > MAX_TOTAL_CELLS:
                raise DataProblem(_size_message())
            chunks.append(compact_frame(chunk))
    if not chunks:
        return pd.DataFrame()
    if len(chunks) == 1:
        return chunks[0]
    frame = pd.concat(chunks, ignore_index=True)
    chunks.clear()
    return compact_frame(frame)


def _size_message() -> str:
    return (
        f"This file has more than {MAX_TABLE_ROWS:,} rows or {MAX_TOTAL_CELLS:,} cells, the local limit. "
        "Keep only the needed columns, or split the respondents into waves."
    )


def load_data(source: str | Path | bytes | BinaryIO, name: str | None = None) -> LoadedData:
    """Read CSV, Excel, or JSON without executing uploaded content."""
    raw, detected_name = _source_bytes(source)
    source_name = name or detected_name
    extension = Path(source_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DataProblem("Please use CSV, Excel, or JSON survey data.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise DataProblem(f"This file is larger than the configured {MAX_UPLOAD_MB:,} MB limit.")
    if not raw:
        raise DataProblem("This file is empty.")

    try:
        if extension == ".csv":
            tables = {"data": _read_csv(raw)}
        elif extension in {".xlsx", ".xls", ".xlsm"}:
            if extension in {".xlsx", ".xlsm"}:
                with zipfile.ZipFile(BytesIO(raw)) as workbook:
                    expanded_size = sum(member.file_size for member in workbook.infolist())
                    if expanded_size > MAX_UNCOMPRESSED_EXCEL_BYTES:
                        raise DataProblem(
                            f"This workbook expands beyond {MAX_UNCOMPRESSED_EXCEL_BYTES // (1024 * 1024):,} MB. "
                            "Keep only the needed sheets, or save the survey as CSV."
                        )
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
        raise DataProblem(
            "This file does not fit in the memory available to Driver Signal. Keep only the needed columns, "
            "save it as CSV, or split the respondents into waves."
        ) from exc
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
        if len(frame) > MAX_TABLE_ROWS or total_cells > MAX_TOTAL_CELLS:
            raise DataProblem(_size_message())
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
        series = safe[column].astype(object) if isinstance(safe[column].dtype, pd.CategoricalDtype) else safe[column]
        safe[column] = series.map(neutralize)
    return safe


def results_to_excel(tables: dict[str, pd.DataFrame]) -> bytes:
    """Create an in-memory Excel evidence pack with readable sheets."""
    if not tables:
        raise DataProblem("There are no result tables to export.")
    output = BytesIO()
    used_names: set[str] = set()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for raw_name, frame in tables.items():
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


def results_to_json(tables: dict[str, pd.DataFrame], metadata: dict | None = None) -> bytes:
    """Serialize evidence tables and reproducibility metadata as UTF-8 JSON."""
    payload: dict[str, object] = {}
    for name, frame in tables.items():
        records = json.loads(frame.to_json(orient="records", date_format="iso"))
        payload[name] = _json_safe(records)
    if metadata:
        payload["analysis_metadata"] = _json_safe(metadata)
    return json.dumps(payload, indent=2, default=str, allow_nan=False).encode("utf-8")


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
