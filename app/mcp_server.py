from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("mindfulness-guide-mcp")

@mcp.tool()
def log_mood(mood: str, note: str = "") -> str:
    """Log the user's current mood and an optional note.
    
    Args:
        mood: The user's mood (e.g., happy, calm, stressed, anxious, tired).
        note: Optional context or explanation for the mood.
    """
    return f"Successfully logged mood: '{mood}' with note: '{note}'"

@mcp.tool()
def log_screentime(hours: float) -> str:
    """Log the user's screen time in hours and return a feedback message.
    
    Args:
        hours: Number of hours spent on screen.
    """
    if hours > 6:
        status = "⚠️ Screen time is high! Consider taking a break."
    else:
        status = "✅ Screen time is within healthy limits."
    return f"Logged {hours} hours. Status: {status}"

@mcp.tool()
def get_breathing_technique(mood: str) -> str:
    """Provide a guided breathing technique recommendation based on the user's current mood.
    
    Args:
        mood: The user's current mood (e.g. anxious, stressed, tired, calm).
    """
    m = mood.lower()
    if "anxious" in m or "panic" in m:
        return "4-7-8 Breathing: Inhale for 4s, hold for 7s, exhale for 8s. Repeat 4 times to calm the nervous system."
    elif "stress" in m or "overwhelm" in m:
        return "Box Breathing: Inhale for 4s, hold for 4s, exhale for 4s, hold for 4s. Repeat 4 times for focus and stress relief."
    elif "tired" in m or "sluggish" in m or "fatigue" in m:
        return "Bellows Breath (Bhastrika): Inhale and exhale rapidly through the nose for 15s to increase energy."
    else:
        return "Deep Belly Breathing: Slow, deep breaths into the abdomen. 5s inhale, 5s exhale. Repeat for 2 minutes."

if __name__ == "__main__":
    mcp.run(transport="stdio")
