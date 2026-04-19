# test_ruleset_loader.py

Tests external JSON ruleset loading and runtime injection.


## 0.7.60 note
Coverage now includes roundtrip loading for stage 3 sections: `economy`, `resources`, `dice`, and `special_tiles`.
Bootstrap note: tests pin their own package directory on import so GPT and CLAUDE suites can run together without cross-package module reuse.
