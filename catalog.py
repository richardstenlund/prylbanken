"""Original command templates for optional library starter packs."""

PACKS = [
    {"id": "spel", "title": "Spelservrar & SteamCMD", "description": "SteamCMD, Windows- och Linux-starter för 21 spel samt serververktyg."},
    {"id": "docker", "title": "Docker & Compose", "description": "Status, loggar, felsökning och uppdatering."},
    {"id": "linux", "title": "Linux & backup", "description": "Disk, tjänster, processer och säkerhetskopior."},
    {"id": "windows", "title": "Windows & PowerShell", "description": "Tjänster, nätverk, loggar och filer."},
    {"id": "natverk", "title": "Nätverk & SSH", "description": "DNS, HTTP, portar och säkra anslutningar."},
    {"id": "utveckling", "title": "Git, Python & SQL", "description": "Vardagsverktyg för kod och databaser."},
    {"id": "containers", "title": "Färdiga containerstarter", "description": "Compose-mallar för webb, databaser och självhostade program."},
    {"id": "program", "title": "Serverprogram & tjänster", "description": "Starta och kontrollera webbservrar, databaser och utvecklingsappar."},
    {"id": "skript", "title": "Skript & automation", "description": "Systemd, BAT, PowerShell, backup och schemaläggning."},
]
EXAMPLES = []


def add(key, pack, title, category, content, notes, tags, source):
    EXAMPLES.append({"key": key, "pack": pack, "title": title, "category": category,
                     "content": content, "notes": notes + "\nReferens: " + source,
                     "tags": tags, "favorite": False})


def game(key, name, app_id, linux, windows, notes, source):
    tags = f"{key}, spelserver"
    if app_id:
        add(key + "-install", "spel", name + " – installera med SteamCMD", "steamcmd",
            f"steamcmd +force_install_dir ./games/{key} +login anonymous +app_update {app_id} validate +quit",
            "Kräver SteamCMD och internet. Kör från din valda basmapp; installationssökvägen är en mall. "
            "Relativa sökvägar tolkas av SteamCMD; använd gärna en absolut sökväg för din plattform. "
            "Stoppa servern och säkerhetskopiera sparfiler före uppdatering. validate kan ersätta ändrade originalfiler.",
            tags + ", installation", source)
    if linux:
        add(key + "-linux", "spel", name + " – starta på Linux", "spelserver", linux,
            "Kör i spelets installerade servermapp. " + notes, tags + ", linux", source)
    if windows:
        add(key + "-windows", "spel", name + " – start-server.bat", "bat",
            "@echo off\n" + windows + "\npause\n",
            "Spara som start-server.bat i spelets servermapp. " + notes, tags + ", windows, bat", source)


game("valheim", "Valheim", 896660, "./start_server.sh", "call start_headless_server.bat",
     "Anpassa den medföljande startfilen: servernamn, värld och ett unikt serverlösenord. "
     "Behåll miljövariablerna och biblioteksinställningarna från originalskriptet. Kontrollera portar i spelguiden.",
     "https://valheim.com/support/a-guide-to-dedicated-servers/")
game("rust", "Rust", 258550,
     './RustDedicated -batchmode +server.port 28015 +server.level "Procedural Map" +server.seed 1234 +server.worldsize 3000 +server.maxplayers 10 +server.hostname "Min Rust-server" +server.identity "server1"',
     'RustDedicated.exe -batchmode +server.port 28015 +server.level "Procedural Map" +server.seed 1234 +server.worldsize 3000 +server.maxplayers 10 +server.hostname "Min Rust-server" +server.identity "server1"',
     "Byt namn, identitet, seed och kartstorlek. RCON är inte aktiverat i denna mall; om du lägger till RCON, "
     "använd ett starkt lösenord och exponera inte administrationsporten.",
     "https://wiki.facepunch.com/rust/Creating-a-server")
game("palworld", "Palworld", 2394010, "./PalServer.sh", "PalServer.exe",
     "Ändra PalWorldSettings.ini enligt den officiella guiden. Ange serverlösenord, adminlösenord och rätt port. "
     "Kopiera först standardkonfigurationen enligt dokumentationen.",
     "https://docs.palworldgame.com/getting-started/deploy-dedicated-server/")
game("satisfactory", "Satisfactory", 1690800, "./FactoryServer.sh", "FactoryServer.exe",
     "Anslut via spelets Server Manager, gör anspråk på servern och sätt adminlösenord. "
     "Portkrav och konfiguration kan ändras mellan spelversioner.",
     "https://satisfactory.wiki.gg/wiki/Dedicated_servers")
game("cs2", "Counter-Strike 2", 730,
     "./game/bin/linuxsteamrt64/cs2 -dedicated -console +map de_dust2 +sv_lan 1",
     r"game\bin\win64\cs2.exe -dedicated -console +map de_dust2 +sv_lan 1",
     "Mall för LAN. Kör från installationsroten; byt karta vid behov. För publik server behövs rätt "
     "nätverksinställningar och eventuellt GSLT enligt Valve. Använd inte gamla CS:GO AppID 740 för CS2.",
     "https://developer.valvesoftware.com/wiki/Counter-Strike_2/Dedicated_Servers")
game("tf2", "Team Fortress 2", 232250,
     "./srcds_run -game tf -console +map ctf_2fort +maxplayers 24 +sv_lan 1",
     "srcds.exe -game tf -console +map ctf_2fort +maxplayers 24 +sv_lan 1",
     "LAN-mall. Byt karta och spelarantal. Publik drift kan kräva GSLT och server.cfg; kontrollera "
     "aktuella plattformskrav och medföljande binärnamn.",
     "https://developer.valvesoftware.com/wiki/Team_Fortress_2_Dedicated_Server")
game("minecraft-java", "Minecraft Java", None,
     "java -Xms2G -Xmx4G -jar server.jar nogui", "java -Xms2G -Xmx4G -jar server.jar nogui",
     "Ladda ned server-JAR från Minecrafts officiella webbplats och döp den till server.jar. "
     "Installera Java-versionen som spelet kräver. Läs och godkänn EULA. Anpassa RAM, "
     "server.properties och whitelist; behåll online-mode=true.",
     "https://www.minecraft.net/en-us/download/server")
game("minecraft-bedrock", "Minecraft Bedrock", None,
     "LD_LIBRARY_PATH=. ./bedrock_server", "bedrock_server.exe",
     "Ladda ned den officiella Bedrock-servern för din plattform. Anpassa server.properties "
     "och allowlist. Kontrollera stödd Linux-distribution och nätverksportar.",
     "https://www.minecraft.net/en-us/download/server/bedrock")
game("factorio", "Factorio", None,
     "./bin/x64/factorio --start-server ./saves/min-varld.zip --server-settings ./server-settings.json",
     r"bin\x64\factorio.exe --start-server saves\min-varld.zip --server-settings server-settings.json",
     "Ladda ned Factorios headless-server för Linux eller använd Windows-installationen. "
     "Skapa eller kopiera en sparfil först och kopiera server-settings.example.json "
     "till server-settings.json. Ändra sökvägar, lösenord och eventuell kontokonfiguration.",
     "https://wiki.factorio.com/Multiplayer")
game("terraria", "Terraria", None, "./TerrariaServer.bin.x86_64 -config serverconfig.txt",
     "TerrariaServer.exe -config serverconfig.txt",
     "Kräver den officiella serverdistributionen. Linux-binären ligger i versionsmappens Linux-katalog. "
     "Skapa serverconfig.txt med bland annat world, port, maxplayers och password enligt guiden.",
     "https://terraria.wiki.gg/wiki/Server")
game("7daystodie", "7 Days to Die", 294420, None, "call startdedicated.bat",
     "Använd det medföljande startskriptet och konfigurera serverconfig.xml. "
     "Kontrollera serverversion, värld, lösenord och portar. Säkerhetskopiera världen före versionsbyte.",
     "https://developer.valvesoftware.com/wiki/7_Days_to_Die_Dedicated_Server")

DOCKER = "https://docs.docker.com/reference/cli/docker/"
COMPOSE = "https://docs.docker.com/reference/cli/docker/compose/"
for key, title, content, notes in [
    ("status", "Docker – containrar och resurser", "docker ps -a\ndocker stats --no-stream\ndocker system df",
     "Visar containrar, resursförbrukning och diskutrymme. Raderar inget."),
    ("logs", "Docker Compose – följ loggar", "docker compose logs -f --tail=100",
     "Kör i projektmappen. Avsluta loggvisningen med Ctrl+C; containrarna fortsätter köra."),
    ("start", "Docker Compose – bygg och starta", "docker compose up -d --build\ndocker compose ps",
     "Kör i projektmappen. Återskapar ändrade tjänster; säkerhetskopiera beständig lagring först."),
    ("update", "Docker Compose – uppdatera image", "docker compose pull\ndocker compose up -d",
     "För tjänster som använder image. För lokalt byggda tjänster: uppdatera källkoden och bygg igen. "
     "Läs release notes och säkerhetskopiera före uppgradering."),
    ("restart", "Docker Compose – starta om en tjänst", "docker compose restart TJANST",
     "Byt TJANST till namnet i compose.yaml. Omstart läser inte in ändrad containermiljö; använd up -d för det."),
    ("shell", "Docker – öppna ett skal", "docker exec -it CONTAINER sh",
     "Byt CONTAINER. Kräver att imagen innehåller sh. Ändringar inne i containern kan försvinna när den återskapas."),
    ("ports", "Docker – kontrollera publicerade portar", "docker port CONTAINER\ndocker inspect --format '{{json .NetworkSettings.Ports}}' CONTAINER",
     "Byt CONTAINER. Visar vilken hostadress och port som är publicerad."),
    ("volumes", "Docker – lista volymer och nätverk", "docker volume ls\ndocker network ls",
     "Inventering utan radering. Använd inte volume prune eller down -v om data ska behållas."),
]:
    add("docker-" + key, "docker", title, "docker", content, notes, "docker, drift", COMPOSE if "compose" in content else DOCKER)

for key, title, content, notes, source in [
    ("disk", "Linux – disk och katalogstorlek", "df -h\ndu -sh ./data", "Byt ./data till din datamapp. Visar utrymme utan att ändra filer.", "https://www.gnu.org/software/coreutils/manual/coreutils.html"),
    ("memory", "Linux – minne och processer", "free -h\nps aux --sort=-%mem | head -n 15", "För Linux med procps. Listar processerna med högst minnesanvändning.", "https://gitlab.com/procps-ng/procps"),
    ("services", "Linux – kontrollera en systemd-tjänst", "systemctl status TJANST\njournalctl -u TJANST -n 100 --no-pager", "Byt TJANST, till exempel docker. Vissa loggar kräver sudo. Kräver systemd.", "https://www.freedesktop.org/software/systemd/man/latest/systemctl.html"),
    ("listen", "Linux – lyssnande portar", "ss -tuln", "Visar lyssnande TCP- och UDP-portar. Gör ingen ändring i brandväggen.", "https://man7.org/linux/man-pages/man8/ss.8.html"),
    ("archive", "Linux – säkerhetskopiera en mapp", 'tar -czf "backup-$(date +%Y%m%d-%H%M%S).tar.gz" ./data', "Kör från mappen ovanför data. Stoppa tjänsten först för konsistent databasbackup. Bevara och testa kopian.", "https://www.gnu.org/software/tar/manual/tar.html"),
    ("verify", "Linux – kontrollera en backup", "tar -tzf BACKUP.tar.gz\nsha256sum BACKUP.tar.gz", "Byt filnamn. Listar arkivet och beräknar kontrollsumma; återställningstest behövs också.", "https://www.gnu.org/software/tar/manual/tar.html"),
]:
    add("linux-" + key, "linux", title, "linux", content, notes, "linux, drift, backup", source)

for key, title, content, notes in [
    ("services", "PowerShell – tjänsternas status", "Get-Service | Sort-Object Status, DisplayName", "Visar tjänster. Gör ingen omstart."),
    ("network", "PowerShell – nätverksinformation", "Get-NetIPConfiguration\nGet-DnsClientServerAddress", "Visar nätverkskort, IP, gateway och DNS."),
    ("ports", "PowerShell – testa en TCP-port", "Test-NetConnection -ComputerName SERVERNS-IP -Port 8080", "Byt SERVERNS-IP och port. Testar endast TCP, inte UDP-spelportar."),
    ("logs", "PowerShell – senaste systemhändelserna", "Get-WinEvent -LogName System -MaxEvents 30 | Select-Object TimeCreated, Id, LevelDisplayName, Message", "Visar händelser från Windows systemlogg; vissa loggar kräver administratör."),
    ("hash", "PowerShell – SHA256 för en fil", "Get-FileHash -LiteralPath '.\\backup.zip' -Algorithm SHA256", "Byt sökväg. Jämför med en betrodd kontrollsumma."),
    ("archive", "PowerShell – ZIP-backup", "Compress-Archive -Path '.\\data' -DestinationPath '.\\backup.zip'", "Stoppa tjänsten först vid databasbackup. Välj ett nytt filnamn; PowerShell Compress-Archive har storleksbegränsningar och kan utelämna dolda filer."),
]:
    add("windows-" + key, "windows", title, "windows", content, notes, "windows, powershell", "https://learn.microsoft.com/powershell/")

for key, title, content, notes, source in [
    ("dns", "Nätverk – slå upp DNS", "nslookup example.com", "Byt domän. Finns på både Windows och många Linux-system.", "https://learn.microsoft.com/windows-server/administration/windows-commands/nslookup"),
    ("http", "HTTP – kontrollera svarshuvuden", "curl -I https://example.com", "Byt URL. Använd curl.exe i Windows PowerShell om curl är ett alias. Ignorera inte certifikatfel med -k.", "https://curl.se/docs/manpage.html"),
    ("ping", "Nätverk – ping från Linux", "ping -c 4 SERVERNS-IP", "Byt IP eller värdnamn. Uteblivet ICMP-svar betyder inte automatiskt att en tjänst är nere.", "https://man7.org/linux/man-pages/man8/ping.8.html"),
    ("ssh", "SSH – anslut till en server", "ssh ANVANDARE@SERVERNS-IP", "Byt användare och adress. Kontrollera värdens fingerprint före första anslutningen.", "https://man.openbsd.org/ssh"),
    ("tunnel", "SSH – privat tunnel till Prylbanken", "ssh -N -L 18080:127.0.0.1:8080 ANVANDARE@SERVERNS-IP", "Öppna http://localhost:18080 när tunneln är igång. Serverappen kan då vara bunden till localhost. Avsluta med Ctrl+C.", "https://man.openbsd.org/ssh"),
    ("copy", "SCP – hämta en serverbackup", "scp ANVANDARE@SERVERNS-IP:/sokvag/backup.tar.gz .", "Byt användare, adress och sökväg. Laddar ned filen till aktuell lokal mapp.", "https://man.openbsd.org/scp"),
]:
    add("network-" + key, "natverk", title, "natverk", content, notes, "natverk, felsokning", source)

for key, title, category, content, notes, source in [
    ("git-status", "Git – status och ändringar", "utveckling", "git status\ngit diff\ngit log --oneline -10", "Kör i repositoryt. Läser status utan att ändra filer.", "https://git-scm.com/docs"),
    ("git-update", "Git – hämta utan automatisk merge", "utveckling", "git pull --ff-only", "Avbryter om lokal och fjärrhistorik skiljer sig åt. Hantera lokala ändringar först.", "https://git-scm.com/docs/git-pull"),
    ("python-venv", "Python – virtuell miljö på Linux", "utveckling", "python3 -m venv .venv\n. .venv/bin/activate", "Kräver Python och venv. Installera paket från betrodda källor. Avsluta med deactivate.", "https://docs.python.org/3/library/venv.html"),
    ("python-win", "Python – virtuell miljö på Windows", "windows", "py -m venv .venv\n.\\.venv\\Scripts\\Activate.ps1", "Kör i PowerShell. Följ din organisations exekveringspolicy; stäng inte av skydd globalt.", "https://docs.python.org/3/library/venv.html"),
    ("sqlite-check", "SQLite – integritetskontroll", "databaser", 'sqlite3 ./library.sqlite "PRAGMA integrity_check;"', "Kräver sqlite3 CLI. Byt databasfil. Kör inte mot en godtycklig ny sökväg eftersom SQLite kan skapa en tom databas.", "https://www.sqlite.org/pragma.html#pragma_integrity_check"),
    ("sqlite-backup", "SQLite – konsistent online-backup", "databaser", "sqlite3 ./library.sqlite \".backup './library-backup.sqlite'\"", "Kräver sqlite3 CLI. Använd nytt backupfilnamn och rätt befintlig databas. För Prylbanken rekommenderas export eller stoppad volymbackup.", "https://www.sqlite.org/cli.html"),
]:
    add(key, "utveckling", title, category, content, notes, "utveckling, verktyg", source)


def container(key, name, image, ports, volumes, extra, notes, source):
    content = f"services:\n  {key}:\n    image: {image}\n    restart: unless-stopped\n"
    if ports:
        content += "    ports:\n" + "".join(f'      - "127.0.0.1:{port}"\n' for port in ports)
    if volumes:
        content += "    volumes:\n" + "".join(f"      - {mount}\n" for mount in volumes)
    if extra:
        content += extra
    named = [mount.split(":")[0] for mount in volumes if not mount.startswith((".", "/"))]
    if named:
        content += "\nvolumes:\n" + "".join(f"  {volume}:\n" for volume in named)
    add("compose-" + key, "containers", name + " – compose.yaml", "docker", content,
        "Spara som compose.yaml i en egen projektmapp. Kör docker compose up -d och docker compose logs --tail=50. "
        "Publicerade portar binds bara till localhost; använd SSH-tunnel eller HTTPS-reverseproxy för andra enheter. "
        "Skapa angivna lokala filer och fyll i .env före start. Säkerhetskopiera volymer före uppgradering. "
        "Image-taggar kan uppdateras; lås en testad version/digest för produktion. " + notes,
        f"docker, compose, {key}, start", source)


container("nginx", "Nginx – statisk webbplats", "nginx:stable-alpine", ["8082:80"],
          ["./html:/usr/share/nginx/html:ro"], "",
          "Skapa html/index.html. Ändra hostporten om 8082 används.", "https://hub.docker.com/_/nginx")
container("apache", "Apache HTTP Server", "httpd:2.4-alpine", ["8083:80"],
          ["./html:/usr/local/apache2/htdocs:ro"], "",
          "Skapa html/index.html. TLS och proxykonfiguration ingår inte.", "https://hub.docker.com/_/httpd")
container("caddy", "Caddy – lokal webbserver", "caddy:2-alpine", ["8084:80"],
          ["./Caddyfile:/etc/caddy/Caddyfile:ro", "./html:/srv:ro", "caddy-data:/data", "caddy-config:/config"], "",
          "Skapa Caddyfile med följande innehåll:\n:80 {\n    root * /srv\n    file_server\n}\n"
          "Skapa html/index.html. Detta är lokal HTTP, inte automatisk publik HTTPS.",
          "https://caddyserver.com/docs/running#docker-compose")
container("postgres", "PostgreSQL 17", "postgres:17-alpine", ["5432:5432"],
          ["postgres-data:/var/lib/postgresql/data"],
          "    environment:\n      POSTGRES_DB: app\n      POSTGRES_USER: app\n"
          "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Ange POSTGRES_PASSWORD i .env}\n",
          "Ange ett starkt POSTGRES_PASSWORD i .env. Volymsökvägen gäller PostgreSQL 17; byt inte huvudversion "
          "utan planerad databasmigration. Miljövariablerna initierar en ny databas, inte en befintlig.",
          "https://hub.docker.com/_/postgres")
container("mariadb", "MariaDB", "mariadb:11", ["3306:3306"], ["mariadb-data:/var/lib/mysql"],
          "    environment:\n      MARIADB_DATABASE: app\n      MARIADB_USER: app\n"
          "      MARIADB_PASSWORD: ${MARIADB_PASSWORD:?Ange MARIADB_PASSWORD i .env}\n"
          "      MARIADB_ROOT_PASSWORD: ${MARIADB_ROOT_PASSWORD:?Ange MARIADB_ROOT_PASSWORD i .env}\n",
          "Ange två separata starka lösenord i .env. Miljövariablerna används vid första initieringen.",
          "https://hub.docker.com/_/mariadb")
container("redis", "Redis – intern cache", "redis:7-alpine", [], ["redis-data:/data"],
          '    command: ["redis-server", "--appendonly", "yes"]\n',
          "Ingen hostport publiceras. Endast för betrodda tjänster i samma Compose-nätverk. "
          "Anslut till redis:6379 från en annan tjänst i projektet. Konfigurera ACL/TLS före annan åtkomst.",
          "https://hub.docker.com/_/redis")
container("rabbitmq", "RabbitMQ – meddelandekö", "rabbitmq:4-management", ["5672:5672", "15672:15672"],
          ["rabbitmq-data:/var/lib/rabbitmq"],
          "    hostname: rabbitmq\n    environment:\n      RABBITMQ_DEFAULT_USER: app\n"
          "      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD:?Ange RABBITMQ_PASSWORD i .env}\n",
          "Ange RABBITMQ_PASSWORD i .env. Webbadministration finns lokalt på port 15672. "
          "Behåll nodens hostname för befintliga data.", "https://hub.docker.com/_/rabbitmq")
container("gitea", "Gitea – Git-server", "gitea/gitea:1", ["3002:3000", "2222:22"], ["gitea-data:/data"],
          '    environment:\n      GITEA__service__DISABLE_REGISTRATION: "true"\n',
          "Slutför installationen och skapa första administratören i webben innan åtkomst ges till andra. "
          "SQLite passar för ett litet bibliotek. Ställ in extern ROOT_URL och SSH-port enligt dokumentationen.",
          "https://docs.gitea.com/installation/install-with-docker")
container("vaultwarden", "Vaultwarden – lösenordsvalv", "vaultwarden/server:latest", ["8085:80"],
          ["vaultwarden-data:/data"], '    environment:\n      SIGNUPS_ALLOWED: "false"\n',
          "Registrering är avstängd. Konfigurera säker konto-/inbjudningshantering enligt guiden innan användning. "
          "HTTPS krävs för webbvalvet utanför localhost. Säkerhetskopian innehåller känsliga data.",
          "https://github.com/dani-garcia/vaultwarden/wiki")
container("uptime-kuma", "Uptime Kuma – tillgänglighetskontroll", "louislam/uptime-kuma:2", ["3003:3001"],
          ["uptime-data:/app/data"], "",
          "Skapa första administratören i webbgränssnittet. För befintliga v1-data, läs migrationsguiden först.",
          "https://github.com/louislam/uptime-kuma")
container("grafana", "Grafana – dashboards", "grafana/grafana:latest", ["3004:3000"],
          ["grafana-data:/var/lib/grafana"],
          "    environment:\n      GF_SECURITY_ADMIN_USER: admin\n"
          "      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:?Ange GRAFANA_PASSWORD i .env}\n"
          '      GF_USERS_ALLOW_SIGN_UP: "false"\n',
          "Ange GRAFANA_PASSWORD i .env. Lägg till datakällor i webbgränssnittet. "
          "Adminlösenordet initierar bara nya data.", "https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/")
container("prometheus", "Prometheus – mätvärden", "prom/prometheus:latest", ["9090:9090"],
          ["./prometheus.yml:/etc/prometheus/prometheus.yml:ro", "prometheus-data:/prometheus"], "",
          "Skapa prometheus.yml med följande innehåll för att övervaka Prometheus självt:\n"
          "global:\n  scrape_interval: 15s\nscrape_configs:\n  - job_name: prometheus\n"
          "    static_configs:\n      - targets: ['localhost:9090']\n"
          "Mallen är inte startklar utan konfigurationsfil. Ingen autentisering ingår; behåll privat åtkomst.",
          "https://prometheus.io/docs/prometheus/latest/installation/")

for key, title, category, content, notes, source in [
    ("nginx-start", "Nginx – testa och starta tjänsten", "linux",
     "sudo nginx -t\n# Fortsätt bara om testet godkändes:\nsudo systemctl start nginx\nsystemctl status nginx --no-pager",
     "Kräver installerad Nginx och systemd. Granska vilken adress/port din webbplats binds till.",
     "https://nginx.org/en/docs/beginners_guide.html"),
    ("nginx-reload", "Nginx – ladda om konfiguration", "linux",
     "sudo nginx -t && sudo systemctl reload nginx", "Laddar bara om vid godkänt konfigurationstest. Befintliga anslutningar avslutas normalt inte.",
     "https://nginx.org/en/docs/beginners_guide.html"),
    ("caddy-start", "Caddy – kör en Caddyfile", "linux",
     "caddy validate --config ./Caddyfile && caddy run --config ./Caddyfile",
     "Kräver installerad Caddy och egen Caddyfile. Kör i förgrunden. Publik automatisk HTTPS kräver DNS och nåbara portar.",
     "https://caddyserver.com/docs/command-line"),
    ("apache-start", "Apache på Debian/Ubuntu – starta", "linux",
     "sudo apache2ctl configtest\n# Fortsätt bara efter Syntax OK:\nsudo systemctl start apache2",
     "För Debian/Ubuntu med Apache installerat. Andra distributioner använder ofta tjänsten httpd.",
     "https://httpd.apache.org/docs/2.4/invoking.html"),
    ("python-http", "Python – lokal HTTP-filserver", "utveckling",
     "python3 -m http.server 8000 --bind 127.0.0.1 --directory ./public",
     "Utvecklingstest, inte produktionsserver. Alla filer i public kan hämtas; servera aldrig hemkatalog eller hemligheter.",
     "https://docs.python.org/3/library/http.server.html"),
    ("node-start", "Node.js – starta en serverfil", "utveckling",
     "node server.js", "Kräver Node.js och din egen server.js. Bindningsadress och port bestäms av programmet. Kör i projektmappen.",
     "https://nodejs.org/api/cli.html"),
    ("npm-start", "Node.js – starta via npm", "utveckling",
     "npm ci && npm start", "Kräver package-lock.json och ett start-script. Kör bara i ett betrott projekt; paketens installationsskript kan köra kod.",
     "https://docs.npmjs.com/cli/commands/npm-start"),
    ("dotnet-start", ".NET – kör publicerad webbapp lokalt", "utveckling",
     'dotnet MyApp.dll --urls "http://127.0.0.1:5000"', "Byt MyApp.dll. Kräver kompatibel .NET-runtime och publicerad ASP.NET Core-app.",
     "https://learn.microsoft.com/aspnet/core/fundamentals/servers/kestrel/endpoints"),
    ("java-start", "Java – kör en JAR-server", "utveckling",
     "java -Xms512m -Xmx2g -jar app.jar", "Byt app.jar och RAM. Kräver appens Java-version. Nätverksinställningar är appspecifika.",
     "https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html"),
    ("uvicorn-start", "Uvicorn – lokal ASGI-server", "utveckling",
     "python -m uvicorn main:app --host 127.0.0.1 --port 8000", "Kräver installerad Uvicorn och ASGI-objektet app i main.py. Ingen automatisk installation ingår.",
     "https://www.uvicorn.org/settings/"),
    ("gunicorn-start", "Gunicorn – WSGI på Linux", "linux",
     "gunicorn --workers 2 --bind 127.0.0.1:8000 app:app", "Kräver Gunicorn och WSGI-app. Använd reverseproxy och tjänstehantering för drift.",
     "https://docs.gunicorn.org/en/stable/run.html"),
    ("redis-start", "Redis – lokal tillfällig server", "linux",
     "redis-server --bind 127.0.0.1 --protected-mode yes --port 6379",
     "Kräver Redis installerat. Kör inte parallellt med en befintlig instans på samma port. Konfigurera separat datakatalog före beständig drift.",
     "https://redis.io/docs/latest/operate/oss_and_stack/management/config/"),
    ("postgres-start", "PostgreSQL på Debian/Ubuntu – starta", "linux",
     "sudo systemctl start postgresql\npg_isready -h 127.0.0.1 -p 5432",
     "Kräver installerad och initierad PostgreSQL-kluster. Distributionens tjänstenamn kan skilja sig. pg_isready kontrollerar anslutningsstatus.",
     "https://www.postgresql.org/docs/17/app-pg-isready.html"),
    ("mariadb-start", "MariaDB – starta systemd-tjänst", "linux",
     "sudo systemctl start mariadb\nsystemctl status mariadb --no-pager", "Kräver installerad MariaDB. Konfigurera konton och bindningsadress separat.",
     "https://mariadb.com/kb/en/systemd/"),
    ("tmux-start", "tmux – server i separat terminalsession", "linux",
     "tmux new-session -s spelserver\n# Kör ditt serverkommando i sessionen.\n# Koppla loss: Ctrl+B, sedan D.\n# Återanslut:\ntmux attach-session -t spelserver",
     "Kräver tmux. Terminalsessioner överlever SSH-frånkoppling men inte hostomstart. Använd systemd för automatisk drift.",
     "https://github.com/tmux/tmux/wiki"),
    ("iis-start", "Windows IIS – starta webbplats", "windows",
     "Import-Module WebAdministration\nStart-Website -Name 'MinWebbplats'\nGet-Website",
     "Kräver IIS, WebAdministration, befintlig webbplats och administratörs-PowerShell. Ändra webbplatsnamnet och kontrollera bindings.",
     "https://learn.microsoft.com/powershell/module/webadministration/start-website"),
]:
    add("program-" + key, "program", title, category, content, notes, "serverprogram, start, drift", source)

for key, title, category, content, notes, source in [
    ("systemd-unit", "Systemd – mall för en spelservertjänst", "automation",
     "[Unit]\nDescription=Min spelserver\nAfter=network.target\n\n[Service]\nType=simple\nUser=spelserver\n"
     "WorkingDirectory=/srv/spelserver\nExecStart=/srv/spelserver/start-server.sh\nRestart=on-failure\n"
     "RestartSec=10\nTimeoutStopSec=120\nNoNewPrivileges=true\n\n[Install]\nWantedBy=multi-user.target\n",
     "Spara som /etc/systemd/system/spelserver.service. Skapa en separat användare och rätt katalogbehörigheter först. "
     "Startskriptet ska vara körbart, köra i förgrunden och använda exec för serverprocessen. Anpassa stopptiden till spelets sparning.",
     "https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html"),
    ("systemd-enable", "Systemd – aktivera en egen tjänst", "automation",
     "sudo systemctl daemon-reload\nsudo systemctl enable --now spelserver.service\nsystemctl status spelserver.service --no-pager",
     "Först efter att du granskat och installerat en korrekt service-fil. --now startar tjänsten direkt och enable aktiverar vid hoststart.",
     "https://www.freedesktop.org/software/systemd/man/latest/systemctl.html"),
    ("shell-start", "Bash – startskript för Java-server", "automation",
     '#!/bin/sh\nset -eu\ncd /srv/min-server\nexec java -Xms2G -Xmx4G -jar server.jar nogui\n',
     "Anpassa mapp, JAR, Java-version och RAM. Spara med LF-radbrytningar. Kör sh start-server.sh eller ge bara denna fil körbehörighet.",
     "https://www.gnu.org/software/bash/manual/bash.html"),
    ("bat-java", "BAT – starta Java från skriptmappen", "bat",
     '@echo off\ncd /d "%~dp0"\njava -Xms2G -Xmx4G -jar server.jar nogui\npause\n',
     "Spara som start-server.bat bredvid server.jar. Byt RAM och Java-version efter serverkrav.",
     "https://learn.microsoft.com/windows-server/administration/windows-commands/call"),
    ("bat-compose", "BAT – starta ett Compose-projekt", "bat",
     '@echo off\ncd /d "%~dp0"\ndocker compose up -d\nif errorlevel 1 exit /b 1\ndocker compose ps\npause\n',
     "Spara i mappen med compose.yaml. Docker Desktop/Engine måste vara startat. Befintligt projektnamn och volymer behålls.",
     COMPOSE),
    ("ps-start", "PowerShell – startskript med kontroll", "automation",
     '$ErrorActionPreference = "Stop"\nSet-Location $PSScriptRoot\n& java -Xms2G -Xmx4G -jar server.jar nogui\n'
     'if ($LASTEXITCODE -ne 0) { throw "Servern avslutades med kod $LASTEXITCODE" }\n',
     "Spara som start-server.ps1 bredvid JAR-filen. Följ lokal exekveringspolicy. Ändra inte säkerhetspolicy globalt för detta skript.",
     "https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_scripts"),
    ("cron-backup", "Cron – schemalägg ett backupskript", "automation",
     "# Lägg till via crontab -e:\n0 3 * * * /bin/sh /srv/scripts/backup.sh >> /srv/scripts/backup.log 2>&1\n",
     "Kör 03:00 enligt serverns tidszon. Skapa och testa backup.sh först. Cron har begränsad PATH; använd absoluta sökvägar. "
     "Se till att loggfilen går att skriva och övervaka fel.",
     "https://man7.org/linux/man-pages/man5/crontab.5.html"),
    ("timer", "Systemd – daglig timer", "automation",
     "[Unit]\nDescription=Daglig backup\n\n[Timer]\nOnCalendar=*-*-* 03:00:00\nPersistent=true\n"
     "Unit=backup.service\n\n[Install]\nWantedBy=timers.target\n",
     "Spara som backup.timer. Kräver en separat backup.service som utför en testad backup. Persistent kör en missad tid när timern återaktiveras.",
     "https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html"),
    ("backup-service", "Systemd – backupservice av typen oneshot", "automation",
     "[Unit]\nDescription=Backup av serverdata\n\n[Service]\nType=oneshot\nUser=backup\n"
     "ExecStart=/bin/sh /srv/scripts/backup.sh\nNoNewPrivileges=true\n",
     "Spara som backup.service för timer-mallen. Skapa backup-användaren och ge bara nödvändiga rättigheter. "
     "Backupskriptet måste ge felkod vid fel och hantera konsistenta databasbackuper.",
     "https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html"),
    ("rsync", "rsync – förhandsgranska en filbackup", "linux",
     "rsync -av --dry-run /srv/data/ /mnt/backup/data/\n# Efter kontroll, utför kopian:\nrsync -av /srv/data/ /mnt/backup/data/",
     "Kräver rsync och monterad backupdisk. Avslutande / kopierar mappens innehåll. Inget --delete används. "
     "Stoppa databaser eller använd deras backupverktyg före filkopiering.",
     "https://download.samba.org/pub/rsync/rsync.1"),
    ("ps-scheduled", "PowerShell – schemalägg ett befintligt skript", "automation",
     "$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -File C:\\Scripts\\backup.ps1'\n"
     "$trigger = New-ScheduledTaskTrigger -Daily -At '03:00'\n"
     "Register-ScheduledTask -TaskName 'MinBackup' -Action $action -Trigger $trigger -Description 'Daglig backup'\n",
     "Kräver befintligt och testat skript; använd citerad filväg i Argument om den innehåller blanksteg. "
     "Standarduppgiften körs under aktuell användares interaktiva konto. Obevakad drift kräver en planerad kontokonfiguration.",
     "https://learn.microsoft.com/powershell/module/scheduledtasks/register-scheduledtask"),
    ("env-file", "Miljöfil – mall för containerlösenord", "dokumentation",
     "# .env - fyll i egna unika slumpmassiga losenord.\n"
     "POSTGRES_PASSWORD=\nMARIADB_PASSWORD=\nMARIADB_ROOT_PASSWORD=\n"
     "RABBITMQ_PASSWORD=\nGRAFANA_PASSWORD=\n",
     "Fyll bara i de variabler som din Compose-mall kräver. Tomma lösenord nekas av mallarna. "
     "Lägg .env i .gitignore, begränsa rättigheter med chmod 600 .env på Linux och dela aldrig innehållet. "
     "Använd enkla citattecken runt värden med $ för att undvika Compose-interpolering.",
     "https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/"),
]:
    add("script-" + key, "skript", title, category, content, notes, "skript, automation, backup", source)

for key, pack, title, category, content, notes, source in [
    ("compose-check", "docker", "Compose – validera utan att visa hemligheter", "docker", "docker compose config --quiet",
     "Validerar YAML och miljövariabler utan att skriva ut den utvärderade konfigurationen.", COMPOSE),
    ("compose-service", "docker", "Compose – lista tjänsternas namn", "docker", "docker compose config --services", "Visar tjänstenamn som kan användas i logs, restart och exec.", COMPOSE),
    ("compose-health", "docker", "Compose – invänta friska containrar", "docker", "docker compose up -d --wait --wait-timeout 120", "Kräver Compose v2 med --wait. Tjänster utan healthcheck behöver bara vara running; skriv riktiga healthchecks för viktig funktionalitet.", COMPOSE),
    ("compose-stop", "docker", "Compose – stoppa utan att radera", "docker", "docker compose stop\ndocker compose ps -a", "Stoppar tjänster men behåller containrar och volymer. Starta igen med docker compose start.", COMPOSE),
    ("compose-top", "docker", "Compose – visa processer", "docker", "docker compose top", "Visar processer i projektets containrar. Ändrar inget.", COMPOSE),
    ("docker-health", "docker", "Docker – granska en hälsokontroll", "docker", "docker inspect --format '{{json .State.Health}}' CONTAINER", "Byt CONTAINER. Visar null om containern inte har healthcheck.", DOCKER),
    ("docker-copy", "docker", "Docker – hämta en loggfil", "docker", "docker cp CONTAINER:/app/logs/server.log ./server.log", "Byt container och befintlig filsökväg. Skriv till en ny lokal fil för att inte ersätta en tidigare kopia.", DOCKER),
    ("linux-uptime", "linux", "Linux – hostens uptime", "linux", "uptime\nuname -a", "Visar körtid, load och kärnversion. Dela inte systeminformation okritiskt.", "https://www.gnu.org/software/coreutils/manual/coreutils.html"),
    ("linux-find", "linux", "Linux – hitta konfigurationsfiler", "linux", "find /srv -type f -name '*.conf' -print", "Läser sökvägar utan att ändra filer. Byt basmapp; rättigheter kan begränsa resultatet.", "https://www.gnu.org/software/findutils/manual/html_mono/find.html"),
    ("linux-tail", "linux", "Linux – följ en loggfil", "linux", "tail -n 100 -F /srv/app/server.log", "Byt loggsökväg. -F följer även när loggen roteras. Avsluta med Ctrl+C.", "https://www.gnu.org/software/coreutils/manual/coreutils.html"),
    ("linux-time", "linux", "Linux – kontrollera tid och tidszon", "linux", "timedatectl status", "Kräver systemd. Fel tid kan störa TLS, sessioner och schemalagda jobb.", "https://www.freedesktop.org/software/systemd/man/latest/timedatectl.html"),
    ("linux-list-timers", "linux", "Linux – visa aktiva timers", "automation", "systemctl list-timers --all --no-pager", "Visar kommande och senaste systemd-timerkörningar. Ändrar inget.", "https://www.freedesktop.org/software/systemd/man/latest/systemctl.html"),
    ("windows-process", "windows", "PowerShell – processernas minne", "windows", "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name, Id, WorkingSet64", "Visar de 15 processer som använder mest working-set-minne. Stoppar inga processer.", "https://learn.microsoft.com/powershell/module/microsoft.powershell.management/get-process"),
    ("windows-disks", "windows", "PowerShell – ledigt diskutrymme", "windows", "Get-Volume | Select-Object DriveLetter, FileSystemLabel, SizeRemaining, Size", "Visar volymer och utrymme i byte. Ändrar ingen disk.", "https://learn.microsoft.com/powershell/module/storage/get-volume"),
    ("windows-listening", "windows", "PowerShell – lyssnande TCP-portar", "windows", "Get-NetTCPConnection -State Listen | Select-Object LocalAddress, LocalPort, OwningProcess", "Visar TCP-portar och process-ID. UDP visas separat med Get-NetUDPEndpoint.", "https://learn.microsoft.com/powershell/module/nettcpip/get-nettcpconnection"),
    ("network-route", "natverk", "Linux – IP och routing", "natverk", "ip address show\nip route show", "Visar nätverkskonfiguration utan att ändra den.", "https://man7.org/linux/man-pages/man8/ip.8.html"),
    ("git-branch", "utveckling", "Git – skapa arbetsbranch", "utveckling", "git switch -c min-andring", "Byt branchnamn. Kräver Git 2.23+. Kommitta relevanta ändringar innan du byter arbetskontext.", "https://git-scm.com/docs/git-switch"),
    ("git-remotes", "utveckling", "Git – kontrollera remotes", "utveckling", "git remote -v\ngit branch -vv", "Visar fjärr-URL och tracking. URL kan innehålla känsliga uppgifter om felaktigt konfigurerad.", "https://git-scm.com/docs/git-remote"),
    ("python-tests", "utveckling", "Python – kör unittest", "utveckling", "python -m unittest discover -s tests -v", "Kör projektets testkod. Använd bara betrodda projekt och deras angivna Python-miljö.", "https://docs.python.org/3/library/unittest.html"),
    ("sql-read", "utveckling", "SQL – grundmall för läsning", "databaser", "SELECT id, title\nFROM items\nORDER BY id DESC\nLIMIT 20;", "För SQLite/PostgreSQL/MariaDB med motsvarande schema. Kör som läsbehörig användare; anpassa tabell och kolumner.", "https://www.sqlite.org/lang_select.html"),
]:
    add("extra-" + key, pack, title, category, content, notes, "bra-att-ha, drift, verktyg", source)

game("zomboid", "Project Zomboid", 380870,
     "bash start-server.sh -servername MinServer", "call StartServer64.bat -servername MinServer",
     "Byt servernamn. Kör första starten interaktivt och välj adminlösenord när servern frågar. "
     "Servernamnet bestämmer konfiguration och sparmapp. Kontrollera stöd för klientens build; "
     "använd inte samma värld för olika builds utan backup.",
     "https://pzwiki.net/wiki/Dedicated_server")
game("unturned", "Unturned", 1110390,
     "./ServerHelper.sh +LanServer/MinServer", 'call "%~dp0ServerHelper.bat" +LanServer/MinServer',
     "LAN-mall med medföljande hjälpskript som sätter miljön. Byt ServerID MinServer. "
     "Inställningar sparas under Servers/MinServer. Använd Save eller Shutdown i konsolen för att spara. "
     "Internetserver kräver separat konfiguration och GSLT enligt dokumentationen.",
     "https://docs.smartlydressedgames.com/en/stable/servers/steamcmd.html")
game("gmod", "Garry's Mod", 4020,
     "./srcds_run -game garrysmod -console +gamemode sandbox +map gm_construct +maxplayers 16 +sv_lan 1",
     "srcds.exe -game garrysmod -console +gamemode sandbox +map gm_construct +maxplayers 16 +sv_lan 1",
     "LAN-mall. Byt karta och gamemode. För publik drift måste GSLT och serverns plats ställas in enligt "
     "Facepunchs regler. Workshop-tillägg kan köra kod; installera bara betrodda addons.",
     "https://wiki.facepunch.com/gmod/Downloading_a_Dedicated_Server")
game("l4d2", "Left 4 Dead 2", 222860,
     "./srcds_run -game left4dead2 -console +map c1m1_hotel +sv_lan 1",
     "srcds.exe -game left4dead2 -console +map c1m1_hotel +sv_lan 1",
     "LAN-mall med första Dead Center-kartan. Byt karta och konfigurera server.cfg. "
     "Spelarantal och spelläge styrs av spelet; extra slots kan kräva mods.",
     "https://developer.valvesoftware.com/wiki/Left_4_Dead_2/Dedicated_server")
game("svencoop", "Sven Co-op", 276060,
     "./svends_run -console -port 27015 +map _server_start +sv_lan 1",
     "svends.exe -console -port 27015 +map _server_start +sv_lan 1",
     "LAN-mall. Kontrollera att kartan _server_start finns i din distribution; byt annars till installerad karta. "
     "AppID avser dedicated server, inte klienten. Anpassa server.cfg och port vid flera instanser.",
     "https://wiki.svencoop.com/wiki/Running_a_server")
game("dst", "Don't Starve Together", 343050,
     "cd bin\n./dontstarve_dedicated_server_nullrenderer -console -cluster Cluster_1 -shard Master",
     'cd /d bin\ndontstarve_dedicated_server_nullrenderer.exe -console -cluster Cluster_1 -shard Master',
     "För distributionens bin-mapp; 64-bitarsbinärer kan ligga i bin64 och ha suffix _x64. "
     "Skapa Cluster_1, cluster.ini, Master/server.ini och ett giltigt cluster_token.txt från Klei. "
     "Token är en hemlighet. Grottor körs som separat shard med egna inställningar.",
     "https://forums.kleientertainment.com/forums/forum/83-dont-starve-together-dedicated-server-discussion/")
game("vrising", "V Rising", 1829350, None,
     'VRisingServer.exe -persistentDataPath ".\\server-data" -serverName "Min V Rising-server"',
     "Windows-servermall. Skapa Settings under server-data och anpassa ServerHostSettings.json och "
     "ServerGameSettings.json enligt rätt spelversion. Använd egna lösenord och separata portar för varje instans. "
     "Native Linux-start ingår inte; använd inte den här EXE-filen som ett Linux-kommando.",
     "https://github.com/StunlockStudios/vrising-dedicated-server-instructions")
game("openttd", "OpenTTD", None,
     "openttd -D", "openttd.exe -D",
     "Kräver OpenTTD och dess basdata. Konfigurera openttd.cfg, servernamn och spel-/adminlösenord. "
     "Versalt -D startar dedicated-läge. Använd identiska NewGRF och versioner på klient och server.",
     "https://wiki.openttd.org/en/Manual/Dedicated%20server")
game("mindustry", "Mindustry", None,
     "java -jar server-release.jar", "java -jar server-release.jar",
     "Hämta server-release.jar från projektets officiella releases och installera Java-versionen releasen kräver. "
     "När konsolen startat: skriv help och sedan host KARTNAMN för en tillgänglig karta. "
     "Matcha klientversion. JAR-starten ensam startar inte en karta.",
     "https://mindustrygame.github.io/wiki/servers/")
game("teeworlds", "Teeworlds", None,
     "./teeworlds_srv -f serverconfig.cfg", "teeworlds_srv.exe -f serverconfig.cfg",
     "Kräver Teeworlds-serverbinär, kartor och egen serverconfig.cfg. Ange servernamn, karta, speltyp och "
     "starkt RCON-lösenord. Standardport är 8303; kontrollera rätt version för klienterna.",
     "https://www.teeworlds.com/?page=docs&wiki=server_setup")

for key, title, category, content, notes, source in [
    ("steamcmd-windows", "SteamCMD – Windows-installationsmall", "steamcmd",
     '@echo off\ncd /d "%~dp0"\nsteamcmd.exe +force_install_dir "C:\\GameServers\\MinServer" +login anonymous +app_update APPID validate +quit\n'
     'if errorlevel 1 exit /b 1\npause\n',
     "Byt APPID till spelets dedicated server-ID och installationsmappen till en absolut sökväg. "
     "steamcmd.exe ska finnas bredvid BAT-filen. Stoppa servern och säkerhetskopiera världen först. "
     "Inte alla spel tillåter anonymous.", "https://developer.valvesoftware.com/wiki/SteamCMD"),
    ("steamcmd-platform", "SteamCMD – hämta Windows-filer från Linux", "steamcmd",
     'steamcmd +@sSteamCmdForcePlatformType windows +force_install_dir /srv/windows-server +login anonymous +app_update APPID validate +quit',
     "Byt APPID och mapp. Detta laddar ned Windows-filer men gör dem inte körbara på Linux. "
     "Wine/Proton-kompatibilitet är en separat fråga; använd native-server eller Windows-host när möjligt.",
     "https://developer.valvesoftware.com/wiki/SteamCMD"),
    ("steamcmd-login", "SteamCMD – interaktiv inloggning för licenskrävande spel", "steamcmd",
     "steamcmd\n# Skriv sedan i SteamCMD-konsolen:\nforce_install_dir /srv/min-server\nlogin DITT_STEAMNAMN\napp_update APPID validate\nquit",
     "Byt namn, APPID och mapp. Skriv lösenord/Steam Guard interaktivt när SteamCMD frågar; "
     "lägg inte lösenord i kommandohistorik eller sparade kodsnuttar. Kräver rätt licens.",
     "https://developer.valvesoftware.com/wiki/SteamCMD"),
    ("steamcmd-inspect", "SteamCMD – kontrollera appinformation", "steamcmd",
     "steamcmd +login anonymous +app_info_update 1 +app_info_print APPID +quit",
     "Byt APPID. Visar den information som anonymt konto får se; vissa depots eller branches kräver licens.",
     "https://developer.valvesoftware.com/wiki/SteamCMD"),
    ("factorio-create", "Factorio – skapa en ny servervärld", "spelserver",
     "./bin/x64/factorio --create ./saves/ny-varld.zip",
     "Linux från Factorios installationsrot. Skapa saves-mappen först och använd ett nytt filnamn. "
     "Starta sedan med --start-server och samma sökväg. Använd separat backup för befintliga världar.",
     "https://wiki.factorio.com/Multiplayer"),
    ("openttd-save", "OpenTTD – starta från sparfil", "spelserver",
     "openttd -D -g ./saves/min-varld.sav",
     "Kräver befintlig sparfil samt rätt version och NewGRF. Anpassa nätverksinställningar i openttd.cfg.",
     "https://wiki.openttd.org/en/Manual/Dedicated%20server"),
    ("minecraft-props", "Minecraft Java – privat server.properties-mall", "dokumentation",
     "server-port=25565\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\n"
     "enable-rcon=false\nmax-players=10\nmotd=Min privata Minecraft-server\n",
     "Infoga relevanta rader i befintlig server.properties när servern är stoppad. "
     "Kör whitelist add SPELARNAMN i konsolen för dina spelare. Hela filen ersätts inte av denna mall.",
     "https://minecraft.wiki/w/Server.properties"),
    ("minecraft-console", "Minecraft Java – spara och stoppa säkert", "spelserver",
     "save-all flush\nstop",
     "Skriv dessa i Minecraft-serverns konsol, inte i Linux-terminalen. Vänta tills servern avslutats innan "
     "du säkerhetskopierar world-mappar eller uppdaterar JAR.",
     "https://minecraft.wiki/w/Commands/save-all"),
    ("unturned-console", "Unturned – spara och avsluta", "spelserver",
     "Save\nShutdown",
     "Kommandon för spelets serverkonsol, inte operativsystemets skal. Vänta på avslut före kopiering av Servers-mappen.",
     "https://docs.smartlydressedgames.com/en/stable/servers/server-hosting.html"),
    ("dst-caves", "Don't Starve Together – separat grottserver", "spelserver",
     "cd bin\n./dontstarve_dedicated_server_nullrenderer -console -cluster Cluster_1 -shard Caves",
     "Starta som separat process bredvid Master-sharden. Kräver Caves/server.ini och korrekta shard-ID, "
     "masteranslutning och världskonfiguration enligt Klei. Använd rätt bin/bin64 för din distribution.",
     "https://forums.kleientertainment.com/forums/forum/83-dont-starve-together-dedicated-server-discussion/"),
    ("zomboid-console", "Project Zomboid – spara och avsluta", "spelserver",
     "save\nquit",
     "Kör i Zomboid-serverkonsolen. Spara världen och vänta på avslut före backup av Zomboid-profilmappen.",
     "https://pzwiki.net/wiki/Dedicated_server"),
    ("game-isolation", "Spelservrar – checklista för flera instanser", "dokumentation",
     "# En separat spelserverinstans behöver:\n"
     "# 1. Egen spar-/profilkatalog och konfigurationsfil.\n"
     "# 2. Unika game-, query- och adminportar enligt spelguiden.\n"
     "# 3. Egen systemd-tjanst, container eller terminalsession.\n"
     "# 4. Egen backupplan och testad aterstallning.\n"
     "# 5. Tillrackligt RAM och diskutrymme.\n",
     "Ändra inte alla spel till samma port. Query och RCON kan kräva andra protokoll/portar än själva spelet. "
     "Ge spelprocessen bara rättigheter till dess egna filer.",
     "https://developer.valvesoftware.com/wiki/SteamCMD"),
    ("game-ports", "Spelservrar – kontrollera lyssnande portar på Linux", "natverk",
     "ss -tuln\n# Om du har rattigheter att se processerna:\nss -tulnp",
     "Jämför med spelets guide. En TCP-portkontroll bevisar inte att UDP fungerar. "
     "Använd spelets klient för att testa anslutning och kontrollera serverloggen.",
     "https://man7.org/linux/man-pages/man8/ss.8.html"),
    ("game-backup", "Spelservrar – backupchecklista före uppdatering", "dokumentation",
     "# Stoppa med spelets egen save/stop/shutdown-funktion.\n"
     "# Kopiera varldar, profiler, konfiguration och modlista.\n"
     "# Notera serverversion, branch och startargument.\n"
     "# Testa aterstallning i en separat instans utan att ersatta originalet.\n"
     "# Uppdatera forst nar backupen har verifierats.\n",
     "SteamCMD validate kan ersätta originalfiler men är inte en backup. Klient och server kan behöva samma "
     "version eller mods. Lagra hemliga server-/RCON-lösenord separat och säkert.",
     "https://developer.valvesoftware.com/wiki/SteamCMD"),
]:
    add("game-tools-" + key, "spel", title, category, content, notes, "spelserver, steamcmd, drift", source)
