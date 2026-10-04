"use strict";
const form = document.querySelector("#login-form");
const errorBox = document.querySelector("#login-error");
const button = document.querySelector("#login-button");
const registerForm = document.querySelector("#register-form");
function switchForm(register) {
  form.hidden = register;
  registerForm.hidden = !register;
  document.querySelector("#login-tab").setAttribute("aria-pressed", String(!register));
  document.querySelector("#register-tab").setAttribute("aria-pressed", String(register));
  document.querySelector(".login-card h2").textContent = register ? "Skapa ditt eget konto." : "Logga in i ditt bibliotek.";
  document.querySelector(".login-card .eyebrow").textContent = register ? "VÄLKOMMEN TILL BIBLIOTEKET" : "VÄLKOMMEN TILLBAKA";
  errorBox.hidden = true;
  document.querySelector("#register-error").hidden = true;
  document.querySelector("#register-success").hidden = true;
  (register ? registerForm : form).elements.username.focus();
}
document.querySelector("#login-tab").addEventListener("click", () => switchForm(false));
document.querySelector("#register-tab").addEventListener("click", () => switchForm(true));
async function loadRegistrationAvailability() {
  const tab = document.querySelector("#register-tab");
  const notice = document.querySelector("#registration-notice");
  try {
    const response = await fetch("/api/registration");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Registreringsstatus kunde inte hämtas.");
    tab.hidden = !result.registration_open;
    document.querySelector(".login-help").hidden = !result.registration_open;
    if (!result.registration_open) {
      notice.textContent = "Kontoregistrering är stängd. Be en administratör skapa ditt konto.";
      notice.hidden = false;
    }
  } catch (error) {
    tab.hidden = true;
    document.querySelector(".login-help").hidden = true;
    notice.textContent = error.message;
    notice.hidden = false;
  }
}
registerForm.addEventListener("submit", async event => {
  event.preventDefault();
  const submit = document.querySelector("#register-button");
  const registerError = document.querySelector("#register-error");
  registerError.hidden = true;
  submit.disabled = true;
  submit.textContent = "Skapar konto…";
  try {
    const username = registerForm.elements.username.value.trim();
    const password = registerForm.elements.password.value;
    if (password !== registerForm.elements.confirm_password.value) throw new Error("Lösenorden matchar inte.");
    const response = await fetch("/api/register", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({username, password})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Kontot kunde inte skapas.");
    registerForm.reset();
    switchForm(false);
    form.elements.username.value = result.username;
    form.elements.password.value = "";
    const success = document.querySelector("#register-success");
    success.textContent = `Kontot ${result.username} är skapat med läsbehörighet. Logga in med ditt lösenord. En administratör kan ändra din roll.`;
    success.hidden = false;
    form.elements.password.focus();
  } catch (error) {
    registerError.textContent = error.message;
    registerError.hidden = false;
  } finally {
    submit.disabled = false;
    submit.textContent = "Skapa mitt konto →";
  }
});
document.querySelector("#show-password").addEventListener("click", event => {
  const input = document.querySelector("#login-password");
  const visible = input.type === "password";
  input.type = visible ? "text" : "password";
  event.currentTarget.textContent = visible ? "Dölj" : "Visa";
  event.currentTarget.setAttribute("aria-pressed", String(visible));
});
form.addEventListener("submit", async event => {
  event.preventDefault();
  errorBox.hidden = true;
  button.disabled = true;
  button.textContent = "Loggar in…";
  try {
    const response = await fetch("/api/login", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({username: form.elements.username.value.trim(), password: form.elements.password.value})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Inloggningen misslyckades.");
    const validHash = (location.hash.startsWith("#capture=") && location.hash.length <= 18000) ||
      /^#(?:item|guide|project|server)=\d+$/.test(location.hash);
    location.replace("/" + (validHash ? location.hash : ""));
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Logga in →";
  }
});
button.disabled = false;
document.querySelector("#register-button").disabled = false;
loadRegistrationAvailability();
