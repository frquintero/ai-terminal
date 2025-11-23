#!/usr/bin/env python3
"""
Utility script to preview the current Agent A / Agent B prompts.

Usage:
  python preview_prompts.py --agent a
  python preview_prompts.py --agent b
  python preview_prompts.py --agent b --plan-file path/to/plan.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from orchestrator.prompts import (
    get_agent_a_system_prompt,
    get_agent_a_user_message,
    get_agent_b_system_prompt,
    get_agent_b_user_message,
)
from tools import get_tool_schemas

DEFAULT_CONTEXT = (
    "Conversation:\n"
    "User: Inspect the sqlite3 database for pending automation tasks.\n"
    "Agent: Acknowledged; preparing plan.\n"
)

DEFAULT_PLAN: Dict[str, Any] = {
    "intent": "Inspect automation tasks stored in sqlite3 and summarize blockers.",
    "success_criteria": [
        "sqlite3 is executed in deterministic batch mode",
        "results list each pending task with its state",
    ],
    "todos": [
        {
            "description": "Query pending tasks via sqlite3",
            "success_criteria": [
                "Command exits 0",
                "stdout contains the tasks table as CSV",
            ],
            "policy_contract": {
                "policy_id": "sqlite3.batch",
                "executable": "sqlite3",
                "required_flags": ["-batch", "-header", "-csv"],
                "stdin_plan": "pipe_from(history/sql/pending_tasks.sql)",
                "allowed_wrappers": ["env"],
                "expected_tool_call_ref": "call-pipe-sql",
            },
            "artifacts_needed": ["history/sql/pending_tasks.sql"],
        },
        {
            "description": "Summarize task blockers",
            "success_criteria": [
                "Summary references the sqlite3 output",
                "Highlights any tasks without owners",
            ],
            "policy_contract": {
                "policy_id": "shell.pipeline",
                "executable": "python3",
                "required_flags": ["-c"],
                "stdin_plan": "input_data_ref from sqlite3 output",
                "allowed_wrappers": [],
                "expected_tool_call_ref": "call-sqlite3",
            },
        },
    ],
}


def load_plan_from_file(path: Path) -> Dict[str, Any]:
    """Load a JSON plan from disk."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        print(f"Plan file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in plan file {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def preview_agent_a(context: str) -> None:
    """Render Agent A system prompt and sample user message."""
    system_prompt = get_agent_a_system_prompt(get_tool_schemas())
    user_message = get_agent_a_user_message(context)

    print("=== Agent A System Prompt ===\n")
    print(system_prompt)
    print("\n=== Agent A User Message (sample) ===\n")
    print(user_message)


def preview_agent_b(plan: Dict[str, Any]) -> None:
    """Render Agent B system prompt and user message for the supplied plan."""
    system_prompt = get_agent_b_system_prompt(get_tool_schemas())
    user_message = get_agent_b_user_message(plan)

    print("=== Agent B System Prompt ===\n")
    print(system_prompt)
    print("\n=== Agent B User Message (plan payload) ===\n")
    print(user_message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview Agent prompts.")
    parser.add_argument(
        "--agent",
        choices=("a", "b"),
        required=True,
        help="Which agent prompt to render.",
    )
    parser.add_argument(
        "--plan-file",
        type=Path,
        help="Path to a JSON file containing a plan (Agent B only).",
    )
    parser.add_argument(
        "--context",
        help="Optional context string for Agent A's user message.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.agent == "a":
        if args.plan_file:
            print("--plan-file is ignored for Agent A previews.", file=sys.stderr)
        preview_agent_a(args.context or DEFAULT_CONTEXT)
        return

    # Agent B branch
    if args.context:
        print("--context applies only to Agent A previews.", file=sys.stderr)

    plan = DEFAULT_PLAN
    if args.plan_file:
        plan = load_plan_from_file(args.plan_file)

    preview_agent_b(plan)


if __name__ == "__main__":
    main()
