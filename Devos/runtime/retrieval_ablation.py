#!/usr/bin/env python3
"""Deterministic two-arm retrieval ablation harness for portable DevOS."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Iterable

try:
    from .build_knowledge_db import DEFAULT_DB_NAME, build
    from .db_runtime import connect_runtime, runtime_health
    from .knowledge_runtime import _branch_tier, _score, _tokens, resolve_branches
except ImportError:
    from build_knowledge_db import DEFAULT_DB_NAME, build
    from db_runtime import connect_runtime, runtime_health
    from knowledge_runtime import _branch_tier, _score, _tokens, resolve_branches

DEVOS_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_SCHEMA = "devos-retrieval-ablation/v1"
BENCHMARK_ID = "DEVOS_RETRIEVAL_ABLATION_01"
LEXICAL_V1 = "LEXICAL_V1"
FTS5_BM25_V1 = "FTS5_BM25_V1"
ARMS = (LEXICAL_V1, FTS5_BM25_V1)
FTS5_QUERY_COMPILER = "fts5-literal-or-v1"
FTS5_WEIGHTS = {"path": 3.0, "title": 6.0, "section": 4.0, "content": 1.0}
THIRD_ARM_GATE_K = 5
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _doc_key(row: dict | sqlite3.Row) -> str:
    return f"{row['path']}#{row['section']}"


def compile_fts5_query(query: str) -> str:
    """Compile the runtime's tokenization into literal FTS5 terms joined by OR."""
    tokens = [token for token in _tokens(query) if re.search(r"[A-Za-z0-9]", token)]
    if not tokens:
        raise ValueError("query must contain at least one FTS5-searchable token")
    quoted = []
    for token in tokens:
        escaped = token.replace('"', '""')
        quoted.append(f'"{escaped}"')
    return " OR ".join(quoted)


def _projection_digest(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT value FROM projection_meta WHERE key='projection_digest'"
    ).fetchone()
    if row is None or not row[0]:
        raise ValueError("knowledge projection has no projection_digest")
    return str(row[0])


def _eligible_documents(
    connection: sqlite3.Connection, branches: list[str]
) -> tuple[list[dict], list[str]]:
    requested = list(dict.fromkeys(branches))
    resolved, branch_index = resolve_branches(connection, requested)
    rows: list[dict] = []
    for row in connection.execute(
        "SELECT id,path,title,section,kind,content,content_hash "
        "FROM documents ORDER BY path,section"
    ).fetchall():
        tier, matched = _branch_tier(row["path"], requested, resolved, branch_index)
        if tier == 99:
            continue
        rows.append(
            {
                "id": int(row["id"]),
                "path": row["path"],
                "title": row["title"],
                "section": row["section"],
                "kind": row["kind"],
                "content": row["content"],
                "content_hash": row["content_hash"],
                "branch_keys": matched,
                "branch_tier": tier,
            }
        )
    return rows, resolved


def _lexical_results(
    connection: sqlite3.Connection, query: str, branches: list[str], limit: int
) -> list[dict]:
    if limit <= 0:
        return []
    tokens = _tokens(query)
    eligible, _ = _eligible_documents(connection, branches)
    rows: list[dict] = []
    for row in eligible:
        score = _score(
            query,
            tokens,
            (
                (row["title"], 6),
                (row["section"], 4),
                (row["path"], 3),
                (row["content"], 1),
            ),
        )
        if score <= 0:
            continue
        rows.append(
            {
                "path": row["path"],
                "section": row["section"],
                "kind": row["kind"],
                "content_hash": row["content_hash"],
                "branch_keys": row["branch_keys"],
                "branch_tier": row["branch_tier"],
                "score": score,
                "score_direction": "higher_is_better",
            }
        )
    rows.sort(
        key=lambda row: (
            row["branch_tier"],
            -int(row["score"]),
            row["path"],
            row["section"],
        )
    )
    return rows[:limit]


def _fts5_results(
    connection: sqlite3.Connection, query: str, branches: list[str], limit: int
) -> list[dict]:
    if limit <= 0:
        return []
    compiled = compile_fts5_query(query)
    eligible, _ = _eligible_documents(connection, branches)
    by_id = {row["id"]: row for row in eligible}

    scoped = sqlite3.connect(":memory:")
    scoped.row_factory = sqlite3.Row
    try:
        try:
            scoped.execute(
                "CREATE VIRTUAL TABLE scoped_fts USING fts5("
                "path,title,section,content,doc_id UNINDEXED)"
            )
        except sqlite3.OperationalError as exc:
            raise RuntimeError("SQLite FTS5 is required for FTS5_BM25_V1") from exc
        scoped.executemany(
            "INSERT INTO scoped_fts(path,title,section,content,doc_id) VALUES (?,?,?,?,?)",
            [
                (
                    row["path"],
                    row["title"],
                    row["section"],
                    row["content"],
                    str(row["id"]),
                )
                for row in eligible
            ],
        )
        ranked = scoped.execute(
            "SELECT doc_id,bm25(scoped_fts,?,?,?,?,?) AS bm25_score "
            "FROM scoped_fts WHERE scoped_fts MATCH ? "
            "ORDER BY bm25_score, doc_id",
            (
                FTS5_WEIGHTS["path"],
                FTS5_WEIGHTS["title"],
                FTS5_WEIGHTS["section"],
                FTS5_WEIGHTS["content"],
                0.0,
                compiled,
            ),
        ).fetchall()
    finally:
        scoped.close()

    rows: list[dict] = []
    for ranked_row in ranked:
        source = by_id[int(ranked_row["doc_id"])]
        rows.append(
            {
                "path": source["path"],
                "section": source["section"],
                "kind": source["kind"],
                "content_hash": source["content_hash"],
                "branch_keys": source["branch_keys"],
                "branch_tier": source["branch_tier"],
                "score": float(ranked_row["bm25_score"]),
                "score_direction": "lower_is_better",
            }
        )
    rows.sort(
        key=lambda row: (
            row["branch_tier"],
            float(row["score"]),
            row["path"],
            row["section"],
        )
    )
    return rows[:limit]


def retrieve(
    connection: sqlite3.Connection,
    query: str,
    branches: list[str],
    arm: str,
    *,
    limit: int = 20,
) -> list[dict]:
    if arm == LEXICAL_V1:
        return _lexical_results(connection, query, branches, limit)
    if arm == FTS5_BM25_V1:
        return _fts5_results(connection, query, branches, limit)
    raise ValueError(f"unsupported retrieval arm: {arm}")


def _validate_spec(spec: dict) -> None:
    if not isinstance(spec, dict):
        raise ValueError("benchmark spec must be a JSON object")
    if spec.get("schema") != BENCHMARK_SCHEMA:
        raise ValueError(f"unsupported benchmark schema: {spec.get('schema')!r}")
    if spec.get("benchmark_id") != BENCHMARK_ID:
        raise ValueError(f"benchmark_id must be {BENCHMARK_ID}")
    if "arms" in spec:
        raise ValueError("benchmark arms are fixed by DEVOS_RETRIEVAL_ABLATION_01")
    queries = spec.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("benchmark requires a non-empty queries array")
    seen: set[str] = set()
    for case in queries:
        if not isinstance(case, dict):
            raise ValueError("benchmark query entries must be objects")
        query_id = case.get("query_id")
        query = case.get("query")
        branches = case.get("branches")
        relevant = case.get("relevant")
        split = case.get("split")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError("query_id must be non-empty")
        if query_id in seen:
            raise ValueError(f"duplicate query_id: {query_id}")
        seen.add(query_id)
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{query_id}: query must be non-empty")
        if not isinstance(branches, list) or not branches or any(
            not isinstance(item, str) or not item.strip() for item in branches
        ):
            raise ValueError(f"{query_id}: branches must be non-empty strings")
        if not isinstance(relevant, list) or any(
            not isinstance(item, str) or not item for item in relevant
        ):
            raise ValueError(f"{query_id}: relevant must be a string array")
        if split not in {"development", "holdout"}:
            raise ValueError(f"{query_id}: split must be development or holdout")
        expect_no_results = bool(case.get("expect_no_results", False))
        if expect_no_results and relevant:
            raise ValueError(f"{query_id}: expected-empty query cannot declare relevant docs")
        if not expect_no_results and not relevant:
            raise ValueError(f"{query_id}: relevant docs required unless expect_no_results=true")


def _case_result(case: dict, rows: list[dict]) -> dict:
    keys = [_doc_key(row) for row in rows]
    relevant = list(dict.fromkeys(case["relevant"]))
    relevant_set = set(relevant)
    ranks = [idx + 1 for idx, key in enumerate(keys) if key in relevant_set]
    expected_empty = bool(case.get("expect_no_results", False))
    return {
        "query_id": case["query_id"],
        "split": case["split"],
        "query": case["query"],
        "branches": case["branches"],
        "relevant": relevant,
        "result_keys": keys,
        "first_relevant_rank": min(ranks) if ranks else None,
        "recall_at_1": (
            sum(1 for key in keys[:1] if key in relevant_set) / len(relevant)
            if relevant
            else None
        ),
        "recall_at_3": (
            sum(1 for key in keys[:3] if key in relevant_set) / len(relevant)
            if relevant
            else None
        ),
        "recall_at_5": (
            sum(1 for key in keys[:5] if key in relevant_set) / len(relevant)
            if relevant
            else None
        ),
        "reciprocal_rank": (1.0 / min(ranks)) if ranks else (None if expected_empty else 0.0),
        "expected_empty": expected_empty,
        "expected_empty_pass": (not rows) if expected_empty else None,
        "scope_leakage_count": sum(
            1 for row in rows if not row["branch_keys"] or row["branch_tier"] not in {0, 1}
        ),
        "branch_tier_violation": any(
            rows[idx]["branch_tier"] > rows[idx + 1]["branch_tier"]
            for idx in range(len(rows) - 1)
        ),
    }


def _mean(values: Iterable[float]) -> float | None:
    material = list(values)
    return (sum(material) / len(material)) if material else None


def _aggregate(cases: list[dict]) -> dict:
    judged = [case for case in cases if case["relevant"]]
    empty = [case for case in cases if case["expected_empty"]]
    return {
        "query_count": len(cases),
        "judged_query_count": len(judged),
        "recall_at_1": _mean(float(case["recall_at_1"]) for case in judged),
        "recall_at_3": _mean(float(case["recall_at_3"]) for case in judged),
        "recall_at_5": _mean(float(case["recall_at_5"]) for case in judged),
        "mrr": _mean(float(case["reciprocal_rank"]) for case in judged),
        "expected_empty_accuracy": _mean(
            1.0 if case["expected_empty_pass"] else 0.0 for case in empty
        ),
        "scope_leakage_count": sum(case["scope_leakage_count"] for case in cases),
        "branch_tier_violation_count": sum(
            1 for case in cases if case["branch_tier_violation"]
        ),
        "missed_at_5": sorted(
            case["query_id"]
            for case in judged
            if float(case["recall_at_5"]) < 1.0
        ),
    }


def _evaluate_arm(
    connection: sqlite3.Connection, spec: dict, arm: str, limit: int
) -> dict:
    cases = []
    for case in spec["queries"]:
        rows = retrieve(
            connection,
            case["query"],
            list(case["branches"]),
            arm,
            limit=limit,
        )
        cases.append(_case_result(case, rows))
    splits = {
        split: _aggregate([case for case in cases if case["split"] == split])
        for split in ("development", "holdout")
    }
    return {"arm": arm, "aggregate": _aggregate(cases), "splits": splits, "cases": cases}


def run_benchmark(
    connection: sqlite3.Connection,
    spec: dict,
    *,
    candidate_revision: str,
    limit: int = 20,
) -> dict:
    _validate_spec(spec)
    if not _SHA1_RE.fullmatch(candidate_revision):
        raise ValueError("candidate_revision must be a 40-character lowercase Git SHA")
    if limit < THIRD_ARM_GATE_K:
        raise ValueError(f"limit must be at least {THIRD_ARM_GATE_K}")

    health = runtime_health(connection)
    if not health.get("fts5"):
        raise RuntimeError("DEVOS_RETRIEVAL_ABLATION_01 requires SQLite FTS5")

    evaluations = {
        arm: _evaluate_arm(connection, spec, arm, limit)
        for arm in ARMS
    }
    lexical_misses = set(evaluations[LEXICAL_V1]["aggregate"]["missed_at_5"])
    fts_misses = set(evaluations[FTS5_BM25_V1]["aggregate"]["missed_at_5"])
    shared_misses = sorted(lexical_misses & fts_misses)

    receipt: dict[str, object] = {
        "schema": BENCHMARK_SCHEMA,
        "benchmark_id": BENCHMARK_ID,
        "candidate_revision": candidate_revision,
        "projection_digest": _projection_digest(connection),
        "benchmark_spec_digest": _digest(spec),
        "sqlite": {
            "version": sqlite3.sqlite_version,
            "source_id": connection.execute("SELECT sqlite_source_id()").fetchone()[0],
            "fts5": True,
        },
        "arms": {
            LEXICAL_V1: {
                "implementation": "knowledge_runtime._score",
                "query_tokenizer": "knowledge_runtime._tokens",
                "weights": {"title": 6, "section": 4, "path": 3, "content": 1},
                "phrase_bonus_multiplier": 4,
                "scope_policy": "resolved-branch-surfaces-before-scoring",
            },
            FTS5_BM25_V1: {
                "implementation": "sqlite-fts5-bm25",
                "query_compiler": FTS5_QUERY_COMPILER,
                "weights": dict(FTS5_WEIGHTS),
                "scope_policy": "ephemeral-scope-local-fts5",
            },
        },
        "limit": limit,
        "evaluations": evaluations,
        "third_arm_gate": {
            "top_k": THIRD_ARM_GATE_K,
            "eligible_for_research": bool(shared_misses),
            "specific_shared_recall_failures": shared_misses,
            "law": (
                "No embeddings, reranker, RRF, or other third arm is admitted unless "
                "both fixed arms miss relevant evidence on the same frozen query."
            ),
        },
        "authority_effect": "NONE",
        "promotion_state": "BENCHMARK_ONLY",
    }
    receipt["receipt_hash"] = _digest(receipt)
    return receipt


def _default_db(devos_root: Path) -> Path:
    return devos_root / "state" / DEFAULT_DB_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--devos-root", type=Path, default=DEVOS_ROOT)
    parser.add_argument("--host-root", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    devos_root = args.devos_root.resolve()
    host_root = (args.host_root or devos_root.parent).resolve()
    db_path = (args.db or _default_db(devos_root)).resolve()
    try:
        build(devos_root, host_root, db_path, fresh=args.fresh or not db_path.exists())
        spec = json.loads(args.benchmark.read_text(encoding="utf-8"))
        connection = connect_runtime(db_path)
        try:
            receipt = run_benchmark(
                connection,
                spec,
                candidate_revision=args.candidate_revision,
                limit=args.limit,
            )
        finally:
            connection.close()
        encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
