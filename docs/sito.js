// Vesper - comportamenti del sito: tema chiaro/scuro e "torna su".
// Niente librerie: poche righe, tutto qui.
(function () {
  "use strict";

  var html = document.documentElement;
  var CHIAVE = "vesper-tema";

  function applica(tema) {
    if (tema === "chiaro" || tema === "scuro") {
      html.setAttribute("data-tema", tema);
    } else {
      html.removeAttribute("data-tema");   // torna a seguire il sistema
    }
    aggiornaPulsante();
  }

  function temaAttivo() {
    var scelto = html.getAttribute("data-tema");
    if (scelto) return scelto;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "scuro" : "chiaro";
  }

  function aggiornaPulsante() {
    var b = document.getElementById("cambia-tema");
    if (!b) return;
    var scuro = temaAttivo() === "scuro";
    b.textContent = scuro ? "☀ Chiaro" : "☾ Scuro";
    b.setAttribute("aria-label",
      scuro ? "Passa al tema chiaro" : "Passa al tema scuro");
  }

  // preferenza salvata (se il browser la nega, si prosegue col sistema)
  try {
    var salvato = localStorage.getItem(CHIAVE);
    if (salvato) applica(salvato);
  } catch (e) { /* localStorage non disponibile: pazienza */ }

  document.addEventListener("DOMContentLoaded", function () {
    aggiornaPulsante();

    var b = document.getElementById("cambia-tema");
    if (b) {
      b.addEventListener("click", function () {
        var nuovo = temaAttivo() === "scuro" ? "chiaro" : "scuro";
        applica(nuovo);
        try { localStorage.setItem(CHIAVE, nuovo); } catch (e) {}
      });
    }

    // torna su: compare dopo un po' di scorrimento
    var su = document.getElementById("torna-su");
    if (!su) return;
    function controlla() {
      if (window.scrollY > 400) su.classList.add("visibile");
      else su.classList.remove("visibile");
    }
    window.addEventListener("scroll", controlla, { passive: true });
    su.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    controlla();
  });
})();
