"use strict";
let serverRegistry = [], environmentProfiles = [], linkChecks = new Map(), importCandidates = [];
let registryMode = "servers", editingRecord = null, deferredInstall = null;
let registryRevision = 0, bookmarkRevision = 0;
const serverFilter = document.createElement("select"); serverFilter.id = "filter-server";
serverFilter.append(option("", "Alla servrar")); $(".filters").append(labeled("Server", serverFilter));
serverFilter.addEventListener("change", render);
const troubleshootingFilter = document.createElement("input"); troubleshootingFilter.type = "checkbox";
troubleshootingFilter.id = "filter-troubleshooting";
const troubleLabel = labeled("Bara felsökning", troubleshootingFilter); troubleLabel.className = "checkbox";
$(".filters").append(troubleLabel); troubleshootingFilter.addEventListener("change", render);
function refreshExpansion(servers, profiles, checks) {
  serverRegistry = servers; environmentProfiles = profiles;
  linkChecks = new Map(checks.map(check => [check.item_id, check]));
  const selected = serverFilter.value;
  serverFilter.replaceChildren(option("", "Alla servrar"), ...servers.map(server => option(server.id, server.name)));
  serverFilter.value = servers.some(server => String(server.id) === selected) ? selected : "";
}
function expansionMatches(item) {
  return (!serverFilter.value || item.server_ids.includes(Number(serverFilter.value))) &&
    (!troubleshootingFilter.checked || item.entry_type === "troubleshooting");
}
const itemServerChoices = el("fieldset", "account-form");
const pinnedInput = document.createElement("input"); pinnedInput.type = "checkbox"; pinnedInput.id = "editor-pinned";
const pinLabel = labeled("Fäst gemensamt överst (administratör)", pinnedInput); pinLabel.className = "checkbox";
const entryType = document.createElement("select"); entryType.id = "editor-entry-type";
entryType.append(option("standard","Vanlig bibliotekspost"), option("troubleshooting","Felsökningspost"));
const symptomsInput = document.createElement("textarea"); symptomsInput.id = "editor-symptoms"; symptomsInput.maxLength = 10000;
const solutionInput = document.createElement("textarea"); solutionInput.id = "editor-solution"; solutionInput.maxLength = 10000;
const incidentInput = document.createElement("input"); incidentInput.type = "date"; incidentInput.id = "editor-incident-at";
const troubleFields = el("section", "account-form");
troubleFields.append(labeled("Symptom / felmeddelande", symptomsInput), labeled("Lösning / vad provades", solutionInput),
  labeled("Felsökningsdatum", incidentInput));
$("#existing-file").after(itemServerChoices, pinLabel, labeled("Posttyp",entryType), troubleFields);
form.elements.language.append(option("markdown","Markdown"));
entryType.addEventListener("change", () => { troubleFields.hidden = entryType.value !== "troubleshooting"; });
function fillServerChoices(container, selected = []) {
  container.replaceChildren(el("legend","","Kopplade servrar"));
  serverRegistry.forEach(server => {
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.value = server.id;
    checkbox.checked = selected.includes(server.id);
    const label = labeled(server.name,checkbox); label.className = "checkbox"; container.append(label);
  });
  if (!serverRegistry.length) container.append(el("p","muted","Lägg till servrar i Serverregister."));
}
function selectedServers(container) {
  return [...container.querySelectorAll("input:checked")].map(input => Number(input.value));
}
function populateExpansionEditor(item) {
  fillServerChoices(itemServerChoices,item?.server_ids || []);
  pinnedInput.checked = item?.pinned === "1"; pinnedInput.disabled = !isAdmin(); pinLabel.hidden = !isAdmin();
  entryType.value = item?.entry_type || "standard"; troubleFields.hidden = entryType.value !== "troubleshooting";
  symptomsInput.value = item?.symptoms || ""; solutionInput.value = item?.solution || ""; incidentInput.value = item?.incident_at || "";
}
function expansionEditorPayload() {
  return {server_ids:selectedServers(itemServerChoices), pinned:pinnedInput.checked ? "1" : "0",
    entry_type:entryType.value, symptoms:symptomsInput.value, solution:solutionInput.value, incident_at:incidentInput.value};
}
const guideServers = el("fieldset","account-form"); guideForm.insertBefore(guideServers,stepRows);
function populateGuideServers(guide) { fillServerChoices(guideServers,guide?.server_ids || []); }
function guideServerPayload() { return selectedServers(guideServers); }
function appendGuideSharing(container, guide) {
  appendShareButton(container,"guide",guide.id);
  (guide.server_ids || []).forEach(id => {
    const server = serverRegistry.find(record => record.id === id);
    if (server) container.append(action(server.name,"small-button",() => showServer(server)));
  });
}
function appendShareButton(container, type, id) {
  container.append(action("Dela intern länk","secondary",() => {
    const url = `${location.origin}/#${type}=${id}`;
    const input = document.createElement("input"); input.readOnly = true; input.value = url;
    input.setAttribute("aria-label","Intern länk (inloggning krävs)");
    shareBody.replaceChildren(el("p","muted","Länken kräver inloggning och ger inte nya behörigheter."),input,
      action("Kopiera länk","secondary",() => copy(url)));
    shareDialog.showModal(); input.select();
  }));
}
const shareDialog = makeDialog("share-link","Dela inom biblioteket"), shareBody = $("#share-link-body");
function appendExpansionTools(body,item) {
  appendShareButton(body,"item",item.id);
  if (canEdit()) body.append(action("Duplicera som egen mall","secondary",async event => {
    const button = event.currentTarget; button.disabled = true;
    try {
      const result = await api(`/api/items/${item.id}/duplicate`,"POST",{});
      await load(); $("#detail").close(); openEditor(items.find(record => record.id === result.id));
      notify("En separat kopia har sparats. Originalet är oförändrat.");
    } catch (failure) { showError(failure); }
    finally { button.disabled = false; }
  }));
  item.server_ids.forEach(id => {
    const server = serverRegistry.find(record => record.id === id);
    if (server) body.append(action("Server: "+server.name,"small-button",() => showServer(server)));
  });
  if (item.entry_type === "troubleshooting") body.append(el("h3","","Felsökning "+(item.incident_at || "")),
    el("h4","","Symptom"),el("p","detail-notes",item.symptoms),el("h4","","Lösning"),el("p","detail-notes",item.solution));
  if (item.category === "lankar") {
    const state = linkChecks.get(item.id);
    const status = el("p","muted",state ? `${formatDate(state.checked)} · ${state.status} · ${state.detail}` : "Länken har inte kontrollerats.");
    body.append(status);
    if (canEdit()) {
      const error = el("p","error"); error.hidden = true; error.setAttribute("role","alert");
      body.append(action("Kontrollera publik länk","secondary",async event => {
        const button = event.currentTarget; button.disabled = true; error.hidden = true;
        try {
          const result = await api(`/api/items/${item.id}/check-link`,"POST",{});
          status.textContent = `${result.detail} · ${result.final_url}`; await load();
        } catch (failure) { showError(failure,error); }
        finally { button.disabled = false; }
      }),error);
    }
  }
}
function appendProfilePicker(section, inputs) {
  const select = document.createElement("select"); select.append(option("","Välj miljöprofil"),
    ...environmentProfiles.map(profile => option(profile.id,profile.name)));
  section.append(labeled("Fyll variabler från miljöprofil",select),action("Använd profil","secondary",() => {
    const profile = environmentProfiles.find(record => String(record.id) === select.value);
    if (!profile) { showError(new Error("Välj en miljöprofil.")); return; }
    let count = 0;
    inputs.forEach((input,name) => {
      if (Object.hasOwn(profile.variables,name)) {
        input.value = profile.variables[name]; input.dispatchEvent(new Event("input")); count += 1;
      }
    });
    notify(count ? `${count} variabler ifyllda. Granska alla värden före generering.` : "Profilen saknar matchande variabler.");
  }));
}

const recordsDialog = makeDialog("registry","Serverregister & miljöprofiler");
const recordEditor = makeDialog("registry-editor","Redigera registerpost");
const recordForm = document.createElement("form");
function recordField(name,label,max,multiline=false) {
  const input = document.createElement(multiline ? "textarea" : "input"); input.name = name; input.maxLength = max;
  if (multiline) input.rows = 4; input.required = name === "name";
  const wrapper = labeled(label,input); wrapper.dataset.field = name; recordForm.append(wrapper);
}
recordField("name","Namn",80); recordField("address","IP / DNS-adress",255); recordField("os","Operativsystem",200);
recordField("role","Serverns funktion / roll",200); recordField("url","Administrationslänk (HTTP/HTTPS)",2000);
recordField("notes","Anteckningar (inga lösenord)",5000,true);
recordField("description","Profilbeskrivning",2000,true); recordField("variables","Variabler som JSON-objekt",120000,true);
recordForm.append(el("p","review-warning","Profiler delas med alla konton. Spara endast IP, portar och sökvägar – aldrig lösenord, token eller nycklar. Namnfilter kan inte upptäcka hemligheter i godtyckliga värden."));
const recordSave = el("button","primary","Spara"); recordSave.type = "submit"; recordForm.append(recordSave);
$("#registry-editor-body").append(recordForm);
function editRecord(record=null) {
  editingRecord = record; recordForm.reset(); $("#registry-editor-error").hidden = true;
  recordForm.querySelectorAll("[data-field]").forEach(label => {
    const key = label.dataset.field;
    label.hidden = registryMode === "servers" ? ["description","variables"].includes(key) :
      ["address","os","role","url","notes"].includes(key);
    recordForm.elements[key].value = key === "variables" ? JSON.stringify(record?.variables || {ip:"192.168.1.10",port:"27015"},null,2) : record?.[key] || "";
  });
  recordEditor.showModal();
}
recordForm.addEventListener("submit",async event => {
  event.preventDefault(); recordSave.disabled = true; $("#registry-editor-error").hidden = true;
  try {
    const payload = Object.fromEntries([...new FormData(recordForm)]);
    if (registryMode === "profiles") payload.variables = JSON.parse(payload.variables);
    await api(`/api/${registryMode}${editingRecord ? "/"+editingRecord.id : ""}`,editingRecord ? "PUT" : "POST",payload);
    recordEditor.close(); await load(); await showRecords(registryMode);
  } catch (failure) { showError(failure,$("#registry-editor-error")); }
  finally { recordSave.disabled = false; }
});
async function showRecords(mode="servers") {
  const revision = ++registryRevision;
  registryMode = mode; $("#registry-error").hidden = true;
  try {
    await load();
    const linkedGuides = mode === "servers" ? await api("/api/guides") : [];
    if (revision !== registryRevision || !recordsDialog.open) return;
    const body = $("#registry-body"); body.replaceChildren(
      action("Servrar","secondary",() => showRecords("servers")), action("Miljöprofiler","secondary",() => showRecords("profiles")),
      el("p","muted",mode === "servers" ? "Ett gemensamt register. Inga anslutningar eller kommandon körs automatiskt." :
        "Gemensamma profiler med icke-hemliga mallvärden. Kontrollera argument och citattecken."));
    if (canEdit()) body.append(action("Lägg till "+(mode === "servers" ? "server" : "profil"),"primary",() => editRecord()));
    const records = mode === "servers" ? serverRegistry : environmentProfiles;
    if (!records.length) body.append(el("p","muted","Registret är tomt."));
    records.forEach(record => {
      const section = el("section","account-form"); section.dataset.recordId = record.id;
      section.append(el("h3","",record.name));
      if (mode === "servers") {
        section.append(el("p","detail-notes",`${record.address} · ${record.os} · ${record.role}\n${record.notes}`));
        if (record.url) { const link = el("a","secondary","Öppna administration ↗"); link.href = record.url; link.target="_blank"; link.rel="noopener noreferrer"; section.append(link); }
        section.append(action("Visa kopplat innehåll","secondary",() => {
          active="all"; serverFilter.value=String(record.id); $("#filter-project").value=""; $("#search").value="";
          $("#filter-tags").value=""; $("#filter-os").value=""; $("#filter-language").value=""; $("#filter-status").value="";
          $("#filter-attachments").checked=false;
          personalFilter.checked=false; reviewFilter.checked=false; troubleshootingFilter.checked=false;
          recordsDialog.close(); render();
        }));
        linkedGuides.filter(guide => guide.server_ids.includes(record.id)).forEach(guide =>
          section.append(action("Guide: "+guide.title,"small-button",() => openGuide(guide.id))));
        appendShareButton(section,"server",record.id);
      } else section.append(el("p","detail-notes",record.description),el("pre","detail-code",JSON.stringify(record.variables,null,2)));
      if (canEdit()) section.append(action("Redigera","secondary",() => editRecord(record)),
        action("Ta bort","danger-button",async () => {
          if (!confirm(`Ta bort "${record.name}"? Biblioteksposter och guider behålls; serverkopplingar tas bort.`)) return;
          try { await api(`/api/${mode}/${record.id}`,"DELETE"); await load(); await showRecords(mode); }
          catch (failure) { showError(failure,$("#registry-error")); }
        }));
      body.append(section);
    });
  } catch (failure) { if (revision === registryRevision && recordsDialog.open) showError(failure,$("#registry-error")); }
}
recordsDialog.addEventListener("close", () => { registryRevision += 1; });
async function showServer(server) {
  if (!recordsDialog.open) recordsDialog.showModal();
  await showRecords("servers");
  $("#registry-body").querySelector(`[data-record-id="${server.id}"]`)?.scrollIntoView({block:"start"});
}
$(".toolbar").append(action("Serverregister & profiler","secondary",() => { recordsDialog.showModal(); showRecords(); }));

const palette = makeDialog("command-palette","Snabbsök · Ctrl+K");
const paletteInput = document.createElement("input"); paletteInput.type="search"; paletteInput.placeholder="Sök poster, projekt, guider och servrar…";
paletteInput.setAttribute("aria-label","Sök i kommandopaletten");
const paletteResults = el("div","palette-results"); $("#command-palette-body").append(paletteInput,paletteResults);
let paletteGuides=[];
function renderPalette() {
  const query=paletteInput.value.toLocaleLowerCase("sv").trim();
  const matches=[];
  for (const [kind,records] of [["item",items],["project",projects],["guide",paletteGuides],["server",serverRegistry]]) {
    records.filter(record => (record.title || record.name).toLocaleLowerCase("sv").includes(query)).forEach(record => matches.push({kind,record}));
  }
  paletteResults.replaceChildren();
  matches.slice(0,30).forEach(({kind,record}) => paletteResults.append(action(
    `${({item:"Post",project:"Projekt",guide:"Guide",server:"Server"})[kind]}: ${record.title || record.name}`,
    "title-button",() => { palette.close(); goToResource(kind,record.id).catch(failure => showError(failure)); })));
  if (!matches.length) paletteResults.append(el("p","muted","Inga träffar."));
}
async function openPalette() {
  paletteInput.value=""; $("#command-palette-error").hidden=true; paletteResults.replaceChildren(); palette.showModal(); paletteInput.focus();
  try { paletteGuides=await api("/api/guides"); renderPalette(); } catch (failure) { showError(failure,$("#command-palette-error")); }
}
paletteInput.addEventListener("input",renderPalette);
paletteInput.addEventListener("keydown",event => {
  if (event.key==="ArrowDown") { event.preventDefault(); paletteResults.querySelector("button")?.focus(); }
  if (event.key==="Enter") { event.preventDefault(); paletteResults.querySelector("button")?.click(); }
});
document.addEventListener("keydown",event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase()==="k") { event.preventDefault(); if (!palette.open) openPalette(); }
});
$(".toolbar").append(action("Snabbsök Ctrl+K","secondary",openPalette));
async function openGuide(id) {
  if (!guidesDialog.open) guidesDialog.showModal(); await showGuides();
  const guide=loadedGuides.find(record => record.id===id);
  if (!guide) throw new Error("Guiden finns inte längre.");
  const index=loadedGuides.indexOf(guide);
  $("#guides-body").querySelectorAll("section")[index]?.scrollIntoView({block:"start"});
}
async function goToResource(kind,id) {
  if (kind==="item") { const item=items.find(record=>record.id===id); if (!item) throw new Error("Posten finns inte längre."); showDetail(item); }
  if (kind==="guide") await openGuide(id);
  if (kind==="server") { const server=serverRegistry.find(record=>record.id===id); if (!server) throw new Error("Servern finns inte längre."); await showServer(server); }
  if (kind==="project") {
    if (!projects.some(record=>record.id===id)) throw new Error("Projektet finns inte längre.");
    active="all"; $("#filter-project").value=String(id); $("#search").value=""; $("#filter-tags").value="";
    $("#filter-os").value=""; $("#filter-language").value=""; $("#filter-status").value="";
    $("#filter-attachments").checked=false; personalFilter.checked=false; reviewFilter.checked=false;
    serverFilter.value=""; troubleshootingFilter.checked=false; render();
  }
}
async function openDeepLink() {
  const match=/^#(item|guide|project|server)=(\d+)$/.exec(location.hash);
  if (!match) return;
  try { await goToResource(match[1],Number(match[2])); } catch (failure) { showError(failure); }
}
window.addEventListener("hashchange",()=>{ if (currentUser) openDeepLink(); });

function inlineMarkdown(container,text) {
  const pattern=/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let position=0;
  for (const match of text.matchAll(pattern)) {
    container.append(document.createTextNode(text.slice(position,match.index)));
    const value=match[0]; let node;
    if (value.startsWith("`")) node=el("code","",value.slice(1,-1));
    else if (value.startsWith("**")) node=el("strong","",value.slice(2,-2));
    else if (value.startsWith("*")) node=el("em","",value.slice(1,-1));
    else {
      const link=/^\[([^\]]+)\]\(([^)]+)\)$/.exec(value);
      try {
        const url=new URL(link[2]);
        if (!["http:","https:"].includes(url.protocol) || url.username || url.password) throw new Error("Unsafe");
        node=el("a","",link[1]); node.href=url.href; node.target="_blank"; node.rel="noopener noreferrer";
      } catch { node=document.createTextNode(value); }
    }
    container.append(node); position=match.index+value.length;
  }
  container.append(document.createTextNode(text.slice(position)));
}
function renderMarkdown(text) {
  const body=el("section","markdown-view"); const lines=text.split("\n");
  if (lines.length > 5000) {
    body.append(el("p","error","Markdown har fler än 5000 rader och visas därför som originaltext."),
      el("pre","detail-code",text));
    return body;
  }
  let code=null, list=null, codeLines=[];
  for (let index=0;index<lines.length;index+=1) {
    const line=lines[index];
    if (/^\s*```/.test(line)) {
      if (code) { code.textContent=codeLines.join("\n"); body.append(code); code=null; codeLines=[]; }
      else { code=el("pre","detail-code"); list=null; }
      continue;
    }
    if (code) { codeLines.push(line); continue; }
    if (line.includes("|") && index+1<lines.length && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index+1])) {
      const table=el("table"); const split=value=>value.trim().replace(/^\||\|$/g,"").split("|").map(cell=>cell.trim());
      const header=el("tr"); split(line).forEach(cell=>{ const th=el("th"); inlineMarkdown(th,cell); header.append(th); }); table.append(header); index+=2;
      while (index<lines.length && lines[index].includes("|") && lines[index].trim()) {
        const row=el("tr"); split(lines[index]).forEach(cell=>{ const td=el("td"); inlineMarkdown(td,cell); row.append(td); }); table.append(row); index+=1;
      }
      index-=1; body.append(table); list=null; continue;
    }
    const heading=/^(#{1,6})\s+(.+)$/.exec(line), bullet=/^\s*(?:[-*]|\d+\.)\s+(.+)$/.exec(line);
    if (heading) { const node=el("h"+heading[1].length); inlineMarkdown(node,heading[2]); body.append(node); list=null; }
    else if (bullet) {
      const type=/^\s*\d+\./.test(line) ? "ol" : "ul";
      if (!list || list.tagName.toLowerCase()!==type) { list=el(type); body.append(list); }
      const node=el("li"); inlineMarkdown(node,bullet[1]); list.append(node);
    } else {
      list=null; if (!line.trim()) continue;
      const node=el("p"); inlineMarkdown(node,line); body.append(node);
    }
  }
  if (code) { code.textContent=codeLines.join("\n"); body.append(code); }
  return body;
}

const storageDialog=makeDialog("storage","Lagringsöversikt");
async function showStorage() {
  $("#storage-error").hidden=true; $("#storage-body").replaceChildren();
  try {
    const state=await api("/api/storage"); const body=$("#storage-body");
    body.append(el("p","",`Databas: ${formatSize(state.database_bytes)} · WAL: ${formatSize(state.wal_bytes)} · Bilagor: ${formatSize(state.attachment_bytes)} (${state.attachment_count})`),
      el("p","muted","Bilagor ingår redan i databasstorleken. Papperskorgens filer räknas också. WAL är ändringar som ännu inte skrivits in i databasfilen."));
    const backups=state.backups, files=backups.files, external=backups.external;
    body.append(el("h3","","Backuper"),
      el("p","",`${files.length} lokala kopior · ${formatSize(files.reduce((total,file)=>total+file.size,0))} · Daglig backup ${backups.enabled ? "aktiverad" : "avstängd"}`));
    if (files.length) {
      const latest=[...files].sort((left,right)=>right.created.localeCompare(left.created))[0];
      body.append(el("p","",`Senaste lokala: ${latest.name} · ${formatDate(latest.created)}`));
    }
    if (backups.last_error) body.append(el("p","error",backups.last_error));
    body.append(el("p","",external.enabled ? `Extern backup: ${external.directory} · Senast kopierad: ${external.last_success || "aldrig"}` : "Extern backup är inte konfigurerad."));
    if (external.last_error) body.append(el("p","error",external.last_error));
    body.append(el("h3","","Största bilagorna"));
    state.largest.forEach(item=>body.append(el("p","",`${item.title} · ${item.filename} · ${formatSize(item.bytes)}${item.deleted_at ? " · Papperskorg" : ""}`)));
  } catch (failure) { showError(failure,$("#storage-error")); }
}
const storageButton=action("Lagringsöversikt","secondary",()=>{storageDialog.showModal();showStorage();});
$("#admin-dialog").append(storageButton);
const linkToggle=document.createElement("input"); linkToggle.type="checkbox"; linkToggle.id="link-check-toggle";
const linkSettings=el("section","admin-section"); const toggleLabel=labeled("Tillåt manuell kontroll av publika webblänkar",linkToggle); toggleLabel.className="checkbox";
linkSettings.append(el("h3","","Valfri länkkontroll"),toggleLabel,
  el("p","muted","Endast HTTP/HTTPS till publika IP-adresser, port 80/443. Redirects kontrolleras och DNS-resultat låses per anslutning. Ingen kontroll av dina interna VPN-adresser."),
  action("Spara länkkontroll","secondary",async ()=>{
    try { await api("/api/settings","PUT",{link_check_enabled:linkToggle.checked});notify("Inställningen sparades."); }
    catch(failure){showError(failure,$("#admin-error"));}
  }));
$("#admin-dialog").append(linkSettings);
$("#admin-button").addEventListener("click",async ()=>{
  try{ const state=await api("/api/settings");linkToggle.checked=state.link_check_enabled; }catch(failure){showError(failure,$("#admin-error"));}
});

const bookmarksDialog=makeDialog("bookmarks-import","Importera webbläsarbokmärken");
const bookmarkFile=document.createElement("input"); bookmarkFile.type="file"; bookmarkFile.accept=".html,.htm,text/html";
const bookmarkPreview=el("div"); const bookmarkCategory=document.createElement("select");
const importBookmarksButton=action("Importera valda (högst 50)","primary",async ()=>{
  importBookmarksButton.disabled=true;$("#bookmarks-import-error").hidden=true;
  try {
    const selected=[...bookmarkPreview.querySelectorAll("article")].filter(row=>row.querySelector("input[type=checkbox]").checked);
    if (!selected.length || selected.length>50) throw new Error("Välj 1–50 bokmärken. Upprepa för fler.");
    const payload=selected.map(row=>({...importCandidates[Number(row.dataset.index)],title:row.querySelector("input[type=text]").value,category:bookmarkCategory.value}));
    const result=await api("/api/batch/import","POST",{items:payload,allow_duplicates:false});
    bookmarksDialog.close();await load();notify(`${result.added} bokmärken sparade, ${result.skipped} dubbletter hoppades över.`);
  }catch(failure){showError(failure,$("#bookmarks-import-error"));}
  finally{importBookmarksButton.disabled=false;}
}); importBookmarksButton.disabled=true;
$("#bookmarks-import-body").append(el("p","muted","Exportera bokmärken som HTML från din webbläsare. Endast HTTP/HTTPS-länkar tas med. Förhandsvisningen kör aldrig filens HTML."),
  labeled("Bokmärkesfil (UTF-8, högst 2 MB)",bookmarkFile),labeled("Kategori",bookmarkCategory),bookmarkPreview,importBookmarksButton);
bookmarkFile.addEventListener("change",async ()=>{
  const revision=++bookmarkRevision;
  bookmarkPreview.replaceChildren();importCandidates=[];importBookmarksButton.disabled=true;$("#bookmarks-import-error").hidden=true;
  const file=bookmarkFile.files[0];if(!file)return;
  bookmarkFile.disabled=true;
  try {
    if(file.size>2*1024*1024)throw new Error("Högst 2 MB.");
    const html=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());
    if (revision !== bookmarkRevision || !bookmarksDialog.open) return;
    const result=await api("/api/bookmarks/preview","POST",{html});
    if (revision !== bookmarkRevision || !bookmarksDialog.open) return;
    importCandidates=result.items;
    bookmarkPreview.append(el("p","muted",`${result.items.length} länkar. ${result.skipped} osäkra/ogiltiga länkar utelämnade. Första 50 är valda.`));
    result.items.forEach((item,index)=>{
      const row=el("article","account-form");row.dataset.index=index;
      const check=document.createElement("input");check.type="checkbox";check.checked=index<50;
      const title=document.createElement("input");title.type="text";title.value=item.title;title.maxLength=200;
      const label=labeled("Importera",check);label.className="checkbox";
      row.append(label,labeled("Titel",title),el("p","detail-notes",item.content));bookmarkPreview.append(row);
    });
    importBookmarksButton.disabled=result.items.length===0;
  }catch(failure){if(revision===bookmarkRevision && bookmarksDialog.open)showError(failure,$("#bookmarks-import-error"));}
  finally{bookmarkFile.disabled=false;}
});
bookmarksDialog.addEventListener("close",()=>{bookmarkRevision+=1;});
const bookmarkImportButton=action("Importera bokmärken","secondary",()=>{
  if(!canEdit()){showError(new Error("Redigerarbehörighet krävs."));return;}
  bookmarkFile.value="";bookmarkPreview.replaceChildren();importCandidates=[];importBookmarksButton.disabled=true;
  $("#bookmarks-import-error").hidden=true;
  bookmarkCategory.replaceChildren(...categories.slice(2).map(category=>option(category[0],categoryName(category[0]))));
  bookmarkCategory.value="lankar";bookmarksDialog.showModal();
});
$(".toolbar").append(bookmarkImportButton);
const directoryInput=document.createElement("input");directoryInput.type="file";directoryInput.multiple=true;
directoryInput.setAttribute("webkitdirectory","");directoryInput.hidden=true;$("#batch-dialog").append(directoryInput);
const directoryButton=action("Välj mapp med filer","secondary",()=>directoryInput.click());
$("#drop-zone").before(directoryButton,el("p","muted","Mappimport använder samma förhandsvisning, kategori, UTF-8- och storleksgränser som Flera filer. Högst 50 filer/20 MB; välj en mindre mapp vid behov."));
directoryInput.addEventListener("change",()=>{previewFiles([...directoryInput.files]);directoryInput.value="";});

const installDialog=makeDialog("install-app","Installera som app");
const installButton=action("Installera app","secondary",()=>{
  $("#install-app-body").replaceChildren(el("p","muted",deferredInstall ?
    "Installera Prylbanken som en genvägsapp. Inget bibliotek eller inloggningsinnehåll sparas i offline-cache." :
    "Använd webbläsarens meny → Installera app / Lägg till på hemskärmen. På iPhone: Safari → Dela → Lägg till på hemskärmen. HTTPS (eller localhost) krävs; webbläsarstöd varierar. Appen kräver nät/VPN och har ingen offline-cache."));
  if(deferredInstall)$("#install-app-body").append(action("Installera nu","primary",async ()=>{
    const prompt=deferredInstall;deferredInstall=null;
    try{await prompt.prompt();const choice=await prompt.userChoice;notify(choice.outcome==="accepted"?"Appinstallationen accepterades.":"Appinstallationen avbröts.");}
    catch(failure){showError(failure,$("#install-app-error"));}
  }));
  $("#install-app-error").hidden=true;installDialog.showModal();
});
$(".toolbar").append(installButton);
window.addEventListener("beforeinstallprompt",event=>{event.preventDefault();deferredInstall=event;});
window.addEventListener("appinstalled",()=>{deferredInstall=null;notify("Prylbanken installerades som app.");});
if("serviceWorker" in navigator && window.isSecureContext){
  navigator.serviceWorker.register("/service-worker.js").catch(failure=>showError(new Error("Appstödet kunde inte registreras: "+failure.message)));
}
boot();
