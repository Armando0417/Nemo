<script lang="ts">
	import { buildGalleryDetailApiUrl, buildGalleryThumbApiUrl, buildIshtarUrl, buildReaderUrl } from '$lib/paths';
	import { page } from '$app/state';
	import { onMount } from 'svelte';

	type GalleryDetails = {
		title: string;
		page_count: number;
		upload_date: string;
		is_completed: boolean;
		tags?: Record<string, string[]>;
	};
	const galleryId = page.params.id ?? '';

	let gallery = $state<GalleryDetails | null>(null);
	let isLoading = $state(true);
	let coverLoaded = $state(false);

	const categoryOrder = ['artist', 'group', 'series', 'character', 'tag'] as const;
	const categoryLabels: Record<(typeof categoryOrder)[number], string> = {
		artist: 'Artist',
		group: 'Group',
		series: 'Series',
		character: 'Characters',
		tag: 'Tags'
	};
	const categoryIcons: Record<(typeof categoryOrder)[number], string> = {
		artist: 'M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z',
		group:
			'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z',
		series:
			'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253',
		character: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z',
		tag: 'M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z'
	};
	const categoryAccents: Record<(typeof categoryOrder)[number], string> = {
		artist: '#c9a84c',
		group: '#7c8cbf',
		series: '#6dab8e',
		character: '#c47daa',
		tag: '#8a8890'
	};

	onMount(async () => {
		try {
			const res = await fetch(buildGalleryDetailApiUrl(galleryId));
			if (!res.ok) {
				throw new Error(`Request failed with ${res.status}`);
			}

			gallery = (await res.json()) as GalleryDetails;
		} catch (error) {
			console.error('Failed to load gallery', error);
			gallery = null;
		} finally {
			isLoading = false;
		}
	});
</script>

<svelte:head>
	<title>{gallery?.title || 'Gallery'} - The Tomb</title>
	<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
	<meta name="theme-color" content="#0a0a0c" />
</svelte:head>

<div data-theme="tomb" class="min-h-[100dvh] pb-24" style="background: var(--tomb-bg);">
	{#if isLoading}
		<div class="flex h-[100dvh] items-center justify-center">
			<div
				class="h-8 w-8 animate-spin rounded-full border-2 border-t-transparent"
				style="border-color: var(--tomb-border); border-top-color: transparent;"
			></div>
		</div>
	{:else if gallery}
		<div class="relative">
			<a
				href={buildIshtarUrl('/')}
				aria-label="Back to gallery list"
				class="absolute top-3 left-3 z-30 flex h-10 w-10 items-center justify-center rounded-full transition-transform active:scale-90"
				style="background: rgb(0 0 0 / 60%); backdrop-filter: blur(8px); color: white; -webkit-tap-highlight-color: transparent;"
			>
				<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
				</svg>
			</a>

			<div
				class="absolute top-3 right-3 z-30 rounded-full px-2.5 py-1 text-[10px] font-bold tabular-nums"
				style="background: rgb(0 0 0 / 60%); backdrop-filter: blur(8px); color: rgb(255 255 255 / 60%);"
			>
				#{galleryId}
			</div>

			<div class="relative max-h-[65dvh] w-full overflow-hidden aspect-[3/4]" style="background: var(--tomb-surface);">
				{#if !coverLoaded}
					<div class="absolute inset-0 flex items-center justify-center">
						<div
							class="h-6 w-6 animate-spin rounded-full border-2 border-t-transparent"
							style="border-color: var(--tomb-border); border-top-color: transparent;"
						></div>
					</div>
				{/if}
				<img
					src={buildGalleryThumbApiUrl(galleryId)}
					alt={gallery.title}
					class="absolute inset-0 h-full w-full object-contain"
					style={`opacity: ${coverLoaded ? 1 : 0}; transition: opacity 0.3s ease; background: var(--tomb-surface);`}
					onload={() => (coverLoaded = true)}
				/>
				<div
					class="pointer-events-none absolute inset-x-0 bottom-0 h-24"
					style="background: linear-gradient(to top, var(--tomb-bg), transparent);"
				></div>
			</div>
		</div>

		<div class="relative z-10 -mt-4 px-4">
			<h1
				class="mb-3 text-[17px] font-bold leading-snug"
				style="color: var(--tomb-text); font-family: var(--font-body);"
			>
				{gallery.title}
			</h1>

			<div class="mb-5 flex items-center gap-4 text-[12px]" style="color: var(--tomb-text-muted);">
				<div class="flex items-center gap-1.5">
					<svg class="h-3.5 w-3.5 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
						/>
					</svg>
					{gallery.page_count} pages
				</div>
				<div class="flex items-center gap-1.5">
					<svg class="h-3.5 w-3.5 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
						/>
					</svg>
					{gallery.upload_date}
				</div>
				{#if !gallery.is_completed}
					<div class="flex items-center gap-1.5">
						<div class="h-2 w-2 rounded-full" style="background: var(--tomb-red);"></div>
						<span style="color: var(--tomb-red);">Incomplete</span>
					</div>
				{/if}
			</div>
		</div>

		<div class="mb-6 space-y-4">
			{#each categoryOrder as category}
				{#if gallery.tags?.[category]?.length}
					<div>
						<div class="mb-2 flex items-center gap-2 px-4">
							<svg
								class="h-3.5 w-3.5"
								style={`color: ${categoryAccents[category]};`}
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="2"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d={categoryIcons[category]} />
							</svg>
							<span
								class="text-[10px] font-bold uppercase tracking-[0.15em]"
								style={`color: ${categoryAccents[category]};`}
							>
								{categoryLabels[category]}
							</span>
						</div>
						<div class="no-scrollbar flex gap-1.5 overflow-x-auto px-4 pb-1">
							{#each gallery.tags[category] as tagName}
								<span
									class="inline-flex shrink-0 whitespace-nowrap rounded-lg px-3 py-1.5 text-[12px] font-medium"
									style="background: var(--tomb-surface); color: var(--tomb-text-muted); border: 1px solid var(--tomb-border-subtle);"
								>
									{tagName}
								</span>
							{/each}
						</div>
					</div>
				{/if}
			{/each}
		</div>
	{:else}
		<div class="flex h-[80dvh] flex-col items-center justify-center gap-4">
			<p class="text-sm" style="color: var(--tomb-text-dim);">Gallery not found.</p>
			<a href={buildIshtarUrl('/')} class="text-sm font-semibold" style="color: var(--tomb-gold);">
				Return to The Tomb
			</a>
		</div>
	{/if}

	{#if gallery && !isLoading}
		<div
			class="safe-bottom fixed inset-x-0 bottom-0 z-50"
			style="background: linear-gradient(to top, var(--tomb-bg) 60%, transparent);"
		>
			<div class="px-4 pt-6 pb-4">
				<a
					href={buildReaderUrl(galleryId)}
					class="flex w-full items-center justify-center gap-2.5 rounded-2xl py-4 text-[15px] font-bold transition-transform active:scale-[0.97]"
					style="background: var(--tomb-gold); color: var(--tomb-bg); -webkit-tap-highlight-color: transparent;"
				>
					<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
						/>
					</svg>
					Start Reading
				</a>
			</div>
		</div>
	{/if}
</div>

<style>
	.no-scrollbar::-webkit-scrollbar {
		display: none;
	}

	.no-scrollbar {
		-ms-overflow-style: none;
		scrollbar-width: none;
	}

	a {
		-webkit-tap-highlight-color: transparent;
	}
</style>


