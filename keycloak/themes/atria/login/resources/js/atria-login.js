/* Atria login theme — companion motion.
   Dependency-free, ~1KB. Adds three effects on top of the CSS:
     1. cursor spotlight on the glass card (--mx / --my)
     2. aurora parallax that tracks the pointer (--px / --py)
     3. staggered fade-up of the form rows (via .atria-ready + --i)
   All of it is a no-op under prefers-reduced-motion. */
(function () {
  'use strict';

  var reduce =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function ready(fn) {
    if (document.readyState !== 'loading') {
      fn();
    } else {
      document.addEventListener('DOMContentLoaded', fn);
    }
  }

  ready(function () {
    var body = document.body;
    var card =
      document.querySelector('.pf-v5-c-login__main') ||
      document.querySelector('.login-pf-page > div') ||
      document.querySelector('#kc-content-wrapper');

    // Stagger index on each form row so the CSS transition-delay steps through.
    var rows = document.querySelectorAll('.pf-v5-c-form__group, .form-group');
    for (var i = 0; i < rows.length; i++) {
      rows[i].style.setProperty('--i', String(i));
    }
    // Trigger the entrance on the next frame so the initial state paints first.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        body.classList.add('atria-ready');
      });
    });

    if (reduce) {
      return;
    }

    // Cursor spotlight on the card + subtle aurora parallax.
    var raf = 0;
    var lastX = 0;
    var lastY = 0;

    function apply() {
      raf = 0;
      if (card) {
        var r = card.getBoundingClientRect();
        var mx = ((lastX - r.left) / r.width) * 100;
        var my = ((lastY - r.top) / r.height) * 100;
        card.style.setProperty('--mx', mx.toFixed(1) + '%');
        card.style.setProperty('--my', my.toFixed(1) + '%');
      }
      var px = lastX / window.innerWidth - 0.5;
      var py = lastY / window.innerHeight - 0.5;
      body.style.setProperty('--px', px.toFixed(3));
      body.style.setProperty('--py', py.toFixed(3));
    }

    window.addEventListener(
      'pointermove',
      function (e) {
        lastX = e.clientX;
        lastY = e.clientY;
        if (!raf) {
          raf = requestAnimationFrame(apply);
        }
      },
      { passive: true }
    );
  });
})();
