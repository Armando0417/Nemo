(function () {
	"use strict";

	const root = document.querySelector(".relay-app");
	const API_ROOT = "/api/relay";
	const RELAY_ROOT = "/relay";
	if (!root) {
		return;
	}

	const state = {
		bootstrap: null,
		selectedTargetId: "",
		files: [],
		installPrompt: null
	};

	void init();

	async function init() {
		registerServiceWorker();
		renderShell();
		wireEvents();
		await loadBootstrap();
	}

	function renderShell() {
		root.innerHTML = `
			<section class="hero">
				<div class="hero-top">
					<div class="hero-copy">
						<div class="eyebrow">Copyparty Mailbox Relay</div>
						<h1 id="device-name">Relay</h1>
						<p id="device-tagline">Loading mailbox configuration...</p>
					</div>
					<div class="actions-row">
						<div class="top-status" id="top-status" data-ready="false">
							<span class="top-status-dot"></span>
							<span>Contacting Relay...</span>
						</div>
						<button class="btn btn-secondary hidden" id="install-btn" type="button">Install</button>
					</div>
				</div>
				<div class="nav-row">
					<div class="nav-pills" id="device-nav"></div>
					<a class="nav-link" href="/relay">All Mailboxes</a>
				</div>
				<div class="path-row" id="path-row"></div>
			</section>

			<section class="card">
				<div class="section-heading">
					<div class="stack">
						<h2>Send Payload</h2>
						<p>Choose files or a folder and Relay will create one mailbox payload in the destination inbox.</p>
					</div>
				</div>
				<div class="pill-row" id="target-list"></div>
				<div class="actions-row">
					<button class="btn btn-primary" id="pick-files-btn" type="button">Choose Files</button>
					<button class="btn btn-secondary hidden" id="pick-folder-btn" type="button">Choose Folder</button>
					<button class="btn btn-secondary hidden" id="capture-btn" type="button">Camera or Media</button>
				</div>
				<div class="input-sinks">
					<input id="file-input" type="file" multiple />
					<input id="folder-input" type="file" webkitdirectory multiple />
					<input id="capture-input" type="file" accept="image/*,video/*" capture />
				</div>
				<div id="selected-files"></div>
				<button class="btn btn-primary" id="upload-btn" type="button" disabled>Send Now</button>
				<div class="status-box" id="send-status">Choose files or a folder and a destination.</div>
			</section>

			<section class="card">
				<div class="section-heading">
					<div class="stack">
						<h2>This Inbox</h2>
						<p>Refreshing reads the mailbox from Copyparty through Relay. Downloading also moves the item into Relay Hub handoff storage.</p>
					</div>
					<button class="btn btn-secondary" id="refresh-btn" type="button">Refresh</button>
				</div>
				<ul class="inbox-list" id="inbox-list"></ul>
				<div class="status-box" id="receive-status">Inbox status will appear here.</div>
			</section>
		`;
	}

	function wireEvents() {
		get("pick-files-btn").addEventListener("click", function () {
			get("file-input").click();
		});
		get("file-input").addEventListener("change", function () {
			setSelectedEntries(get("file-input").files, false);
		});
		get("folder-input").addEventListener("change", function () {
			setSelectedEntries(get("folder-input").files, true);
		});
		get("capture-input").addEventListener("change", function () {
			setSelectedEntries(get("capture-input").files, false);
		});
		get("upload-btn").addEventListener("click", function () {
			void sendFiles();
		});
		get("refresh-btn").addEventListener("click", function () {
			void refreshInbox(true);
		});
		window.addEventListener("beforeinstallprompt", function (event) {
			event.preventDefault();
			state.installPrompt = event;
			get("install-btn").classList.remove("hidden");
		});
		get("install-btn").addEventListener("click", function () {
			void promptInstall();
		});
		if ("webkitdirectory" in get("folder-input")) {
			get("pick-folder-btn").classList.remove("hidden");
			get("pick-folder-btn").addEventListener("click", function () {
				get("folder-input").click();
			});
		}
	}

	async function loadBootstrap() {
		const deviceId = root.dataset.deviceId;
		try {
			const response = await fetch(`${API_ROOT}/bootstrap/${encodeURIComponent(deviceId)}`);
			if (!response.ok) {
				throw new Error(`Failed to load Relay config (HTTP ${response.status}).`);
			}
			state.bootstrap = await response.json();
			state.selectedTargetId =
				state.bootstrap.device.defaultTargetId ||
				(state.bootstrap.targets[0] && state.bootstrap.targets[0].id) ||
				"";
			applyBootstrap();
			await refreshInbox(false);
		} catch (error) {
			setStatus(get("top-status"), resolveErrorMessage(error), "error", false);
			setStatus(get("send-status"), resolveErrorMessage(error), "error");
			setStatus(get("receive-status"), resolveErrorMessage(error), "error");
		}
	}

	function applyBootstrap() {
		const device = state.bootstrap.device;
		const copyparty = state.bootstrap.copyparty || {};
		document.title = device.name;
		document.documentElement.style.setProperty("--accent", device.accentColor);
		document.documentElement.style.setProperty("--accent-strong", device.accentColorStrong);
		get("device-name").textContent = device.name;
		get("device-tagline").textContent = device.tagline;
		setStatus(
			get("top-status"),
			copyparty.reachable
				? `Connected through Relay to ${state.bootstrap.copypartyBaseUrl}`
				: `Copyparty not detected at ${state.bootstrap.copypartyBaseUrl}`,
			copyparty.reachable ? "ok" : "warn",
			Boolean(copyparty.reachable)
		);
		renderDeviceNav();
		renderPaths();
		renderTargets();
		renderSelection();
		if (device.capture) {
			get("capture-btn").classList.remove("hidden");
			get("capture-btn").addEventListener("click", function () {
				get("capture-input").click();
			});
		}
	}

	function renderDeviceNav() {
		const nav = get("device-nav");
		nav.innerHTML = "";
		state.bootstrap.devices.forEach(function (device) {
			const link = document.createElement("a");
			link.className = "nav-pill";
			if (device.id === state.bootstrap.device.id) {
				link.classList.add("active");
			}
			link.href = device.pagePath;
			link.innerHTML = `<strong>${escapeHtml(device.shortName)}</strong><span>${escapeHtml(device.name)}</span>`;
			nav.appendChild(link);
		});
	}

	function renderPaths() {
		const row = get("path-row");
		const device = state.bootstrap.device;
		row.innerHTML = `
			<div class="path-chip">Inbox: ${escapeHtml(device.inboxPath)}</div>
			<div class="path-chip">Dump: ${escapeHtml(device.dumpPath)}</div>
		`;
	}

	function renderTargets() {
		const targetList = get("target-list");
		targetList.innerHTML = "";
		state.bootstrap.targets.forEach(function (target) {
			const button = document.createElement("button");
			button.type = "button";
			button.className = "target-pill";
			if (target.id === state.selectedTargetId) {
				button.classList.add("active");
			}
			button.innerHTML = `<strong>${escapeHtml(target.label)}</strong><span>${escapeHtml(target.path)}</span>`;
			button.addEventListener("click", function () {
				state.selectedTargetId = target.id;
				renderTargets();
				renderSelection();
			});
			targetList.appendChild(button);
		});
	}

	function setSelectedEntries(fileList, preservePaths) {
		state.files = Array.from(fileList || []).map(function (file) {
			return {
				file: file,
				relativePath: preservePaths && file.webkitRelativePath ? file.webkitRelativePath : file.name
			};
		});
		renderSelection();
	}

	function renderSelection() {
		const selected = getSelectedTarget();
		get("upload-btn").disabled = !selected || state.files.length === 0 || !state.bootstrap;
		const host = get("selected-files");
		if (state.files.length === 0) {
			host.innerHTML = '<p class="hint">No files or folders selected yet.</p>';
			return;
		}
		const list = document.createElement("ul");
		list.className = "file-list";
		state.files.slice(0, 8).forEach(function (entry) {
			const item = document.createElement("li");
			item.className = "file-item";
			item.innerHTML =
				`<strong>${escapeHtml(entry.file.name)}</strong>` +
				`<span>${escapeHtml(entry.relativePath)} • ${formatBytes(entry.file.size)}</span>`;
			list.appendChild(item);
		});
		host.replaceChildren(list);
		if (state.files.length > 8) {
			const hint = document.createElement("p");
			hint.className = "hint";
			hint.textContent = `${state.files.length - 8} more item(s) selected.`;
			host.appendChild(hint);
		}
	}

	async function sendFiles() {
		const target = getSelectedTarget();
		if (!target) {
			setStatus(get("send-status"), "Choose a destination first.", "warn");
			return;
		}
		if (state.files.length === 0) {
			setStatus(get("send-status"), "Select at least one file or folder.", "warn");
			return;
		}
		setStatus(get("send-status"), `Preparing payload for ${target.label}...`, "busy");
		get("upload-btn").disabled = true;
		try {
			const formData = new FormData();
			formData.append("targetId", target.id);
			formData.append(
				"relativePaths",
				JSON.stringify(
					state.files.map(function (entry) {
						return entry.relativePath;
					})
				)
			);
			state.files.forEach(function (entry) {
				formData.append("file", entry.file, entry.file.name);
			});
			const response = await fetch(`${API_ROOT}/device/${encodeURIComponent(state.bootstrap.device.id)}/send`, {
				method: "POST",
				body: formData
			});
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload.error || payload.detail || `Send failed with HTTP ${response.status}.`);
			}
			clearSelection();
			await refreshInbox(false);
			if (payload.failed.length) {
				setStatus(
					get("send-status"),
					`Payload ${payload.payloadName} uploaded with ${payload.uploaded} success(es). First failure: ${payload.failed[0]}`,
					"warn"
				);
				return;
			}
			setStatus(
				get("send-status"),
				`Payload ${payload.payloadName} sent to ${payload.targetLabel}.`,
				"ok"
			);
		} catch (error) {
			setStatus(get("send-status"), resolveErrorMessage(error), "error");
			renderSelection();
		}
	}

	async function refreshInbox(showBusy) {
		if (!state.bootstrap) {
			return;
		}
		if (showBusy) {
			setStatus(get("receive-status"), "Refreshing inbox...", "busy");
		}
		try {
			const response = await fetch(`${API_ROOT}/device/${encodeURIComponent(state.bootstrap.device.id)}/inbox`);
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload.error || payload.detail || `Inbox refresh failed with HTTP ${response.status}.`);
			}
			renderInbox(payload.dirs || [], payload.files || []);
			if (payload.missing) {
				setStatus(get("receive-status"), `Inbox ${payload.inboxPath} does not exist yet.`, "warn");
				return;
			}
			const totalEntries = (payload.dirs || []).length + (payload.files || []).length;
			setStatus(
				get("receive-status"),
				totalEntries === 0
					? "Inbox ready. No payloads yet."
					: `Inbox ready. ${(payload.dirs || []).length} payload(s) and ${(payload.files || []).length} loose file(s) found.`,
				"ok"
			);
		} catch (error) {
			get("inbox-list").innerHTML = "";
			setStatus(get("receive-status"), resolveErrorMessage(error), "error");
		}
	}

	function renderInbox(dirs, files) {
		const list = get("inbox-list");
		list.innerHTML = "";
		if (dirs.length === 0 && files.length === 0) {
			list.innerHTML =
				'<li class="inbox-item"><strong>No payloads yet.</strong><span>Send something to this mailbox.</span></li>';
			return;
		}
		dirs
			.slice()
			.sort(sortByName)
			.forEach(function (directory) {
				list.appendChild(createInboxItem(directory, "payload"));
			});
		files
			.slice()
			.sort(sortByName)
			.forEach(function (file) {
				list.appendChild(createInboxItem(file, "file"));
			});
	}

	function createInboxItem(entry, kind) {
		const item = document.createElement("li");
		item.className = "inbox-item";
		const entryName = getInboxEntryName(entry) || kind;
		const label = String(entryName);
		const secondary = kind === "payload" ? "Payload folder" : formatBytes(Number(entry.sz || 0));
		item.innerHTML =
			`<strong>${escapeHtml(label)}</strong>` +
			`<span>${escapeHtml(secondary)}</span>` +
			`<div class="inbox-meta"><span>${escapeHtml(entry.dt || "Ready to download")}</span></div>`;
		const actions = item.querySelector(".inbox-meta");
		const button = document.createElement("button");
		button.type = "button";
		button.className = "btn btn-secondary";
		button.textContent = "Download + Dump";
		button.addEventListener("click", function () {
			void archiveAndDownload(entryName, kind);
		});
		actions.appendChild(button);
		return item;
	}

	async function archiveAndDownload(name, kind) {
		setStatus(get("receive-status"), `Archiving ${name}...`, "busy");
		try {
			const response = await fetch(`${API_ROOT}/device/${encodeURIComponent(state.bootstrap.device.id)}/archive`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ name: name, kind: kind })
			});
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload.error || payload.detail || `Archive failed with HTTP ${response.status}.`);
			}
			triggerDownload(payload.downloadUrl, payload.suggestedName);
			await refreshInbox(false);
			const archiveVerb = payload.archiveAction && payload.archiveAction.startsWith("copied") ? "copied" : "moved";
			setStatus(get("receive-status"), `Started download and ${archiveVerb} ${name} into Relay Hub handoff storage.`, "ok");
		} catch (error) {
			setStatus(get("receive-status"), resolveErrorMessage(error), "error");
		}
	}

	function triggerDownload(href, suggestedName) {
		const link = document.createElement("a");
		link.href = href;
		link.className = "hidden";
		if (suggestedName) {
			link.setAttribute("download", suggestedName);
		}
		document.body.appendChild(link);
		link.click();
		link.remove();
	}

	function getInboxEntryName(entry) {
		const raw =
			(entry && (entry.name || entry.href || entry.rp || entry.path || entry.file)) ||
			"";
		return decodeURIComponent(String(raw).replace(/[?#].*$/, "").replace(/\/+$/, ""));
	}

	function getSelectedTarget() {
		if (!state.bootstrap) {
			return null;
		}
		return (
			state.bootstrap.targets.find(function (target) {
				return target.id === state.selectedTargetId;
			}) || null
		);
	}

	function clearSelection() {
		state.files = [];
		get("file-input").value = "";
		get("folder-input").value = "";
		get("capture-input").value = "";
		renderSelection();
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

	async function promptInstall() {
		if (!state.installPrompt) {
			return;
		}
		await state.installPrompt.prompt();
		state.installPrompt = null;
		get("install-btn").classList.add("hidden");
	}

	function setStatus(element, text, tone, ready) {
		element.dataset.tone = tone || "";
		if (typeof ready === "boolean") {
			element.dataset.ready = ready ? "true" : "false";
		}
		const textNode = element.querySelector(".top-status-dot")
			? element.querySelector("span:last-child")
			: null;
		if (textNode) {
			textNode.textContent = text;
			return;
		}
		element.textContent = text;
	}

	function sortByName(a, b) {
		return String(a.name || "").localeCompare(String(b.name || ""));
	}

	function formatBytes(size) {
		if (!Number.isFinite(size) || size <= 0) {
			return "0 B";
		}
		if (size >= 1024 ** 3) {
			return `${(size / 1024 ** 3).toFixed(2)} GB`;
		}
		if (size >= 1024 ** 2) {
			return `${(size / 1024 ** 2).toFixed(1)} MB`;
		}
		if (size >= 1024) {
			return `${(size / 1024).toFixed(1)} KB`;
		}
		return `${size} B`;
	}

	function get(id) {
		return document.getElementById(id);
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
