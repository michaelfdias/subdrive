// Theme: follows the system unless the visitor picks one with the button (remembered in this browser).
(function () {
  var root = document.documentElement, chave = "subdrive-tema";
  try { var salvo = localStorage.getItem(chave); if (salvo) root.dataset.tema = salvo; } catch (e) {}
  function escuro() {
    return root.dataset.tema ? root.dataset.tema === "escuro" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function rotulo(b) { b.textContent = escuro() ? "☀️ Claro" : "🌙 Escuro"; b.setAttribute("aria-label", escuro() ? "Mudar para o tema claro" : "Mudar para o tema escuro"); }
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("button.tema").forEach(function (b) {
      rotulo(b);
      b.addEventListener("click", function () {
        root.dataset.tema = escuro() ? "claro" : "escuro";
        try { localStorage.setItem(chave, root.dataset.tema); } catch (e) {}
        document.querySelectorAll("button.tema").forEach(rotulo);
      });
    });
  });
})();
