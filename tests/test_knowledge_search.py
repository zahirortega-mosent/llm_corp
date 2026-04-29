from app.router.router import IntentRouter
from app.services.answer_composer import AnswerComposer
from app.services.knowledge_service import InstitutionalEvidence, KnowledgeService


def test_no_evidence_message_does_not_invent():
    answer = AnswerComposer().institutional_answer(
        "quien autoriza excepciones",
        [],
        memory_enabled=True,
    )
    assert "No hay memoria institucional aprobada suficiente" in answer
    assert "No voy a inventar" in answer


def test_merge_dedupe_prefers_hybrid_score():
    service = KnowledgeService(engine=object())
    lexical = [InstitutionalEvidence(chunk_id=1, document_id=10, chunk_index=0, title="Manual", content="proceso", rank=0.4)]
    semantic = [InstitutionalEvidence(chunk_id=1, document_id=10, chunk_index=0, title="Manual", content="proceso", rank=0.7)]
    merged = service.merge_dedupe(lexical, semantic)
    assert len(merged) == 1
    assert merged[0].search_mode == "hybrid"
    assert merged[0].rank > 0.7


def test_router_process_requires_memory_but_count_does_not():
    metadata = {"periods": ["2026-01-01"]}
    router = IntentRouter()
    assert router.route("como se hace el escalamiento de incidencias", metadata=metadata).requires_memory is True
    assert router.route("cuantos movimientos hubo en enero 2026", metadata=metadata).requires_memory is False
