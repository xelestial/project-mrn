# Protocol Identity Consumer Inventory

Date: 2026-05-14

Source plan: `docs/current/planning/PLAN_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md`

This inventory exists because numeric `player_id` still has three different
meanings in the current system:

- Internal engine actor index: allowed inside engine/runtime adaptation.
- Compatibility alias: allowed at protocol/tool boundaries only while public
  identity fields are additive.
- Display/debug label input: allowed for `P1`-style labels, replay summaries,
  and audit grouping.

Do not remove numeric aliases until this inventory has no `compat alias` entries.
Removing numeric fields before that point would break known protocol consumers
instead of completing the identity migration.

## Classification

- `display`: the numeric value is used only for labels, summaries, replay rows,
  latency grouping, or audit output. It is not the public identity contract.
- `engine bridge`: the numeric value is needed to adapt a public protocol
  identity back to the current engine seat/player index.
- `compat alias`: the numeric value crosses a protocol, tool, schema, or API
  boundary for compatibility while public identity companions are introduced.
- `protocol violation`: the numeric value is being used as public identity
  without a public companion field or an explicit bridge justification.

Current `protocol violation` entries: none found.

## Consumer Inventory

| Consumer | Classification | Evidence | Removal condition |
| --- | --- | --- | --- |
| `apps/web/src/domain/stream/decisionProtocol.ts` | `compat alias` | `buildDecisionMessage()` can send a public string `player_id`, but it still carries `legacy_player_id`, numeric `missing_player_ids`, numeric `resume_tokens_by_player_id`, and numeric `prompt_instance_id` companions. | Outbound decision contracts and all receivers must accept public identity as primary and consume numeric values only from explicit legacy fields. |
| `apps/web/src/hooks/useGameStream.ts` | `compat alias` | UI decision submission passes `playerId`, `legacyPlayerId`, `publicPlayerId`, `seatId`, and `viewerId` into the decision message while duplicate-flight keys still resolve through the numeric legacy bridge. | The UI duplicate-flight key and send path must no longer require a numeric `player_id` alias when public identity companions are present. |
| `apps/web/src/headless/HeadlessGameClient.ts` | `compat alias` | Headless decisions and compact traces preserve protocol/public identity companions, but the client still routes and records decisions with the numeric player seat value for compatibility. | Headless submission, trace compaction, and identity checks must treat numeric values only as explicit legacy/debug fields. |
| `apps/web/src/headless/httpDecisionPolicy.ts` | `compat alias` | `HttpDecisionPolicyRequest` still includes numeric `player_id` and `legacy_player_id` beside `protocol_player_id`, `public_player_id`, `seat_id`, and `viewer_id`. | The policy request schema and all policy consumers must use public identity fields as the primary request identity. |
| `apps/web/src/headless/protocolReplay.ts` | `display` | Replay rows use numeric `player_id` to group observations, rewards, final rank, and historical summaries while preserving public identity companions where available. | No protocol removal blocker, but replay exports should label the field as legacy/display if public identity becomes the primary export key. |
| `apps/web/src/headless/fullStackProtocolHarness.ts` | `display` | The harness keeps joined seat numbers and latency trace `player_id` values for progress, grouping, and operator evidence. | No protocol removal blocker if harness output remains display-only or moves to public identity labels. |
| `apps/web/src/domain/selectors/streamSelectors.ts` | `display` | Stream selectors derive actor labels, player cards, board ownership labels, and prompt actor labels from numeric player fields. | No protocol removal blocker if display labels keep using `seat_index`/`player_label` or explicit legacy fields. |
| `apps/web/src/domain/selectors/promptSelectors.ts` | `engine bridge` | Active prompt selection accepts a protocol `player_id`, but still requires a numeric `legacy_player_id` bridge before building the prompt view model. | The prompt selector/adapter must receive a public identity that can be resolved to the engine seat without requiring the public field itself to be numeric. |
| `packages/runtime-contracts/ws/schemas/outbound.decision.schema.json` | `compat alias` | The outbound decision schema now accepts public string `player_id` and explicit public companions, while still accepting numeric `player_id` for compatibility. | All outbound decision producers and receivers must stop depending on numeric `player_id` as the primary identity. |
| `packages/runtime-contracts/ws/schemas/inbound.prompt.schema.json` | `compat alias` | The inbound prompt schema now accepts public string payload `player_id` and explicit public companions, while still accepting numeric `player_id` for compatibility. | Prompt producers and consumers must make public prompt target identity primary and use numeric identity only as an explicit legacy companion. |
| `packages/runtime-contracts/external-ai/schemas/request.schema.json` | `compat alias` | The external AI decision request schema now accepts public string `player_id` and explicit public companions, while still accepting numeric `player_id` for compatibility. | External worker requests must use public identity fields as primary, with numeric `player_id` retained only under a legacy compatibility name if still needed. |
| `tools/scripts/external_ai_full_stack_smoke.py` | `compat alias` | The smoke worker request and callback payload are built from pending prompt numeric `player_id`. | The smoke script must round-trip public identity fields and use numeric values only as explicit legacy callback aliases. |
| `tools/scripts/redis_restart_smoke.py` | `compat alias` | The restart smoke finds prompts and builds decisions by numeric `player_id`. | Restart smoke must select and submit by public prompt identity, with numeric values only as legacy bridge inputs. |
| `tools/scripts/game_debug_log_audit.py` | `display` | The audit groups duplicate decisions and prompt lifecycles by `session_id`, `player_id`, and `request_id` to produce human-readable findings. | No protocol removal blocker if audit grouping switches to public identity or labels numeric values as legacy/display. |

## Removal Gates

1. Runtime contract schemas stop requiring numeric `player_id` as the public
   identity field.
2. Browser, headless, external-AI, and smoke decision submitters can send a
   decision without a numeric public `player_id` when public identity companions
   are present.
3. Prompt selection keeps the engine bridge at one explicit adapter boundary
   instead of requiring protocol payload consumers to infer numeric identity.
4. Replay, harness, and audit outputs either use public identity keys or mark
   numeric values as display/legacy-only.
5. This inventory is updated until no `compat alias` entries remain; only then
   can numeric alias removal be treated as a protocol cleanup instead of a
   breaking migration.
