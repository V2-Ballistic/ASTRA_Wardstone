-- ══════════════════════════════════════════════════════════════
--  ASTRA — Append-Only Audit Log Trigger
--  File: database/migrations/audit_append_only.sql   ← NEW
--
--  This migration makes the audit_log table physically
--  tamper-resistant at the database level.  Even a DBA with
--  direct psql access cannot silently UPDATE or DELETE records
--  without first dropping the trigger (which itself should be
--  gated by change-management controls).
--
--  Run once after the table is created:
--    psql -U astra -d astra -f audit_append_only.sql
-- ══════════════════════════════════════════════════════════════

-- 1. Prevent UPDATE on audit_log
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


-- 2. Prevent DELETE on audit_log
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


-- 3. Prevent TRUNCATE on audit_log
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


-- ══════════════════════════════════════════════════════════════
--  Verification:
--    INSERT INTO audit_log (...) VALUES (...);   -- ✓ allowed
--    UPDATE audit_log SET event_type='x';        -- ✗ EXCEPTION
--    DELETE FROM audit_log WHERE id=1;           -- ✗ EXCEPTION
--    TRUNCATE audit_log;                         -- ✗ EXCEPTION
-- ══════════════════════════════════════════════════════════════
