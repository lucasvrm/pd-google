-- Tabela para controlar o estado da sincronização incremental (Sync Token)
CREATE TABLE IF NOT EXISTS calendar_sync_states (
    id SERIAL PRIMARY KEY,
    resource_id VARCHAR(255),       -- ID do recurso retornado pelo Google ao criar o canal
    channel_id VARCHAR(255) UNIQUE, -- Nosso UUID para o canal de webhook
    calendar_id VARCHAR(255) DEFAULT 'primary', -- ID do calendário monitorado
    sync_token VARCHAR(255),        -- Token para buscar apenas alterações incrementais
    expiration TIMESTAMP,           -- Data de expiração do canal (Google exige renovação)
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Tabela para espelhar eventos locais (Cache/Mirror)
CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    google_event_id VARCHAR(255) UNIQUE NOT NULL, -- ID oficial do evento no Google
    calendar_id VARCHAR(255) DEFAULT 'primary',

    -- Dados principais
    summary VARCHAR(255),           -- Título da reunião
    description TEXT,               -- Descrição/Pauta
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,

    -- Links Importantes
    meet_link VARCHAR(255),         -- Link do Google Meet
    html_link VARCHAR(255),         -- Link para ver no Google Calendar web

    -- Metadados
    status VARCHAR(50),             -- confirmed, tentative, cancelled
    organizer_email VARCHAR(255),   -- Email de quem criou (neste caso, a Service Account)

    -- Participantes (armazenado como JSONB para simplificar leitura rápida)
    -- Ex: [{"email": "lead@gmail.com", "responseStatus": "needsAction"}]
    attendees JSONB,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
