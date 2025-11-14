"""
Typed output parsing for Agent B + ToolExecutor results.

Converts stdout/raw_stdout text into concrete Python values according to
Agent B's declared output_format (int, float, list, raw, table, json, str).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


class OutputParserError(ValueError):
    """Raised when stdout cannot be parsed into the requested type."""


class OutputParser:
    """Parse ToolExecutor stdout into structured values for narration/templates."""

    _INT_PATTERN = re.compile(r"[-+]?\d+")
    _DECIMAL_PATTERN = re.compile(r"[-+]?(?:\d+\.\d+|\d*\.\d+)")

    def parse(
        self,
        output_format: Dict[str, str],
        stdout: Optional[str],
        raw_stdout: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Parse stdout/raw_stdout according to Agent B's output_format mapping.

        Returns a tuple of:
            parsed_values: Dict[str, Any] with typed Python objects
            rendered_values: Dict[str, str] formatted strings for narration templates
        """
        if not output_format:
            return {}, {}

        parsed: Dict[str, Any] = {}
        rendered: Dict[str, str] = {}

        normalized_stdout = stdout or ""
        normalized_raw = raw_stdout if raw_stdout not in (None, "") else normalized_stdout

        for key, fmt in output_format.items():
            if not isinstance(fmt, str):
                raise OutputParserError(f"output_format for '{key}' must be a string")

            fmt_lower = fmt.strip().lower()
            if fmt_lower == "int":
                value = self._parse_int(normalized_stdout, key)
                rendered_value = str(value)
            elif fmt_lower == "float":
                value = self._parse_float(normalized_stdout, key)
                rendered_value = str(value)
            elif fmt_lower == "str":
                value = normalized_stdout.strip()
                rendered_value = value
            elif fmt_lower == "list":
                value = self._parse_list(normalized_stdout)
                rendered_value = ", ".join(value)
            elif fmt_lower in ("raw", "table"):
                value = normalized_raw
                rendered_value = value
            elif fmt_lower == "json":
                value = self._parse_json(normalized_stdout, key)
                rendered_value = json.dumps(value, ensure_ascii=False)
            else:
                raise OutputParserError(
                    f"Unsupported output_format type '{fmt}' for key '{key}'"
                )

            parsed[key] = value
            rendered[key] = rendered_value

        return parsed, rendered

    def _parse_int(self, text: str, key: str) -> int:
        match = self._INT_PATTERN.search(text.strip())
        if not match:
            raise OutputParserError(
                f"Failed to parse integer for '{key}' from output: {self._sample(text)}"
            )
        return int(match.group(0))

    def _parse_float(self, text: str, key: str) -> float:
        stripped = text.strip()
        match = self._DECIMAL_PATTERN.search(stripped)
        if match:
            return float(match.group(0))
        int_match = self._INT_PATTERN.search(stripped)
        if int_match:
            return float(int_match.group(0))
        raise OutputParserError(
            f"Failed to parse float for '{key}' from output: {self._sample(text)}"
        )

    def _parse_list(self, text: str) -> List[str]:
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]
        return lines

    def _parse_json(self, text: str, key: str) -> Any:
        payload = text.strip()
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise OutputParserError(
                f"Failed to parse json for '{key}': {exc.msg}"
            ) from exc

    def _sample(self, text: str, limit: int = 60) -> str:
        snippet = text.strip().splitlines()[0] if text.strip() else ""
        if len(snippet) > limit:
            return snippet[:limit] + "..."
        return snippet
