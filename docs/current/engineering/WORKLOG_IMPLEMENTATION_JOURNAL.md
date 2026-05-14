# Implementation Journal

This journal is current-state context, not an exhaustive historical log. Keep
entries only when they help a future implementation session decide:

- what changed recently,
- what responsibility moved or intentionally stayed,
- what verification already proved,
- what remaining work should be picked next.

Older detailed phase logs should be removed once their conclusions are reflected
in the active plans, status index, tests, or canonical contract documents.

## 2026-05-14 Runtime Protocol Identity Continuation

- Added `PROTOCOL_IDENTITY_CONSUMER_INVENTORY.md` to classify the remaining
  numeric `player_id` consumers before alias removal. The inventory separates
  display-only uses, the current engine bridge, compatibility aliases, and
  protocol violations; current protocol violation entries are none found. The
  explicit removal rule is that numeric aliases stay until the inventory has no
  `compat alias` entries.
- Runtime contract schemas for WebSocket outbound decisions, WebSocket inbound
  prompts, and external-AI decision requests now accept public string
  `player_id` plus explicit `legacy_player_id`, `public_player_id`, `seat_id`,
  and `viewer_id` companions. Existing numeric `player_id` examples remain
  valid; this only removes the schema-level integer-only blocker.
- The WebSocket outbound decision schema now explicitly owns the continuation
  identity companion contract already emitted by frontend decisions and
  accepted by the server: `prompt_instance_id`, `public_prompt_instance_id`,
  prompt fingerprint fields, resume metadata, frame/module/batch fields,
  numeric `missing_player_ids` and `resume_tokens_by_player_id`, plus
  public-player, seat, and viewer companion lists/maps. The outbound decision
  example now exercises that path, so the contract no longer relies on
  `additionalProperties` to hide those fields.
- WebSocket outbound decision construction now exposes `primary_player_id` and
  `primary_player_id_source`, and labels a top-level numeric `player_id` as
  `player_id_alias_role: "legacy_compatibility_alias"`. Public/protocol
  `player_id` values remain primary protocol identities, while numeric-only
  decisions are explicitly marked as the legacy fallback path.
- `PromptService.create_prompt()` and server active prompt view-state now emit
  `primary_player_id`, `primary_player_id_source`, and label numeric top-level
  `player_id` as `player_id_alias_role: "legacy_compatibility_alias"`. The
  frontend prompt selector consumes those explicit primary fields first, then
  keeps the existing public/protocol/legacy fallback path for mixed migration
  payloads.
- Server active prompt view-state now preserves `legacy_player_id` and uses it
  as the numeric compatibility bridge when the source prompt has public/protocol
  top-level `player_id`. This prevents mixed migration prompts from projecting
  a fabricated `player_id: 0` while keeping public `primary_player_id` as the
  prompt target identity.
- `PromptService.submit_decision()` now preserves the same primary identity trio
  from the pending prompt into lifecycle decision records, command payloads, and
  nested command decision payloads. This keeps the command boundary from
  silently downgrading an explicit public primary identity back to an unlabeled
  numeric `player_id`.
- `decision_ack` payloads now carry `player_id_alias_role`,
  `primary_player_id`, and `primary_player_id_source` whenever the legacy
  numeric `player_id` remains in the ACK. `SessionService.protocol_identity_fields()`
  supplies the public primary identity for normal session-backed ACKs, and
  `build_decision_ack_payload()` falls back to explicit legacy-primary metadata
  if no public identity companion is available. The WebSocket ACK schema and
  examples now require that primary metadata for numeric ACK aliases.
- The protocol identity consumer inventory already documented the WebSocket
  inbound `decision_ack` schema as a `compat alias` boundary, but the inventory
  integrity test did not require that row. The doc guard now includes the ACK
  schema so this protocol boundary cannot silently disappear from the
  inventory while numeric ACK aliases remain.
- External-AI request contract examples now exercise the public-primary request
  shape: top-level `player_id` is the public string identity,
  `primary_player_id_source` is `public`, and `legacy_player_id`,
  `public_player_id`, `seat_id`, and `viewer_id` are explicit companions.
  Numeric player ids still remain valid as a labeled legacy alias in schema
  tests, but the frozen examples no longer present the numeric alias as the
  canonical external worker contract.
- External-AI request schema tests now separate the canonical public-primary
  sample from the labeled numeric compatibility-alias sample. This keeps the
  compatibility path covered without teaching external worker authors to attach
  `player_id_alias_role` to the normal public string `player_id` request.
- The external-AI full-stack smoke adapter now preserves pending prompt
  `legacy_request_id`, `public_request_id`, `public_prompt_instance_id`,
  `legacy_player_id`, `public_player_id`, `seat_id`, and `viewer_id` through the
  worker request and callback body. It now uses public/protocol top-level
  `player_id` when available and keeps numeric `player_id` plus
  `player_id_alias_role: "legacy_compatibility_alias"` only for legacy-only
  prompt input.
  When a pending prompt already carries explicit `primary_player_id` metadata,
  the worker request and callback now consume that primary identity before
  falling back to `public_player_id`, protocol `player_id`, or legacy numeric
  aliases.
- The Redis restart decision smoke adapter now accepts replay prompts whose
  protocol `player_id` is public as long as `legacy_player_id` or another
  numeric bridge is present. Decision payload construction now preserves the
  same request/player/seat/viewer companions, emits `primary_player_id` and
  `primary_player_id_source`, and uses public/protocol top-level `player_id`
  when available. Numeric top-level `player_id` is labeled as
  `player_id_alias_role: "legacy_compatibility_alias"` only for legacy-only
  prompt input.
- HTTP decision policy requests now use public/protocol top-level `player_id`
  when available and mirror that value in `identity.player_id`. Numeric
  `player_id` plus `player_id_alias_role: "legacy_compatibility_alias"` remains
  only for legacy-only policy input.
- Headless view-commit trace compaction now consumes explicit active-prompt
  `primary_player_id` plus `primary_player_id_source` before numeric aliases.
  Numeric `active_prompt_player_id` and `active_prompt_protocol_player_id`
  remain trace/debug compatibility fields, not the primary prompt identity.
Responsibility result: ACK primary identity ownership moved to the server ACK
builder/session identity boundary, and HTTP policy request protocol identity is
owned by the request builder. Consumers no longer need to guess whether numeric
ACK or legacy-only HTTP-policy `player_id` values are primary identity or
compatibility aliases.
Runtime contract responsibility also moved: outbound decision continuation
companion fields are now owned by the frozen schema and example instead of
being tolerated only through open-ended `additionalProperties`.
- Runtime fanout and session bootstrap identity helpers now keep explicit
  prefixed/list legacy companions for protocol player-id fields. Examples:
  `acting_legacy_player_id`, `owner_legacy_player_id`,
  `alive_legacy_player_ids`, `marker_owner_legacy_player_id`, and
  `pawn_legacy_player_ids`. Numeric `*_player_id` aliases still remain for
  compatibility; this only makes the companion shape complete while public
  string IDs are additive.
- `domain.protocol_identity.public_identity_numeric_leaks()` now provides a
  reusable recursive guard for protocol payload tests. It fails when public
  identity fields such as `public_player_id`, `seat_id`, `viewer_id`,
  `public_request_id`, `public_prompt_instance_id`, `event_id`, public identity
  lists, or `*_by_public_player_id` map keys collapse to numeric values, while
  allowing explicit numeric compatibility aliases such as `player_id`,
  `legacy_player_id`, `seat`, and `prompt_instance_id`.
- The same guard now runs over representative runtime fanout event payloads,
  fanout snapshots, active simultaneous batch prompt payloads, delayed prompt
  publication payloads, WebSocket decision acks, external-AI callback decision
  records, and admin external-AI pending-prompt rows. This expands the evidence
  net before any future numeric alias removal; it does not remove the
  compatibility aliases.
- Prompt timeout fallback now preserves prompt identity companions through
  fallback execution history and timeout/resolved event publication. The
  canonical `request_id` remains the opaque public id, and
  `legacy_request_id` remains the compatibility/debug alias.
- `PromptBoundaryBuilder` now attaches prompt protocol identity companions at
  boundary construction time. Explicit-request prompts and module continuation
  prompts carry `legacy_request_id`, `public_request_id`, and
  `public_prompt_instance_id` before they reach prompt persistence or gateway
  publication; numeric `prompt_instance_id` remains the compatibility lifecycle
  key.
- Flipped new `PromptService` prompt storage and command-resume payloads to use
  the opaque public request id as the canonical `request_id`.
- Legacy semantic request IDs remain as `legacy_request_id` plus bounded
  in-memory/Redis aliases, so older callbacks and debug lookups still resolve
  to the public canonical key.
- `PromptService` now accepts a submitted `public_request_id` at the protocol
  boundary, preserves it as the canonical prompt key, and accepts submitted
  legacy request IDs as compatibility aliases.
- `DecisionGateway` now switches its local request-id variable to the
  `PromptService` canonical public id after prompt creation/reuse, so prompt
  messages plus requested/resolved/timeout events share the same opaque
  `request_id` while carrying `legacy_request_id` for compatibility.
- Module decision commands now carry explicit `prompt_instance_id`, and runtime
  resume matching and prompt sequence seeding now use that explicit field
  without parsing legacy request-id suffixes for prompt instance recovery.
- Prompt instance sequence increment/restore now lives behind
  `services.prompt_boundary_builder.PromptBoundaryBuilder`, which uses
  `domain.prompt_sequence.PromptInstanceSequencer` for the numeric rule.
  `_ServerDecisionPolicyBridge` owns the builder and recovery seed API;
  `_LocalHumanDecisionClient` no longer exposes prompt sequence state or
  increments prompt instances itself.
- Pending prompt boundary state recording and clearing now also live in
  `domain.prompt_sequence` helpers. `RuntimeService` still detects the
  `PromptRequired` boundary, but the checkpoint fields for pending request,
  prompt type, player, instance id, and sequence advancement are no longer
  hand-written in the transition loop.
- Prompt boundary envelope preparation now runs through
  `PromptBoundaryBuilder`, with the pure merge/copy rule still in
  `domain.prompt_sequence.prepare_prompt_boundary_envelope()`. The builder
  allocates compatibility `prompt_instance_id` values, merges active request
  metadata, and attaches module continuation metadata before the prompt reaches
  `DecisionGateway`.
- Decision-resume prompt sequence matching and post-resume advancement now use
  `domain.prompt_sequence` helpers against the bridge-owned
  `PromptBoundaryBuilder`. The "unknown instance matches", "unseeded sequence
  matches", and `max(current + 1, resume_instance)` rules are no longer
  bridge-local arithmetic or local human client state.
- Active batch prompt enrichment now requires explicit `batch_id` plus
  submitted player identity when exact request-id equality does not match.
  Runtime no longer derives batch identity or player position from the legacy
  `batch:*:pN` request-id shape.
- WebSocket human decision ACKs now include the accepted decision
  `command_seq`, matching the REST/external-AI decision callback boundary and
  letting clients correlate an accepted prompt decision with the queued runtime
  command.
- Admin external-AI pending prompt reads now expose the public canonical
  request id, legacy request alias, public player id, seat id, and viewer id
  while retaining numeric `player_id` as a compatibility routing alias.
- Frontend/headless decision construction now accepts active prompt public
  string `player_id` as the outbound protocol identity. `buildDecisionMessage()`
  carries explicit `legacy_player_id`, `public_player_id`, `seat_id`, and
  `viewer_id` companions, and pure numeric decision messages remain unchanged.
  Active prompt selection only accepts a string protocol `player_id` when the
  payload also carries a numeric `legacy_player_id`, preserving the current
  engine/seat bridge instead of guessing from public IDs.
- The rendered React UI prompt submission path now uses the same active-prompt
  protocol identity extraction as headless. `App.tsx` passes public player,
  legacy player, seat, and viewer companions into `useGameStream.sendDecision()`;
  `useGameStream` now resolves duplicate-flight keys through public/protocol
  identity when present and falls back to numeric identity only for legacy
  prompts.
- The same React UI path now preserves explicit `PromptViewModel.primaryPlayerId`
  plus `primaryPlayerIdSource` through `App.tsx`, `useGameStream`, and
  `buildDecisionMessage()`. Browser decision messages and duplicate-flight keys
  prefer that server-issued prompt primary identity before recomputing from
  public, protocol, or legacy fallback fields.
- `promptSelectors` now exposes an explicit `PromptIdentityViewModel` on
  `PromptViewModel.identity`. The selector can parse public prompt identity
  before the UI resolves it to a legacy engine seat; later prompt display work
  also exposes the same primary identity on `PromptViewModel.primaryPlayerId`.
- `App.tsx` prompt actionability now compares `LocalViewerIdentity`
  public/protocol/viewer/seat identity against `PromptViewModel.identity`
  before legacy fallback. Queued burden-exchange suppression stays on the
  prompt primary identity helper. The remaining numeric requirement is
  compatibility output and engine-bridge selector input, not prompt target
  comparison itself.
- Headless external-policy and replay exports now preserve public player,
  seat, viewer, and legacy player companions. HTTP decision policy requests
  now use public/protocol `player_id` when available while retaining
  `legacy_player_id` and numeric legacy-only fallback fields. They also expose
  an `identity.primary_player_id` block with `primary_player_id_source`, so HTTP
  policy consumers have a clear public-primary identity field. Compact trace
  payloads and replay rows carry the same companions without changing reward
  calculation's numeric actor-index bridge.
- `HeadlessGameClient` now gives decision policies a
  `HeadlessDecisionContext.identity` object and writes compact decision/view
  trace identity blocks with `primary_player_id`. Public identity is visible as
  the policy/trace primary value while numeric `playerId` remains the legacy
  route/debug bridge for current prompt matching, duplicate suppression, and
  retry handling.
- Session bootstrap identity was aligned with the runtime protocol identity
  migration. `session_start.players`, initial snapshot players, marker owner,
  and starting pawn lists now carry public player, seat, and viewer companion
  fields while retaining numeric compatibility aliases.
- `PromptService.wait_for_decision()` now resolves already-submitted public
  request aliases through lifecycle metadata for both in-memory and Redis
  stores. Zero-timeout missing-decision probes still avoid pending/resolved hash
  scans.
- Public request alias lookup now has an in-memory request alias index and
  Redis prompt-hash alias indexes. Pending-read, accept, wait, lifecycle-read,
  timeout, resolved, and command-replay paths can resolve legacy/public request
  aliases without making legacy semantic IDs the canonical key.
- `PromptService.get_prompt_lifecycle()` now accepts both public and legacy
  request aliases and returns the public-key lifecycle record.
- `PromptService.get_pending_prompt()` now accepts public request aliases for
  active pending prompts. It resolves only against active pending records, so
  completed prompts do not reappear as pending through lifecycle metadata.
- `PromptService.mark_prompt_delivered()` and
  `record_external_decision_result()` now resolve submitted public request
  aliases before lifecycle writes, and `PromptService.expire_prompt()` resolves
  active pending aliases before deletion/resolution. Delivered, external-result,
  and expired states therefore update the same legacy-key lifecycle record
  instead of creating or missing a parallel public-key record.
- Redis-backed `PromptService` coverage now proves the same public request
  alias adapter at pending-read, accept, wait, lifecycle-read, and expire
  boundaries. That keeps the Redis path aligned with the in-memory service
  tests instead of relying on one backend's behavior as evidence for both.
- Decision command materialization now copies prompt player identity companions
  (`public_player_id`, `seat_id`, `viewer_id`, and display aliases) into normal
  decision commands, simultaneous batch collector responses, and timeout
  fallback responses. Numeric `player_id` remains the compatibility routing
  alias.
- `BatchCollector` completion commands now expose
  `responses_by_public_player_id` and ordered `expected_public_player_ids` as
  additive companions derived from collected response payloads. Numeric
  `responses_by_player_id` and `expected_player_ids` remain the compatibility
  resume map and ordering contract.
- `RuntimeDecisionResume` now accepts public-only `batch_complete`
  `responses_by_public_player_id` payloads by resolving public player IDs
  through `SessionService` and materializing the numeric engine bridge map.
  Legacy numeric `responses_by_player_id` payloads are still accepted.
- `test_public_batch_complete_resume_applies_to_internal_engine_batch` verifies
  that a public-only batch completion command reaches the engine batch by way
  of the runtime bridge. The remaining numeric `responses_by_player_id` map is
  an internal engine actor-index structure, not a public protocol requirement.
- Responsibility moved: prompt continuation matching and prompt
  storage/resume no longer rely first on semantic `request_id` strings.
  Decision event publication also no longer keeps the pre-create legacy id as
  the event key after `PromptService` has assigned a public id.
  Runtime batch resume/enrichment also no longer manufactures `batch_id` from
  request-id suffixes. `PromptService` command materialization now follows the
  same rule; producers must carry explicit batch identity. Public prompt-id
  lookup responsibility moved into the prompt service/store alias indexes.
  Bootstrap event construction now owns additive public identity enrichment
  before runtime fanout starts. Runtime fanout still owns post-start view
  commits. Both bootstrap and fanout helpers now also own complete
  prefixed/list legacy companion enrichment; route consumers should not patch
  those fields after publication. Frontend decision construction now owns the
  protocol outbound identity shape instead of assuming caller numeric
  `playerId` is the wire identity. Rendered UI prompt submission now owns
  extracting protocol identity from `PromptViewModel`, while `useGameStream`
  owns serialization and numeric flight-key compatibility. Headless policy,
  trace, and replay export boundaries now own public identity preservation
  instead of silently reducing those artifacts back to numeric player ids.
  Engine actor indexes remain internal numeric state. Legacy request IDs now
  remain compatibility inputs rather than the canonical storage key.

Verification:

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -k "fanout_event_payload_adds_actor_public_identity_for_acting_player or fanout_event_payload_adds_prefixed_identity_for_related_players or fanout_event_payload_adds_public_identity_lists_for_player_id_lists or fanout_snapshot_payload_adds_public_identity_companions" -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py -k "start_replay_session_start_includes_initial_active_faces" -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_stream_api.py::StreamApiTests::test_connect_resends_pending_prompt_to_matching_seat_without_stream_event apps/server/tests/test_stream_api.py::StreamApiTests::test_resume_resends_pending_prompt_created_without_stream_event apps/server/tests/test_stream_api.py::StreamApiTests::test_prompt_timeout_emits_fallback_execution_and_runtime_tracks_history -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_session_service.py apps/server/tests/test_stream_api.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_resume_does_not_derive_batch_id_from_batch_request_id apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_prompt_boundary_enrichment_uses_explicit_batch_and_player_for_opaque_request_id -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_resume_from_batch_complete_command_uses_collected_response apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_resume_from_batch_complete_command_accepts_public_response_map apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_collected_batch_responses_are_applied_before_primary_resume -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_sequence.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_runtime_prompt_boundary_can_publish_after_view_commit_guardrail apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_human_bridge_prompt_sequence_can_resume_from_checkpoint_value apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_seeds_prompt_sequence_from_previous_same_module_decision -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_prompt_module_continuation.py::test_local_human_client_prompt_boundary_is_owned_by_builder apps/server/tests/test_prompt_module_continuation.py::test_local_human_prompt_created_inside_module_attaches_active_continuation -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py::PromptServiceTests::test_public_request_alias_resolution_uses_index_before_scans -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py::PromptServiceTests::test_module_decision_command_does_not_derive_batch_id_from_request_id apps/server/tests/test_prompt_service.py::PromptServiceTests::test_module_decision_command_carries_prompt_instance_id_for_public_request_alias -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py::PromptServiceTests::test_mark_prompt_delivered_resolves_public_request_id_alias apps/server/tests/test_prompt_service.py::PromptServiceTests::test_external_decision_result_resolves_public_request_id_alias -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_batch_collector.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_stream_api.py -q`
- `npm --prefix apps/web test -- src/domain/stream/decisionProtocol.spec.ts src/headless/HeadlessGameClient.spec.ts src/hooks/useGameStream.spec.ts src/headless/frontendTransportAdapter.spec.ts`
- `npm --prefix apps/web test -- src/headless/httpDecisionPolicy.spec.ts src/headless/protocolReplay.spec.ts src/headless/HeadlessGameClient.spec.ts`
- `npm --prefix apps/web run build`
- `./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py::SessionsApiTests::test_external_ai_decision_callback_accepts_public_player_and_request_identity -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py::SessionsApiTests::test_start_replay_session_start_includes_initial_active_faces -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_accepts_public_request_id_with_redis_prompt_store apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_expires_public_request_id_with_redis_prompt_store -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_uses_redis_alias_index_for_public_request_id_lookup -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_sequence.py apps/server/tests/test_redis_realtime_services.py -q -k "runtime_prompt_sequence_seed or prompt_sequence"`
- `./.venv/bin/python tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-13 Prompt Identity Cleanup

- Removed `DecisionGateway`'s process-local request id fallback for prompt
  creation errors.
- Blocking human prompt replay now reuses an existing pending prompt with the
  same deterministic `request_id`; it does not create a new per-process/random
  request id and supersede the original prompt.
- AI decision events now use a deterministic protocol id derived from request
  type, player id, and public context fingerprint. At the time of this cleanup
  it did not replace the external AI worker/callback redesign; the HTTP
  external AI path was later moved to a pending prompt plus callback command
  boundary, while local/loopback AI remains a separate test-profile concern.
- Responsibility moved: request identity is no longer owned by a
  `DecisionGateway` in-memory counter. Prompt identity is owned by protocol
  boundary data, and duplicate pending prompts remain owned by the existing
  prompt lifecycle.
- Server `_LocalHumanDecisionClient` no longer reads or writes engine
  `HumanHttpPolicy._prompt_seq`. Runtime prompt sequence is seeded from
  checkpoint/domain logic and held by the server adapter while the engine
  transition is running.
- Responsibility intentionally remains: process-local runtime `_prompt_seq`
  ownership is still open and requires prompt boundary creation to move out of
  the policy adapter path. Engine standalone `HumanHttpPolicy._prompt_seq`
  remains for non-server human play.

Verification:

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_gateway_reuses_pending_prompt_id_when_blocking apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_gateway_has_no_process_local_request_seq_fallback -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q -k 'decision_gateway or runtime_prompt_boundary'`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_prompt_module_continuation.py::test_local_human_client_prompt_boundary_is_owned_by_builder apps/server/tests/test_prompt_module_continuation.py::test_local_human_prompt_created_inside_module_attaches_active_continuation -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_human_bridge_prompt_sequence_can_resume_from_checkpoint_value apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_seeds_prompt_sequence_from_previous_same_module_decision -q`

## 2026-05-13 Runtime Matrix Coverage Sync

- Fixed `tests/test_module_runtime_playtest_matrix_doc.py` failures caused by
  stale coverage artifacts, not runtime rule changes.
- Added frontend prompt selector coverage for serial prompt request types already
  present in `round-combination.regression-pack.json`: `trick_to_use`,
  `specific_trick_reward`, `lap_reward`, `purchase_tile`, and
  `coin_placement`.
- Added `InitialRewardModule` to the RoundFrame module inventory in
  `docs/current/runtime/round-action-control-matrix.md`, matching
  `engine/runtime_modules/catalog.py`.
- Responsibility did not move: runtime contracts remain owned by the catalog and
  regression pack; the frontend spec and runtime matrix now track those
  contracts again.

Verification:

- `./.venv/bin/python -m pytest tests/test_module_runtime_playtest_matrix_doc.py -q`
- `npm --prefix apps/web test -- src/domain/selectors/promptSelectors.spec.ts`
- `python3 tools/plan_policy_gate.py`
- `git diff --check`

## 2026-05-13 Documentation Hygiene

- Renamed current documentation files under `docs/current` so filenames no
  longer contain shell-special square brackets.
- Preserved prefix semantics with plain names such as `PLAN_`, `ACTIVE_`, and
  `WORKLOG_`.
- Updated in-repo references, README pointers, tests, and
  `tools/plan_policy_gate.py`.
- Added policy that forbids square brackets in `docs/current` filenames and
  requires reference/policy gate updates in the same rename change.
- Added the mandatory pre-implementation contract to
  `docs/current/engineering/MANDATORY_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
  and root `AGENTS.md`.

Verification:

- bracket filename/reference check: `files=0`, `refs=0`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-13 Server Runtime Rebuild Phase 9 Current State

Phase 9 is reducing `RuntimeService` from command lifecycle owner to runtime
boundary adapter. The current split is:

- `SessionLoop` owns command lifecycle control flow through
  `SessionCommandExecutor`.
- `CommandRouter` only validates accepted command references and wakes
  `SessionLoopManager`.
- `CommandStreamWakeupWorker` observes Redis pending/resumable commands and
  wakes `SessionLoopManager`; it no longer directly calls runtime execution.
- `CommandRecoveryService` owns read-side command recovery queries.
- `CommandProcessingGuardService` owns consumer-offset checks, stale terminal
  classification, rejected/superseded/expired marking, and rejected offset
  advancement.
- `CommandExecutionGate` owns in-process active command/session gating and
  active runtime task deferral.
- `CommandBoundaryFinalizer` owns deferred commit finalization, latest
  `view_commit` emission, waiting prompt materialization, and finalization
  timing logs.
- `CommandBoundaryGameStateStore` owns command-boundary staging/deferred commit
  behavior and prevents internal module transitions from committing
  authoritatively mid-command.
- `CommandBoundaryRunner` owns command-boundary per-call store creation,
  transition repetition, terminal detection, finalizer call, module trace, and
  timing result assembly. `RuntimeService` only injects engine/persistence
  callables for that boundary.
- `runtime_prompt_sequence_seed()` lives in
  `apps/server/src/domain/prompt_sequence.py`, not `runtime_service.py`.
- Final command-boundary commit rechecks runtime lease ownership before
  authoritative Redis/view/prompt side effects.
- `RuntimeService.process_command_once()` has been removed. Production
  `SessionLoop` paths and diagnostic tests now use `SessionCommandExecutor`
  directly, while `RuntimeService` exposes only runtime-boundary lifecycle
  methods for command execution.
- `SessionLoop` no longer has a fallback to
  `RuntimeService.process_command_once()` when a runtime boundary lacks the
  lifecycle interface. Loop tests now exercise the lifecycle boundary path.

Important remaining responsibility:

- Prompt boundary construction is no longer owned by `_LocalHumanDecisionClient`;
  the remaining architectural question is whether the bridge-owned
  `PromptBoundaryBuilder` should later move up into `SessionCommandExecutor` or
  a UnitOfWork-style owner. Do not move it until command/prompt atomicity is
  being redesigned as one boundary.
- Keep `CommandBoundaryGameStateStore` as the explicit command atomicity staging
  boundary until a future UnitOfWork-style owner exists in `SessionLoop` or
  `SessionCommandExecutor`.
- Keep Redis authoritative and `view_commit` as read model; do not reintroduce
  route-level runtime execution or heartbeat-driven repair.

Representative verification already passed during this phase:

- focused service tests for command recovery, processing guard, execution gate,
  boundary finalizer, boundary store, session loop, router, stream, and wakeup
  worker
- full `apps/server/tests` passes through the Phase 9 checkpoints
- `npm --prefix apps/web test -- src/headless/protocolGateRunArtifacts.spec.ts src/headless/protocolGateRunProgress.spec.ts src/headless/protocolLatencyGate.spec.ts`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-12 Runtime Rebuild Evidence To Preserve

- The valid scaling baseline is `5 server instances + 1 Redis`, not
  `1 server + 5 Redis`. Current server state construction uses one global
  `MRN_REDIS_URL`, so multiple Redis containers behind one server are unused
  unless a session-aware routing layer is built.
- A 5-game isolated server/Redis run passed with per-game server and Redis.
- A 5-server/1-Redis run passed, isolating earlier concurrent failures away from
  Redis-only saturation.
- A single-server/20-game stress run failed on backend timing, not command loss:
  `InitialRewardModule` transition wall-clock dominated, with evidence showing
  engine transition time far above Redis commit and view commit time.
- Conclusion: the observed 20-game single-server bottleneck was server-side
  engine transition saturation under one Python server process, not Redis
  commit, view projection, missing ACK, duplicate view commit, or command inbox
  loss.

This evidence remains useful because it explains why server-instance count and
runtime ownership matter more than Redis fan-out for the current architecture.

## 2026-05-13 Phase 10 Prompt Replay Probe Fix

- Removed the nonblocking prompt replay wait from human prompt creation.
  `DecisionGateway.resolve_human_prompt(blocking_human_prompts=False)` now uses
  `PromptService.wait_for_decision(timeout_ms=0)` as an immediate resolved
  decision probe. That probe does not create a pending waiter and does not scan
  the full resolved hash for TTL pruning on every wait call.
- Pre-fix 5-server evidence showed `WeatherModule` prompt creation spending
  6773ms in `replay_wait_ms`, with Redis commit/view commit still bounded.
  Post-fix 5-server evidence completed all games with max transition 538ms and
  max command 1224ms.
- Restart, pending-prompt reconnect, and duplicate decision smokes passed.
  Duplicate decision replay returned `stale/already_resolved`.
- 20-game/1-server remains a capacity bottleneck by design of the test: after
  the prompt replay wait was removed, fail-fast showed command wall-clock
  5357ms under one server process while prompt timing count was 0 and
  Redis/view commit counts stayed at 1.

Responsibility result: prompt lifecycle replay probing no longer blocks prompt
materialization. The remaining 20-game/1-server failure belongs to single-server
runtime scheduling/capacity, not prompt identity, Redis commit, view projection,
ACK delivery, or command inbox dedupe.

## 2026-05-13 Protocol Gate Output Hygiene

- The direct full-stack protocol gate and repeated-game protocol gate runner now
  suppress compact progress output by default. Pass `--verbose-progress` only
  when live progress lines are useful enough to spend terminal/chat context.
- `--verbose-progress` is the explicit opt-in for investigation runs where
  progress lines are worth the terminal/chat context cost.
- In repeated runs, raw child stdout/stderr and progress remain persisted under
  each `game-N/raw/` directory, and failure diagnosis still starts from
  `PROTOCOL_GATE_FAILURE_POINTER` plus `summary/failure_reason.json`.

Responsibility result: long-run evidence ownership stays with file artifacts and
failure pointers. Chat/terminal output is no longer responsible for carrying
successful progress details.

## 2026-05-13 Session Loop Recovery Status Closure

- Closed stale Phase 2/3 checklist items in the active server-runtime rebuild
  plan against existing implementation evidence.
- The selected wake policy is lazy wake start: session start does not create a
  long-lived loop; accepted durable commands wake `SessionLoopManager` through
  `CommandRouter` or `CommandStreamWakeupWorker`.
- The loop is a bounded drain task, not an idle daemon. Lease ownership is scoped
  to each command execution and released in `SessionCommandExecutor.finally`;
  the manager task exits once the Redis inbox is idle.
- Restart recovery is covered by Redis command inbox plus worker polling, not
  by process-local queue state or a separate remote-owner pub/sub signal.

Responsibility result: no runtime responsibility moved in this checkpoint. The
plan now matches the already implemented ownership: Redis inbox is durable
authority, router/worker are wake paths, and `SessionLoopManager` owns one
process-local drain task per session. External AI command-boundary unification
remains open.

## 2026-05-13 HTTP External AI Command Boundary

- HTTP external AI transport no longer invokes the worker sender/healthchecker
  inside the session loop. It materializes a provider=`ai` pending prompt and
  stops at `PromptRequired`.
- Added an external AI decision callback route. Accepted callbacks go through
  `PromptService.submit_decision()` and `CommandInbox.accept_prompt_decision()`,
  then wake the session loop through `CommandRouter.wake_after_accept()`.
- Preserved provider=`ai` through pending prompt payload, submitted decision
  payload, persisted `decision_submitted` command, runtime decision resume, and
  stream ACK.
- Removed obsolete runtime-service tests that asserted the old forbidden
  behavior: direct in-loop HTTP worker calls, retry loops, and local AI fallback
  from the HTTP transport path. Worker API and helper validation remain covered
  outside the session-loop transport contract.

Responsibility result: HTTP external AI provider execution moved out of the
session loop. Decision acceptance remains in `PromptService`/`CommandInbox`.
Wake remains in `CommandRouter`. Redis command inbox remains the durable
authority. Local and loopback AI transports intentionally remain outside this
checkpoint.

## 2026-05-13 Simultaneous Batch Command Boundary

- `PromptService.submit_decision()` now routes simultaneous batch prompt
  responses through `BatchCollector` instead of appending one
  `decision_submitted` command per player.
- `PromptService.record_timeout_fallback_decision()` uses the same collector for
  simultaneous batch timeout fallback decisions, so human and timeout races are
  resolved by the collector's atomic completion primitive.
- Incomplete batch responses return accepted decision state with no command
  sequence. `PromptTimeoutWorker` now wakes the command router only when the
  accepted decision state contains a positive command sequence.
- `SessionLoop` accepts `batch_complete` as a runtime command, and
  `RuntimeService` reconstructs a `RuntimeDecisionResume` from the collected
  responses. Non-primary collected responses are applied to the active batch
  before the primary resume continues the engine transition.

Responsibility result: simultaneous batch completion ownership moved out of
route/timeout-side command append paths and into `BatchCollector`. The session
loop remains the only command execution path. `RuntimeService` still performs
the engine resume and state mutation, but it no longer decides whether a batch
is complete or creates per-response commands.

## 2026-05-13 One-Server Five-Game Baseline

- Live protocol gate with one server, one Redis, five concurrent games passed:
  `tmp/rl/full-stack-protocol/server-rebuild-live-5game-20260513-205642`.
- All five sessions completed with no stale ACK, rejected ACK, failed command,
  or raw-prompt fallback counts.
- Backend timing stayed inside the 5s gate: max command 1875ms and max
  transition 1232ms. Redis commit count and view commit count stayed at 1.
- Redis state inspector reported diagnostic `ok` for all five sessions.

Responsibility result: the current rebuild is not dependent on one server per
game for a five-game live smoke. The remaining one-server question is capacity
boundary measurement, not a known Redis/view-commit/prompt-lifecycle violation.

## 2026-05-13 One-Server Capacity Boundary

- Committed local reproducibility cleanup as `f1a24ead`
  (`chore: stabilize protocol gate local artifacts`): ignored `.playwright-mcp/`
  and passed `MRN_ADMIN_TOKEN` through the protocol compose file.
- One server plus one Redis with eight concurrent games passed:
  `tmp/rl/full-stack-protocol/server-rebuild-capacity-8game-1server-20260513-211035`.
  All eight sessions completed; max command was 3943ms, max transition was
  2159ms, Redis/view commit counts stayed at 1, and slow command/transition
  counts were 0.
- One server plus one Redis with ten concurrent games found the first measured
  SLO boundary:
  `tmp/rl/full-stack-protocol/server-rebuild-capacity-10game-1server-20260513-211951`.
  Game 3 failed `backend_timing` because command seq 1 took 5886ms for
  `reason=prompt_required`, above the 5000ms command SLO.
- The failure did not show a rule-flow or persistence contract break. For the
  failing command, `engine_loop_total_ms=203`, `redis_commit_count=1`,
  `view_commit_count=1`, and max transition stayed 1273ms. The excess was
  `executor_overhead_ms=5680`, which points to single-server runtime scheduling
  contention under concurrent command execution.

Responsibility result: no game-rule, Redis authority, `view_commit`, prompt
identity, ACK, or command-inbox responsibility moved or failed in this
checkpoint. The measured boundary is capacity/SLO ownership: a single server is
inside the current 5s command SLO at eight concurrent games and outside it at
ten concurrent games. Further 12/15-game one-server runs would characterize
overload, not find the first boundary, so they were not run.

## 2026-05-13 Protocol Evidence And Remote Gate Closure

- Committed and pushed fail-closed remote evidence gates as `fe882c7c`
  (`Harden external evidence gates`) on
  `codex/external-topology-protocol-ops`.
- Confirmed missing remote inputs are blocked by design: local Redis platform
  manifests fail with `--require-external-topology`, loopback worker URLs fail
  with `--require-non-local-endpoint`, and loopback game-server URLs fail with
  `--require-non-local-server`.
- Synchronized the runtime protocol plan status with actual evidence. Phase 0
  additive identity, Redis debug retention, baseline prompt lifecycle, and
  Redis viewer-outbox debug/indexing were implemented at that checkpoint.
  Later 2026-05-14 evidence in this journal and
  `PLAN_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md` supersedes the older
  residual list: opaque request IDs, first-class stale/resolved lifecycle
  states, and read-mode viewer outbox delivery are now implemented. The
  remaining protocol migration boundaries are numeric compatibility aliases,
  especially numeric `player_id` payload aliases and numeric
  `prompt_instance_id` lifecycle keys.
- Local validation passed: 190 server protocol/lifecycle/outbox tests, 76
  frontend headless/stream tests, smoke workflow gate, live protocol gate,
  bounded UI full-game progress, and full-stack live RL smoke at
  `tmp/rl/full-stack-protocol/codex-all-20260513`.

Responsibility result: no runtime ownership was silently moved in this
checkpoint. Evidence classification moved into scripts and status docs:
loopback/local runs are local evidence only, while remote/external evidence
requires non-local endpoint URLs, auth, and platform-filled Redis commands.
Protocol-plan responsibility also became explicit: completed additive/debug
foundations are separated from residual identity and outbox migration work.

## 2026-05-14 React Local Viewer Identity Bridge

- Added `LocalViewerIdentity` as the React-side local viewer model.
- Token-derived `session_pN_*` values and join-response `player_id` values are
  now normalized as legacy fallback inputs, not stored as the UI's whole viewer
  identity.
- `view_commit.viewer` public/protocol companions can now populate the same
  model, while existing display selectors still receive the resolved numeric
  `legacyPlayerId` bridge.
- Prompt actionability now consumes this model directly through
  `isPromptTargetedToIdentity()`, comparing public/protocol/viewer/seat identity
  before falling back to the legacy numeric bridge.
- Updated the protocol identity inventory and runtime protocol plan to record
  that this is an intermediate bridge, not numeric alias removal.

Responsibility result: token parsing and local viewer identity construction
moved out of `App.tsx` into the domain viewer helper. Prompt target comparison
moved into `promptSelectors`; `App.tsx` still owns feeding legacy numeric
selector inputs until the remaining render selectors can consume public/protocol
viewer identity directly.

## 2026-05-14 Frontend Prompt Instance Companion Preservation

- Added frontend/headless coverage that fails when `public_prompt_instance_id`
  is dropped after the server prompt boundary creates it.
- `promptViewModelFromActivePromptPayload()` now maps
  `public_prompt_instance_id` into the prompt continuation view model.
- `buildDecisionMessage()` serializes `public_prompt_instance_id` together
  with the numeric `prompt_instance_id`.
- Headless HTTP policy requests and compact decision trace payloads preserve
  the same public prompt-instance companion for external policy debugging and
  artifact inspection.

Responsibility result: no prompt lifecycle ownership moved. The numeric
`prompt_instance_id` remains the compatibility lifecycle bridge, and the web
decision boundary now owns preserving the already-created public companion
instead of silently dropping it before submit, policy input, or trace export.

## 2026-05-14 Actionable Prompt Without Legacy Seat Bridge

- Added selector coverage for public prompt identity that has `player_id`,
  `public_player_id`, `seat_id`, and `viewer_id` but no numeric
  `legacy_player_id`.
- `promptViewModelFromActivePromptPayload()` now builds an actionable prompt
  view model from that public/protocol identity instead of returning `null`
  until the numeric engine bridge is available.
- `PromptViewModel.playerId` is now nullable and means only the optional legacy
  display/engine bridge. The primary prompt target remains
  `PromptViewModel.identity.primaryPlayerId`.
- React decision serialization now uses public/protocol prompt identity first
  and includes `legacy_player_id` only when a numeric bridge is actually
  present.
- Prompt display strings kept their existing numeric `P2` output, while the
  later prompt-overlay migration made public/protocol identity visible instead
  of rendering `P?` solely because a numeric seat bridge is absent.

Responsibility result: actionable prompt construction moved off the numeric
legacy seat bridge. Numeric `PromptViewModel.playerId` intentionally remains as
display/headless compatibility data until those remaining consumers are migrated.

## 2026-05-14 Prompt Overlay Primary Identity Display

- Added selector coverage for `PromptViewModel.primaryPlayerId` and
  `primaryPlayerIdSource` on a public-only prompt with no numeric
  `legacy_player_id`.
- `PromptOverlay` now feeds header metadata from `prompt.primaryPlayerId`
  instead of the legacy top-level numeric `prompt.playerId` alias.
- Prompt i18n metadata helpers now accept `ProtocolPlayerId | null`, preserving
  existing `P2` numeric labels while allowing public/protocol string identity
  to be displayed when no legacy seat bridge exists.

Responsibility result: prompt header display ownership moved off
`PromptViewModel.playerId`. Numeric `playerId` remains only as the legacy
display/engine bridge for consumers that still need engine-seat numbers.

## 2026-05-14 Headless Prompt Routing Identity

- Added headless coverage for an active public prompt that has no numeric
  `legacy_player_id` bridge and for a mixed migration commit where the viewer
  exposes public identity while the active prompt remains legacy-only.
- `HeadlessGameClient` now routes active and raw prompts through
  `isPromptTargetedToIdentity()` using latest `view_commit.viewer`
  public/protocol/viewer/seat identity.
- The numeric `playerId` fallback remains narrowly scoped to prompts whose
  primary identity source is explicitly legacy, preserving transition-period
  compatibility without treating `PromptViewModel.playerId` as the primary
  target for public prompts.

Responsibility result: headless prompt target ownership moved from direct
`PromptViewModel.playerId === this.playerId` checks into the shared prompt
identity selector. Duplicate/retry ledgers and top-level trace seat keys
intentionally remain numeric compatibility surfaces.

## 2026-05-14 HTTP Decision Policy Primary Identity

- Added HTTP policy request coverage that fails when public primary player
  identity is already resolved on `HeadlessDecisionContext.identity` but prompt
  fields are stale or legacy-only.
- `buildHttpDecisionPolicyRequest()` now consumes
  `HeadlessDecisionContext.identity` directly instead of reinterpreting
  `PromptViewModel` fields in a second helper.
- `HttpDecisionPolicyRequest` now carries top-level `primary_player_id` and
  `primary_player_id_source` while preserving `legacy_player_id` compatibility.
- `HttpDecisionPolicyRequest.player_id` now uses public/protocol identity when
  available and carries `player_id_alias_role: "legacy_compatibility_alias"`
  only for legacy-only numeric fallback input.
- Numeric-only prompt requests still serialize `primary_player_id: 2` with
  `primary_player_id_source: "legacy"`, making the fallback explicit instead
  of pretending numeric `player_id` is the general primary identity.

Responsibility result: HTTP policy primary identity ownership moved from local
prompt reinterpretation to the already-resolved headless decision context.
External policy compatibility remains intact for legacy-only prompts because the
legacy numeric fallback is still labeled in the request.

## 2026-05-14 Headless Decision Primary Identity

- Added headless coverage for the mixed migration case where an active prompt
  still carries numeric top-level `player_id` as a legacy alias but also carries
  explicit public `primary_player_id`.
- `HeadlessGameClient` decision construction now passes
  `PromptViewModel.identity.primaryPlayerId` and `primaryPlayerIdSource` into
  `buildDecisionMessage()` instead of recomputing primary identity from the
  numeric alias.
- Numeric top-level `player_id` remains as the compatibility alias, but the
  decision now also carries `legacy_player_id` when the primary identity is not
  legacy so receivers do not have to infer the bridge from the alias. A later
  submitted-decision step moved the actual outbound top-level `player_id` off
  this numeric alias when the explicit primary identity is public/protocol.
- Decision trace top-level identity fields now use the prompt identity for
  decision events, while the generic trace default still uses the latest viewer
  identity for non-prompt events.

Responsibility result: headless decision primary identity ownership moved from
local fallback inference into the prompt selector's `PromptViewModel.identity`.
Numeric aliases remain only as compatibility fields until the protocol removal
gates close.

## 2026-05-14 Runtime Contract Numeric Alias Guard

- Added schema coverage that fails when outbound WebSocket decisions, inbound
  prompt payloads, or external-AI decision requests carry numeric `player_id`
  without primary identity metadata.
- Runtime contract schemas now keep numeric `player_id` compatible, but only
  when `player_id_alias_role`, `primary_player_id`, and
  `primary_player_id_source` are present.
- The local subset schema validator now handles the small `allOf` plus
  `if`/`then` subset needed by these frozen contract checks.

Responsibility result: detecting unlabeled numeric public identity moved into
the shared contract layer. Producers still own emitting the companion fields;
numeric alias removal remains a later compatibility-gated migration.

## 2026-05-14 Headless Trace Primary Identity

- Added headless trace coverage for both legacy-only and public-player decision
  traces.
- `HeadlessTraceEvent` now carries top-level `primary_player_id`,
  `primary_player_id_source`, protocol, legacy, public, seat, and viewer
  identity fields through the shared `recordTrace()` path.
- `view_commit_seen` trace events use the inbound commit viewer identity
  directly, so the first public commit trace is not limited by the previously
  cached client state.
- The duplicate suppression and retry ledgers were left unchanged because code
  inspection showed they are keyed by stream/request id, not by numeric
  `player_id`.

Responsibility result: trace identity interpretation moved off the numeric
`player_id` alias. The legacy numeric field remains in JSONL for compatibility
and display/debug grouping, but it is no longer the only top-level player
identity available to trace consumers.

## 2026-05-14 Protocol Harness Primary Identity Diagnostics

- Added harness coverage for public active-prompt identity in pace,
  command-latency, and repeated-prompt diagnostics.
- `ProtocolPaceDiagnostic` now exposes `activePromptPrimaryPlayerId` and source
  while keeping `activePromptPlayerId` as the legacy numeric alias.
- Repeated-prompt signatures and command-latency rows now prefer
  `active_prompt_primary_player_id` or trace `primary_player_id` before falling
  back to legacy numeric player ids.

Responsibility result: protocol-gate operator diagnostics no longer interpret
numeric active-prompt `player_id` as the primary identity. Seat numbers remain
available for display and legacy grouping only.

## 2026-05-14 Protocol Replay Primary Identity Export

- Added replay coverage for public primary player identity in rows,
  observations, and final player summaries.
- `ProtocolReplayRow` and `ProtocolReplayPlayerSummary` now expose
  `primary_player_id` plus `primary_player_id_source`.
- Numeric `player_id` remains available for reward/rank grouping and legacy
  display, but replay exports no longer present it as the only player identity.

Responsibility result: replay artifact identity moved to explicit primary
identity fields. Numeric player ids intentionally remain as display/training
grouping aliases because reward and rank calculations still consume engine-seat
snapshots.

## 2026-05-14 Debug Log Audit Primary Identity Grouping

- Added debug-log audit coverage for simultaneous public identities that share
  a request id, including cases where numeric `player_id` is absent and cases
  where nested `identity.primary_player_id` must beat a top-level numeric alias.
- `game_debug_log_audit.py` now groups duplicate frontend decisions, backend
  accepts, and draft-to-final prompt lifecycles with an identity key that
  prefers `primary_player_id`, public, protocol, viewer, and seat identity
  before falling back to numeric legacy/display fields.
- Existing numeric-only debug logs remain supported during the compatibility
  window.

Responsibility result: human diagnostic grouping moved off the bare numeric
`player_id` alias. Numeric values remain only as legacy/display fallback labels
for old logs.

## 2026-05-14 External AI Worker and Callback Public Player Identity

- Added regression coverage for `SessionService.resolve_protocol_player_id()`
  resolving a public string supplied as top-level `player_id`.
- The `/external-ai/decisions` callback request model now accepts string
  `player_id` and normalizes it through the same session identity adapter used
  by other protocol decision boundaries.
- The reference external AI worker `/decide` request model now accepts public or
  protocol string `player_id` plus explicit legacy/public/seat/viewer identity
  companions.
- `external_ai_full_stack_smoke.py` now sends public/protocol top-level
  `player_id` to both the worker `/decide` request and the server callback when
  the pending prompt provides that primary identity. Numeric `player_id` remains
  only for legacy-only prompt input and is labeled as a compatibility alias.

Responsibility result: public-string player resolution moved into
`SessionService.resolve_protocol_player_id()` for server callbacks, while the
worker boundary itself now accepts the same public/protocol identity contract
instead of forcing the smoke adapter to down-convert to a numeric alias.

## 2026-05-14 Redis Restart Smoke Public Decision Identity

- `redis_restart_smoke.py` now uses the prompt's explicit public/protocol
  primary identity as submitted decision `player_id` when available.
- The script still uses `legacy_player_id` as the replay prompt lookup bridge
  for operator-selected numeric player seats.
- Legacy-only prompts still submit numeric `player_id` and label it as
  `player_id_alias_role: "legacy_compatibility_alias"`.

Responsibility result: restart-smoke decision submission moved off the numeric
top-level alias when public/protocol identity exists. Numeric identity remains
only as replay lookup and legacy-only compatibility input.

## 2026-05-14 Headless Submitted Decision Public Identity

- Added decision-protocol and headless coverage that fails when an active prompt
  still carries numeric top-level `player_id` but also carries explicit public
  `primary_player_id`, and the outbound decision still submits the numeric
  alias.
- `buildDecisionMessage()` now chooses the submitted top-level `player_id` from
  explicit public/protocol `primaryPlayerId` before falling back to the legacy
  active-prompt `playerId`.
- Legacy-only decisions still submit numeric `player_id` and label it with
  `player_id_alias_role: "legacy_compatibility_alias"`.
- `HeadlessGameClient` keeps numeric trace `player_id` as the local seat/debug
  key, while the WebSocket decision payload itself now uses the public submitted
  identity in the mixed migration case.

Responsibility result: WebSocket decision submission moved from "forward the
active prompt top-level alias" to "submit explicit public/protocol primary
identity when available." Internal headless seat/debug identity and legacy-only
fallback routing intentionally remain numeric compatibility surfaces.

## 2026-05-14 React Submitted Decision Public Identity Coverage

- Added `useGameStream.spec.ts` coverage for the UI decision boundary where the
  active prompt still carries numeric top-level `playerId` but explicit
  `primaryPlayerId` is public.
- No production hook change was required: `useGameStream` already delegates
  decision payload serialization to `buildDecisionMessage()`, and that shared
  builder now owns submitted top-level `player_id` selection.
- The legacy numeric-only decision test remains in the same suite and continues
  to require `player_id_alias_role: "legacy_compatibility_alias"`.

Responsibility result: no new runtime responsibility moved. This locks the UI
submission boundary to the shared decision-protocol builder instead of adding a
parallel identity rule in the hook.

## 2026-05-14 External Topology Guard and Numeric Alias Companion Contract

- Redis platform smoke validation now rejects external-required manifests that
  retain local runtime preflight or local Docker Compose runtime commands, even
  if the manifest's `target_topology` is renamed to an external-looking value.
- Actual external Redis evidence remains open: it still requires a filled
  platform manifest with non-local restart and worker exec commands.
- WS decision, inbound prompt, inbound decision ACK, and external-AI request
  schemas now require `legacy_player_id` whenever top-level `player_id` remains
  numeric. Existing public string identity paths are unchanged.

Responsibility result: external-evidence classification moved from topology
name alone to manifest operation validation. Numeric player alias contracts now
make the legacy bridge explicit instead of requiring consumers to infer it from
the alias value. Numeric aliases intentionally remain during the compatibility
window.

## 2026-05-12 Runtime Rebuild Baseline

- The active rebuild plan is
  `docs/current/architecture/PLAN_SERVER_RUNTIME_REBUILD_2026-05-12.md`.
- Rejected directions included direct local queue command acceptance,
  pub/sub-only outbound delivery, non-atomic batch completion, weak deterministic
  prompt ids, and further expansion of `RuntimeService`.
- Accepted direction: Redis remains authoritative, accepted decisions become
  durable command references, `SessionLoop` drains commands, and external
  boundaries publish state through explicit commits and projected `view_commit`
  records.

## Journal Maintenance Rule

When adding to this file:

- Add only the current checkpoint and its responsibility result.
- Prefer one consolidated entry over one entry per micro-change.
- Remove old details once the active plan, tests, or status index carries the
  durable conclusion.
- Do not keep raw protocol logs here. Store bulky evidence under the run
  artifact directory and keep only decision-grade conclusions in this journal.
