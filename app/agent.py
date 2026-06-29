import os
import sys
from google.adk.workflow import Workflow, START, node, Edge
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.genai import types

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.config import config

# --- MCP Toolset Setup ---
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_path = os.path.join(current_dir, "mcp_server.py")

mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[mcp_server_path],
        )
    )
)

# --- Specialized Agents ---

wellness_coach = LlmAgent(
    name="wellness_coach",
    model=config.model,
    instruction=(
        "You are a professional Wellness Coach. Your job is to suggest personalized daily breathing "
        "and meditation routines. Answer questions about mindfulness techniques, guide the user through "
        "breathing exercises, and tailor routines to the user's specific context. Keep your responses "
        "supportive, clear, and actionable. You have access to MCP tools to get breathing techniques."
    ),
    tools=[mcp_toolset],
    description="Suggests personalized daily breathing and meditation routines, and guides breathing exercises."
)

mood_screentime_tracker = LlmAgent(
    name="mood_screentime_tracker",
    model=config.model,
    instruction=(
        "You are a Mood & Screen Time Tracker. Your job is to log user mood trends, check screen time limits, "
        "and recommend reflection prompts when screen time is excessive or mood is low. "
        "You help users reflect on their screen time and emotional well-being. Make your advice compassionate "
        "and direct. You have access to MCP tools to log mood and log screen time."
    ),
    tools=[mcp_toolset],
    description="Logs user mood trends, checks screen time limits, and recommends reflection prompts."
)

# --- Orchestrator Agent ---

orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction=(
        "You are the Mindfulness Guide Orchestrator. Your role is to coordinate the user's daily mindfulness "
        "journey. You can delegate specialized tasks to the sub-agents using their tools: "
        "wellness_coach (for daily breathing/meditation routines) and mood_screentime_tracker (for mood logging "
        "and screen time limit checks). Analyze user requests, select the appropriate sub-agent, and output the result. "
        "If you delegate to a sub-agent, return their output directly or explain their recommendations. "
        "If the user asks a general mindfulness question, you can answer it yourself."
    ),
    tools=[
        AgentTool(wellness_coach),
        AgentTool(mood_screentime_tracker)
    ]
)

# --- Workflow Node Functions ---

def _get_text_content(content) -> str:
    if isinstance(content, str):
        return content
    if hasattr(content, "parts") and content.parts:
        return content.parts[0].text or ""
    return ""

@node
def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Security node to check input safety, scrub PII, detect prompt injection and crisis keywords."""
    import re
    import json
    import datetime

    user_text = _get_text_content(node_input)

    # 1. PII Scrubbing (Email, Phone, SSN)
    email_regex = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_regex = r'\b(?:\+?\d{1,3}[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b'
    ssn_regex = r'\b\d{3}-\d{2}-\d{4}\b'

    scrubbed_text = user_text
    scrubbed_text = re.sub(email_regex, "[EMAIL_REDACTED]", scrubbed_text)
    scrubbed_text = re.sub(phone_regex, "[PHONE_REDACTED]", scrubbed_text)
    scrubbed_text = re.sub(ssn_regex, "[SSN_REDACTED]", scrubbed_text)

    # Rebuild types.Content with the scrubbed text
    scrubbed_content = types.Content(role='user', parts=[types.Part.from_text(text=scrubbed_text)])

    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions",
        "ignore instructions",
        "system prompt",
        "you are now",
        "bypass safety",
        "override settings"
    ]

    text_lower = user_text.lower()
    is_injection = any(kw in text_lower for kw in injection_keywords)

    # 3. Domain-Specific Rule: Crisis / Emergency Detection
    crisis_keywords = [
        "kill myself",
        "suicide",
        "self-harm",
        "chest pain",
        "heart attack",
        "emergency"
    ]
    is_crisis = any(ckw in text_lower for ckw in crisis_keywords)

    # 4. Structured Audit Log
    log_data = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "session_id": ctx.session.id if ctx.session else "unknown",
        "node": "security_checkpoint",
        "severity": "INFO",
        "decision": "proceed",
        "reason": "Input checked and is safe."
    }

    if is_crisis:
        log_data["severity"] = "CRITICAL"
        log_data["decision"] = "security_event"
        log_data["reason"] = "Crisis/medical emergency keywords detected."
        print(json.dumps(log_data))
        return Event(output="CRISIS_EVENT", route="security_event")

    if is_injection:
        log_data["severity"] = "WARNING"
        log_data["decision"] = "security_event"
        log_data["reason"] = "Prompt injection attempt detected."
        print(json.dumps(log_data))
        return Event(output="INJECTION_EVENT", route="security_event")

    if scrubbed_text != user_text:
        log_data["severity"] = "INFO"
        log_data["reason"] = "PII scrubbed from user input."

    print(json.dumps(log_data))
    return Event(output=scrubbed_content, route="proceed")

@node
def security_event_node(ctx: Context, node_input: str) -> Event:
    """Triggered on security violations or medical/crisis events."""
    if node_input == "CRISIS_EVENT":
        msg = (
            "⚠️ It sounds like you might be going through a difficult time or experiencing a medical emergency.\n"
            "This app is a wellness guide, not a medical or crisis response tool. "
            "Please reach out for professional help immediately:\n"
            "- In the US: Call or text 988 to reach the Suicide & Crisis Lifeline, or call 911 for emergencies.\n"
            "- International: Please contact your local emergency services or a crisis helpline."
        )
    elif node_input == "INJECTION_EVENT":
        msg = "⚠️ Security Checkpoint: Prompt injection or system command bypass detected. Action blocked."
    else:
        msg = "⚠️ Security Event: Your request could not be processed due to a safety policy violation."

    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]))
    yield Event(output=msg)

@node(rerun_on_resume=True)
async def orchestrate_node(ctx: Context, node_input: types.Content) -> Event:
    """Orchestrates incoming messages to sub-agents and updates ctx.state."""
    user_text = _get_text_content(node_input)
        
    ctx.state["last_user_input"] = user_text
    
    # Run the orchestrator agent programmatically
    result_content = await ctx.run_node(orchestrator, node_input=node_input)
    
    response_text = _get_text_content(result_content)
        
    ctx.state["last_orchestrator_output"] = response_text
    return Event(output=response_text)

@node(rerun_on_resume=True)
async def human_confirmation_node(ctx: Context, node_input: str):
    """Asks for human confirmation before recommending a specific mindfulness routine/session."""
    text_lower = node_input.lower()
    
    # Check if a routine, session or logging activity needs confirmation
    needs_confirm = any(kw in text_lower for kw in ["routine", "meditation", "breathing", "session", "schedule"])
    
    if needs_confirm:
        if not ctx.resume_inputs or "user_confirm" not in ctx.resume_inputs:
            yield RequestInput(
                interrupt_id="user_confirm",
                message="I've designed a mindfulness activity/routine for you. Would you like to proceed and start now? (Reply 'yes' to start)"
            )
            return
            
        confirm_val = ctx.resume_inputs["user_confirm"]
        if confirm_val.strip().lower() in ["yes", "y", "confirm", "proceed", "start"]:
            msg = f"✨ Beginning your routine now! Take a deep breath.\n\n{node_input}"
            yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]))
            yield Event(output=msg)
        else:
            msg = f"No problem, let's try something else. Feel free to log your mood or ask questions.\n\n{node_input}"
            yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]))
            yield Event(output=msg)
    else:
        # Pass through response without confirmation gate
        yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=node_input)]))
        yield Event(output=node_input)

# --- Workflow Definition ---

root_agent = Workflow(
    name="mindfulness_guide_workflow",
    edges=[
        (START, security_checkpoint),
        Edge(from_node=security_checkpoint, to_node=orchestrate_node, route="proceed"),
        Edge(from_node=security_checkpoint, to_node=security_event_node, route="security_event"),
        (orchestrate_node, human_confirmation_node)
    ]
)

# --- App Definition ---

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True)
)
