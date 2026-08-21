# The time tracking app, as one container.
#
# Two stages: the first installs the dependencies, the second copies in the
# resulting virtualenv and the code. It halves the image — the build tools,
# uv itself and the pip cache never reach the runtime layer — and it means a
# code change rebuilds only the small stage.
#
# The DS723+ is an AMD64 Ryzen, so no cross-building is needed; `docker build`
# on the NAS, or on any x86-64 machine, produces the same image.

# ---------------------------------------------------------------------------
# Stage 1: dependencies
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/venv

WORKDIR /build

# The lockfile alone first, so this layer is cached until a dependency actually
# changes. Copying the whole source here would rebuild the world on every edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim

# gettext is needed at *build* time for compilemessages; curl is what the
# HEALTHCHECK below calls. `--no-install-recommends` keeps this to what is named.
#
# **No image libraries**, and nothing else for handling uploads: this app stores
# no files at all and has no MEDIA_ROOT, which config/tests.py enforces by
# walking every model for a FileField.
#
# The IANA time zone database is *not* installed here either, and that is
# deliberate rather than an omission: it arrives as the `tzdata` wheel in
# pyproject.toml, so the container and the test suite read the same database
# from the same place. Relying on the base image's apt contents would make the
# app's answer depend on a Debian packaging decision nobody here would notice
# changing — and the failure is silent, because zones.py falls back to UTC.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gettext \
        curl \
    && rm -rf /var/lib/apt/lists/*

# A non-root user, and one whose uid is easy to grant on a Synology share: the
# bind mount at /data has to be writable by whoever this process is, and
# "chown 1000" is a sentence the DSM file manager can carry out.
RUN groupadd --gid 1000 timetrack \
    && useradd --uid 1000 --gid 1000 --create-home timetrack

# Which build this is. Supplied by .github/workflows/release.yml from the tag;
# left as "dev" for a hand-built image, which is the honest answer — an image
# built from an uncommitted working copy has no version, and printing one that
# looks official is worse than printing nothing.
#
# It is baked as an environment variable rather than only as a label because the
# app itself shows it (the sidebar footer): `docker inspect` answers "what did I
# build", and the page answers "what am I actually looking at", which after a
# failed update are different questions.
ARG TIMETRACK_VERSION=dev
ARG BUILD_REVISION=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="Time Tracking" \
      org.opencontainers.image.description="Self-hosted roster and time tracking for a small business" \
      org.opencontainers.image.source="https://github.com/ChristianH99/TimeTracking" \
      org.opencontainers.image.version="${TIMETRACK_VERSION}" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="NOASSERTION"

ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    TIMETRACK_DATA_DIR=/data \
    TIMETRACK_VERSION=${TIMETRACK_VERSION}

COPY --from=builder /venv /venv

WORKDIR /app
COPY --chown=timetrack:timetrack . /app

# The entrypoint has to be executable, and it cannot be assumed to arrive that
# way. This repository is developed on Windows, where `core.filemode` is false
# and git therefore never notices the bit — `deploy/entrypoint.sh` sat in the
# index as 0644 for its whole life. Docker Desktop hides that completely: it
# copies from an NTFS filesystem and hands everything 0755, so the image builds
# and runs perfectly on the machine it was written on, and the *same commit*
# built on Linux dies at start-up with
#
#     exec: "/app/deploy/entrypoint.sh": permission denied
#
# which is an exit code 126 and no application log at all. The mode is fixed in
# git as well; this line is here so that a checkout which loses it again — any
# Windows clone, a zip download, a `COPY` from a context that flattens modes —
# still produces an image that starts.
RUN chmod +x /app/deploy/entrypoint.sh

# Both of these are *build* steps, not start-up steps, and doing them here is
# deliberate:
#
#   collectstatic — STORAGES uses WhiteNoise's manifest storage, so {% static %}
#   resolves through staticfiles.json. Without it every page renders unstyled
#   with a dead script tag. Running it at start-up instead would mean writing to
#   the image on every boot and a slower start for no gain.
#
#   compilemessages — nothing at runtime compiles a .po. The .mo files are
#   committed, but recompiling here means a container built from a checkout that
#   forgot to is still correct.
#
# DJANGO_SECRET_KEY is supplied because settings refuses to import without one
# when DEBUG is off; it is a throwaway used by this command only and never
# reaches the running app, which gets the real one from the environment.
RUN DJANGO_DEBUG=False DJANGO_SECRET_KEY=build-only-not-a-runtime-key \
    TIMETRACK_DATA_DIR=/tmp/build \
    python manage.py collectstatic --noinput \
 && DJANGO_DEBUG=False DJANGO_SECRET_KEY=build-only-not-a-runtime-key \
    TIMETRACK_DATA_DIR=/tmp/build \
    python manage.py compilemessages --ignore=.venv \
 && rm -rf /tmp/build

# The bind mount goes here. Created and owned now so the container comes up even
# on a fresh volume.
RUN mkdir -p /data && chown timetrack:timetrack /data
VOLUME ["/data"]

USER timetrack
EXPOSE 8000

# Plain HTTP on localhost, because that is what the health check is for and what
# the reverse proxy speaks to. config/health.py explains why it says so little.
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/app/deploy/entrypoint.sh"]

# Two workers, two threads — not the usual (2 x cores) + 1. This is a small
# business app on a two-core NAS that also runs DSM, Home Assistant and a
# backup, and each worker is a whole Python interpreter. Two is enough that a
# manager rebuilding a week's roster does not block eleven people confirming
# yesterday's hours on their phones — which all arrive at once, because a
# shift ends for everybody at the same time.
#
# Comments cannot go inside the JSON array below: exec-form CMD is parsed as
# JSON, and a `#` line spliced into a line-continued instruction is not
# reliably stripped.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
