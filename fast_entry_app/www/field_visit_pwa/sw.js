const CACHE_NAME = "field-visit-pwa-v1";
const ASSETS = ["/field_visit_pwa", "/field_visit_pwa/index.html"];

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("fetch", (event) => {
    if (event.request.url.includes("/api/")) return;
    event.respondWith(
        caches.match(event.request).then((resp) => resp || fetch(event.request))
    );
});