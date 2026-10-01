"""Account for every collected test. This is diagnostic, not execution authentication."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict


def reconcile(collection, collection_exit_code, junit, execution, *, source_unchanged):
    """Use captured bytes, not mutable paths or pytest's aggregate pass count."""
    lines = collection.decode("utf-8").splitlines()
    nodes = [line for line in lines if re.fullmatch(r"tests/[^\n]+\.py::[^\n]+", line)]
    totals = [
        int(match.group(1))
        for line in lines
        if (match := re.fullmatch(r"(\d+) tests? collected in .+", line.strip()))
    ]
    valid_collection = (
        collection_exit_code == 0
        and bool(nodes)
        and len(nodes) == len(set(nodes))
        and totals == [len(nodes)]
    )
    identities = defaultdict(list)
    for node in nodes:
        filename, rest = node.split("::", 1)
        prefix, bracket, parameters = rest.partition("[")
        parts = prefix.split("::")
        classname = filename.removesuffix(".py").replace("/", ".")
        if len(parts) > 1:
            classname += "." + ".".join(parts[:-1])
        identities[(classname, parts[-1] + bracket + parameters)].append(node)
    rows, seen, errors = [], Counter(), []
    try:
        tree = ET.fromstring(junit)
        if tree.tag not in ("testsuite", "testsuites"):
            raise ValueError("JUnit root is not a test suite")
        for case in tree.iter("testcase"):
            key = (case.get("classname"), case.get("name"))
            matches = identities.get(key, [])
            if len(matches) == 1:
                seen.update(matches)
            outcomes = [child for child in case if child.tag in ("failure", "error", "skipped")]
            status = "passed"
            if outcomes:
                status = outcomes[0].tag
                if status == "skipped" and outcomes[0].get("type") == "pytest.xfail":
                    status = "xfailed"
            if len(outcomes) > 1:
                errors.append("multiple outcomes in one JUnit testcase")
            rows.append({"identity": key, "nodes": matches, "status": status})
    except (ET.ParseError, ValueError) as error:
        errors.append(str(error))
    missing = sorted(set(nodes) - set(seen))
    duplicates = {node: count for node, count in seen.items() if count != 1}
    unmatched = [row for row in rows if len(row["nodes"]) != 1]
    complete = valid_collection and not (missing or duplicates or unmatched or errors)
    failure_free = (
        complete
        and execution.get("status") == "PASSED"
        and execution.get("exit_code") == 0
        and execution.get("child_exit_code") == 0
        and not execution.get("timed_out", False)
        and not execution.get("interrupted", False)
        and source_unchanged is True
        and all(row["status"] in ("passed", "skipped", "xfailed") for row in rows)
    )
    return {
        "scope": "COLLECTED_TEST_ACCOUNTING_NOT_AUTHENTICATED_OR_SCIENTIFIC_ACCEPTANCE",
        "collection_sha256": hashlib.sha256(collection).hexdigest(),
        "junit_sha256": hashlib.sha256(junit).hexdigest(),
        "collection_valid": valid_collection,
        "collected_count": len(nodes),
        "junit_record_count": len(rows),
        "outcomes": dict(Counter(row["status"] for row in rows)),
        "missing_nodes": missing,
        "multiple_records": duplicates,
        "unmatched_or_ambiguous_records": unmatched,
        "errors": errors,
        "source_unchanged": source_unchanged,
        "all_nodes_have_one_terminal_result": complete,
        "ordinary_regression_passed": failure_free,
        "strict_all_nodes_passed": failure_free and all(row["status"] == "passed" for row in rows),
    }
