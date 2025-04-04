import logging


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
from livekit.plugins import cartesia, openai, deepgram, silero, turn_detector,azure,google,playai,elevenlabs,speechmatics
from redis_utils import get_config_by_room_id
import os,json
from glocal_vaiables import conversation_log,ctx_agents


import aiohttp
import os

from llm_actions import AssistantFnc
from livekit.agents.llm import ChatMessage



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
    elif model_name == "speechmatics":
        return speechmatics.STT(connection_settings=speechmatics.ConnectionSettings(url="wss://eu2.rt.speechmatics.com/v2",api_key=api_key))
    
def get_tts_class(model_name:str,voice_config:dict):
    print("model_name",model_name)
    if model_name == "azure":
        return azure.TTS(speech_key=voice_config.get("api_key"),speech_region="centralus")
    elif model_name == "cartesia":
        return cartesia.TTS(api_key=voice_config.get("api_key"),voice=voice_config.get("voice_id"),speed=voice_config.get("speed"),emotion=voice_config.get("emotions"))
    elif model_name == "playht":
        return playai.TTS(api_key=voice_config.get("api_key"),voice=voice_config.get("voice_id"),language=voice_config.get("language"))
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



async def shutdown_callback(ctx: JobContext,usage_collector:metrics.UsageCollector):
    return
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
    print("====================================>ctx.job",ctx.job.metadata)
    

    # fnc_ctx = action_class.register_available_actions(actions=actions,kb_id=kb_id)



   

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    metadata = json.loads(ctx.job.metadata)

    if ctx.room.name and ctx.room.name.startswith("call-"):
        call_details = participant.attributes
        async with aiohttp.ClientSession() as session:
            async with session.post(url=f"{os.getenv('BACKEND_URL')}/voice/inbound",json={"from_number":call_details.get("sip.phoneNumber"),"to_number":call_details.get("sip.trunkPhoneNumber"),"call_sid":call_details.get("sip.twilio.callSid")}) as response:
                print(response)
                response = await response.json()
                print("response=======================>",response)
                session_id = response.get("data",{}).get("session_id")
                
    else:
        session_id = ctx.room.name
    # Wait for the first participant to connect
    print("participant=======================>",participant.attributes)
    logger.info(f"starting voice assistant for participant {participant.identity}")
    
    config = await get_config_by_room_id(session_id)
    config_json = json.loads(config)
    assistant_id = metadata.get("assistant_id")
    agent_config = config_json.get("agents_config", {})
    assistant_config = agent_config.get(str(assistant_id), {})
    system_prompt = assistant_config.get("system_prompt", "")
    support_agents = config_json.get("support_agents", []) or None
    support_agent_transfer_prompt = ""
    if support_agents:
        for agent in support_agents:
            print("====================================>agent",agent,assistant_id)
            if str(agent.get("assistant_id")) == assistant_id:
                continue
            support_agent_transfer_prompt += "\n\n " + (
            f'When a user asks {agent["trigger"]},\n'
            f'"say {agent["transfer_text"]}"'
            f'pass transfer_to_agent tool to transfer to another agent Assistant ID {agent["assistant_id"]}'
        ) 
    system_prompt += support_agent_transfer_prompt
    actions = assistant_config.get("actions", [])
    print("actions=======================>",actions)
    kb_id = assistant_config.get("kb_id", "")
    action_class = AssistantFnc(actions=actions,kb_id=kb_id,session_id=session_id,ctx=ctx,support_agents=support_agents)
    initial_message = config_json.get("initial_message", "Hey, how can I help you today?")
    agent_config = assistant_config.get("agent", {})
    tts_config = assistant_config.get("synthesizer", {})
    stt_config = assistant_config.get("transcriber", {})
    llm_class = get_llm_class_by_model_name(agent_config.get("model"),config_json.get("api_key"))
    stt_class = get_stt_class(stt_config.get("model"),stt_config.get('api_key'))
    tts_class = get_tts_class(tts_config.get("model"),tts_config)
    metadata = json.loads(ctx.job.metadata)
    print("====================================>metadata",metadata)
    if metadata.get("change_assistant") :

        initial_ctx = llm.ChatContext().append(
            role="system",
            text=f"You are a helpful assistant. You are currently in a conversation with a user. Tranferred to you from another agent. The conversation log is as follows: {json.dumps(metadata.get('conversation_log'))} you need to continue the conversation with the user. {system_prompt}",
        )
    else:
        initial_ctx = llm.ChatContext().append(
            role="system",
            text=system_prompt,
        )

    # This project is configured to use Deepgram STT, OpenAI LLM and Cartesia TTS plugins
    # Other great providers exist like Cerebras, ElevenLabs, Groq, Play.ht, Rime, and more
    # Learn more and pick the best one for your app:
    # https://docs.livekit.io/agents/plugins
    print("====================================>initial_ctx",initial_ctx)
    print("====================================>system_prompt",stt_class)
    print("====================================>tts_class",tts_class)
    print("====================================>llm_class",llm_class)
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
    ctx.add_shutdown_callback(lambda reason: shutdown_callback(ctx, usage_collector))

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

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        print("====================================>participant_disconnected",participant)
        print(f"Participant disconnected: {participant.identity}")



    agent.start(ctx.room, participant)

    # The agent should be polite and greet the user when it joins :)
    global ctx_agents
    ctx_agents[session_id] = {
        "ctx":ctx,
        "agent":agent,
        "stt":stt_class,
        "tts":tts_class,
        "llm":llm_class
    }

    print("====================================>session_id",session_id,ctx_agents)
    await agent.say(initial_message, allow_interruptions=True)



if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
             agent_name="voice_widget",
             
        ),
    )
