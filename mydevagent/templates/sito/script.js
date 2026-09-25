// Interattività del sito: tema chiaro/scuro e contatore dei saluti.

document.getElementById("anno").textContent = new Date().getFullYear();

const tema = document.getElementById("tema");
tema.addEventListener("click", () => {
  const scuro = document.body.classList.toggle("scuro");
  tema.textContent = scuro ? "☀️" : "🌙";
});

let saluti = 0;
document.getElementById("saluta").addEventListener("click", () => {
  saluti += 1;
  document.getElementById("saluti").textContent =
    saluti === 1 ? "Mi hai salutato 1 volta 👋" : `Mi hai salutato ${saluti} volte 👋`;
});
