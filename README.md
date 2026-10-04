# Prylbanken

En svensk, självhostad samlingssida för länkar, kodsnuttar, Docker-kommandon,
spelservrar, SteamCMD, BAT-skript och bifogade filer. Responsiv layout, sökning,
taggar, favoriter, redigering och säkerhetskopiering ingår.

## Bibliotek och administration

- Kodvisning med lokal syntaxmarkering och radnummer. Kopiering och nedladdning
  använder originaltexten, inte radnumren.
- Språk och eget nedladdningsnamn samt operativsystem, programversion, portar,
  beroenden, testdatum och status för varje post.
- Versionshistorik: återställ tidigare innehåll, metadata och bilagor.
  En återställning skapar också en ny version.
- Papperskorg: återställ borttagna poster eller radera dem permanent.
  Permanent radering tar också bort postens historik.
- Kategorier med underkategorier, namnbyte och flytt av innehåll vid radering.
  Inbyggda kategorier kan byta namn och flyttas, men inte tas bort.
- Aktivitetslogg för gemensamma ändringar och administration.
- Kontohantering: skapa konton, inaktivera dem och sätt nya lösenord.
  Inaktivering och lösenordsåterställning avslutar kontots sessioner.
- Öppen registrering kan stängas och öppnas igen i administrationen.
- Mallvariabler, bokmärkesknapp, avancerade och sparade sökningar,
  projektsamlingar och import av flera filer med förhandsvisning.

Alla konton delar samma bibliotek, men har olika behörigheter. Befintliga konton
behåller administratörsrollen vid uppgradering. **Nya självregistrerade konton
blir läsare**; administratörer kan ändra deras roll. Även läsare kan se biblioteket
och ladda ned bilagor. Begränsa därför öppen registrering till betrodda användare.

### Snabbare användning

- **Mallvariabler:** skriv exempelvis
  `start --name "{{server_name}}" --ip {{ip}} --port {{port}}` i kodfältet.
  Öppna posten, fyll i variablerna under **Anpassa mall** och välj **Generera
  kommando**. Kopiera eller ladda ned resultatet. Namn använder a–z/A–Z,
  siffror och understreck, börjar med bokstav/understreck och är högst 40 tecken.
  Värden ersätts bokstavligt, utan shell-escaping eller rekursiv ersättning.
  Kontrollera själv citattecken och argument. Variabelvärden sparas inte i
  databasen, och Prylbanken kör aldrig kommandot.
  Redigeringsformuläret har färdiga variabelexempel för Docker, SteamCMD och BAT.
- **Spara från webbläsaren:** dra länken **Spara i Prylbanken** till
  bokmärkesfältet. Klicka på bokmärket på en annan webbsida för att öppna
  Prylbankens formulär med titel och länk. Inloggning och redigerarbehörighet
  krävs. Bekräfta genom att spara formuläret; ingen extern sida hämtas av servern.
  Vissa webbsidor/webbläsare blockerar bokmärkeskript; klistra då in länken manuellt.
- **Sökning:** alla sökord måste finnas i posten. Taggfiltret matchar hela taggar,
  och alla kommaseparerade taggar måste finnas. Kombinera med **Bara bilagor**,
  **Inkludera underkategorier**, projekt, OS, språk och status.
  **Spara sökning** sparar filter och sortering för ditt konto, inte en kopia
  av träffarna. Sökningarna finns kvar efter omstart och visas inte för andra konton.
- **Projektsamlingar:** skapa till exempel ”Hemmaserver” eller ”Valheim”.
  Välj projekt i postens redigeringsformulär. En post kan ingå i flera projekt
  oavsett kategori. Ett borttaget projekt raderar inte posterna.
- **Flera filer:** välj eller dra in upp till 50 filer, sammanlagt högst 20 MB.
  Välj kategori och automatisk avkänning, kodtext eller bilagor. Text läses som
  UTF-8 med högst 200 kB per fil; binära/större filer ska importeras som bilagor.
  Förhandsvisningen låter dig ändra titlar och välja bort filer.
  Dubbletter kontrolleras både före och vid import: en identisk kombination
  av kodtext och bilageinnehåll i aktivt bibliotek eller samma import. De hoppas över som
  standard, men kan tillåtas uttryckligen. Poster i papperskorgen räknas inte
  som dubbletter. Ogiltig post avbryter hela importen.

### Säkerhetskopiering och återställning

Automatiska fullständiga SQLite-säkerhetskopior tas dagligen i en **separat
Docker-volym**, med **14 sparade kopior**. Du kan också skapa, ladda ned och
återställa kopior från webbgränssnittet. Kopiorna innehåller bibliotek, bilagor,
historik, konton och inställningar. Förvara nedladdade kopior säkert.

14 dagliga kopior behålls. Manuella kopior och säkerhetskopior före återställning
har var sin separat gräns på 14 kopior. Dagens första kopia tas vid start;
servern kontrollerar sedan en gång i timmen om en ny dag har börjat (UTC).

En full återställning ersätter nuvarande databas, tar först en säkerhetskopia av
nuläget och loggar ut alla. Logga därefter in med ett konto och lösenord som fanns
i den återställda kopian. JSON-exporten är en biblioteksöverföring, inte en full
säkerhetskopia av konton och administration.

En separat volym på samma Docker-värd skyddar inte mot förlust av hela värden eller
disken. Ladda regelbundet ned en kopia till en annan dator eller ett separat
backupsystem. Använd inte `docker compose down -v` när data ska bevaras:
det tar bort volymerna.

### Automatisk backup till NAS

NAS-backup är **valfri och avstängd tills du konfigurerar ett mål**.
Montera först din NAS på Linux-värden med operativsystemets SMB/NFS-stöd.
Använd en separat, befintlig katalog för Prylbanken. Exempel:

```sh
mountpoint /mnt/nas &&
mkdir -p /mnt/nas/prylbanken &&
touch /mnt/nas/prylbanken/.prylbanken-backup-target &&
cp compose.nas.yaml compose.override.yaml
```

Om du redan har en `compose.override.yaml`, sammanfoga NAS-inställningarna med
den i stället för att skriva över filen.
Fortsätt bara om `mountpoint` bekräftar att NAS är monterad. Lägg till
`NAS_BACKUP_PATH=/mnt/nas/prylbanken` i din befintliga `.env` och ge containerns
`app`-användare läs- och skrivrättigheter till katalogen. Använd NAS-monterings-
inställningar/ACL eller lämpligt ägarskap, inte allmänna `777`-rättigheter.
Skapa inte markörfilen i en omonterad lokal reservkatalog.
**NAS-monteringen ska ske innan containern startas, även efter omstart av värden.**
Kör därefter `sh install.sh`. Compose läser den lokala, Git-ignorerade
`compose.override.yaml` automatiskt. Standardinstallationen ändras inte.

Nya lokala kopior skickas till NAS som temporära filer, kontrollsumman verifieras
med SHA-256 och filen publiceras sedan genom namnbyte. Även NAS behåller högst
14 kopior av vardera typen daglig/manuell/före återställning. Endast Prylbankens
namngivna backupfiler gallras; använd ändå en dedikerad katalog.
Misslyckanden visas under **Administration**, loggas i serverloggen och
försöks igen varje timme. Den lokala kopian behålls när NAS-kopieringen misslyckas;
en manuell begäran visar då fel, inte ett falskt framgångsmeddelande.
En saknad katalog eller markörfil behandlas som ett fel, inte som lyckad extern backup.

För lokal körning utan Docker kan `EXTERNAL_BACKUP_DIR` ange den monterade
NAS-katalogen direkt. Samma markörfil krävs. NAS-kopior innehåller också
konton, lösenordshashar, sessioner och sparade sökningar; skydda katalogen och
transporten. För återställning från NAS, kopiera den valda `.sqlite`-filen med
oförändrat namn till den lokala backupvolymen, ge `app` läsrättigheter och
använd **Full återställning** i gränssnittet.

### Uppdatera en befintlig installation

```sh
cd prylbanken
git pull --ff-only && sh install.sh
```

Databasen uppgraderas automatiskt vid start och befintliga poster, bilagor och
konton bevaras. Installeraren behåller din befintliga `.env`. Ta gärna en kopia
av datavolymen innan större uppgraderingar.

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
krypterat på disk. Biblioteket och projektsamlingarna delas av alla användare;
det finns inga privata innehållssamlingar. Sparade sökningar hör till respektive konto.

## Inloggning och användare

- Vid första starten skapas `admin` med lösenordet i `APP_PASSWORD`. Vid uppgradering
  från Basic-inloggningen används samma lösenord. Befintligt innehåll behålls.
- Logga in via den nya inloggningssidan. Webbläsarens gamla Basic-inloggning
  används inte längre.
- När registreringen är öppen kan alla som når inloggningssidan välja **Skapa konto** och registrera sig
  utan inloggning eller inbjudan. Varje konto får ett unikt användarnamn och eget
  lösenord. Stora och små bokstäver räknas som samma namn; upptagna namn nekas.
  Efter registreringen loggar användaren in med sitt nya lösenord.
- Administratörer kan under **Användare** skapa konton och välja eller ändra roll.
  Övriga användare har **Mitt konto** för eget lösenordsbyte.
- Användarnamn innehåller 3–40 tecken (a–z, siffror, punkt, bindestreck eller
  understreck) och sparas med små bokstäver. Lösenord kräver 12–256 tecken.
- **Läsare:** kan läsa gemensamt innehåll, historik och papperskorg, kopiera/ladda ned
  text och bilagor, exportera biblioteket, använda mallvariabler och spara egna sökningar.
- **Redigerare:** kan dessutom skapa/ändra poster, importera, ändra kategorier och
  projektsamlingar, flytta till papperskorgen och återställa poster/versioner.
- **Administratörer:** kan dessutom hantera konton/roller, registrering, aktivitetslogg,
  fulla SQLite-säkerhetskopior och permanent radering. Rollbyte återkallar sessioner.
  Det egna kontot kan inte inaktiveras eller ändra roll; ett aktivt adminkonto måste finnas.
- Öppen registrering ger nya konton **läsåtkomst till allt gemensamt innehåll**.
  Begränsa nätverksåtkomsten med ett betrott LAN eller VPN. HTTPS krypterar trafiken
  men begränsar inte vem som kan registrera sig.
- Under **Mitt konto/Användare → Byt ditt lösenord** kan användaren ändra sitt eget lösenord.
  Alla användarens sessioner återkallas och ny inloggning krävs.
- **Logga ut** återkallar den aktuella sessionen. Sessioner gäller i 12 timmar
  och sparas i databasen så att en containeromstart inte loggar ut alla.
- Lösenord sparas som individuellt saltade PBKDF2-SHA256-hashar (600 000 iterationer),
  inte i klartext. Sessionscookies är HttpOnly och SameSite=Strict. Skrivningar
  skyddas av en sessionstoken för CSRF. Inloggningsförsök begränsas till 10 per
  fem minuter och anslutande IP; bakom en reverseproxy kan gränsen delas av alla.
  Registreringen tillåter högst fem giltigt formaterade försök per fem minuter
  och anslutande IP, inklusive försök med redan upptagna namn.
- `APP_PASSWORD` används **bara för att skapa första kontot**. Att ändra `.env`
  återställer inte ett befintligt lösenord. Administratörer kan sätta ett nytt
  lösenord och inaktivera konton. Behåll tillgången till minst ett konto;
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
  säkerhet och dokumentation ingår. Använd **Hantera kategorier** för att skapa
  till exempel Proxmox eller Kubernetes och välja överordnad kategori.
  Egna kategorier visas i sidomenyn efter sparandet.
- **Läs in kod från en textfil** läser UTF-8-filer på högst 200 kB till kodfältet,
  så att innehållet kan sökas och redigeras. Indrag och radbrytningar bevaras.
- **Ladda ned text** sparar kodfältet som en fil. Ange ett nedladdningsnamn eller använd en titel med filändelse,
  till exempel `backup.py`, för önskat filnamn. Annars väljs `.bat`, `.sh` eller
  `.sql` för motsvarande kategori och `.txt` för övriga kategorier.
- Varje fil får vara högst **20 MB**. Filen lagras och laddas ned som en bilaga;
  den körs aldrig på servern. Även `.bat`, `.sh`, `.zip` och tomma filer fungerar.
- Klicka på en titel för hela innehållet, eller kopiera direkt från kortet.
- Filkategorin visar alla poster med bifogade filer.
- Stjärnan markerar favoriter. Standardordningen visar favoriter först, därefter
  senast uppdaterade poster. `/` fokuserar sökfältet.
- **Startbibliotek** låter dig välja bland nio paket med totalt **160 mallar**:
  spelservrar/SteamCMD, Docker, Linux/backup, Windows/PowerShell, nätverk/SSH och
  Git/Python/SQL samt containerstarter, serverprogram och skript/automation.
  Samma knapp finns i den tomma samlingen.
- Containerpaketet innehåller 12 Compose-mallar: Nginx, Apache, Caddy,
  PostgreSQL, MariaDB, Redis, RabbitMQ, Gitea, Vaultwarden, Uptime Kuma,
  Grafana och Prometheus. Publicerade portar binds till localhost; Redis
  har ingen publicerad hostport. Konfigurationsfiler och lösenord som
  anges i anteckningarna måste skapas innan körning. Mallarna är separata
  projekt, inte en gemensam produktionsstack.
- Serverprogram-paketet innehåller 16 startmallar för bland annat Node.js,
  .NET, Java, Python, Uvicorn, Gunicorn, IIS, databaser och webbservrar.
  Skriptpaketet innehåller 12 mallar för systemd, timers, cron, BAT,
  PowerShell, miljöfiler och backup. Programmen måste finnas installerade.
- Spelmallarna omfattar Valheim, Rust, Palworld, Satisfactory, CS2, Team Fortress 2,
  Minecraft Java och Bedrock, Factorio, Terraria samt 7 Days to Die.
  Plattformar och installationsmetoder varierar per spel.
- Spelpaketet innehåller nu **68 mallar för 21 spel och serververktyg**.
  Ytterligare spel är Project Zomboid, Unturned, Garry's Mod, Left 4 Dead 2,
  Sven Co-op, Don't Starve Together, V Rising, OpenTTD, Mindustry och Teeworlds.
  SteamCMD-installation ingår där den används. Windows-/Linux-start finns
  där respektive distribution stöds; ingen native Linux-start anges för V Rising.
- Dessutom ingår SteamCMD-mallar för Windows, plattformsval, licenskrävande
  interaktiv inloggning och appinformation; separat DST-grottserver, Factorio-
  världsskapande, Minecraft-whitelist, konsolkommandon för säker avstängning
  och checklistor för flera instanser och backup. Konsolkommandon ska köras
  i spelets serverkonsol, inte i operativsystemets terminal.
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

Data hamnar i `data/` om `DATA_DIR` inte sätts. Utanför Docker sparas
SQLite-säkerhetskopior i `DATA_DIR/backups/` som standard; välj en annan plats
med `BACKUP_DIR`. `BACKUPS_ENABLED=false` stänger av SQLite-säkerhetskopiering
vid lokal körning.

```powershell
python -m unittest discover -s tests -v
node --test tests/library-tools.test.js
```
