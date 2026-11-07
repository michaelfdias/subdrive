// Ao abrir uma página por um link, começa do topo (ou da âncora pedida).
// Navegadores fazem isso sozinhos; alguns visualizadores, que mostram o site dentro de outra janela,
// mantêm a rolagem da página anterior. Ao voltar (botão Voltar), o navegador restaura a posição normalmente.
(function () {
  var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
  if (nav && nav.type === "back_forward") return;
  function posicionar() {
    var alvo = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : document.documentElement;
    if (!alvo) return;
    try { alvo.scrollIntoView({ block: "start", behavior: "instant" }); } catch (e) { alvo.scrollIntoView(true); }
  }
  posicionar();
  window.addEventListener("load", posicionar, { once: true });
})();

// Menu do celular.
(function () {
  var botao = document.querySelector(".abrir-menu"), menu = document.getElementById("menu");
  if (!botao || !menu) return;
  function fechar() { menu.classList.remove("aberto"); botao.setAttribute("aria-expanded", "false"); }
  botao.addEventListener("click", function () {
    var aberto = menu.classList.toggle("aberto");
    botao.setAttribute("aria-expanded", aberto ? "true" : "false");
  });
  menu.addEventListener("click", function (e) { if (e.target.closest("a")) fechar(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") fechar(); });
})();

// Escolha do ZIP: computador + tipo de disco mostram o nome do arquivo.
(function () {
  var form = document.getElementById("escolher-zip");
  if (!form) return;
  var saida = document.getElementById("nome-zip"), vazio = document.getElementById("zip-vazio"), rotulo = form.querySelector(".resultado .rotulo");
  function atualizar() {
    var pc = form.querySelector("input[name=pc]:checked"), disco = form.querySelector("input[name=disco]:checked");
    if (pc && disco) {
      saida.textContent = "…-" + disco.value + "-" + pc.value + ".zip";
      saida.hidden = false; vazio.hidden = true; rotulo.hidden = false;
    } else { saida.hidden = true; vazio.hidden = false; rotulo.hidden = true; }
  }
  // Marca Windows ou Linux quando dá para saber com certeza. No Mac, o chip não dá para saber: a pessoa escolhe.
  var ua = navigator.userAgent;
  var palpite = /Windows/.test(ua) ? "Windows" : (/Linux/.test(ua) && !/Android/.test(ua) ? "Linux" : null);
  if (palpite) { var el = form.querySelector("input[name=pc][value=" + palpite + "]"); if (el) el.checked = true; }
  form.addEventListener("change", atualizar);
  atualizar();
})();

// Botões "Copiar": <button data-copiar="#id"> copia o texto do elemento, ou do arquivo em data-arquivo.
document.addEventListener("click", async function (e) {
  var b = e.target.closest("button[data-copiar], button[data-arquivo]");
  if (!b) return;
  var texto = "";
  try {
    if (b.dataset.arquivo) texto = await (await fetch(b.dataset.arquivo)).text();
    else texto = document.querySelector(b.dataset.copiar).textContent.trim();
    await navigator.clipboard.writeText(texto);
    var antes = b.textContent; b.textContent = "Copiado!"; setTimeout(function () { b.textContent = antes; }, 1800);
  } catch (err) { b.textContent = "Não deu para copiar"; }
});

// A chave Pix entra na publicação; sem ela, a seção fica escondida.
document.querySelectorAll("[data-pix]").forEach(function (el) {
  if (el.textContent.indexOf("__PIX") !== -1) el.closest("[data-secao-pix]").hidden = true;
});

// <details> abrem e fecham deslizando.
(function () {
  var calmo = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (calmo || !Element.prototype.animate) return;
  document.querySelectorAll("details > summary").forEach(function (summary) {
    var det = summary.parentElement, anim = null;
    summary.addEventListener("click", function (e) {
      e.preventDefault();
      if (anim) anim.cancel();
      var inicio = det.offsetHeight + "px", abrindo = !det.open;
      if (abrindo) det.open = true;
      var fim = abrindo ? det.scrollHeight + "px" : summary.offsetHeight + 1 + "px";
      anim = det.animate({ height: [inicio, fim] }, { duration: 240, easing: "ease-out" });
      anim.onfinish = function () { anim = null; if (!abrindo) det.open = false; };
      anim.oncancel = function () { anim = null; };
    });
  });
})();

// Guia: destaca no índice a etapa que está na tela.
(function () {
  var links = document.querySelectorAll(".indice a");
  if (!links.length || !("IntersectionObserver" in window)) return;
  var mapa = {};
  links.forEach(function (a) { mapa[a.hash.slice(1)] = a; });
  var obs = new IntersectionObserver(function (entradas) {
    entradas.forEach(function (en) {
      if (en.isIntersecting) {
        links.forEach(function (a) { a.classList.remove("atual"); });
        var a = mapa[en.target.id]; if (a) a.classList.add("atual");
      }
    });
  }, { rootMargin: "-30% 0px -60% 0px" });
  Object.keys(mapa).forEach(function (id) { var s = document.getElementById(id); if (s) obs.observe(s); });
})();
