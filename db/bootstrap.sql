-- CareerOS — one-time database bootstrap
-- Run as an administrative MySQL account (e.g. root) in MySQL Workbench.
-- This creates the databases and the least-privilege application account.
-- The application password must match DATABASE_URL in backend/.env.
--
-- Already executed on this machine. Re-running is safe (IF NOT EXISTS).

CREATE DATABASE IF NOT EXISTS careeros
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS careeros_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

-- Least-privilege application user. DDL is granted because Alembic owns the schema.
CREATE USER IF NOT EXISTS 'careeros_app'@'localhost'
  IDENTIFIED BY '<SET_A_STRONG_PASSWORD>';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
  ON careeros.* TO 'careeros_app'@'localhost';

-- Test schema: full privileges so the suite can reset it freely.
GRANT ALL PRIVILEGES ON careeros_test.* TO 'careeros_app'@'localhost';

FLUSH PRIVILEGES;

-- Verification
SELECT VERSION() AS mysql_version, @@character_set_server AS charset;
SHOW DATABASES LIKE 'careeros%';
