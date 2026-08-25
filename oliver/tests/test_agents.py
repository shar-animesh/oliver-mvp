"""Regression tests for the first Assessment and Coach boundaries."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils.agents.assessment import AssessmentRequest, RubricAssessmentAgent, canonical_assessment_context
from utils.agents.coach import AgentContractError, CoachAgent, render_coach_response
from utils.models import ApproachGuidance, AssessmentReport, CoachingItem, NextStep, OliverResponse, Opportunity, PathForward
from utils.postgres import EmailThreadDb
from utils.scoring import DIStage, assess_email
from utils.transition_policy import ReportDepth


def _assessment_report() -> AssessmentReport:
    return AssessmentReport(
        position_note="The evidence supports a focused pilot decision.",
        executive_summary=(
            "The proposal connects turbine sensor history to earlier maintenance intervention. "
            "The next move is to validate the target and baseline with the sponsor."
        ),
        working_well=["Historical turbine sensor data and a measurable outage objective are identified."],
        coaching_recommendations=[
            CoachingItem(
                title="Confirm the baseline",
                detail="Record the current outage rate and the exact comparison period before the pilot begins.",
                criterion_ids=["DI1_DI2_INITIAL_EVIDENCE"],
            )
        ],
        approach_guidance=ApproachGuidance(
            problem_type="Time-series anomaly detection for maintenance intervention.",
            recommended_approach="Begin with a bounded offline comparison against known maintenance events.",
            what_to_do_first="Create a labelled evaluation set from six months of sensor history.",
            criterion_ids=["DI1_DI2_SOLUTION_PLAUSIBLE"],
        ),
        opportunities=[
            Opportunity(
                area="Value evidence",
                priority="High",
                suggestion="Confirm the avoided-downtime baseline with the operational owner.",
                criterion_ids=["DI1_DI2_VALUE_VALIDATION"],
            )
        ],
        path_forward=PathForward(
            timeline="A four-week validation window for confirmation.",
            milestones=["Agree baseline", "Run offline test"],
            criterion_ids=["DI1_DI2_INITIAL_EVIDENCE"],
        ),
        next_steps=[
            NextStep(
                action="Confirm the evaluation baseline",
                owner="Owner needed",
                timeline="Within one week",
                criterion_ids=["DI1_DI2_INITIAL_EVIDENCE"],
            )
        ],
        closing_note="Please share the confirmed baseline so Oliver can reassess the complete evidence set.",
    )


class AssessmentAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = RubricAssessmentAgent()

    def test_ordinary_follow_up_does_not_trigger_reassessment(self) -> None:
        result = self.agent.assess(
            AssessmentRequest(
                subject="Re: Predictive maintenance AI assessment",
                latest_message_html="<p>Thanks, can you explain the previous recommendation?</p>",
                inbound_messages_html=("<p>Earlier initiative evidence.</p>", "<p>Thanks, can you explain the previous recommendation?</p>"),
                has_previous_assessment=True,
            )
        )
        self.assertIsNone(result)

    def test_new_evidence_reassesses_the_accumulated_history(self) -> None:
        original = """
        <p>Unplanned turbine downtime costs 2M EUR per year.</p>
        <p>We will use anomaly detection on PI System sensor data.</p>
        <p>The VP of Gas Services sponsors a pilot next quarter.</p>
        """
        update = "<p>We tested six months of historical data and achieved 92% detection accuracy.</p>"
        result = self.agent.assess(
            AssessmentRequest(
                subject="Re: Predictive maintenance AI pilot",
                latest_message_html=update,
                inbound_messages_html=(original, update),
                has_previous_assessment=True,
            )
        )
        self.assertIsNotNone(result)
        assert result is not None
        technical = next(dimension for dimension in result.dimensions if dimension.dimension == "technicalFeasibility")
        self.assertGreater(technical.value, 0)

    def test_duplicate_message_bodies_do_not_change_the_result(self) -> None:
        idea = "<p>We propose an AI pilot using archived contracts to reduce manual review by 30%.</p>"
        single = self.agent.assess(AssessmentRequest("Contract AI", idea, (idea,), False))
        duplicate = self.agent.assess(AssessmentRequest("Contract AI", idea, (idea, idea), False))
        self.assertEqual(single, duplicate)

    def test_configuration_value_error_is_not_hidden_as_unassessable(self) -> None:
        request = AssessmentRequest(
            subject="Assess this AI idea",
            latest_message_html="<p>Please assess this AI initiative with sufficient supporting content.</p>",
            inbound_messages_html=("<p>Please assess this AI initiative with sufficient supporting content.</p>",),
            has_previous_assessment=False,
        )
        with patch("utils.agents.assessment.assess_email", side_effect=ValueError("invalid weight configuration")):
            with self.assertRaisesRegex(ValueError, "invalid weight configuration"):
                self.agent.assess(request)

    def test_canonical_context_contains_one_authoritative_score(self) -> None:
        assessment = assess_email(
            "Predictive maintenance AI",
            "We will use anomaly detection on sensor data to reduce 2M EUR downtime with a pilot sponsored by the VP of Services.",
        )
        context = canonical_assessment_context(assessment)
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.count('"composite_score"'), 1)


class CoachContractTests(unittest.TestCase):
    def test_coach_agent_returns_parsed_response_and_usage(self) -> None:
        response = OliverResponse(
            action="SEND_EMAIL",
            reply_kind="message",
            subject="Re: Question",
            content_html="<p>Here is the answer.</p>",
        )

        class FakeResponses:
            def create(self, **kwargs: object) -> SimpleNamespace:
                return SimpleNamespace(
                    usage=SimpleNamespace(input_tokens=12, output_tokens=7),
                    output=[SimpleNamespace(type="message", content=[SimpleNamespace(text=response.model_dump_json())])],
                )

        fake_client = SimpleNamespace(responses=FakeResponses())
        agent = CoachAgent(
            client=fake_client,  # type: ignore[arg-type]
            model="provider/model",
            reasoning_effort="high",
            embedding_model="openai/embedding-model",
            embedding_dimensions=1536,
            max_tool_rounds=2,
        )
        result = agent.respond(
            database=object(),  # type: ignore[arg-type]
            current_thread=EmailThreadDb(conversation_id="conversation-1"),
            email_thread="<email>Question</email>",
            canonical_context=None,
        )
        self.assertEqual(result.response, response)
        self.assertEqual(result.prompt_tokens, 12)
        self.assertEqual(result.completion_tokens, 7)
        self.assertEqual(result.related_threads, ())

    def test_tool_free_preview_does_not_attach_tools(self) -> None:
        response = OliverResponse(
            action="SEND_EMAIL",
            reply_kind="message",
            subject="Re: Assessment",
            content_html="<p>Please provide the missing evidence.</p>",
        )

        class FakeResponses:
            request: dict[str, object] | None = None

            def create(self, **kwargs: object) -> SimpleNamespace:
                self.request = kwargs
                return SimpleNamespace(
                    usage=None,
                    output=[SimpleNamespace(type="message", content=[SimpleNamespace(text=response.model_dump_json())])],
                )

        responses = FakeResponses()
        agent = CoachAgent(
            client=SimpleNamespace(responses=responses),  # type: ignore[arg-type]
            model="provider/model",
            reasoning_effort="high",
            embedding_model="openai/embedding-model",
            embedding_dimensions=1536,
            max_tool_rounds=2,
        )

        result = agent.respond(
            database=None,
            current_thread=None,
            email_thread="<email>Assess this idea</email>",
            canonical_context='{"composite_score": 65}',
        )

        self.assertEqual(result.response, response)
        self.assertIsNotNone(responses.request)
        assert responses.request is not None
        self.assertNotIn("tools", responses.request)

    def test_assessment_reply_without_canonical_result_is_rejected(self) -> None:
        response = OliverResponse(action="SEND_EMAIL", reply_kind="assessment", subject="Assessment", report=_assessment_report())
        with self.assertRaises(AgentContractError):
            render_coach_response(response, None)

    def test_message_reply_never_renders_literal_none(self) -> None:
        response = OliverResponse(
            action="SEND_EMAIL",
            reply_kind="message",
            subject="Re: Question",
            content_html="<p>Here is the requested explanation.</p>",
        )
        rendered = render_coach_response(response, None)
        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertNotIn(">None<", rendered)

    def test_unapproved_stage_policy_cannot_authorize_assessment_recommendations(self) -> None:
        assessment = assess_email(
            "Scale assessment",
            "We will use anomaly detection on sensor data to reduce 2M EUR downtime with a pilot sponsored by the VP of Services.",
            DIStage.DI5,
        )
        response = OliverResponse(action="SEND_EMAIL", reply_kind="assessment", subject="Assessment", report=_assessment_report())
        with self.assertRaises(AgentContractError):
            render_coach_response(response, assessment)

    def test_assessment_email_never_exposes_internal_policy_ids(self) -> None:
        assessment = assess_email(
            "Predictive maintenance AI",
            "We will test anomaly detection on sensor data in a controlled pilot with an accountable operational owner.",
        ).model_copy(update={"response_depth": ReportDepth.DETAILED})
        report = _assessment_report().model_copy(
            update={"executive_summary": "The internal reference DI1_DI2_PILOT_SCOPE must not appear in this email."}
        )
        response = OliverResponse(action="SEND_EMAIL", reply_kind="assessment", subject="Assessment", report=report)

        rendered = render_coach_response(response, assessment)

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertNotIn("DI1_DI2_", rendered)
        self.assertNotIn("Policy basis:", rendered)
        self.assertIn("Recommendation:</strong>", rendered)


if __name__ == "__main__":
    unittest.main()
