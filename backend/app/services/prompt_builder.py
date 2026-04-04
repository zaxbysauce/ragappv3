"""Prompt builder service for RAG pipeline.

Handles building system prompts, user messages, and formatting context for LLM.
"""

from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.memory_store import MemoryRecord
from app.services.document_retrieval import RAGSource

CITATION_INSTRUCTION = (
    "\n\nWhen answering questions based on the provided context:\n"
    "- Cite your sources inline using the format [Source: filename] when referencing specific documents\n"
    "- If the provided context does not contain enough information to answer the question, "
    "clearly state that the information is not available in the retrieved documents\n"
    "- Do not fabricate or hallucinate information not present in the context"
)


class PromptBuilderService:
    """Service for building prompts and messages for the LLM."""

    def __init__(
        self,
        system_prompt: Optional[str] = None,
        max_context_chunks: Optional[int] = None,
    ) -> None:
        """Initialize the prompt builder service.

        Args:
            system_prompt: Custom system prompt (defaults to standard KnowledgeVault prompt)
            max_context_chunks: Maximum number of context chunks to include
        """
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.max_context_chunks = max_context_chunks or settings.max_context_chunks

    def _default_system_prompt(self) -> str:
        """Return the default system prompt."""
        return (
            "You are KnowledgeVault, a highly accurate assistant that references sources when "
            "answering questions. Cite the relevant documents or memories by name."
            + CITATION_INSTRUCTION
        )

    def build_messages(
        self,
        user_input: str,
        chat_history: List[Dict[str, Any]],
        chunks: List[RAGSource],
        memories: List[MemoryRecord],
        relevance_hint: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build the complete message list for LLM completion.

        Args:
            user_input: The user's question/input
            chat_history: List of previous chat messages
            chunks: Retrieved document chunks
            memories: Retrieved memories
            relevance_hint: Optional hint about retrieval quality

        Returns:
            List of message dictionaries for the LLM
        """
        context_sections = [self.format_chunk(ch) for ch in chunks]
        memory_context = [mem.content for mem in memories if mem.content]

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        # Truncate history to last N messages to prevent context overflow
        max_history = 20
        for entry in chat_history[-max_history:]:
            messages.append(entry)

        context = "\n\n".join(filter(None, context_sections))

        user_content_parts: List[str] = []
        if relevance_hint:
            user_content_parts.append(relevance_hint)
        if context:
            user_content_parts.append(f"Context:\n{context}")
        else:
            user_content_parts.append("No relevant documents found for this query.")
        user_content = "\n\n".join(user_content_parts) + "\n\n"

        memory_text = "\n".join(memory_context)
        if memory_text:
            user_content += f"Memories:\n{memory_text}\n\n"

        user_content += f"Question: {user_input}"
        messages.append({"role": "user", "content": user_content})
        return messages

    def format_chunk(self, chunk: RAGSource) -> str:
        """Format a chunk for inclusion in the prompt context.

        Args:
            chunk: RAGSource to format

        Returns:
            Formatted string with source and text
        """
        source_title = (
            chunk.metadata.get("source_file")
            or chunk.metadata.get("section_title")
            or "document"
        )
        return f"Source {source_title} (score: {chunk.score:.2f}):\n{chunk.text}"

    def build_system_prompt(self) -> str:
        """Return the system prompt.

        Returns:
            System prompt string
        """
        return self.system_prompt
