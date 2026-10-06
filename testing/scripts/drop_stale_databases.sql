DO $$
DECLARE
    db_name text;
BEGIN
    FOR db_name IN
        SELECT datname
        FROM pg_database
        WHERE datname LIKE 'app_template_%' OR datname LIKE 'test_%'
    LOOP
        EXECUTE format('DROP DATABASE IF EXISTS %I WITH (FORCE)', db_name);
    END LOOP;
END
$$;
