// "Copiar" buttons: <button data-copiar="#id"> copies the text of that element, or of the file in data-arquivo.
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
// The Pix key is filled in when the site is published; without it the section stays hidden.
document.querySelectorAll("[data-pix]").forEach(function (el) {
  if (el.textContent.indexOf("__PIX") !== -1) el.closest("[data-secao-pix]").hidden = true;
});
// Contact: the e-mail address is put together here so simple spam robots do not read it from the page.
(function () {
  var email = ["michaelfdias", "gmail.com"].join("@");
  document.querySelectorAll("a[data-email]").forEach(function (a) { a.href = "mailto:" + email + "?subject=SubDrive"; });
  document.querySelectorAll("[data-email-texto]").forEach(function (el) {
    var a = document.createElement("a"); a.href = "mailto:" + email + "?subject=SubDrive"; a.textContent = email; el.replaceWith(a);
  });
  document.querySelectorAll("a[data-form]").forEach(function (a) { if (a.getAttribute("href").indexOf("__FORMS") === 0) a.hidden = true; });
})();
// Sections that open and close (<details>) slide instead of jumping.
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
      var fim = abrindo ? det.scrollHeight + "px" : summary.offsetHeight + parseFloat(getComputedStyle(det).paddingTop) + parseFloat(getComputedStyle(det).paddingBottom) + 2 + "px";
      anim = det.animate({ height: [inicio, fim] }, { duration: 260, easing: "ease-out" });
      anim.onfinish = function () { anim = null; if (!abrindo) det.open = false; };
      anim.oncancel = function () { anim = null; };
    });
  });
})();
