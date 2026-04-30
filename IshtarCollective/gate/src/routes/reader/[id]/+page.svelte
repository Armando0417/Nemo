<script lang="ts">
	import { buildGalleryPageApiUrl, buildGalleryPagesApiUrl, buildGalleryUrl } from '$lib/paths';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';

	type ReaderData = {
		title: string;
		pages: string[];
	};
	const galleryId = page.params.id ?? '';

	let galleryData = $state<ReaderData>({ title: '', pages: [] });
	let currentPage = $state(0);
	let isLoading = $state(true);
	let imageLoading = $state(true);
	let fitMode = $state<'contain' | 'cover'>('contain');
	let showUI = $state(false);
	let atEdge = $state<'start' | 'end' | null>(null);

	let uiTimeout = 0;
	let edgeTimeout = 0;

	let progress = $derived(
		galleryData.pages.length > 1 ? (currentPage / (galleryData.pages.length - 1)) * 100 : 0
	);

	function nextPage() {
		if (currentPage < galleryData.pages.length - 1) {
			currentPage += 1;
			imageLoading = true;
			scheduleHideUI();
			return;
		}

		flashEdge('end');
	}

	function prevPage() {
		if (currentPage > 0) {
			currentPage -= 1;
			imageLoading = true;
			scheduleHideUI();
			return;
		}

		flashEdge('start');
	}

	function goToPage(pageNumber: number) {
		if (pageNumber >= 0 && pageNumber < galleryData.pages.length) {
			currentPage = pageNumber;
			imageLoading = true;
		}
	}

	function toggleFit() {
		fitMode = fitMode === 'contain' ? 'cover' : 'contain';
	}

	function flashEdge(side: 'start' | 'end') {
		atEdge = side;
		clearTimeout(edgeTimeout);
		edgeTimeout = window.setTimeout(() => {
			atEdge = null;
		}, 400);
		navigator.vibrate?.(30);
	}

	function scheduleHideUI() {
		clearTimeout(uiTimeout);
		uiTimeout = window.setTimeout(() => {
			showUI = false;
		}, 2500);
	}

	function toggleUI() {
		showUI = !showUI;
		if (showUI) {
			scheduleHideUI();
		} else {
			clearTimeout(uiTimeout);
		}
	}

	function handleKeyPress(event: KeyboardEvent) {
		if (event.key === 'ArrowRight' || event.key === 'd') {
			nextPage();
		} else if (event.key === 'ArrowLeft' || event.key === 'a') {
			prevPage();
		} else if (event.key === 'f') {
			toggleFit();
		} else if (event.key === ' ') {
			event.preventDefault();
			toggleUI();
		} else if (event.key === 'Escape') {
			void goto(buildGalleryUrl(galleryId));
		}
	}

	function handleImageLoad() {
		imageLoading = false;
	}

	function handleTap(event: MouseEvent | TouchEvent) {
		const target = event.target;
		if (!(target instanceof HTMLElement) || target.closest('.reader-controls')) {
			return;
		}

		const width = window.innerWidth;
		const clientX = 'touches' in event ? event.changedTouches[0].clientX : event.clientX;

		if (clientX < width * 0.25) {
			prevPage();
		} else if (clientX > width * 0.4) {
			nextPage();
		} else {
			toggleUI();
		}
	}

	let touchStartX = 0;
	let touchStartY = 0;
	let touchStartTime = 0;

	function handleTouchStart(event: TouchEvent) {
		touchStartX = event.touches[0].clientX;
		touchStartY = event.touches[0].clientY;
		touchStartTime = Date.now();
	}

	function handleTouchEnd(event: TouchEvent) {
		const dx = event.changedTouches[0].clientX - touchStartX;
		const dy = event.changedTouches[0].clientY - touchStartY;
		const dt = Date.now() - touchStartTime;

		if (touchStartX < 20 || touchStartX > window.innerWidth - 20) {
			return;
		}

		if (Math.abs(dx) > Math.abs(dy) * 1.5 && Math.abs(dx) > 40 && dt < 300) {
			if (dx < 0) {
				nextPage();
			} else {
				prevPage();
			}

			event.preventDefault();
		}
	}

	$effect(() => {
		if (galleryData.pages.length === 0) {
			return;
		}

		for (const index of [currentPage + 1, currentPage + 2, currentPage - 1]) {
			if (index >= 0 && index < galleryData.pages.length) {
				const img = new Image();
				img.src = buildGalleryPageApiUrl(galleryId, galleryData.pages[index]);
			}
		}
	});

	onMount(() => {
		void (async () => {
			try {
				const res = await fetch(buildGalleryPagesApiUrl(galleryId));
				if (!res.ok) {
					throw new Error(`Request failed with ${res.status}`);
				}

				galleryData = (await res.json()) as ReaderData;
			} catch (error) {
				console.error('Failed to load gallery', error);
				galleryData = { title: '', pages: [] };
			} finally {
				isLoading = false;
				imageLoading = false;
			}
		})();

		window.addEventListener('keydown', handleKeyPress);

		return () => {
			window.removeEventListener('keydown', handleKeyPress);
			clearTimeout(uiTimeout);
			clearTimeout(edgeTimeout);
		};
	});
</script>

<svelte:head>
	<title>{galleryData.title || 'Reader'}</title>
	<meta
		name="viewport"
		content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0, viewport-fit=cover"
	/>
	<meta name="theme-color" content="#000000" />
</svelte:head>

<div
	data-theme="tomb"
	class="fixed inset-0 h-[100dvh] w-screen select-none overflow-hidden"
	style="background: #000; touch-action: pan-y;"
>
	{#if atEdge === 'start'}
		<div
			class="pointer-events-none absolute inset-y-0 left-0 z-[60] w-1"
			style="background: var(--tomb-gold); opacity: 0.6; animation: edgeFade 0.4s ease-out forwards;"
		></div>
	{/if}
	{#if atEdge === 'end'}
		<div
			class="pointer-events-none absolute inset-y-0 right-0 z-[60] w-1"
			style="background: var(--tomb-gold); opacity: 0.6; animation: edgeFade 0.4s ease-out forwards;"
		></div>
	{/if}

	<div class="pointer-events-none absolute top-0 right-0 left-0 z-[55] h-[2px]" style="background: rgb(255 255 255 / 5%);">
		<div
			class="h-full transition-all duration-200 ease-out"
			style={`width: ${progress}%; background: var(--tomb-gold); opacity: 0.7;`}
		></div>
	</div>

	<div
		class="reader-controls absolute top-0 right-0 left-0 z-50"
		style={`transform: translateY(${showUI ? '0' : '-100%'}); transition: transform 0.25s ease; pointer-events: ${
			showUI ? 'auto' : 'none'
		};`}
	>
		<div
			class="flex h-14 items-center px-3"
			style="background: rgb(0 0 0 / 90%); backdrop-filter: blur(16px); padding-top: env(safe-area-inset-top, 0px);"
		>
			<a
				href={buildGalleryUrl(galleryId)}
				aria-label="Back to gallery details"
				class="flex h-10 w-10 items-center justify-center rounded-xl transition-transform active:scale-90"
				style="color: white; background: rgb(255 255 255 / 8%);"
			>
				<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
				</svg>
			</a>

			<div class="flex-1 text-center">
				<span class="text-sm font-bold tabular-nums" style="font-family: var(--font-body);">
					<span style="color: var(--tomb-gold);">{currentPage + 1}</span>
					<span style="color: rgb(255 255 255 / 25%);"> / </span>
					<span style="color: rgb(255 255 255 / 50%);">{galleryData.pages.length}</span>
				</span>
			</div>

			<button
				class="flex h-10 items-center gap-1.5 rounded-xl px-3 text-[12px] font-semibold transition-transform active:scale-90"
				style="color: rgb(255 255 255 / 70%); background: rgb(255 255 255 / 8%);"
				onclick={toggleFit}
			>
				{fitMode === 'contain' ? 'Fit' : 'Fill'}
			</button>
		</div>
	</div>

	{#if isLoading}
		<div class="flex h-full w-full items-center justify-center">
			<div
				class="h-8 w-8 animate-spin rounded-full border-2 border-t-transparent"
				style="border-color: rgb(255 255 255 / 10%); border-top-color: transparent;"
			></div>
		</div>
	{:else}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<div
			class="relative flex h-full w-full items-center justify-center"
			onclick={handleTap}
			ontouchstart={handleTouchStart}
			ontouchend={handleTouchEnd}
		>
			{#if imageLoading}
				<div class="absolute inset-0 z-0 flex items-center justify-center">
					<div
						class="h-6 w-6 animate-spin rounded-full border-2 border-t-transparent"
						style="border-color: rgb(255 255 255 / 8%); border-top-color: transparent;"
					></div>
				</div>
			{/if}

			{#if galleryData.pages[currentPage]}
				<img
					src={buildGalleryPageApiUrl(galleryId, galleryData.pages[currentPage])}
					alt={`Page ${currentPage + 1}`}
					class="pointer-events-none transition-opacity duration-150"
					class:opacity-30={imageLoading}
					style={fitMode === 'contain'
						? 'max-width: 100%; max-height: 100%; object-fit: contain;'
						: 'width: 100%; height: 100%; object-fit: cover;'}
					onload={handleImageLoad}
					draggable="false"
				/>
			{/if}
		</div>
	{/if}

	<div
		class="reader-controls absolute right-0 bottom-0 left-0 z-50"
		style={`transform: translateY(${showUI ? '0' : '100%'}); transition: transform 0.25s ease; pointer-events: ${
			showUI ? 'auto' : 'none'
		};`}
	>
		<div
			class="px-5 pt-4 pb-5"
			style="background: rgb(0 0 0 / 90%); backdrop-filter: blur(16px); padding-bottom: max(20px, env(safe-area-inset-bottom, 20px));"
		>
			<input
				type="range"
				min="0"
				max={Math.max(galleryData.pages.length - 1, 0)}
				bind:value={currentPage}
				oninput={(event) => goToPage(Number((event.currentTarget as HTMLInputElement).value))}
				onclick={(event) => event.stopPropagation()}
				class="reader-slider w-full"
				style={`--progress: ${progress}%;`}
			/>

			<div class="mt-1.5 flex justify-between text-[11px] font-medium tabular-nums" style="color: rgb(255 255 255 / 30%);">
				<span>{currentPage + 1}</span>
				<span>{galleryData.pages.length}</span>
			</div>
		</div>
	</div>
</div>

<style>
	@keyframes edgeFade {
		from {
			opacity: 0.7;
		}

		to {
			opacity: 0;
		}
	}

	.reader-slider {
		appearance: none;
		height: 4px;
		border-radius: 2px;
		outline: none;
		background: linear-gradient(
			to right,
			var(--tomb-gold) var(--progress, 0%),
			rgb(255 255 255 / 10%) var(--progress, 0%)
		);
	}

	.reader-slider::-webkit-slider-thumb {
		appearance: none;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--tomb-gold);
		cursor: pointer;
		box-shadow:
			0 0 12px rgb(201 168 76 / 50%),
			0 0 0 4px rgb(201 168 76 / 15%);
	}

	.reader-slider::-moz-range-thumb {
		width: 22px;
		height: 22px;
		border: none;
		border-radius: 50%;
		background: var(--tomb-gold);
		cursor: pointer;
		box-shadow:
			0 0 12px rgb(201 168 76 / 50%),
			0 0 0 4px rgb(201 168 76 / 15%);
	}

	.reader-slider:active::-webkit-slider-thumb {
		transform: scale(1.2);
	}

	.reader-slider:active::-moz-range-thumb {
		transform: scale(1.2);
	}

	* {
		-webkit-tap-highlight-color: transparent;
	}
</style>


