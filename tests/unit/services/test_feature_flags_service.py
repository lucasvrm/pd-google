"""
Unit tests for Feature Flags Service
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "..")))

from services import feature_flags_service
from services.feature_flags_service import (
    get_feature_flag,
    is_auto_priority_enabled,
    is_auto_next_action_enabled,
    is_manual_priority_enabled,
    is_task_next_action_enabled,
    clear_cache,
    _is_cache_valid,
    _refresh_cache,
)


class TestFeatureFlagsService:
    """Test suite for feature flags service"""
    
    def setup_method(self):
        """Clear cache before each test"""
        clear_cache()
    
    def test_default_values_when_no_flags_in_db(self):
        """Flags devem ter defaults seguros quando não existem no banco"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        # Auto features desabilitadas por padrão
        assert is_auto_priority_enabled(db=mock_db) is False
        assert is_auto_next_action_enabled(db=mock_db) is False
        
        # Manual features habilitadas por padrão
        assert is_manual_priority_enabled(db=mock_db) is True
        assert is_task_next_action_enabled(db=mock_db) is True
    
    def test_cache_is_used(self):
        """Cache deve evitar queries repetidas"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("feature_lead_auto_priority", True),
        ]
        mock_db.execute.return_value = mock_result
        
        # Primeira chamada
        result1 = get_feature_flag("feature_lead_auto_priority", db=mock_db)
        # Segunda chamada (deve usar cache)
        result2 = get_feature_flag("feature_lead_auto_priority", db=mock_db)
        
        # Ambas devem retornar True
        assert result1 is True
        assert result2 is True
        
        # Banco chamado apenas uma vez
        assert mock_db.execute.call_count == 1
    
    def test_boolean_value_parsing(self):
        """Deve parsear corretamente valores booleanos"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("feature_lead_auto_priority", True),
            ("feature_lead_auto_next_action", False),
        ]
        mock_db.execute.return_value = mock_result
        
        assert get_feature_flag("feature_lead_auto_priority", db=mock_db) is True
        assert get_feature_flag("feature_lead_auto_next_action", db=mock_db) is False
    
    def test_string_value_parsing(self):
        """Deve parsear corretamente valores string"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("feature_lead_auto_priority", "true"),
            ("feature_lead_auto_next_action", "false"),
            ("feature_test_1", "1"),
            ("feature_test_0", "0"),
            ("feature_test_yes", "yes"),
            ("feature_test_no", "no"),
        ]
        mock_db.execute.return_value = mock_result
        
        assert get_feature_flag("feature_lead_auto_priority", db=mock_db) is True
        assert get_feature_flag("feature_lead_auto_next_action", db=mock_db) is False
        assert get_feature_flag("feature_test_1", db=mock_db) is True
        assert get_feature_flag("feature_test_0", db=mock_db) is False
        assert get_feature_flag("feature_test_yes", db=mock_db) is True
        assert get_feature_flag("feature_test_no", db=mock_db) is False
    
    def test_missing_flag_returns_default(self):
        """Flag não encontrada deve retornar valor padrão"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        # Sem default especificado
        assert get_feature_flag("feature_nonexistent", db=mock_db) is False
        
        # Com default especificado
        assert get_feature_flag("feature_nonexistent", default=True, db=mock_db) is True
    
    def test_cache_validity(self):
        """Testa que o cache expira corretamente"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("feature_lead_auto_priority", True),
        ]
        mock_db.execute.return_value = mock_result
        
        # Primeira chamada - popula cache
        get_feature_flag("feature_lead_auto_priority", db=mock_db)
        assert mock_db.execute.call_count == 1
        
        # Segunda chamada imediata - usa cache
        get_feature_flag("feature_lead_auto_priority", db=mock_db)
        assert mock_db.execute.call_count == 1
        
        # Simular expiração do cache
        clear_cache()
        
        # Terceira chamada - após limpar cache, busca novamente
        get_feature_flag("feature_lead_auto_priority", db=mock_db)
        assert mock_db.execute.call_count == 2
    
    def test_error_handling_with_fallback_defaults(self):
        """Quando há erro no banco, deve usar defaults seguros"""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Database error")
        
        # Deve retornar defaults sem quebrar
        assert is_auto_priority_enabled(db=mock_db) is False
        assert is_auto_next_action_enabled(db=mock_db) is False
        assert is_manual_priority_enabled(db=mock_db) is True
        assert is_task_next_action_enabled(db=mock_db) is True
    
    def test_convenience_functions(self):
        """Testa as funções de conveniência"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("feature_lead_auto_priority", True),
            ("feature_lead_auto_next_action", False),
            ("feature_lead_manual_priority", True),
            ("feature_lead_task_next_action", False),
        ]
        mock_db.execute.return_value = mock_result
        
        assert is_auto_priority_enabled(db=mock_db) is True
        assert is_auto_next_action_enabled(db=mock_db) is False
        assert is_manual_priority_enabled(db=mock_db) is True
        assert is_task_next_action_enabled(db=mock_db) is False
    
    def test_clear_cache(self):
        """Testa que clear_cache limpa corretamente"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("feature_lead_auto_priority", True),
        ]
        mock_db.execute.return_value = mock_result
        
        # Popular cache
        get_feature_flag("feature_lead_auto_priority", db=mock_db)
        
        # Limpar cache
        clear_cache()
        
        # Cache deve estar vazio
        assert feature_flags_service._cache == {}
        assert feature_flags_service._cache_timestamp is None
    
    def test_cache_validity_check(self):
        """Testa _is_cache_valid"""
        # Cache vazio
        clear_cache()
        assert _is_cache_valid() is False
        
        # Simular cache populado recentemente
        feature_flags_service._cache = {"feature_test": True}
        feature_flags_service._cache_timestamp = datetime.now(timezone.utc)
        assert _is_cache_valid() is True
