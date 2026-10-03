"""Data limits: none when Driver Signal runs locally, hard caps only for a public demo.

Run on someone's own computer (standalone, a local Signal Hub, or an internal company deployment), Driver Signal has
no built-in limit on file size, respondents, cells, items or drivers; memory is the limit. A public demo sets
``SIGNAL_PUBLIC=1`` (Signal Hub's public Docker image does), and then the caps below protect the shared server.
Every cap lives here.
"""

from __future__ import annotations

import os

from .errors import DataProblem


DEMO_MAX_UPLOAD_MB = 200
DEMO_MAX_JSON_MB = 30
DEMO_MAX_WORKBOOK_UNPACKED_MB = 250
DEMO_MAX_ROWS = 500_000
DEMO_MAX_CELLS = 8_000_000
DEMO_MAX_ITEMS = 30
DEMO_MAX_DRIVERS = 20
DEMO_NOTE = "This public demo has that limit to protect a shared server; the downloaded app has no built-in limit."


def is_public() -> bool:
    """True only for a public demo deployment (``SIGNAL_PUBLIC=1``)."""
    return os.environ.get("SIGNAL_PUBLIC") == "1"


def _refuse(what: str) -> None:
    raise DataProblem(f"{what} {DEMO_NOTE}")


def check_upload_bytes(size: int, *, json_file: bool = False) -> None:
    if not is_public():
        return
    if size > DEMO_MAX_UPLOAD_MB * 1024 * 1024:
        _refuse(f"The file is larger than {DEMO_MAX_UPLOAD_MB} MB.")
    if json_file and size > DEMO_MAX_JSON_MB * 1024 * 1024:
        _refuse(f"JSON uploads are limited to {DEMO_MAX_JSON_MB} MB.")


def check_workbook_unpacked(size: int) -> None:
    if is_public() and size > DEMO_MAX_WORKBOOK_UNPACKED_MB * 1024 * 1024:
        _refuse(f"The workbook expands beyond {DEMO_MAX_WORKBOOK_UNPACKED_MB} MB.")


def check_table(rows: int, cells: int) -> None:
    if is_public() and (rows > DEMO_MAX_ROWS or cells > DEMO_MAX_CELLS):
        _refuse(f"The file has more than {DEMO_MAX_ROWS:,} rows or {DEMO_MAX_CELLS:,} cells.")


def check_items(count: int) -> None:
    if is_public() and count > DEMO_MAX_ITEMS:
        _refuse(f"Use at most {DEMO_MAX_ITEMS} item columns in one analysis.")


def check_drivers(count: int) -> None:
    if is_public() and count > DEMO_MAX_DRIVERS:
        _refuse(f"Use at most {DEMO_MAX_DRIVERS} scored drivers in one model.")
