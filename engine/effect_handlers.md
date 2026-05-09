# effect_handlers.py

Default effect handlers registered by `GameEngine`.

Handlers keep rule effects behind event boundaries so the engine can emit semantic events while modules own execution order and checkpointing.

## Current Responsibilities

- marker flip resolution
- weather and end-condition effects
- purchase, rent, force-sale, takeover, and token placement helpers
- LAP and start reward allocation resolution
- fortune card action production
- trick tile-rent modifier production
- semantic/action log enrichment

## Runtime Rule

Handlers may produce module actions or mutate within the active module boundary. They must not create hidden turn restarts, frontend-only prompts, or uncatalogued action types.
