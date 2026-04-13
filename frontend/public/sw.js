// Unregister any stale service workers on this origin
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    self.registration.unregister().then(() =>
      self.clients.matchAll({ type: "window" })
    ).then((clients) => {
      clients.forEach((c) => c.navigate(c.url));
    })
  );
});
