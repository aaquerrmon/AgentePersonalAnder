CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Capturar las variables de entorno del contenedor
\getenv ro_user RO_USER
\getenv ro_pass RO_PASSWORD
\getenv db_name POSTGRES_DB

-- 2. Crear el usuario si no existe (usando \gexec para interpolar de forma segura)
SELECT format('CREATE USER %I WITH PASSWORD %L', :'ro_user', :'ro_pass')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'ro_user')\gexec

-- 3. Permisos de conexión y esquema
GRANT CONNECT ON DATABASE :"db_name" TO :"ro_user";
GRANT USAGE ON SCHEMA public TO :"ro_user";

-- 4. Permisos de solo lectura sobre tablas y secuencias actuales
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"ro_user";
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO :"ro_user";

-- 5. Permisos automáticos para las tablas que se creen en el futuro
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO :"ro_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO :"ro_user";