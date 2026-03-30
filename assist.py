from datetime import datetime
import anthropic
import config
from tools import TOOL_DEFINITIONS, execute_tool
from memory import build_memory_context, save_conversation


# Initialize the Anthropic client
client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Conversation history (short-term memory — current session only)
conversation_history = []


def _trim_history():
    """Keep conversation history within budget to minimize token usage."""
    max_msgs = config.MAX_HISTORY_MESSAGES
    if len(conversation_history) > max_msgs:
        trim_count = len(conversation_history) - max_msgs
        trim_count = trim_count + (trim_count % 2)  # round up to even
        del conversation_history[:trim_count]


def ask(user_message):
    """Send a message to Claude with tool_use, memory injection, and conversation history.

    Before each call, relevant memories are pulled from:
    - Long-term facts (SQLite) — always included
    - Episodic memory (ChromaDB) — semantically matched to current topic

    Returns the final text response after any tool calls are resolved.
    """
    _trim_history()

    # Build memory context from long-term storage
    memory_context = build_memory_context(user_message)

    # Construct system prompt with memories injected
    system = config.SYSTEM_PROMPT
    if memory_context:
        system += f"\n\n{memory_context}"

    # Add timestamp
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
            system=system,
            tools=TOOL_DEFINITIONS,
            messages=conversation_history,
        )

        assistant_content = response.content
        conversation_history.append({
            "role": "assistant",
            "content": assistant_content,
        })

        tool_uses = [block for block in assistant_content if block.type == "tool_use"]

        if not tool_uses:
            text_parts = [block.text for block in assistant_content if block.type == "text"]
            return " ".join(text_parts)

        tool_results = []
        for tool_use in tool_uses:
            print(f"  [Tool: {tool_use.name}({tool_use.input})]")
            result = execute_tool(tool_use.name, tool_use.input)

            # Vision tools return image data — send as image content block
            if isinstance(result, dict) and result.get("__vision__"):
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": result["media_type"],
                                "data": result["image_base64"],
                            },
                        },
                        {
                            "type": "text",
                            "text": result.get("description", "Image captured"),
                        },
                    ],
                })
            else:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": str(result),
                })

        conversation_history.append({
            "role": "user",
            "content": tool_results,
        })


def end_conversation():
    """Call when a conversation ends (timeout/sleep).

    Saves an episode summary and extracts facts to long-term memory.
    Then clears short-term history for the next conversation.
    """
    if len(conversation_history) >= 2:
        save_conversation(conversation_history)
    conversation_history.clear()


def get_history():
    """Return current conversation history (for memory saving)."""
    return conversation_history
