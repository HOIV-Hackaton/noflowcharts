from fastapi import HTTPException, status

from app.core.redaction import redact_text


class AppError(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str):
        self.message = redact_text(message)
        super().__init__(self.message)


class ConfigurationError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class PhoenixError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY


class PhoenixUnauthorizedError(PhoenixError):
    status_code = status.HTTP_401_UNAUTHORIZED


class PhoenixNotFoundError(PhoenixError):
    status_code = status.HTTP_404_NOT_FOUND


class PhoenixValidationError(PhoenixError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class SshError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY



class SafetyError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST



class AgentError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY



class DatabaseError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR



class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY



class ActivitySubmissionError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY



def to_http_exception(error: AppError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)
