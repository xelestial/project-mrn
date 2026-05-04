# test_board_layout_creator.py

Covers JSON full board layout loading and CSV tile layout loading with sidecar metadata JSON.

The tests resolve fixture files from the module directory so they remain stable when pytest runs from the repository root.
Bootstrap note: tests pin the engine directory on import so runtime modules resolve consistently.
