"""Compatibility adapter hooks for legacy pending actions.

This file is intentionally small in the first migration slice.  Legacy
pending actions still own gameplay order until module-runner flags are enabled;
adapter functions added here must remain read-only for legacy sessions.
"""
