"""Original Proxmox templates with official references and community bookmarks."""

PACK = {
    "id": "proxmox", "title": "Proxmox VE & hjälpskript",
    "description": "VM/LXC, snapshots, backup, inventering och länkar till community-skript. Inget körs automatiskt.",
}
BASE = "https://pve.proxmox.com/pve-docs/"
WARNING = (
    "Kör manuellt i rätt Proxmox VE-nods shell med nödvändiga behörigheter, inte i Prylbankens container. "
    "Använd Anpassa mall för {{variabler}}. Kontrollera ID, lagring och argument före körning; "
    "värden ersätts bokstavligt utan shell-escaping. Syntaxen är kontrollerad mot dokumentationen, "
    "men mallen är inte körtestad på en Proxmox-host. "
)

COMMANDS = [
    ("version", "Proxmox – version och komponenter", "pveversion -v\n",
     "Läsning av installerade versioner. Dela inte diagnostik publikt utan att granska den.", "pve-admin-guide.html", "diagnostik"),
    ("guests", "Proxmox – lista virtuella maskiner och LXC", "qm list\npct list\n",
     "Listar gäster på aktuell nod. Använd klusterresursmallen för övriga noder.", "qm.1.html", "inventering, lxc, vm"),
    ("vm-status", "Proxmox VM – visa status", 'qm status "{{vmid}}"\n',
     "Läsning. VMID ska vara ett befintligt VM-ID, inte ett LXC-ID.", "qm.1.html", "vm, status"),
    ("ct-status", "Proxmox LXC – visa status", 'pct status "{{ctid}}"\n',
     "Läsning. CTID ska vara ett befintligt container-ID.", "pct.1.html", "lxc, status"),
    ("vm-config", "Proxmox VM – visa konfiguration", 'qm config "{{vmid}}"\n',
     "Läsning. Konfigurationen kan innehålla interna nätverksuppgifter och känsliga inställningar.", "qm.1.html", "vm, konfiguration"),
    ("ct-config", "Proxmox LXC – visa konfiguration", 'pct config "{{ctid}}"\n',
     "Läsning. Granska mount points, backupflagga och unprivileged. Dela inte känsliga uppgifter.", "pct.1.html", "lxc, konfiguration"),
    ("vm-start", "Proxmox VM – starta en maskin", 'qm start "{{vmid}}"\n',
     "ÄNDRAR DRIFT: startar vald VM. Kontrollera minne, lagring och eventuella HA-regler.", "qm.1.html", "vm, start"),
    ("ct-start", "Proxmox LXC – starta en container", 'pct start "{{ctid}}"\n',
     "ÄNDRAR DRIFT: startar vald LXC. Kontrollera mount points och resurser.", "pct.1.html", "lxc, start"),
    ("vm-shutdown", "Proxmox VM – stäng av skonsamt", 'qm shutdown "{{vmid}}" --timeout 120\n',
     "DRIFTAVBROTT: skickar avstängningsbegäran till vald VM. Gäst-OS måste hantera den. "
     "Ingen tvingad stop används; kontrollera status efteråt och avbryt inte backupjobb.", "qm.1.html", "vm, avstangning"),
    ("ct-shutdown", "Proxmox LXC – stäng av skonsamt", 'pct shutdown "{{ctid}}" --timeout 120\n',
     "DRIFTAVBROTT: stänger av vald container. Ingen tvingad stop används. Kontrollera status efteråt.", "pct.1.html", "lxc, avstangning"),
    ("ct-exec", "Proxmox LXC – kontrollera diskutrymme inifrån", 'pct exec "{{ctid}}" -- df -h\n',
     "Kör ett läsande kommando inne i en startad LXC. Kommandot df måste finnas i containern. "
     "Ingen miljövariabel från hosten behövs.", "pct.1.html", "lxc, disk"),
    ("vm-snapshots", "Proxmox VM – lista snapshots", 'qm listsnapshot "{{vmid}}"\n',
     "Läsning. En snapshot är inte en separat säkerhetskopia och skyddar inte mot lagringshaveri.", "qm.1.html", "vm, snapshot"),
    ("ct-snapshots", "Proxmox LXC – lista snapshots", 'pct listsnapshot "{{ctid}}"\n',
     "Läsning. Snapshots ersätter inte extern backup.", "pct.1.html", "lxc, snapshot"),
    ("vm-snapshot", "Proxmox VM – skapa snapshot utan RAM", 'qm snapshot "{{vmid}}" "{{snapshot_name}}" --vmstate 0\n',
     "ÄNDRAR LAGRING: kräver snapshotstöd för berörda diskar. Använd ett nytt giltigt namn. "
     "Ingen RAM-status sparas. Gästagent och applikationsrutiner kan krävas för konsistens; ta separat backup.", "qm.1.html", "vm, snapshot"),
    ("ct-snapshot", "Proxmox LXC – skapa snapshot", 'pct snapshot "{{ctid}}" "{{snapshot_name}}"\n',
     "ÄNDRAR LAGRING: kräver stöd från containerlagring och berörda volymer. "
     "Bind mounts och externa data behöver separat skydd. Använd ett nytt giltigt namn.", "pct.1.html", "lxc, snapshot"),
    ("vm-clone", "Proxmox VM – fullständig klon till nytt ID",
     'qm clone "{{source_vmid}}" "{{new_vmid}}" --full 1 --name "{{new_name}}" --storage "{{target_storage}}"\n',
     "ÄNDRAR LAGRING: new_vmid måste vara ledigt i hela klustret. Kräver diskutrymme. "
     "Kontrollera klonens IP, hostname och applikationsidentitet innan start för att undvika konflikter.", "qm.1.html", "vm, klon"),
    ("backup", "Proxmox – backup av en gäst till backuplagring",
     'vzdump "{{guest_id}}" --storage "{{backup_storage}}" --mode snapshot\n',
     "SKAPAR BACKUP: gäller VM eller LXC. Målet måste stödja backupinnehåll och ha plats. "
     "Snapshotläge kan belasta lagring och ge korta avbrott för LXC. Bind/device mounts ingår inte "
     "i LXC-backup; extra volymer måste kontrolleras. Testa återställning separat.", "vzdump.1.html", "backup, vm, lxc"),
    ("vm-restore", "Proxmox VM – återställ backup till nytt ID",
     'qmrestore "{{backup_archive}}" "{{new_vmid}}" --storage "{{target_storage}}"\n',
     "SKAPAR VM FRÅN BACKUP: argumentordningen är arkiv först, VMID sedan. "
     "Ange en befintlig Proxmox-backupfil eller backupvolym, inte en snapshot. "
     "Använd ledigt ID och rätt diskstorage. Ingen --force och ingen automatisk start; kontrollera nätverk före start.", "qmrestore.1.html", "vm, aterstallning"),
    ("ct-restore", "Proxmox LXC – återställ backup till nytt ID",
     'pct restore "{{new_ctid}}" "{{backup_archive}}" --storage "{{target_storage}}"\n',
     "SKAPAR LXC FRÅN BACKUP: argumentordningen är CTID först, arkiv sedan. "
     "Använd ledigt ID. Ingen --force. Externa bind mounts och data som inte ingick måste återställas separat.", "pct.1.html", "lxc, aterstallning"),
    ("storage", "Proxmox – kontrollera lagring", "pvesm status\n",
     "Läsning av lagringsstatus. Lagringstyp avgör vilka innehåll och snapshotfunktioner som stöds.", "pvesm.1.html", "lagring"),
    ("nodes", "Proxmox – lista klustrets noder", "pvesh get /nodes --output-format json-pretty\n",
     "Läsande API-anrop. Kräver rättigheter på hosten. API-sökvägar och egenskaper kan variera mellan versioner.", "pvesh.1.html", "kluster, api"),
    ("resources", "Proxmox – lista gäster i hela klustret", "pvesh get /cluster/resources --type vm --output-format json-pretty\n",
     "Läsning. API-typen vm omfattar både QEMU och LXC; kontrollera varje posts type och node.", "pvesh.1.html", "kluster, inventering"),
    ("templates", "Proxmox LXC – uppdatera och lista OS-mallar", "pveam update\npveam available --section system\n",
     "Uppdaterar mallkatalogen via nätet, men installerar ingen gäst. Välj ett exakt tillgängligt mallnamn.", "pveam.1.html", "lxc, mallar"),
    ("template-download", "Proxmox LXC – ladda ned vald OS-mall", 'pveam download "{{template_storage}}" "{{template_filename}}"\n',
     "SKRIVER FIL: välj storage med innehållstyp vztmpl och ledigt utrymme. "
     "Hämta exakt filnamn från pveam available; inga versionsnamn antas i denna mall.", "pveam.1.html", "lxc, mallar"),
    ("report-script", "Proxmox – eget läsande inventeringsskript",
     '#!/usr/bin/env bash\nset -euo pipefail\n'
     'for tool in pveversion qm pct pvesm; do\n'
     '  command -v "$tool" >/dev/null || { printf "Saknat verktyg: %s\\n" "$tool" >&2; exit 1; }\n'
     'done\n'
     'printf "\\n=== Version ===\\n"\npveversion -v\n'
     'printf "\\n=== Virtuella maskiner ===\\n"\nqm list\n'
     'printf "\\n=== LXC ===\\n"\npct list\n'
     'printf "\\n=== Lagring ===\\n"\npvesm status\n',
     "Eget originalskript. Spara som pve-inventory.sh och kör med bash pve-inventory.sh på hosten. "
     "Läser endast och avbryter vid fel. Utdata kan innehålla intern infrastrukturinformation.", "pve-admin-guide.html", "skript, inventering"),
    ("backup-script", "Proxmox – eget backupskript med bekräftelse",
     '#!/usr/bin/env bash\nset -euo pipefail\n'
     'guest_id="${1:?Anvand: bash pve-backup.sh GUEST_ID BACKUP_STORAGE}"\n'
     'storage="${2:?Ange backup-storage som andra argument}"\n'
     '[[ "$guest_id" =~ ^[1-9][0-9]{2,8}$ ]] || { printf "Ogiltigt gast-ID\\n" >&2; exit 1; }\n'
     '[[ "$storage" =~ ^[A-Za-z][A-Za-z0-9_-]*$ ]] || { printf "Ogiltigt storage-ID\\n" >&2; exit 1; }\n'
     'command -v vzdump >/dev/null || { printf "vzdump saknas\\n" >&2; exit 1; }\n'
     'printf "Backup av gast %s till %s. Kontrollera mal och ledigt utrymme.\\n" "$guest_id" "$storage"\n'
     'read -r -p "Skriv BACKUP for att fortsatta: " confirmation\n'
     '[[ "$confirmation" == BACKUP ]] || { printf "Avbrutet\\n" >&2; exit 1; }\n'
     'vzdump "$guest_id" --storage "$storage" --mode snapshot\n',
     "Eget originalskript med argumentkontroll, felavbrott och interaktiv bekräftelse. "
     "Exempel: bash pve-backup.sh 100 backup-storage. Inte avsett för obevakad schemaläggning. "
     "Kontrollera backupmålets innehållstyp/plats och att externa LXC-data skyddas separat.", "vzdump.1.html", "skript, backup"),
]
BOOKMARKS = [
    ("community-site", "Proxmox – Community Scripts katalog", "https://community-scripts.org/",
     "Community-projekt, inte en officiell Proxmox-tjänst. Hitta hjälpskript för bland annat LXC, VM och självhostade appar. "
     "Läs krav, källkod och ändringar före användning. Många installationsskript kör med root och hämtar ytterligare kod. "
     "Använd först en testmiljö och verifierad backup. Kör inte blint curl/wget direkt till bash."),
    ("community-source", "Proxmox – Community Scripts källkod", "https://github.com/community-scripts/ProxmoxVE",
     "Källkod, versionshistorik och ärenden för community-skripten. Läs både valt skript och dess inlästa hjälpfiler. "
     "Granska en bestämd commit/version; huvudgrenen kan ändras. Inga tredjepartsskript kopieras eller körs av Prylbanken."),
    ("official-guide", "Proxmox VE – officiell administrationsguide", BASE + "pve-admin-guide.html",
     "Officiell dokumentation för virtualisering, nätverk, lagring, kluster och backup. "
     "Kontrollera din installerade version med pveversion -v och använd rätt versionsdokumentation."),
    ("pbs-docs", "Proxmox Backup Server – officiell dokumentation", "https://pbs.proxmox.com/docs/",
     "Planera extern backup, verifieringsjobb, retention och återställning. "
     "En snapshot på samma lagring ersätter inte en testad extern backup. Skydda API-token och krypteringsnycklar."),
]
EXAMPLES = [
    {"key": "proxmox-" + key, "pack": "proxmox", "title": title, "category": "proxmox",
     "content": content, "notes": WARNING + notes + "\nReferens: " + BASE + reference,
     "tags": "proxmox, " + tags, "favorite": False, "language": "bash",
     "download_name": ("pve-inventory.sh" if key == "report-script" else "pve-backup.sh" if key == "backup-script" else ""),
     "os": "Linux / Proxmox VE", "status": "template"}
    for key, title, content, notes, reference, tags in COMMANDS
] + [
    {"key": "proxmox-" + key, "pack": "proxmox", "title": title, "category": "lankar",
     "content": url, "notes": notes + "\nReferens: " + url,
     "tags": "proxmox, dokumentation" + (", community, skript" if key.startswith("community") else ""),
     "favorite": False, "language": "plain", "status": "template"}
    for key, title, url, notes in BOOKMARKS
]
