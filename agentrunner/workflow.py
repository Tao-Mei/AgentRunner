"""Validate and expand a local workflow before it can be accepted."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

import yaml

from .cli import preflight
from .environment import validate as validate_environment


STEP_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
ITEM_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
RESOURCE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


def _names(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) and STEP_ID.fullmatch(x) for x in value):
        raise ValueError(f"{field} must be a list of step IDs")
    return value


def _resource_names(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) and RESOURCE_ID.fullmatch(x) for x in value):
        raise ValueError(f"{field} must be a list of resource IDs")
    return value


def _command(raw: dict[str, Any], item: str | None, cwd: str) -> list[str]:
    if ("command" in raw) == ("run" in raw):
        raise ValueError("Each step needs exactly one of command or run")
    source = raw.get("command", raw.get("run"))
    if isinstance(source, list):
        if not source or not all(isinstance(part, str) and part for part in source):
            raise ValueError("command must be a nonempty string array")
        parts = source
    elif isinstance(source, str) and source.strip():
        if raw.get("shell") is True:
            parts = ["pwsh", "-NoProfile", "-Command", source] if os.name == "nt" else ["/bin/sh", "-c", source]
        else:
            parts = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part
                     for part in shlex.split(source, posix=os.name != "nt")]
    else:
        raise ValueError("run must be a nonempty string or command must be an array")
    if item is not None:
        parts = [part.replace("{{ item }}", item).replace("{{item}}", item) for part in parts]
    if any("{{" in part or "}}" in part for part in parts):
        raise ValueError("Unsupported or unresolved template variable")
    preflight(parts, cwd, None)
    return parts


def _step(raw: dict[str, Any], base: str, item: str | None, cwd: str, declared_resources: set[str]) -> dict[str, Any]:
    step_id = f"{base}[{item}]" if item is not None else base
    retry = raw.get("retry", {})
    if not isinstance(retry, dict):
        raise ValueError(f"{base}: retry must be a mapping")
    attempts = retry.get("max_attempts", 1)
    delay = retry.get("delay_seconds", 0)
    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 10:
        raise ValueError(f"{base}: retry.max_attempts must be 1..10")
    if not isinstance(delay, (int, float)) or not 0 <= delay <= 3600:
        raise ValueError(f"{base}: invalid retry delay")
    if attempts > 1 and raw.get("safe_to_retry") is not True:
        raise ValueError(f"{base}: retries require safe_to_retry: true")
    timeout = raw.get("timeout_seconds")
    if timeout is not None and (not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0):
        raise ValueError(f"{base}: timeout_seconds must be positive")
    resources = _resource_names(raw.get("resources"), f"{base}.resources")
    if len(set(resources)) != len(resources) or not set(resources) <= declared_resources:
        raise ValueError(f"{base}: duplicate or undeclared resource")
    artifacts = raw.get("artifacts", [])
    if not isinstance(artifacts, list) or not all(isinstance(x, str) and x for x in artifacts):
        raise ValueError(f"{base}: artifacts must be a list of patterns")
    if item is not None:
        artifacts = [pattern.replace("{{ item }}", item).replace("{{item}}", item) for pattern in artifacts]
    return {
        "id": step_id, "base": base, "item": item, "command": _command(raw, item, cwd),
        "resources": resources, "max_attempts": attempts, "retry_delay_seconds": float(delay),
        "safe_to_retry": raw.get("safe_to_retry") is True,
        "timeout_seconds": float(timeout) if timeout is not None else None,
        "artifacts": artifacts, "concurrency": raw.get("concurrency"),
        "pass_env": validate_environment(raw.get("pass_env")),
        "deps": [],
    }


def load(path: str | Path, cwd: str | None = None) -> dict[str, Any]:
    workflow_path = Path(path).resolve()
    if not workflow_path.is_file() or workflow_path.stat().st_size > 1_000_000:
        raise ValueError("Workflow file is missing or exceeds 1 MB")
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("Workflow requires version: 1")
    directory = Path(cwd or workflow_path.parent).resolve()
    if not directory.is_dir():
        raise ValueError(f"Working directory does not exist: {directory}")
    raw_steps = document.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("Workflow needs a nonempty steps list")
    raw_resources = document.get("resources", [])
    if isinstance(raw_resources, dict):
        raw_resources = [{"id": key, "capacity": value} for key, value in raw_resources.items()]
    if not isinstance(raw_resources, list):
        raise ValueError("resources must be a list or mapping")
    capacities: dict[str, int] = {}
    for resource in raw_resources:
        if not isinstance(resource, dict) or not isinstance(resource.get("id"), str) or not RESOURCE_ID.fullmatch(resource["id"]):
            raise ValueError("Invalid resource ID")
        if resource.get("billable") is True:
            raise ValueError(f"Billable resource {resource['id']} is outside local v0.1")
        capacity = resource.get("capacity", 1)
        if not isinstance(capacity, int) or isinstance(capacity, bool) or not 1 <= capacity <= 64:
            raise ValueError("Resource capacity must be 1..64")
        if resource["id"] in capacities:
            raise ValueError(f"Duplicate resource: {resource['id']}")
        capacities[resource["id"]] = capacity
    by_base: dict[str, list[dict[str, Any]]] = {}
    raw_by_base: dict[str, dict[str, Any]] = {}
    expanded: list[dict[str, Any]] = []
    for raw in raw_steps:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not STEP_ID.fullmatch(raw["id"]):
            raise ValueError("Each step requires a valid id")
        base = raw["id"]
        if base in by_base:
            raise ValueError(f"Duplicate step: {base}")
        foreach = raw.get("foreach")
        if foreach is None:
            items: list[str | None] = [None]
        else:
            if not isinstance(foreach, list) or not foreach:
                raise ValueError(f"{base}: foreach must be a nonempty list")
            items = [str(item) for item in foreach]
            if len(set(items)) != len(items) or not all(ITEM_ID.fullmatch(item) for item in items):
                raise ValueError(f"{base}: foreach items must be unique safe identifiers")
        concurrency = raw.get("concurrency")
        if concurrency is not None and (not isinstance(concurrency, int) or isinstance(concurrency, bool) or concurrency < 1):
            raise ValueError(f"{base}: concurrency must be positive")
        rows = [_step(raw, base, item, str(directory), set(capacities)) for item in items]
        by_base[base] = rows
        raw_by_base[base] = raw
        expanded.extend(rows)
    for step in expanded:
        raw = raw_by_base[step["base"]]
        dependencies: list[str] = []
        for parent in _names(raw.get("after"), f"{step['base']}.after") + _names(raw.get("after_all"), f"{step['base']}.after_all"):
            if parent not in by_base:
                raise ValueError(f"{step['id']}: unknown dependency {parent}")
            dependencies.extend(row["id"] for row in by_base[parent])
        each = raw.get("after_each")
        if each is not None:
            if not isinstance(each, dict) or not isinstance(each.get("step"), str):
                raise ValueError(f"{step['id']}: after_each needs step")
            parent = each["step"]
            if step["item"] is None or parent not in by_base:
                raise ValueError(f"{step['id']}: after_each requires matching foreach steps")
            matches = [row for row in by_base[parent] if row["item"] == step["item"]]
            if len(matches) != 1:
                raise ValueError(f"{step['id']}: after_each item has no parent")
            dependencies.append(matches[0]["id"])
        if step["id"] in dependencies:
            raise ValueError(f"{step['id']}: self dependency")
        step["deps"] = list(dict.fromkeys(dependencies))
    by_id = {step["id"]: step for step in expanded}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError("Workflow dependency cycle")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in by_id[step_id]["deps"]:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in by_id:
        visit(step_id)
    raw_finalizers = document.get("finalizers", [])
    if not isinstance(raw_finalizers, list):
        raise ValueError("finalizers must be a list")
    finalizers: list[dict[str, Any]] = []
    for raw in raw_finalizers:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not STEP_ID.fullmatch(raw["id"]):
            raise ValueError("Each finalizer needs a valid id")
        if raw["id"] in by_base or any(row["base"] == raw["id"] for row in finalizers):
            raise ValueError("Duplicate finalizer ID")
        finalizers.append(_step(raw, raw["id"], None, str(directory), set(capacities)))
    max_parallel = document.get("max_parallel", 4)
    if not isinstance(max_parallel, int) or isinstance(max_parallel, bool) or not 1 <= max_parallel <= 64:
        raise ValueError("max_parallel must be 1..64")
    return {
        "version": 1, "name": str(document.get("job", {}).get("name", workflow_path.stem)) if isinstance(document.get("job", {}), dict) else workflow_path.stem,
        "cwd": str(directory), "max_parallel": max_parallel, "resources": capacities,
        "steps": expanded, "finalizers": finalizers,
    }
