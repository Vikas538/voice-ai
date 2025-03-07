import json
import redis
from typing import Annotated,Callable
from livekit.agents import llm
import logging
import aiohttp
import types
import functools
import inspect
from dataclasses import dataclass

logger = logging.getLogger("llm_actions")

class _UseDocMarker:
    pass

@dataclass(frozen=True)
class _AIFncMetadata:
    name: str
    description: str
    auto_retry: bool


METADATA_ATTR = "__livekit_ai_metadata__"
USE_DOCSTRING = _UseDocMarker()


def dynamic_ai_callable(*, name=None, description=None, auto_retry=False):
    """Custom decorator that dynamically applies @llm.ai_callable()"""
    
    def decorator(f):
        print(f"🔹 Wrapping function: {f.__name__}")
        sig = inspect.signature(f)

        # Apply @llm.ai_callable directly
        @llm.ai_callable(name=name, description=description, auto_retry=auto_retry)
        @functools.wraps(f)
        async def wrapped(self, *args, **kwargs):
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()

            return await f(*bound_args.args, **bound_args.kwargs)

        return wrapped

    return decorator



import types

def _set_metadata(
    f: Callable,
    name: str | None = None,
    desc: str | _UseDocMarker = USE_DOCSTRING,
    auto_retry: bool = False,
) -> None:
    """Attach AI metadata to a function, ensuring that bound methods are handled correctly."""
    
    # If `f` is a bound method, get its original function
    if isinstance(f, types.MethodType):
        f = f.__func__  # Unbind method to get the actual function
    
    if isinstance(desc, _UseDocMarker):
        docstring = inspect.getdoc(f)
        if docstring is None:
            raise ValueError(
                f"Missing docstring for function {f.__name__}, "
                "use explicit description or provide docstring."
            )
        desc = docstring

    metadata = _AIFncMetadata(
        name=name or f.__name__, description=desc, auto_retry=auto_retry
    )

    setattr(f, METADATA_ATTR, metadata)  # ✅ Now it will work for both functions and bound methods



# class AssistantFnc(llm.FunctionContext):

#     def __init__(self):
#         super().__init__()
#         self.register_function(self.get_weather,"get weather action id is 1234567890")



#     def register_available_actions(self,actions:list,kb_id:str):
#         """Dynamically register only the available actions in Redis."""
#         print("actions===================>",actions)

#         for action in actions:
#             description = action.get("description") + "action id is " + action.get("id")
#             if action.get("type") == "SEND_EMAIL":  
#                 print("description===================>",description)
#                 self.register_function(self.get_weather,"get weather action id is 1234567890")

#             # if action.get("type") == "SEND_SMS":
#             #     self.register_function(self.send_sms_action_by_openai,description)
#             # if action.get("type") == "APPOINTMENT":
#             #     self.register_function(AssistantFnc.create_appointment_action_openai)
#             # if kb_id:
#             #     self.register_function(AssistantFnc.search_in_kb_action_openai)

        


#     def register_function(self, func: Callable, description: str):
#         func_name = func.__name__

#         # Check if function is already registered
#         if func_name in self.ai_functions:
#             print(f"⚠️ Function '{func_name}' is already registered. Skipping re-registration.")
#             return  # Prevent duplicate registration

#         print(f"Registering function: {func_name}, description: {description}")

#         _set_metadata(func, name=func_name, desc=description, auto_retry=True)

#         self._register_ai_function(func)  # Registers with the AI system

#         setattr(self, func_name, func)  # Dynamically attach function

#         print(f"✅ Function '{func_name}' registered successfully!")


    

#     async def send_email(
#         self,
#         to_email: Annotated[str, llm.TypeInfo(description="Recipient email")],
#         subject: Annotated[str, llm.TypeInfo(description="Email subject")],
#         body: Annotated[str, llm.TypeInfo(description="Email body")],
#         action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
#     ):
#         """Send an email to a specified recipient."""
#         print("send_email==========================================>",to_email,subject,body,action_id)
#         logger.info(f"Sending email to {to_email} with subject {subject}")
#         return f"Email sent to {to_email} with subject: {subject}"
    

#     async def get_weather(
#         self,
#         # by using the Annotated type, arg description and type are available to the LLM
#         location: Annotated[
#             str, llm.TypeInfo(description="The location to get the weather for")
#         ],
#     ):
#         """Called when the user asks about the weather. This function will return the weather for the given location."""
#         logger.info(f"getting weather for {location}")
#         url = f"https://wttr.in/{location}?format=%C+%t"
#         async with aiohttp.ClientSession() as session:
#             async with session.get(url) as response:
#                 if response.status == 200:
#                     weather_data = await response.text()
#                     # response from the function call is returned to the LLM
#                     # as a tool response. The LLM's response will include this data
#                     return f"The weather in {location} is {weather_data}."
#                 else:
#                     raise f"Failed to get weather data, status code: {response.status}"

#     @staticmethod
#     async def send_sms_action_by_openai(
#         to_number: Annotated[str, llm.TypeInfo(description="Recipient phone number")],
#         message: Annotated[str, llm.TypeInfo(description="SMS body")],
#         action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
#     ):
#         """Send an SMS message to a recipient."""
#         logger.info(f"Sending SMS to {to_number}: {message}")
#         return f"SMS sent to {to_number}: {message}"

#     @staticmethod
#     @llm.ai_callable()
#     async def fetch_slots_action_openai(
#         timezone: Annotated[str, llm.TypeInfo(description="Timezone for fetching slots")],
#         block_date: Annotated[str, llm.TypeInfo(description="Date in YYYY-MM-DD format")],
#         timedelta: Annotated[str, llm.TypeInfo(description="Time delta in days")],
#         action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
#     ):
#         """Fetch available appointment slots based on provided details."""
#         logger.info(f"Fetching slots for date {block_date} in {timezone} with delta {timedelta}")
#         return f"Available slots for {block_date} in {timezone}: [10:00 AM, 2:00 PM, 4:00 PM]"

#     @staticmethod
#     async def create_appointment_action_openai(
#         length: Annotated[str, llm.TypeInfo(description="Appointment length (15m, 30m, 45m, 1hr)")],
#         nl_date_time: Annotated[str, llm.TypeInfo(description="Natural language date and time")],
#         timezone: Annotated[str, llm.TypeInfo(description="Timezone of the appointment")],
#         email: Annotated[str, llm.TypeInfo(description="Email to send confirmation")],
#         title: Annotated[str, llm.TypeInfo(description="Title of the appointment")],
#         description: Annotated[str, llm.TypeInfo(description="Description of the appointment")],
#         action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
#     ):
#         """Book an appointment for the user based on the given details."""
#         logger.info(f"Creating appointment '{title}' on {nl_date_time} for {email}")
#         return f"Appointment '{title}' booked for {email} on {nl_date_time}"

#     @staticmethod
#     async def search_in_kb_action_openai(
#         query: Annotated[str, llm.TypeInfo(description="User query for KB search")],
#     ):
#         """Search the internal knowledge base for relevant information."""
#         logger.info(f"Searching KB for query: {query}")
#         return f"KB search results for '{query}': [Relevant Info 1, Relevant Info 2]"



class AssistantFnc(llm.FunctionContext):
    # the llm.ai_callable decorator marks this function as a tool available to the LLM

    # by default, it'll use the docstring as the function's description
    @llm.ai_callable()
    async def get_weather(
        self,
        # by using the Annotated type, arg description and type are available to the LLM
        location: Annotated[
            str, llm.TypeInfo(description="The location to get the weather for")
        ],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
    ):
        print("action_id==================================================>",action_id)
        """Called when the user asks about the weather. This function will return the weather for the given location."""
        logger.info(f"getting weather for {location}")
        url = f"https://wttr.in/{location}?format=%C+%t"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    weather_data = await response.text()
                    # response from the function call is returned to the LLM
                    # as a tool response. The LLM's response will include this data
                    return f"The weather in {location} is {weather_data}."
                else:
                    raise f"Failed to get weather data, status code: {response.status}"
                
    @llm.ai_callable()
    async def send_email(
        self,
        # by using the Annotated type, arg description and type are available to the LLM
        to_email: Annotated[
            str, llm.TypeInfo(description="Recipient email")
        ],
        subject: Annotated[str, llm.TypeInfo(description="Email subject")],
        body: Annotated[str, llm.TypeInfo(description="Email body")],
        action_id: Annotated[str, llm.TypeInfo(description="Action ID")],
    ):
        """Called when the user asks about the weather. This function will return the weather for the given location."""
        logger.info(f"------------------------------------------------------->sending email to {to_email} with subject {subject} and body {body} and action id is {action_id}")
        return f"Email sent to {to_email} with subject: {subject}"

# fnc_ctx = AssistantFnc()


