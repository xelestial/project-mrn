from .registry import PROFILE_REGISTRY

# Alias mappings to resolve common heuristic names to standard profile json names
# For instance, "heuristic_v2_control" -> "control" loading "policy_weights_control.json"
PROFILE_ALIASES = {
    "heuristic_v1": "control",
    "arena": "control",
    "heuristic_v2_control": "control",
    "heuristic_v2_growth": "growth",
    "heuristic_v2_balanced": "balanced",
    "heuristic_v2_avoid_control": "avoid_control",
    "heuristic_v2_aggressive": "aggressive",
    "heuristic_v2_token_opt": "token_opt",
    "heuristic_v2_v3_claude": "v3_claude",
    
    # LAP policies map to same underlying weights, though lap mechanics use their own logic mostly
    "cash_focus": "control",
    "shard_focus": "control",
    "coin_focus": "control",
}

def resolve_profile_name(mode_name: str) -> str:
    """Resolve a raw policy mode string into a canonical profile name."""
    if mode_name in PROFILE_ALIASES:
        return PROFILE_ALIASES[mode_name]
    
    # If the mode name already matches a profile (e.g., "control", "v3_claude")
    if mode_name.startswith("heuristic_v2_"):
        return mode_name.replace("heuristic_v2_", "")
    if mode_name.startswith("heuristic_v3_"):
        # e.g. heuristic_v3_gpt_exp -> v3_gpt_exp
        return mode_name.replace("heuristic_v3_", "v3_")

    return mode_name

def get_profile_spec(mode_name: str):
    canonical_name = resolve_profile_name(mode_name)
    return PROFILE_REGISTRY.load_profile(canonical_name)
