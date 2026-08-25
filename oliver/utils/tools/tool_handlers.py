"""Handlers for Oliver's custom semantic-search tool."""

import json
import math
from typing import Any, Dict, List, Tuple

from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utils.postgres import EmailThreadDb, InitiativeDb

from .tool_schema import SEARCH_RELATED_IDEAS_TOOL_NAME, SearchRelatedIdeasInput

INTERNAL_EMAIL_DOMAIN = "siemens-energy.com"
SIMILAR_IDEA_LIMIT = 3
SIMILAR_IDEA_CANDIDATE_LIMIT = 250
SIMILAR_IDEA_MAX_COSINE_DISTANCE = 0.35
SIMILAR_IDEA_CONTEXT_CHARACTER_LIMIT = 1500


def cosine_distance(left: List[float], right: List[float]) -> float:
    """Calculate cosine distance for two non-empty vectors of equal length."""
    if len(left) != len(right) or not left:
        raise ValueError("Embedding vectors must be non-empty and have equal dimensions")

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("Embedding vectors must have non-zero magnitude")
    return 1 - dot_product / (left_norm * right_norm)


def generate_embedding(
    client: OpenAI,
    input_text: str,
    *,
    model: str,
    dimensions: int,
) -> List[float]:
    """Generate one vector for the complete supplied text."""
    response = client.embeddings.create(
        model=model,
        input=input_text,
        dimensions=dimensions,
        encoding_format="float",
    )
    return response.data[0].embedding


def handle_tool_call(
    client: OpenAI,
    db: Session,
    current_thread: EmailThreadDb,
    tool_name: str,
    tool_arguments: str,
    embedding_model: str,
    embedding_dimensions: int,
) -> Tuple[str, List[Tuple[EmailThreadDb, float]]]:
    """Execute one custom tool call and return model context plus matched threads."""
    if tool_name != SEARCH_RELATED_IDEAS_TOOL_NAME:
        return json.dumps({"error": f"Unsupported tool: {tool_name}"}), []

    participant_email = (current_thread.participant_email or "").lower()
    if not participant_email.endswith(f"@{INTERNAL_EMAIL_DOMAIN}"):
        return json.dumps({"results": [], "reason": "Related internal ideas are available only for internal participants."}), []

    arguments = SearchRelatedIdeasInput.model_validate_json(tool_arguments)
    query_embedding = generate_embedding(
        client,
        arguments.query,
        model=embedding_model,
        dimensions=embedding_dimensions,
    )
    candidates = list(
        db.scalars(
            select(EmailThreadDb)
            .join(InitiativeDb, EmailThreadDb.initiative_id == InitiativeDb.id)
            .where(
                EmailThreadDb.id != current_thread.id,
                InitiativeDb.related_idea_sharing_scope == "INTERNAL",
                EmailThreadDb.embedding.is_not(None),
                EmailThreadDb.participant_email.is_not(None),
                func.lower(EmailThreadDb.participant_email).like(f"%@{INTERNAL_EMAIL_DOMAIN}"),
                func.lower(EmailThreadDb.participant_email) != participant_email,
                EmailThreadDb.embedding_model == embedding_model,
                EmailThreadDb.embedding_dimensions == embedding_dimensions,
            )
            .order_by(EmailThreadDb.embedded_at.desc().nullslast(), EmailThreadDb.id)
            .limit(SIMILAR_IDEA_CANDIDATE_LIMIT)
        )
    )

    matches = [(candidate, cosine_distance(candidate.embedding, query_embedding)) for candidate in candidates if candidate.embedding is not None]
    matches = [match for match in matches if match[1] <= SIMILAR_IDEA_MAX_COSINE_DISTANCE]
    matches.sort(key=lambda match: match[1])
    matches = matches[:SIMILAR_IDEA_LIMIT]
    if not matches:
        return json.dumps({"results": []}), []

    results: List[Dict[str, Any]] = []
    for related_thread, related_distance in matches:
        results.append(
            {
                "subject": related_thread.subject,
                "cosine_distance": round(related_distance, 4),
                "participant_authored_context": (related_thread.semantic_text or "")[:SIMILAR_IDEA_CONTEXT_CHARACTER_LIMIT],
            }
        )

    return json.dumps({"results": results}, ensure_ascii=False), matches
