# run_chunked_batch.py

Chunked batch runner that launches `simulate_with_logs.run()` repeatedly and merges the resulting game logs into a single aggregate output.

## v7.61 forensic patch notes
- Merge now backfills missing `chunk_id` from directory names.
- Aggregate outputs always expose globally unique `game_id` and preserve `chunk_game_id`.
