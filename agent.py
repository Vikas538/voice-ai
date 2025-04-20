import logging
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from livekit.api import RoomParticipantIdentity

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
from livekit.plugins import cartesia, openai, deepgram, silero, turn_detector, azure, google, playai, elevenlabs, speechmatics
from redis_utils import get_config_by_room_id
from glocal_vaiables import conversation_log, ctx_agents
from llm_actions import AssistantFnc

from livekit.agents.llm import ChatMessage

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")

from livekit.api import LiveKitAPI

# Will read LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET from environment variables



def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


def get_llm_class_by_model_name(model_name: str, api_key: str):
    if model_name == "gemini":
        return google.LLM(model="gemini-2.0-flash-exp", temperature="0.8", api_key=api_key)
    elif model_name == "openai":
        return openai.LLM(model="gpt-4o-mini", api_key=api_key)
    elif model_name == "groq":
        return openai.LLM.with_groq(model="llama3-8b-8192", api_key=api_key)
    elif model_name == "deepseek":
        return openai.LLM.with_deepseek(model="deepseek-chat", api_key=api_key)
    elif model_name == "perplexity":
        return openai.LLM.with_perplexity(model="llama-3.1-sonar-small-128k-chat", api_key=api_key)


def get_stt_class(model_name: str, api_key: str):
    if model_name == "deepgram":
        return deepgram.STT()
    elif model_name == "groq":
        return openai.STT.with_groq(model="whisper-large-v3", language="en", api_key=api_key)
    elif model_name == "azure":
        return azure.STT(speech_key=api_key, speech_region="centralus")
    elif model_name == "speechmatics":
        return speechmatics.STT(connection_settings=speechmatics.ConnectionSettings(url="wss://eu2.rt.speechmatics.com/v2", api_key=api_key))


def get_tts_class(model_name: str, voice_config: dict):
    if model_name == "azure":
        return azure.TTS(speech_key=voice_config.get("api_key"), speech_region="centralus")
    elif model_name == "cartesia":
        return cartesia.TTS(api_key=voice_config.get("api_key"), voice=voice_config.get("voice_id"),
                            speed=voice_config.get("speed"), emotion=voice_config.get("emotions"))
    elif model_name == "playht":
        return playai.TTS(api_key=voice_config.get("api_key"), voice=voice_config.get("voice_id"),
                          language=voice_config.get("language"))
    elif model_name == "elevenlabs":
        return elevenlabs.tts.TTS(
            model="eleven_turbo_v2_5",
            api_key=voice_config.get("api_key"),
            voice=elevenlabs.tts.Voice(
                id=voice_config.get("voice_id"),
                name="jessica",
                category="premade"
            ),
            language="en",
            streaming_latency=3,
            enable_ssml_parsing=False,
            chunk_length_schedule=[80, 120, 200, 260],
        )


async def shutdown_callback(ctx: JobContext, usage_collector: metrics.UsageCollector):
    usage_summary = usage_collector.get_summary()
    if not conversation_log.get(ctx.room.name):
        return
    convsersations = []
    for log in conversation_log.get(ctx.room.name):
        convsersations.append({
            "role": log.role,
            "content": log.content
        })
    async with aiohttp.ClientSession() as session:
        await session.post(
            url=f"{os.getenv('BACKEND_URL')}/save/conversations",
            json={
                "conversations": convsersations,
                "session_id": ctx.room.name,
                "usage_summary": {
                    "llm_prompt_tokens": usage_summary.llm_prompt_tokens,
                    "llm_completion_tokens": usage_summary.llm_completion_tokens,
                    "tts_characters_count": usage_summary.tts_characters_count,
                    "stt_audio_duration": usage_summary.stt_audio_duration
                }
            }
        )
    conversation_log.pop(ctx.room.name, None)
    ctx.shutdown()


async def entrypoint(ctx: JobContext):
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    print("====================================>participant",participant.identity,participant.attributes,participant._info)

    metadata = json.loads(ctx.job.metadata)
    session_id = ctx.room.name

    if session_id.startswith("call-"):
        call_details = participant.attributes
        async with aiohttp.ClientSession() as session:
            async with session.post(url=f"{os.getenv('BACKEND_URL')}/voice/inbound", json={
                "from_number": call_details.get("sip.phoneNumber"),
                "to_number": call_details.get("sip.trunkPhoneNumber"),
                "call_sid": call_details.get("sip.twilio.callSid")
            }) as response:
                resp_data = await response.json()
                session_id = resp_data.get("data", {}).get("session_id", session_id)

    config = await get_config_by_room_id(session_id)
    config_json = json.loads(config)
    assistant_id = metadata.get("assistant_id")
    agent_config = config_json.get("agents_config", {}).get(str(assistant_id), {})
    assistant_config = agent_config
    system_prompt = assistant_config.get("system_prompt", "")
    support_agents = config_json.get("support_agents", []) or None

    support_agent_transfer_prompt = ""
    if support_agents:
        for agent in support_agents:
            if str(agent.get("assistant_id")) == str(assistant_id):
                continue
            support_agent_transfer_prompt += "\n\n" + (
                f"When a user asks {agent['trigger']},\n"
                f"say {agent['transfer_text']}\n"
                f"Use transfer_to_agent tool to transfer to assistant {agent['assistant_id']}"
            )
    system_prompt += support_agent_transfer_prompt

    actions = assistant_config.get("actions", [])
    kb_id = assistant_config.get("kb_id", "")
    tts_config = assistant_config.get("synthesizer", {})
    stt_config = assistant_config.get("transcriber", {})
    agent_model_config = assistant_config.get("agent", {})
    reminder_config = agent_model_config.get("additional_settings", {}).get("reminder", {})

    print("====================================>remainder_config",agent_model_config.get("additional_settings", {}))
    print("====================================>remainder_config",agent_model_config.get("additional_settings", {}).get("reminder", {}))
    llm_class = get_llm_class_by_model_name(agent_model_config.get("model"), agent_model_config.get("api_key"))
    stt_class = get_stt_class(stt_config.get("model"), stt_config.get('api_key'))
    tts_class = get_tts_class(tts_config.get("model"), tts_config)

    initial_message = agent_model_config.get("additional_settings", {}).get("initial_message", "Hello, how can I help you today?")
    reminder_messages = reminder_config.get("reminder_messages", [])
    message_before_termination = reminder_config.get("message_before_termination", "Thanks, goodbye!")
    max_call_duration = reminder_config.get("max_call_duration", 300)
    allowed_idle_time_seconds = reminder_config.get("allowed_idle_time_seconds", 30)
    num_check_human_present_times = reminder_config.get("num_check_human_present_times", 3)

    print("====================================>metadata",metadata)

    if metadata.get("change_assistant"):
        initial_ctx = llm.ChatContext().append(
            role="system",
            text=f"You are a helpful assistant transferred from another agent. Past conversation: {json.dumps(metadata.get('conversation_log'))} Continue the chat. {system_prompt}"
        )
    else:
        initial_ctx = llm.ChatContext().append(
            role="system",
            text=system_prompt
        )

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=stt_class,
        llm=llm_class,
        tts=tts_class,
        turn_detector=turn_detector.EOUModel(),
        min_endpointing_delay=0.3,
        max_endpointing_delay=3.0,
        chat_ctx=initial_ctx,
        fnc_ctx=AssistantFnc(actions=actions, kb_id=kb_id, session_id=session_id, ctx=ctx, support_agents=support_agents)
    )

    usage_collector = metrics.UsageCollector()
    ctx.add_shutdown_callback(lambda reason: shutdown_callback(ctx, usage_collector))

    @agent.on("metrics_collected")
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        metrics.log_metrics(agent_metrics)
        usage_collector.collect(agent_metrics)

    @agent.on("user_speech_committed")
    def on_user_speech_committed(user_msg: ChatMessage):
        if ctx.room.name not in conversation_log:
            conversation_log[ctx.room.name] = []
        conversation_log[ctx.room.name].append(user_msg)

    @agent.on("agent_speech_committed")
    def on_agent_speech_committed(agent_msg: ChatMessage):
        if ctx.room.name not in conversation_log:
            conversation_log[ctx.room.name] = []
        conversation_log[ctx.room.name].append(agent_msg)

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        logger.info(f"Participant disconnected: {participant.identity}")

    agent.start(ctx.room, participant)

    # Save session details
    global ctx_agents
    ctx_agents[session_id] = {
        "ctx": ctx,
        "agent": agent,
        "stt": stt_class,
        "tts": tts_class,
        "llm": llm_class,
        "participant": participant
    }

    logger.info(f"Session initialized: {session_id}")

    await agent.say(initial_message, allow_interruptions=True)

    async def del_room():
        print("====================================>del_room")
        async with LiveKitAPI() as lkapi:
            await lkapi.room.remove_participant(RoomParticipantIdentity(
                room=ctx.room.name,
                identity=participant.identity
            ))

    # Monitor silence and auto-end if user inactive
    async def monitor_user_activity():
        silence_timeout = int(allowed_idle_time_seconds)
        max_repeats = num_check_human_present_times
        prompt_message = reminder_messages[0]
        final_message = message_before_termination
    
        last_user_activity = datetime.now()
        repeat_count = 0
    
        is_user_speaking = False
        is_agent_speaking = False
    
        @agent.on("user_speech_committed")
        def on_user_speech(user_msg):
            nonlocal last_user_activity
            last_user_activity = datetime.now()
            print("[Monitor] User speech committed. Updated last activity.")
    
        @agent.on("user_started_speaking")
        def on_user_started():
            nonlocal is_user_speaking
            is_user_speaking = True
            print("[Monitor] User started speaking.")
    
        @agent.on("user_stopped_speaking")
        def on_user_stopped():
            nonlocal is_user_speaking, last_user_activity
            is_user_speaking = False
            last_user_activity = datetime.now()
            print("[Monitor] User stopped speaking.")
    
        @agent.on("agent_started_speaking")
        def on_agent_started():
            nonlocal is_agent_speaking
            is_agent_speaking = True
            print("[Monitor] Agent started speaking.")
    
        @agent.on("agent_stopped_speaking")
        def on_agent_stopped():
            nonlocal is_agent_speaking, last_user_activity
            is_agent_speaking = False
            last_user_activity = datetime.now()
            print("[Monitor] Agent stopped speaking.")
    
        while True:
            await asyncio.sleep(5)
            
            if is_user_speaking or is_agent_speaking:
                # Active speech detected, reset timer logic or skip
                print("[Monitor] Skipping reminder check: Someone is speaking.")
                continue
            
            time_since_last = (datetime.now() - last_user_activity).total_seconds()
            print(f"[Monitor] Silence detected. Idle time: {time_since_last:.2f}s")
    
            if time_since_last > silence_timeout:
                if repeat_count < max_repeats:
                    await agent.say(prompt_message, allow_interruptions=True)
                    repeat_count += 1
                    last_user_activity = datetime.now()
                else:
                    print("[Monitor] Max reminders reached. Saying final message and ending session.")
                    task = asyncio.create_task(agent.say(final_message, allow_interruptions=False))
                    task.add_done_callback(lambda _: asyncio.create_task(del_room()))
                    break
                


    async def timeout_and_close_call():
        final_message = assistant_config.get("final_message", "Thanks, goodbye!")
        try:
            task = asyncio.create_task(agent.say(final_message, allow_interruptions=False))
            task.add_done_callback(lambda _: asyncio.create_task(del_room()))
        except Exception as e:
            logger.error(f"Error closing call: {e}")

    asyncio.create_task(monitor_user_activity())
    asyncio.create_task(asyncio.sleep(max_call_duration*60)).add_done_callback(lambda _: asyncio.create_task(timeout_and_close_call()))


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            agent_name="voice_agent",
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm
        ),
    )
