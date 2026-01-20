"""Tests for structured output validation.

These tests verify the StructuredOutputValidator class correctly
validates agent output against Pydantic schemas.
"""

import json
import pytest
from pydantic import BaseModel, Field


class TestStructuredOutputValidator:
    """Test the StructuredOutputValidator class."""

    def test_import_validator(self):
        """WHEN importing StructuredOutputValidator THEN it should succeed."""
        from soda.validation import StructuredOutputValidator
        assert StructuredOutputValidator is not None

    def test_validate_valid_json_returns_typed_object(self):
        """WHEN validating valid JSON THEN it returns a typed Pydantic model."""
        from soda.validation import StructuredOutputValidator

        class ResultSchema(BaseModel):
            status: str
            count: int

        validator = StructuredOutputValidator()
        raw_output = '{"status": "success", "count": 42}'

        result = validator.validate(raw_output, ResultSchema)

        assert isinstance(result, ResultSchema)
        assert result.status == "success"
        assert result.count == 42

    def test_validate_missing_field_raises_error(self):
        """WHEN validating JSON missing a required field THEN it raises ValidationError."""
        from soda.validation import StructuredOutputValidator, StructuredOutputValidationError

        class ResultSchema(BaseModel):
            status: str
            count: int

        validator = StructuredOutputValidator()
        raw_output = '{"status": "success"}'  # missing 'count'

        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validator.validate(raw_output, ResultSchema)

        error = exc_info.value
        assert "count" in str(error)
        assert error.errors is not None
        # Should include field details
        field_names = [e.field for e in error.errors]
        assert "count" in field_names

    def test_validate_wrong_type_raises_error(self):
        """WHEN validating JSON with wrong field type THEN it raises ValidationError."""
        from soda.validation import StructuredOutputValidator, StructuredOutputValidationError

        class ResultSchema(BaseModel):
            status: str
            count: int

        validator = StructuredOutputValidator()
        raw_output = '{"status": "success", "count": "not-a-number"}'

        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validator.validate(raw_output, ResultSchema)

        error = exc_info.value
        assert error.errors is not None
        # Should include field details showing type mismatch
        field_names = [e.field for e in error.errors]
        assert "count" in field_names

    def test_validate_invalid_json_raises_error(self):
        """WHEN validating invalid JSON THEN it raises ValidationError."""
        from soda.validation import StructuredOutputValidator, StructuredOutputValidationError

        class ResultSchema(BaseModel):
            status: str

        validator = StructuredOutputValidator()
        raw_output = 'not valid json {'

        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validator.validate(raw_output, ResultSchema)

        error = exc_info.value
        assert "JSON" in str(error) or "parse" in str(error).lower()

    def test_validate_complex_nested_schema(self):
        """WHEN validating nested schema THEN it validates deeply."""
        from soda.validation import StructuredOutputValidator

        class Address(BaseModel):
            city: str
            zip_code: str

        class Person(BaseModel):
            name: str
            address: Address

        validator = StructuredOutputValidator()
        raw_output = json.dumps({
            "name": "Alice",
            "address": {
                "city": "San Francisco",
                "zip_code": "94102"
            }
        })

        result = validator.validate(raw_output, Person)

        assert isinstance(result, Person)
        assert result.name == "Alice"
        assert result.address.city == "San Francisco"

    def test_validate_nested_schema_error_includes_path(self):
        """WHEN nested field fails validation THEN error includes field path."""
        from soda.validation import StructuredOutputValidator, StructuredOutputValidationError

        class Address(BaseModel):
            city: str
            zip_code: str

        class Person(BaseModel):
            name: str
            address: Address

        validator = StructuredOutputValidator()
        raw_output = json.dumps({
            "name": "Alice",
            "address": {
                "city": "San Francisco"
                # missing zip_code
            }
        })

        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validator.validate(raw_output, Person)

        error = exc_info.value
        # Should identify the nested field
        error_str = str(error)
        assert "zip_code" in error_str or "address" in error_str

    def test_validate_error_includes_received_value(self):
        """WHEN validation fails THEN error includes what was received."""
        from soda.validation import StructuredOutputValidator, StructuredOutputValidationError

        class ResultSchema(BaseModel):
            count: int

        validator = StructuredOutputValidator()
        raw_output = '{"count": "not-a-number"}'

        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validator.validate(raw_output, ResultSchema)

        error = exc_info.value
        # Should have the received value in error details
        count_error = next((e for e in error.errors if "count" in e.field), None)
        assert count_error is not None
        assert count_error.received == "not-a-number"

    def test_validate_list_field(self):
        """WHEN validating schema with list field THEN it validates correctly."""
        from soda.validation import StructuredOutputValidator

        class ResultSchema(BaseModel):
            items: list[str]

        validator = StructuredOutputValidator()
        raw_output = '{"items": ["a", "b", "c"]}'

        result = validator.validate(raw_output, ResultSchema)

        assert result.items == ["a", "b", "c"]

    def test_validate_optional_field_missing(self):
        """WHEN optional field is missing THEN validation succeeds."""
        from soda.validation import StructuredOutputValidator
        from typing import Optional

        class ResultSchema(BaseModel):
            required: str
            optional: Optional[str] = None

        validator = StructuredOutputValidator()
        raw_output = '{"required": "value"}'

        result = validator.validate(raw_output, ResultSchema)

        assert result.required == "value"
        assert result.optional is None

    def test_validate_with_default_field(self):
        """WHEN field has default and is missing THEN default is used."""
        from soda.validation import StructuredOutputValidator

        class ResultSchema(BaseModel):
            status: str
            count: int = 0

        validator = StructuredOutputValidator()
        raw_output = '{"status": "done"}'

        result = validator.validate(raw_output, ResultSchema)

        assert result.status == "done"
        assert result.count == 0


class TestStructuredOutputValidationError:
    """Test the StructuredOutputValidationError exception class."""

    def test_error_has_message(self):
        """WHEN creating ValidationError THEN it has a descriptive message."""
        from soda.validation import StructuredOutputValidationError
        from soda.types import ValidationError as ValidationErrorDetail

        error = StructuredOutputValidationError(
            message="Validation failed",
            errors=[ValidationErrorDetail(field="name", error="field required")]
        )

        assert "Validation failed" in str(error)

    def test_error_has_errors_list(self):
        """WHEN creating ValidationError with errors THEN they are accessible."""
        from soda.validation import StructuredOutputValidationError
        from soda.types import ValidationError as ValidationErrorDetail

        errors = [
            ValidationErrorDetail(field="name", error="field required"),
            ValidationErrorDetail(field="age", error="must be positive")
        ]
        error = StructuredOutputValidationError(
            message="Validation failed",
            errors=errors
        )

        assert len(error.errors) == 2
        assert error.errors[0].field == "name"
        assert error.errors[1].field == "age"

    def test_error_string_includes_field_details(self):
        """WHEN converting error to string THEN it includes field details."""
        from soda.validation import StructuredOutputValidationError
        from soda.types import ValidationError as ValidationErrorDetail

        error = StructuredOutputValidationError(
            message="Validation failed",
            errors=[ValidationErrorDetail(field="count", error="type error", received="abc")]
        )

        error_str = str(error)
        assert "count" in error_str
