(function(window) {
  function withSocketDefaults(options) {
    return Object.assign({
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 5000,
    }, options || {});
  }

  window.GoldMonitorShell = {
    withSocketDefaults: withSocketDefaults,
  };
})(window);
