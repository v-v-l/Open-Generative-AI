#!/bin/sh
set -eu
# The app role owns only this dedicated database, with no cluster privileges.
psql -v ON_ERROR_STOP=1 --username postgres --dbname nora_media_prod --set=app_password="$MEDIA_DATABASE_PASSWORD" <<'SQL'
CREATE ROLE nora_media LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER DATABASE nora_media_prod OWNER TO nora_media;
REVOKE ALL ON DATABASE nora_media_prod FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE nora_media_prod TO nora_media;
SQL
