"""Structured output validation for Soda agent infrastructure.

This module provides validation of agent outputs against Pydantic schemas,
returning typed objects on success or raising detailed validation errors.
"""

import json
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError as PydanticValidationError

from soda.types import ValidationError as ValidationErrorDetail


T = TypeVar("T", bound=BaseModel)


class StructuredOutputValidationError(Exception):
    """Exception raised when structured output validation fails.

    Attributes:
        message: Human-readable description of the validation failure
        errors: List of ValidationError details for each field that failed
    """

    def __init__(self, message: str, errors: list[ValidationErrorDetail]):
        """Initialize the validation error.

        Args:
            message: Human-readable description of the failure
            errors: List of field-level validation errors
        """
        self.message = message
        self.errors = errors
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the error message with field details."""
        parts = [self.message]
        if self.errors:
            parts.append("Field errors:")
            for error in self.errors:
                field_msg = f"  - {error.field}: {error.error}"
                if error.received is not None:
                    field_msg += f" (received: {error.received!r})"
                parts.append(field_msg)
        return "\n".join(parts)


class StructuredOutputValidator:
    """Validates raw agent output against Pydantic schemas.

    This validator parses JSON output from agents and validates it against
    expected Pydantic schemas, returning typed objects or raising detailed
    validation errors.
    """

    def validate(self, raw_output: str, schema: Type[T]) -> T:
        """Validate raw output against a Pydantic schema.

        Args:
            raw_output: Raw JSON string from agent output
            schema: Pydantic model class to validate against

        Returns:
            Typed Pydantic model instance if validation succeeds

        Raises:
            StructuredOutputValidationError: If validation fails with details
        """
        # First try to parse JSON
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as e:
            raise StructuredOutputValidationError(
                message=f"Failed to parse JSON: {e}",
                errors=[
                    ValidationErrorDetail(
                        field="__root__",
                        error=f"Invalid JSON: {e}",
                        received=raw_output[:100] if len(raw_output) > 100 else raw_output
                    )
                ]
            ) from e

        # Then validate against schema
        try:
            return schema.model_validate(data)
        except PydanticValidationError as e:
            errors = self._extract_validation_errors(e, data)
            raise StructuredOutputValidationError(
                message=f"Schema validation failed for {schema.__name__}",
                errors=errors
            ) from e

    def _extract_validation_errors(
        self,
        pydantic_error: PydanticValidationError,
        original_data: dict
    ) -> list[ValidationErrorDetail]:
        """Extract field-level errors from Pydantic validation error.

        Args:
            pydantic_error: The Pydantic validation error
            original_data: The original data that was validated

        Returns:
            List of ValidationError details for each field
        """
        errors = []
        for error in pydantic_error.errors():
            # Build field path (e.g., "address.zip_code")
            loc = error.get("loc", ())
            field_path = ".".join(str(part) for part in loc)

            # Get the received value by traversing the path
            received = self._get_nested_value(original_data, loc)

            errors.append(
                ValidationErrorDetail(
                    field=field_path,
                    error=error.get("msg", "validation error"),
                    received=received
                )
            )

        return errors

    def _get_nested_value(self, data: dict, loc: tuple) -> any:
        """Get a nested value from data using a location tuple.

        Args:
            data: The data dictionary to search
            loc: Tuple of keys/indices to traverse

        Returns:
            The value at the location, or None if not found
        """
        current = data
        for key in loc:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and isinstance(key, int) and key < len(current):
                current = current[key]
            else:
                return None
        return current
