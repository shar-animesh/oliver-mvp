"""Idempotently score historical Oliver runs that predate canonical persistence."""

import argparse

from sqlalchemy import select

from utils.postgres import CanonicalAssessmentDb, EmailMessageDb, OliverRunDb
from utils.postgres.base import SessionFactory
from utils.scoring import assess_email
from utils.scoring.exceptions import UnassessableEmailError
from utils.scoring.persistence import apply_assessment, assessment_record


def main() -> None:
    """Create only missing rows for runs recorded as structured assessments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Recalculate existing records with their configured policy version")
    arguments = parser.parse_args()
    created = 0
    updated = 0
    skipped = 0
    with SessionFactory.begin() as database:
        statement = (
            select(OliverRunDb, EmailMessageDb)
            .join(EmailMessageDb, EmailMessageDb.id == OliverRunDb.inbound_message_id)
            .outerjoin(CanonicalAssessmentDb, CanonicalAssessmentDb.run_id == OliverRunDb.id)
            .where(
                OliverRunDb.action == "SEND_EMAIL",
                OliverRunDb.generated_content_html.is_(None),
            )
            .order_by(OliverRunDb.created_at)
        )
        if not arguments.refresh:
            statement = statement.where(CanonicalAssessmentDb.run_id.is_(None))
        rows = database.execute(statement).all()
        for run, inbound_message in rows:
            try:
                assessment = assess_email(inbound_message.subject, inbound_message.content_html or "")
            except UnassessableEmailError:
                skipped += 1
                continue
            existing = database.get(CanonicalAssessmentDb, run.id)
            if existing is None:
                database.add(assessment_record(run.id, assessment))
                created += 1
            else:
                apply_assessment(existing, assessment)
                updated += 1
    print(f"Created {created}, refreshed {updated}, and skipped {skipped} canonical assessment record(s).")


if __name__ == "__main__":
    main()
