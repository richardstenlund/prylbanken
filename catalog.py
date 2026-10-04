"""Original command templates for optional library starter packs."""

PACKS = [
    {"id": "spel", "title": "Spelservrar & SteamCMD", "description": "Installation och startmallar för elva spel."},
    {"id": "docker", "title": "Docker & Compose", "description": "Status, loggar, felsökning och uppdatering."},
    {"id": "linux", "title": "Linux & backup", "description": "Disk, tjänster, processer och säkerhetskopior."},
    {"id": "windows", "title": "Windows & PowerShell", "description": "Tjänster, nätverk, loggar och filer."},
    {"id": "natverk", "title": "Nätverk & SSH", "description": "DNS, HTTP, portar och säkra anslutningar."},
    {"id": "utveckling", "title": "Git, Python & SQL", "description": "Vardagsverktyg för kod och databaser."},
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
