import json
import redis
from typing import Annotated,Callable
from livekit.agents import llm
import logging


logger = logging.getLogger("llm_actions")



class AssistantFnc(llm.FunctionContext):
    def __init__(self,actions:list,kb_id:str):
        super().__init__()
        self.actions = actions
        self.kb_id = kb_id
        self.register_available_actions()


    def register_available_actions(self):
        """Dynamically register only the available actions in Redis."""
        if "send_email_action_openai" in self.actions:
            self.register_function(self.send_email_action_openai)
        if "send_sms_action_by_openai" in self.actions:
            self.register_function(self.send_sms_action_by_openai)
        if "fetch_slots_action_openai" in self.actions:
            self.register_function(self.fetch_slots_action_openai)
        if "create_appointment_action_openai" in self.actions:
            self.register_function(self.create_appointment_action_openai)
        if self.kb_id:
            self.register_function(self.search_in_kb_action_openai)

        logger.info(f"Registered functions: {list(self.actions.keys())}")

    def register_function(self, func: Callable):
        """Registers a function dynamically with @llm.ai_callable()."""
        llm.ai_callable()(func)

    async def send_email_action_openai(
        self,
        to_email: Annotated[str, llm.TypeInfo(description="Recipient email")],
        subject: Annotated[str, llm.TypeInfo(description="Email subject")],
        body: Annotated[str, llm.TypeInfo(description="Email body")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
    ):
        """Send an email to a specified recipient."""
        logger.info(f"Sending email to {to_email} with subject {subject}")
        return f"Email sent to {to_email} with subject: {subject}"

    async def send_sms_action_by_openai(
        self,
        to_number: Annotated[str, llm.TypeInfo(description="Recipient phone number")],
        message: Annotated[str, llm.TypeInfo(description="SMS body")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
    ):
        """Send an SMS message to a recipient."""
        logger.info(f"Sending SMS to {to_number}: {message}")
        return f"SMS sent to {to_number}: {message}"

    async def fetch_slots_action_openai(
        self,
        timezone: Annotated[str, llm.TypeInfo(description="Timezone for fetching slots")],
        block_date: Annotated[str, llm.TypeInfo(description="Date in YYYY-MM-DD format")],
        timedelta: Annotated[str, llm.TypeInfo(description="Time delta in days")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
    ):
        """Fetch available appointment slots based on provided details."""
        logger.info(f"Fetching slots for date {block_date} in {timezone} with delta {timedelta}")
        return f"Available slots for {block_date} in {timezone}: [10:00 AM, 2:00 PM, 4:00 PM]"

    async def create_appointment_action_openai(
        self,
        length: Annotated[str, llm.TypeInfo(description="Appointment length (15m, 30m, 45m, 1hr)")],
        nl_date_time: Annotated[str, llm.TypeInfo(description="Natural language date and time")],
        timezone: Annotated[str, llm.TypeInfo(description="Timezone of the appointment")],
        email: Annotated[str, llm.TypeInfo(description="Email to send confirmation")],
        title: Annotated[str, llm.TypeInfo(description="Title of the appointment")],
        description: Annotated[str, llm.TypeInfo(description="Description of the appointment")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
    ):
        """Book an appointment for the user based on the given details."""
        logger.info(f"Creating appointment '{title}' on {nl_date_time} for {email}")
        return f"Appointment '{title}' booked for {email} on {nl_date_time}"

    async def search_in_kb_action_openai(
        self,
        query: Annotated[str, llm.TypeInfo(description="User query for KB search")],
    ):
        """Search the internal knowledge base for relevant information."""
        logger.info(f"Searching KB for query: {query}")
        return f"KB search results for '{query}': [Relevant Info 1, Relevant Info 2]"



