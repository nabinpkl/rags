"""The single OpenTelemetry setup point (D15): tracer + meter + JSON logging.

Default export is JSON lines on stdout — one span or log event per line,
greppable locally, journald-friendly on the VPS, and **zero network by
construction** (tests/test_telemetry.py proves no socket is touched).
Setting ``otlp_endpoint`` in config additionally attaches OTLP/HTTP export
with no code change. Ops telemetry stays distinct from traces.db (the
product record).

Naming convention — the contract later issues attach to:

    spans       askrag.<area>.<operation>, area names are stable:
                askrag.ingest.*   (pipeline stages; .extract is the run span,
                                   .extract.pdf the per-paper span)
                askrag.db.*       (connection factories, queries)
                askrag.tool.*     (#23 agent tools, one span per invocation)
                askrag.api.*      (#30 routes; FastAPI auto-instrumentation)
                askrag.sandbox.*  (#33 container runs)
    attributes  askrag.<snake_case> (e.g. askrag.arxiv_id, askrag.duration_ms,
                askrag.tokens_in); OTel semconv keys keep their own names.
    logs        stdlib logging, logger names mirror module paths; records
                inside a span carry trace_id/span_id automatically.

Process model: only the parent process emits telemetry. Pool workers
(spawned, no tracer) measure their own wall-clock and hand timings back;
the parent emits per-item spans with those timestamps — no per-worker
tracer init, no interleaved stdout from concurrent processes.

FastAPI/httpx auto-instrumentation deliberately does not live here yet: it
needs `opentelemetry-instrumentation-fastapi`/`-httpx`, new dependencies
that #30's app.py did not add (dependency gate, docs/sdlc.md) — app.py's
lifespan calls ``init()``/``shutdown()`` only, no auto-instrumentors. Land
them, gated, the day something actually needs the trace.
"""

import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import NoOpTracerProvider, StatusCode

from askrag.config import Settings, get_settings

_SERVICE_NAME = "askrag"  # OTel resource identity (protocol fact, D15)
_LOG_HANDLER_TAG = "_askrag_telemetry_handler"


class _JsonLinesSpanExporter(SpanExporter):
    """One JSON object per finished span, written to stdout."""

    def export(self, spans: Any) -> SpanExportResult:
        for span in spans:
            sys.stdout.write(json.dumps(_span_record(span), ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        # stdout is not ours to close.
        return None


def _span_record(span: ReadableSpan) -> dict[str, Any]:
    ctx = span.get_span_context()
    # A finished span reaching the exporter always carries its context; the
    # SDK never emits a contextless span (stubs type it Optional regardless).
    assert ctx is not None
    record: dict[str, Any] = {
        "type": "span",
        "service": _SERVICE_NAME,
        "name": span.name,
        "trace_id": f"{ctx.trace_id:032x}",
        "span_id": f"{ctx.span_id:016x}",
        "start": span.start_time,
        "duration_ms": ((span.end_time or 0) - (span.start_time or 0)) / 1e6,
        # UNSET means "ended without error" in OTel; report it as OK so the
        # field is a clean OK/ERROR signal for grepping.
        "status": "ERROR" if span.status.status_code is StatusCode.ERROR else "OK",
        "attributes": dict(span.attributes or {}),
    }
    if span.parent is not None:
        record["parent_span_id"] = f"{span.parent.span_id:016x}"
    return record


class _JsonLogFormatter(logging.Formatter):
    """Structured JSON lines; trace/span ids attached when inside a span."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "type": "log",
            "service": _SERVICE_NAME,
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        ctx = trace.get_current_span().get_span_context()
        if ctx is not None and ctx.is_valid:
            payload["trace_id"] = f"{ctx.trace_id:032x}"
            payload["span_id"] = f"{ctx.span_id:016x}"
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "askrag_extra", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


@dataclass
class _TelemetryState:
    tracer_provider: TracerProvider | None
    meter_provider: MeterProvider | None
    log_handler: logging.Handler | None
    exporters: tuple[str, ...] = field(default=())


_state: _TelemetryState | None = None
_noop_tracer_provider = NoOpTracerProvider()


def init(settings: Settings | None = None, *, force: bool = False) -> None:
    """Set up telemetry once per process; every entrypoint calls this first.

    ``force=True`` tears down and rebuilds (tests, config changes); a plain
    second call is a no-op so accidental double-init cannot duplicate output.
    """
    global _state
    if _state is not None:
        if not force:
            return
        shutdown()

    settings = settings if settings is not None else get_settings()
    if not settings.telemetry_enabled:
        _state = _TelemetryState(None, None, None, exporters=())
        return

    resource = Resource.create({"service.name": _SERVICE_NAME})
    tracer_provider = TracerProvider(resource=resource)
    # Stdout is synchronous on purpose: CLI runs exit immediately after the
    # last span; a batching queue would need an explicit flush to not lose it.
    tracer_provider.add_span_processor(SimpleSpanProcessor(_JsonLinesSpanExporter()))
    exporters = ["stdout-json"]

    metric_readers = []
    if settings.otlp_endpoint:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint}/v1/traces"))
        )
        metric_readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{settings.otlp_endpoint}/v1/metrics")
            )
        )
        exporters.append("otlp")

    # Without OTLP the MeterProvider has no reader: instruments record
    # cheaply into nothing, and a collector picks them up the moment one is
    # configured — callers never branch on telemetry state.
    meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonLogFormatter())
    setattr(handler, _LOG_HANDLER_TAG, True)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    _state = _TelemetryState(tracer_provider, meter_provider, handler, tuple(exporters))


def get_tracer(name: str) -> trace.Tracer:
    if _state is None or _state.tracer_provider is None:
        return _noop_tracer_provider.get_tracer(name)
    return _state.tracer_provider.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    if _state is None or _state.meter_provider is None:
        return metrics.NoOpMeterProvider().get_meter(name)
    return _state.meter_provider.get_meter(name)


def active_exporters() -> tuple[str, ...]:
    """Which export paths init() configured — the no-egress test's seam."""
    return _state.exporters if _state is not None else ()


def force_flush() -> None:
    if _state is not None and _state.tracer_provider is not None:
        _state.tracer_provider.force_flush()


def shutdown() -> None:
    """Flush and tear down; safe to call when never initialized."""
    global _state
    if _state is None:
        return
    if _state.log_handler is not None:
        logging.getLogger().removeHandler(_state.log_handler)
    if _state.tracer_provider is not None:
        _state.tracer_provider.shutdown()
    if _state.meter_provider is not None:
        _state.meter_provider.shutdown()
    _state = None
