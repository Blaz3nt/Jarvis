import time
from datetime import datetime
import anthropic
import config
from tools import TOOL_DEFINITIONS, execute_tool


# Initialize the Anthropic client
client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Conversation history for memory
conversation_history = []


def _trim_history():
    """Keep conversation history within budget to minimize token usage."""
    max_msgs = config.MAX_HISTORY_MESSAGES
    if len(conversation_history) > max_msgs:
        # Always trim in pairs (user/assistant) to keep valid alternation
        trim_count = len(conversation_history) - max_msgs
        trim_count = trim_count + (trim_count % 2)  # round up to even
        del conversation_history[:trim_count]


def ask(user_message):
    """Send a message to Claude with tool_use support and conversation memory.

    Returns the final text response after any tool calls are resolved.
    Uses Haiku by default for low cost (~$0.25/1M input, $1.25/1M output).
    """
    _trim_history()

    # Add context about current time (compact format)
    now = datetime.now().strftime("%H:%M %m/%d")
    enriched_message = f"[{now}] {user_message}"

    conversation_history.append({
        "role": "user",
        "content": enriched_message,
    })

    # Agentic loop: keep calling Claude until we get a final text response
    while True:
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            system=config.SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=conversation_history,
        )

        # Collect the full response content
        assistant_content = response.content
        conversation_history.append({
            "role": "assistant",
            "content": assistant_content,
        })

        # Check if Claude wants to use tools
        tool_uses = [block for block in assistant_content if block.type == "tool_use"]

        if not tool_uses:
            # No tool calls — extract the text response
            text_parts = [block.text for block in assistant_content if block.type == "text"]
            return " ".join(text_parts)

        # Execute each tool and send results back
        tool_results = []
        for tool_use in tool_uses:
            print(f"  [Tool: {tool_use.name}({tool_use.input})]")
            result = execute_tool(tool_use.name, tool_use.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": str(result),
            })

        conversation_history.append({
            "role": "user",
            "content": tool_results,
        })
        # Loop back to let Claude process the tool results


def clear_history():
    """Clear conversation history."""
    conversation_history.clear()
