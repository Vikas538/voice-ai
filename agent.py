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
from livekit.plugins import cartesia, openai, deepgram, silero, turn_detector,azure,google,playai,elevenlabs
from redis_utils import get_config_by_room_id
import os,json
conversation_log = {}


import aiohttp
from typing import Annotated

from livekit.agents import llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.agents.multimodal import MultimodalAgent
from livekit.agents.llm import ChatMessage

from llm_actions import AssistantFnc




load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

def get_llm_class_by_model_name(model_name:str,api_key:str):
    if model_name == "gemini":
        return google.LLM(
            model="gemini-2.0-flash-exp",
            temperature="0.8",
            api_key=api_key,
        )
    elif model_name == "openai":
        return openai.LLM(model="gpt-4o-mini",api_key=api_key)
    elif model_name == "groq":
        return openai.LLM.with_groq(model="llama3-8b-8192",api_key=api_key)
    elif model_name == "deepseek":
        return openai.LLM.with_deepseek(model="deepseek-chat",api_key=api_key)
    elif model_name == "perplexity":
        return openai.LLM.with_perplexity(model="llama-3.1-sonar-small-128k-chat",api_key=api_key)


def get_stt_class(model_name:str,api_key:str):
    if model_name == "deepgram":
        return deepgram.STT()
    elif model_name == "groq":
        return openai.STT.with_groq(model="whisper-large-v3", language="en",api_key=api_key)
    elif model_name == "azure":
        return azure.STT(speech_key=api_key,speech_region="centralus")
    
def get_tts_class(model_name:str,voice_config:dict):
    if model_name == "azure":
        return azure.TTS(speech_key=voice_config.get("api_key"),speech_region="centralus")
    elif model_name == "cartesia":
        return cartesia.TTS(api_key=voice_config.get("api_key"),voice=voice_config.get("voice_id"),speed=voice_config.get("speed"),emotion=voice_config.get("emotions"))
    elif model_name == "playht":
        return playai.TTS(api_key=voice_config.get("api_key"),voice=voice_config.get("voice_id"),language=voice_config.get("language"))
    elif model_name == "elevenlabs":
        return elevenlabs.tts.TTS(
    model="eleven_turbo_v2_5",
    voice=elevenlabs.tts.Voice(
        id="EXAVITQu4vr4xnSDxMaL",
        name="Bella",
        api_key=voice_config.get("api_key"),
        category="premade",
        settings=elevenlabs.tts.VoiceSettings(
            stability=0.71,
            similarity_boost=0.5,
            style=0.0,
            use_speaker_boost=True
        ),
    ),
    language="en",
    streaming_latency=3,
    enable_ssml_parsing=False,
    chunk_length_schedule=[80, 120, 200, 260],
)



async def shutdown_callback(ctx: JobContext,usage_collector:metrics.UsageCollector):
    print("====================================>shutdown",ctx)
    usage_summary = usage_collector.get_summary()
    print(ctx.room.name)
    convsersations = []
    print(conversation_log.get(ctx.room.name))
    if not conversation_log.get(ctx.room.name):
        return
    for log in conversation_log.get(ctx.room.name):
        print(log.role,log.content)
        convsersations.append({
            "role":log.role,
            "content":log.content
        })
    # if len is > 0 call api 
    print("BACKEND_URL",os.getenv("BACKEND_URL"))

    async with aiohttp.ClientSession() as session:
        async with session.post(url=f"{os.getenv('BACKEND_URL')}/save/conversations",json={"conversations":convsersations,"session_id":ctx.room.name,"usage_summary":{
            "llm_prompt_tokens":usage_summary.llm_prompt_tokens,
            "llm_completion_tokens":usage_summary.llm_completion_tokens,
            "tts_characters_count":usage_summary.tts_characters_count,
            "stt_audio_duration":usage_summary.stt_audio_duration
        }}) as response:
            print(response)
    
    conversation_log.pop(ctx.room.name)

    ctx.shutdown()

    return convsersations



async def entrypoint(ctx: JobContext):
    print(ctx.room)

    # fnc_ctx = action_class.register_available_actions(actions=actions,kb_id=kb_id)



   

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    config = await get_config_by_room_id(ctx.room.name)
    config_json = json.loads(config)
    system_prompt = config_json.get("system_prompt", "")
    actions = config_json.get("actions", [])
    print("actions=======================>",actions)
    kb_id = config_json.get("kb_id", "")
    action_class = AssistantFnc(actions=actions,kb_id=kb_id,session_id=ctx.room.name)
    initial_message = config_json.get("initial_message", "Hey, how can I help you today?")
    agent_config = config_json.get("agent", {})
    tts_config = config_json.get("synthesizer", {})
    stt_config = config_json.get("transcriber", {})
    llm_class = get_llm_class_by_model_name(agent_config.get("model"),config_json.get("api_key"))
    stt_class = get_stt_class(stt_config.get("model"),stt_config.get('api_key'))
    tts_class = get_tts_class(tts_config.get("model"),tts_config)
    initial_ctx = llm.ChatContext().append(
        role="system",
            text=system_prompt,
    )

    # This project is configured to use Deepgram STT, OpenAI LLM and Cartesia TTS plugins
    # Other great providers exist like Cerebras, ElevenLabs, Groq, Play.ht, Rime, and more
    # Learn more and pick the best one for your app:
    # https://docs.livekit.io/agents/plugins
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=stt_class,
        llm=llm_class,
        tts=tts_class,
        turn_detector=turn_detector.EOUModel(),
        # minimum delay for endpointing, used when turn detector believes the user is done with their turn
        min_endpointing_delay=0.3,
        # maximum delay for endpointing, used when turn detector does not believe the user is done with their turn
        max_endpointing_delay=3.0,
        chat_ctx=initial_ctx,
        fnc_ctx=action_class
    )

    # cp = ConversationPersistor(model=agent, log="log.txt")
    # cp.start()


    usage_collector = metrics.UsageCollector()
    ctx._shutdown_callbacks.append(lambda reason: shutdown_callback(ctx, usage_collector))

    @agent.on("metrics_collected")
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        metrics.log_metrics(agent_metrics)
        usage_collector.collect(agent_metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage:=========================================> ${summary}")

    @agent.on("user_speech_committed")
    def on_user_speech_committed(user_msg: ChatMessage):
        print("====================================>",user_msg)
        if ctx.room.name not in conversation_log:
            conversation_log[ctx.room.name] = []
        conversation_log[ctx.room.name].append(user_msg)

    @agent.on("agent_speech_committed")
    def on_agent_speech_committed(agent_msg: ChatMessage):
        print("====================================>",agent_msg,ctx.room.name)
        if ctx.room.name not in conversation_log:
            conversation_log[ctx.room.name] = []
        conversation_log[ctx.room.name].append(agent_msg)



    agent.start(ctx.room, participant)

    # The agent should be polite and greet the user when it joins :)
    await agent.say(initial_message, allow_interruptions=True)






if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
             agent_name="voice_widget2",
             
        ),
    )
