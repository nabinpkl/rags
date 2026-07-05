"""Tests for askrag.telemetry — written before telemetry.py existed (§4d):
the OTLP-unset ⇒ zero-network guarantee is the D12-adjacent no-egress
surface, so its test comes first."""

import json
import logging
import socket

import pytest

from askrag import telemetry
from askrag.config import Settings


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[unknown-argument]


@pytest.fixture(autouse=True)
def _fresh_telemetry():
    yield
    telemetry.shutdown()


def emitted_lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


# --- the no-egress guarantee (test-first) -----------------------------------


def test_otlp_unset_attempts_zero_network(monkeypatch, capsys):
    # Any socket creation fails the test: with otlp_endpoint empty, init,
    # span emission, flush, and shutdown must never touch the network.
    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("telemetry attempted network access with OTLP unset")

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)

    telemetry.init(make_settings(otlp_endpoint=""), force=True)
    with telemetry.get_tracer("askrag.test").start_as_current_span("askrag.test.op"):
        pass
    telemetry.force_flush()
    assert telemetry.active_exporters() == ("stdout-json",)


def test_otlp_endpoint_registers_exporter_without_code_change(capsys):
    telemetry.init(make_settings(otlp_endpoint="http://localhost:4318"), force=True)
    assert telemetry.active_exporters() == ("stdout-json", "otlp")


# --- span emission: JSON lines on stdout -------------------------------------


def test_span_emits_one_json_line(capsys):
    telemetry.init(make_settings(), force=True)
    with telemetry.get_tracer("askrag.test").start_as_current_span("askrag.test.op") as span:
        span.set_attribute("askrag.count", 3)
    telemetry.force_flush()
    spans = [line for line in emitted_lines(capsys) if line["type"] == "span"]
    assert len(spans) == 1
    record = spans[0]
    assert record["name"] == "askrag.test.op"
    assert record["service"] == "askrag"
    assert len(record["trace_id"]) == 32 and len(record["span_id"]) == 16
    assert record["attributes"]["askrag.count"] == 3
    assert record["duration_ms"] >= 0
    assert record["status"] == "OK"


def test_child_span_carries_parent_ids(capsys):
    telemetry.init(make_settings(), force=True)
    tracer = telemetry.get_tracer("askrag.test")
    with tracer.start_as_current_span("askrag.test.parent"):
        with tracer.start_as_current_span("askrag.test.child"):
            pass
    telemetry.force_flush()
    spans = {line["name"]: line for line in emitted_lines(capsys) if line["type"] == "span"}
    child, parent = spans["askrag.test.child"], spans["askrag.test.parent"]
    assert child["trace_id"] == parent["trace_id"]
    assert child["parent_span_id"] == parent["span_id"]


# --- JSON logs: parseable, trace-correlated ----------------------------------


def test_log_line_is_json_with_trace_correlation(capsys):
    telemetry.init(make_settings(), force=True)
    logger = logging.getLogger("askrag.test")
    with telemetry.get_tracer("askrag.test").start_as_current_span("askrag.test.op") as span:
        span_ctx = span.get_span_context()
        logger.info("inside span", extra={"askrag_extra": {"pdfs": 7}})
    telemetry.force_flush()
    logs = [line for line in emitted_lines(capsys) if line["type"] == "log"]
    assert len(logs) == 1
    record = logs[0]
    assert record["message"] == "inside span"
    assert record["level"] == "INFO"
    assert record["logger"] == "askrag.test"
    assert record["trace_id"] == f"{span_ctx.trace_id:032x}"
    assert record["span_id"] == f"{span_ctx.span_id:016x}"
    assert record["pdfs"] == 7


def test_log_line_outside_span_has_no_trace_id(capsys):
    telemetry.init(make_settings(), force=True)
    logging.getLogger("askrag.test").warning("no span here")
    logs = [line for line in emitted_lines(capsys) if line["type"] == "log"]
    assert logs[0]["level"] == "WARNING"
    assert "trace_id" not in logs[0]


def test_log_level_config_respected(capsys):
    telemetry.init(make_settings(log_level="WARNING"), force=True)
    logging.getLogger("askrag.test").info("filtered out")
    logging.getLogger("askrag.test").warning("kept")
    messages = [line["message"] for line in emitted_lines(capsys) if line["type"] == "log"]
    assert messages == ["kept"]


# --- lifecycle ----------------------------------------------------------------


def test_init_is_idempotent_without_force(capsys):
    telemetry.init(make_settings(), force=True)
    telemetry.init(make_settings())  # second call: no duplicate pipelines
    logging.getLogger("askrag.test").warning("once")
    with telemetry.get_tracer("askrag.test").start_as_current_span("askrag.test.op"):
        pass
    telemetry.force_flush()
    lines = emitted_lines(capsys)
    assert len([line for line in lines if line["type"] == "log"]) == 1
    assert len([line for line in lines if line["type"] == "span"]) == 1


def test_telemetry_disabled_emits_nothing(capsys):
    telemetry.init(make_settings(telemetry_enabled=False), force=True)
    with telemetry.get_tracer("askrag.test").start_as_current_span("askrag.test.op"):
        logging.getLogger("askrag.test").info("quiet")
    telemetry.force_flush()
    assert telemetry.active_exporters() == ()
    assert [line for line in emitted_lines(capsys) if line["type"] == "span"] == []
