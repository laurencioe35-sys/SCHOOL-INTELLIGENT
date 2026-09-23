"""Production worker for the ERP agent runtime.

Consumes events published by the multimedia/transcription service from Redis
Streams and publishes aggregated agent results to a separate stream. It never
creates synthetic input and refuses to start without Redis and a real LLM.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from agents_v2.analytics_agent import AnalyticsAgent
from agents_v2.content_generator_agent import ContentGeneratorAgent
from agents_v2.exercise_agent import build_all_subject_agents
from agents_v2.grading_agent import GradingAgent
from agents_v2.teacher_response_agent import TeacherResponseAgent
from config.llm_client import require_real_provider
from orchestrator.blackboard import build_blackboard
from orchestrator.loop_engine import AgentLoop
from orchestrator.queue_adapter import build_event_queue
from orchestrator.registry import AgentRegistry
from transcription import GeminiTranscriber

logger = logging.getLogger("ai-agents-engine.service")


def _required_environment() -> tuple[str, str, str]:
    redis_url = os.getenv("ERP_REDIS_URL")
    if not redis_url:
        raise RuntimeError("ERP_REDIS_URL is required for the production agent worker")
    input_stream = os.getenv("AGENT_INPUT_STREAM", "class:transcript:chunks")
    output_stream = os.getenv("AGENT_OUTPUT_STREAM", "class:agent:results")
    return redis_url, input_stream, output_stream


def _require_redis_dependency() -> None:
    try:
        import redis  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("The redis Python package is required for the production agent worker") from exc


def build_production_loop() -> AgentLoop:
    redis_url, input_stream, output_stream = _required_environment()
    _require_redis_dependency()
    require_real_provider()

    registry = AgentRegistry()
    registry.register(GradingAgent())
    registry.register(ContentGeneratorAgent())
    registry.register(TeacherResponseAgent())
    registry.register(AnalyticsAgent())
    for subject_agent in build_all_subject_agents():
        registry.register(subject_agent)

    return AgentLoop(
        event_queue=build_event_queue(redis_url, input_stream),
        blackboard=build_blackboard(redis_url),
        registry=registry,
        output_queue=build_event_queue(redis_url, output_stream),
    )


async def _transcription_worker() -> None:
    redis_url, _, _ = _required_environment()
    audio_queue = build_event_queue(redis_url, os.getenv("AGENT_AUDIO_STREAM", "class:audio:chunks"))
    transcript_queue = build_event_queue(redis_url, os.getenv("AGENT_INPUT_STREAM", "class:transcript:chunks"))
    transcriber = GeminiTranscriber()
    while True:
        event = await audio_queue.consume()
        try:
            text = await asyncio.to_thread(transcriber.transcribe, event["audio_b64"], event["mime_type"])
            if event.get("dispatch_mode", "auto") == "manual":
                await transcript_queue.publish({
                    "type": "transcription_ready",
                    "session_id": event["session_id"],
                    "tenant_id": event["tenant_id"],
                    "actor_user_id": event.get("actor_user_id"),
                    "text": text,
                })
                continue
            await transcript_queue.publish({
                "type": "transcript_chunk",
                "session_id": event["session_id"],
                "tenant_id": event["tenant_id"],
                "actor_user_id": event.get("actor_user_id"),
                "raw_text": text,
                "provider_event_id": event.get("stream_id"),
                "priority": event.get("priority", "normal"),
            })
        except Exception:
            logger.exception("audio_transcription_failed session_id=%s", event.get("session_id"))


async def _run() -> None:
    loop = build_production_loop()
    worker = asyncio.create_task(loop.run_forever())
    transcription_worker = asyncio.create_task(_transcription_worker())
    heartbeat = asyncio.create_task(_heartbeat(loop))
    stop_event = asyncio.Event()

    def request_shutdown() -> None:
        logger.info("agent_worker_shutdown_requested")
        stop_event.set()
        loop.stop()
        worker.cancel()
        transcription_worker.cancel()
        heartbeat.cancel()

    event_loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            event_loop.add_signal_handler(signum, request_shutdown)
        except NotImplementedError:
            signal.signal(signum, lambda *_: request_shutdown())

    try:
        await asyncio.gather(worker, stop_event.wait())
    except asyncio.CancelledError:
        worker.cancel()
        transcription_worker.cancel()
        heartbeat.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await asyncio.gather(transcription_worker, return_exceptions=True)
        await asyncio.gather(heartbeat, return_exceptions=True)
        raise


async def _heartbeat(loop: AgentLoop) -> None:
    import time

    redis_url, input_stream, output_stream = _required_environment()
    import redis

    client = redis.from_url(redis_url, decode_responses=True)
    key = f"agents:worker:heartbeat:{os.getpid()}"
    try:
        while True:
            client.hset(key, mapping={
                "status": "running",
                "pid": str(os.getpid()),
                "input_stream": input_stream,
                "output_stream": output_stream,
                "processed_events": str(loop.processed_events),
                "failed_events": str(loop.failed_events),
                "updated_at": str(int(time.time())),
            })
            client.expire(key, 30)
            await asyncio.sleep(10)
    finally:
        client.delete(key)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("agent_worker_stopped")


if __name__ == "__main__":
    main()
