// Mostra um slide por vez quando a URL traz ?s=N. Sem query, a página
// exibe todos os slides empilhados, que é o modo de conferir a peça
// inteira no navegador. O render usa a query para tirar um PNG de cada
// slide em 1080x1080.
(function () {
  var n = new URLSearchParams(location.search).get('s');
  if (!n) return;
  var slides = document.querySelectorAll('.slide');
  var i = parseInt(n, 10) - 1;
  if (!slides[i]) return;
  document.body.classList.add('isolado');
  slides[i].classList.add('alvo');
})();
