# test_ruleset_loader.py

Tests external JSON ruleset loading and runtime injection.


## 0.7.60 note
Coverage now includes roundtrip loading for stage 3 sections: `economy`, `resources`, `dice`, and `special_tiles`.
Bootstrap note: tests pin the engine directory on import so runtime modules resolve consistently.

## Start reward coverage
Roundtrip tests now include `start_reward` so the game-start allocation metadata is preserved through JSON ruleset load/save.

## 2026-05-09 contract sync
Ruleset roundtrip coverage must remain aligned with server parameter manifest expectations, especially for fields exposed to frontend setup or adapter tests.
