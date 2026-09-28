# Production

Keshtkaran runs as a Django app behind Gunicorn. WhiteNoise serves collected static files. The database is a SQLite file at `DB/db.sqlite3`, in a `DB` folder next to `manage.py`.

Local development reads `.env`. A PaaS should set the same variables in its environment. Do not commit `.env`.

## Environment

Copy `.env.example` to `.env` for local work. On the server, set these variables in the platform:

| Variable | Local | Production |
| --- | --- | --- |
| `SECRET_KEY` | Any long random string | A new secret, different from local |
| `DEBUG` | `True` | `False` |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | The public hostname, comma-separated if you have more than one |
| `CSRF_TRUSTED_ORIGINS` | Empty | `https://your-app.example.com` |
| `SECURE_SSL_REDIRECT` | `False` | `False` unless the platform does not already redirect HTTP to HTTPS |
| `PORT` | Unused by `runserver` | Set by the platform. The Procfile binds Gunicorn to it |

`DEBUG` defaults to `False` when the variable is missing, so a deploy without `.env` does not turn debug on. `SECRET_KEY` has no default. The process refuses to start until it is set.

With `DEBUG=False`, the app trusts `X-Forwarded-Proto` from the platform proxy and marks the session and CSRF cookies as secure.

## Database

SQLite lives only in `DB/`. Settings create that folder on startup if it is missing.

Mount a persistent disk on `DB/` (the directory beside `manage.py`). The rest of the app filesystem can be ephemeral. Without a persistent mount, every restart or new deploy creates an empty database.

Run one web instance. SQLite is a single file. Two containers writing the same file will corrupt it or hit lock errors. The app turns on WAL mode and a 20 second busy timeout so a couple of Gunicorn workers on that one instance can share the file.

## Build

Python dependencies are already listed in `requirements.txt` (`Django`, `gunicorn`, `whitenoise`, `python-dotenv`).

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
```

`collectstatic` writes to `staticfiles/`, which is gitignored. WhiteNoise serves that directory when `DEBUG=False`.

Styles are compiled with Tailwind into `static/css/output.css`. When templates or `tailwind/input.css` change, build CSS before deploy:

```bash
npm ci
npm run build:css
```

If the PaaS image has no Node, run that build locally and deploy the compiled `static/css/output.css` with the app.

## Start

`Procfile`:

```text
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

Platforms that ignore the Procfile can use the same command as the web process. The WSGI module is `config.wsgi:application`.

If requests fail with `database is locked`, drop to one worker:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

## First boot

After migrate, create an admin user once:

```bash
python manage.py createsuperuser
```

Seed data, if you want the sample marketplace content:

```bash
python manage.py seed
```

## Checklist

- `DEBUG=False`
- `SECRET_KEY` is new and is not the value in your local `.env`
- `ALLOWED_HOSTS` is the real hostname
- `CSRF_TRUSTED_ORIGINS` is the `https://` origin
- `DB/` is on a persistent disk
- `collectstatic` and `migrate` run on each release
- Only one app instance is writing to `DB/db.sqlite3`
