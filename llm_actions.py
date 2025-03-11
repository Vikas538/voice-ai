import json
from typing import Annotated
from livekit.agents import llm
import logging
import aiohttp
from dataclasses import dataclass
from datetime import datetime
import os
import re

logger = logging.getLogger("llm_actions")



from redis_utils import get_config_by_room_id

class AssistantFnc(llm.FunctionContext):
    def __init__(self,actions:list,kb_id:str,session_id:str):
    # First decorate and set class methods

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
            elif action.get("type") == "APPOINTMENT":
                appointment_func = llm.ai_callable(
                    name="create_appointment",
                    description=f"""If anyone asks for a meeting/appointment use this tool.make sure you have collected or know the email, date, time and timezone for booking using this appointment. 
            
            Note: You don't need to fetch the available slots to use this tool.
            If this tool not able to book in the requested time, it will return the other available slots for booking.Today's date and time in America/new_york is {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} and action_id = {action.get('id')} and session_id = {session_id}"""
                )(self.create_appointment.__func__)
                self.__class__.create_appointment = appointment_func
            elif action.get("type") == "SEARCH_KB":
                search_kb_func = llm.ai_callable(
                    name="search_kb",
                    description=f"Search the internal knowledge base for relevant information kb_id = {kb_id} and session_id = {session_id}"
                )(self.search_kb.__func__)
                self.__class__.search_kb = search_kb_func


        # Now call super().__init__() which will find and register our decorated methods
        super().__init__()
    
    # def register_functions(self):
    #     # Register get_weather function
    #     weather_func = llm.ai_callable(
    #         name="get_weather", 
    #         description="get weather action id is 1234567890"
    #     )(self.get_weather.__func__)

    #     self.__class__.get_weather = weather_func

        
    #     # Register send_email function
    #     email_func = llm.ai_callable(
    #         name="send_email",
    #         description="Send an email to the specified recipient"
    #     )(self.send_email.__func__)

    #     self.__class__.send_email = email_func

        
        # No need to return anything - the functions are registered in the parent class

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
    
    
# fnc_ctx = AssistantFnc()


