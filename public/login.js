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
    success.textContent = `Kontot ${result.username} är skapat! Du är administratör. Logga in med ditt lösenord.`;
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
    location.replace("/");
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Logga in →";
  }
});
