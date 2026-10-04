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
   i `APP_PASSWORD`. Använd inte kolon. För lösenord med `$`, omslut värdet med
   enkla citattecken i `.env`. Dela eller checka inte in `.env`.
3. Kör i den här mappen:

   ```sh
   docker compose up -d --build
   ```

4. Öppna <http://localhost:8080>. Logga in med användarnamnet **admin** och ditt
   lösenord. Webbläsaren visar en inloggningsruta.

Allt sparas i SQLite i den namngivna Docker-volymen `prylbanken-data`, inklusive
filer. Inga externa tjänster, typsnitt eller beroenden behövs. Innehållet är inte
krypterat på disk. Detta är ett privat bibliotek med ett gemensamt adminkonto,
inte en fleranvändartjänst med separata rättigheter.

## Nå sidan från andra enheter

Som säkert standardval exponeras porten bara på Docker-värdens localhost.
För andra enheter: använd en HTTPS-reverseproxy som kan nå port 8080.
Vid direkt LAN-test kan `BIND_ADDRESS=0.0.0.0` anges i `.env`. Öppna då
`http://SERVERNS-IP:8080`, men endast på ett betrott privat nätverk.
HTTP Basic-inloggning skickar inte lösenordet krypterat utan HTTPS.
Exponera därför **inte** HTTP-porten direkt mot internet. Kopiering till urklipp
kräver HTTPS eller localhost; annars visas ett fel och texten kan kopieras manuellt.
Reverseproxyn måste bevara ursprunglig `Host` för skrivningar och tillåta
begäranden på upp till 29 MB. Använd gärna VPN för privat åtkomst.

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
- Start­exemplen läggs till först när du själv klickar på knappen i en tom samling.
  Kommandona är mallar; anpassa dem före körning. Lösenordet `BYT_MIG` är en
  platshållare, inte ett riktigt serverlösenord.
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

Byt lösenord i `.env` och kör `docker compose up -d` för att återskapa containern.
Webbläsarens Basic-inloggning kan cachelagras; stäng webbläsaren efter användning
på delade datorer.

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
