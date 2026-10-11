-- The integration tests' database (tests/integration). Runs on a fresh dev MySQL volume;
-- for an existing one: ./dev.sh exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' < scripts/test-db.sql
CREATE DATABASE IF NOT EXISTS dnd_within_test;
GRANT ALL PRIVILEGES ON dnd_within_test.* TO 'dnd'@'%';
