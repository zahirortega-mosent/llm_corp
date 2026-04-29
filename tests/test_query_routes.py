from pathlib import Path


def test_query_service_contains_required_direct_methods():
    source = Path("api/app/services/query_service.py").read_text()
    required = [
        "def get_available_periods_summary",
        "def get_summary",
        "def get_movements(",
        "def search_movements_text",
        "def get_movements_breakdown",
        "def get_incidents(",
        "def get_incidents_breakdown",
        "def get_incidents_for_movements",
        "def get_review_candidates",
        "def get_account_profile",
        "def get_files_for_statement_uids",
        "def get_relevant_rules",
    ]
    missing = [item for item in required if item not in source]
    assert missing == []


def test_direct_answer_path_uses_composer_and_no_llm_for_direct_sql():
    source = Path("api/app/services/answer_service.py").read_text()
    assert "if route.is_direct_sql" in source
    assert "self.answer_composer.compose_direct" in source
    assert "used_llm=False" in source


def test_indexes_file_exists():
    source = Path("db/init/003_indexes.sql").read_text()
    assert "idx_movements_period_bank_filial" in source
    assert "idx_movements_text_search" in source


def test_block3_conversation_files_exist():
    assert Path("api/app/services/conversation_service.py").exists()
    assert Path("api/app/services/context_resolver.py").exists()
    assert Path("db/init/005_conversation_state.sql").exists()
    assert Path("db/migrations/005_conversation_state.sql").exists()


def test_answer_service_persists_conversation_state_when_enabled():
    source = Path("api/app/services/answer_service.py").read_text()
    assert "ConversationService" in source
    assert "ContextResolver" in source
    assert "_save_conversation_state" in source
    assert "conversation_id=conversation_id" in source
