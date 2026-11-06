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
