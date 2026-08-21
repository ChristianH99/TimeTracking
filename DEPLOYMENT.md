# Deploying on a Synology NAS

Written for a DS723+ behind DSM's own reverse proxy, which is what this app was
built to run on. Everything here works on any x86-64 Docker host; the parts that
are specifically Synology are marked, and they are the parts most likely to cost
an afternoon.

The image is `linux/amd64` only. The DS723+ is an AMD Ryzen R1600, and adding
`arm64` would mean QEMU emulation in CI for an architecture nobody here owns.

---

## 1. What to expose, and what not to

The app has **no public pages**. Every route needs a session except the sign-in
page, the OIDC callback, the health probe and the favicon — that list is
enumerated in `apps/accounts/pages.py` and a test walks the URLconf to make sure
nothing else has quietly joined it.

So: put it behind the reverse proxy on a hostname you control, give it a
certificate, and do not forward the container port from the router. The health
probe is the only thing that answers without a session and it answers `ok` or
503 and nothing else.

---

## 2. The reverse proxy rule

DSM → **Control Panel → Login Portal → Advanced → Reverse Proxy**.

| Field | Value |
|---|---|
| Source protocol | HTTPS |
| Source hostname | `zeit.example.de` (whatever you have a certificate for) |
| Source port | 443 |
| Destination protocol | HTTP |
| Destination hostname | `localhost` |
| Destination port | `8000` (or whatever you publish) |

Then, on the **Custom Header** tab, add the `WebSocket` preset *and* these two —
DSM does not send them by default and without them Django builds every redirect
as `http://` and the SSO handshake bounces:

| Header | Value |
|---|---|
| `X-Forwarded-Proto` | `https` |
| `X-Forwarded-Host` | `$host` |

`DJANGO_TRUST_PROXY_HEADERS=True` in the environment is what makes Django
believe them. **Leave it `False` if the app is ever reachable without going
through the proxy**, because a client that can set those headers itself can then
tell Django it arrived over HTTPS when it did not.

---

## 3. The Synology SSO client

### 3.1 Create it in DSM

**Control Panel → Domain/LDAP → SSO Client**, or **Application Portal → SSO
Server** on newer DSM. Create an **OIDC** application:

- **Redirect URI** — `https://zeit.example.de/oidc/callback/`. Exactly that,
  **including the trailing slash**; a mismatch here is refused by the provider
  with an error that does not say which of the two strings is wrong.
- **Scopes** — `openid`, `profile`, `email`, and `groups` if you have it.

DSM shows you a **client ID** and a **client secret**. The secret is shown once.

### 3.2 Fill it in, in the order that cannot lock you out

In the app: **Settings → Sign-in**. Enter the issuer, client ID and secret, save,
and *then* switch SSO on — not the other way round. A configuration that is
switched on and incomplete is one nobody can sign in through, including you.

**The local password form stays reachable at `?local=1` whatever is configured**,
and that is deliberate: `https://zeit.example.de/accounts/login/?local=1` is the
way back in when the provider is down or the issuer was typed wrong. Keep one
local superuser account for exactly that.

### 3.3 Where the secret lives

In the database, encrypted with a key derived from `DJANGO_SECRET_KEY`, never
rendered back to a browser, behind a superuser-only page. `apps/accounts/models.py`
states the trade at length. The consequence to know: **changing
`DJANGO_SECRET_KEY` makes the stored secret unreadable** and you will have to
paste it in again.

### 3.4 The trap that is not obvious: hairpin DNS

The container has to reach the provider at the *same* hostname the browser uses,
and inside Docker on the NAS that name usually resolves to the public IP — which
the NAS then refuses to route back to itself. The symptom is a callback that
times out while the login page works perfectly.

Fix it with an `extra_hosts` entry pinning the hostname to the NAS's LAN
address:

```yaml
extra_hosts:
  - "zeit.example.de:192.168.1.10"
```

---

## 4. The container

### 4.1 The data folder

Everything the app writes lives under `/data`: the SQLite database, the log, and
the generated signing key if you did not supply one. Nothing else is written
anywhere — there is no upload path and no `MEDIA_ROOT`.

```sh
mkdir -p /volume1/docker/timetracking/data
```

**Then find the uid that owns it.** On `/volume1/docker`, which is an
ACL-enabled share, `chown` appears to succeed and grants nothing — so the
container's own uid 1000 ends up unable to write, and the app fails at the first
migration with a database it cannot open.

```sh
stat -c '%u %g' /volume1/docker/timetracking/data
```

Put those two numbers into `.env` as `TIMETRACK_UID` and `TIMETRACK_GID`. The
entrypoint runs as them.

### 4.2 Configure

Copy `env.example` from the release assets to `.env` beside the compose file and
fill in:

```sh
DJANGO_SECRET_KEY=          # 50+ random characters; changing it invalidates the OIDC secret
DJANGO_ALLOWED_HOSTS=zeit.example.de
DJANGO_CSRF_TRUSTED_ORIGINS=https://zeit.example.de
DJANGO_TRUST_PROXY_HEADERS=True
DJANGO_TIME_ZONE=Europe/Berlin
TIMETRACK_UID=1026
TIMETRACK_GID=100
```

Nothing loads `.env` automatically — Django reads the process environment, and
`docker compose` is what passes it in.

`DJANGO_TIME_ZONE` is the *server's* clock, used for displaying stored
timestamps. **The clock the app measures work against is a setting inside the
app** (Settings → Working time → Time zone), because a NAS's zone is a fact
about the NAS and not a statement about where the staff stand. Set both.

### 4.3 Get the image and start it

Either from the registry:

```sh
sudo docker login ghcr.io -u <github-username> --password-stdin   # private packages only
sudo docker compose pull
sudo docker compose up -d
```

or from the tarball attached to the release, which needs no registry, no token
and no network:

```sh
gunzip -c timetracking-0.1.0-linux-amd64.tar.gz | sudo docker load
sudo docker compose up -d
```

Verify the checksums first — `SHA256SUMS` is attached to the same release:

```sh
sha256sum -c SHA256SUMS
```

Migrations run automatically on start (`deploy/entrypoint.sh`). Watch them:

```sh
sudo docker compose logs -f
```

### 4.4 `check --deploy`, and the warnings that stay

```sh
sudo docker compose exec app python manage.py check --deploy
```

Two warnings are expected and correct behind a reverse proxy that terminates
TLS:

- **`security.W008`** — `SECURE_SSL_REDIRECT` is off, because the proxy already
  redirects and doing it twice makes a loop.
- **`security.W004`** — HSTS is short by default. Raise
  `DJANGO_HSTS_SECONDS` once you are sure the certificate renews cleanly; it
  cannot be revoked before it expires.

Anything else is worth reading.

---

## 5. First sign-in

1. Open `https://zeit.example.de/accounts/login/?local=1` and sign in as the
   superuser created during setup.
2. **Settings → Working time** — set the federal state (nine of the thirteen
   public holidays depend on it), the full-time week, the leave entitlement, and
   the time zone.
3. **Settings → Public holidays** — generate the current and next year.
4. **Team → Employees** — add everybody. The **sign-in name** is what the
   directory calls them (`anna.berger`), *not* an e-mail address; the form
   suggests `firstname.surname` and stops the moment you type. Fill in what each
   person **arrived with** if they came from another contract.
5. **Team → Roster** — draft the week from the contracts, then drag.

The link between an employee and their login is made by itself the first time
they sign in, matched on that sign-in name. Nobody needs an account to be
rostered.

---

## 6. Backups

The whole application state is one SQLite file:
`/volume1/docker/timetracking/data/db.sqlite3` (plus its `-wal` and `-shm`
companions).

Point **Hyper Backup** at the folder. To take a consistent copy while the app is
running, use SQLite's own backup rather than copying the file:

```sh
sudo docker compose exec app python -c \
  "import sqlite3,os; s=sqlite3.connect(os.environ['TIMETRACK_DATA_DIR']+'/db.sqlite3'); \
   d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d); d.close(); s.close()"
```

**There is deliberately no in-app export.** The database is one file that
Hyper Backup already covers, and a payroll export is a format question nobody
has asked yet.

---

## 7. Updating, and rolling back

```sh
# edit docker-compose.yml to the new version tag, then:
sudo docker compose pull
sudo docker compose up -d
```

The compose file from a release pins an exact version rather than `latest`,
**because a file that says `latest` cannot be rolled back by re-reading it.**
Rolling back is editing the tag back and running the same two commands.

Two things to know before rolling back:

- **Migrations are not automatically reversed.** Every migration in this project
  has a reverse, but going back a version does not run it. If the new version
  added a column, the old code simply ignores it, which is safe. If it *removed*
  one, restore the database from backup instead.
- Check the version the app reports, not the one you asked for. It is in the
  sidebar footer, and after a failed update "what did I build" and "what am I
  looking at" are different questions.

---

## 8. Cutting a release

Tag it and push the tag. `.github/workflows/release.yml` does the rest: it runs
the whole test suite, builds the image, **starts it and checks it serves**, then
pushes to GHCR and attaches a loadable tarball, a pinned compose file, the
example environment file and their checksums to the GitHub release.

```sh
git tag -a v0.1.0 -m "..."
git push origin v0.1.0
```

A tag cannot publish an image the suite has not passed — the release workflow
calls the CI workflow rather than repeating its steps, so a release can never be
verified by a stale copy of the checks.

---

## 9. When something is wrong

| Symptom | Where to look |
|---|---|
| Container restarts in a loop | `docker compose logs`. Almost always `/data` not writable — see 4.1. |
| `DisallowedHost` | `DJANGO_ALLOWED_HOSTS` does not contain the hostname the browser used. |
| CSRF failures on every form | `DJANGO_CSRF_TRUSTED_ORIGINS` missing the scheme, or `X-Forwarded-Proto` not reaching Django. |
| Login page fine, callback times out | Hairpin DNS — see 3.4. |
| Signed in, but "no contract" | The employee row's sign-in name does not match what the provider sent. Link it by hand on the employee page. |
| Every page unstyled | `collectstatic` did not run in the image build. It is a build step in `deploy/Dockerfile`; a hand-built image that skipped it will do this. |
| Times an hour out all summer | The zone database is missing, or the in-app time zone is wrong. `tzdata` is a pinned dependency for exactly this; a test asserts Europe/Berlin resolves. |
| Health check red, app looks fine | `/healthz` runs one `SELECT 1`. A red probe with working pages means the database file has gone away underneath the process. |
