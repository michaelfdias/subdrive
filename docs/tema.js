// Tema: segue o sistema, a menos que o visitante escolha um no botão (fica guardado neste navegador).
(function () {
  var root = document.documentElement, chave = "subdrive-tema", midia = window.matchMedia("(prefers-color-scheme: dark)");
  try { var salvo = localStorage.getItem(chave); if (salvo) root.dataset.tema = salvo; } catch (e) {}
  function escuro() { return root.dataset.tema ? root.dataset.tema === "escuro" : midia.matches; }
  function aplicar() {
    root.toggleAttribute("data-escuro", escuro());
    // Barra do navegador no celular: acompanha o tema escolhido no botão.
    if (root.dataset.tema) document.querySelectorAll('meta[name="theme-color"]').forEach(function (m) { m.content = escuro() ? "#111214" : "#f7f7f5"; });
    document.querySelectorAll("button.tema").forEach(function (b) {
      b.setAttribute("aria-label", escuro() ? "Mudar para o tema claro" : "Mudar para o tema escuro");
      b.title = b.getAttribute("aria-label");
    });
  }
  aplicar();
  if (midia.addEventListener) midia.addEventListener("change", aplicar);
  document.addEventListener("DOMContentLoaded", function () {
    aplicar();
    document.querySelectorAll("button.tema").forEach(function (b) {
      b.addEventListener("click", function () {
        root.dataset.tema = escuro() ? "claro" : "escuro";
        try { localStorage.setItem(chave, root.dataset.tema); } catch (e) {}
        aplicar();
      });
    });
  });
})();
