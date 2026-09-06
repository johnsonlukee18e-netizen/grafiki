\# ZADANIE: MVP SYSTEMU DO ZARZĄDZANIA I AUTOMATYCZNEGO GENEROWANIA GRAFIKÓW PIELĘGNIAREK



Zbuduj od podstaw kompletną aplikację webową do zarządzania grafikami pracy pielęgniarek i opiekunek w szpitalu.



Aplikacja będzie używana przez szefową pielęgniarek / managera oddziału.



To ma być rzeczywiste MVP gotowe do uruchomienia na VPS za pomocą Dockera, a nie makieta ani proof-of-concept.



Najważniejsza jest poprawność logiki grafiku.



\---



\# 1. GŁÓWNY WORKFLOW APLIKACJI



Aplikacja ma działać według następującego procesu:



GENEROWANIE

↓

WALIDACJA

↓

RĘCZNA KOREKTA

↓

PONOWNA WALIDACJA

↓

PUBLIKACJA / ZATWIERDZENIE

↓

PDF



Dokładniej:



1\. Manager wybiera miesiąc.

2\. System pobiera:



&#x20;  \* aktywnych pracowników,

&#x20;  \* ich dostępność,

&#x20;  \* preferencje,

&#x20;  \* grafik z poprzedniego miesiąca,

&#x20;  \* grafik z kolejnego miesiąca, jeżeli istnieje,

&#x20;  \* święta,

&#x20;  \* konfigurację oddziału,

&#x20;  \* wszystkie ograniczenia.

3\. Manager klika "GENERUJ GRAFIK".

4\. OR-Tools generuje najlepszy możliwy grafik.

5\. System automatycznie wykonuje WALIDACJĘ.

6\. Jeżeli wszystkie HARD CONSTRAINTS są spełnione, grafik otrzymuje status:

&#x20;  GENERATED / VALID.

7\. Manager może ręcznie poprawiać grafik.

8\. Po każdej ręcznej zmianie system wykonuje ponowną walidację.

9\. Jeżeli zmiana powoduje HARD CONSTRAINT violation, operacja ma zostać zablokowana.

10\. Jeżeli powoduje tylko SOFT CONSTRAINT violation, pokaż ostrzeżenie.

11\. Po zakończeniu manager może zatwierdzić grafik.

12\. Zatwierdzony grafik otrzymuje status:

&#x20;   APPROVED.

13\. Możliwy jest eksport do PDF.



Nie pozwalaj traktować wygenerowanego grafiku jako automatycznie zatwierdzonego.



\---



\# 2. TECHNOLOGIA



\## Frontend



Użyj:



\* React

\* TypeScript

\* Vite

\* Bootstrap 5

\* FullCalendar

\* React Router

\* TanStack Query / React Query



Interfejs ma być minimalistyczny i profesjonalny.



Nie używaj ciężkiego UI frameworka.



Bootstrap 5 jest wystarczający.



\---



\# 3. BACKEND



Użyj:



\* Python 3.12+

\* FastAPI

\* SQLAlchemy 2.x

\* Pydantic v2

\* Alembic

\* PostgreSQL

\* OR-Tools CP-SAT

\* ReportLab



Backend musi być REST API.



\---



\# 4. BAZA DANYCH



Użyj WYŁĄCZNIE PostgreSQL jako głównej bazy danych.



Nie używaj SQLite nawet jako domyślnej bazy produkcyjnej.



Przygotuj:



\* SQLAlchemy models

\* Alembic migrations

\* indeksy

\* foreign keys

\* constraints

\* odpowiednie relacje



Docker Compose ma uruchamiać PostgreSQL.



Dane PostgreSQL muszą znajdować się na persistent volume.



\---



\# 5. LOGOWANIE — GOOGLE



Logowanie ma działać przez:



\## Google OAuth 2.0 / OpenID Connect



Nie implementuj klasycznego logowania:



\* email + hasło



Użytkownik loguje się przez:



"Zaloguj przez Google"



Po poprawnym uwierzytelnieniu Google aplikacja tworzy lub odnajduje użytkownika w PostgreSQL.



Przechowuj m.in.:



\* id

\* google\_subject\_id

\* email

\* name

\* avatar\_url

\* role

\* is\_active

\* created\_at

\* last\_login\_at



Nie przechowuj hasła użytkownika.



\## Bezpieczeństwo OAuth



Zaimplementuj prawidłowy OAuth Authorization Code Flow.



Nie implementuj OAuth własnoręcznie w sposób uproszczony.



Waliduj:



\* issuer

\* audience

\* state

\* nonce

\* redirect URI

\* authorization code



Nie ufaj danym przekazanym bezpośrednio z frontendu.



Sekrety Google:



GOOGLE\_CLIENT\_ID

GOOGLE\_CLIENT\_SECRET



mają być przechowywane wyłącznie w zmiennych środowiskowych / secretach.



Nigdy nie commituj ich do repozytorium.



\---



\# 6. SESJA UŻYTKOWNIKA



Po poprawnym OAuth utwórz bezpieczną sesję.



Preferowane rozwiązanie:



\* HTTP-only secure cookie

\* SameSite=Lax lub odpowiednio dobrane do architektury

\* Secure=true w produkcji



Nie przechowuj tokenów uwierzytelniających w localStorage, jeżeli nie jest to konieczne.



Dodaj:



\* logout

\* session expiration

\* bezpieczne odświeżanie sesji

\* ochronę endpointów backendu



\---



\# 7. ROLE



Na początek:



ADMIN

MANAGER



ADMIN:



\* zarządzanie użytkownikami,

\* zmiana ról,

\* konfiguracja systemu.



MANAGER:



\* pracownicy,

\* dostępność,

\* grafiki,

\* generowanie,

\* walidacja,

\* ręczna edycja,

\* PDF.



Zaimplementuj RBAC po stronie backendu.



Nigdy nie polegaj wyłącznie na ukrywaniu przycisku we frontendzie.



\---



\# 8. PRACOWNICY



Dodaj encję employees.



Pola:



\* id

\* first\_name

\* last\_name

\* role

\* employment\_date

\* active

\* created\_at

\* updated\_at



Role pracownika:



NURSE

CARE\_WORKER



\---



\# 9. KOLORY PRACOWNIKÓW



Kolor wyliczaj automatycznie na podstawie daty zatrudnienia.



\### Pielęgniarka:



> 3 lata:

> CZERWONY



> 1 rok i <= 3 lata:

> ŻÓŁTY



<= 1 rok:

ZIELONY



\### Opiekunka:



FIOLETOWY



Kolor powinien być widoczny:



\* obok nazwiska,

\* w grafiku,

\* w widoku pracowników,

\* w dostępności.



Nie pozwalaj ręcznie ustawiać koloru.



Kolor wynika z danych.



\---



\# 10. ZMIANY



Domyślnie:



\## D — DZIEŃ



07:00–19:00



12 godzin



\## R — RANEK



07:00–14:35



7 godzin 35 minut



\## N — NOC



19:00–07:00



12 godzin



\## W — WOLNE



0 godzin



Zmiany mają być przechowywane w bazie.



Nie hardcoduj godzin wyłącznie w kodzie.



Model Shift:



\* id

\* code

\* name

\* start\_time

\* end\_time

\* duration\_minutes

\* crosses\_midnight

\* minimum\_staff

\* active



Domyślnie:



D = 720 minut

R = 455 minut

N = 720 minut



Noc przechodzi przez północ.



\---



\# 11. WAŻNE — TIMESTAMPS



Każde przypisanie zmiany musi być możliwe do przeliczenia na:



start\_datetime

end\_datetime



Przykład:



2026-09-10 N:



start:

2026-09-10 19:00



end:

2026-09-11 07:00



Dzięki temu można prawidłowo liczyć:



\* odpoczynek,

\* następstwo zmian,

\* tygodniowy czas pracy,

\* przejście pomiędzy miesiącami.



\---



\# 12. HARD CONSTRAINTS



Hard constraints NIE MOGĄ być łamane.



Generator ma zwracać wyłącznie rozwiązania spełniające te wymagania.



\---



\## HARD CONSTRAINT 1 — MINIMUM 2 OSOBY



Domyślnie:



Dzień:

minimum 2



Ranek:

minimum 2



Noc:

minimum 2



Wartość ma być konfigurowalna.



Jeżeli jest:



minimum\_staff = 2



generator musi zapewnić minimum 2 osoby.



\---



\# 13. HARD CONSTRAINT 2 — 37 GODZIN 55 MINUT



Maksymalny czas pracy:



37 godzin 55 minut tygodniowo.



W bazie i solverze przechowuj czas w minutach.



37:55 = 2275 minut.



Nigdy nie używaj floatów do czasu pracy.



Generator nie może przekroczyć limitu.



Walidator również musi sprawdzać ten limit niezależnie od generatora.



\---



\# 14. TYGODNIE NA GRANICY MIESIĄCA



To bardzo ważne.



Nie traktuj każdego miesiąca jako niezależnego.



Przykład:



Miesiąc kończy się w środę.



Tydzień trwa:



poniedziałek → niedziela.



Pracownik może mieć już 30 godzin z poprzednich dni.



Generator musi to uwzględnić.



Jeżeli poprzedni miesiąc istnieje, pobierz dane z poprzedniego miesiąca.



Jeżeli następny miesiąc istnieje, również uwzględnij jego zmiany tam, gdzie jest to potrzebne do walidacji odpoczynku / tygodnia.



\---



\# 15. HARD CONSTRAINT 3 — MINIMUM 11 GODZIN ODPOCZYNKU



Pomiędzy końcem jednej zmiany i początkiem kolejnej:



minimum 11 godzin.



Przykład:



Koniec:

19:00



Następny start:

06:00



= 11 godzin



Dozwolone.



05:59:



= 10 h 59 min



Niedozwolone.



Walidacja ma działać na rzeczywistych timestampach.



\---



\# 16. HARD CONSTRAINT 4 — PO NOCCE



Jeżeli pracownik ma:



NOC:

19:00–07:00



to następna zmiana nie może być:



DZIEŃ:

07:00–19:00



ani:



RANEK:

07:00–14:35



Po nocce może być:



WOLNE



lub



NOC



Reguła ma być HARD CONSTRAINT.



\---



\# 17. HARD CONSTRAINT 5 — CO CZWARTA NIEDZIELA WOLNA



Każdy pracownik ma mieć co czwartą niedzielę wolną.



Nie resetuj licznika przy zmianie miesiąca.



Przechowuj / wyliczaj cykl w sposób pozwalający zachować ciągłość pomiędzy miesiącami.



Punkt startowy cyklu powinien być konfigurowalny.



System musi analizować również poprzednie niedziele.



\---



\# 18. HARD CONSTRAINT 6 — NIEDOSTĘPNOŚĆ



Pracownik może zaznaczyć dzień jako:



UNAVAILABLE



Jeżeli jest niedostępny:



nie może dostać żadnej zmiany.



Niedostępność jest HARD CONSTRAINT.



\---



\# 19. SOFT CONSTRAINTS



Jeżeli wszystkie HARD CONSTRAINTS są spełnione, OR-Tools powinien optymalizować grafik.



Priorytet:



1\. równy podział nocnych zmian,

2\. równy podział weekendów,

3\. równy podział świąt,

4\. równy podział całkowitej liczby godzin,

5\. preferencje pracowników,

6\. preferowane dni wolne.



Nie wystarczy znaleźć pierwszego poprawnego rozwiązania.



Generator ma szukać możliwie najlepszego.



\---



\# 20. RÓWNY PODZIAŁ NOCY



Policz dla każdego pracownika:



night\_count



Minimalizuj różnicę pomiędzy:



max(night\_count)



a



min(night\_count)



Jeżeli istnieje rozwiązanie:



Anna 5

Barbara 5

Celina 5

Dorota 6



jest ono preferowane nad:



Anna 10

Barbara 3

Celina 4

Dorota 4



\---



\# 21. RÓWNY PODZIAŁ WEEKENDÓW



Policz:



\* soboty,

\* niedziele,

\* weekendowe dyżury.



Minimalizuj nierówności.



\---



\# 22. RÓWNY PODZIAŁ ŚWIĄT



Policz pracę w święta.



Minimalizuj różnice pomiędzy pracownikami.



\---



\# 23. DOSTĘPNOŚĆ I PREFERENCJE



Dodaj tabelę availability.



Typ:



AVAILABLE

UNAVAILABLE

PREFERRED\_DAY

PREFERRED\_MORNING

PREFERRED\_NIGHT

PREFERRED\_OFF



UNAVAILABLE = HARD



Pozostałe preferencje = SOFT.



\---



\# 24. POLSKIE ŚWIĘTA



System musi automatycznie uwzględniać święta ustawowo wolne od pracy w Polsce.



Implementacja ma działać dla dowolnego roku.



Nie hardcoduj tylko roku 2026.



Dodaj tabelę holidays.



Pola:



\* id

\* date

\* name

\* country

\* is\_custom



System powinien generować / importować święta PL.



Święta muszą być widoczne w kalendarzu.



\---



\# 25. MODEL GRAFIKU



Utwórz:



Schedule:



\* id

\* year

\* month

\* status

\* version

\* generated\_at

\* approved\_at

\* created\_by

\* updated\_at



Statusy:



DRAFT

GENERATING

GENERATED

VALID

INVALID

APPROVED

ARCHIVED



Assignment:



\* id

\* schedule\_id

\* employee\_id

\* shift\_id

\* work\_date

\* start\_datetime

\* end\_datetime

\* manually\_modified

\* created\_at

\* updated\_at



\---



\# 26. WERSJONOWANIE GRAFIKU



Ponieważ grafik może być wielokrotnie generowany i ręcznie poprawiany, zachowuj historię.



Nie usuwaj bezpowrotnie poprzedniej wersji.



Dodaj wersjonowanie.



Przykład:



Grafik wrzesień:



v1 — wygenerowany

v2 — ręczna korekta

v3 — kolejna korekta



Manager może zobaczyć historię zmian.



\---



\# 27. AUDIT LOG



Każda istotna zmiana ma być logowana.



Loguj:



\* login,

\* logout,

\* dodanie pracownika,

\* edycję pracownika,

\* dezaktywację,

\* zmianę dostępności,

\* wygenerowanie grafiku,

\* ręczne przeniesienie zmiany,

\* zmianę zmiany,

\* zatwierdzenie grafiku,

\* eksport PDF.



Audit log:



\* user\_id

\* action

\* entity\_type

\* entity\_id

\* timestamp

\* metadata



\---



\# 28. GŁÓWNY WIDOK GRAFIKU



Zaprojektuj czytelną tabelę miesięczną.



Wiersze:



pracownicy.



Kolumny:



dni miesiąca.



Przykład:



Pielęgniarka | 1 | 2 | 3 | 4 | 5 | 6 | ...

Anna | D | D | W | N | N | W | ...

Barbara | N | W | D | D | W | N | ...

Celina | R | R | W | N | W | D | ...



Legenda:



D = 07:00–19:00

R = 07:00–14:35

N = 19:00–07:00

W = wolne



Weekend oraz święta powinny być wizualnie wyróżnione.



\---



\# 29. DRAG \& DROP



Manager może przeciągać zmianę pomiędzy dniami.



Po każdej operacji:



1\. wykonaj zmianę tymczasowo,

2\. uruchom walidację,

3\. jeżeli HARD CONSTRAINT zostanie złamany:



&#x20;  \* cofnij operację,

&#x20;  \* pokaż powód.

4\. jeżeli tylko SOFT CONSTRAINT zostanie pogorszony:



&#x20;  \* pozwól zapisać,

&#x20;  \* pokaż warning.



Przykład:



"Nie można wykonać operacji.



Pracownik miałby tylko 10 godzin 30 minut odpoczynku.

Wymagane minimum: 11 godzin."



\---



\# 30. RĘCZNA EDYCJA



Manager może:



\* zmienić zmianę,

\* usunąć zmianę,

\* dodać zmianę,

\* przenieść zmianę,

\* ustawić wolne.



Każda ręczna zmiana:



manually\_modified = true



Po zmianie uruchom ponowną walidację całego grafiku.



\---



\# 31. WALIDATOR



Stwórz niezależny moduł:



scheduler/validator.py



Generator nie może być jedynym miejscem sprawdzania reguł.



Validator ma niezależnie sprawdzać:



\* minimum obsady,

\* limit godzin,

\* odpoczynek,

\* następstwo po nocce,

\* niedziele,

\* dostępność,

\* święta,

\* inne konfiguracje.



Walidator zwraca strukturę podobną do:



{

"valid": true,

"errors": \[],

"warnings": \[],

"statistics": {}

}



\---



\# 32. PANEL WALIDACJI



Pokaż:



KONTROLA GRAFIKU



✓ Minimum 2 osoby

✓ Limit 37:55

✓ Minimum 11 h odpoczynku

✓ Reguła po nocce

✓ Co 4 niedziela wolna

✓ Dostępność

✓ Święta

✓ Równy podział nocy

✓ Równy podział weekendów



Status:



OK

WARNING

ERROR



Kliknięcie błędu pokazuje szczegóły.



\---



\# 33. BRAK ROZWIĄZANIA



Jeżeli OR-Tools nie znajdzie rozwiązania:



nie pokazuj tylko:



"Nie udało się wygenerować grafiku."



Pokaż:



"Nie znaleziono grafiku spełniającego wszystkie wymagania."



Następnie pokaż możliwe przyczyny.



Np.:



\* 03.09 noc wymaga 2 osób, dostępna jest tylko 1,

\* Anna jest niedostępna,

\* Barbara nie może otrzymać tej zmiany ze względu na poprzednią nockę,

\* pozostałe osoby przekroczyłyby limit godzin.



Dodaj sugestie.



\---



\# 34. STATYSTYKI



Dla każdego pracownika pokaż:



\* suma godzin,

\* liczba D,

\* liczba R,

\* liczba N,

\* liczba sobót,

\* liczba niedziel,

\* liczba weekendów,

\* liczba świąt,

\* liczba dni wolnych.



Przykład:



Anna Kowalska



Godziny:

34:45 / 37:55



D:

2



R:

1



N:

2



Weekend:

2



Święta:

1



\---



\# 35. PDF



Dodaj eksport:



"EKSPORT PDF"



PDF powinien zawierać:



\* nazwę placówki,

\* oddział,

\* miesiąc,

\* rok,

\* grafik,

\* legendę,

\* godziny zmian,

\* statystyki,

\* datę wygenerowania,

\* numer wersji grafiku.



Format:



A4 LANDSCAPE.



Dodaj:



PDF całego oddziału



oraz:



PDF pojedynczego pracownika.



\---



\# 36. DASHBOARD



Po zalogowaniu:



Dashboard.



Pokaż:



AKTUALNY GRAFIK



Wrzesień 2026



Status:

VALID



Pracownicy:

10



Zmiany:

...



Błędy:

0



Ostrzeżenia:

2



Przyciski:



\[OTWÓRZ GRAFIK]



\[GENERUJ GRAFIK]



\[PRACOWNICY]



\[DOSTĘPNOŚĆ]



\---



\# 37. PANEL PRACOWNIKÓW



Tabela:



Kolor | Imię | Nazwisko | Rola | Staż | Aktywny



Dodawanie:



Imię

Nazwisko

Rola

Data zatrudnienia

Aktywny



Staż oblicz automatycznie.



\---



\# 38. PANEL DOSTĘPNOŚCI



Manager wybiera:



pracownik

miesiąc



i widzi kalendarz.



Możliwość szybkiego zaznaczania wielu dni.



\---



\# 39. USTAWIENIA



Dodaj:



Nazwa placówki

Oddział



Minimalna obsada D

Minimalna obsada R

Minimalna obsada N



Limit tygodniowy

37:55



Minimalny odpoczynek:

11 godzin



Reguła:

co 4 niedziela



Godziny zmian.



\---



\# 40. API



Przygotuj REST API.



Auth:



GET /api/auth/google

GET /api/auth/google/callback

POST /api/auth/logout

GET /api/auth/me



Employees:



GET /api/employees

POST /api/employees

GET /api/employees/{id}

PUT /api/employees/{id}

DELETE /api/employees/{id}



Schedules:



GET /api/schedules/{year}/{month}

POST /api/schedules/generate

POST /api/schedules/{id}/validate

POST /api/schedules/{id}/approve

GET /api/schedules/{id}/history



Assignments:



POST /api/assignments

PUT /api/assignments/{id}

DELETE /api/assignments/{id}



Availability:



GET /api/availability

POST /api/availability

PUT /api/availability/{id}

DELETE /api/availability/{id}



Holidays:



GET /api/holidays/{year}



PDF:



GET /api/schedules/{id}/pdf

GET /api/schedules/{id}/employee/{employee\_id}/pdf



\---



\# 41. BEZPIECZEŃSTWO



Aplikacja będzie publicznie dostępna w Internecie na VPS.



Traktuj bezpieczeństwo jako wymaganie podstawowe.



Zaimplementuj:



\* HTTPS za Nginx,

\* secure cookies,

\* HTTP-only cookies,

\* SameSite,

\* OAuth state,

\* nonce,

\* CSRF protection odpowiednie do architektury,

\* rate limiting,

\* security headers,

\* CSP,

\* X-Content-Type-Options,

\* Referrer-Policy,

\* HSTS w produkcji,

\* CORS tylko dla własnej domeny,

\* walidację backendową,

\* ORM / parametryzowane zapytania,

\* ochronę przed SQL Injection,

\* ochronę przed XSS,

\* kontrolę uprawnień na backendzie,

\* audit log.



Nigdy nie przechowuj sekretów w kodzie.



\---



\# 42. DOCKER



Przygotuj:



docker-compose.yml



Kontenery:



nginx

frontend

backend

postgres



PostgreSQL:



persistent volume.



Backend:



healthcheck.



Postgres:



healthcheck.



Restart policy.



Nie uruchamiaj aplikacji jako root.



\---



\# 43. NGINX



Nginx ma:



\* obsługiwać HTTPS,

\* kierować frontend,

\* proxy do API,

\* dodawać security headers,

\* ograniczać niepotrzebne endpointy.



Przygotuj konfigurację produkcyjną.



Nie zakładaj, że Replit będzie środowiskiem produkcyjnym.



Aplikacja ma działać samodzielnie na VPS.



\---



\# 44. ENV



Przygotuj:



.env.example



Przykładowe zmienne:



DATABASE\_URL=

GOOGLE\_CLIENT\_ID=

GOOGLE\_CLIENT\_SECRET=

GOOGLE\_REDIRECT\_URI=

SESSION\_SECRET=

APP\_ENV=production

FRONTEND\_URL=



Nie umieszczaj rzeczywistych sekretów w repozytorium.



\---



\# 45. BACKUP POSTGRESQL



Przygotuj:



scripts/backup.sh



Backup ma wykonywać pg\_dump.



Dodaj instrukcję konfiguracji cron.



Przykład:



codzienny backup.



README powinien opisywać:



\* gdzie backup jest zapisywany,

\* jak go odtworzyć.



\---



\# 46. TESTY



Koniecznie przygotuj testy.



Minimum:



1\. limit 37:55,

2\. przekroczenie 37:55,

3\. dokładnie 11 godzin odpoczynku,

4\. mniej niż 11 godzin,

5\. noc → wolne,

6\. noc → noc,

7\. noc → ranek = ERROR,

8\. noc → dzień = ERROR,

9\. minimum 2 osoby,

10\. niedostępność,

11\. co 4 niedziela,

12\. przejście cyklu pomiędzy miesiącami,

13\. święta PL,

14\. równy podział nocy,

15\. równy podział weekendów,

16\. tygodnie na granicy miesiąca,

17\. generowanie PDF,

18\. autoryzacja,

19\. RBAC,

20\. OAuth state/nonce,

21\. brak dostępu do API bez sesji,

22\. brak dostępu MANAGER do endpointów ADMIN.



\---



\# 47. DEMO DATA



Dodaj seed danych.



10 pracowników:



7 pielęgniarek

3 opiekunki



różne daty zatrudnienia.



Przykładowe dostępności.



Przykładowy miesiąc.



Możliwość wygenerowania grafiku demonstracyjnego.



\---



\# 48. STRUKTURA PROJEKTU



Proponowana struktura:



nurse-scheduler/



frontend/

backend/

nginx/

scripts/

docs/

docker-compose.yml

.env.example

.gitignore

README.md



Backend:



backend/app/



main.py



api/

models/

schemas/

services/

security/

scheduler/

utils/

database/



Scheduler:



scheduler/

\*\*init\*\*.py

models.py

constraints.py

optimizer.py

solver.py

validator.py

statistics.py



Rozdziel:



\* dane,

\* constraints,

\* solver,

\* validator,

\* statystyki.



\---



\# 49. JAK DZIAŁA GENERATOR



Przy:



POST /api/schedules/generate



backend:



1\. pobiera pracowników,

2\. pobiera dostępność,

3\. pobiera konfigurację,

4\. pobiera poprzedni grafik,

5\. pobiera istniejące dane dotyczące kolejnego miesiąca,

6\. pobiera święta,

7\. tworzy model CP-SAT,

8\. dodaje HARD CONSTRAINTS,

9\. dodaje SOFT CONSTRAINTS,

10\. definiuje funkcję celu,

11\. uruchamia solver,

12\. pobiera rozwiązanie,

13\. zapisuje Assignment,

14\. uruchamia niezależny validator,

15\. zwraca grafik + wyniki walidacji + statystyki.



\---



\# 50. NIEZAWODNOŚĆ GENERATORA



Generator musi być deterministyczny lub mieć możliwość ustawienia seed.



Dodaj konfigurację:



solver\_time\_limit\_seconds



Domyślnie np.:



60 sekund.



Jeżeli solver nie znajdzie idealnego rozwiązania w czasie:



\* jeżeli ma poprawne rozwiązanie spełniające HARD CONSTRAINTS — zwróć najlepsze znalezione,

\* pokaż informację, że jest to najlepsze znalezione rozwiązanie,

\* jeżeli nie ma żadnego poprawnego rozwiązania — pokaż konflikt.



\---



\# 51. WAŻNE — NIE UKRYWAJ BŁĘDÓW



Nigdy nie obchodź constraintów po to, aby "jakoś wygenerować grafik".



Jeżeli nie da się spełnić wymagań:



pokaż problem.



Nie zmniejszaj automatycznie minimum obsady.



Nie zwiększaj automatycznie limitu 37:55.



Nie ignoruj niedostępności.



Nie łam reguły po nocce.



Nie łam 11 godzin odpoczynku.



\---



\# 52. MANUALNA KOREKTA



Proces:



GENERATED

↓

VALID

↓

MANUAL EDIT

↓

VALIDATE

↓

APPROVED



Jeżeli po ręcznej korekcie pojawi się:



ERROR



status:



INVALID



Nie pozwalaj zatwierdzić grafiku z HARD CONSTRAINT violation.



\---



\# 53. INTERFEJS



Minimalistyczny Bootstrap 5.



Sidebar:



Dashboard

Grafik

Pracownicy

Dostępność

Święta

Historia grafików

Ustawienia

Użytkownicy

Wyloguj



Główny ekran:



miesięczny grafik.



Na desktopie tabela ma być maksymalnie czytelna.



Na urządzeniach mobilnych zastosuj poziome przewijanie grafiku.



\---



\# 54. UX



Manager nie powinien potrzebować wiedzy technicznej.



Komunikaty muszą być zrozumiałe.



Zamiast:



"Constraint violation: C17"



pokaż:



"Nie można zaplanować zmiany.



Anna Kowalska kończy poprzednią zmianę o 19:00.

Nowa zmiana rozpoczyna się o 05:30.



Odpoczynek: 10 h 30 min.

Wymagane minimum: 11 h."



\---



\# 55. PIERWSZE URUCHOMIENIE



README ma zawierać kompletną instrukcję:



1\. instalacja Docker,

2\. clone repo,

3\. utworzenie .env,

4\. konfiguracja Google OAuth,

5\. docker compose build,

6\. docker compose up -d,

7\. migracje Alembic,

8\. seed,

9\. utworzenie / autoryzacja pierwszego ADMINA,

10\. konfiguracja domeny,

11\. HTTPS,

12\. backup,

13\. aktualizacja.



\---



\# 56. GOOGLE OAUTH — DODATKOWA KONFIGURACJA



README musi dokładnie wyjaśniać, gdzie w Google Cloud Console utworzyć OAuth Client.



Wyjaśnij:



\* utworzenie projektu,

\* konfigurację OAuth consent screen,

\* utworzenie OAuth Client,

\* Authorized JavaScript origins, jeżeli wymagane,

\* Authorized redirect URIs,

\* gdzie znaleźć Client ID,

\* gdzie znaleźć Client Secret.



Redirect URI ma być konfigurowalne przez:



GOOGLE\_REDIRECT\_URI



Nie hardcoduj domeny.



\---



\# 57. PRODUKCYJNE DOMYŚLNE USTAWIENIA



Production:



DEBUG=false



CORS:

tylko własna domena.



Cookie:

Secure=true



HSTS:

włączone za HTTPS.



Nie pokazuj stack trace użytkownikowi.



Błędy backendu loguj po stronie serwera.



Nie loguj:



\* tokenów,

\* sekretów,

\* cookies,

\* danych uwierzytelniających.



\---



\# 58. OBSŁUGA BŁĘDÓW



Frontend powinien poprawnie obsługiwać:



401

403

404

409

422

500



Przy 401:



przekierowanie do logowania Google.



Przy 403:



"Nie masz uprawnień do wykonania tej operacji."



Przy błędach grafiku:



pokazuj konkretną przyczynę.



\---



\# 59. MIGRACJE



Użyj Alembic.



Nie twórz tabel automatycznie przez:



Base.metadata.create\_all()



w produkcji.



Migracje mają być wersjonowane.



\---



\# 60. CODE QUALITY



Kod ma być:



\* modularny,

\* typowany,

\* testowalny,

\* czytelny,

\* łatwy do rozszerzenia.



Nie twórz monolitycznego pliku.



Nie duplikuj logiki.



Szczególnie:



Walidator i solver nie powinny zawierać dwóch różnych implementacji tych samych zasad.



Jeżeli jest reguła biznesowa, powinna mieć jedno źródło prawdy.



\---



\# 61. KOŃCOWE KRYTERIA AKCEPTACJI



Projekt uznaj za gotowy dopiero, gdy:



✓ można zalogować się przez Google



✓ użytkownik jest zapisany w PostgreSQL



✓ działa RBAC



✓ można dodać pracownika



✓ staż automatycznie określa kolor



✓ można wybrać miesiąc



✓ można ustawić dostępność



✓ święta PL są uwzględniane



✓ można wygenerować grafik



✓ generator używa OR-Tools



✓ generator respektuje HARD CONSTRAINTS



✓ generator optymalizuje SOFT CONSTRAINTS



✓ działa limit 37:55



✓ działa 11 godzin odpoczynku



✓ działa reguła po nocce



✓ działa co 4 niedziela



✓ działa minimum 2 osoby



✓ działa równy podział nocy



✓ działa równy podział weekendów



✓ działa drag \& drop



✓ ręczna zmiana powoduje ponowną walidację



✓ konflikt HARD blokuje zmianę



✓ konflikt SOFT pokazuje ostrzeżenie



✓ działa wersjonowanie grafiku



✓ działa audit log



✓ można zatwierdzić grafik



✓ nie można zatwierdzić INVALID grafiku



✓ można wygenerować PDF



✓ działa PostgreSQL



✓ działa Docker Compose



✓ działa Nginx



✓ działa HTTPS



✓ istnieją testy



✓ istnieje backup PostgreSQL



✓ istnieje README



✓ aplikację można uruchomić na czystym VPS



\---



\# 62. KOLEJNOŚĆ IMPLEMENTACJI



Realizuj projekt etapami.



ETAP 1:

Architektura + PostgreSQL + Docker + FastAPI



ETAP 2:

Google OAuth + sesje + RBAC



ETAP 3:

Pracownicy + zmiany + konfiguracja



ETAP 4:

Dostępność + święta



ETAP 5:

Model grafiku



ETAP 6:

OR-Tools generator



ETAP 7:

Niezależny validator



ETAP 8:

Frontend grafiku



ETAP 9:

Drag \& drop + ręczna edycja



ETAP 10:

Statystyki + historia



ETAP 11:

PDF



ETAP 12:

Security hardening



ETAP 13:

Testy



ETAP 14:

Docker production + Nginx + README



Po każdym etapie uruchamiaj testy i naprawiaj błędy.



Nie przechodź dalej, jeżeli podstawowa funkcjonalność poprzedniego etapu nie działa.



\---



\# 63. WAŻNA ZASADA DLA CLAUDE CODE



Nie twórz atrap.



Nie twórz funkcji typu:



generateSchedule() {

// TODO

}



Jeżeli implementujesz funkcję, ma działać.



Nie zastępuj OR-Tools losowym przydziałem.



Nie pomijaj walidacji.



Nie obchodź ograniczeń.



Jeżeli jakaś decyzja biznesowa jest niejednoznaczna, zaprojektuj ją jako konfigurację systemową zamiast hardcodować.



Jeżeli potrzebujesz wybrać pomiędzy kilkoma technologiami, wybierz rozwiązanie najprostsze, stabilne i dobrze nadające się do Docker + VPS.



\---



\# 64. OCZEKIWANY REZULTAT



Na końcu projektu chcę otrzymać działającą aplikację:



Google Login

↓

Dashboard

↓

Pracownicy

↓

Dostępność

↓

Wybór miesiąca

↓

GENERUJ GRAFIK

↓

OR-Tools

↓

WALIDACJA

↓

RĘCZNA KOREKTA / DRAG \& DROP

↓

PONOWNA WALIDACJA

↓

ZATWIERDZENIE

↓

PDF



Aplikacja ma być gotowa do uruchomienia na VPS za pomocą:



docker compose up -d



z PostgreSQL jako bazą danych.



Po zakończeniu implementacji uruchom wszystkie testy, wykonaj podstawowy test end-to-end i popraw wszystkie znalezione problemy.



Nie kończ pracy na samym wygenerowaniu kodu — sprawdź, że aplikacja faktycznie się uruchamia i działa.



