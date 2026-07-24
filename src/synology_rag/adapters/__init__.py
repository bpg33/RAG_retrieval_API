"""Adapters: concrete, read-only implementations of the domain ports.

Each adapter exposes read operations only. There are deliberately no upsert,
delete, or collection-management methods anywhere in this package - read-only
is enforced by absence of capability, not by runtime checks alone.
"""
