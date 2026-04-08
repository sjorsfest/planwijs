class AppError(Exception):
    """Base exception for application errors.

    Subclasses set ``status_code`` and ``code`` so the global error handler
    can return a consistent JSON response without routes needing to build
    HTTPException objects manually.
    """

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "An error occurred"):
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, message: str = "Not found"):
        super().__init__(message)


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"

    def __init__(self, message: str = "Conflict"):
        super().__init__(message)


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"

    def __init__(self, message: str = "Validation error"):
        super().__init__(message)


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message)


class AuthenticationError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"

    def __init__(self, message: str = "Invalid or missing credentials"):
        super().__init__(message)
