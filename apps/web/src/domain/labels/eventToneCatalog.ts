export type EventTone = "move" | "economy" | "system" | "critical";

const MOVE_EVENT_CODES = new Set<string>(["player_move", "dice_roll"]);
const ECONOMY_EVENT_CODES = new Set<string>([
  "tile_purchased",
  "landing_resolved",
  "marker_transferred",
  "lap_reward_chosen",
]);
const CRITICAL_EVENT_CODES = new Set<string>(["bankruptcy", "game_end"]);

export function toneForEventCode(eventCode: string): EventTone {
  if (CRITICAL_EVENT_CODES.has(eventCode)) {
    return "critical";
  }
  if (MOVE_EVENT_CODES.has(eventCode)) {
    return "move";
  }
  if (ECONOMY_EVENT_CODES.has(eventCode)) {
    return "economy";
  }
  return "system";
}
