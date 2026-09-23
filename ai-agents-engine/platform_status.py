"""Read-only production status for Redis, agent workers and event streams."""

from __future__ import annotations

import os
import sys


def main() -> int:
    redis_url = os.getenv("ERP_REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis
        client = redis.from_url(redis_url, decode_responses=True)
        client.ping()
    except Exception as error:
        print(f"REDIS=UNAVAILABLE error={error}")
        return 1

    input_stream = os.getenv("AGENT_INPUT_STREAM", "class:transcript:chunks")
    output_stream = os.getenv("AGENT_OUTPUT_STREAM", "class:agent:results")
    print(f"REDIS=OK input_stream={input_stream} input_length={client.xlen(input_stream)}")
    print(f"output_stream={output_stream} output_length={client.xlen(output_stream)}")
    workers = client.keys("agents:worker:heartbeat:*")
    if not workers:
        print("WORKERS=0")
        return 2
    for key in sorted(workers):
        values = client.hgetall(key)
        print("WORKER=" + key.rsplit(":", 1)[-1] + " " + " ".join(f"{k}={v}" for k, v in sorted(values.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())