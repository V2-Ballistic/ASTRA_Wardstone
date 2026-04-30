"""F-009: install audit_log append-only triggers via Alembic

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-30

Pre-fix state: ``database/migrations/audit_append_only.sql`` shipped
the BEFORE UPDATE/DELETE/TRUNCATE triggers but was never auto-applied
— SECURITY.md listed it in a manual operator checklist. In practice
no default install had the triggers, so the "tamper-evident audit
log" was tamper-evident in app code only; a DBA could silently UPDATE
/ DELETE rows. NIST AU-9 control was broken-by-default.

Pre-flight (per remediation plan): grepped backend/ for any path that
UPDATE/DELETE/TRUNCATEs audit_log — none exist. record_event() is
INSERT-only; the audit router is read-only; no admin redaction or
GDPR right-to-erasure path touches the table. Safe to install.

Upgrade installs three trigger functions + three triggers, mirroring
the original audit_append_only.sql exactly so the SQL file remains a
useful out-of-band reference.

Downgrade drops the triggers and their underlying functions in
reverse order.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPGRADE_SQL = """
-- 1. Prevent UPDATE
CREATE OR REPLACE FUNCTION audit_log_prevent_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'NIST 800-53 AU-9: audit_log records are immutable. '
        'UPDATE is prohibited.  Attempted on id=%', OLD.id;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_no_update ON audit_log;
CREATE TRIGGER trg_audit_log_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION audit_log_prevent_update();

-- 2. Prevent DELETE
CREATE OR REPLACE FUNCTION audit_log_prevent_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'NIST 800-53 AU-9: audit_log records are immutable. '
        'DELETE is prohibited.  Attempted on id=%', OLD.id;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_no_delete ON audit_log;
CREATE TRIGGER trg_audit_log_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION audit_log_prevent_delete();

-- 3. Prevent TRUNCATE
CREATE OR REPLACE FUNCTION audit_log_prevent_truncate()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'NIST 800-53 AU-9: TRUNCATE on audit_log is prohibited.';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_no_truncate ON audit_log;
CREATE TRIGGER trg_audit_log_no_truncate
    BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT
    EXECUTE FUNCTION audit_log_prevent_truncate();
"""


_DOWNGRADE_SQL = """
DROP TRIGGER IF EXISTS trg_audit_log_no_truncate ON audit_log;
DROP TRIGGER IF EXISTS trg_audit_log_no_delete ON audit_log;
DROP TRIGGER IF EXISTS trg_audit_log_no_update ON audit_log;
DROP FUNCTION IF EXISTS audit_log_prevent_truncate();
DROP FUNCTION IF EXISTS audit_log_prevent_delete();
DROP FUNCTION IF EXISTS audit_log_prevent_update();
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
