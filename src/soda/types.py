"""Type definitions for Soda agent infrastructure.

This module defines Pydantic models for structured agent outputs
and related type definitions used across the soda package.
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# =============================================================================
# Agent Invocation Types
# =============================================================================

class AgentConfig(BaseModel):
    """Configuration for agent invocation."""

    model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use for the agent"
    )
    max_tokens: int = Field(
        default=16000,
        description="Maximum tokens for agent response"
    )
    tools: Optional[list[str]] = Field(
        default=None,
        description="Tool allowlist for narrow agents (None = all tools)"
    )


class AgentInvocation(BaseModel):
    """Record of a single agent invocation."""

    timestamp: str = Field(description="ISO 8601 timestamp of invocation")
    agent_type: Literal["narrow", "walked", "bookended"] = Field(
        description="Type of agent pattern used"
    )
    prompt_summary: str = Field(
        description="Brief summary of the prompt (first 100 chars or custom)"
    )
    config: AgentConfig = Field(description="Agent configuration used")


# =============================================================================
# Structured Output Types
# =============================================================================

class StructuredOutput(BaseModel):
    """Base class for structured agent outputs.

    Subclass this to define custom output schemas for your agents.
    The SDK validates agent output against these schemas.
    """
    pass


class ValidationError(BaseModel):
    """Details of a schema validation error."""

    field: str = Field(description="Field that failed validation")
    error: str = Field(description="Error message")
    received: Optional[Any] = Field(
        default=None,
        description="Value received (if available)"
    )


# =============================================================================
# Conversation Types
# =============================================================================

class Message(BaseModel):
    """A single message in a conversation."""

    role: Literal["user", "assistant"] = Field(description="Message role")
    content: str = Field(description="Message content")


class Conversation(BaseModel):
    """A captured conversation from agent invocation."""

    invocation: AgentInvocation = Field(description="Invocation metadata")
    messages: list[Message] = Field(description="Conversation messages")
    output: Optional[dict[str, Any]] = Field(
        default=None,
        description="Structured output if schema was provided"
    )


# =============================================================================
# Error Types
# =============================================================================

class AgentError(BaseModel):
    """Error information from agent invocation."""

    error_type: Literal["transient", "fatal"] = Field(
        description="Whether error is transient (retryable) or fatal"
    )
    message: str = Field(description="Error message")
    retry_count: int = Field(
        default=0,
        description="Number of retry attempts made"
    )
    original_error: Optional[str] = Field(
        default=None,
        description="Original error string (for debugging)"
    )
