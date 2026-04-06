"""Prompt builder service for RAG pipeline.

Handles building system prompts, user messages, and formatting context for LLM.
"""

from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.memory_store import MemoryRecord
from app.services.document_retrieval import RAGSource

CITATION_INSTRUCTION = (
    "\n\nWhen answering questions based on the provided context:\n"
    "- Cite your sources inline using only the stable source labels provided (e.g. [S1], [S2], [S3])\n"
    "- Do NOT cite by filename. Always use the [S#] label assigned to each source.\n"
    "- If the provided context does not contain enough information to answer the question, "
    "clearly state that the information is not available in the retrieved documents\n"
    "- Do not fabricate or hallucinate information not present in the context\n"
    "- Prefer citing primary evidence over supporting evidence when both are available"
)


def calculate_primary_count(total_chunks: int) -> int:
    """Calculate the number of primary evidence chunks from total chunk count.

    Uses at least 3 chunks (or all if fewer) and at most half the total.
    """
    return min(max(total_chunks // 2, 3), total_chunks)


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
            "answering questions. Cite the relevant documents or memories using their assigned "
            "source labels (e.g. [S1], [S2])."
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
        # Split chunks into primary (top-scoring) and supporting
        primary_count = calculate_primary_count(len(chunks))
        primary_chunks = chunks[:primary_count]
        supporting_chunks = chunks[primary_count:]

        # Format with stable source labels [S1], [S2], etc.
        primary_sections = [
            self.format_chunk(ch, idx + 1) for idx, ch in enumerate(primary_chunks)
        ]
        supporting_sections = [
            self.format_chunk(ch, idx + primary_count + 1)
            for idx, ch in enumerate(supporting_chunks)
        ]

        memory_context = [mem.content for mem in memories if mem.content]

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        # Truncate history to last N messages to prevent context overflow
        max_history = settings.chat_history_max_messages
        for entry in chat_history[-max_history:]:
            messages.append(entry)

        # Build structured context
        user_content_parts: List[str] = []
        if relevance_hint:
            user_content_parts.append(relevance_hint)

        if primary_sections:
            primary_text = "\n\n".join(primary_sections)
            user_content_parts.append(f"Primary Evidence:\n{primary_text}")

        if supporting_sections:
            supporting_text = "\n\n".join(supporting_sections)
            user_content_parts.append(f"Supporting Evidence:\n{supporting_text}")

        if not primary_sections and not supporting_sections:
            user_content_parts.append("No relevant documents found for this query.")

        user_content = "\n\n".join(user_content_parts) + "\n\n"

        memory_text = "\n".join(memory_context)
        if memory_text:
            user_content += f"Memories:\n{memory_text}\n\n"

        user_content += f"Question: {user_input}"
        messages.append({"role": "user", "content": user_content})
        return messages

    def format_chunk(self, chunk: RAGSource, source_index: int) -> str:
        """Format a chunk for inclusion in the prompt context with a stable source label.

        Args:
            chunk: RAGSource to format
            source_index: 1-based index for the stable source label

        Returns:
            Formatted string with stable source label and metadata
        """
        filename = (
            chunk.metadata.get("source_file")
            or chunk.metadata.get("filename")
            or chunk.metadata.get("section_title")
            or "document"
        )
        section = chunk.metadata.get("section_title") or chunk.metadata.get("heading") or ""
        label = f"[S{source_index}]"

        header_parts = [f"{label} {filename}"]
        if section and section != filename:
            header_parts.append(f"Section: {section}")
        header_parts.append(f"score: {chunk.score:.2f}")
        if chunk.file_id:
            header_parts.append(f"id: {chunk.file_id}")

        header = " | ".join(header_parts)
        return f"{header}\n{chunk.text}"

    def build_system_prompt(self) -> str:
        """Return the system prompt.

        Returns:
            System prompt string
        """
        return self.system_prompt
