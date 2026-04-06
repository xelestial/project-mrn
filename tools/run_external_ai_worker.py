from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MRN external AI worker.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--worker-id", default="external-ai-worker")
    parser.add_argument("--policy-mode", default="heuristic_v3_gpt")
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    os.environ["MRN_EXTERNAL_AI_WORKER_ID"] = args.worker_id
    os.environ["MRN_EXTERNAL_AI_POLICY_MODE"] = args.policy_mode
    uvicorn.run(
        "apps.server.src.external_ai_app:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
