"""Custom exceptions for worklogger domain."""


class WorklogError(Exception):
    """Base exception for worklog operations."""


class AuthenticationError(WorklogError):
    """Raised when authentication against Jira fails."""


class ValidationError(WorklogError):
    """Raised for invalid input data."""


class WorklogOperationError(WorklogError):
    """Raised when Jira worklog operation fails."""
