# Prylbanken

En svensk, självhostad samlingssida för länkar, kodsnuttar, Docker-kommandon,
spelservrar, SteamCMD, BAT-skript och bifogade filer. Responsiv layout, sökning,
taggar, favoriter, redigering och säkerhetskopiering ingår.

## Starta med Docker

### Enkel installation på en Linux Docker-host

Docker Engine, Docker Compose v2 (med stöd för `--wait`) och Git måste finnas.
Kör detta på servern:

```sh
git clone https://github.com/richardstenlund/prylbanken.git && cd prylbanken && sh install.sh
```

Skriptet skapar ett slumpmässigt lösenord, öppnar port 8080 för LAN-åtkomst,
bygger containern och väntar på godkänd hälsokontroll. Därefter visas
användarnamnet `admin` och lösenordet i terminalen. Öppna
`http://SERVERNS-IP:8080` från en annan enhet på samma betrodda nätverk.
Visa serverns IP med `hostname -I`.

Lösenord och inställningar sparas i `.env` med begränsade filrättigheter.
**Dela inte terminalutskriften eller `.env`.** HTTP är inte krypterat och
LAN-installationen binder till alla nätverksgränssnitt; exponera inte porten
mot internet. Skriptet installerar inte Docker och ändrar inte brandväggen.

Om du redan har hämtat projektet: kör `git pull --ff-only` och `sh install.sh`
i projektmappen. En befintlig `.env`, lösenordet och biblioteket bevaras.
Skriptet använder `.env`, inte exporterade `APP_PASSWORD`, `BIND_ADDRESS` eller
`APP_PORT` från din terminal.

Om port 8080 är upptagen: ändra `APP_PORT=8081` i `.env`, kör `sh install.sh`
igen och öppna port 8081. Vid misslyckad installation visas ett fel, inte ett
framgångsmeddelande. Läs `docker compose logs --tail=50`. Det skapade lösenordet
finns kvar i `.env` även om bygget misslyckas.

### Manuell installation (endast localhost som standard)

1. Installera Docker med Docker Compose.
2. Kopiera `.env.example` till `.env`. Ange ett unikt lösenord på minst 12 tecken
   i `APP_PASSWORD` (max 256 tecken). För lösenord med `$`, omslut värdet med
   enkla citattecken i `.env`. Dela eller checka inte in `.env`.
3. Kör i den här mappen:

   ```sh
   docker compose up -d --build
   ```

4. Öppna <http://localhost:8080>. Logga in med användarnamnet **admin** och ditt
   lösenord på Prylbankens inloggningssida.

Allt sparas i SQLite i den namngivna Docker-volymen `prylbanken-data`, inklusive
filer. Inga externa tjänster, typsnitt eller beroenden behövs. Innehållet är inte
krypterat på disk. Biblioteket delas av alla användare; alla konton har
administratörsbehörighet. Det finns inga privata samlingar eller separata rättigheter.

## Inloggning och användare

- Vid första starten skapas `admin` med lösenordet i `APP_PASSWORD`. Vid uppgradering
  från Basic-inloggningen används samma lösenord. Befintligt innehåll behålls.
- Logga in via den nya inloggningssidan. Webbläsarens gamla Basic-inloggning
  används inte längre.
- Klicka på **Användare** för att se konton och skapa en ny administratör.
  Bara inloggade administratörer kan skapa konton. Självregistrering är inte tillåten.
- Användarnamn innehåller 3–40 tecken (a–z, siffror, punkt, bindestreck eller
  understreck) och sparas med små bokstäver. Lösenord kräver 12–256 tecken.
- Alla användare kan läsa, redigera och radera hela biblioteket, exportera filer
  och skapa fler administratörer. Skapa därför bara konton åt personer du litar på.
- Under **Användare → Byt ditt lösenord** kan användaren ändra sitt eget lösenord.
  Alla användarens sessioner återkallas och ny inloggning krävs.
- **Logga ut** återkallar den aktuella sessionen. Sessioner gäller i 12 timmar
  och sparas i databasen så att en containeromstart inte loggar ut alla.
- Lösenord sparas som individuellt saltade PBKDF2-SHA256-hashar (600 000 iterationer),
  inte i klartext. Sessionscookies är HttpOnly och SameSite=Strict. Skrivningar
  skyddas av en sessionstoken för CSRF. Inloggningsförsök begränsas till 10 per
  fem minuter och anslutande IP; bakom en reverseproxy kan gränsen delas av alla.
- `APP_PASSWORD` används **bara för att skapa första kontot**. Att ändra `.env`
  återställer inte ett befintligt lösenord. Behåll tillgången till minst ett konto;
  lösenordsåterställning via e-post och radering av konton ingår inte.
- JSON-exporten innehåller biblioteket, inte konton eller sessioner. En
  fullständig Docker-volymbackup innehåller även dessa.

## Nå sidan från andra enheter

Som säkert standardval exponeras porten bara på Docker-värdens localhost.
För andra enheter: använd en HTTPS-reverseproxy som kan nå port 8080.
Vid direkt LAN-test kan `BIND_ADDRESS=0.0.0.0` anges i `.env`. Öppna då
`http://SERVERNS-IP:8080`, men endast på ett betrott privat nätverk.
HTTP skickar lösenord och sessionscookies utan transportkryptering.
Exponera därför **inte** HTTP-porten direkt mot internet. Kopiering till urklipp
kräver HTTPS eller localhost; annars visas ett fel och texten kan kopieras manuellt.
Reverseproxyn måste bevara ursprunglig `Host` för skrivningar och tillåta
begäranden på upp till 29 MB. Vid HTTPS, ange `COOKIE_SECURE=true` i `.env`
och återskapa containern med `docker compose up -d`; då skickas cookies bara
över HTTPS. Behåll `false` för direkt HTTP-åtkomst på LAN. Servern litar inte
automatiskt på `X-Forwarded-Proto` eller `X-Forwarded-For`. Använd gärna VPN
för privat åtkomst.

## Användning

- **Lägg till nytt:** välj kategori, titel, innehåll, anteckningar och taggar
  separerade med kommatecken. Valfri fil kan bifogas i alla kategorier.
- IT-kategorier för Linux, Windows, nätverk, databaser, utveckling, automation,
  säkerhet och dokumentation ingår. Välj **Egen kategori** för till exempel
  Proxmox eller Kubernetes. Egna kategorier visas i sidomenyn efter sparandet.
- **Läs in kod från en textfil** läser UTF-8-filer på högst 200 kB till kodfältet,
  så att innehållet kan sökas och redigeras. Indrag och radbrytningar bevaras.
- **Ladda ned text** sparar kodfältet som en fil. Använd en titel med filändelse,
  till exempel `backup.py`, för önskat filnamn. Annars väljs `.bat`, `.sh` eller
  `.sql` för motsvarande kategori och `.txt` för övriga kategorier.
- Varje fil får vara högst **20 MB**. Filen lagras och laddas ned som en bilaga;
  den körs aldrig på servern. Även `.bat`, `.sh`, `.zip` och tomma filer fungerar.
- Klicka på en titel för hela innehållet, eller kopiera direkt från kortet.
- Filkategorin visar alla poster med bifogade filer.
- Stjärnan markerar favoriter. Standardordningen visar favoriter först, därefter
  senast uppdaterade poster. `/` fokuserar sökfältet.
- **Startbibliotek** låter dig välja bland sex paket med totalt 60 mallar:
  spelservrar/SteamCMD, Docker, Linux/backup, Windows/PowerShell, nätverk/SSH och
  Git/Python/SQL. Samma knapp finns i den tomma samlingen.
- Spelmallarna omfattar Valheim, Rust, Palworld, Satisfactory, CS2, Team Fortress 2,
  Minecraft Java och Bedrock, Factorio, Terraria samt 7 Days to Die.
  Plattformar och installationsmetoder varierar per spel.
- Du kan förhandsvisa kommandon och referenser innan paketen läggs till. Alla
  mallar är redigerbara. Inga kommandon körs av webbplatsen. Anpassa sökvägar,
  lösenord, RAM, spelversion och portar innan du använder dem.
- Upprepad tilläggning via Startbibliotek hoppar över redan importerade mallar
  och skriver inte över dina ändringar. En raderad mall kan läggas till igen.
  De fem äldre startexemplen och vanliga JSON-importer har inte samma
  importmarkering och kan därför överlappa med de nya mallarna.
- Länkar är bokmärken. Sidan laddar inte ned externa webbplatsers innehåll.
- Exportera skapar en JSON-fil med allt innehåll, inklusive filer. Den kan
  innehålla känslig kod eller hemligheter; förvara säkerhetskopian säkert.
- Importera lägger till poster och behåller befintliga poster. Upprepad import
  kan skapa dubbletter. Importen är atomisk: en ogiltig post avbryter hela importen.
  Max 5000 poster och 29 MB per import. Större samlingar återställs via volymbackup.

## Drift och säkerhetskopiering

```sh
docker compose logs -f --tail=100
docker compose down
docker compose up -d --build
```

`docker compose down` behåller volymen. **`docker compose down -v` raderar data.**
Säkerhetskopiera regelbundet med Exportera och, för större samlingar, en
volymbackup när containern är stoppad. Bevara hela datamappen inklusive eventuella
SQLite WAL/SHM-filer. `.env` behöver säkerhetskopieras separat.

Byt befintliga användarlösenord inne på sidan under **Användare**.
Logga alltid ut efter användning på delade datorer.

Uppdatera en befintlig installation utan att radera data:

```sh
git pull --ff-only && sh install.sh
```

## Lokal verifiering utan Docker

Python 3.13+ krävs. På PowerShell:

```powershell
$env:APP_PASSWORD = 'ett-unikt-lokalt-testlosenord'
python server.py
```

Data hamnar i `data/` om `DATA_DIR` inte sätts.

```powershell
python -m unittest discover -s tests -v
```
