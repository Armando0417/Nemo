(function () {
	"use strict";

	const grid = document.getElementById("device-grid");
	const status = document.getElementById("home-status");
	const API_ROOT = "/api/relay";
	const RELAY_ROOT = "/relay";

	void init();

	async function init() {
		registerServiceWorker();
		try {
			const response = await fetch(`${API_ROOT}/devices`);
			if (!response.ok) {
				throw new Error(`Failed to load Relay device roster (HTTP ${response.status}).`);
			}
			const payload = await response.json();
			renderDevices(payload.devices || []);
			const copyparty = payload.copyparty || {};
			status.dataset.ready = copyparty.reachable ? "true" : "false";
			status.lastElementChild.textContent = copyparty.reachable
				? `${payload.devices.length} mailbox page(s) ready. Copyparty detected at ${copyparty.baseUrl}.`
				: `${payload.devices.length} mailbox page(s) ready. Copyparty not detected${copyparty.baseUrl ? ` at ${copyparty.baseUrl}` : ""}.`;
		} catch (error) {
			status.dataset.ready = "false";
			status.lastElementChild.textContent = resolveErrorMessage(error);
		}
	}

	function renderDevices(devices) {
		grid.innerHTML = "";
		devices.forEach((device) => {
			const card = document.createElement("a");
			card.className = "device-card";
			card.href = device.pagePath;
			card.style.setProperty("--accent", device.accentColor);
			card.innerHTML =
				`<div class="device-card-tag">${escapeHtml(device.shortName)}</div>` +
				`<strong>${escapeHtml(device.name)}</strong>` +
				`<span>${escapeHtml(device.tagline || "Open this mailbox.")}</span>`;
			grid.appendChild(card);
		});
	}

	function registerServiceWorker() {
		if (!("serviceWorker" in navigator)) {
			return;
		}
		window.addEventListener("load", function () {
			navigator.serviceWorker.register(`${RELAY_ROOT}/sw.js`).catch(function () {
				// Keep the page usable if registration fails.
			});
		});
	}

	function resolveErrorMessage(error) {
		if (error instanceof Error && error.message) {
			return error.message;
		}
		return "Unexpected Relay error.";
	}

	function escapeHtml(value) {
		return String(value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}
})();
