import logging
from redis.asyncio import Redis

from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    metrics,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import cartesia, openai, deepgram, silero, turn_detector,azure
from redis_utils import get_config_by_room_id
import os,json


import aiohttp
from typing import Annotated

from livekit.agents import llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.agents.multimodal import MultimodalAgent


# from llm_actions import AssistantFnc


# Initialize the Assistant Context


load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    print(ctx.room)
    config = await get_config_by_room_id("c78c8925-c88f-4512-a872-e964f19f2ab8")
    config_json = json.loads(config)
    print("config_json==================================================>",config_json.get("api_key"))
    system_prompt = config_json.get("system_prompt", "")
    actions = config_json.get("actions", [])
    kb_id = config_json.get("kb_id", "")
    # action_class = AssistantFnc()

    # fnc_ctx = action_class.register_available_actions(actions=actions,kb_id=kb_id)
    # fnc_ctx = action_class


    initial_ctx = llm.ChatContext().append(
        role="system",
        text=system_prompt,
    )

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    # This project is configured to use Deepgram STT, OpenAI LLM and Cartesia TTS plugins
    # Other great providers exist like Cerebras, ElevenLabs, Groq, Play.ht, Rime, and more
    # Learn more and pick the best one for your app:
    # https://docs.livekit.io/agents/plugins
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini",api_key=config_json.get("openai_api_key")),
        tts=azure.TTS(
            speech_key="d667d32b10934e0084577bc79a258f68",
            speech_region="centralus",
            voice=config_json.get("voice_id","en-US-JennyNeural"),
        ),
        turn_detector=turn_detector.EOUModel(),
        # minimum delay for endpointing, used when turn detector believes the user is done with their turn
        min_endpointing_delay=0.5,
        # maximum delay for endpointing, used when turn detector does not believe the user is done with their turn
        max_endpointing_delay=5.0,
        chat_ctx=initial_ctx,
    )


    usage_collector = metrics.UsageCollector()

    @agent.on("metrics_collected")
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        metrics.log_metrics(agent_metrics)
        usage_collector.collect(agent_metrics)

    agent.start(ctx.room, participant)

    # The agent should be polite and greet the user when it joins :)
    await agent.say("Hey, how can I help you today?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
