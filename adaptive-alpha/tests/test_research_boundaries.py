"""Adversarial inputs, numerical bounds and reproducibility contracts."""

import ast
import copy
from datetime import timedelta

import numpy as np
import polars as pl
import pytest
from test_autonomous import SOURCE, candidate, dataset
from test_evaluation import spec

from adaptive_alpha.agents.baseline import TemplateEngineer
from adaptive_alpha.agents.contracts import EngineeringAgent
from adaptive_alpha.data import synthetic_daily, validate_pit
from adaptive_alpha.domain import digest
from adaptive_alpha.research.backtest import backtest
from adaptive_alpha.research.datasets import import_dataset, timestamp
from adaptive_alpha.research.portfolio import allocate, pareto_population
from adaptive_alpha.research.program import Program
from adaptive_alpha.research.reproduction import provenance, reproduce
from adaptive_alpha.research.roles import NoveltyAgent
from adaptive_alpha.research.walk_forward import rolling_selection
from adaptive_alpha.risk.engine import monitor_account
from adaptive_alpha.store import Store


def test_reference_engineer_exposes_supported_and_unsupported_operations():
    engineer: EngineeringAgent = TemplateEngineer()
    assert engineer.propose_implementation(spec())["kind"] == "trusted-template"
    assert engineer.fix_tests("artifact")["status"] == "unsupported"
    assert engineer.create_tool("Read files")["status"] == "unsupported"
    assert "hidden" in engineer.analyze_failure({})


@pytest.mark.parametrize(
    "source,error",
    [
        (" " * 16385, "PROGRAM_TOO_LARGE"),
        ("def signal(", "PROGRAM_SYNTAX"),
        ("1", "ONE_SIGNAL_FUNCTION_REQUIRED"),
        (
            "def signal(history):\n    def nested(history):\n        return 0\n    return 0",
            "NESTED_FUNCTION_FORBIDDEN",
        ),
        ("def signal(history):\n    _secret = 0\n    return 0", "INVALID_NAME"),
        ("def signal(history):\n    x = 'text'\n    return 0", "NUMERIC_CONSTANT_REQUIRED"),
        ("def signal(history):\n    history = 0\n    return 0", "LOCAL_ASSIGNMENT_REQUIRED"),
        ("def signal(history):\n    x = y = 1\n    return 0", "LOCAL_ASSIGNMENT_REQUIRED"),
    ],
)
def test_program_validation_rejects_unsupported_structure(source, error):
    with pytest.raises(ValueError, match=error):
        Program(source)


@pytest.mark.parametrize(
    "source,error",
    [
        ("return", "SIGNAL_REQUIRED"),
        ("1", "UNSUPPORTED_STATEMENT"),
        ("return (1, 2) + (3, 4)", "NUMERIC_ARITHMETIC_ONLY"),
        ("return 1000000000000 * 1000000000000", "NUMERIC_BOUND"),
        ("return history[100]", "PROGRAM_RUNTIME"),
        ("return 1 / 0", "PROGRAM_RUNTIME"),
        ("return True", "SIGNAL_MUST_BE_FRACTION"),
        ("x = 1", "SIGNAL_MUST_BE_FRACTION"),
    ],
)
def test_program_runtime_rejects_invalid_signal(source, error):
    with pytest.raises(ValueError, match=error):
        Program("def signal(history):\n    " + source).signal([1.0])


def test_program_arithmetic_short_circuit_and_history_bounds():
    assert Program("def signal(history):\n    return (history[-1] + 1)/100").signal([4]) == 0.05
    program = Program(
        "def signal(history):\n    x = +history[-1] * 2 - 1\n    if x < 0:\n        x = 0\n    if not (0 < x < 10) or (x == 1 and x != 2):\n        return 0.1\n    return x/100\n"
    )
    assert program.signal([1]) == 0.1
    assert program.signal([2]) == 0.03
    assert program.signal([-1]) == 0.1
    for history in ([], [1.0] * 10001):
        with pytest.raises(ValueError, match="HISTORY_BOUND"):
            program.signal(history)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (
            [ast.Return(value=ast.Call(func=ast.Constant(value=0), args=[], keywords=[]))],
            "FUNCTION_REQUIRED",
        ),
        (
            [ast.Assign(targets=[ast.Constant(value=0)], value=ast.Constant(value=1))],
            "LOCAL_REQUIRED",
        ),
        ([ast.Return(value=ast.Set(elts=[]))], "UNSUPPORTED_EXPRESSION"),
        (
            [ast.Assign(targets=[ast.Name(id="x")], value=ast.Constant(value=1))] * 2050,
            "PROGRAM_BUDGET",
        ),
    ],
)
def test_interpreter_runtime_defenses_reject_corrupted_prevalidated_ast(mutation, error):
    program = Program("def signal(history):\n    return 0")
    program.body = mutation
    with pytest.raises(ValueError, match=error):
        program.signal([1.0])


def test_syntax_failure_is_preserved_by_novelty_diagnostics():
    broken = candidate("e").model_copy(update={"source": "def signal("})
    assert NoveltyAgent().compare(broken, [])["program_ast_hash"] is None


def test_backtest_timeout_and_missing_timezone():
    with pytest.raises(ValueError, match="COMPUTE_BUDGET_EXHAUSTED"):
        backtest(SOURCE, dataset(), -1)
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        timestamp("2020-01-01")


def test_snapshot_parquet_and_reproduction_detect_tampering(settings, tmp_path):
    store = Store(settings.database_url, artifact_dir=tmp_path / "artifacts")
    store.initialize()
    data = dataset()
    manifest = import_dataset(store, data, "operator")
    assert (tmp_path / "artifacts" / manifest["parquet"]["id"]).read_bytes().startswith(b"PAR1")
    with store.transaction() as conn:
        stored = store.get(conn, manifest["id"], "dataset")
    bundle = {
        "dataset": stored,
        "candidate": [
            {"id": "c", "source": SOURCE, "source_hash": digest(SOURCE), "provenance": provenance()}
        ],
        "candidate-result": [
            {"id": "invalid", "status": "INVALID"},
            {"id": "c", "public": backtest(SOURCE, data)},
        ],
    }
    assert reproduce(bundle) == [{"candidate_id": "c", "exact": True}]
    for section, key, value, error in [
        ("candidate", "source_hash", "bad", "SOURCE_HASH_MISMATCH"),
        ("candidate", "provenance", {}, "PINNED_RUNTIME_REQUIRED"),
    ]:
        changed = copy.deepcopy(bundle)
        changed[section][0][key] = value
        with pytest.raises(ValueError, match=error):
            reproduce(changed)
    changed = copy.deepcopy(bundle)
    changed["dataset"]["manifest"]["content_hash"] = "bad"
    with pytest.raises(ValueError, match="DATASET_HASH_MISMATCH"):
        reproduce(changed)


def test_allocator_rejects_misaligned_data_and_reports_zero_risk():
    assert allocate([])["cash"] == 1

    def result(identity, returns):
        return {"id": identity, "status": "PASS", "public": {"returns": returns}}

    assert allocate([result("a", [0] * 100)])["reason"] == "ZERO_VARIANCE"
    with pytest.raises(ValueError, match="ALIGNED_DATASET_REQUIRED"):
        allocate([result("a", [0, 1]), result("b", [0, 1, 2])])
    values = [
        {
            "id": str(i),
            "status": "PASS",
            "public": {"metrics": {"return": r, "max_drawdown": d, "turnover": t}},
        }
        for i, (r, d, t) in enumerate([(0.1, 0.05, 2), (0.2, 0.05, 1), (0.3, 0.2, 3)])
    ]
    population = {r["id"]: r["pareto_front"] for r in pareto_population(values)}
    assert population == {"0": False, "1": True, "2": True}


def test_walk_forward_charges_actual_switches_and_validates_inputs():
    matrix = np.tile([0.001, -0.001], (200, 1))
    weights = np.tile([0.1, 0.2], (200, 1))
    outcome = rolling_selection(matrix, weights=weights)
    assert outcome["switching_costs_included"]
    assert outcome["returns"][0] == pytest.approx(0.001 - 0.1 * 10 / 10000)
    assert outcome["returns"][1] == 0.001
    for value, kwargs, error in [
        (matrix[:, 0], {}, "FINITE_VARIANT_MATRIX_REQUIRED"),
        (matrix, {"cost_bps": -1}, "FINITE_NONNEGATIVE_COST_REQUIRED"),
        (matrix[:100], {}, "WALK_FORWARD_SAMPLE_OR_PURGE"),
        (matrix, {"weights": weights[:10]}, "ALIGNED_POSITION_MATRIX_REQUIRED"),
    ]:
        with pytest.raises(ValueError, match=error):
            rolling_selection(value, **kwargs)


def test_held_risk_rejects_invalid_prices_and_insolvency():
    account = {"cash": 0, "positions": {"SPY": 1}, "high_watermark": 100, "day_start_nav": 100}
    assert monitor_account(account, {}, {})["breaches"] == ["valid_prices"]
    account["cash"] = -200
    assert monitor_account(account, {"SPY": 100}, {})["breaches"] == ["solvency"]


def test_point_in_time_schema_and_ingestion_failures():
    frame = synthetic_daily(1)
    for broken in (
        frame.drop("close"),
        frame.with_columns(pl.lit(None).alias("close")),
        frame.with_columns((pl.col("event_time") - timedelta(days=1)).alias("ingestion_time")),
    ):
        with pytest.raises(ValueError):
            validate_pit(broken)


def test_evaluation_rejects_invalid_returns_and_universe_alignment():
    from adaptive_alpha.evaluation.engine import evaluate, metrics

    for vector in (np.array([]), np.array([float("nan")]), np.array([-1.0])):
        with pytest.raises(ValueError, match="INVALID_RETURNS"):
            metrics(vector, np.zeros(len(vector)))
    frame = synthetic_daily(42)
    for universe in ((), ("SPY", "SPY")):
        with pytest.raises(ValueError, match="INVALID_UNIVERSE"):
            evaluate(frame, spec(universe=universe))
    missing_date = frame.filter(
        ~((pl.col("symbol") == "QQQ") & (pl.col("event_time") == frame["event_time"][0]))
    )
    with pytest.raises(ValueError, match="UNALIGNED_UNIVERSE"):
        evaluate(missing_date, spec(universe=("SPY", "QQQ")))
