"""
Unit tests for Lead Priority Config Service
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "..")))

from services import lead_priority_config_service
from services.lead_priority_config_service import (
    get_lead_priority_config,
    clear_cache,
    DEFAULT_CONFIG,
    _sanitize_config,
)


class TestLeadPriorityConfigService:
    """Test suite for lead priority config service"""
    
    def setup_method(self):
        """Clear cache before each test"""
        clear_cache()
    
    def test_default_config_when_not_in_db(self):
        """Deve retornar defaults quando não existe no banco"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result
        
        config = get_lead_priority_config(db=mock_db)
        
        # Deve retornar config padrão
        assert config["thresholds"]["hot"] == 70
        assert config["thresholds"]["warm"] == 40
        assert config["scoring"]["recencyMaxPoints"] == 40
        assert config["scoring"]["staleDays"] == 30
        assert config["scoring"]["upcomingMeetingPoints"] == 25
    
    def test_cache_is_used(self):
        """Cache deve evitar queries repetidas"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (DEFAULT_CONFIG,)
        mock_db.execute.return_value = mock_result
        
        # Primeira chamada
        config1 = get_lead_priority_config(db=mock_db)
        # Segunda chamada (deve usar cache)
        config2 = get_lead_priority_config(db=mock_db)
        
        # Ambas devem retornar config
        assert config1 == config2
        
        # Banco chamado apenas uma vez
        assert mock_db.execute.call_count == 1
    
    def test_sanitize_config_with_valid_data(self):
        """Deve aceitar configuração válida"""
        raw_config = {
            "thresholds": {
                "hot": 80,
                "warm": 50,
            },
            "scoring": {
                "recencyMaxPoints": 35,
                "staleDays": 20,
                "upcomingMeetingPoints": 30,
                "minScore": 0,
                "maxScore": 100,
            }
        }
        
        result = _sanitize_config(raw_config)
        
        assert result["thresholds"]["hot"] == 80
        assert result["thresholds"]["warm"] == 50
        assert result["scoring"]["recencyMaxPoints"] == 35
        assert result["scoring"]["staleDays"] == 20
    
    def test_sanitize_config_with_invalid_types(self):
        """Deve usar defaults quando tipos são inválidos"""
        raw_config = {
            "thresholds": {
                "hot": "not_a_number",
                "warm": 50,
            },
            "scoring": {
                "recencyMaxPoints": None,
                "staleDays": "invalid",
            }
        }
        
        result = _sanitize_config(raw_config)
        
        # hot deve usar default (tipo inválido)
        assert result["thresholds"]["hot"] == 70
        # warm deve usar valor fornecido
        assert result["thresholds"]["warm"] == 50
        # recencyMaxPoints deve usar default
        assert result["scoring"]["recencyMaxPoints"] == 40
        # staleDays deve usar default
        assert result["scoring"]["staleDays"] == 30
    
    def test_sanitize_config_with_non_dict(self):
        """Deve usar defaults quando valor não é dict"""
        result = _sanitize_config("not a dict")
        
        assert result == DEFAULT_CONFIG
    
    def test_sanitize_config_preserves_descriptions(self):
        """Deve preservar descrições customizadas"""
        raw_config = {
            "descriptions": {
                "hot": "Custom hot description",
                "warm": "Custom warm description",
                "cold": "Custom cold description",
            }
        }
        
        result = _sanitize_config(raw_config)
        
        assert result["descriptions"]["hot"] == "Custom hot description"
        assert result["descriptions"]["warm"] == "Custom warm description"
        assert result["descriptions"]["cold"] == "Custom cold description"
    
    def test_config_from_db_with_partial_data(self):
        """Deve mesclar defaults com dados parciais do banco"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        
        # Apenas thresholds fornecidos
        partial_config = {
            "thresholds": {
                "hot": 85,
            }
        }
        mock_result.fetchone.return_value = (partial_config,)
        mock_db.execute.return_value = mock_result
        
        config = get_lead_priority_config(db=mock_db)
        
        # hot deve ser customizado
        assert config["thresholds"]["hot"] == 85
        # warm deve usar default
        assert config["thresholds"]["warm"] == 40
        # scoring deve usar defaults
        assert config["scoring"]["recencyMaxPoints"] == 40
    
    def test_error_handling_with_fallback_defaults(self):
        """Quando há erro no banco, deve usar defaults"""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Database error")
        
        config = get_lead_priority_config(db=mock_db)
        
        # Deve retornar config padrão
        assert config == DEFAULT_CONFIG
    
    def test_clear_cache(self):
        """Testa que clear_cache limpa corretamente"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (DEFAULT_CONFIG,)
        mock_db.execute.return_value = mock_result
        
        # Popular cache
        get_lead_priority_config(db=mock_db)
        
        # Limpar cache
        clear_cache()
        
        # Cache deve estar vazio
        assert lead_priority_config_service._cache is None
        assert lead_priority_config_service._cache_timestamp is None
    
    def test_cache_expires_after_ttl(self):
        """Cache deve expirar após TTL"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (DEFAULT_CONFIG,)
        mock_db.execute.return_value = mock_result
        
        # Primeira chamada - popula cache
        get_lead_priority_config(db=mock_db)
        assert mock_db.execute.call_count == 1
        
        # Segunda chamada imediata - usa cache
        get_lead_priority_config(db=mock_db)
        assert mock_db.execute.call_count == 1
        
        # Simular expiração do cache
        clear_cache()
        
        # Terceira chamada - após limpar cache, busca novamente
        get_lead_priority_config(db=mock_db)
        assert mock_db.execute.call_count == 2
    
    def test_numeric_string_conversion(self):
        """Deve converter strings numéricas para int"""
        raw_config = {
            "thresholds": {
                "hot": "75",
                "warm": "45",
            },
            "scoring": {
                "recencyMaxPoints": "30",
            }
        }
        
        result = _sanitize_config(raw_config)
        
        assert result["thresholds"]["hot"] == 75
        assert result["thresholds"]["warm"] == 45
        assert result["scoring"]["recencyMaxPoints"] == 30
        assert isinstance(result["thresholds"]["hot"], int)
