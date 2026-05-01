<script lang="ts">
	import { browser } from '$app/environment';
	import { goto, replaceState } from '$app/navigation';
	import {
		buildCodexUrl,
		buildReaderUrl,
		buildSeriesUrl,
		resolveSeriesChapter,
		sortChapters
	} from '$lib/utils/reader';
	import { page } from '$app/state';
	import { onDestroy, onMount } from 'svelte';
	import '../../../../../app.css';

	type ReaderPage = {
		index: number;
		filename: string;
		thumbUrl: string;
		url: string;
	};

	type ChapterMeta = {
		id: number;
		title?: string;
		chapter_number?: number;
		page_count?: number;
	};

	type SeriesMeta = {
		id: number;
		title?: string;
	};

	type ReadingMode = 'horizontal' | 'vertical';
	const FLASK_URL = '/api/codex';
	const seriesId = $derived(Number(page.params.seriesId));
	const chapterParam = $derived(Number(page.params.chapterId));
	const initialPage = $derived(Number(page.params.pageIdx || 0));

	const INSPECT_STORAGE_KEY = 'cv.reader.inspect-panel.v1';
	const LEGACY_MAGNIFIER_KEY = 'cv.reader.magnifier.v1';
	const MODE_KEY = 'cv.reader.mode';
	const INSPECT_PANEL_WIDTH = 380;
	const INSPECT_PANEL_HEIGHT = 540;
	const INSPECT_PANEL_PADDING = 14;

	let currentPage = $state(0);
	let pages = $state<ReaderPage[]>([]);
	let totalPages = $state(0);
	let chapter = $state<ChapterMeta | null>(null);
	let series = $state<SeriesMeta | null>(null);
	let allChapters = $state<ChapterMeta[]>([]);
	let currentChapterId = $state<number | null>(null);
	let currentChapterNumber = $state(1);
	let nextChapterUrl = $state<string | null>(null);
	let prevChapterUrl = $state<string | null>(null);
	let isLoading = $state(true);
	let lastLoadedChapterRoute = $state('');

	let readingMode = $state<ReadingMode>('horizontal');

	let inspectPanelEnabled = $state(false);
	let inspectZoomLevel = $state(1.8);
	let ctrlPressed = $state(false);
	let drawerOpen = $state(false);
	let imgLoaded = $state(false);
	let hintShown = $state(false);

	let zoomPanelVisible = $state(false);
	let zoomPanelSrc = $state('');
	let zoomBgX = $state(0);
	let zoomBgY = $state(0);
	let zoomBgW = $state(0);
	let zoomBgH = $state(0);

	let scale = $state(1);
	let isDragging = $state(false);
	let startX = 0;
	let startY = 0;
	let translateX = $state(0);
	let translateY = $state(0);
	let img = $state<HTMLImageElement | null>(null);

	let headerVisible = $state(true);
	let hideHeaderTimer: ReturnType<typeof setTimeout> | null = null;
	let hintTimer: ReturnType<typeof setTimeout> | null = null;
	let preloadTimer: ReturnType<typeof setTimeout> | null = null;

	const isZoomed = $derived(scale > 1);

	function clamp(value: number, min: number, max: number) {
		return Math.max(min, Math.min(max, value));
	}

	function loadSettings() {
		try {
			const saved = JSON.parse(localStorage.getItem(INSPECT_STORAGE_KEY) || 'null');
			const legacy = JSON.parse(localStorage.getItem(LEGACY_MAGNIFIER_KEY) || 'null');
			inspectPanelEnabled = saved?.enabled ?? false;
			inspectZoomLevel = saved?.zoom ?? legacy?.zoom ?? 1.8;
		} catch {}

		try {
			const savedMode = localStorage.getItem(MODE_KEY);
			if (savedMode === 'vertical' || savedMode === 'horizontal') {
				readingMode = savedMode;
			}
		} catch {}
	}

	function saveInspectSettings() {
		try {
			localStorage.setItem(
				INSPECT_STORAGE_KEY,
				JSON.stringify({
					enabled: inspectPanelEnabled,
					zoom: inspectZoomLevel
				})
			);
		} catch {}
	}

	function saveReadingMode() {
		try {
			localStorage.setItem(MODE_KEY, readingMode);
		} catch {}
	}

	async function getChapterPages(chapterId: number) {
		const pagesRes = await fetch(`${FLASK_URL}/view/chapter/${chapterId}/pages`);
		const pageData = await pagesRes.json();
		return (Array.isArray(pageData) ? pageData : pageData.images || []) as string[];
	}

	async function loadChapterData() {
		isLoading = true;
		hideInspectPanel();
		imgLoaded = false;

		try {
			const [seriesRes, chaptersRes] = await Promise.all([
				fetch(`${FLASK_URL}/report/series/${seriesId}`),
				fetch(`${FLASK_URL}/report/chapters?series_id=${seriesId}`)
			]);
			series = await seriesRes.json();
			allChapters = sortChapters(await chaptersRes.json());

			const resolvedChapter = resolveSeriesChapter(allChapters, chapterParam);
			chapter = resolvedChapter?.chapter ?? null;
			currentChapterId = resolvedChapter?.chapter.id ?? null;
			currentChapterNumber = resolvedChapter ? resolvedChapter.chapterIndex + 1 : 1;
			nextChapterUrl = null;
			prevChapterUrl = null;
			pages = [];
			totalPages = 0;

			if (!resolvedChapter) {
				currentPage = 0;
				return;
			}

			if (resolvedChapter.chapterIndex < allChapters.length - 1) {
				nextChapterUrl = buildReaderUrl(seriesId, resolvedChapter.chapterIndex + 2, 0);
			}

			if (resolvedChapter.chapterIndex > 0) {
				const previousChapter = allChapters[resolvedChapter.chapterIndex - 1];
				const previousChapterLastPage = Math.max((previousChapter.page_count ?? 1) - 1, 0);
				prevChapterUrl = buildReaderUrl(
					seriesId,
					resolvedChapter.chapterIndex,
					previousChapterLastPage
				);
			}

			const pageList = await getChapterPages(resolvedChapter.chapter.id);

			pages = pageList.map((filename, index) => ({
				index,
				filename,
				thumbUrl: `${FLASK_URL}/view/chapter/${resolvedChapter.chapter.id}/page/${filename}/thumb`,
				url: `${FLASK_URL}/view/chapter/${resolvedChapter.chapter.id}/page/${filename}`
			}));
			totalPages = pageList.length;
			currentPage = clamp(initialPage, 0, Math.max(pages.length - 1, 0));
		} catch (error) {
			console.error('Failed to load chapter', error);
		} finally {
			isLoading = false;
		}
	}

	function showHeader() {
		headerVisible = true;
		if (hideHeaderTimer) {
			clearTimeout(hideHeaderTimer);
		}

		hideHeaderTimer = setTimeout(() => {
			headerVisible = false;
		}, 2500);
	}

	function jumpToPage(event: MouseEvent) {
		if (!totalPages) {
			return;
		}

		const track = event.currentTarget as HTMLElement;
		const rect = track.getBoundingClientRect();
		const ratio = (event.clientX - rect.left) / rect.width;
		imgLoaded = false;
		currentPage = Math.min(Math.floor(ratio * totalPages), totalPages - 1);
		resetZoom();
		hideInspectPanel();
	}

	function goToPage(pageIndex: number) {
		if (!totalPages) {
			return;
		}

		const targetPage = clamp(pageIndex, 0, totalPages - 1);
		if (readingMode === 'horizontal' && targetPage !== currentPage) {
			imgLoaded = false;
		}
		currentPage = targetPage;
		resetZoom();
		hideInspectPanel();
		drawerOpen = false;

		if (browser && readingMode === 'vertical') {
			requestAnimationFrame(() => {
				const pageEl = document.querySelector(`[data-page="${targetPage}"]`);
				pageEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
			});
		}
	}

	function goToChapter(chapterNumber: number, pageIndex = 0) {
		drawerOpen = false;

		if (chapterNumber === currentChapterNumber) {
			goToPage(pageIndex);
			return;
		}

		goToUrl(buildReaderUrl(seriesId, chapterNumber, pageIndex));
	}

	function setReadingMode(mode: ReadingMode) {
		if (readingMode === mode) {
			return;
		}

		readingMode = mode;
		saveReadingMode();
		resetZoom();
		hideInspectPanel();
		drawerOpen = false;
	}

	function goToUrl(url: string) {
		if (!browser) {
			return;
		}
		void goto(url);
	}

	function goNext() {
		hideInspectPanel();

		if (readingMode === 'vertical') {
			if (!browser) {
				return;
			}
			const nextPageEl = document.querySelector(`[data-page="${currentPage + 1}"]`);
			if (nextPageEl) {
				nextPageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
				currentPage += 1;
			} else if (nextChapterUrl) {
				goToUrl(nextChapterUrl);
			}
			return;
		}

		if (currentPage < totalPages - 1) {
			imgLoaded = false;
			currentPage += 1;
			resetZoom();
		} else if (nextChapterUrl) {
			goToUrl(nextChapterUrl);
		}
	}

	function goPrev() {
		hideInspectPanel();

		if (readingMode === 'vertical') {
			if (!browser) {
				return;
			}
			const prevPageEl = document.querySelector(`[data-page="${currentPage - 1}"]`);
			if (prevPageEl) {
				prevPageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
				currentPage -= 1;
			} else if (prevChapterUrl) {
				goToUrl(prevChapterUrl);
			}
			return;
		}

		if (currentPage > 0) {
			imgLoaded = false;
			currentPage -= 1;
			resetZoom();
		} else if (prevChapterUrl) {
			goToUrl(prevChapterUrl);
		}
	}

	function exitReader() {
		goToUrl(buildSeriesUrl(seriesId));
	}

	function exitToEntryPage() {
		goToUrl(buildCodexUrl('/'));
	}

	function resetZoom() {
		scale = 1;
		translateX = 0;
		translateY = 0;
		updateTransform();
	}

	function isInspectActive() {
		return (inspectPanelEnabled || ctrlPressed) && imgLoaded;
	}

	function getHoveredImage(event: MouseEvent) {
		if (readingMode === 'horizontal') {
			return img;
		}

		const target = event.target;
		if (target instanceof HTMLImageElement && target.classList.contains('vertical-page')) {
			return target;
		}

		return null;
	}

	function updateInspectPanel(event: MouseEvent) {
		if (!isInspectActive()) {
			hideInspectPanel();
			return;
		}

		const targetImg = getHoveredImage(event);
		if (!targetImg) {
			hideInspectPanel();
			return;
		}

		const imageRect = targetImg.getBoundingClientRect();
		const overImage =
			event.clientX >= imageRect.left &&
			event.clientX <= imageRect.right &&
			event.clientY >= imageRect.top &&
			event.clientY <= imageRect.bottom;

		if (!overImage) {
			hideInspectPanel();
			return;
		}

		const xInImage = clamp(event.clientX - imageRect.left, 0, imageRect.width);
		const yInImage = clamp(event.clientY - imageRect.top, 0, imageRect.height);
		const innerWidth = INSPECT_PANEL_WIDTH - INSPECT_PANEL_PADDING * 2;
		const innerHeight = INSPECT_PANEL_HEIGHT - INSPECT_PANEL_PADDING * 2 - 28;
		const backgroundWidth = Math.round(imageRect.width * inspectZoomLevel);
		const backgroundHeight = Math.round(imageRect.height * inspectZoomLevel);
		const minBgX = Math.min(innerWidth - backgroundWidth, 0);
		const minBgY = Math.min(innerHeight - backgroundHeight, 0);

		zoomBgX = clamp(
			Math.round(-(xInImage * inspectZoomLevel) + innerWidth / 2),
			minBgX,
			0
		);
		zoomBgY = clamp(
			Math.round(-(yInImage * inspectZoomLevel) + innerHeight / 2),
			minBgY,
			0
		);
		zoomBgW = backgroundWidth;
		zoomBgH = backgroundHeight;
		zoomPanelSrc = targetImg.src;
		zoomPanelVisible = true;
	}

	function hideInspectPanel() {
		zoomPanelVisible = false;
	}

	function toggleInspectPanel() {
		inspectPanelEnabled = !inspectPanelEnabled;
		saveInspectSettings();
		if (!inspectPanelEnabled && !ctrlPressed) {
			hideInspectPanel();
		}
	}

	function toggleDrawer() {
		drawerOpen = !drawerOpen;
	}

	function showHint() {
		if (hintShown) {
			return;
		}

		hintShown = true;
		if (hintTimer) {
			clearTimeout(hintTimer);
		}

		hintTimer = setTimeout(() => {
			hintShown = false;
		}, 3200);
	}

	function handleWheel(event: WheelEvent) {
		if (readingMode === 'vertical' || ctrlPressed) {
			return;
		}

		event.preventDefault();
		const delta = event.deltaY * -0.001;
		scale = Math.min(Math.max(1, scale + delta), 4);
		updateTransform();
	}

	function handleMouseDown(event: MouseEvent) {
		if (readingMode === 'vertical' || ctrlPressed || event.button !== 0) {
			return;
		}

		if (scale > 1) {
			event.preventDefault();
			isDragging = true;
			startX = event.clientX - translateX;
			startY = event.clientY - translateY;
		}
	}

	function handleMouseUp() {
		isDragging = false;
	}

	function handleMouseMove(event: MouseEvent) {
		updateInspectPanel(event);
		showHeader();

		if (!isDragging) {
			return;
		}

		event.preventDefault();
		translateX = event.clientX - startX;
		translateY = event.clientY - startY;
		updateTransform();
	}

	function handleViewerLeave() {
		isDragging = false;
		hideInspectPanel();
	}

	function handleDblClick(event: MouseEvent) {
		if (readingMode === 'vertical' || ctrlPressed) {
			return;
		}

		event.preventDefault();
		if (scale > 1) {
			resetZoom();
			return;
		}

		scale = 2;
		translateX = 0;
		translateY = 0;
		updateTransform();
	}

	function updateTransform() {
		if (img && readingMode === 'horizontal') {
			img.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Control') {
			ctrlPressed = true;
		}

		if (event.key === 'ArrowRight' || event.key === ' ') {
			event.preventDefault();
			goNext();
		}

		if (event.key === 'ArrowLeft') {
			event.preventDefault();
			goPrev();
		}

		if (!event.repeat && (event.key === 'm' || event.key === 'M')) {
			toggleInspectPanel();
		}

		if (event.key === 'Escape') {
			if (drawerOpen) {
				toggleDrawer();
			} else {
				exitToEntryPage();
			}
		}
	}

	function handleKeyup(event: KeyboardEvent) {
		if (event.key === 'Control') {
			ctrlPressed = false;
			if (!inspectPanelEnabled) {
				hideInspectPanel();
			}
		}
	}

	function handleImgLoad() {
		imgLoaded = true;
		if (!inspectPanelEnabled) {
			setTimeout(showHint, 800);
		}
	}

	onMount(() => {
		loadSettings();
		showHeader();
		document.body.style.overflow = 'hidden';
		document.body.style.background = '#09090b';
	});

	onDestroy(() => {
		if (hideHeaderTimer) {
			clearTimeout(hideHeaderTimer);
		}

		if (hintTimer) {
			clearTimeout(hintTimer);
		}
		if (preloadTimer) {
			clearTimeout(preloadTimer);
		}
		if (browser) {
			document.body.style.overflow = '';
			document.body.style.background = '';
		}
	});

	$effect(() => {
		if (browser) {
			const routeKey = `${seriesId}:${chapterParam}`;
			if (routeKey !== lastLoadedChapterRoute) {
				lastLoadedChapterRoute = routeKey;
				imgLoaded = false;
				currentPage = initialPage;
				loadChapterData();
			}
		}
	});

	$effect(() => {
		if (browser && currentPage >= 0 && !isLoading && currentChapterId) {
			replaceState(buildReaderUrl(seriesId, currentChapterNumber, currentPage), {});
		}
	});

	$effect(() => {
		if (readingMode === 'vertical' && img) {
			resetZoom();
			img.style.transform = '';
		}
	});

	$effect(() => {
		if (!browser || readingMode !== 'horizontal' || !imgLoaded || currentPage >= totalPages - 1) {
			return;
		}

		const nextPageUrl = pages[currentPage + 1]?.url;
		if (!nextPageUrl) {
			return;
		}

		preloadTimer = setTimeout(() => {
			const nextImg = new Image();
			nextImg.decoding = 'async';
			nextImg.src = nextPageUrl;
		}, 140);

		return () => {
			if (preloadTimer) {
				clearTimeout(preloadTimer);
				preloadTimer = null;
			}
		};
	});
</script>

<svelte:window
	onkeydown={handleKeydown}
	onkeyup={handleKeyup}
	onmouseup={handleMouseUp}
	onmousemove={handleMouseMove}
/>

<div class="drawer">
	<input id="settings-drawer" type="checkbox" class="drawer-toggle" bind:checked={drawerOpen} />

	<div class="drawer-content">
		<div class="reader-root {readingMode}">
			<div class="reader-header" class:hidden={!headerVisible}>
				<button
					class="header-btn header-back"
					type="button"
					onclick={exitReader}
					title="Back to series"
					aria-label="Back to series"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						width="18"
						height="18"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="2"
						stroke="currentColor"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
					</svg>
				</button>

				<div class="header-info">
					<span class="header-series">{series?.title || ''}</span>
					{#if chapter?.title}
						<span class="header-sep">›</span>
						<span class="header-chapter">{chapter.title}</span>
					{/if}
				</div>

				<div class="header-right">
					{#if readingMode === 'horizontal' && totalPages > 0}
						<span class="header-page">{currentPage + 1} / {totalPages}</span>
					{/if}

					{#if prevChapterUrl}
						<a
							href={prevChapterUrl}
							class="header-btn"
							title="Previous chapter"
							aria-label="Previous chapter"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="16"
								height="16"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="2"
								stroke="currentColor"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="m18.75 4.5-7.5 7.5 7.5 7.5m-6-15L6.75 12l6 6" />
							</svg>
						</a>
					{/if}

					{#if nextChapterUrl}
						<a
							href={nextChapterUrl}
							class="header-btn"
							title="Next chapter"
							aria-label="Next chapter"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								width="16"
								height="16"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="2"
								stroke="currentColor"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="m5.25 4.5 7.5 7.5-7.5 7.5m6-15 7.5 7.5-7.5 7.5" />
							</svg>
						</a>
					{/if}

					<label
						for="settings-drawer"
						class="header-btn"
						title="Settings"
						aria-label="Open reader settings"
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							width="18"
							height="18"
							fill="none"
							viewBox="0 0 24 24"
							stroke-width="1.5"
							stroke="currentColor"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75"
							/>
						</svg>
					</label>
				</div>
			</div>

			{#if readingMode === 'horizontal'}
				<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
				<div
					class="viewer-container"
					class:zoomed={isZoomed}
					onwheel={handleWheel}
					onmousedown={handleMouseDown}
					onmouseleave={handleViewerLeave}
					ondblclick={handleDblClick}
					role="region"
					aria-label="Manga reader"
				>
					{#if !isLoading && pages.length > 0}
						{#key pages[currentPage]?.url}
							<img
								bind:this={img}
								class="manga-page"
								src={pages[currentPage]?.url}
								alt="Page {currentPage + 1}"
								draggable="false"
								decoding="async"
								fetchpriority="high"
								onload={handleImgLoad}
							/>
						{/key}
					{/if}
				</div>

				<button
					class="nav-zone left {currentPage === 0 && !prevChapterUrl ? 'disabled' : ''}"
					type="button"
					onclick={goPrev}
					title="Previous page"
					aria-label="Previous page"
				>
					<span class="nav-icon">‹</span>
				</button>
				<button
					class="nav-zone right {currentPage === totalPages - 1 && !nextChapterUrl
						? 'disabled'
						: ''}"
					type="button"
					onclick={goNext}
					title="Next page"
					aria-label="Next page"
				>
					<span class="nav-icon">›</span>
				</button>
			{:else}
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div class="vertical-container" onmouseleave={handleViewerLeave}>
					{#if !isLoading}
						{#each pages as entry, index}
							<img
								data-page={index}
								class="vertical-page"
								src={entry.url}
								alt="Page {index + 1}"
								loading="lazy"
								onload={handleImgLoad}
							/>
						{/each}
					{/if}
				</div>
			{/if}

			<div
				class="inspect-panel"
				class:visible={zoomPanelVisible}
				aria-hidden={!zoomPanelVisible}
			>
				<div class="inspect-panel-head">
					<span>Inspect</span>
					<span>{inspectZoomLevel.toFixed(1)}x</span>
				</div>
				<div class="inspect-panel-body">
					<div
						class="inspect-panel-media"
						style={`background-image: url('${zoomPanelSrc}'); background-position: ${zoomBgX}px ${zoomBgY}px; background-size: ${zoomBgW}px ${zoomBgH}px;`}
					></div>
				</div>
			</div>

			{#if readingMode === 'horizontal' && totalPages > 0}
				<button
					class="progress-track"
					class:hidden={!headerVisible}
					type="button"
					onclick={jumpToPage}
					title="Click to jump to page"
					aria-label="Jump to page"
				>
					<div class="progress-fill" style="width: {((currentPage + 1) / totalPages) * 100}%"></div>
				</button>
			{/if}

			{#if hintShown}
				<div class="hint-toast visible">
					<kbd>Ctrl</kbd> to inspect&nbsp;·&nbsp;<kbd>M</kbd> to pin
				</div>
			{/if}
		</div>
	</div>

	<div class="drawer-side z-50">
		<label for="settings-drawer" aria-label="close sidebar" class="drawer-overlay"></label>
		<div class="reader-sidebar menu bg-base-200 text-base-content min-h-full gap-4 overflow-y-auto p-4">
			<div>
				<div class="text-xs font-semibold tracking-[0.24em] uppercase opacity-50">Reader</div>
				<h2 class="mt-1.5 text-xl font-bold">Navigation</h2>
			</div>

			<div class="bg-base-300 rounded-2xl p-3.5">
				<div class="text-xs opacity-60">Now Reading</div>
				<div class="mt-1 font-bold">{series?.title || 'Loading...'}</div>
				<div class="text-sm leading-5 opacity-80">
					{chapter?.title || `Chapter ${currentChapterNumber}`}
				</div>
				<div class="mt-2.5 flex items-center justify-between text-xs opacity-70">
					<span>Chapter {currentChapterNumber} / {allChapters.length || '...'}</span>
					<span>Page {totalPages ? currentPage + 1 : 0} / {totalPages}</span>
				</div>
			</div>

			<div class="rounded-2xl border border-white/5 bg-black/10 p-3">
				<div class="mb-2.5 flex items-center justify-between">
					<div>
						<div class="text-sm font-semibold">Chapters</div>
						<div class="text-xs opacity-60">Jump anywhere in the series</div>
					</div>
					<span class="badge badge-ghost badge-sm">{allChapters.length}</span>
				</div>

				<div class="max-h-56 space-y-1.5 overflow-y-auto pr-1">
					{#each allChapters as chapterEntry, index}
						<button
							type="button"
							class="w-full rounded-xl border px-3 py-2.5 text-left transition-all {currentChapterNumber === index + 1
								? 'border-white/10 bg-base-100 shadow-sm'
								: 'border-transparent bg-base-300/60 hover:bg-base-300'}"
							onclick={() => goToChapter(index + 1)}
						>
							<div class="flex items-start gap-2.5">
								<span class="min-w-8 text-xs font-semibold uppercase opacity-50">
									{index + 1}
								</span>
								<div class="min-w-0 flex-1">
									<div class="truncate text-sm font-semibold">
										{chapterEntry.title || `Chapter ${chapterEntry.chapter_number ?? index + 1}`}
									</div>
									<div class="mt-0.5 text-xs opacity-60">
										{chapterEntry.page_count || 0} pages
									</div>
								</div>
							</div>
						</button>
					{/each}
				</div>
			</div>

			<div class="rounded-2xl border border-white/5 bg-black/10 p-3">
				<div class="mb-2.5 flex items-center justify-between">
					<div>
						<div class="text-sm font-semibold">Page Scrubber</div>
						<div class="text-xs opacity-60">Thumbnail jump for this chapter</div>
					</div>
					<span class="badge badge-ghost badge-sm">{totalPages}</span>
				</div>

				<div class="grid max-h-[32vh] grid-cols-2 gap-2 overflow-y-auto pr-1">
					{#each pages as entry}
						<button
							type="button"
							class="overflow-hidden rounded-xl border transition-all {currentPage === entry.index
								? 'border-white/20 bg-base-100 shadow-sm'
								: 'border-transparent bg-base-300/60 hover:bg-base-300'}"
							onclick={() => goToPage(entry.index)}
						>
							<img
								src={entry.thumbUrl}
								alt={`Page ${entry.index + 1}`}
								loading="lazy"
								class="aspect-[3/4] w-full object-cover"
							/>
							<div class="flex items-center justify-between px-2.5 py-2 text-[11px]">
								<span>Page {entry.index + 1}</span>
								{#if currentPage === entry.index}
									<span class="font-semibold">Now</span>
								{/if}
							</div>
						</button>
					{/each}
				</div>
			</div>

			<div class="rounded-2xl border border-white/5 bg-black/10 p-3.5">
				<div class="mb-3 text-sm font-semibold">Reader Settings</div>

				<div class="mb-4">
					<div class="label">
						<span class="label-text font-semibold">Reading Mode</span>
					</div>
					<div class="join w-full">
						<button
							class="btn join-item flex-1 {readingMode === 'horizontal' ? 'btn-active' : ''}"
							type="button"
							onclick={() => setReadingMode('horizontal')}
						>
							← → Horizontal
						</button>
						<button
							class="btn join-item flex-1 {readingMode === 'vertical' ? 'btn-active' : ''}"
							type="button"
							onclick={() => setReadingMode('vertical')}
						>
							↑ ↓ Vertical
						</button>
					</div>
				</div>

				<div class="mb-4">
					<label class="label cursor-pointer">
						<span class="label-text font-semibold">Inspect Panel</span>
						<input
							type="checkbox"
							class="toggle toggle-primary"
							bind:checked={inspectPanelEnabled}
							onchange={saveInspectSettings}
						/>
					</label>
				</div>

				<div class="mb-4">
					<label class="label" for="inspect-zoom-range">
						<span class="label-text font-semibold">Inspect Zoom</span>
						<span class="label-text-alt">{inspectZoomLevel.toFixed(1)}x</span>
					</label>
					<input
						id="inspect-zoom-range"
						type="range"
						min="1.3"
						max="3.5"
						step="0.1"
						bind:value={inspectZoomLevel}
						class="range range-primary"
						oninput={saveInspectSettings}
					/>
				</div>

				<div class="bg-base-300 rounded-xl p-3 text-sm leading-6 opacity-80">
					<div>Mouse wheel zooms the page.</div>
					<div>Drag the page while zoomed in to pan.</div>
					<div>Hold <kbd>Ctrl</kbd> to inspect or press <kbd>M</kbd> to keep the panel on.</div>
				</div>
			</div>

			<div class="flex gap-2">
				<button
					class="btn btn-outline flex-1 {currentPage === 0 && !prevChapterUrl ? 'btn-disabled' : ''}"
					type="button"
					onclick={goPrev}
				>
					◀ Prev
				</button>
				<button
					class="btn btn-outline flex-1 {currentPage === totalPages - 1 && !nextChapterUrl
						? 'btn-disabled'
						: ''}"
					type="button"
					onclick={goNext}
				>
					Next ▶
				</button>
			</div>

			<button class="btn btn-error btn-block" type="button" onclick={exitReader}>Back to Series</button>
		</div>
	</div>
</div>

<style>
	.reader-root {
		position: fixed;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #e4e4e7;
		background:
			radial-gradient(circle at top, rgba(82, 82, 91, 0.22), transparent 36%),
			linear-gradient(180deg, #09090b 0%, #111113 100%);
	}

	.reader-root.vertical {
		overflow-y: auto;
		align-items: flex-start;
	}

	.viewer-container {
		position: relative;
		display: flex;
		width: 100%;
		height: 100%;
		align-items: center;
		justify-content: center;
		padding: 64px 8vw 36px;
		box-sizing: border-box;
		cursor: default;
	}

	.viewer-container.zoomed {
		cursor: grab;
	}

	.viewer-container.zoomed:active {
		cursor: grabbing;
	}

	.manga-page {
		width: auto;
		height: auto;
		max-width: min(100%, 1100px);
		max-height: calc(100vh - 118px);
		border-radius: 12px;
		background: #151518;
		box-shadow:
			0 28px 80px rgba(0, 0, 0, 0.45),
			0 0 0 1px rgba(255, 255, 255, 0.06);
		transition: transform 0.1s ease-out;
		transform-origin: center center;
		user-select: none;
		-webkit-user-drag: none;
	}

	.vertical-container {
		width: 100%;
		max-width: 1080px;
		margin: 0 auto;
		padding: 80px 24px 32px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 16px;
	}

	.vertical-page {
		width: min(100%, 980px);
		height: auto;
		display: block;
		border-radius: 10px;
		background: #151518;
		box-shadow:
			0 24px 60px rgba(0, 0, 0, 0.35),
			0 0 0 1px rgba(255, 255, 255, 0.06);
	}

	.nav-zone {
		position: fixed;
		top: 0;
		bottom: 0;
		width: 18%;
		z-index: 40;
		display: flex;
		align-items: center;
		background: none;
		border: none;
		color: inherit;
		cursor: pointer;
		transition: background 0.2s ease;
	}

	.nav-zone.left {
		left: 0;
		justify-content: flex-start;
		padding-left: 18px;
	}

	.nav-zone.right {
		right: 0;
		justify-content: flex-end;
		padding-right: 18px;
	}

	.nav-zone:hover {
		background: linear-gradient(to right, rgba(255, 255, 255, 0.03), transparent);
	}

	.nav-zone.right:hover {
		background: linear-gradient(to left, rgba(255, 255, 255, 0.03), transparent);
	}

	.nav-zone.disabled {
		pointer-events: none;
		opacity: 0.28;
	}

	.nav-icon {
		opacity: 0.09;
		font-size: 46px;
		line-height: 1;
		color: #fff;
		text-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
		transition: opacity 0.2s ease;
	}

	.nav-zone:hover .nav-icon {
		opacity: 0.45;
	}

	.reader-root.vertical .nav-zone {
		display: none;
	}

	.reader-header {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		z-index: 50;
		height: 54px;
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 0 10px;
		background: linear-gradient(to bottom, rgba(0, 0, 0, 0.84) 0%, transparent 100%);
		transition: opacity 0.35s ease;
	}

	.reader-header.hidden {
		opacity: 0;
		pointer-events: none;
	}

	.header-info {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		gap: 6px;
		overflow: hidden;
		font-size: 13px;
	}

	.header-series {
		max-width: 220px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-weight: 600;
		color: #d4d4d8;
	}

	.header-sep {
		flex-shrink: 0;
		color: #52525b;
	}

	.header-chapter {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: #a1a1aa;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 4px;
		flex-shrink: 0;
	}

	.header-page {
		padding: 0 8px;
		font-size: 13px;
		color: #a1a1aa;
		font-variant-numeric: tabular-nums;
	}

	.header-btn {
		width: 36px;
		height: 36px;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		border: none;
		border-radius: 10px;
		background: none;
		color: #b4b4bd;
		text-decoration: none;
		cursor: pointer;
		transition:
			background 0.15s ease,
			color 0.15s ease;
	}

	.header-btn:hover {
		background: rgba(255, 255, 255, 0.1);
		color: #fff;
	}

	.inspect-panel {
		position: fixed;
		top: 72px;
		right: 20px;
		z-index: 60;
		width: min(460px, calc(100vw - 40px));
		height: 560px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 14px;
		border-radius: 20px;
		background: rgba(12, 12, 15, 0.92);
		border: 1px solid rgba(255, 255, 255, 0.1);
		box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
		backdrop-filter: blur(14px);
		pointer-events: none;
		opacity: 0;
		transform: translateX(18px);
		transition:
			opacity 0.18s ease,
			transform 0.18s ease;
	}

	.inspect-panel.visible {
		opacity: 1;
		transform: translateX(0);
	}

	.inspect-panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		font-size: 11px;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: #a1a1aa;
	}

	.inspect-panel-body {
		position: relative;
		flex: 1;
		overflow: hidden;
		border-radius: 14px;
		background: linear-gradient(180deg, #17171b 0%, #0f0f12 100%);
		border: 1px solid rgba(255, 255, 255, 0.08);
	}

	.inspect-panel-body::after {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: inherit;
		box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
	}

	.inspect-panel-media {
		position: absolute;
		inset: 0;
		background-repeat: no-repeat;
	}

	.progress-track {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 50;
		height: 4px;
		padding: 0;
		background: rgba(255, 255, 255, 0.1);
		border: none;
		cursor: pointer;
		transition:
			height 0.2s ease,
			opacity 0.35s ease;
	}

	.progress-track:hover {
		height: 10px;
	}

	.progress-track.hidden {
		opacity: 0;
		pointer-events: none;
	}

	.progress-fill {
		height: 100%;
		background: rgba(255, 255, 255, 0.58);
		transition: width 0.15s ease;
		pointer-events: none;
	}

	.hint-toast {
		position: fixed;
		right: 20px;
		bottom: 24px;
		z-index: 100;
		max-width: min(360px, calc(100vw - 32px));
		padding: 8px 16px;
		border: 1px solid #303036;
		border-radius: 10px;
		background: rgba(17, 17, 20, 0.95);
		color: #a1a1aa;
		font-size: 12px;
		opacity: 0;
		transform: translateY(8px);
		transition:
			opacity 0.3s ease,
			transform 0.3s ease;
		pointer-events: none;
	}

	.hint-toast.visible {
		opacity: 1;
		transform: translateY(0);
	}

	.hint-toast kbd {
		margin: 0 2px;
		padding: 2px 6px;
		border-radius: 6px;
		background: #27272a;
		font-family: monospace;
	}

	.reader-sidebar {
		width: min(22.5rem, calc(100vw - 1rem));
	}

	.reader-root.vertical::-webkit-scrollbar {
		width: 8px;
	}

	.reader-root.vertical::-webkit-scrollbar-track {
		background: #111113;
	}

	.reader-root.vertical::-webkit-scrollbar-thumb {
		background: #2f2f35;
		border-radius: 999px;
	}

	.reader-root.vertical::-webkit-scrollbar-thumb:hover {
		background: #3f3f46;
	}

	@media (max-width: 960px) {
		.viewer-container {
			padding-inline: 24px;
		}

		.inspect-panel {
			top: 68px;
			right: 14px;
			width: min(360px, calc(100vw - 28px));
			height: 470px;
		}

		.nav-zone {
			width: 22%;
		}

		.reader-sidebar {
			width: min(20.5rem, calc(100vw - 0.75rem));
		}

		.hint-toast {
			right: 12px;
			bottom: 18px;
			max-width: min(300px, calc(100vw - 24px));
			padding: 7px 12px;
			font-size: 11px;
		}
	}
</style>
