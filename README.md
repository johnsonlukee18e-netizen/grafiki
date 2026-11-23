# Grafiki pielegniarek - system generowania i zarzadzania grafikami

Aplikacja webowa do ukladania miesiecznych grafikow pracy pielegniarek
i opiekunek na oddziale szpitalnym. Grafik uklada solver **OR-Tools CP-SAT**,
a **niezalezny walidator** sprawdza gotowy wynik jeszcze raz, od zera.

```
GENEROWANIE -> WALIDACJA -> RECZNA KOREKTA -> PONOWNA WALIDACJA -> ZATWIERDZENIE -> PDF
```

Wygenerowany grafik **nigdy** nie jest automatycznie zatwierdzony, a grafik
z bledem twardego ograniczenia **nie moze** zostac zatwierdzony.

---

## Spis tresci

1. [Stos technologiczny](#stos-technologiczny)
2. [Reguly grafiku](#reguly-grafiku)
3. [Szybki start (VPS, Docker)](#szybki-start-vps-docker)
4. [Konfiguracja Google OAuth](#konfiguracja-google-oauth)
5. [Zmienne srodowiskowe](#zmienne-srodowiskowe)
6. [Reverse proxy i TLS (VPS)](#reverse-proxy-i-tls-vps)
7. [Pierwszy administrator](#pierwszy-administrator)
8. [Kopie zapasowe](#kopie-zapasowe)
9. [Aktualizacja](#aktualizacja)
10. [Praca lokalna (development)](#praca-lokalna-development)
11. [Testy](#testy)
12. [CI/CD - wdrozenie z GitHuba](#cicd---wdrozenie-z-githuba)
13. [Struktura projektu](#struktura-projektu)
14. [API](#api)
15. [Decyzje projektowe i ograniczenia](#decyzje-projektowe-i-ograniczenia)

---

## Stos technologiczny

| Warstwa   | Technologia                                                                 |
| --------- | --------------------------------------------------------------------------- |
| Frontend  | React 18, TypeScript, Vite, Bootstrap 5, React Router, TanStack Query, FullCalendar |
| Backend   | Python 3.12, FastAPI, SQLAlchemy 2.x, Pydantic v2, Alembic                   |
| Solver    | OR-Tools CP-SAT                                                              |
| PDF       | ReportLab (A4 poziomo)                                                       |
| Baza      | PostgreSQL 16 (wylacznie - bez SQLite)                                       |
| Logowanie | Google OAuth 2.0 / OpenID Connect (bez hasel)                                |
| Wdrozenie | Docker Compose: backend + frontend + postgres; TLS i domena - reverse proxy na VPS |

---

## Reguly grafiku

### Twarde ograniczenia (nigdy nie moga byc zlamane)

| # | Regula | Domyslnie | Konfigurowalne |
| - | ------ | --------- | -------------- |
| 1 | Minimalna obsada na kazdej zmianie | 2 osoby na D, R i N | tak (per zmiana) |
| 1b | Minimalna liczba pielegniarek w obsadzie zmiany | 1 (nowe instalacje), 0 = wylaczone | tak (per zmiana) |
| 1c | Ranek (R) tylko w dni robocze - nigdy w sobote, niedziele i swieto | wlaczone dla R | tak (per zmiana, "Tylko dni robocze") |
| 2 | Maksymalny tygodniowy czas pracy | 37:55 (2275 minut) | tak |
| 3 | Minimalny odpoczynek miedzy zmianami | 11 h (660 minut) | tak |
| 4 | Po nocce tylko wolne albo kolejna noc | - | - |
| 5 | Co N-ta niedziela wolna | co 4. | tak (N, tryb, kotwica) |
| 6 | Zgloszona niedostepnosc | - | - |
| 7 | Jedna zmiana dziennie na pracownika | - | - |
| 8 | Brak zmian przed data zatrudnienia | - | - |

Czas pracy jest liczony **wylacznie w minutach** (nigdy w liczbach
zmiennoprzecinkowych), a odpoczynek na **rzeczywistych znacznikach czasu**:
noc 10.09 to `10.09 19:00 -> 11.09 07:00`.

Tydzien liczy sie od **poniedzialku do niedzieli** i **nie resetuje sie**
na granicy miesiaca - generator i walidator wczytuja grafiki sasiednich
miesiecy. To samo dotyczy odpoczynku, reguly po nocce i cyklu niedziel.

### Miekkie kryteria (optymalizowane, kolejnosc wg wagi)

1. rowny podzial nocy, 2. weekendow, 3. swiat, 4. laczny czas pracy,
5. preferencje zmian, 6. preferowane dni wolne.

Wagi zmienia sie w panelu **Ustawienia** - nie sa zaszyte w kodzie.

### Kolory pracownikow

Kolor **wynika z danych** i nie da sie go ustawic recznie:

| Rola | Staz | Kolor |
| ---- | ---- | ----- |
| Pielegniarka | powyzej 3 lat | czerwony |
| Pielegniarka | powyzej 1 roku do 3 lat | zolty |
| Pielegniarka | do 1 roku | zielony |
| Opiekunka | dowolny | fioletowy |

### Zmiany

| Kod | Nazwa | Godziny | Czas |
| --- | ----- | ------- | ---- |
| D | Dzien | 07:00-19:00 | 720 min |
| R | Ranek | 07:00-14:35 | 455 min |
| N | Noc | 19:00-07:00 (przez polnoc) | 720 min |
| W | Wolne | - | 0 min |

Godziny sa przechowywane w bazie (tabela `shifts`) i edytowalne w Ustawieniach.

---

## Szybki start (VPS, Docker)

### 1. Zainstaluj Dockera

Na czystym Ubuntu 22.04/24.04:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker
docker compose version
```

### 2. Sklonuj repozytorium

```bash
git clone <adres-repozytorium> /opt/nurse-scheduler
cd /opt/nurse-scheduler
```

### 3. Utworz plik `.env`

```bash
cp .env.example .env
openssl rand -hex 32          # wynik wklej do SESSION_SECRET
openssl rand -hex 24          # wynik wklej do POSTGRES_PASSWORD
nano .env
```

Uzupelnij co najmniej: `POSTGRES_PASSWORD`, `SESSION_SECRET`,
`FRONTEND_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`GOOGLE_REDIRECT_URI`, `INITIAL_ADMIN_EMAILS`.

> `.env` nigdy nie trafia do repozytorium - jest w `.gitignore`. Ten krok
> jeszcze nie dotyczy domeny ani certyfikatu - stack sam nigdy nie terminuje
> TLS, wiec zajmiesz sie tym w kroku [Reverse proxy i TLS](#reverse-proxy-i-tls-vps),
> po pierwszym uruchomieniu.

### 4. Zbuduj i uruchom

```bash
docker compose build
docker compose up -d
docker compose ps
```

Migracje Alembic uruchamiaja sie **automatycznie** przy starcie kontenera
`backend` (`SEED_ON_START=true` dodaje takze zmiany D/R/N, konfiguracje
oddzialu i polskie swieta).

### 5. Sprawdz

```bash
curl -s http://127.0.0.1:${BACKEND_PORT:-8000}/api/health
# {"status":"ok","database":"ok","env":"production"}
```

To sprawdza backend bezposrednio na loopbacku, z pominieciem reverse proxy -
na tym etapie strona nie jest jeszcze widoczna publicznie. Zobacz
[Reverse proxy i TLS](#reverse-proxy-i-tls-vps), zeby wystawic ja pod domena.

### Recznie uruchamiane operacje

```bash
# migracje (gdyby trzeba bylo je wywolac osobno)
docker compose exec backend alembic upgrade head

# dane bazowe (zmiany, konfiguracja, swieta) - idempotentne
docker compose exec backend python -m app.seed

# dodatkowo dane demonstracyjne (16 pracownikow + przykladowe dostepnosci)
docker compose exec backend python -m app.seed --demo --year 2026 --month 9
```

---

## Konfiguracja Google OAuth

1. Wejdz na <https://console.cloud.google.com/>.
2. **Utworz projekt**: gorny pasek -> *Select a project* -> *NEW PROJECT*.
   Nazwa np. `grafiki-pielegniarek`.
3. **OAuth consent screen** (menu: *APIs & Services -> OAuth consent screen*):
   - typ uzytkownika: **Internal**, jesli macie Google Workspace i tylko
     pracownicy maja sie logowac; w przeciwnym razie **External**,
   - *App name*: nazwa widoczna na ekranie logowania,
   - *User support email* i *Developer contact information*: adres e-mail,
   - zakresy (*Scopes*): wystarcza domyslne `openid`, `email`, `profile`,
   - przy typie **External** dodaj adresy osob, ktore beda sie logowac,
     w sekcji *Test users* (albo opublikuj aplikacje).
4. **Utworz OAuth Client** (*APIs & Services -> Credentials ->
   CREATE CREDENTIALS -> OAuth client ID*):
   - *Application type*: **Web application**,
   - *Name*: dowolna, np. `nurse-scheduler-prod`,
   - **Authorized JavaScript origins**: `https://twoja-domena.pl`
     (bez ukosnika na koncu). Formalnie nie jest wymagane przy przeplywie
     Authorization Code po stronie serwera, ale nie zaszkodzi,
   - **Authorized redirect URIs**: dokladnie ta sama wartosc,
     ktora ustawisz w `GOOGLE_REDIRECT_URI`, czyli
     `https://twoja-domena.pl/api/auth/google/callback`.
5. Po zapisaniu Google pokaze **Client ID** i **Client secret** - sa tez
   dostepne pozniej: *Credentials -> OAuth 2.0 Client IDs -> (klient) ->
   ikona edycji / Download JSON*.
6. Wklej je do `.env` jako `GOOGLE_CLIENT_ID` i `GOOGLE_CLIENT_SECRET`,
   a nastepnie zrestartuj backend:

```bash
docker compose up -d --force-recreate backend
```

> Redirect URI **musi** zgadzac sie co do znaku - inaczej Google zwroci
> `redirect_uri_mismatch`. Backend wypisuje uzywana wartosc przy starcie,
> wiec sprawdzisz ja bez zgadywania:
>
> ```bash
> docker compose logs backend | grep 'OAuth redirect URI'
> ```
>
> Uwaga: `docker compose restart` **nie czyta ponownie** `.env`. Po edycji
> pliku uzyj `docker compose up -d --force-recreate backend`.
>
> Domena nie jest nigdzie zaszyta w kodzie - pochodzi wylacznie ze zmiennej
> `GOOGLE_REDIRECT_URI`.

### Co robi backend

Aplikacja realizuje pelny **Authorization Code Flow**:
`GET /api/auth/google` generuje `state` + `nonce` i zapisuje je w podpisanym,
krotkozyjacym ciasteczku HTTP-only. W `GET /api/auth/google/callback` backend
sprawdza `state`, wymienia kod na tokeny **po stronie serwera**, a nastepnie
weryfikuje `id_token`: podpis (JWKS Google), `iss`, `aud`, `exp`, `nonce`
i `email_verified`. Zadne dane tozsamosci przekazane z przegladarki nie sa
przyjmowane na wiare.

---

## Zmienne srodowiskowe

Pelna lista z komentarzami: [`.env.example`](.env.example).

| Zmienna | Znaczenie |
| ------- | --------- |
| `APP_ENV` | `production` / `development` / `test` |
| `DATABASE_URL` | polaczenie do PostgreSQL (w Dockerze skladane z `POSTGRES_*`) |
| `SESSION_SECRET` | klucz podpisu ciasteczka sesji, min. 32 znaki |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | dane klienta OAuth |
| `GOOGLE_REDIRECT_URI` | musi byc identyczne z wpisem w Google Console |
| `GOOGLE_ALLOWED_DOMAIN` | opcjonalne ograniczenie do jednej domeny Workspace |
| `BACKEND_PORT` / `FRONTEND_PORT` | porty publikowane na `127.0.0.1` dla reverse proxy na hoscie |
| `FRONTEND_URL` | adres SPA (uzywany przy przekierowaniach i CORS) |
| `INITIAL_ADMIN_EMAILS` | e-maile, ktore przy pierwszym logowaniu dostaja role ADMIN |
| `SOLVER_TIME_LIMIT_SECONDS` | budzet czasu solvera (domyslnie 60 s) |
| `SEED_ON_START` / `SEED_DEMO` | automatyczne dane bazowe / demonstracyjne |
| `DEV_AUTH_ENABLED` | logowanie lokalne bez Google - **ignorowane przy `APP_ENV=production`** |

Sekrety trzymaj wylacznie w `.env` (lub w GitHub Secrets przy CI/CD).
W repozytorium nie ma i nie moze byc zadnych rzeczywistych wartosci.

---

## Reverse proxy i TLS (VPS)

Ten stack **nigdy nie wiaze sie z portem 80 ani 443 i nigdy nie terminuje
TLS**. `docker compose up -d` publikuje wylacznie:

```
backend  -> 127.0.0.1:${BACKEND_PORT:-8000}
frontend -> 127.0.0.1:${FRONTEND_PORT:-8080}
```

czyli tylko na petli zwrotnej - z zewnatrz nieosiagalne. Publiczna domene,
HTTPS i certyfikat zapewnia reverse proxy, ktory **juz dziala na Twoim
VPS**, a certyfikat dla przegladarki wystawia Cloudflare. Nie ma tu wlasnego
kontenera nginx do zarzadzania ani certyfikatu do odnawiania.

### 1. Dodaj server block na hoscie

Gotowy przyklad: [`docs/nginx-host-example.conf`](docs/nginx-host-example.conf).
Skopiuj go, podmien domene, wlacz i przeladuj:

```bash
sudo cp docs/nginx-host-example.conf /etc/nginx/sites-available/grafiki
sudo ln -s /etc/nginx/sites-available/grafiki /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Minimum, ktore musi sie w nim znalezc - **bez TLS**, bo o to dba Cloudflare:

```nginx
server {
    listen 80;
    server_name grafiki.twoja-domena.pl;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 180s;   # generowanie grafiku trwa
        proxy_send_timeout 180s;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Dwie rzeczy, ktore psuja sie po cichu, jesli ich zabraknie:

- **`proxy_read_timeout`** - domyslne 60 s nginxa utnie generowanie grafiku
  dokladnie wtedy, gdy solver dostanie pelny budzet czasu;
- **`X-Forwarded-For` ustawiony na `$remote_addr`** (nie dopisany przez
  `$proxy_add_x_forwarded_for`) - inaczej klient moze sam wstrzyknac ten
  naglowek i podszyc sie pod kogos innego wobec limitu zapytan i dziennika
  zdarzen backendu.

### 2. Cloudflare: tryb `Flexible`, bez wlasnego certyfikatu

Za pomaranczowa chmurka istnieja **dwa odcinki polaczenia**:

```
przegladarka  --(1) HTTPS-->  Cloudflare  --(2)-->  Twoj serwer
```

Wybierz **SSL/TLS -> Overview -> Flexible**. Wtedy odcinek (1) jest
szyfrowany certyfikatem Cloudflare - powszechnie zaufanym, nic nie robisz.
Odcinek (2) to zwykly HTTP, dokladnie taki, jaki mowi powyzszy server block.
**Na serwerze nie ma zadnego certyfikatu** - ani do wygenerowania, ani do
odnowienia, ani do pomylenia z czyms niezaufanym.

To dziala poprawnie z ta aplikacja: backend decyduje, czy oznaczyc
ciasteczko sesji jako `Secure`, wylacznie na podstawie `APP_ENV=production` -
nie na podstawie tego, czy konkretne zadanie przyszlo po HTTP czy HTTPS.
Przegladarka i tak zawsze widzi ta strone przez HTTPS (polaczenie do
Cloudflare), wiec logowanie dziala i sesja sie utrzymuje. Cena trybu
`Flexible` to brak szyfrowania na samym odcinku Cloudflare-serwer - w
zamian caly temat certyfikatow znika.

> Tryby `Full` i `Full (strict)` wymagalyby certyfikatu z powrotem na
> serwerze - to jest dokladnie to, czego ten wariant unika. Jesli kiedys
> zechcesz podniesc poprzeczke, wroc do wariantu z wlasnym certyfikatem
> (Let's Encrypt lub Cloudflare Origin CA) i 443 w server bloku.

### 3. Prawdziwy adres uzytkownika

Bez tego `$remote_addr` jest adresem Cloudflare przy **kazdym** zadaniu, wiec
wszyscy uzytkownicy trafiaja do jednego wspolnego licznika limitu zapytan, a w
logu i w dzienniku zdarzen widnieje proxy zamiast klienta. Gotowy plik jest w
repozytorium:

```bash
sudo cp docs/cloudflare-real-ip.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
```

Cloudflare czasem dokłada nowe zakresy - odswiez je i przeladuj nginx:

```bash
./scripts/update-cloudflare-ips.sh
```

### 4. Limit czasu

Cloudflare przerywa zadanie po **100 sekundach** i pokazuje blad 524.
Domyslny `SOLVER_TIME_LIMIT_SECONDS=60` miesci sie w limicie, ale podniesienie
go powyzej okolo 90 s sprawi, ze generowanie grafiku bedzie sie wywalac w
przegladarce, mimo ze solver dalej liczy na serwerze.

### 5. IPv6

Rekord AAAA wymaga `listen [::]:80;` w server bloku - blok tylko dla
IPv4 nigdy nie zostanie osiagniety.

### Skad sie brala "connection is untrusted" i dlaczego ten wariant to usuwa

Certyfikat samopodpisany (ten generowany kiedys skryptem `dev-certs.sh`,
ktorego juz nie ma w repozytorium) jest zaufany tylko przez przegladarke,
ktora sama go wygenerowala. Kazde inne urzadzenie - inny komputer, telefon,
a takze filtr tresci w rodzaju Fortinet WebFilter - zobaczy certyfikat
wystawiony przez nieznanego wystawce i pokaze ostrzezenie.

W tym wariancie serwer **nigdy nie prezentuje wlasnego certyfikatu** -
jedynym certyfikatem, jaki widzi ktokolwiek na zewnatrz, jest certyfikat
Cloudflare, powszechnie zaufany. To usuwa ta klase problemu calkowicie.

Jest jeden wyjatek, ktorego zadna zmiana po stronie serwera nie naprawi:
korporacyjna inspekcja SSL (Fortinet w trybie *deep inspection*, Zscaler
i podobne) podmienia certyfikat kazdej odwiedzanej strony - wlacznie z
Google czy bankami - na certyfikat wlasnego CA firmy. Jesli to CA nie jest
zainstalowane jako zaufane na danym urzadzeniu, przegladarka pokaze
dokladnie ten sam komunikat *"connection is untrusted"*, niezaleznie od
tego, jak poprawny jest certyfikat Cloudflare. To rozroznia sie po
wystawcy certyfikatu (przegladarka -> ikona klodki -> szczegoly certyfikatu):
jesli jako *Issued by* widnieje Cloudflare/Google Trust Services - problem
jest po stronie tej konkretnej sieci firmowej i naprawia go tamtejszy dzial
IT (instalacja CA firmy albo wyjatek dla tej domeny), nie ten projekt.

### Opcjonalne domkniecie

Gdy wszystko dziala: firewall przyjmujacy port 80 na tym hoscie tylko z
zakresow Cloudflare (`docs/cloudflare-real-ip.conf` ma pelna liste). Bez
tego kazdy, kto pozna surowy adres IP VPS, moze ominac Cloudflare i
polaczyc sie z serwerem bezposrednio - w tym sfalszowac `X-Forwarded-For`,
bo nic wyzej juz by go nie odtwarzalo z zaufanego zrodla.

---

## Pierwszy administrator

Role przyznawane sa automatycznie przy pierwszym logowaniu:

- e-mail wymieniony w `INITIAL_ADMIN_EMAILS` dostaje **ADMIN** i dostep od razu,
- **pierwsze konto w calym systemie** dostaje **ADMIN** (nawet gdy lista
  jest pusta - inaczej nie byloby jak zaczac),
- **kazde inne konto powstaje zablokowane**: rola MANAGER, ale bez dostepu,
  dopoki ADMIN nie wlaczy przelacznika *Aktywne* w panelu **Uzytkownicy**.

### Dlaczego konta sa domyslnie zablokowane

Poprawne zalogowanie przez Google dowodzi **kim ktos jest**, a nie tego, ze
**wolno mu** korzystac z tego systemu. Ekran zgody Google nie jest lista
kontroli dostepu: wystarczy opublikowac aplikacje (External -> In production),
zeby kazdy posiadacz konta Google, ktory trafi na adres, zalozyl sobie konto.

Dlatego kontrola dostepu jest po stronie aplikacji i nie zalezy od ustawien w
Google Cloud Console. Nowe konto pojawia sie w panelu **Uzytkownicy** z
etykieta *brak dostepu* i ostrzezeniem u gory - Ty decydujesz, kto wejdzie.

Zachowanie mozna zmienic zmienna `AUTO_ACTIVATE_NEW_USERS=true`, ale wtedy
kazdy, kto przejdzie logowanie Google, dostaje od razu dostep do danych
pracownikow. W produkcji zostaw `false`.

Dalsze zmiany rol robi sie w panelu **Uzytkownicy**. System pilnuje, zeby
zawsze zostal co najmniej jeden aktywny administrator, i nie pozwala odebrac
uprawnien wlasnemu kontu.

| Rola | Uprawnienia |
| ---- | ----------- |
| MANAGER | pracownicy, dostepnosc, generowanie, walidacja, reczna edycja, zatwierdzanie, PDF |
| ADMIN | to co MANAGER + uzytkownicy, role, ustawienia oddzialu, zmiany, swieta, dziennik zdarzen |

RBAC jest egzekwowany **na backendzie**; ukrycie przycisku w SPA nigdy nie
jest traktowane jako zabezpieczenie.

---

## Kopie zapasowe

### Wykonanie

```bash
./scripts/backup.sh
```

Skrypt uruchamia `pg_dump` w kontenerze `nurse_postgres`, kompresuje wynik
gzipem, weryfikuje archiwum (`gzip -t`) i ustawia prawa `600`.

- **Gdzie ladują kopie**: katalog `backups/` w katalogu projektu
  (np. `/opt/nurse-scheduler/backups/nurse_nurse_20260906_020000.sql.gz`).
  Inna lokalizacja: `BACKUP_DIR=/srv/backups ./scripts/backup.sh`.
- **Retencja**: domyslnie 14 dni, zmienna `RETENTION_DAYS`.
- Katalog `backups/` jest w `.gitignore`.

### Codzienny cron

```bash
crontab -e
```

```cron
# kopia bazy codziennie o 02:00
0 2 * * * cd /opt/nurse-scheduler && BACKUP_DIR=/srv/backups RETENTION_DAYS=30 ./scripts/backup.sh >> /var/log/nurse-backup.log 2>&1
```

> Trzymaj kopie takze **poza serwerem** (np. `rclone`, `scp` na inny host).

### Odtworzenie

```bash
docker compose stop backend
./scripts/restore.sh backups/nurse_nurse_20260906_020000.sql.gz
docker compose up -d backend
```

Skrypt prosi o potwierdzenie nazwy bazy, bo nadpisuje jej zawartosc.
Zrzut powstaje z `--clean --if-exists`, wiec da sie go zaladowac na
istniejaca baze.

---

## Aktualizacja

```bash
cd /opt/nurse-scheduler
./scripts/backup.sh                        # najpierw kopia
git fetch origin && git checkout -B main origin/main
docker compose build
docker compose up -d
docker compose logs -f backend             # migracje wykonaja sie automatycznie
```

> Dlaczego nie `git pull`: wdrozenie przypina dokladny commit przez
> `git checkout --detach`, wiec repozytorium na serwerze nie stoi na galezi i
> `git pull` konczy sie komunikatem *"You are not currently on a branch"*.
> `git checkout -B main origin/main` dziala w obu przypadkach.

Wycofanie do poprzedniej wersji:

```bash
git checkout <poprzedni-tag>
docker compose up -d --build
./scripts/restore.sh backups/<kopia-sprzed-aktualizacji>.sql.gz
```

---

## Praca lokalna (development)

Wymagania: Python 3.12+, Node 20+, Docker.

```bash
# 1. PostgreSQL w Dockerze (port 5433, zeby nie kolidowac z lokalnym)
docker compose -f docker-compose.dev.yml up -d

# 2. Backend
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash); Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env              # i ustaw DATABASE_URL na localhost:5433
alembic upgrade head
python -m app.seed --demo --year 2026 --month 9
uvicorn app.main:app --reload --port 8000

# 3. Frontend (drugi terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Vite proxuje `/api` na `http://127.0.0.1:8000`, dzieki czemu ciasteczko sesji
jest same-origin - dokladnie jak za reverse proxy w produkcji.

> Oba pliki Compose maja wlasne nazwy projektow (`nurse` i `nurse-dev`),
> wiec stack produkcyjny i deweloperska baza moga dzialac obok siebie na
> jednej maszynie i nie kasuja sobie kontenerow.

**Logowanie lokalne bez Google**: ustaw w `backend/.env`

```
APP_ENV=development
DEV_AUTH_ENABLED=true
DEV_AUTH_EMAIL=dev.admin@example.com
```

Na ekranie logowania pojawi sie przycisk *Zaloguj lokalnie jako administrator*.
Endpoint `POST /api/auth/dev-login` zwraca **404**, gdy `APP_ENV=production` -
niezaleznie od wartosci `DEV_AUTH_ENABLED`.

---

## Testy

```bash
cd backend
pytest -q                 # calosc (potrzebny dzialajacy PostgreSQL)
pytest -q tests/test_hours_limit.py tests/test_rest_and_night.py   # sam rdzen regul
```

Testy API tworza i kasuja osobna baze `<nazwa>_test`; testy rdzenia
scheduler'a nie potrzebuja bazy w ogole.

Zakres (pokrywa liste z wymagan):

| Obszar | Plik |
| ------ | ---- |
| limit 37:55, przekroczenie, tygodnie na granicy miesiaca | `tests/test_hours_limit.py` |
| dokladnie 11 h, mniej niz 11 h, noc->wolne, noc->noc, noc->ranek, noc->dzien | `tests/test_rest_and_night.py` |
| minimum obsady, niedostepnosc, diagnostyka braku rozwiazania | `tests/test_staffing_and_availability.py` |
| co 4. niedziela, ciaglosc cyklu miedzy miesiacami, tryby cyklu | `tests/test_sundays.py` |
| swieta PL (dowolny rok), rowny podzial nocy i weekendow, powtarzalnosc | `tests/test_holidays_and_fairness.py` |
| autoryzacja, RBAC, OAuth state/nonce, CSRF, rate limiting, naglowki | `tests/test_api_security.py` |
| pelny przeplyw: generacja -> edycja -> walidacja -> zatwierdzenie -> PDF | `tests/test_api_workflow.py` |

Frontend:

```bash
cd frontend
npm run lint     # tsc --noEmit
npm run build
```

---

## CI/CD - wdrozenie z GitHuba

W repozytorium sa dwa przeplywy:

- **`.github/workflows/ci.yml`** - przy kazdym push i pull requescie:
  testy backendu na prawdziwym PostgreSQL, kontrola typow i build frontendu,
  proba zbudowania obrazow Dockera.
- **`.github/workflows/deploy.yml`** - po zielonym CI na galezi `main`
  (albo recznie, *Run workflow*): laczy sie po SSH z VPS, robi kopie bazy,
  pobiera nowa wersje i przebudowuje stack.

### Konfiguracja jednorazowa

1. Na VPS przygotuj katalog i klucz wdrozeniowy:

```bash
sudo mkdir -p /opt/nurse-scheduler && sudo chown "$USER" /opt/nurse-scheduler
git clone <adres-repozytorium> /opt/nurse-scheduler
cd /opt/nurse-scheduler && cp .env.example .env && nano .env

# klucz uzywany wylacznie przez GitHub Actions
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/github_deploy          # zawartosc -> sekret DEPLOY_SSH_KEY
```

2. W GitHubie: *Settings -> Secrets and variables -> Actions* dodaj sekrety:

| Sekret | Wartosc |
| ------ | ------- |
| `DEPLOY_HOST` | adres IP lub domena VPS |
| `DEPLOY_USER` | uzytkownik SSH (nie root) |
| `DEPLOY_SSH_KEY` | prywatny klucz `~/.ssh/github_deploy` |
| `DEPLOY_PORT` | port SSH (opcjonalny, domyslnie 22) |
| `DEPLOY_PATH` | sciezka projektu, np. `/opt/nurse-scheduler` |

3. Wypchnij zmiany na `main` - reszta dzieje sie sama.

Plik `.env` **zostaje na serwerze** i nigdy nie jest nadpisywany przez
wdrozenie. Zaden sekret nie trafia do repozytorium.

---

## Struktura projektu

```
nurse-scheduler/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI, middleware, obsluga bledow
│   │   ├── config.py               # ustawienia z ENV (pydantic-settings)
│   │   ├── seed.py                 # dane bazowe i demonstracyjne
│   │   ├── api/                    # routery REST + RBAC (deps.py)
│   │   ├── models/                 # SQLAlchemy 2.x
│   │   ├── schemas/                # Pydantic v2
│   │   ├── security/               # sesje, OAuth, CSRF, naglowki, rate limit
│   │   ├── services/               # logika aplikacyjna, PDF, audyt
│   │   ├── scheduler/              # rdzen regul (czysty Python, bez bazy)
│   │   │   ├── rules.py            # JEDNO zrodlo prawdy dla wszystkich regul
│   │   │   ├── models.py           # struktury danych planowania
│   │   │   ├── constraints.py      # twarde ograniczenia w modelu CP-SAT
│   │   │   ├── optimizer.py        # funkcja celu (miekkie kryteria)
│   │   │   ├── solver.py           # uruchomienie solvera
│   │   │   ├── diagnostics.py      # wyjasnienie braku rozwiazania
│   │   │   ├── validator.py        # NIEZALEZNA walidacja gotowego grafiku
│   │   │   └── statistics.py       # statystyki miesieczne
│   │   └── database/
│   ├── alembic/                    # migracje wersjonowane
│   └── tests/
├── frontend/
│   └── src/{api,components,pages,types,styles}
├── scripts/                        # backup.sh, restore.sh, update-cloudflare-ips.sh
├── docs/
│   ├── SPEC.md                     # oryginalne wymagania
│   ├── nginx-host-example.conf     # server block dla reverse proxy na VPS
│   └── cloudflare-real-ip.conf     # przywraca prawdziwy adres klienta
├── docker-compose.yml              # produkcja
├── docker-compose.dev.yml          # sam PostgreSQL do pracy lokalnej
└── .env.example
```

Kluczowa zasada: **walidator i solver nie maja dwoch implementacji tych samych
regul**. Predykaty (odpoczynek, nastepstwo po nocce, limit tygodniowy, cykl
niedziel) zyja w `app/scheduler/rules.py`, a `constraints.py` i `validator.py`
tylko z nich korzystaja.

---

## API

Wszystkie endpointy poza `/api/health` i `/api/auth/*` wymagaja sesji.
Operacje modyfikujace wymagaja naglowka `X-CSRF-Token` zgodnego z ciasteczkiem
`nurse_csrf`.

| Metoda | Sciezka | Rola |
| ------ | ------- | ---- |
| GET | `/api/auth/google` | - |
| GET | `/api/auth/google/callback` | - |
| GET | `/api/auth/status`, `/api/auth/me` | - / zalogowany |
| POST | `/api/auth/logout` | zalogowany |
| GET/POST | `/api/employees` | MANAGER |
| GET/PUT/DELETE | `/api/employees/{id}` | MANAGER |
| GET | `/api/schedules`, `/api/schedules/{year}/{month}` | MANAGER |
| POST | `/api/schedules/generate` | MANAGER |
| POST | `/api/schedules/{id}/validate`, `/approve`, `/unapprove` | MANAGER |
| GET | `/api/schedules/{id}/history`, `/history/{version}`, `/statistics` | MANAGER |
| POST | `/api/schedules/{id}/history/{version}/restore` | MANAGER |
| POST | `/api/schedules/manual` (reczne ukladanie miesiaca) | MANAGER |
| PUT | `/api/schedules/{id}/cells` (komorki grafiku w trybie recznym) | MANAGER |
| GET | `/api/schedules/{id}/pdf` | MANAGER |
| GET | `/api/schedules/{id}/employee/{employee_id}/pdf` | MANAGER |
| POST/PUT/DELETE | `/api/assignments`, `/api/assignments/{id}` | MANAGER |
| GET/POST/PUT/DELETE | `/api/availability`, `/api/availability/bulk`, `/{id}` | MANAGER |
| GET | `/api/holidays/{year}` | MANAGER |
| POST/DELETE | `/api/holidays`, `/api/holidays/{id}` | ADMIN |
| GET | `/api/settings`, `/api/settings/shifts` | MANAGER |
| PUT | `/api/settings`, `/api/settings/shifts/{id}` | ADMIN |
| GET/PUT | `/api/users`, `/api/users/{id}` | ADMIN |
| GET | `/api/audit` | ADMIN |
| GET | `/api/dashboard` | MANAGER |
| GET | `/api/health` | - |

Dokumentacja interaktywna (`/api/docs`) jest dostepna **tylko** poza produkcja -
FastAPI sam wylacza ten routing, gdy `APP_ENV=production` (`docs_url=None`),
niezaleznie od tego, co stoi przed nim.

Kody bledow: `401` brak sesji, `403` brak uprawnien lub zly token CSRF,
`404` brak zasobu, `409` konflikt z regula grafiku (z lista naruszen),
`422` bledne dane, `429` rate limit, `500` blad serwera (bez stack trace).

---

## Decyzje projektowe i ograniczenia

**Ile osob potrzeba, zeby grafik byl mozliwy.** Przy domyslnych ustawieniach
(2 osoby na D, R i N) jeden tydzien wymaga
`7 x (2x720 + 2x455 + 2x720) = 26 530` minut pracy, a jedna osoba moze
przepracowac najwyzej `2275` minut. Dziesiec osob daje `22 750` minut - grafiku
**nie da sie ulozyc** i generator to zglosi zamiast po cichu obnizyc obsade.
Minimum to **13 osob**; seed demonstracyjny tworzy **16**, zeby solver mial
zapas na rowny podzial nocy i weekendow. Jesli zespol jest mniejszy, zmniejsz
minimalna obsade w Ustawieniach - swiadomie, a nie przez przypadek.

**Gdy nie ma rozwiazania** aplikacja pokazuje konkretne przyczyny (np. brak
mocy przerobowych w danym tygodniu, dzien z niewystarczajaca liczba dostepnych
osob, a przy sprzecznosci wykrytej przez solver - konkretne dni i zmiany
z jadra niespelnialnosci CP-SAT) oraz sugestie. Nigdy nie obniza automatycznie
minimalnej obsady, nie podnosi limitu godzin i nie ignoruje niedostepnosci.

**Powtarzalnosc solvera.** Wynik jest identyczny przy tym samym ziarnie
**i `solver_workers = 1`**. Rownolegle watki CP-SAT scigaja sie miedzy soba,
wiec przy domyslnych 8 watkach dwa uruchomienia moga dac dwa rozne, rownie
dobre grafiki. Ustaw `solver_workers = 1` w Ustawieniach, jesli powtarzalnosc
jest wazniejsza niz czas.

**Niejednoznacznosci z wymagan sa konfiguracja, nie kodem:**

- *co 4. niedziela wolna* - tryb `SLIDING` (w kazdych 4 kolejnych niedzielach
  co najmniej jedna wolna; domyslny, mocniejszy i odporny na granice miesiaca)
  albo `BLOCK` (stale bloki liczone od daty kotwiczenia);
- czy nocka z soboty liczy sie jako praca w niedziele - przelacznik
  `sunday_includes_saturday_night` (domyslnie nie);
- czy zmiana moze byc obsadzona ponad minimum - `allow_overstaffing`
  oraz waga `weight_coverage_bonus` (domyslnie dodatnia, zeby grafik wypelnial
  etaty; ustaw 0, zeby planowac wylacznie minimalna obsade).

**Strefy czasowe.** Godziny zmian sa zapisywane jako czas lokalny scienny
(`2026-09-10 19:00`). Przy zmianie czasu letniego/zimowego doba ma 23 lub 25
godzin, wiec faktyczna dlugosc nocnej zmiany w te jedna noc rozni sie o godzine
od `duration_minutes`. Rozliczenie czasu pracy opiera sie na `duration_minutes`
z definicji zmiany - tak jak w grafikach papierowych.

**Brak TLS w samej aplikacji jest zamierzony.** Wczesniejsza wersja tego
projektu miala wlasny kontener nginx z certyfikatem (Let's Encrypt albo
samopodpisany do testow). Certyfikat samopodpisany byl zrodlem realnego
problemu - dowolne urzadzenie laczace sie z serwerem bezposrednio zglaszalo
go jako niezaufany. Zamiast utrzymywac certyfikat w dwoch miejscach (Cloudflare
dla przegladarki i cos innego dla origin), stack przestal w ogole terminowac
TLS: caly ruch publiczny idzie przez reverse proxy, ktory juz dziala na VPS,
a jedynym certyfikatem widocznym z zewnatrz jest certyfikat Cloudflare. Patrz
[Reverse proxy i TLS](#reverse-proxy-i-tls-vps).

**Historia.** Kazda generacja i kazda reczna korekta zapisuje pelny zrzut
grafiku w `schedule_versions`. Nic nie jest kasowane bezpowrotnie. W panelu
*Historia grafikow* kazda wersje mozna podejrzec i przywrocic - przywrocenie
samo jest nowa wersja (biezacy stan trafia najpierw do historii), a wynik jest
od razu walidowany wedlug aktualnych danych.

**Reczne ukladanie.** Osobny modul (menu *Reczne ukladanie*), w ktorym system
niczego nie generuje: manager uklada miesiac sam, klikajac w siatke albo
"pedzlem" (wybrana zmiana wpisuje sie jednym kliknieciem), i moze przeciagac
zmiany. W trakcie pracy nic nie jest blokowane - zmiany zapisuja sie jako szkic
(status *Szkic*). Przycisk **Wyslij do sprawdzenia** uruchamia walidator i
pokazuje liste rzeczy do poprawienia (klikniecie bledu zaznacza go w siatce);
poprawny grafik mozna zatwierdzic. Prosby pracownikow (preferowana zmiana,
wolne, niedostepnosc) sa widoczne jako kropka w komorce i jako sugestie:
pusta komorka pokazuje polprzezroczysta proponowana zmiane, a panel *Sugestie
z prosb* pozwala je zaakceptowac pojedynczo lub wszystkie naraz - i zmienic
pozniej. Mozna zaczac od pustego miesiaca albo od wygenerowanego grafiku.
Pierwsza zmiana po sprawdzeniu zapisuje sprawdzony stan w Historii; kolejne
zmiany szkicu nie tworza osobnych wersji. Wygenerowanie grafiku (z
potwierdzeniem) przelacza miesiac z powrotem na tryb automatyczny.

**Ranek tylko w dni robocze.** Zmiana z wlaczonym "Tylko dni robocze" (domyslnie
R) nie istnieje w soboty, niedziele i swieta: solver jej wtedy nie planuje,
jej minimalna obsada nie obowiazuje, a reczne wpisanie jej na taki dzien
walidator zglasza jako blad. Migracja wlacza to dla R w istniejacej bazie.

**Pielegniarki na zmianie.** Opiekunka nie zastapi pielegniarki, dlatego kazda
zmiana ma oprocz minimalnej obsady takze `minimum_nurses` (Ustawienia ->
Zmiany -> *Min. pielegniarek*). Migracja ustawia 0 dla istniejacych baz, zeby
nie zmienic dzialania dotychczasowych grafikow; seed nowej instalacji ustawia 1.

**Limit czasu solvera.** Generowanie dziala w ramach zadania HTTP, a Cloudflare
zrywa je po 100 s (blad 524). Limit w Ustawieniach jest wiec ograniczony do
`SOLVER_MAX_SECONDS` (domyslnie 75 s).

**Aktualnosc walidacji.** Otwarcie grafiku zawsze pokazuje walidacje
policzona od nowa (dostepnosci, pracownicy i sasiednie miesiace mogly sie
zmienic). Status grafiku edytowalnego jest aktualizowany; grafik zatwierdzony
nie zmienia statusu od samego otwarcia - pokazuje jedynie aktualne bledy.
Pracownik nieaktywny w miesiacach, ktore juz minely, nie jest bledem.

**Rownolegla praca.** Dwa jednoczesne generowania tego samego miesiaca sa
blokowane (advisory lock PostgreSQL - drugie dostaje komunikat), a reczne
korekty jednego grafiku sa wykonywane po kolei (blokada wiersza).

**PDF i polskie znaki.** Eksport uzywa czcionki DejaVu Sans (pakiet
`fonts-dejavu-core` w obrazie), bo wbudowana Helvetica nie ma liter "l", "s",
"z" z ogonkami/kreska. Inna czcionke wskazuja `PDF_FONT_REGULAR` i
`PDF_FONT_BOLD`.

**Audyt.** Logowanie, wylogowanie, operacje na pracownikach, dostepnosci,
generowanie, reczne zmiany, zatwierdzanie, eksport PDF, zmiany ustawien i rol
trafiaja do `audit_logs` (panel *Dziennik zdarzen*, tylko ADMIN).
