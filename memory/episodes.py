"""Episodic memory — summaries of past conversations, searchable by meaning.

After each conversation, Claude generates a short summary. That summary
is stored with a vector embedding so future conversations can recall
relevant past interactions by semantic similarity.

Example:
  Past episode: "On March 15, user asked about flights to NYC for April 10."
  New question: "What about that trip I was planning?"
  → Vector search finds the NYC flight episode and injects it as context.

Uses ChromaDB for local vector storage (no external API, free).
Stored at /data/chroma/ (Docker volume — persists across restarts).
"""

import os
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

import config

CHROMA_PATH = os.path.join(os.path.dirname(config.REMINDERS_DB), "chroma")
_client = None
_collection = None


def _get_collection():
    """Get or create the episodes collection."""
    global _client, _collection
    if _collection is not None:
        return _collection

    if not HAS_CHROMADB:
        return None

    os.makedirs(CHROMA_PATH, exist_ok=True)
    _client = chromadb.PersistentClient(path=CHROMA_PATH)
    _collection = _client.get_or_create_collection(
        name="episodes",
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def add_episode(summary, conversation_turns=0):
    """Store a conversation episode.

    Args:
        summary: Claude-generated summary of the conversation.
        conversation_turns: How many back-and-forth exchanges happened.
    """
    collection = _get_collection()
    if collection is None:
        return

    now = datetime.now()
    episode_id = f"ep_{now.strftime('%Y%m%d_%H%M%S')}"

    collection.add(
        ids=[episode_id],
        documents=[summary],
        metadatas=[{
            "timestamp": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "turns": conversation_turns,
        }],
    )


def recall(query, n_results=5):
    """Find past episodes relevant to the current query.

    Args:
        query: What to search for (user's current message or topic).
        n_results: Max episodes to return.

    Returns:
        List of dicts with 'summary', 'date', 'relevance' keys.
    """
    collection = _get_collection()
    if collection is None:
        return []

    if collection.count() == 0:
        return []

    # Don't request more results than exist
    actual_n = min(n_results, collection.count())

    results = collection.query(
        query_texts=[query],
        n_results=actual_n,
    )

    episodes = []
    for i in range(len(results["ids"][0])):
        episodes.append({
            "summary": results["documents"][0][i],
            "date": results["metadatas"][0][i].get("date", "unknown"),
            "relevance": 1 - (results["distances"][0][i] if results["distances"] else 0),
        })

    # Only return episodes with decent relevance
    return [e for e in episodes if e["relevance"] > 0.3]


def get_recent(n=10):
    """Get the N most recent episodes."""
    collection = _get_collection()
    if collection is None:
        return []

    if collection.count() == 0:
        return []

    actual_n = min(n, collection.count())
    results = collection.get(
        limit=actual_n,
        include=["documents", "metadatas"],
    )

    episodes = []
    for i in range(len(results["ids"])):
        episodes.append({
            "summary": results["documents"][i],
            "date": results["metadatas"][i].get("date", "unknown"),
        })

    return episodes


def count():
    """Return total number of stored episodes."""
    collection = _get_collection()
    if collection is None:
        return 0
    return collection.count()
