"""Strict parsing and validation of model output.

Model output is **untrusted**. This module is the hard gate between "text a model
produced" and "a proposal the assistant would consider":

* The response must be a JSON object with an exact, known ``type``.
* Extra keys, wrong types, and oversized values are rejected.
* A proposed ``action.name`` must be in the policy allowlist (registered intents
  only). Anything else raises :class:`UnknownActionError`.
* A proposed action's arguments are re-validated with the *same* validators the
  rule-based router uses, so the model cannot introduce a shape a human could
  not type.

Nothing here executes anything. It returns a :class:`ModelAnswer` or a
:class:`ModelAction` (a *candidate*), which the assistant still routes through
the normal policy and approval gate.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from actions.open_url import normalize_and_validate_url
from ai.errors import InvalidModelOutputError, UnknownActionError
from config import settings
from core.intents import (
    IntentName,
    resolve_safe_root,
    validate_app_target,
    validate_folder_name,
    validate_search_query,
)

#: Largest argument string we will accept from a model.
_MAX_ARG_CHARS = 2000

#: Exact key sets allowed for each action's arguments.
_ALLOWED_ARG_KEYS: dict[str, frozenset[str]] = {
    IntentName.OPEN_APPLICATION.value: frozenset({"target"}),
    IntentName.OPEN_URL.value: frozenset({"url"}),
    IntentName.LIST_DIRECTORY.value: frozenset({"location"}),
    IntentName.CREATE_FOLDER.value: frozenset({"name", "location"}),
    IntentName.OPEN_FILE.value: frozenset({"name", "location", "path"}),
    IntentName.TELL_TIME.value: frozenset(),
    "set_volume": frozenset({"level"}),
    IntentName.SEARCH_WEB.value: frozenset({"query"}),
}


@dataclass(frozen=True)
class ModelAnswer:
    """A conversational answer from the model."""

    text: str


@dataclass(frozen=True)
class ModelAction:
    """A validated candidate action proposed by the model (not executed)."""

    action_name: str
    arguments: Mapping[str, object]


ParsedModelOutput = ModelAnswer | ModelAction


def _as_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _reject(message: str) -> InvalidModelOutputError:
    return InvalidModelOutputError(message)


class ModelOutputValidator:
    """Validates model output against the allowlist and the argument rules."""

    def __init__(
        self,
        *,
        allowed_actions: Iterable[str],
        application_allowlist: Mapping[str, object] | Iterable[str],
        safe_extensions: Iterable[str],
        max_output_chars: int = settings.AI_MAX_OUTPUT_CHARS,
    ) -> None:
        self._allowed = frozenset(allowed_actions)
        names = (
            application_allowlist.keys()
            if isinstance(application_allowlist, Mapping)
            else application_allowlist
        )
        self._apps = frozenset(str(name).lower() for name in names)
        self._extensions = frozenset(ext.lower() for ext in safe_extensions)
        self._max_output_chars = max_output_chars

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def parse(self, raw_text: str) -> ParsedModelOutput:
        """Validate ``raw_text`` and return a parsed answer or candidate action."""
        payload = self._load_json(raw_text)
        kind = _as_text(payload.get("type"))
        if kind == "answer":
            return self._parse_answer(payload)
        if kind == "propose_action":
            return self._parse_action(payload)
        raise _reject("Model output must be an 'answer' or a 'propose_action'.")

    # ------------------------------------------------------------------ #
    # JSON loading
    # ------------------------------------------------------------------ #
    def _load_json(self, raw_text: str) -> Mapping[str, object]:
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise _reject("The model returned an empty response.")
        text = raw_text.strip()
        # Tolerate a single fenced code block, which some models add.
        if text.startswith("```"):
            text = text.split("\n", 1)[-1] if "\n" in text else ""
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise _reject("The model did not return valid JSON.") from exc
        if not isinstance(payload, Mapping):
            raise _reject("Model output must be a JSON object.")
        return payload

    # ------------------------------------------------------------------ #
    # Answer
    # ------------------------------------------------------------------ #
    def _parse_answer(self, payload: Mapping[str, object]) -> ModelAnswer:
        extra = set(payload) - {"type", "text"}
        if extra:
            raise _reject(f"Unexpected fields in answer: {sorted(extra)}.")
        text = _as_text(payload.get("text"))
        if text is None or not text.strip():
            raise _reject("An answer must include non-empty 'text'.")
        if len(text) > self._max_output_chars:
            raise _reject("The answer was too long.")
        return ModelAnswer(text.strip())

    # ------------------------------------------------------------------ #
    # Action
    # ------------------------------------------------------------------ #
    def _parse_action(self, payload: Mapping[str, object]) -> ModelAction:
        extra = set(payload) - {"type", "action"}
        if extra:
            raise _reject(f"Unexpected fields in proposal: {sorted(extra)}.")
        action = payload.get("action")
        if not isinstance(action, Mapping):
            raise _reject("A proposal must contain an 'action' object.")
        action_extra = set(action) - {"name", "arguments"}
        if action_extra:
            raise _reject(
                f"Unexpected fields in action: {sorted(action_extra)}."
            )

        name = _as_text(action.get("name"))
        if not name:
            raise _reject("A proposed action must have a name.")
        if name not in self._allowed:
            raise UnknownActionError(
                f"Action '{name}' is not in the allowlist."
            )

        arguments = action.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            raise _reject("Action arguments must be an object.")

        normalized = self._validate_arguments(name, arguments)
        return ModelAction(name, normalized)

    def _validate_arguments(
        self, name: str, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        allowed_keys = _ALLOWED_ARG_KEYS.get(name, frozenset())
        extra = set(arguments) - set(allowed_keys)
        if extra:
            raise _reject(f"Unexpected argument(s): {sorted(extra)}.")
        for value in arguments.values():
            if isinstance(value, str) and len(value) > _MAX_ARG_CHARS:
                raise _reject("An argument value was too long.")
            if isinstance(value, (dict, list)):
                raise _reject("Argument values must be simple scalars.")

        validator = getattr(self, f"_arg_{name}", None)
        if validator is None:
            # An allowlisted action with no argument rules must take none.
            if arguments:
                raise _reject(f"Action '{name}' takes no arguments.")
            return {}
        return validator(arguments)

    # ------------------------------------------------------------------ #
    # Per-action argument validators (mirror the rule-based router)
    # ------------------------------------------------------------------ #
    def _arg_open_application(self, args: Mapping[str, object]) -> dict[str, object]:
        target = _as_text(args.get("target"))
        safe = validate_app_target(target or "")
        if safe is None:
            raise _reject("That application name is not allowed.")
        key = safe[:-4].lower() if safe.lower().endswith(".exe") else safe.lower()
        if key not in self._apps:
            raise _reject(f"Application '{safe}' is not in the allowlist.")
        return {"target": safe}

    def _arg_open_url(self, args: Mapping[str, object]) -> dict[str, object]:
        url = _as_text(args.get("url"))
        if url is None:
            raise _reject("A URL is required.")
        try:
            safe = normalize_and_validate_url(url)
        except Exception as exc:  # actions.open_url raises its own error type
            raise _reject(f"That URL is not allowed: {exc}") from exc
        return {"url": safe}

    def _arg_list_directory(self, args: Mapping[str, object]) -> dict[str, object]:
        return {"location": self._resolve_location(args.get("location"))}

    def _arg_create_folder(self, args: Mapping[str, object]) -> dict[str, object]:
        name = validate_folder_name(_as_text(args.get("name")) or "")
        if name is None:
            raise _reject("That folder name is not allowed.")
        return {
            "name": name,
            "location": self._resolve_location(args.get("location")),
        }

    def _arg_open_file(self, args: Mapping[str, object]) -> dict[str, object]:
        if "path" in args:
            path = _as_text(args.get("path"))
            if not path:
                raise _reject("A file path is required.")
            return {"path": path}
        name = _as_text(args.get("name"))
        if not name or "." not in name:
            raise _reject("A file name with an extension is required.")
        extension = "." + name.rsplit(".", 1)[1].lower()
        if extension not in self._extensions:
            raise _reject(f"File type '{extension}' is not allowed.")
        valid = validate_folder_name(name)
        if valid is None:
            raise _reject("That file name is not allowed.")
        return {
            "name": valid,
            "location": self._resolve_location(args.get("location")),
        }

    def _arg_set_volume(self, args: Mapping[str, object]) -> dict[str, object]:
        level = args.get("level")
        if isinstance(level, bool) or not isinstance(level, (int, float)):
            raise _reject("Volume must be a number.")
        return {"level": max(0, min(100, int(level)))}

    def _arg_search_web(self, args: Mapping[str, object]) -> dict[str, object]:
        query = validate_search_query(_as_text(args.get("query")) or "")
        if query is None:
            raise _reject("A search query is required.")
        return {"query": query}

    def _resolve_location(self, value: object) -> str:
        raw = _as_text(value) if value is not None else settings.DEFAULT_SAFE_FOLDER
        resolved = resolve_safe_root(raw or settings.DEFAULT_SAFE_FOLDER)
        if resolved is None:
            raise _reject(f"'{raw}' is not a permitted location.")
        return resolved


def build_default_validator(validator: ModelOutputValidator | None = None) -> ModelOutputValidator:
    """Build a validator wired to the default policy and settings."""
    if validator is not None:
        return validator
    from security.policy import build_default_policy

    policy = build_default_policy()
    return ModelOutputValidator(
        allowed_actions=policy.allowed_actions(),
        application_allowlist=settings.APPLICATION_ALLOWLIST,
        safe_extensions=settings.SAFE_OPEN_EXTENSIONS,
    )
