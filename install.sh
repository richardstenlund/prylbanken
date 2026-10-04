#!/bin/sh
set -eu
umask 077

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' 'Docker saknas. Installera Docker Engine och Docker Compose v2 innan du fortsatter.' >&2
    exit 1
fi
if ! docker info >/dev/null; then
    printf '%s\n' 'Docker svarar inte. Starta Docker och kontrollera dina behorigheter.' >&2
    exit 1
fi
if ! docker compose version; then
    printf '%s\n' 'Docker Compose v2 saknas. Installera Compose-pluginen.' >&2
    exit 1
fi

# Use the saved configuration, not exported variables from the calling shell.
unset APP_PASSWORD BIND_ADDRESS APP_PORT
password=''
if [ -L .env ]; then
    printf '%s\n' '.env ar en symbolisk lank. Avbryter for att inte andra en annan fil.' >&2
    exit 1
elif [ -e .env ]; then
    if [ ! -f .env ]; then
        printf '%s\n' '.env maste vara en vanlig fil.' >&2
        exit 1
    fi
    printf '%s\n' 'Befintlig .env bevaras. Ditt losenord och dina portinstallningar andras inte.'
else
    password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
    case "$password" in
        ''|*[!0-9a-f]*)
            printf '%s\n' 'Kunde inte skapa ett sakert losenord.' >&2
            exit 1 ;;
    esac
    if [ "${#password}" -ne 48 ]; then
        printf '%s\n' 'Kunde inte lasa tillrackligt med slumpdata.' >&2
        exit 1
    fi
    (set -C; printf 'APP_PASSWORD=%s\nBIND_ADDRESS=0.0.0.0\nAPP_PORT=8080\n' "$password" > .env)
    printf '%s\n' 'Ny .env skapad med slumpmassigt losenord och LAN-atkomst pa port 8080.'
fi
chmod 600 .env

printf '\n%s\n' \
    'LAN-installationen oppnar porten pa serverns alla natverksgranssnitt.' \
    'Anvand bara pa ett betrott privat natverk. Oppna inte porten i routern.' \
    'HTTP krypterar inte inloggningen. Anvand HTTPS eller VPN for annan atkomst.' \
    'Bygger och startar Prylbanken. Forsta starten kan ta nagra minuter...'

if ! docker compose config --quiet; then
    printf '%s\n' 'Konfigurationen ar ogiltig. Kontrollera .env och compose.yaml.' >&2
    exit 1
fi
if ! docker compose up -d --build --wait --wait-timeout 120; then
    printf '%s\n' \
        'Installationen ar inte klar. Las felmeddelandet ovan och kor docker compose logs --tail=50.' \
        'Din .env och dina data finns kvar. Kor sh install.sh igen nar felet ar lost.' \
        'Om --wait inte stods behover Docker Compose uppdateras.' >&2
    exit 1
fi

printf '\n%s\n' 'Prylbanken ar startad och halsokontrollen har godkants.' 'Anvandarnamn: admin'
if [ -n "$password" ]; then
    printf 'Losenord: %s\n' "$password"
else
    printf '%s\n' 'Anvand kontots befintliga losenord. Vid forsta konto-starten anvands APP_PASSWORD i .env.'
fi
printf '%s\n' \
    'Vid standardinstallationen: oppna http://SERVERNS-IP:8080 i din webblasare.' \
    'Om du redan hade en .env, anvand dess port och bindningsadress.' \
    'Visa serverns IP med: hostname -I' \
    'APP_PASSWORD i .env anvands bara for att skapa forsta admin-kontot.' \
    'Byt sedan losenord inne pa sidan under Anvandare. Dela inte .env eller terminalutskriften.'
