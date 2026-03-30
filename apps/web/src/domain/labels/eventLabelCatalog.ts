const EVENT_LABELS: Record<string, string> = {
  session_created: "Session Created",
  session_start: "Session Start",
  session_started: "Session Started",
  parameter_manifest: "Parameter Manifest",
  seat_joined: "Seat Joined",
  round_start: "Round Start",
  weather_reveal: "Weather Reveal",
  draft_pick: "Draft Pick",
  final_character_choice: "Final Character Choice",
  turn_start: "Turn Start",
  dice_roll: "Move Decision",
  player_move: "Player Move",
  landing_resolved: "Landing Resolved",
  tile_purchased: "Tile Purchased",
  marker_transferred: "Marker Transferred",
  lap_reward_chosen: "Lap Reward Chosen",
  fortune_drawn: "Fortune Drawn",
  fortune_resolved: "Fortune Resolved",
  turn_end_snapshot: "Turn End",
  decision_timeout_fallback: "Decision Timeout Fallback",
  bankruptcy: "Bankruptcy",
  game_end: "Game End",
};

const NON_EVENT_LABELS: Record<string, string> = {
  prompt: "Prompt",
  decision_ack: "Decision Ack",
  heartbeat: "Heartbeat",
  error: "Error",
};

export function eventLabelForCode(eventCode: string): string {
  if (!eventCode.trim()) {
    return "Unknown Event";
  }
  return EVENT_LABELS[eventCode] ?? eventCode;
}

export function nonEventLabelForMessageType(messageType: string): string {
  return NON_EVENT_LABELS[messageType] ?? "Message";
}
