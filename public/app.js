"use strict";
const $ = (selector) => document.querySelector(selector);
const builtInCategories = [
  ["all", "Allt innehåll", "▦"], ["favorites", "Gemensamma favoriter", "☆"],
  ["lankar", "Länkar", "↗"], ["kod", "Kodsnuttar", "⌘"],
  ["docker", "Docker", "▣"], ["spelserver", "Spelservrar", "◈"],
  ["steamcmd", "SteamCMD", "›_"], ["bat", "BAT & skript", "▤"],
  ["linux", "Linux", "›_"], ["windows", "Windows", "⊞"],
  ["natverk", "Nätverk", "⇄"], ["databaser", "Databaser & SQL", "▥"],
  ["utveckling", "Utveckling", "{ }"], ["automation", "Automation", "⚙"],
  ["sakerhet", "IT-säkerhet", "◇"], ["dokumentation", "Guider & anteckningar", "▧"],
  ["filer", "Filer", "↥"], ["proxmox", "Proxmox VE", "▣"]
];
let categories = [...builtInCategories], items = [], active = "all", editing = null, detailItem = null, loading = true;
let currentHistoryItem = null, currentHistory = [], currentUser = null;
const roleName = role => ({admin:"Administratör", editor:"Redigerare", reader:"Läsare"})[role] || role;
const canEdit = () => currentUser && currentUser.role !== "reader";
const isAdmin = () => currentUser?.role === "admin";
let toastTimer;
let csrf = "";
const form = $("#edit-form");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function formatDate(value) {
  const date = new Date(String(value || "").replace(" ", "T") + (/(?:Z|[+-]\d{2}:\d{2})$/.test(String(value || "")) ? "" : "Z"));
  return Number.isNaN(date.getTime()) ? value || "Okänt datum" : date.toLocaleString("sv-SE");
}
function openHistory(item = detailItem) {
  if (!item) return;
  currentHistoryItem = item;
  $("#history-error").hidden = true;
  $("#history-list").replaceChildren();
  $("#history-preview").replaceChildren();
  $("#history-dialog").showModal();
  loadHistory();
}
async function loadHistory() {
  $("#history-error").hidden = true;
  try {
    currentHistory = await api(`/api/items/${currentHistoryItem.id}/history`);
    if (!currentHistory.length) {
      $("#history-list").append(el("p", "muted", "Det finns inga tidigare versioner."));
      return;
    }
    currentHistory.forEach(snapshot => {
      const row = el("article", "history-row");
      const info = el("div", "history-info");
      info.append(el("strong", "", snapshot.title || "Namnlös version"),
        el("small", "muted", `${formatDate(snapshot.created)} · ${snapshot.actor || "Okänd användare"}`));
      const preview = action("Visa", "small-button", () => {
        $("#history-preview").replaceChildren(
          el("h3", "", snapshot.title || "Namnlös version"),
          codeBlock(snapshot.content || "", snapshot.language || "plain", true, "detail-code"),
          action("Kopiera version", "secondary", () => copy(snapshot.content || "", snapshot)),
          action("Återställ den här versionen", "primary", async () => {
            if (!confirm(`Återställa versionen "${snapshot.title || "Namnlös version"}" från ${formatDate(snapshot.created)}? Nuvarande innehåll blir en version i historiken.`)) return;
            preview.disabled = true;
            try {
              await api(`/api/items/${currentHistoryItem.id}/history/${snapshot.id}/restore`, "POST", {});
              await load();
              detailItem = items.find(entry => entry.id === currentHistoryItem.id) || null;
              if (detailItem) showDetail(detailItem);
              $("#history-dialog").close();
              notify("Versionen har återställts.");
            } catch (error) { showError(error, $("#history-error")); }
            finally { preview.disabled = false; }
          })
        );
        $("#history-preview .primary").hidden = !canEdit();
      });
      row.append(info, preview);
      $("#history-list").append(row);
    });
    appendHistoryComparison();
  } catch (error) { showError(error, $("#history-error")); }
}
async function loadTrash() {
  $("#trash-error").hidden = true;
  $("#trash-list").replaceChildren();
  try {
    const deleted = await api("/api/trash");
    if (!deleted.length) {
      $("#trash-list").append(el("p", "muted", "Papperskorgen är tom."));
      return;
    }
    deleted.forEach(item => {
      const row = el("article", "management-row");
      const info = el("div", "management-info");
      info.append(el("strong", "", item.title), el("small", "muted", `${categoryName(item.category)} · ${formatDate(item.deleted_at || item.updated)}`));
      const restore = action("Återställ", "secondary", async () => {
        restore.disabled = true; permanent.disabled = true;
        try { await api(`/api/items/${item.id}/restore`, "POST", {}); await load(); await loadTrash(); notify("Posten har återställts."); }
        catch (error) { showError(error, $("#trash-error")); }
        finally { restore.disabled = false; permanent.disabled = false; }
      });
      const permanent = action("Radera permanent", "danger-button", async () => {
        if (!confirm(`Radera "${item.title}" permanent, inklusive eventuell bifogad fil? Detta går inte att ångra.`)) return;
        restore.disabled = true; permanent.disabled = true;
        try { await api(`/api/trash/${item.id}`, "DELETE"); await loadTrash(); notify("Posten har raderats permanent."); }
        catch (error) { showError(error, $("#trash-error")); }
        finally { restore.disabled = false; permanent.disabled = false; }
      });
      row.append(info, restore, permanent);
      restore.hidden = !canEdit();
      permanent.hidden = !isAdmin();
      $("#trash-list").append(row);
    });
  } catch (error) { showError(error, $("#trash-error")); }
}
function categoryDescendants(key) {
  const result = new Set([key]);
  let changed = true;
  while (changed) {
    changed = false;
    categories.forEach(category => {
      if (category[3] && result.has(category[3]) && !result.has(category[0])) {
        result.add(category[0]); changed = true;
      }
    });
  }
  return result;
}
function fillParentSelect(select, selected = "", exclude = new Set()) {
  select.replaceChildren();
  select.append(el("option", "", "Ingen (rot)"));
  select.firstElementChild.value = "";
  categories.slice(2).filter(category => !exclude.has(category[0])).forEach(category => {
    const option = el("option", "", categoryName(category[0]));
    option.value = category[0]; select.append(option);
  });
  select.value = selected || "";
}
async function loadCategoriesForManagement() {
  $("#category-error").hidden = true;
  try {
  await load();
  const trash = await api("/api/trash");
  fillParentSelect($("#category-form").elements.parent);
  $("#category-list").replaceChildren();
  categories.slice(2).forEach(category => {
    const [key, name, , parent] = category;
    const row = el("article", "category-row");
    const builtin = builtInCategories.some(entry => entry[0] === key);
    const nameInput = document.createElement("input");
    nameInput.value = name; nameInput.maxLength = 60; nameInput.setAttribute("aria-label", `Namn för ${name}`);
    const parentSelect = document.createElement("select");
    parentSelect.setAttribute("aria-label", `Överordnad kategori för ${name}`);
    fillParentSelect(parentSelect, parent, categoryDescendants(key));
    const save = action("Spara", "secondary", async () => {
      if (!nameInput.value.trim()) { showError(new Error("Kategorin måste ha ett namn."), $("#category-error")); return; }
      save.disabled = true;
      try { await api(`/api/categories/${encodeURIComponent(key)}`, "PUT", {name:nameInput.value.trim(), parent:parentSelect.value || null}); await loadCategoriesForManagement(); notify("Kategorin har uppdaterats."); }
      catch (error) { showError(error, $("#category-error")); }
      finally { save.disabled = false; }
    });
    const moveTo = document.createElement("select");
    moveTo.setAttribute("aria-label", `Flytta innehåll från ${name} till`);
    const destinations = categories.slice(2).filter(entry => !categoryDescendants(key).has(entry[0]));
    destinations.forEach(entry => {
      const option = el("option", "", categoryName(entry[0]));
      option.value = entry[0]; moveTo.append(option);
    });
    moveTo.value = destinations.some(entry => entry[0] === "kod") ? "kod" : destinations[0][0];
    const hasItems = [...items, ...trash].some(item => item.category === key);
    if (!hasItems) {
      moveTo.replaceChildren(el("option", "", "Inget innehåll att flytta"));
      moveTo.firstElementChild.value = "";
      moveTo.disabled = true;
    }
    const hasChildren = categories.some(entry => entry[3] === key);
    const remove = action("Ta bort", "danger-button", async () => {
      if (hasChildren) {
        showError(new Error("Flytta eller ta först bort underkategorierna."), $("#category-error"));
        return;
      }
      const question = hasItems
        ? `Ta bort kategorin "${name}" och flytta dess innehåll till den valda kategorin?`
        : `Ta bort den tomma kategorin "${name}"?`;
      if (!confirm(question)) return;
      if (hasItems && !moveTo.value) {
        showError(new Error("Välj en kategori att flytta innehållet till."), $("#category-error"));
        return;
      }
      save.disabled = true; remove.disabled = true;
      try {
        await api(`/api/categories/${encodeURIComponent(key)}`, "DELETE", hasItems ? {move_to:moveTo.value} : {});
        await loadCategoriesForManagement(); notify("Kategorin har tagits bort.");
      }
      catch (error) { showError(error, $("#category-error")); }
      finally { save.disabled = false; remove.disabled = false; }
    });
    remove.disabled = builtin || hasChildren;
    if (builtin) remove.title = "Inbyggda kategorier kan byta namn och flyttas, men inte tas bort.";
    else if (hasChildren) remove.title = "Flytta eller ta först bort underkategorierna.";
    row.append(el("span", "category-row-label", categoryName(key)), nameInput, parentSelect, save,
      ...(hasItems ? [moveTo] : []), remove);
    $("#category-list").append(row);
  });
  } catch (error) { showError(error, $("#category-error")); }
}
async function loadActivity() {
  $("#activity-error").hidden = true;
  $("#activity-list").replaceChildren();
  try {
    const entries = await api("/api/activity");
    if (!entries.length) $("#activity-list").append(el("p", "muted", "Ingen aktivitet ännu."));
    entries.forEach(entry => {
      const row = el("article", "management-row activity-row");
      row.append(el("strong", "", activityName(entry.action)), el("span", "", entry.target || ""),
        el("small", "muted", `${entry.actor || "Okänd användare"} · ${formatDate(entry.created)}`));
      $("#activity-list").append(row);
    });
  } catch (error) { showError(error, $("#activity-error")); }
}
function activityName(action) {
  return ({
    "item.create": "Post skapad", "item.update": "Post ändrad", "item.trash": "Post till papperskorgen",
    "item.restore": "Post återställd", "item.restore-version": "Version återställd",
    "item.delete-permanently": "Post raderad permanent", "item.move-category": "Post flyttad",
    "items.import": "Bibliotek importerat", "examples.import": "Startmallar importerade",
    "category.create": "Kategori skapad", "category.update": "Kategori ändrad",
    "category.delete": "Kategori borttagen", "category.restore": "Kategori återställd",
    "user.create": "Konto skapat", "user.login": "Inloggning", "user.enable": "Konto aktiverat",
    "user.disable": "Konto inaktiverat", "user.reset-password": "Lösenord återställt",
    "user.password": "Lösenord ändrat", "user.role": "Roll ändrad", "settings.registration": "Registrering ändrad",
    "project.create": "Projekt skapat", "project.update": "Projekt ändrat", "project.delete": "Projekt borttaget",
    "backup.create": "Säkerhetskopia skapad", "database.restore": "Databas återställd"
  })[action] || action;
}
async function loadAdmin() {
  $("#admin-error").hidden = true;
  $("#backup-status").textContent = "Laddar status…";
  $("#backup-list").replaceChildren();
  try {
    const [settings, backups] = await Promise.all([api("/api/settings"), api("/api/backups")]);
    $("#registration-toggle").checked = Boolean(settings.registration_open);
    $("#backup-status").textContent = `${backups.enabled ? "Automatiska säkerhetskopior är aktiverade." : "Automatiska säkerhetskopior är avstängda."}${backups.last_error ? ` Senaste fel: ${backups.last_error}` : ""}`;
    const external = backups.external;
    if (external) $("#backup-status").textContent += external.enabled
      ? ` NAS: ${external.directory}. ${external.last_error ? `Fel: ${external.last_error}` :
        external.last_success ? `Verifierad kopia: ${formatDate(external.last_success)}` : "Ingen extern kopia verifierad ännu."}`
      : " Extern NAS-backup är inte konfigurerad.";
    if (!backups.files.length) $("#backup-list").append(el("p", "muted", "Inga säkerhetskopior tillgängliga."));
    backups.files.forEach(file => {
      const row = el("article", "management-row backup-row");
      const info = el("div", "management-info");
      info.append(el("strong", "", file.name), el("small", "muted", `${formatDate(file.created)} · ${formatSize(file.size)}`));
      const download = el("a", "small-button", "Ladda ned");
      download.href = `/api/backups/${encodeURIComponent(file.name)}`;
      download.setAttribute("download", file.name);
      const restore = action("Full återställning", "danger-button", async () => {
        const first = confirm(`Full återställning från "${file.name}" ersätter hela databasen: alla poster, konton, inställningar och historik blir som i säkerhetskopian. Servern skapar först en säkerhetskopia av nuläget. Du loggas ut efter återställningen. Fortsätta?`);
        if (!first || !confirm("Bekräfta en gång till: ersätt hela Prylbanken och logga ut?")) return;
        restore.disabled = true;
        try {
          await api(`/api/backups/${encodeURIComponent(file.name)}/restore`, "POST", {confirm:true});
          location.replace("/login");
        } catch (error) { showError(error, $("#admin-error")); }
        finally { restore.disabled = false; }
      });
      row.append(info, download, restore);
      $("#backup-list").append(row);
    });
  } catch (error) {
    $("#backup-status").textContent = "Säkerhetskopiestatus kunde inte hämtas.";
    showError(error, $("#admin-error"));
  }
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
    method, headers: {...(body === undefined ? {} : {"Content-Type": "application/json"}),
      ...(method === "GET" ? {} : {"X-CSRF-Token": csrf})},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    if (response.status === 401) {
      location.replace("/login");
      throw new Error("Inloggningen har gått ut. Logga in igen.");
    }
    const result = await response.json();
    throw new Error(result.error || `Serverfel (${response.status}).`);
  }
  return response.json();
}
async function load() {
  $("#error").hidden = true;
  try {
    const [loadedItems, loadedCategories, loadedProjects, loadedSearches, personal, servers, profiles, checks] = await Promise.all([
      api("/api/items"), api("/api/categories"), api("/api/projects"), api("/api/searches"), api("/api/personal"),
      api("/api/servers"), api("/api/profiles"), api("/api/link-checks")]);
    items = loadedItems;
    categories = builtInCategories.slice(0, 2);
    const categoryData = loadedCategories.filter(category => !["all", "favorites"].includes(category.key)).map(category => {
      const builtin = builtInCategories.find(entry => entry[0] === category.key);
      return [category.key, category.name, builtin?.[2] || "▧", category.parent || null];
    });
    categories.push(...categoryData);
    items.forEach(item => {
      if (!categories.some(c => c[0] === item.category)) categories.push([item.category, item.category, "▧"]);
    });
    if (!categories.some(category => category[0] === active)) active = "all";
    refreshLibraryTools(loadedProjects, loadedSearches);
    refreshPersonal(personal);
    refreshExpansion(servers, profiles, checks);
    loading = false; populateFilters(); render();
  }
  catch (error) { showError(error); }
}
function filtered() {
  const filters = currentFilters();
  const keys = filters.descendants ? categoryDescendants(active) : new Set([active]);
  return items.filter(item => LibraryTools.matches(item, filters, keys) && workbenchMatches(item) && expansionMatches(item)).sort((a, b) => {
    const pinOrder = Number(b.pinned) - Number(a.pinned);
    if (pinOrder) return pinOrder;
    if ($("#sort").value === "title") return a.title.localeCompare(b.title, "sv");
    const order = a.updated.localeCompare(b.updated) || a.id - b.id;
    return $("#sort").value === "old" ? order : b.favorite - a.favorite || -order;
  });
}
function count(key) {
  if (key === "all") return items.length;
  if (key === "favorites") return items.filter(i => i.favorite).length;
  const keys = $("#filter-descendants").checked ? categoryDescendants(key) : new Set([key]);
  return items.filter(i => key === "filer" ? i.filename !== null || i.category === "filer" : keys.has(i.category)).length;
}
function action(label, className, handler) {
  const button = el("button", className, label);
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}
const keywordSets = {
  bash: /\b(?:if|then|else|fi|for|while|do|done|case|esac|function|export|local|return|sudo|echo)\b/g,
  powershell: /\b(?:param|function|if|else|elseif|foreach|while|try|catch|return|Write-Host|Get-\w+|Set-\w+|New-\w+)\b/gi,
  bat: /\b(?:echo|set|if|else|for|in|do|call|goto|pause|exit|rem)\b/gi,
  yaml: /\b(?:true|false|null|yes|no)\b/gi,
  json: /\b(?:true|false|null)\b/g,
  python: /\b(?:and|as|assert|async|await|break|class|continue|def|del|elif|else|except|False|finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|pass|raise|return|True|try|while|with|yield)\b/g,
  javascript: /\b(?:async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|false|finally|for|function|if|import|in|instanceof|let|new|null|of|return|static|super|switch|this|throw|true|try|typeof|var|void|while|yield)\b/g,
  sql: /\b(?:select|from|where|and|or|not|null|insert|into|values|update|set|delete|create|alter|drop|table|join|left|right|inner|on|as|order|by|group|having|limit|primary|key|foreign|references|begin|commit|rollback)\b/gi
};
function codeBlock(text, language = "plain", lineNumbers = false, className = "code-block") {
  const pre = el("pre", className);
  const lines = String(text).split("\n");
  lines.forEach((line, index) => {
    const row = el("span", "code-line");
    if (lineNumbers) {
      const number = el("span", "line-number", String(index + 1));
      number.setAttribute("aria-hidden", "true");
      row.append(number);
    }
    const commentPattern = language === "sql" ? /--.*/ : language === "javascript" ? /\/\/.*/ :
      ["bash", "powershell", "python", "yaml"].includes(language) ? /#.*/ :
        language === "bat" ? /(?:^|\s)(?:rem\b|::).*/i : null;
    let cursor = 0;
    const appendTokenized = segment => {
      const combined = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b\d+(?:\.\d+)?\b)/g;
      const keywords = keywordSets[language];
      const tokens = [];
      if (keywords) {
        keywords.lastIndex = 0;
        let keyword;
        while ((keyword = keywords.exec(segment))) tokens.push({start: keyword.index, end: keyword.index + keyword[0].length, kind: "keyword"});
      }
      let match;
      while ((match = combined.exec(segment))) tokens.push({
        start: match.index, end: match.index + match[0].length,
        kind: /^\d/.test(match[0]) ? "number" : "string"
      });
      tokens.sort((a, b) => a.start - b.start || b.end - a.end);
      let position = 0;
      tokens.forEach(token => {
        if (token.start < position) return;
        if (token.start > position) row.append(document.createTextNode(segment.slice(position, token.start)));
        row.append(el("span", `syntax-${token.kind}`, segment.slice(token.start, token.end)));
        position = token.end;
      });
      row.append(document.createTextNode(segment.slice(position)));
    };
    if (commentPattern) {
      const comment = commentPattern.exec(line);
      if (comment) {
        cursor = comment.index;
        appendTokenized(line.slice(0, cursor));
        row.append(el("span", "syntax-comment", line.slice(cursor)));
      } else appendTokenized(line);
    } else appendTokenized(line);
    if (!line.length) row.append(document.createTextNode(" "));
    pre.append(row);
  });
  return pre;
}
function metadataSummary(item) {
  return [
    item.os && `OS: ${item.os}`,
    item.program_version && `Version: ${item.program_version}`,
    item.ports && `Portar: ${item.ports}`,
    item.dependencies && `Beroenden: ${item.dependencies}`,
    item.tested_at && `Testad: ${item.tested_at}`,
    item.status && `Status: ${statusName(item.status)}`,
    item.language && item.language !== "plain" && `Språk: ${item.language}`
  ].filter(Boolean).join(" · ");
}
function statusName(status) {
  return ({template:"Mall", tested:"Testad", "needs-update":"Behöver uppdateras"})[status] || status;
}
function categoryName(key, seen = new Set()) {
  const category = categories.find(entry => entry[0] === key);
  if (!category) return key;
  if (seen.has(key)) return category[1];
  seen.add(key);
  const parent = category[3] ? categoryName(category[3], seen) : "";
  return parent && !["Allt innehåll", "Favoriter"].includes(parent) ? `${parent} / ${category[1]}` : category[1];
}
function populateFilters() {
  const fill = (selector, values, firstLabel, labels = {}) => {
    const select = $(selector), value = select.value;
    select.replaceChildren(el("option", "", firstLabel));
    select.firstElementChild.value = "";
    [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "sv")).forEach(item => {
      const option = el("option", "", labels[item] || item); option.value = item; select.append(option);
    });
    select.value = values.includes(value) ? value : "";
  };
  fill("#filter-os", items.map(item => item.os), "Alla system");
  fill("#filter-language", items.map(item => item.language), "Alla språk");
}
function render() {
  $("#navigation").replaceChildren();
  categories.forEach(([key, name, icon], index) => {
    if (index === 2) $("#navigation").append(el("div", "nav-divider"));
    const button = action("", `nav-button${active === key ? " active" : ""}`, () => {
      active = key; render();
    });
    button.setAttribute("aria-current", active === key ? "page" : "false");
    const depth = categoryDepth(key);
    button.style.paddingLeft = `${12 + depth * 14}px`;
    button.append(el("span", "nav-icon", icon), el("span", "", name), el("span", "nav-count", count(key)));
    $("#navigation").append(button);
  });
  const name = categoryName(active);
  $("#breadcrumb").textContent = name;
  $("#collection-title").textContent = name;
  $("#total").textContent = items.length;
  $("#commands").textContent = items.filter(i => i.content && !["lankar", "dokumentation", "filer"].includes(i.category)).length;
  $("#favorites").textContent = count("favorites");
  $("#files").textContent = items.filter(i => i.filename !== null).length;
  const visible = filtered();
  $("#result-count").textContent = `${visible.length} ${visible.length === 1 ? "sak" : "saker"}`;
  $("#cards").replaceChildren(...visible.map(card));
  renderDashboard();
  $("#empty").hidden = loading || visible.length > 0;
  const first = items.length === 0;
  $("#empty-title").textContent = first ? "Här börjar din samling." : "Inga träffar den här gången.";
  $("#empty-text").textContent = first ? "Spara din första länk, kodsnutt eller fil – och slipp leta nästa gång." : "Prova en annan sökning eller lägg till något i den här kategorin.";
  $("#examples-button").hidden = !first || !canEdit();
}
function categoryDepth(key, seen = new Set()) {
  const category = categories.find(entry => entry[0] === key);
  if (!category || !category[3] || seen.has(key)) return 0;
  seen.add(key);
  return 1 + categoryDepth(category[3], seen);
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
  appendPersonalFavorite(top, item);
  const favorite = action(item.favorite ? "★" : "☆", `icon-button${item.favorite ? " selected" : ""}`, async () => {
    favorite.disabled = true;
    try { await api(`/api/items/${item.id}`, "PUT", {...item, favorite: !item.favorite}); await load(); }
    catch (error) { showError(error); }
    finally { favorite.disabled = false; }
  });
  favorite.setAttribute("aria-label", item.favorite ? "Ta bort gemensam favorit" : "Markera som gemensam favorit");
  favorite.title = "Gemensam favorit för biblioteket";
  favorite.setAttribute("aria-pressed", String(Boolean(item.favorite)));
  favorite.disabled = !canEdit();
  top.append(el("span", `category-badge ${item.category}`, categoryName(item.category)), favorite);
  const title = el("h3");
  title.append(action(item.title, "title-button", () => showDetail(item)));
  node.append(top, title);
  if (item.content) {
    const preview = item.content.slice(0, 2000).split("\n").slice(0, 8).join("\n");
    node.append(codeBlock(preview, item.language || "plain", false, "preview"));
  }
  const metadata = metadataSummary(item);
  if (metadata) node.append(el("p", "metadata-summary", metadata));
  if (item.pinned === "1") node.append(el("span", "tag", "Fäst av administratör"));
  node.append(riskBadge(item));
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
    actions.append(action("Kopiera", "small-button", () => copy(item.content, item)));
    actions.append(action("↓ Text", "small-button", () => downloadText(item)));
  }
  if (canEdit()) actions.append(action("Redigera", "small-button", () => openEditor(item)));
  const remove = action("×", "small-button delete-button", async () => {
    if (!confirm(`Flytta "${item.title}" till papperskorgen? Du kan återställa den senare.`)) return;
    remove.disabled = true;
    try { await api(`/api/items/${item.id}`, "DELETE"); await load(); notify("Posten flyttades till papperskorgen."); }
    catch (error) { showError(error); }
    finally { remove.disabled = false; }
  });
  remove.setAttribute("aria-label", `Ta bort ${item.title}`);
  if (canEdit()) actions.append(remove);
  bottom.append(actions); node.append(tags, bottom);
  return node;
}
async function copy(text, item = null) {
  if (item && !confirmRisk(item)) return;
  try {
    if (!navigator.clipboard || !window.isSecureContext) {
      throw new Error("Direktkopiering kräver HTTPS eller localhost. Öppna posten och kopiera texten manuellt.");
    }
    await navigator.clipboard.writeText(text); notify("Kopierat till urklipp.");
  } catch (error) { showError(error); }
}
function openEditor(item = null) {
  if (!canEdit()) { showError(new Error("Läsare kan inte ändra biblioteket.")); return; }
  editing = item;
  form.reset();
  populateCategories();
  populateProjectChoices(item);
  populateWorkbenchEditor(item);
  $("#form-error").hidden = true;
  $("#editor-title").textContent = item ? "Redigera sparad sak" : "Lägg till nytt";
  ["title", "download_name", "category", "content", "notes", "tags", "language", "os",
    "program_version", "ports", "dependencies", "tested_at", "status"].forEach(name => {
    const fallback = name === "category" ? (["all", "favorites"].includes(active) ? "kod" : active) :
      name === "language" ? "plain" : name === "status" ? "template" : "";
    if (!item && name === "category" && !categories.some(category => category[0] === fallback)) {
      form.elements[name].value = "kod";
    } else form.elements[name].value = item ? item[name] ?? fallback : fallback;
  });
  form.elements.favorite.checked = Boolean(item?.favorite);
  $("#existing-file").textContent = item?.filename !== null && item?.filename !== undefined ? `Bifogad: ${item.filename}. Välj en ny fil för att ersätta den.` : "";
  updateCategory(); $("#editor").showModal();
}
function updateCategory() {
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
  if (item.language === "markdown") body.append(renderMarkdown(item.content));
  if (item.content) {
    body.append(codeBlock(item.content, item.language || "plain", true, "detail-code"));
    body.append(action("Kopiera innehåll", "secondary", () => copy(item.content, item)));
    body.append(action("↓ Ladda ned text", "secondary", () => downloadText(item)));
  }
  const metadata = metadataSummary(item);
  if (metadata) body.append(el("p", "metadata-summary detail-metadata", metadata));
  if (item.notes) body.append(el("p", "detail-notes", item.notes));
  if (item.filename !== null) body.append(fileLink(item));
  appendItemTools(body, item);
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
    const payload = Object.fromEntries(["title", "download_name", "category", "content", "notes", "tags", "language",
      "os", "program_version", "ports", "dependencies", "tested_at", "status"].map(name => [name, form.elements[name].value]));
    payload.favorite = form.elements.favorite.checked;
    payload.project_ids = [...$("#editor-projects").querySelectorAll("input:checked")].map(input => Number(input.value));
    Object.assign(payload, workbenchEditorPayload());
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
function populateCategories() {
  $("#category-input").replaceChildren();
  categories.slice(2).forEach(([value]) => {
    const option = el("option", "", categoryName(value)); option.value = value; $("#category-input").append(option);
  });
}
function downloadText(item) {
  const extensions = {bat: ".bat", linux: ".sh", databaser: ".sql", docker: ".txt"};
  const preferred = (item.download_name || "").trim();
  const safe = (preferred || item.title).replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").slice(0, 200).replace(/[. ]+$/, "") || "kod";
  const filename = preferred ? safe : /\.[a-z0-9]{1,8}$/i.test(safe) ? safe : safe + (extensions[item.category] || ".txt");
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
$("#detail-history").addEventListener("click", () => openHistory(detailItem));
$("#category-input").addEventListener("change", updateCategory);
$("#search").addEventListener("input", render);
$("#sort").addEventListener("change", render);
["#filter-os", "#filter-status", "#filter-language"].forEach(selector => $(selector).addEventListener("change", render));
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
async function openCatalog() {
  $("#catalog-error").hidden = true;
  $("#catalog-packs").replaceChildren();
  $("#add-packs-button").disabled = true;
  $("#catalog-dialog").showModal();
  try {
    const catalog = await api("/api/examples");
    catalog.packs.forEach(pack => {
      const container = el("section", "catalog-pack");
      const label = el("label", "pack-label");
      const input = el("input");
      input.type = "checkbox"; input.name = "packs"; input.value = pack.id; input.checked = true;
      const heading = el("span");
      heading.append(el("strong", "", pack.title), el("small", "", `${pack.count} mallar · ${pack.description}`));
      label.append(input, heading);
      const details = el("details", "pack-details");
      details.append(el("summary", "", "Visa innehåll"));
      catalog.items.filter(item => item.pack === pack.id).forEach(item => {
        const example = el("div", "catalog-example");
        example.append(el("strong", "", item.title), el("pre", "preview", item.content),
          el("p", "muted", item.notes));
        details.append(example);
      });
      container.append(label, details); $("#catalog-packs").append(container);
    });
    $("#add-packs-button").disabled = false;
  } catch (error) { showError(error, $("#catalog-error")); }
}
$("#catalog-button").addEventListener("click", openCatalog);
$("#examples-button").addEventListener("click", openCatalog);
$("#close-catalog").addEventListener("click", () => $("#catalog-dialog").close());
$("#catalog-form").addEventListener("submit", async event => {
  event.preventDefault();
  $("#catalog-error").hidden = true; $("#add-packs-button").disabled = true;
  try {
    const packs = [...$("#catalog-packs").querySelectorAll("input:checked")].map(input => input.value);
    if (!packs.length) throw new Error("Välj minst ett paket.");
    const result = await api("/api/examples", "POST", {packs});
    $("#catalog-dialog").close(); await load();
    notify(`${result.added} mallar tillagda. ${result.skipped} redan sparade hoppades över.`);
  } catch (error) { showError(error, $("#catalog-error")); }
  finally { $("#add-packs-button").disabled = false; }
});
async function loadUsers() {
  $("#users-error").hidden = true;
  try {
    const users = await api("/api/users");
    $("#users-list").replaceChildren(...users.map(user => {
      const row = el("div", "user-row");
      const isSelf = currentUser && user.username === currentUser.username;
      row.append(el("span", "user-avatar", user.username.slice(0, 1).toUpperCase()),
        el("strong", "", user.username), el("span", `category-badge${user.active === false ? " inactive-badge" : ""}`, user.active === false ? "Inaktiv" : roleName(user.role)));
      const role = document.createElement("select");
      role.setAttribute("aria-label", `Roll för ${user.username}`);
      ["reader", "editor", "admin"].forEach(value => { const option = el("option", "", roleName(value)); option.value = value; role.append(option); });
      role.value = user.role;
      role.disabled = isSelf;
      const saveRole = action("Spara roll", "small-button", async () => {
        saveRole.disabled = true;
        try { await api(`/api/users/${user.id}`, "PUT", {role:role.value}); await loadUsers(); notify("Rollen har ändrats."); }
        catch (error) { showError(error, $("#users-error")); }
        finally { saveRole.disabled = isSelf; }
      });
      saveRole.disabled = isSelf;
      row.append(role, saveRole);
      const password = document.createElement("input");
      password.type = "password"; password.minLength = 12; password.maxLength = 256;
      password.autocomplete = "new-password"; password.placeholder = "Nytt lösenord (minst 12 tecken)";
      password.setAttribute("aria-label", `Nytt lösenord för ${user.username}`);
      const reset = action("Återställ lösenord", "small-button", async () => {
        if (password.value.length < 12 || password.value.length > 256) {
          showError(new Error("Lösenordet måste vara 12–256 tecken."), $("#users-error")); return;
        }
        reset.disabled = true; toggle.disabled = true;
        try {
          await api(`/api/users/${encodeURIComponent(user.id)}/reset-password`, "POST", {password:password.value});
          password.value = "";
          if (isSelf) location.replace("/login");
          else notify(`Lösenordet för ${user.username} har återställts.`);
        } catch (error) { showError(error, $("#users-error")); }
        finally { reset.disabled = false; toggle.disabled = isSelf; }
      });
      const toggle = action(user.active === false ? "Aktivera" : "Inaktivera", "small-button", async () => {
        if (isSelf) return;
        toggle.disabled = true; reset.disabled = true;
        try {
          await api(`/api/users/${encodeURIComponent(user.id)}`, "PUT", {active:user.active === false});
          await loadUsers(); notify(user.active === false ? "Användaren har aktiverats." : "Användaren har inaktiverats.");
        } catch (error) { showError(error, $("#users-error")); }
        finally { toggle.disabled = false; reset.disabled = false; }
      });
      toggle.disabled = isSelf;
      if (isSelf) toggle.title = "Du kan inte inaktivera ditt eget konto.";
      row.append(password, reset, toggle);
      return row;
    }));
  } catch (error) { showError(error, $("#users-error")); }
}
$("#users-button").addEventListener("click", () => {
  $("#user-form").reset(); $("#password-form").reset();
  $("#user-error").hidden = true; $("#password-error").hidden = true;
  $("#users-list").replaceChildren();
  $("#users-dialog").showModal();
  $("#user-form").hidden = !isAdmin();
  $("#users-list").hidden = !isAdmin();
  if (isAdmin()) loadUsers();
});
$("#close-users").addEventListener("click", () => $("#users-dialog").close());
$("#logout-button").addEventListener("click", async () => {
  $("#logout-button").disabled = true;
  try { await api("/api/logout", "POST"); location.replace("/login"); }
  catch (error) { showError(error); }
  finally { $("#logout-button").disabled = false; }
});
$("#user-form").addEventListener("submit", async event => {
  event.preventDefault();
  const userForm = event.currentTarget;
  $("#create-user-button").disabled = true; $("#user-error").hidden = true;
  try {
    await api("/api/users", "POST", {username:userForm.elements.username.value.trim(),
      password:userForm.elements.password.value, role:$("#new-user-role").value});
    userForm.reset(); await loadUsers(); notify("Användaren har skapats.");
  } catch (error) { showError(error, $("#user-error")); }
  finally { $("#create-user-button").disabled = false; }
});
$("#password-form").addEventListener("submit", async event => {
  event.preventDefault();
  const passwordForm = event.currentTarget;
  $("#change-password-button").disabled = true; $("#password-error").hidden = true;
  try {
    const current = passwordForm.elements.current_password.value;
    const next = passwordForm.elements.new_password.value;
    if (next !== passwordForm.elements.confirm_password.value) throw new Error("De nya lösenorden matchar inte.");
    await api("/api/password", "PUT", {current_password:current, new_password:next});
    location.replace("/login");
  } catch (error) { showError(error, $("#password-error")); }
  finally { $("#change-password-button").disabled = false; }
});
document.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", () => $(`#${button.dataset.close}`).close()));
$("#trash-button").addEventListener("click", () => {
  $("#trash-dialog").showModal(); loadTrash();
});
$("#activity-button").addEventListener("click", () => {
  $("#activity-dialog").showModal(); loadActivity();
});
$("#category-manage-button").addEventListener("click", () => {
  $("#category-dialog").showModal(); loadCategoriesForManagement();
});
$("#category-form").addEventListener("submit", async event => {
  event.preventDefault();
  const categoryForm = event.currentTarget;
  $("#category-error").hidden = true; $("#category-create").disabled = true;
  try {
    await api("/api/categories", "POST", {name:categoryForm.elements.name.value.trim(), parent:categoryForm.elements.parent.value || null});
    categoryForm.reset(); await loadCategoriesForManagement(); notify("Kategorin har skapats.");
  } catch (error) { showError(error, $("#category-error")); }
  finally { $("#category-create").disabled = false; }
});
$("#admin-button").addEventListener("click", () => {
  $("#admin-dialog").showModal(); loadAdmin();
});
$("#registration-save").addEventListener("click", async () => {
  $("#registration-save").disabled = true; $("#admin-error").hidden = true;
  try {
    await api("/api/settings", "PUT", {registration_open:$("#registration-toggle").checked});
    notify($("#registration-toggle").checked ? "Registreringen är öppen." : "Publik registrering är stängd.");
  } catch (error) { showError(error, $("#admin-error")); }
  finally { $("#registration-save").disabled = false; }
});
$("#backup-create").addEventListener("click", async () => {
  $("#backup-create").disabled = true; $("#admin-error").hidden = true;
  try { await api("/api/backups", "POST", {}); await loadAdmin(); notify("Säkerhetskopian har skapats."); }
  catch (error) { showError(error, $("#admin-error")); }
  finally { $("#backup-create").disabled = false; }
});
async function boot() {
  try {
    const user = await api("/api/me");
    csrf = user.csrf;
    currentUser = user;
    bookmarkImportButton.hidden = !canEdit();
    $("#account-name").textContent = `${user.username} · ${roleName(user.role)}`;
    applyPermissions();
    await load();
    $("main").inert = false;
    openCapturedBookmark();
    await openDeepLink();
  } catch (error) { showError(error); }
}
window.addEventListener("pageshow", event => { if (event.persisted) location.reload(); });
