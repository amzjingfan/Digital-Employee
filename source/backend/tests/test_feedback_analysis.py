import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.database import set_tenant_context as bind_tenant_context
from app.db.models import APIJob, ChatSession, Message, MessageFeedback, ModelConfig, Tenant, User
from app.feedback import jobs as feedback_jobs
from app.feedback.service import FeedbackAnalysisService, feedback_summary
from app.llm.client import LLMClient


def test_feedback_analysis_uses_model_bucket(monkeypatch) -> None:
    def fake_init(self, model_config):  # noqa: ANN001
        return None

    def fake_generate_json(self, system_prompt, payload):  # noqa: ANN001
        assert payload["feedback"]["rating"] == "down"
        assert payload["target_message"]["content"] == "请稍候"
        return {
            "bucket": "skill_issue",
            "confidence": 0.82,
            "reason": "技能步骤停在请稍候，没有闭环。",
            "summary": "下单流程缺少完成回复。",
            "evidence": ["助手回复没有最终结果"],
            "suggested_action": "补充最终反馈步骤。",
        }

    monkeypatch.setattr(LLMClient, "__init__", fake_init)
    monkeypatch.setattr(LLMClient, "generate_json", fake_generate_json)

    with _test_session() as db:
        feedback = _seed_feedback(db, with_model=True)
        analyzed = FeedbackAnalysisService(db).analyze_feedback(feedback.id)

    assert analyzed is not None
    assert analyzed.analysis_status == "analyzed"
    assert analyzed.analysis_bucket == "skill_issue"
    assert analyzed.analysis_confidence == 0.82
    assert "下单流程" in (analyzed.analysis_summary or "")


def test_feedback_analysis_without_model_marks_needs_model() -> None:
    with _test_session() as db:
        feedback = _seed_feedback(db, with_model=False)
        analyzed = FeedbackAnalysisService(db).analyze_feedback(feedback.id)

    assert analyzed is not None
    assert analyzed.analysis_status == "needs_model"
    assert analyzed.analysis_bucket == "needs_model_analysis"


def test_feedback_summary_buckets_downvotes() -> None:
    rows = [
        MessageFeedback(
            tenant_id="tenant_demo",
            session_id="session_1",
            message_id="msg_1",
            user_id="user_demo",
            rating="down",
            analysis_bucket="model_issue",
            analysis_summary="回复理解错了。",
        ),
        MessageFeedback(
            tenant_id="tenant_demo",
            session_id="session_2",
            message_id="msg_2",
            user_id="user_demo",
            rating="down",
            analysis_bucket="model_issue",
        ),
        MessageFeedback(
            tenant_id="tenant_demo",
            session_id="session_3",
            message_id="msg_3",
            user_id="user_demo",
            rating="up",
            analysis_bucket="positive_or_resolved",
        ),
    ]

    summary = feedback_summary(rows)

    assert summary["down_count"] == 2
    assert summary["up_count"] == 1
    assert summary["bucket_counts"][0]["bucket"] == "model_issue"
    assert summary["bucket_counts"][0]["count"] == 2
    assert "模型问题" in summary["summary"]


def test_feedback_analysis_tenant_filter_rejects_cross_tenant_feedback() -> None:
    with _test_session() as db:
        db.add(
            MessageFeedback(
                id="feedback_other_tenant",
                tenant_id="tenant_other",
                session_id="session_other",
                message_id="message_other",
                user_id="user_other",
                rating="down",
            )
        )
        db.commit()

        assert (
            FeedbackAnalysisService(db).analyze_feedback(
                "feedback_other_tenant", tenant_id="tenant_demo"
            )
            is None
        )


def test_feedback_analysis_job_binds_request_tenant_before_analysis(monkeypatch) -> None:
    tenant_contexts: list[str] = []
    captured: dict[str, object] = {}

    def record_tenant_context(db: Session, tenant_id: str) -> None:
        tenant_contexts.append(tenant_id)
        bind_tenant_context(db, tenant_id)

    with _test_session() as db:
        feedback = _seed_feedback(db, with_model=False)
        monkeypatch.setattr(feedback_jobs, "engine", db.get_bind())

        def fake_analyze(self, feedback_id: str, *, tenant_id: str | None = None):
            captured.update(
                {
                    "session_tenant_context": self.db.info.get("staffdeck_tenant_id"),
                    "feedback_id": feedback_id,
                    "tenant_id": tenant_id,
                }
            )
            return feedback

        monkeypatch.setattr(feedback_jobs, "set_tenant_context", record_tenant_context)
        monkeypatch.setattr(FeedbackAnalysisService, "analyze_feedback", fake_analyze)

        feedback_jobs.run_feedback_analysis_job(
            {
                "tenant_id": "tenant_demo",
                "feedback_id": feedback.id,
                "session_id": feedback.session_id,
            }
        )

    assert tenant_contexts == ["tenant_demo"]
    assert captured == {
        "session_tenant_context": "tenant_demo",
        "feedback_id": feedback.id,
        "tenant_id": "tenant_demo",
    }


def test_feedback_job_handler_rejects_payload_tenant_mismatch() -> None:
    with _test_session() as db:
        job = APIJob(
            id="job_feedback_mismatch",
            tenant_id="tenant_demo",
            credential_id="internal",
            kind="feedback.analyze",
            request_json={
                "tenant_id": "tenant_other",
                "feedback_id": "feedback_other",
                "session_id": "session_other",
            },
        )

        with pytest.raises(LookupError, match="tenant mismatch"):
            feedback_jobs.handle_feedback_analysis_job(db, job)


def test_feedback_job_handler_binds_job_tenant_before_analysis(monkeypatch) -> None:
    tenant_contexts: list[str] = []
    captured: dict[str, object] = {}

    def record_tenant_context(db: Session, tenant_id: str) -> None:
        tenant_contexts.append(tenant_id)
        bind_tenant_context(db, tenant_id)

    with _test_session() as db:
        feedback = _seed_feedback(db, with_model=False)
        job = APIJob(
            id="job_feedback_valid",
            tenant_id="tenant_demo",
            credential_id="internal",
            kind="feedback.analyze",
            request_json={
                "tenant_id": "tenant_demo",
                "feedback_id": feedback.id,
                "session_id": feedback.session_id,
            },
        )

        def fake_analyze(self, feedback_id: str, *, tenant_id: str | None = None):
            captured.update(
                {
                    "session_tenant_context": self.db.info.get("staffdeck_tenant_id"),
                    "feedback_id": feedback_id,
                    "tenant_id": tenant_id,
                }
            )
            return feedback

        monkeypatch.setattr(feedback_jobs, "set_tenant_context", record_tenant_context)
        monkeypatch.setattr(FeedbackAnalysisService, "analyze_feedback", fake_analyze)

        result = feedback_jobs.handle_feedback_analysis_job(db, job)

    assert tenant_contexts == ["tenant_demo"]
    assert captured == {
        "session_tenant_context": "tenant_demo",
        "feedback_id": feedback.id,
        "tenant_id": "tenant_demo",
    }
    assert result == {
        "feedback_id": feedback.id,
        "analysis_status": feedback.analysis_status,
        "analysis_bucket": feedback.analysis_bucket,
    }


def _seed_feedback(db: Session, with_model: bool) -> MessageFeedback:
    db.add(Tenant(id="tenant_demo", name="Demo"))
    user = User(
        id="user_demo",
        tenant_id="tenant_demo",
        username="demo",
        display_name="Demo",
        password_hash="hash",
    )
    db.add(user)
    db.add(ChatSession(id="session_1", tenant_id="tenant_demo", user_id=user.id, title="测试会话"))
    db.add(Message(id="msg_user", tenant_id="tenant_demo", session_id="session_1", role="user", content="我要买东西"))
    db.add(Message(id="msg_assistant", tenant_id="tenant_demo", session_id="session_1", role="assistant", content="请稍候"))
    if with_model:
        db.add(
            ModelConfig(
                tenant_id="tenant_demo",
                name="demo",
                api_key_encrypted="mock",
                model="mock",
                is_default=True,
                enabled=True,
            )
        )
    feedback = MessageFeedback(
        tenant_id="tenant_demo",
        session_id="session_1",
        message_id="msg_assistant",
        user_id=user.id,
        rating="down",
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def _test_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)
