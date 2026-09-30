"""Bounded, experimental local Codex goal controls; no model turns are started."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess

from . import codex_command


IDENTITY = ("threadId", "objective", "createdAt", "tokenBudget")
REVISION = (*IDENTITY, "status", "updatedAt")


def matches(first: dict, second: dict, *, revision: bool = True) -> bool:
    return all(first.get(key) == second.get(key) for key in (REVISION if revision else IDENTITY))


async def _exchange(thread_id: str, status: str | None, expected: dict | None) -> dict | None:
    process = await asyncio.create_subprocess_exec(
        codex_command.resolve(), "app-server", "--stdio", stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    async def send(message: dict) -> None:
        process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        await process.stdin.drain()

    async def request(number: int, method: str, params: dict) -> dict:
        await send({"id": number, "method": method, "params": params})
        while True:
            line = await process.stdout.readline()
            if not line:
                raise RuntimeError("Codex goal protocol closed before responding")
            response = json.loads(line)
            if response.get("id") == number:
                if "error" in response:
                    raise RuntimeError(f"Codex goal method unavailable: {method}")
                return response["result"]

    try:
        await asyncio.wait_for(request(1, "initialize", {
            "clientInfo": {"name": "agentrunner_goal_handoff", "version": "0.2"},
            "capabilities": {"experimentalApi": True},
        }), 8)
        await send({"method": "initialized"})
        goal = (await asyncio.wait_for(request(2, "thread/goal/get", {"threadId": thread_id}), 8)).get("goal")
        if status is None:
            return goal
        if goal is None or expected is None or not matches(goal, expected):
            raise ValueError("Goal changed; refusing status update")
        changed = (await asyncio.wait_for(request(3, "thread/goal/set", {
            "threadId": thread_id, "status": status,
        }), 8))["goal"]
        if not matches(changed, goal, revision=False) or changed["status"] != status:
            raise RuntimeError("Goal update outcome is unconfirmed")
        return changed
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        await asyncio.wait_for(process.wait(), 5)


def exchange(thread_id: str, status: str | None = None, expected: dict | None = None) -> dict | None:
    if status not in {None, "active", "paused"}:
        raise ValueError("Unsupported goal status")
    return asyncio.run(_exchange(thread_id, status, expected))
