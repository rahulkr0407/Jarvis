"""Security package: allowlist, policy, and approval primitives.

This package is the guardrail layer. It contains no operating-system access and
no shell execution. Its only job is to decide *whether* an action may be
proposed and *whether* an approval is still valid.
"""
