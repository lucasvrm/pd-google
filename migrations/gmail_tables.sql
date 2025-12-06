CREATE TABLE IF NOT EXISTS emails (
    id SERIAL PRIMARY KEY,
    google_message_id VARCHAR(255) UNIQUE NOT NULL,
    thread_id VARCHAR(255) NOT NULL,

    -- Associações
    user_email VARCHAR(255),       -- Quem enviou/recebeu (o dono da caixa)
    entity_id VARCHAR(255),        -- Lead/Deal ID vinculado (opcional no MVP, pode ser inferido depois)
    entity_type VARCHAR(50),       -- 'lead', 'deal'

    -- Conteúdo
    subject VARCHAR(255),
    from_address VARCHAR(255),
    to_address TEXT,               -- Lista de emails
    snippet TEXT,                  -- Resumo curto
    body_html TEXT,                -- Conteúdo completo (sanitizado)

    internal_date TIMESTAMP,       -- Data real do email
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_attachments (
    id SERIAL PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id),
    drive_file_id INTEGER REFERENCES drive_files(id), -- Link com o arquivo salvo no Drive
    file_name VARCHAR(255),
    mime_type VARCHAR(255)
);
