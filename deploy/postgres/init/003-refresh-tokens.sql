CREATE TABLE IF NOT EXISTS instance01.mtd_refresh_tokens (
    id uuid PRIMARY KEY,
    user_id character varying NOT NULL,
    token_hash text NOT NULL UNIQUE,
    family_id uuid NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    revoked boolean NOT NULL DEFAULT false,
    replaced_by_token uuid,
    user_agent text,
    ip_address character varying,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mtd_refresh_tokens_user_id
    ON instance01.mtd_refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_mtd_refresh_tokens_family_id
    ON instance01.mtd_refresh_tokens (family_id);
CREATE INDEX IF NOT EXISTS idx_mtd_refresh_tokens_expires_at
    ON instance01.mtd_refresh_tokens (expires_at);
