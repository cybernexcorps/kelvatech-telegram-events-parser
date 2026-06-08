"""EventExtractor — turns a RawPost into structured Event records via an LLM.

The LLM is injected as a "structured" model (one bound with
`.with_structured_output(ExtractionResult)`), so unit tests use a fake and the
real Yandex model is wired only in `build_yandex_extractor` (imported lazily).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional, Protocol

from pydantic import BaseModel, field_validator

from .models import CostStatus, Domain, Event, EventType, RawPost

log = logging.getLogger(__name__)

# Small models sometimes emit the literal string "null"/"none"/"-" for empty fields
# instead of a real JSON null; treat those as missing so the renderer's fallbacks apply.
_BLANKS = {"", "null", "none", "n/a", "нет", "не указано", "-", "—"}


class ExtractedEvent(BaseModel):
    """The fields the LLM is asked to produce (no source/derived fields)."""

    title: str
    description: Optional[str] = None
    event_type: EventType = "other"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_online: Optional[bool] = None
    location: Optional[str] = None
    host: Optional[str] = None
    cost_status: CostStatus = "unknown"
    price_note: Optional[str] = None
    registration_url: Optional[str] = None

    @field_validator("description", "location", "host", "price_note", "registration_url",
                     mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and v.strip().lower() in _BLANKS:
            return None
        return v


class ExtractionResult(BaseModel):
    events: list[ExtractedEvent] = []


class StructuredLLM(Protocol):
    def invoke(self, input): ...  # returns ExtractionResult


SYSTEM_PROMPT = (
    "Ты — ассистент, который извлекает анонсы мероприятий, на которые человек может прийти "
    "или зарегистрироваться: конференции, митапы, вебинары, форумы, мастер-классы, лекции. "
    "Для каждого мероприятия определи название, тип, дату начала и окончания, формат "
    "(онлайн/офлайн), место, организатора, стоимость участия (free — если участие бесплатное, "
    "paid — если платное, unknown — если неясно) и ссылку на регистрацию. "
    "ВАЖНО: не извлекай новости, релизы продуктов, обзоры, статьи, вакансии, опросы, "
    "рекламу курсов без конкретной даты и просто упоминания прошедших событий — для них "
    "верни пустой список. Если у мероприятия нет ни даты, ни возможности регистрации, "
    "скорее всего это не анонс — не включай его. Название бери из текста дословно, не "
    "придумывай порядковые номера вроде «Вебинар 2». Не выдумывай данные: поля, которых нет "
    "в тексте, оставляй пустыми."
)


def _is_content_filter(exc: Exception) -> bool:
    """Yandex rejects some posts deterministically via its content filter — no point retrying."""
    return "content filter" in str(exc).lower()


class EventExtractor:
    def __init__(self, structured_llm: StructuredLLM, *, retries: int = 1,
                 default_domain: Domain = "ai"):
        self._llm = structured_llm
        self._retries = retries
        self._default_domain = default_domain

    def _prompt(self, post: RawPost):
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Пост (дата {post.dt}):\n\n{post.text}"},
        ]

    def _to_event(self, ex: ExtractedEvent, post: RawPost) -> Event:
        return Event(
            **ex.model_dump(),
            domain=self._default_domain,
            source_channel=post.channel,
            source_post_url=post.permalink,
            source_post_dt=post.dt,
        )

    def extract(self, post: RawPost) -> list[Event]:
        for attempt in range(self._retries + 1):
            try:
                result = self._llm.invoke(self._prompt(post))
                return [self._to_event(e, post) for e in result.events]
            except Exception as exc:  # malformed output / transient model error
                if _is_content_filter(exc):
                    log.info("extraction skipped for %s/%s (content filter)",
                             post.channel, post.id)
                    return []  # deterministic rejection — retrying cannot help
                log.warning("extraction failed for %s/%s attempt %d (%s)",
                            post.channel, post.id, attempt + 1, exc)
        log.warning("extraction skipped for %s/%s after retries", post.channel, post.id)
        return []


def build_yandex_extractor(default_domain: Domain = "ai") -> EventExtractor:
    """Real extractor backed by Yandex Foundation Models (yandexgpt-lite).

    Imported lazily so the unit suite needs no langchain. Uses the OpenAI-compatible
    Yandex inference endpoint for reliable structured output.
    """
    from langchain_openai import ChatOpenAI  # lazy

    model = os.environ.get("YANDEX_EXTRACT_MODEL", "yandexgpt-lite/latest")
    base_url = os.environ.get("YANDEX_OPENAI_BASE_URL", "https://llm.api.cloud.yandex.net/v1")
    api_key = os.environ.get("YANDEX_API_KEY", "")
    folder = os.environ.get("YANDEX_FOLDER_ID", "")
    # Yandex model URIs embed the folder: gpt://<folder>/<model>
    model_uri = f"gpt://{folder}/{model}" if folder and "://" not in model else model

    llm = ChatOpenAI(model=model_uri, base_url=base_url, api_key=api_key, temperature=0)
    structured = llm.with_structured_output(ExtractionResult)
    return EventExtractor(structured, default_domain=default_domain)
