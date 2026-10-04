"use strict";
const form = document.querySelector("#login-form");
const errorBox = document.querySelector("#login-error");
const button = document.querySelector("#login-button");
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
