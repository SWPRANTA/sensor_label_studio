"""Label-only CSV editing. Plotting views never become exported data."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import csv, hashlib, io, re
import numpy as np
import pandas as pd


class CsvError(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def label_spans(data, delimiter, label_index):
    """Strict CSV scanner preserving raw offsets, quoted newlines and blank lines."""
    begin = 3 if data.startswith(b'\xef\xbb\xbf') else 0
    sep = ord(delimiter)
    start = record_start = begin
    col = 0
    state = "plain"
    close = skip = -1
    header = True
    span = None
    result = []
    expression = re.compile(b'["\r\n' + re.escape(delimiter.encode("ascii")) + b']')

    def finish_record(end):
        nonlocal header, span, col
        blank = end == record_start and col == 0 and state == "plain"
        if not blank:
            if header:
                header = False
            elif span is not None:
                result.append(span)
            else:
                raise CsvError("A record does not contain the label column")
        span = None
        col = 0

    for match in expression.finditer(data, begin):
        pos = match.start()
        token = data[pos]
        if pos == skip:
            continue
        if token == 34:
            if state == "quoted":
                state = "closed"
                close = pos
            elif state == "closed" and pos == close + 1:
                state = "quoted"
            elif state == "plain" and pos == start:
                state = "quoted"
            else:
                raise CsvError("Unexpected quote in an unquoted CSV field")
            continue
        if state == "quoted":
            continue
        if state == "closed" and pos != close + 1:
            raise CsvError("Unexpected text after a closing CSV quote")
        if col == label_index:
            span = (start, pos)
        if token == sep:
            col += 1
            start = pos + 1
            state = "plain"
        else:
            finish_record(pos)
            skip = pos + 1 if token == 13 and data[pos+1:pos+2] == b'\n' else -1
            start = record_start = pos + (2 if skip >= 0 else 1)
            state = "plain"
    if state == "quoted":
        raise CsvError("Unterminated quoted CSV field")
    if state == "closed" and len(data) != close + 1:
        raise CsvError("Unexpected text after the last closing quote")
    if record_start < len(data):
        if col == label_index:
            span = (start, len(data))
        finish_record(len(data))
    return np.asarray(result, dtype=np.int64).reshape(-1, 2)


def nonlabel_digest(data, spans):
    h = hashlib.sha256()
    h.update(b"label-excluded-csv-v1")
    cursor = 0
    for start, end in spans:
        chunk = data[cursor:int(start)]
        h.update(len(chunk).to_bytes(8, "little"))
        h.update(chunk)
        cursor = int(end)
    chunk = data[cursor:]
    h.update(len(chunk).to_bytes(8, "little"))
    h.update(chunk)
    return h.hexdigest()


@dataclass
class Clock:
    values: np.ndarray
    column: str
    unit: str
    origin: str
    minimum: float
    last: float
    exclusive_end: float
    missing: int
    duplicates: int

    def rows(self, start, end, include_end=False):
        try:
            a, b = float(Decimal(str(start))), float(Decimal(str(end)))
        except (InvalidOperation, ValueError):
            raise CsvError("Time bounds must be numbers in seconds")
        if not np.isfinite([a, b]).all() or b <= a:
            raise CsvError("End time must exceed start time; both must be finite")
        return np.flatnonzero((self.values >= a) & ((self.values <= b) if include_end else (self.values < b)))


@dataclass
class Recording:
    raw: bytes
    filename: str
    encoding: str
    delimiter: str
    frame: pd.DataFrame
    label_column: str
    spans: np.ndarray
    numeric: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, raw, filename="recording.csv", encoding="utf-8", delimiter=","):
        if encoding not in {"utf-8", "cp1252", "latin-1"}:
            raise CsvError("Choose UTF-8, Windows-1252 or Latin-1")
        if delimiter not in {",", ";", "\t"}:
            raise CsvError("Unsupported delimiter")
        if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
            raise CsvError("UTF-16 is not supported; export a separate UTF-8 copy first")
        if not raw:
            raise CsvError("The CSV is empty")
        try:
            codec = "utf-8-sig" if raw.startswith(b'\xef\xbb\xbf') and encoding == "utf-8" else encoding
            reader = csv.reader(io.StringIO(raw.decode(codec), newline=""), delimiter=delimiter, strict=True)
            records = [r for r in reader if r]
        except (UnicodeDecodeError, csv.Error) as exc:
            raise CsvError("Cannot parse this CSV without loss: " + str(exc)) from exc
        if len(records) < 2:
            raise CsvError("A header and at least one data sample are required")
        header = records[0]
        if len(set(header)) != len(header) or any(not h.strip() for h in header):
            raise CsvError("Column names must be unique and nonempty")
        labels = [h for h in header if h.strip().casefold() == "label"]
        if len(labels) != 1:
            raise CsvError("Exactly one label column is required (case-insensitive)")
        for i, row in enumerate(records[1:]):
            if len(row) != len(header):
                raise CsvError(f"Sample {i+1} has {len(row)} fields; expected {len(header)}. No rows were dropped.")
        spans = label_spans(raw, delimiter, header.index(labels[0]))
        if len(spans) != len(records)-1:
            raise CsvError("Sample/byte-span counts disagree; editing is disabled")
        frame = pd.DataFrame(records[1:], columns=header, dtype=str)
        return cls(raw, filename, encoding, delimiter, frame, labels[0], spans)

    @property
    def source_sha256(self):
        return sha(self.raw)

    def numbers(self, column):
        if column not in self.numeric:
            a = pd.to_numeric(self.frame[column], errors="coerce").to_numpy(dtype=float, copy=True)
            a[~np.isfinite(a)] = np.nan
            self.numeric[column] = a
        return self.numeric[column]

    def numeric_columns(self):
        return [c for c in self.frame if c != self.label_column and np.isfinite(self.numbers(c)).any()]

    def clock(self, column, unit="milliseconds", relative=False):
        scale = {"seconds": Decimal(1), "milliseconds": Decimal(1000),
                 "microseconds": Decimal(1000000), "nanoseconds": Decimal(1000000000)}.get(unit)
        if scale is None:
            raise CsvError("Choose a supported timestamp unit")
        values, origin = [], None
        for text in self.frame[column]:
            try:
                v = Decimal(text)
                if not v.is_finite():
                    v = None
            except InvalidOperation:
                v = None
            if v is not None and origin is None:
                origin = v
            values.append(v)
        if origin is None:
            raise CsvError("This clock has no numeric timestamps")
        offset = origin if relative else Decimal(0)
        # Subtract before float conversion to retain very large epoch precision.
        t = np.array([float((v-offset)/scale) if v is not None else np.nan for v in values])
        good = t[np.isfinite(t)]
        if not len(good):
            raise CsvError("The time values exceed the supported numeric range")
        delta = np.diff(good)
        if (delta < 0).any():
            raise CsvError("This clock goes backwards. Choose another clock; samples are never sorted or removed.")
        positive = delta[delta > 0]
        step = float(np.median(positive)) if len(positive) else .001
        return Clock(t, column, unit, str(offset), float(good[0]), float(good[-1]),
                     float(good[-1]+step), int((~np.isfinite(t)).sum()), int((delta == 0).sum()))


def encoded_label(value, encoding, delimiter):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise CsvError("Enter a nonempty label of at most 160 characters")
    if any(ch in value for ch in "\r\n\x00"):
        raise CsvError("A label cannot contain a newline or NUL")
    if value.lstrip().startswith(("=", "+", "-", "@")):
        raise CsvError("Labels starting with spreadsheet formula markers are unsupported")
    out = io.StringIO(newline="")
    csv.writer(out, delimiter=delimiter, lineterminator="").writerow([value])
    try:
        return out.getvalue().encode(encoding)
    except UnicodeEncodeError as exc:
        raise CsvError("The label cannot be represented in the original encoding") from exc


@dataclass
class EditSession:
    recording: Recording
    labels: np.ndarray = field(init=False)
    undo_stack: list = field(default_factory=list, repr=False)
    redo_stack: list = field(default_factory=list, repr=False)
    audit: list = field(default_factory=list)
    revision: int = 0
    prepared: object = None

    def __post_init__(self):
        self.labels = self.recording.frame[self.recording.label_column].to_numpy(copy=True)

    @property
    def changed(self):
        return np.flatnonzero(self.labels != self.recording.frame[self.recording.label_column].to_numpy())

    def _log(self, action, count, details):
        self.revision += 1
        self.prepared = None
        self.audit.append(dict(revision=self.revision, action=action, changed_rows=count,
                               utc=datetime.now(timezone.utc).isoformat(), **details))

    def apply(self, clock, start, end, label, include_end=False):
        encoded_label(label, self.recording.encoding, self.recording.delimiter)
        selected = clock.rows(start, end, include_end)
        if not len(selected):
            raise CsvError("There are no timestamped samples in that interval")
        ids = selected[self.labels[selected] != label]
        if not len(ids):
            return 0
        item = dict(ids=ids.copy(), before=self.labels[ids].copy(), after=label,
                    details=dict(start_s=float(start), end_s=float(end), include_end=include_end,
                                 label=label, time_column=clock.column, time_unit=clock.unit, time_origin=clock.origin))
        self.labels[ids] = label
        self.undo_stack.append(item)
        self.redo_stack.clear()
        self._log("apply", len(ids), item["details"])
        return len(ids)

    def undo(self):
        if not self.undo_stack:
            return False
        item = self.undo_stack.pop()
        self.labels[item["ids"]] = item["before"]
        self.redo_stack.append(item)
        self._log("undo", len(item["ids"]), item["details"])
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        item = self.redo_stack.pop()
        self.labels[item["ids"]] = item["after"]
        self.undo_stack.append(item)
        self._log("redo", len(item["ids"]), item["details"])
        return True

    def reset(self):
        self.labels = self.recording.frame[self.recording.label_column].to_numpy(copy=True)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._log("reset", 0, {})

    def export(self):
        rec, pieces, cursor, ids = self.recording, [], 0, self.changed
        for row in ids:
            start, end = rec.spans[row]
            pieces.extend([rec.raw[cursor:int(start)], encoded_label(str(self.labels[row]), rec.encoding, rec.delimiter)])
            cursor = int(end)
        pieces.append(rec.raw[cursor:])
        data = b"".join(pieces)
        restored = Recording.load(data, rec.filename, rec.encoding, rec.delimiter)
        other = [c for c in rec.frame if c != rec.label_column]
        if not restored.frame[other].equals(rec.frame[other]):
            raise CsvError("Export blocked: an unrelated field changed")
        if not np.array_equal(restored.frame[rec.label_column].to_numpy(), self.labels):
            raise CsvError("Exported labels did not round trip")
        before = nonlabel_digest(rec.raw, rec.spans)
        if before != nonlabel_digest(data, restored.spans):
            raise CsvError("Export blocked: bytes outside label tokens changed")
        report = dict(source_file=rec.filename, source_sha256=rec.source_sha256, output_sha256=sha(data),
                      source_bytes=len(rec.raw), output_bytes=len(data), rows=len(rec.frame), columns=len(rec.frame.columns),
                      edited_column=rec.label_column, changed_label_rows=len(ids), nonlabel_bytes_sha256=before,
                      nonlabel_bytes_identical=True, unrelated_fields_equal=True, labels_round_trip=True,
                      row_order_unchanged=True, encoding=rec.encoding, delimiter=rec.delimiter, revision=self.revision)
        self.prepared = data, report
        return data, report

    def audit_document(self):
        rec = self.recording
        return dict(schema_version=1, source_sha256=rec.source_sha256, source_file=rec.filename,
                    label_column=rec.label_column,
                    row_numbering="zero-based data samples excluding header and blank physical records",
                    changes=[dict(row=int(i), original=rec.frame[rec.label_column].iat[i], label=str(self.labels[i])) for i in self.changed],
                    operations=self.audit)
