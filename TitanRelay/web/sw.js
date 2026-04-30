const CACHE_NAME = "relay-v3";
const RELAY_ROOT = "/relay";
const ASSETS = [
	`${RELAY_ROOT}`,
	`${RELAY_ROOT}/index.html`,
	`${RELAY_ROOT}/assets/app.css`,
	`${RELAY_ROOT}/assets/app.js`,
	`${RELAY_ROOT}/assets/home.js`,
	`${RELAY_ROOT}/assets/titan_relay.png`,
	`${RELAY_ROOT}/devices/pit.html`,
	`${RELAY_ROOT}/devices/ipad.html`,
	`${RELAY_ROOT}/devices/s23.html`,
	`${RELAY_ROOT}/devices/laptop.html`,
	`${RELAY_ROOT}/manifests/pit.webmanifest`,
	`${RELAY_ROOT}/manifests/ipad.webmanifest`,
	`${RELAY_ROOT}/manifests/s23.webmanifest`,
	`${RELAY_ROOT}/manifests/laptop.webmanifest`
];

self.addEventListener("install", (event) => {
	self.skipWaiting();
	event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("activate", (event) => {
	event.waitUntil(
		caches.keys().then((keys) =>
			Promise.all(keys.map((key) => (key === CACHE_NAME ? Promise.resolve() : caches.delete(key))))
		).then(() => self.clients.claim())
	);
});

self.addEventListener("fetch", (event) => {
	if (event.request.method !== "GET") {
		return;
	}
	const url = new URL(event.request.url);
	if (url.pathname.startsWith("/api/")) {
		return;
	}
	if (!url.pathname.startsWith(RELAY_ROOT)) {
		return;
	}
	event.respondWith(
		fetch(event.request)
			.then((response) => {
				const copy = response.clone();
				caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
				return response;
			})
			.catch(() => caches.match(event.request))
	);
});
