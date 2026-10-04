"use strict";
let projects = [], savedSearches = [], batchItems = [], batchRevision = 0;

function option(value, label) {
  const node = el("option", "", label); node.value = String(value); return node;
}
function labeled(text, input) {
  const label = el("label", "", text); label.append(input); return label;
}
function applyPermissions() {
  ["#add-button", "#first-button", "#catalog-button", "#import-button", "#examples-button",
    "#category-manage-button", "#detail-edit", "#batch-button"].forEach(selector => { $(selector).hidden = !canEdit(); });
  ["#activity-button", "#admin-button"].forEach(selector => { $(selector).hidden = !isAdmin(); });
  $("#users-button").textContent = isAdmin() ? "Användare" : "Mitt konto";
}
function currentFilters() {
  return {query:$("#search").value, category:active, tags:$("#filter-tags").value,
    descendants:$("#filter-descendants").checked, attachments:$("#filter-attachments").checked,
    project:$("#filter-project").value, os:$("#filter-os").value, language:$("#filter-language").value,
    status:$("#filter-status").value, sort:$("#sort").value};
}
function refreshLibraryTools(loadedProjects, loadedSearches) {
  projects = loadedProjects; savedSearches = loadedSearches;
  const projectValue = $("#filter-project").value;
  $("#filter-project").replaceChildren(option("", "Alla projekt"),
    ...projects.map(project => option(project.id, project.name)));
  $("#filter-project").value = projects.some(project => String(project.id) === projectValue) ? projectValue : "";
  $("#saved-search").replaceChildren(option("", "Välj sparad sökning"),
    ...savedSearches.map(search => option(search.id, search.name)));
}
function populateProjectChoices(item) {
  $("#editor-projects").replaceChildren(el("legend", "", "Projektsamlingar"));
  if (!projects.length) $("#editor-projects").append(el("p", "muted", "Skapa ett projekt via Projektsamlingar."));
  projects.forEach(project => {
    const input = document.createElement("input");
    input.type = "checkbox"; input.value = String(project.id); input.checked = (item?.project_ids || []).includes(project.id);
    const label = labeled(project.name, input); label.className = "checkbox"; $("#editor-projects").append(label);
  });
}
function appendItemTools(body, item) {
  if (item.project_ids?.length) {
    const memberships = el("div", "project-memberships");
    item.project_ids.forEach(id => {
      const project = projects.find(entry => entry.id === id);
      if (project) memberships.append(action(project.name, "small-button", () => {
        $("#filter-project").value = String(id); active = "all"; $("#detail").close(); render();
      }));
    });
    body.append(el("h3", "", "Projektsamlingar"), memberships);
  }
  const names = LibraryTools.variableNames(item.content);
  if (!names.length) return;
  const section = el("section", "account-form");
  section.append(el("h3", "", "Anpassa mall"),
    el("p", "muted", "Fyll i {{variabler}} för ett färdigt kommando. Värden ersätts bokstavligt, utan shell-escaping. Kontrollera citattecken, sökvägar och lösenord innan användning. Inget körs eller sparas automatiskt."));
  const inputs = new Map();
  names.forEach(name => {
    const input = document.createElement("input");
    input.maxLength = 2000; input.autocomplete = "off"; input.spellcheck = false;
    inputs.set(name, input); section.append(labeled(name, input));
  });
  const error = el("p", "error"); error.hidden = true; error.setAttribute("role", "alert");
  const output = document.createElement("textarea");
  output.readOnly = true; output.rows = 8; output.setAttribute("aria-label", "Genererat kommando"); output.spellcheck = false;
  const copyButton = action("Kopiera genererat kommando", "secondary", () => copy(output.value));
  const downloadButton = action("Ladda ned genererad text", "secondary", () => downloadText({...item, content:output.value}));
  copyButton.disabled = true; downloadButton.disabled = true;
  const generate = action("Generera kommando", "primary", () => {
    error.hidden = true;
    try {
      const values = Object.create(null);
      inputs.forEach((input, name) => { values[name] = input.value; });
      output.value = LibraryTools.renderTemplate(item.content, values);
      copyButton.disabled = false; downloadButton.disabled = false;
    } catch (failure) {
      output.value = ""; copyButton.disabled = true; downloadButton.disabled = true; showError(failure, error);
    }
  });
  inputs.forEach(input => input.addEventListener("input", () => {
    output.value = ""; copyButton.disabled = true; downloadButton.disabled = true;
  }));
  section.append(generate, error, output, copyButton, downloadButton); body.append(section);
}
function openCapturedBookmark() {
  const params = new URLSearchParams(location.hash.slice(1));
  if (!params.has("capture")) return;
  try {
    const raw = params.get("capture");
    if (raw.length > 6000) throw new Error("Bokmärket är för långt.");
    const captured = JSON.parse(raw);
    if (!captured || typeof captured.url !== "string" || typeof captured.title !== "string" ||
        !["https:", "http:"].includes(new URL(captured.url).protocol)) throw new Error("Ogiltig bokmärkeslänk.");
    if (!canEdit()) throw new Error("En läsare kan inte spara bokmärken. Be en administratör ändra din roll.");
    openEditor();
    form.elements.category.value = "lankar"; form.elements.title.value = (captured.title || captured.url).slice(0,200);
    form.elements.content.value = captured.url; updateCategory();
  } catch (failure) { showError(failure); }
  finally { history.replaceState(null, "", location.pathname + location.search); }
}
async function showProjects() {
  $("#projects-error").hidden = true;
  try {
    await load();
    $("#project-form").hidden = !canEdit();
    $("#project-list").replaceChildren();
    projects.forEach(project => {
      const row = el("article", "project-row");
      row.append(action(project.name, "title-button", () => {
        active = "all"; $("#filter-project").value = String(project.id); $("#projects-dialog").close(); render();
      }), el("p", "muted", project.description));
      if (canEdit()) {
        const name = document.createElement("input"); name.value = project.name; name.maxLength = 80;
        const description = document.createElement("textarea"); description.value = project.description; description.maxLength = 2000;
        const save = action("Spara projekt", "secondary", async () => {
          save.disabled = true;
          try {
            await api(`/api/projects/${project.id}`, "PUT", {name:name.value, description:description.value});
            await showProjects(); notify("Projektet sparades.");
          } catch (failure) { showError(failure, $("#projects-error")); }
          finally { save.disabled = false; }
        });
        const remove = action("Ta bort projekt", "danger-button", async () => {
          if (!confirm(`Ta bort projektet "${project.name}"? Poster och filer behålls.`)) return;
          remove.disabled = true;
          try { await api(`/api/projects/${project.id}`, "DELETE"); await showProjects(); notify("Projektet togs bort."); }
          catch (failure) { showError(failure, $("#projects-error")); }
          finally { remove.disabled = false; }
        });
        row.append(labeled("Projektnamn", name), labeled("Beskrivning", description), save, remove);
      }
      $("#project-list").append(row);
    });
  } catch (failure) { showError(failure, $("#projects-error")); }
}
function clearBatchPreview() {
  batchRevision += 1;
  batchItems = []; $("#batch-preview").replaceChildren(); $("#batch-save").disabled = true;
  $("#batch-files").disabled = false; $("#batch-category").disabled = false; $("#batch-mode").disabled = false;
}
async function previewFiles(files) {
  clearBatchPreview(); $("#batch-error").hidden = true; $("#batch-files").disabled = true;
  const revision = batchRevision;
  $("#batch-category").disabled = true; $("#batch-mode").disabled = true;
  try {
    if (!files.length || files.length > 50) throw new Error("Välj 1–50 filer.");
    if (files.reduce((total, file) => total + file.size, 0) > 20 * 1024 * 1024) throw new Error("Filerna får tillsammans vara högst 20 MB.");
    const candidates = [];
    for (const file of files) {
      const textMode = $("#batch-mode").value === "text" ||
        ($("#batch-mode").value === "auto" && LibraryTools.isText(file.name));
      const candidate = {title:file.name.slice(0,200), category:$("#batch-category").value, content:"",
        language:LibraryTools.language(file.name), download_name:textMode ? file.name : "", project_ids:[]};
      if (textMode) {
        if (file.size > 200000) throw new Error(`${file.name}: kodtext får vara högst 200 kB. Välj Bilagor för större filer.`);
        try { candidate.content = new TextDecoder("utf-8", {fatal:true}).decode(await file.arrayBuffer()); }
        catch (failure) {
          if (failure instanceof TypeError) throw new Error(`${file.name}: inte giltig UTF-8. Välj Bilagor.`);
          throw failure;
        }
        if (candidate.content.includes("\0")) throw new Error(`${file.name}: verkar vara binär. Välj Bilagor.`);
      } else { candidate.filename = file.name; candidate.filedata = await readFile(file); }
      candidates.push(candidate);
    }
    const preview = await api("/api/batch/preview", "POST", {items:candidates});
    if (revision !== batchRevision) return;
    batchItems = candidates;
    preview.items.forEach(result => {
      const candidate = candidates[result.index];
      const row = el("article", "batch-row"); row.dataset.index = String(result.index);
      const check = document.createElement("input"); check.type = "checkbox"; check.checked = true;
      const title = document.createElement("input"); title.value = candidate.title; title.maxLength = 200;
      title.addEventListener("input", () => { candidate.title = title.value; });
      row.append(labeled("Importera fil", check), labeled("Titel", title),
        el("p", result.duplicate ? "duplicate-warning" : "muted", result.duplicate
          ? `Dubblett: ${result.duplicate.title || "samma innehåll i denna import"}. Hoppas över om dubbletter inte tillåts.`
          : candidate.filename ? `Bilaga: ${candidate.filename}` : `Kodtext: ${candidate.language}`));
      if (!candidate.filename) row.append(codeBlock(candidate.content.slice(0,2000), candidate.language, false, "preview"));
      $("#batch-preview").append(row);
    });
    $("#batch-save").disabled = false;
  } catch (failure) {
    if (revision === batchRevision) { clearBatchPreview(); showError(failure, $("#batch-error")); }
  } finally {
    if (revision === batchRevision) {
      $("#batch-files").disabled = false; $("#batch-category").disabled = false; $("#batch-mode").disabled = false;
    }
  }
}

const advanced = el("section", "filters advanced-filters"); advanced.setAttribute("aria-label", "Avancerad sökning");
const tagFilter = document.createElement("input"); tagFilter.id = "filter-tags"; tagFilter.maxLength = 500; tagFilter.placeholder = "linux, docker";
const descendants = document.createElement("input"); descendants.id = "filter-descendants"; descendants.type = "checkbox";
const attachmentsOnly = document.createElement("input"); attachmentsOnly.id = "filter-attachments"; attachmentsOnly.type = "checkbox";
const projectFilter = document.createElement("select"); projectFilter.id = "filter-project"; projectFilter.append(option("", "Alla projekt"));
advanced.append(labeled("Alla dessa taggar", tagFilter), labeled("Projekt", projectFilter));
for (const [text, input] of [["Inkludera underkategorier", descendants], ["Bara bilagor", attachmentsOnly]]) {
  const label = labeled(text, input); label.className = "checkbox"; advanced.append(label);
}
$(".filters").after(advanced);
[tagFilter, descendants, attachmentsOnly, projectFilter].forEach(input => input.addEventListener(input === tagFilter ? "input" : "change", render));

const searches = el("section", "filters saved-searches");
const searchSelect = document.createElement("select"); searchSelect.id = "saved-search"; searchSelect.setAttribute("aria-label", "Sparade sökningar");
const searchName = document.createElement("input"); searchName.id = "search-name"; searchName.maxLength = 80; searchName.placeholder = "Namn på sökningen";
searchName.setAttribute("aria-label", "Namn på sparad sökning");
const saveSearch = action("Spara sökning", "secondary", async () => {
  saveSearch.disabled = true;
  try {
    await api("/api/searches", "POST", {name:searchName.value, filters:currentFilters()});
    searchName.value = ""; await load(); notify("Sökningen sparades för ditt konto.");
  } catch (failure) { showError(failure); }
  finally { saveSearch.disabled = false; }
});
const deleteSearch = action("Ta bort sökning", "secondary", async () => {
  if (!searchSelect.value) { showError(new Error("Välj en sparad sökning.")); return; }
  deleteSearch.disabled = true;
  try { await api(`/api/searches/${searchSelect.value}`, "DELETE"); await load(); notify("Sökningen togs bort."); }
  catch (failure) { showError(failure); }
  finally { deleteSearch.disabled = false; }
});
searches.append(searchSelect, searchName, saveSearch, deleteSearch); advanced.after(searches);
searchSelect.addEventListener("change", () => {
  const selected = savedSearches.find(search => String(search.id) === searchSelect.value);
  if (!selected) return;
  const filters = selected.filters;
  if (!categories.some(category => category[0] === filters.category) ||
      (filters.project && !projects.some(project => String(project.id) === filters.project))) {
    showError(new Error("Sökningens kategori eller projekt har tagits bort. Skapa en ny sökning med aktuella filter."));
    return;
  }
  active = filters.category;
  const values = {"#search":"query", "#filter-tags":"tags", "#filter-project":"project", "#filter-os":"os",
    "#filter-language":"language", "#filter-status":"status", "#sort":"sort"};
  Object.entries(values).forEach(([selector, key]) => {
    const input = $(selector);
    if (input.tagName === "SELECT" && ![...input.options].some(entry => entry.value === filters[key])) {
      input.append(option(filters[key], filters[key] || "Alla"));
    }
    input.value = filters[key];
  });
  descendants.checked = filters.descendants; attachmentsOnly.checked = filters.attachments; render();
});

const projectButton = action("Projektsamlingar", "secondary", () => { $("#projects-dialog").showModal(); showProjects(); });
const batchButton = action("Flera filer", "secondary", () => {
  clearBatchPreview(); $("#batch-error").hidden = true; $("#batch-files").value = "";
  $("#batch-category").replaceChildren(...categories.slice(2).filter(category => category[0] !== "lankar").map(category => option(category[0], categoryName(category[0]))));
  $("#batch-category").value = active !== "lankar" && categories.slice(2).some(category => category[0] === active) ? active : "kod";
  $("#batch-dialog").showModal();
}); batchButton.id = "batch-button";
const bookmarkButton = action("Spara från webbläsaren", "secondary", () => { $("#bookmark-dialog").showModal(); });
$(".toolbar").append(projectButton, batchButton, bookmarkButton);
const bookmarkScript = `window.open(${JSON.stringify(location.origin + "/")}+"#capture="+encodeURIComponent(JSON.stringify({url:location.href,title:document.title})),"_blank","noopener");void 0;`;
$("#bookmarklet").href = "javascript:" + bookmarkScript;
$("#bookmarklet").addEventListener("click", event => { event.preventDefault(); notify("Dra länken till bokmärkesfältet i din webbläsare."); });

const projectChoices = document.createElement("fieldset"); projectChoices.id = "editor-projects"; projectChoices.className = "account-form";
$("#existing-file").after(projectChoices);
const templateHint = el("p", "muted", "Mallvariabler: skriv {{server_name}}, {{ip}}, {{port}} eller andra namn i kodtexten. Fyll i dem via Anpassa mall när du öppnar posten.");
$("#content-label").after(templateHint);
const templateSelect = document.createElement("select"); templateSelect.id = "variable-template";
templateSelect.append(option("", "Välj exempelmall"), option("docker", "Docker-container"),
  option("steamcmd", "SteamCMD-installation"), option("bat", "Windows BAT-serverstart"));
const templateExamples = {
  docker: {language:"bash", name:"start-container.sh",
    content:'docker run -d --name "{{container_name}}" -p "{{host_port}}:{{container_port}}" "{{image}}"\n'},
  steamcmd: {language:"bash", name:"install-server.sh",
    content:'steamcmd +force_install_dir "{{server_path}}" +login anonymous +app_update {{app_id}} validate +quit\n'},
  bat: {language:"bat", name:"start-server.bat",
    content:'@echo off\ncd /d "{{server_path}}"\n"{{executable}}" -port {{port}}\npause\n'}
};
const insertTemplate = action("Infoga variabelmall", "secondary", () => {
  const example = templateExamples[templateSelect.value];
  if (!example) { showError(new Error("Välj en exempelmall."), $("#form-error")); return; }
  if (form.elements.content.value && !confirm("Ersätta nuvarande kod med exempelmallens innehåll?")) return;
  form.elements.content.value = example.content;
  form.elements.language.value = example.language;
  form.elements.download_name.value = example.name;
  form.elements.category.value = templateSelect.value; updateCategory();
});
templateHint.after(labeled("Färdiga variabelexempel", templateSelect), insertTemplate);
const newRole = document.createElement("select"); newRole.id = "new-user-role";
newRole.append(option("reader", "Läsare"), option("editor", "Redigerare"), option("admin", "Administratör"));
$("#create-user-button").before(labeled("Roll", newRole)); $("#create-user-button").textContent = "Skapa användare";
$("#project-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button"); button.disabled = true; $("#projects-error").hidden = true;
  try {
    await api("/api/projects", "POST", {name:event.currentTarget.elements.name.value, description:event.currentTarget.elements.description.value});
    $("#project-form").reset(); await showProjects(); notify("Projektet skapades.");
  } catch (failure) { showError(failure, $("#projects-error")); }
  finally { button.disabled = false; }
});
$("#batch-files").addEventListener("change", event => { previewFiles([...event.target.files]); });
["#batch-category", "#batch-mode"].forEach(selector => $(selector).addEventListener("change", () => {
  clearBatchPreview(); $("#batch-files").value = ""; notify("Inställningen ändrades. Välj filerna igen för en ny förhandsvisning.");
}));
$("#drop-zone").addEventListener("dragover", event => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; });
$("#drop-zone").addEventListener("drop", event => {
  event.preventDefault(); if ($("#batch-files").disabled) return; previewFiles([...event.dataTransfer.files]);
});
$("#drop-zone").addEventListener("keydown", event => {
  if (event.target === event.currentTarget && ["Enter", " "].includes(event.key)) { event.preventDefault(); $("#batch-files").click(); }
});
$("#batch-save").addEventListener("click", async () => {
  $("#batch-save").disabled = true; $("#batch-error").hidden = true;
  $("#batch-files").disabled = true; $("#batch-category").disabled = true; $("#batch-mode").disabled = true;
  try {
    const selected = [...document.querySelectorAll("#batch-preview .batch-row")].filter(row => row.querySelector("[type=checkbox]").checked)
      .map(row => batchItems[Number(row.dataset.index)]);
    if (!selected.length) throw new Error("Välj minst en fil i förhandsvisningen.");
    const result = await api("/api/batch/import", "POST", {items:selected, allow_duplicates:$("#batch-duplicates").checked});
    $("#batch-dialog").close(); clearBatchPreview(); await load();
    notify(`${result.added} filer importerades. ${result.skipped} dubbletter hoppades över.`);
  } catch (failure) { showError(failure, $("#batch-error")); $("#batch-save").disabled = false; }
  finally { $("#batch-files").disabled = false; $("#batch-category").disabled = false; $("#batch-mode").disabled = false; }
});
$("#batch-dialog").addEventListener("close", clearBatchPreview);
window.addEventListener("hashchange", () => { if (currentUser) openCapturedBookmark(); });
boot();
