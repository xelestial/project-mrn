# test_board_layout_creator.py

Covers JSON full board layout loading and CSV tile layout loading with sidecar metadata JSON.

The tests resolve fixture files from the module directory so they remain stable when pytest runs from the repository root.
Bootstrap note: tests pin their own package directory on import so GPT and CLAUDE suites can run together without cross-package module reuse.
