// Live2D widget loader — uses oh-my-live2d, an actively-maintained
// wrapper around pixi-live2d-display. Picks the Pio model; the
// wrapper renders it at the bottom-right corner by default.

(function () {
  if (window.__live2dLoaded) return;
  window.__live2dLoaded = true;

  var s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/oh-my-live2d@latest';
  s.async = true;
  s.onload = function () {
    try {
      var loader = window.loadOml2d
        || (window.OML2D && window.OML2D.loadOml2d)
        || (window.oml2d && window.oml2d.loadOml2d);
      if (typeof loader !== 'function') {
        console.error('[live2d] oh-my-live2d loaded but loadOml2d API not found');
        return;
      }
      loader({
        mobileDisplay: true,
        models: [{
          name: 'pio',
          path: 'https://model.oml2d.com/Pio/model.json',
          position: [0, 40],
          scale: 0.25,
          stageStyle: { height: 300 },
        }],
        menus: { disable: true },
        tips: { idleTips: { interval: 20000 } },
      });
    } catch (err) {
      console.error('[live2d] init failed:', err);
    }
  };
  s.onerror = function (e) {
    console.error('[live2d] failed to load oh-my-live2d from jsDelivr', e);
  };
  document.head.appendChild(s);
})();
