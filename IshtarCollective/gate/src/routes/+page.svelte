<script lang="ts">
	import { buildGalleryListApiUrl, buildGalleryThumbApiUrl, buildGalleryUrl, buildIshtarUrl } from '$lib/paths';

	type GalleryListItem = {
		id: number;
		title: string;
		page_count: number;
		is_completed: boolean;
	};

	type GalleryListResponse = {
		items: GalleryListItem[];
		total: number;
	};
	const ITEMS_PER_PAGE = 20;

	let items = $state<GalleryListItem[]>([]);
	let totalItems = $state(0);
	let currentPage = $state(1);
	let isLoading = $state(true);
	let searchQuery = $state('');
	let activeSearch = $state('');
	let imageLoaded = $state<Record<number, boolean>>({});
	let searchInput = $state<HTMLInputElement | undefined>(undefined);
	let searchFocused = $state(false);

	let offset = $derived((currentPage - 1) * ITEMS_PER_PAGE);
	let totalPages = $derived(Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE)));

	async function fetchPage() {
		isLoading = true;
		imageLoaded = {};

		try {
			const endpoint = buildGalleryListApiUrl({ query: activeSearch, limit: ITEMS_PER_PAGE, offset });

			const res = await fetch(endpoint);
			if (!res.ok) {
				throw new Error(`Request failed with ${res.status}`);
			}

			const data = (await res.json()) as GalleryListResponse;
			items = data.items;
			totalItems = data.total;
		} catch (error) {
			console.error('Failed to fetch galleries:', error);
			items = [];
			totalItems = 0;
		} finally {
			isLoading = false;
			window.scrollTo({ top: 0, behavior: 'smooth' });
		}
	}

	function handleSearch() {
		const query = searchQuery.trim();
		if (query === activeSearch) return;

		activeSearch = query;
		currentPage = 1;
		searchInput?.blur();
	}

	function clearSearch() {
		searchQuery = '';
		activeSearch = '';
		currentPage = 1;
	}

	function handleSearchKey(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			handleSearch();
		}
	}

	function onImageLoad(id: number) {
		imageLoaded = {
			...imageLoaded,
			[id]: true
		};
	}

	function goToPage(pageNumber: number) {
		if (pageNumber >= 1 && pageNumber <= totalPages) {
			currentPage = pageNumber;
		}
	}

	$effect(() => {
		offset;
		activeSearch;
		void fetchPage();
	});
</script>

<svelte:head>
	<title>The Tomb{activeSearch ? ` - "${activeSearch}"` : ''}</title>
	<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
	<meta name="theme-color" content="#0a0a0c" />
	<meta name="apple-mobile-web-app-capable" content="yes" />
	<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
</svelte:head>

<div data-theme="tomb" class="min-h-[100dvh]" style="background: var(--tomb-bg);">
	<header
		class="sticky top-0 z-50"
		style="background: var(--tomb-bg); border-bottom: 1px solid var(--tomb-border-subtle);"
	>
		<div class="flex items-center justify-between px-4 pt-3 pb-2">
			<a href={buildIshtarUrl('/')} class="flex items-center gap-2" onclick={clearSearch}>
				<div
					class="flex h-7 w-7 items-center justify-center rounded-md text-xs font-bold"
					style="background: var(--tomb-gold); color: var(--tomb-bg);"
				>
					T
				</div>
				<span
					class="text-base font-semibold tracking-wide"
					style="font-family: var(--font-display); color: var(--tomb-text);"
				>
					The Tomb
				</span>
			</a>
			<span class="text-[11px] font-medium tabular-nums" style="color: var(--tomb-text-dim);">
				{totalItems.toLocaleString()} entries
			</span>
		</div>

		<div class="px-3 pb-3">
			<div
				class="flex items-center gap-2 rounded-xl px-3 transition-all duration-200"
				style={`background: var(--tomb-surface); border: 1.5px solid ${
					searchFocused ? 'var(--tomb-gold-dim)' : 'var(--tomb-border-subtle)'
				};`}
			>
				<svg
					class="h-4 w-4 shrink-0"
					style={`color: ${searchFocused ? 'var(--tomb-gold)' : 'var(--tomb-text-dim)'}`}
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
					/>
				</svg>
				<input
					bind:this={searchInput}
					bind:value={searchQuery}
					onkeydown={handleSearchKey}
					onfocus={() => (searchFocused = true)}
					onblur={() => (searchFocused = false)}
					type="search"
					enterkeyhint="search"
					autocomplete="off"
					autocapitalize="off"
					placeholder="Search titles..."
					class="flex-1 border-0 bg-transparent py-3 text-sm font-light outline-none"
					style="color: var(--tomb-text); caret-color: var(--tomb-gold);"
				/>
				{#if searchQuery || activeSearch}
					<button
						aria-label={activeSearch ? 'Clear active search' : 'Clear search text'}
						onclick={activeSearch ? clearSearch : () => {
							searchQuery = '';
							searchInput?.focus();
						}}
						class="-mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-transform active:scale-90"
						style="background: var(--tomb-surface-raised); color: var(--tomb-text-muted);"
					>
						<svg
							class="h-3.5 w-3.5"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2.5"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				{/if}
			</div>
		</div>

		{#if activeSearch}
			<div
				class="mx-3 mb-3 flex items-center gap-2 rounded-lg px-3 py-2"
				style="background: var(--tomb-gold-glow); border: 1px solid rgb(201 168 76 / 20%);"
			>
				<span class="flex-1 truncate text-[11px] font-medium" style="color: var(--tomb-gold);">
					Results for "{activeSearch}" - {totalItems} found
				</span>
				<button
					onclick={clearSearch}
					class="shrink-0 text-[11px] font-semibold transition-transform active:scale-95"
					style="color: var(--tomb-gold);"
				>
					Clear
				</button>
			</div>
		{/if}
	</header>

	<main class="px-2 py-3 sm:px-4 sm:py-5">
		<div class="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
			{#if isLoading}
				{#each Array(ITEMS_PER_PAGE) as _, index}
					<div
						class="overflow-hidden rounded-xl"
						style={`background: var(--tomb-surface); animation: tombPulse 1.8s ease-in-out infinite; animation-delay: ${index * 50}ms;`}
					>
						<div class="aspect-[2/3] w-full" style="background: var(--tomb-surface-raised);"></div>
						<div class="space-y-1.5 p-2.5">
							<div class="h-2.5 w-full rounded" style="background: var(--tomb-surface-raised);"></div>
							<div class="h-2.5 w-3/5 rounded" style="background: var(--tomb-surface-raised);"></div>
						</div>
					</div>
				{/each}
			{:else if items.length === 0}
				<div class="col-span-full flex flex-col items-center justify-center gap-4 py-24">
					<div
						class="flex h-16 w-16 items-center justify-center rounded-2xl"
						style="background: var(--tomb-surface); border: 1px solid var(--tomb-border-subtle);"
					>
						<svg
							class="h-7 w-7"
							style="color: var(--tomb-text-dim);"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="1.5"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
							/>
						</svg>
					</div>
					<p class="text-sm font-medium" style="color: var(--tomb-text-dim);">Nothing found.</p>
					{#if activeSearch}
						<button onclick={clearSearch} class="text-sm font-semibold" style="color: var(--tomb-gold);">
							Clear search
						</button>
					{/if}
				</div>
			{:else}
				{#each items as gallery, index}
					<a
						href={buildGalleryUrl(gallery.id)}
						class="tomb-card group relative overflow-hidden rounded-xl transition-transform duration-150 active:scale-[0.97]"
						style="background: var(--tomb-surface);"
					>
						<div class="relative aspect-[2/3] w-full overflow-hidden" style="background: var(--tomb-surface-raised);">
							{#if !imageLoaded[gallery.id]}
								<div class="absolute inset-0 flex items-center justify-center">
									<div
										class="h-5 w-5 animate-spin rounded-full border-2 border-t-transparent"
										style="border-color: var(--tomb-border); border-top-color: transparent;"
									></div>
								</div>
							{/if}

							<img
								src={buildGalleryThumbApiUrl(gallery.id)}
								alt={gallery.title}
								loading={index < 4 ? 'eager' : 'lazy'}
								decoding="async"
								class="absolute inset-0 h-full w-full object-cover"
								style={`opacity: ${imageLoaded[gallery.id] ? 1 : 0}; transition: opacity 0.25s ease;`}
								onload={() => onImageLoad(gallery.id)}
							/>

							<div
								class="pointer-events-none absolute inset-x-0 bottom-0 h-20"
								style="background: linear-gradient(to top, rgb(10 10 12 / 85%) 0%, transparent 100%);"
							></div>

							<div
								class="absolute bottom-2 left-2 flex items-center gap-1 text-[10px] font-semibold"
								style="color: rgb(255 255 255 / 70%);"
							>
								<svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
									/>
								</svg>
								{gallery.page_count}
							</div>

							{#if !gallery.is_completed}
								<div
									class="absolute top-2 right-2 h-2.5 w-2.5 rounded-full"
									style="background: var(--tomb-red); box-shadow: 0 0 8px rgb(196 64 64 / 60%);"
								></div>
							{/if}
						</div>

						<div class="px-2.5 py-2">
							<p
								class="line-clamp-2 text-[12px] font-medium leading-[1.35]"
								style="color: var(--tomb-text-muted);"
							>
								{gallery.title}
							</p>
						</div>
					</a>
				{/each}
			{/if}
		</div>
	</main>

	{#if totalPages > 1 && !isLoading}
		<nav class="safe-bottom px-4 pt-2 pb-6">
			<div class="flex items-center justify-center gap-2">
				<button
					aria-label="Go to previous page"
					onclick={() => goToPage(currentPage - 1)}
					disabled={currentPage === 1}
					class="flex h-12 w-12 items-center justify-center rounded-xl transition-all disabled:opacity-25 active:scale-90"
					style="background: var(--tomb-surface); color: var(--tomb-text-muted);"
				>
					<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
					</svg>
				</button>

				<div
					class="flex h-12 min-w-[120px] items-center justify-center gap-1.5 rounded-xl px-5"
					style="background: var(--tomb-surface); border: 1px solid var(--tomb-border-subtle);"
				>
					<span class="text-base font-bold tabular-nums" style="color: var(--tomb-gold);">{currentPage}</span>
					<span class="text-xs" style="color: var(--tomb-text-dim);">of</span>
					<span class="text-base font-semibold tabular-nums" style="color: var(--tomb-text-muted);">{totalPages}</span>
				</div>

				<button
					aria-label="Go to next page"
					onclick={() => goToPage(currentPage + 1)}
					disabled={currentPage === totalPages}
					class="flex h-12 w-12 items-center justify-center rounded-xl transition-all disabled:opacity-25 active:scale-90"
					style="background: var(--tomb-surface); color: var(--tomb-text-muted);"
				>
					<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
					</svg>
				</button>
			</div>

			{#if totalPages > 5}
				<div class="mt-3 flex justify-center gap-3">
					<button
						onclick={() => goToPage(1)}
						disabled={currentPage === 1}
						class="rounded-lg px-3 py-1.5 text-[11px] font-medium transition-all disabled:opacity-25 active:scale-95"
						style="color: var(--tomb-text-dim); background: var(--tomb-surface-raised);"
					>
						First
					</button>
					<button
						onclick={() => goToPage(totalPages)}
						disabled={currentPage === totalPages}
						class="rounded-lg px-3 py-1.5 text-[11px] font-medium transition-all disabled:opacity-25 active:scale-95"
						style="color: var(--tomb-text-dim); background: var(--tomb-surface-raised);"
					>
						Last
					</button>
				</div>
			{/if}
		</nav>
	{/if}
</div>

<style>
	@keyframes tombPulse {
		0%,
		100% {
			opacity: 1;
		}

		50% {
			opacity: 0.4;
		}
	}

	input[type='search']::-webkit-search-decoration,
	input[type='search']::-webkit-search-cancel-button,
	input[type='search']::-webkit-search-results-button,
	input[type='search']::-webkit-search-results-decoration {
		display: none;
	}

	.tomb-card {
		-webkit-tap-highlight-color: transparent;
	}
</style>