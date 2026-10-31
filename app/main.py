"""FastAPI backend: POST /ask turns a question into a structured, query-backed answer."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.analytics import AnalyticsError, run_intent
from app.database import load_csv
from app.interpreter import SUPPORTED_EXAMPLES, UnsupportedQuestion, interpret

logger = logging.getLogger("bi-assistant")


@asynccontextmanager
async def lifespan(app):
    # Rebuild the database from the CSV on startup (cheap, and always consistent).
    summary = load_csv()
    logger.info("Database loaded: %s", summary)
    app.state.load_summary = summary
    yield


app = FastAPI(title="Mini AI Business Intelligence Assistant", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., max_length=500)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value


def error_response(status_code, code, message, **extra):
    return JSONResponse(status_code=status_code,
                        content={"error": code, "message": message, **extra})


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(request, exc):
    return error_response(
        422, "invalid_request",
        'Send JSON like {"question": "What is the total revenue?"} (1-500 characters).')


@app.get("/health")
def health():
    return {"status": "ok", "data_load": getattr(app.state, "load_summary", None)}


@app.post("/ask")
def ask(request: AskRequest):
    try:
        parsed = interpret(request.question)
        result = run_intent(parsed["intent"], parsed["params"])
    except UnsupportedQuestion as exc:
        return error_response(400, "unsupported_question", str(exc),
                              supported_examples=SUPPORTED_EXAMPLES)
    except AnalyticsError as exc:
        return error_response(400, "cannot_answer", str(exc))
    except Exception:
        logger.exception("Unexpected error while answering %r", request.question)
        return error_response(500, "internal_error",
                              "Something went wrong on our side. Please try again.")

    return {"question": request.question, "interpreter": parsed["interpreter"], **result}
