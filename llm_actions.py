import json
from typing import Annotated
from livekit.agents import llm
import logging
import aiohttp
from dataclasses import dataclass
from datetime import datetime
import os
from kb_search import similarity_search_with_score
import re
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.agents import (
    JobContext,
)
import asyncio

logger = logging.getLogger("llm_actions")



from redis_utils import get_config_by_room_id


class AssistantFnc(llm.FunctionContext):
    def __init__(self,actions:list,kb_id:str,session_id:str,ctx:JobContext,support_agents:list):
    # First decorate and set class methods
        print("====================================>support_agents",support_agents)

        for action in actions:
            # if action.get("type") == "SEND_EMAIL":
            #     weather_func = llm.ai_callable(
            #         name="get_weather", 
            #         description="get weather action id is 1234567890"
            #     )(self.get_weather.__func__)
            #     self.__class__.get_weather = weather_func
            if action.get("type") == "SEND_EMAIL":
                email_func = llm.ai_callable(
                    name="send_email",
                    description=f"Send an email to the specified recipient action_id = {action.get('id')} and session_id = {session_id}"
                )(self.send_email.__func__)
                self.__class__.send_email = email_func
            elif action.get("type") == "SEND_SMS":
                sms_func = llm.ai_callable(
                    name="send_sms",
                    description=f"Send an SMS to the specified recipient action_id = {action.get('id')} and session_id = {session_id}"
                )(self.send_sms.__func__)
                self.__class__.send_sms = sms_func
            
            elif action.get("type") == "CALL_TRANSFER":
                transfer_to_agent_func = llm.ai_callable(
                    name="transfer_to_agent",
                    description=f"Transfer call to a human agent phone_number = {action.get('phone_number')} and session_id = {session_id}"
                )(self.transfer_to_agent.__func__)
                self.__class__.transfer_to_agent = transfer_to_agent_func

            elif action.get("type") == "APPOINTMENT":
                appointment_func = llm.ai_callable(
                    name="create_appointment",
                    description=f"""If anyone asks for a meeting/appointment use this tool.make sure you have collected or know the email, date, time and timezone for booking using this appointment. 
            
            Note: You don't need to fetch the available slots to use this tool.
            If this tool not able to book in the requested time, it will return the other available slots for booking.Today's date and time in America/new_york is {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} and action_id = {action.get('id')} and session_id = {session_id}"""
                )(self.create_appointment.__func__)
                self.__class__.create_appointment = appointment_func
            if kb_id:
                search_kb_func = llm.ai_callable(
                    name="search_kb",
                    description=f"Search the internal knowledge base for relevant information kb_id = {kb_id} and session_id = {session_id}"
                )(self.search_kb.__func__)
                self.__class__.search_kb = search_kb_func
            if support_agents:
                transfer_to_agent_func = llm.ai_callable(
                    name="transfer_to_agent",
                    description=f"Transfer the conversation to the specified agent agent_id = {22} and session_id = {session_id}"
                )(self.transfer_to_agent.__func__)
                self.__class__.transfer_to_agent = transfer_to_agent_func
            

            close_call_func = llm.ai_callable(
                name="close_call",
                description=f"Close the call and session_id = {session_id} , should be only used if the idle time is more of user want to close the call"
            )(self.close_call.__func__)
            self.__class__.close_call = close_call_func



        # Now call super().__init__() which will find and register our decorated methods
        super().__init__()
    


    async def send_action_request(self,body:dict):
        config = await get_config_by_room_id(body.get("session_id"))
        config_json = json.loads(config)
        auth_key = config_json.get("auth_key")
        url = os.getenv("BACKEND_URL")
        if body.get("action_type") == "SEND_EMAIL":
            url = f"{url}/send-grid/send-email?assistant_id={config_json.get('assistant_id')}&action_id={body.get('action_id')}"
        elif body.get("action_type") == "SEND_SMS":
            url = f"{url}/external/send/sms?assistant_id={config_json.get('assistant_id')}&action_id={body.get('action_id')}"
        elif body.get("action_type") == "APPOINTMENT":
            url = f"{url}/integration/calendar_natural_language/block?assistant_id={config_json.get('assistant_id')}&action_id={body.get('action_id')}"
        print(url)
        print(body)
        headers = {"Authorization":f"{auth_key}","Content-Type":"application/json"}
        print(config_json.get("assistant_id"),config_json.get("auth_key"))
        request_body = {**body,"assistant_id":config_json.get("assistant_id")}
        print(request_body)
        async with aiohttp.ClientSession() as session:
            async with session.post(url=url,json=request_body,headers=headers) as response:
                return await response.json()

    async def get_weather(
        self,
        location: Annotated[str, llm.TypeInfo(description="The location to get the weather for")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
    ):
        """Called when the user asks about the weather. This function will return the weather for the given location."""
        print("action_id==================================================>", action_id)
        # Rest of your implementation...
                
    async def send_email(
        self,
        to_email: Annotated[str, llm.TypeInfo(description="Recipient email")],
        subject: Annotated[str, llm.TypeInfo(description="Email subject")],
        body: Annotated[str, llm.TypeInfo(description="Email body")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
        session_id: Annotated[str, llm.TypeInfo(description="Session ID")],
    ):
        """Called when the user asks to send an email."""
        logger.info(f"------------------------------------------------------->sending email to {to_email} and session_id = {session_id} and action_id = {action_id}")
        body = {
            "action_type":"SEND_EMAIL",
            "to_email":to_email,
            "subject":subject,
            "body":body,
            "action_id":action_id,
            "session_id":session_id
        }
        result = await self.send_action_request(body)
        print(result)
        return f"result: {json.dumps(result)}"
    
    async def send_sms(
        self,
        to_number: Annotated[str, llm.TypeInfo(description="Recipient phone number")],
        message: Annotated[str, llm.TypeInfo(description="SMS body")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
        session_id: Annotated[str, llm.TypeInfo(description="Session ID")],
    ):
        """Called when the user asks to send an SMS."""
        logger.info(f"------------------------------------------------------->sending sms to {to_number} and session_id = {session_id} and action_id = {action_id}")
        body = {
            "action_type":"SEND_SMS",
            "to_number":"+"+re.sub(r"\D", "", to_number),
            "message_body":message,
            "action_id":action_id,
            "session_id":session_id
        }
        result = await self.send_action_request(body)
        print(result)
        return f"result: {json.dumps(result)}"
    
    async def create_appointment(
        self,
        length: Annotated[str, llm.TypeInfo(description="Appointment length (15m, 30m, 45m, 1hr)")],
        nl_date_time: Annotated[str, llm.TypeInfo(description="""It is the Date and time at which the appointment has to be booked. You can send any specific Date(in formal MM-DD-YYYY) with time or yesterday/today strings with time. Example. "tomorrow 10:30 AM","today 10:30 PM", "10-01-2025 10:30 AM",etc.""")],
        timezone: Annotated[str, llm.TypeInfo(description="""timezone to book an appointment. Example: IST "Asia/Kolkata", PST "America/Los_Angeles" CST = "America/Chicago" EST = "America/New_York" """)],
        email: Annotated[str, llm.TypeInfo(description="Email to send confirmation")],
        title: Annotated[str, llm.TypeInfo(description="Title of the appointment")],
        description: Annotated[str, llm.TypeInfo(description="Description of the appointment")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
        session_id: Annotated[str, llm.TypeInfo(description="Session ID")],
    ):
        """Called when the user asks to create an appointment."""
        logger.info(f"------------------------------------------------------->creating appointment and session_id = {session_id} and action_id = {action_id}")
        body = {
            "action_type":"APPOINTMENT",
            "length":length,
            "nl_date_time":nl_date_time,
            "timezone":timezone,
            "email":email,
            "title":title,
            "description":description,
            "action_id":action_id,
            "session_id":session_id
        }
        result = await self.send_action_request(body)
        print(result)
        return f"result: {json.dumps(result)}"
    
    async def search_kb(
        self,
        query: Annotated[str, llm.TypeInfo(description="Query to search the knowledge base")],
        kb_id: Annotated[str, llm.TypeInfo(description="Knowledge base ID")],
    ):  
        """Called when the user asks to search the knowledge base."""
        logger.info(f"------------------------------------------------------->searching knowledge base and kb_id = {kb_id}")
        try:
    
            docs_with_scores = await similarity_search_with_score(query,{"kb_id":kb_id})
            docs_with_scores_str = "\n\n".join(
                [
                    "File source is : "
                    + "gs://" + doc[0].metadata.get("file_id", "Unknown Source")+ "\n\n [content]"
                    + f" (Confidence: {doc[1]})\n"
                    + doc[0].page_content.replace("\n", "\n")
                    for doc in docs_with_scores
                ]
            )
            vector_db_result = (
                f"Found {len(docs_with_scores)} similar documents:\n{docs_with_scores_str}"
            )
            print(vector_db_result)
            return {
                "data":vector_db_result,
                "file_id":None
            }
        except Exception as e:
            return {"message": str(e)}, 500
        
    async def transfer_to_agent(
        self,
        agent_id: Annotated[str, llm.TypeInfo(description="Agent ID")],
        session_id: Annotated[str, llm.TypeInfo(description="Session ID")],
    ):
        """Called when the user asks to transfer to another agent."""
        logger.info(f"------------------------------------------------------->transferring to agent and session_id = {session_id} ,agent_id = {agent_id}")
        from glocal_vaiables import ctx_agents
        session_context = ctx_agents.get(session_id)
        current_ctx = session_context["ctx"]
        current_agent = session_context["agent"]
        from glocal_vaiables import conversation_log
        convsersations = []
        for log in conversation_log.get(current_ctx.room.name):
            convsersations.append({
                "role":log.role,
                "content":log.content
            })
        

        from livekit.api import LiveKitAPI, CreateAgentDispatchRequest

        lkapi = LiveKitAPI(
                url=os.getenv("LIVEKIT_URL"),
                api_key=os.getenv("LIVEKIT_API_KEY"),
                api_secret=os.getenv("LIVEKIT_API_SECRET")
            )

        await lkapi.agent_dispatch.create_dispatch(
                    CreateAgentDispatchRequest(
                        agent_name="voice_widget3", room=session_id, metadata=json.dumps({"change_assistant":True,"conversation_log":json.dumps(convsersations),"assistant_id":agent_id,"session_id":session_id})
                    )
                )

        current_ctx.shutdown(reason="agent_transferred")

        # print("====================================>new_agent",new_agent)
        # asyncio.create_task(current_ctx.say("transferred you to our telsa expert", allow_interruptions=True))
        # new_agent.start(current_ctx.room, current_ctx.participant)

    async def transfer_to_phone_number( 
        self,
        phone_number: Annotated[str, llm.TypeInfo(description="Phone number to transfer the call to")],
        session_id: Annotated[str, llm.TypeInfo(description="Session ID")],
    ):
        """Called when the user asks to transfer the call to a different phone number."""
        logger.info(f"------------------------------------------------------->transferring to phone number and session_id = {session_id} ,phone_number = {phone_number}")
        from livekit.api import LiveKitAPI
        from livekit import rtc
        from glocal_vaiables import ctx_agents
        from livekit.protocol.sip import TransferSIPParticipantRequest
        from livekit.protocol.sip import TransferSIPParticipantRequest

        session_context = ctx_agents.get(session_id)
        participant:rtc.RemoteParticipant = session_context["participant"]
        async with LiveKitAPI() as lkapi:
            transfer_to = 'tel:+1'+re.sub(r"\D", "", phone_number)
            transfer_request = TransferSIPParticipantRequest(
                participant_identity=participant.identity,
                room_name=session_id,
                transfer_to=transfer_to,
                play_dialtone=False
            )
            logger.debug(f"Transfer request: {transfer_request}")

            # Transfer caller       
            await lkapi.sip.transfer_sip_participant(transfer_request)
            logger.info(f"Successfully transferred participant {participant.identity}")


    async def close_call(self,session_id:Annotated[str, llm.TypeInfo(description="Session ID")]):
        """Called when the user asks to close the call."""
        logger.info(f"------------------------------------------------------->closing call and session_id = {session_id}")
        from glocal_vaiables import ctx_agents
        from livekit.api import LiveKitAPI
        from livekit.api import DeleteRoomRequest
        session_context = ctx_agents.get(session_id)
        current_ctx:JobContext = session_context["ctx"]
        print("====================================>current_ctx",current_ctx)
        async with LiveKitAPI() as lkapi:
            await lkapi.room.delete_room(DeleteRoomRequest(
                room=session_id
            ))
            await current_ctx.shutdown(reason="call_closed")
    
    



