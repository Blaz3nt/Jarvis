"""Jarvis memory system — three-tier, fully persistent.

Tier 1: Short-term (in assist.py)
  - Current conversation messages, kept in RAM
  - Trimmed to MAX_HISTORY_MESSAGES to control token cost

Tier 2: Long-term facts (memory/facts.py)
  - Permanent facts about the user: name, preferences, routines
  - SQLite — /data/memory.db
  - Injected into system prompt every call

Tier 3: Episodic (memory/episodes.py)
  - Summaries of past conversations, searchable by meaning
  - ChromaDB vector store — /data/chroma/
  - Relevant episodes injected when the topic matches

All stored in /data/ (Docker volume), survives restarts/rebuilds.
"""

import json
import anthropic
import config
from memory.facts import get_all_facts, add_facts, count as facts_count, prune as prune_facts
from memory.episodes import add_episode, recall, count as episodes_count


def build_memory_context(user_message):
    """Build a memory context string to inject into Claude's system prompt.

    Enforces a hard character budget (MEMORY_BUDGET_CHARS) so memory
    never burns excessive tokens, even after years of use.

    Budget allocation:
    - 60% for facts (most useful for every call)
    - 40% for episodic recall (only relevant ones)
    """
    budget = config.MEMORY_BUDGET_CHARS
    facts_budget = int(budget * 0.6)
    episodes_budget = budget - facts_budget

    parts = []
    used = 0

    # Facts — always included, truncated to budget
    facts = get_all_facts()
    if facts:
        if len(facts) > facts_budget:
            facts = facts[:facts_budget] + "\n..."
        parts.append(f"== What you know about the user ==\n{facts}")
        used += len(facts)

    # Episodes — only relevant ones, within remaining budget
    episodes = recall(user_message, n_results=config.MAX_EPISODE_RECALL)
    if episodes:
        ep_lines = []
        ep_chars = 0
        for ep in episodes:
            line = f"- [{ep['date']}] {ep['summary']}"
            if ep_chars + len(line) > episodes_budget:
                break
            ep_lines.append(line)
            ep_chars += len(line)
        if ep_lines:
            parts.append(f"== Relevant past conversations ==\n" + "\n".join(ep_lines))

    if not parts:
        return ""

    return "\n\n".join(parts)


def save_conversation(messages):
    """After a conversation ends, extract facts and save an episode summary.

    Uses a single cheap Haiku call to:
    1. Summarize the conversation in 1-2 sentences
    2. Extract any new facts about the user

    Cost: ~$0.0005 per conversation save.
    """
    if len(messages) < 2:
        return

    # Build a compact version of the conversation for summarization
    compact = []
    for msg in messages[-20:]:  # Last 20 messages max
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, list):
            # Tool results — skip for summary
            continue
        if isinstance(content, str):
            text = content
        else:
            # Content blocks from assistant
            text = " ".join(
                block.text for block in content
                if hasattr(block, "text")
            )
        if text:
            compact.append(f"{role}: {text[:200]}")

    if not compact:
        return

    conversation_text = "\n".join(compact)

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=300,
            system="""Extract memory from this conversation. Respond in JSON only:
{
  "summary": "1-2 sentence summary of what was discussed",
  "facts": ["fact 1 about the user", "fact 2"]
}
Rules:
- Summary should mention what the user asked/did, not Jarvis's responses
- Only extract FACTS about the user (preferences, name, location, habits, plans)
- If no new facts, return empty list
- Keep facts atomic: one fact per string
- Do NOT include temporary info (like "user asked about weather")""",
            messages=[{
                "role": "user",
                "content": conversation_text,
            }],
        )

        text = response.content[0].text.strip()

        # Parse JSON from response (handle markdown code blocks)
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]

        data = json.loads(text)

        summary = data.get("summary", "")
        facts = data.get("facts", [])

        if summary:
            turns = len([m for m in messages if m["role"] == "user"])
            add_episode(summary, conversation_turns=turns)

        if facts:
            add_facts(facts)
            pruned = prune_facts(config.MAX_FACTS)
            if pruned:
                print(f"[Pruned {pruned} old facts to stay under {config.MAX_FACTS} limit]")

        fact_str = f", {len(facts)} facts" if facts else ""
        print(f"[Memory saved: episode{fact_str}]")

    except Exception as e:
        print(f"[Memory save failed: {e}]")


def get_stats():
    """Get memory statistics."""
    return {
        "facts": facts_count(),
        "episodes": episodes_count(),
    }
