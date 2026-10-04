"use strict";
const $ = (selector) => document.querySelector(selector);
const categories = [
  ["all", "Allt innehåll", "▦"], ["favorites", "Favoriter", "☆"],
  ["lankar", "Länkar", "↗"], ["kod", "Kodsnuttar", "⌘"],
  ["docker", "Docker", "▣"], ["spelserver", "Spelservrar", "◈"],
  ["steamcmd", "SteamCMD", "›_"], ["bat", "BAT & skript", "▤"],
  ["linux", "Linux", "›_"], ["windows", "Windows", "⊞"],
  ["natverk", "Nätverk", "⇄"], ["databaser", "Databaser & SQL", "▥"],
  ["utveckling", "Utveckling", "{ }"], ["automation", "Automation", "⚙"],
  ["sakerhet", "IT-säkerhet", "◇"], ["dokumentation", "Guider & anteckningar", "▧"],
  ["filer", "Filer", "↥"]
];
let items = [], active = "all", editing = null, detailItem = null, loading = true;
let toastTimer;
const form = $("#edit-form");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function notify(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 3500);
}
function showError(error, target = $("#error")) {
  target.textContent = error.message;
  target.hidden = false;
}
async function api(path, method = "GET", body) {
  const response = await fetch(path, {
    method, headers: body === undefined ? {} : {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error("Inloggningen har gått ut. Ladda om sidan och logga in igen.");
    const result = await response.json();
    throw new Error(result.error || `Serverfel (${response.status}).`);
  }
  return response.json();
}
async function load() {
  $("#error").hidden = true;
  try {
    items = await api("/api/items");
    items.forEach(item => {
      if (!categories.some(c => c[0] === item.category)) categories.push([item.category, item.category, "▧"]);
    });
    loading = false; render();
  }
  catch (error) { showError(error); }
}
function filtered() {
  const query = $("#search").value.toLocaleLowerCase("sv");
  return items.filter(item =>
    (active === "all" || (active === "favorites" ? item.favorite : active === "filer" ? item.filename !== null || item.category === "filer" : item.category === active)) &&
    [item.title, item.content, item.notes, item.tags, item.filename || ""].join(" ").toLocaleLowerCase("sv").includes(query)
  ).sort((a, b) => {
    if ($("#sort").value === "title") return a.title.localeCompare(b.title, "sv");
    const order = a.updated.localeCompare(b.updated) || a.id - b.id;
    return $("#sort").value === "old" ? order : b.favorite - a.favorite || -order;
  });
}
function count(key) {
  if (key === "all") return items.length;
  if (key === "favorites") return items.filter(i => i.favorite).length;
  return items.filter(i => key === "filer" ? i.filename !== null || i.category === "filer" : i.category === key).length;
}
function action(label, className, handler) {
  const button = el("button", className, label);
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}
function render() {
  $("#navigation").replaceChildren();
  categories.forEach(([key, name, icon], index) => {
    if (index === 2) $("#navigation").append(el("div", "nav-divider"));
    const button = action("", `nav-button${active === key ? " active" : ""}`, () => {
      active = key; render();
    });
    button.setAttribute("aria-current", active === key ? "page" : "false");
    button.append(el("span", "nav-icon", icon), el("span", "", name), el("span", "nav-count", count(key)));
    $("#navigation").append(button);
  });
  const name = categories.find(c => c[0] === active)[1];
  $("#breadcrumb").textContent = name;
  $("#collection-title").textContent = name;
  $("#total").textContent = items.length;
  $("#commands").textContent = items.filter(i => i.content && !["lankar", "dokumentation", "filer"].includes(i.category)).length;
  $("#favorites").textContent = count("favorites");
  $("#files").textContent = items.filter(i => i.filename !== null).length;
  const visible = filtered();
  $("#result-count").textContent = `${visible.length} ${visible.length === 1 ? "sak" : "saker"}`;
  $("#cards").replaceChildren(...visible.map(card));
  $("#empty").hidden = loading || visible.length > 0;
  const first = items.length === 0;
  $("#empty-title").textContent = first ? "Här börjar din samling." : "Inga träffar den här gången.";
  $("#empty-text").textContent = first ? "Spara din första länk, kodsnutt eller fil – och slipp leta nästa gång." : "Prova en annan sökning eller lägg till något i den här kategorin.";
  $("#examples-button").hidden = !first;
}
function fileLink(item) {
  const link = el("a", "file-link", `↓ ${item.filename} · ${formatSize(item.filesize)}`);
  link.href = `/api/files/${item.id}`;
  link.setAttribute("download", item.filename);
  return link;
}
function formatSize(size) {
  return size >= 1048576 ? `${(size / 1048576).toFixed(1)} MB` : `${Math.ceil(size / 1024)} kB`;
}
function card(item) {
  const node = el("article", "card");
  const top = el("div", "card-top");
  const favorite = action(item.favorite ? "★" : "☆", `icon-button${item.favorite ? " selected" : ""}`, async () => {
    favorite.disabled = true;
    try { await api(`/api/items/${item.id}`, "PUT", {...item, favorite: !item.favorite}); await load(); }
    catch (error) { showError(error); }
    finally { favorite.disabled = false; }
  });
  favorite.setAttribute("aria-label", item.favorite ? "Ta bort favorit" : "Markera som favorit");
  favorite.setAttribute("aria-pressed", String(Boolean(item.favorite)));
  top.append(el("span", `category-badge ${item.category}`, categoryName(item.category)), favorite);
  const title = el("h3");
  title.append(action(item.title, "title-button", () => showDetail(item)));
  node.append(top, title);
  if (item.content) node.append(el("pre", "preview", item.content));
  if (item.notes) node.append(el("p", "card-notes", item.notes));
  if (item.filename !== null) node.append(fileLink(item));
  const tags = el("div", "tags");
  item.tags.split(",").map(t => t.trim()).filter(Boolean).slice(0, 5).forEach(tag => tags.append(el("span", "tag", `#${tag}`)));
  const bottom = el("div", "card-bottom");
  const date = new Date(item.updated.replace(" ", "T") + "Z");
  bottom.append(el("span", "", date.toLocaleDateString("sv-SE")));
  const actions = el("div", "card-actions");
  if (item.category === "lankar") {
    const link = el("a", "small-button", "Öppna ↗");
    link.href = item.content; link.target = "_blank"; link.rel = "noopener noreferrer";
    actions.append(link);
  } else if (item.content) {
    actions.append(action("Kopiera", "small-button", () => copy(item.content)));
    actions.append(action("↓ Text", "small-button", () => downloadText(item)));
  }
  actions.append(action("Redigera", "small-button", () => openEditor(item)));
  const remove = action("×", "small-button delete-button", async () => {
    if (!confirm(`Ta bort "${item.title}" och eventuell bifogad fil? Detta kan inte ångras.`)) return;
    remove.disabled = true;
    try { await api(`/api/items/${item.id}`, "DELETE"); await load(); notify("Posten är borttagen."); }
    catch (error) { showError(error); }
    finally { remove.disabled = false; }
  });
  remove.setAttribute("aria-label", `Ta bort ${item.title}`);
  actions.append(remove); bottom.append(actions); node.append(tags, bottom);
  return node;
}
async function copy(text) {
  try {
    if (!navigator.clipboard || !window.isSecureContext) {
      throw new Error("Direktkopiering kräver HTTPS eller localhost. Öppna posten och kopiera texten manuellt.");
    }
    await navigator.clipboard.writeText(text); notify("Kopierat till urklipp.");
  } catch (error) { showError(error); }
}
function openEditor(item = null) {
  editing = item;
  form.reset();
  populateCategories();
  $("#form-error").hidden = true;
  $("#editor-title").textContent = item ? "Redigera sparad sak" : "Lägg till nytt";
  ["title", "category", "content", "notes", "tags"].forEach(name => {
    form.elements[name].value = item ? item[name] : name === "category" ? (["all", "favorites"].includes(active) ? "kod" : active) : "";
  });
  form.elements.favorite.checked = Boolean(item?.favorite);
  $("#existing-file").textContent = item?.filename !== null && item?.filename !== undefined ? `Bifogad: ${item.filename}. Välj en ny fil för att ersätta den.` : "";
  updateCategory(); $("#editor").showModal();
}
function updateCategory() {
  const custom = form.elements.category.value === "__custom";
  $("#custom-category-label").hidden = !custom;
  $("#custom-category").required = custom;
  const link = form.elements.category.value === "lankar";
  $("#content-caption").textContent = link ? "Webbadress (http:// eller https://)" : "Kod, kommando eller text";
  form.elements.content.placeholder = link ? "https://…" : "Klistra in det du vill spara…";
  form.elements.content.required = link;
}
function showDetail(item) {
  detailItem = item;
  $("#detail-title").textContent = item.title;
  $("#detail-category").textContent = categoryName(item.category);
  const body = $("#detail-body");
  body.replaceChildren();
  if (item.content) {
    body.append(el("pre", "detail-code", item.content));
    body.append(action("Kopiera innehåll", "secondary", () => copy(item.content)));
    body.append(action("↓ Ladda ned text", "secondary", () => downloadText(item)));
  }
  if (item.notes) body.append(el("p", "detail-notes", item.notes));
  if (item.filename !== null) body.append(fileLink(item));
  $("#detail").showModal();
}
function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(new Error("Filen kunde inte läsas."));
    reader.readAsDataURL(file);
  });
}
form.addEventListener("submit", async event => {
  event.preventDefault();
  $("#form-error").hidden = true;
  $("#save-button").disabled = true;
  try {
    const payload = Object.fromEntries(["title", "category", "content", "notes", "tags"].map(name => [name, form.elements[name].value]));
    if (payload.category === "__custom") payload.category = $("#custom-category").value.trim();
    payload.favorite = form.elements.favorite.checked;
    const file = $("#attachment").files[0];
    if (file) {
      if (file.size > 20 * 1024 * 1024) throw new Error("Filen får vara högst 20 MB.");
      payload.filename = file.name; payload.filedata = await readFile(file);
    }
    await api(editing ? `/api/items/${editing.id}` : "/api/items", editing ? "PUT" : "POST", payload);
    $("#editor").close(); await load(); notify("Sparat i din samling.");
  } catch (error) { showError(error, $("#form-error")); }
  finally { $("#save-button").disabled = false; }
});
function categoryName(key) { return categories.find(c => c[0] === key)?.[1] || key; }
function populateCategories() {
  $("#category-input").replaceChildren();
  [...categories.slice(2), ["__custom", "＋ Egen kategori"]].forEach(([value, label]) => {
    const option = el("option", "", label); option.value = value; $("#category-input").append(option);
  });
}
function downloadText(item) {
  const extensions = {bat: ".bat", linux: ".sh", databaser: ".sql", docker: ".txt"};
  const safe = item.title.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").slice(0, 120).replace(/[. ]+$/, "") || "kod";
  const filename = /\.[a-z0-9]{1,8}$/i.test(safe) ? safe : safe + (extensions[item.category] || ".txt");
  const url = URL.createObjectURL(new Blob([item.content], {type:"text/plain;charset=utf-8"}));
  const link = el("a"); link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("#code-file").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  $("#form-error").hidden = true;
  $("#save-button").disabled = true;
  try {
    if (file.size > 200000) throw new Error("Kodfiler får vara högst 200 kB. Bifoga större filer i stället.");
    const text = new TextDecoder("utf-8", {fatal:true}).decode(await file.arrayBuffer());
    if (text.includes("\0")) throw new Error("Filen verkar vara binär. Bifoga den i stället.");
    if (form.elements.content.value && !confirm("Ersätta nuvarande kodtext med filens innehåll?")) return;
    form.elements.content.value = text;
    if (!form.elements.title.value) form.elements.title.value = file.name.slice(0,200);
  } catch (error) {
    showError(new Error(error instanceof TypeError ? "Filen måste vara en UTF-8-textfil. Bifoga andra filer i stället." : error.message), $("#form-error"));
  } finally { $("#save-button").disabled = false; event.target.value = ""; }
});
$("#add-button").addEventListener("click", () => openEditor());
$("#first-button").addEventListener("click", () => openEditor());
document.querySelectorAll(".close-detail").forEach(button => button.addEventListener("click", () => $("#detail").close()));
document.querySelectorAll(".close-dialog").forEach(button => button.addEventListener("click", () => $("#editor").close()));
$("#detail-edit").addEventListener("click", () => { $("#detail").close(); openEditor(detailItem); });
$("#category-input").addEventListener("change", updateCategory);
$("#search").addEventListener("input", render);
$("#sort").addEventListener("change", render);
document.addEventListener("keydown", event => {
  if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && !document.querySelector("dialog[open]")) {
    event.preventDefault(); $("#search").focus();
  }
});
$("#export-button").addEventListener("click", async () => {
  try {
    const backup = await api("/api/backup");
    const url = URL.createObjectURL(new Blob([JSON.stringify(backup)], {type: "application/json"}));
    const link = el("a"); link.href = url; link.download = `prylbanken-${new Date().toISOString().slice(0,10)}.json`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify("Säkerhetskopian har exporterats.");
  } catch (error) { showError(error); }
});
$("#import-button").addEventListener("click", () => $("#import-file").click());
$("#import-file").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  $("#import-button").disabled = true;
  try {
    if (file.size > 29 * 1024 * 1024) throw new Error("Importfilen får vara högst 29 MB. Återställ större samlingar från Docker-volymen.");
    const backup = JSON.parse(await file.text());
    if (!confirm("Importen lägger till poster utan att radera befintligt innehåll. Dubbletter kan skapas. Fortsätta?")) return;
    const result = await api("/api/restore", "POST", backup); await load(); notify(result.message);
  } catch (error) { showError(error); }
  finally { event.target.value = ""; $("#import-button").disabled = false; }
});
const examples = [
  {title:"Docker Compose – start & loggar", category:"docker", content:"docker compose up -d\ndocker compose logs -f --tail=100\ndocker compose ps", notes:"Kör i mappen där din compose.yaml ligger.", tags:"docker, compose", favorite:true},
  {title:"SteamCMD – installera Valheim", category:"steamcmd", content:"steamcmd +force_install_dir ./valheim-server +login anonymous +app_update 896660 validate +quit", notes:"Byt installationsmapp efter behov. SteamCMD måste vara installerat.", tags:"valheim, installation"},
  {title:"Valheim – startskript för Windows", category:"bat", content:'@echo off\nset SteamAppId=892970\nvalheim_server.exe -nographics -batchmode -name "Min server" -port 2456 -world "MinVarld" -password "BYT_MIG" -public 0\npause', notes:"Exempel: byt namn, värld och lösenord. Spara som start-server.bat i servermappen. Kör inte okända skript utan att läsa dem.", tags:"valheim, windows, bat"},
  {title:"Docker – dokumentation", category:"lankar", content:"https://docs.docker.com/", notes:"Referens för Docker, Compose och containrar.", tags:"dokumentation"},
  {title:"Minecraft Java – startkommando", category:"spelserver", content:"java -Xms2G -Xmx4G -jar server.jar nogui", notes:"Kräver kompatibel Java-version och server.jar. Läs och godkänn Mojangs EULA före användning.", tags:"minecraft, java"}
];
$("#examples-button").addEventListener("click", async () => {
  $("#examples-button").disabled = true;
  try { await api("/api/restore", "POST", {version:1, items:examples}); await load(); notify("Fem exempel har lagts till. Anpassa dem till din server."); }
  catch (error) { showError(error); }
  finally { $("#examples-button").disabled = false; }
});
load();
