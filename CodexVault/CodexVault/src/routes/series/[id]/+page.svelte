<script lang="ts">
	import { buildCodexUrl, buildReaderUrl, sortChapters } from '$lib/utils/reader';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { goto } from '$app/navigation';
	import '../../../app.css';

	const FLASK_URL = '/api/codex';

	type ChapterMeta = {
		id: number;
		title?: string;
		chapter_number?: number;
	};

	let mangaId = $derived(Number(page.params.id));
	let manga = $state<any>(null);
	let isLoading = $state(true);
	let coverUrl = $state<string>('');
	let serverChapList = $state<ChapterMeta[]>([]);
	let loadedChapList = $state(new Map<number, string[]>());
	let selectedChapterId = $state<number | null>(null);
	let selectedChapterNumber = $state<number | null>(null);

	$effect(() => {
		if (manga) {
			coverUrl = `${FLASK_URL}/view/series/cover/${manga.id}`;
		}
	});

	onMount(async () => {
		try {
			// 1. Fetch the specific series metadata using our new endpoint
			const response = await fetch(`${FLASK_URL}/report/series/${mangaId}`);
			if (!response.ok) throw new Error('Manga not found');
			manga = await response.json();

			// 2. Fetch the chapters
			const chapterResponse = await fetch(`${FLASK_URL}/report/chapters?series_id=${mangaId}`);
			serverChapList = sortChapters(await chapterResponse.json());
		} catch (e) {
			console.error('Failed to load manga', e);
		} finally {
			isLoading = false;
		}
	});

	async function loadChapImages(chapterId: number, chapterNumber: number) {
		selectedChapterId = chapterId;
		selectedChapterNumber = chapterNumber;
		if (loadedChapList.has(chapterId)) return;

		isFetchingImages = true;
		try {
			const chapterImagesResponse = await fetch(`${FLASK_URL}/view/chapter/${chapterId}/pages`);
			const imageData = await chapterImagesResponse.json();

			loadedChapList.set(chapterId, imageData.images || imageData);
		} catch (e) {
			console.error('Failed to load chapter images', e);
		} finally {
			isFetchingImages = false;
		}
	}

	function openReader(chapterNumber: number, index: number = 0) {
		goto(buildReaderUrl(manga.id, chapterNumber, index));
	}

	function handleChapterSelection(event: Event) {
		const target = event.currentTarget as HTMLSelectElement;
		const selectedValue = Number(target.value);
		const chapterIndex = serverChapList.findIndex((chapter) => chapter.id === selectedValue);
		if (chapterIndex !== -1) {
			loadChapImages(selectedValue, chapterIndex + 1);
		}
	}

	let isFetchingImages = $state(false);
</script>

<div class="page-root">
	{#if !isLoading && coverUrl}
		<div
			class="ambient-bg"
			style="background-image: url({coverUrl});"
			transition:fade={{ duration: 800 }}
		></div>
	{/if}

	<div class="navbar shadow-sm">
		<div class="flex-none"></div>
		<div class="flex-1">
			<a href={buildCodexUrl('/')} class="btn btn-ghost text-xl">Codex Vault</a>
		</div>
		<div class="flex-none">
			<button class="btn btn-square btn-ghost" type="button" aria-label="Series options">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					class="inline-block h-5 w-5 stroke-current"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z"
					></path>
				</svg>
			</button>
		</div>
	</div>

	<div class="content-container">
		<div class="manga-details frosted">
			<div class="details-layout h-full w-full px-10 py-10">
				{#if isLoading}
					<div class="skeleton h-full w-1/4 rounded-2xl"></div>
				{:else}
					<div class="cover-wrapper cover-panel h-100 w-1/4 min-w-17.5 shrink-0 shadow-xl">
						<img src={coverUrl} alt="Cover" class="h-full w-full object-cover" />
					</div>
				{/if}

				<div class="manga-info info-panel flex w-3/4 flex-col gap-6">
					<div class="title-area">
						{#if isLoading}
							<div class="skeleton mb-4 h-12 w-3/4"></div>
						{:else}
							<h1 class="text-4xl font-black tracking-tight text-gray-900">{manga.title}</h1>
							<div class="mt-2 flex gap-2">
								<span class="badge-light-purple">{serverChapList.length} Chapters</span>
							</div>
						{/if}
					</div>

					<div class="description-area flex-1 overflow-y-auto">
						{#if isLoading}
							<div class="skeleton h-32 w-full"></div>
						{:else}
							<p class="leading-relaxed text-gray-700">
								{manga.description}
							</p>
						{/if}
					</div>
				</div>
			</div>
		</div>

		<div class="section-divider">
			<h2 class="text-2xl font-bold text-gray-800">Chapters</h2>
		</div>

		<div class="chapter-container">
			<div class="chapter-list frosted">
				{#if isLoading}
					<div class="flex flex-col gap-4 p-4">
						{#each Array(5) as _}
							<div class="skeleton h-16 w-full"></div>
						{/each}
					</div>
				{:else}
					{#each serverChapList as chapter, index}
						<button
							class="chapter-item {selectedChapterId === chapter.id ? 'active' : ''}"
							onclick={() => loadChapImages(chapter.id, index + 1)}
						>
							<span class="chapter-number">#</span>
							<span class="chapter-name font-bold text-gray-800">{chapter.title}</span>
							<span class="arrow-icon">→</span>
						</button>
					{/each}
				{/if}
			</div>

			<div class="chapter-preview frosted">
				<div class="mobile-chapter-controls">
					<label class="chapter-select-label" for="chapter-select">Chapter</label>
					<select
						id="chapter-select"
						class="chapter-select"
						value={selectedChapterId ?? ''}
						onchange={handleChapterSelection}
					>
						<option value="" disabled selected={selectedChapterId === null}>Select a chapter</option>
						{#each serverChapList as chapter, index}
							<option value={chapter.id}>
								{index + 1}. {chapter.title || `Chapter ${chapter.chapter_number ?? index + 1}`}
							</option>
						{/each}
					</select>
				</div>

				{#if isFetchingImages}
					<div class="image-grid">
						{#each Array(6) as _}
							<div class="skeleton aspect-[3/4] w-full rounded-xl"></div>
						{/each}
					</div>
				{:else if selectedChapterId && loadedChapList.has(selectedChapterId)}
					<div class="image-grid">
						{#each loadedChapList.get(selectedChapterId) as imgUrl, index}
							<button
								class="preview-card w-full"
								type="button"
								onclick={() => selectedChapterNumber && openReader(selectedChapterNumber, index)}
							>
								<img
									src={`${FLASK_URL}/view/chapter/${selectedChapterId}/page/${imgUrl}/thumb`}
									alt="page"
									loading="lazy"
									class="opacity-0 transition-opacity duration-300"
									onload={(e) => {
										e.currentTarget.classList.remove('opacity-0');
										e.currentTarget.classList.add('opacity-100');
									}}
								/>
							</button>
						{/each}
					</div>
				{:else}
					<div class="flex h-full items-center justify-center text-gray-400">
						<p>Select a chapter to start reading...</p>
					</div>
				{/if}
			</div>
		</div>
	</div>
</div>

<style>
	.page-root {
		position: relative;
		min-height: 100vh;
		background-color: #fcf9f7; /* Matching your library background */
		color: #333;
		overflow-x: hidden;
		padding-bottom: 80px;
	}

	/* Backdrop: Lightened for light theme */
	.ambient-bg {
		position: fixed;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		background-size: cover;
		background-position: center;
		filter: blur(100px) saturate(1.2) brightness(1.1); /* Brighter for light mode */
		transform: scale(1.1);
		z-index: 0;
		opacity: 0.35; /* Very subtle color bleed */
	}

	.content-container {
		position: relative;
		z-index: 1;
		max-width: 1400px;
		width: 90%;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: 32px;
		padding-top: 40px;
	}

	/* Frosted White Glass */
	.frosted {
		background: rgba(255, 255, 255, 0.45);
		backdrop-filter: blur(16px) saturate(180%);
		-webkit-backdrop-filter: blur(16px) saturate(180%);
		border: 1px solid rgba(255, 255, 255, 0.7);
		border-radius: 20px;
		box-shadow:
			0 4px 30px rgba(0, 0, 0, 0.03),
			0 1px 1px rgba(0, 0, 0, 0.05); /* Very light shadow */
	}

	.manga-details {
		min-height: 500px;
	}

	.details-layout {
		display: flex;
		height: 100%;
		width: 100%;
		gap: 40px;
	}

	.cover-wrapper {
		border-radius: 12px;
		overflow: hidden;
		border: 1px solid #ddd;
	}

	.chapter-container {
		display: flex;
		gap: 30px;
		height: 85vh;
	}

	.chapter-list {
		flex: 0 0 35%;
		overflow-y: auto;
		padding: 15px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	/* Flat, Light Chapter Items */
	.chapter-item {
		display: flex;
		align-items: center;
		padding: 14px 20px;
		background: rgba(255, 255, 255, 0.5);
		border: 1px solid rgba(0, 0, 0, 0.05);
		border-radius: 12px;
		cursor: pointer;
		transition: all 0.2s ease;
		text-align: left;
	}

	.chapter-item:hover {
		background: white;
		transform: translateX(5px);
		box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
		border-color: #a659ff;
	}

	.chapter-item.active {
		background: #a659ff;
		color: white;
		border-color: #a659ff;
	}

	.chapter-item.active .chapter-name {
		color: white;
	}

	.chapter-number {
		font-weight: 800;
		margin-right: 12px;
		color: #a659ff;
	}

	.chapter-item.active .chapter-number {
		color: white;
	}

	.arrow-icon {
		margin-left: auto;
		opacity: 0.3;
	}

	.chapter-preview {
		flex: 1;
		padding: 24px;
		overflow-y: auto;
	}

	.mobile-chapter-controls {
		display: none;
		margin-bottom: 18px;
	}

	.chapter-select-label {
		display: block;
		margin-bottom: 8px;
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		color: #7c7c86;
	}

	.chapter-select {
		width: 100%;
		border-radius: 12px;
		border: 1px solid rgba(0, 0, 0, 0.08);
		background: rgba(255, 255, 255, 0.9);
		padding: 12px 14px;
		font-size: 14px;
		font-weight: 600;
		color: #2f2f35;
		outline: none;
	}

	.chapter-select:focus {
		border-color: #a659ff;
		box-shadow: 0 0 0 3px rgba(166, 89, 255, 0.12);
	}

	.image-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: 20px;
	}

	.preview-card {
		padding: 0;
		border-radius: 8px;
		overflow: hidden;
		background: #fff;
		aspect-ratio: 3/4;
		border: 1px solid #eee;
		transition: all 0.3s ease;
		will-change: transform;
		position: relative; /* Ensure proper stacking */
	}

	.preview-card:hover {
		transform: scale(1.03);
		border-color: #a659ff;
		box-shadow: 0 10px 20px rgba(166, 89, 255, 0.15);
		cursor: pointer;
	}

	/* Fix: Removed the scale(50) and added better image handling */
	.preview-card img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
		transition: transform 0.3s ease;
		pointer-events: none;
	}

	/* Optional: subtle zoom on the image inside the card */
	.preview-card:hover img {
		transform: scale(1.05);
		pointer-events: none;
	}

	.badge-light-purple {
		background: #f0e6ff;
		color: #7c3aed;
		padding: 4px 12px;
		border-radius: 99px;
		font-size: 12px;
		font-weight: 700;
		border: 1px solid #e2d1ff;
	}

	/* Light Skeletons */
	.skeleton {
		background: rgba(0, 0, 0, 0.05);
		position: relative;
		overflow: hidden;
	}

	.skeleton::after {
		content: '';
		position: absolute;
		top: 0;
		right: 0;
		bottom: 0;
		left: 0;
		background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.6), transparent);
		animation: loading 1.5s infinite;
	}

	@keyframes loading {
		0% {
			transform: translateX(-100%);
		}
		100% {
			transform: translateX(100%);
		}
	}

	/* Clean Scrollbars */
	.chapter-list::-webkit-scrollbar,
	.chapter-preview::-webkit-scrollbar {
		width: 5px;
	}
	.chapter-list::-webkit-scrollbar-thumb,
	.chapter-preview::-webkit-scrollbar-thumb {
		background: rgba(0, 0, 0, 0.1);
		border-radius: 10px;
	}

	@media (max-width: 820px) {
		.content-container {
			width: calc(100% - 24px);
			gap: 18px;
			padding-top: 20px;
		}

		.manga-details {
			min-height: auto;
		}

		.details-layout {
			align-items: flex-start;
			gap: 16px;
			padding: 18px;
		}

		.cover-panel {
			width: 44%;
			min-width: 0;
			height: auto;
			aspect-ratio: 2 / 3;
		}

		.info-panel {
			width: 56%;
			gap: 12px;
			min-width: 0;
		}

		.title-area :global(h1) {
			font-size: 1.65rem;
			line-height: 1.05;
		}

		.description-area {
			overflow: hidden;
		}

		.description-area p {
			display: -webkit-box;
			line-clamp: 5;
			-webkit-box-orient: vertical;
			-webkit-line-clamp: 5;
			overflow: hidden;
			font-size: 0.92rem;
			line-height: 1.45;
		}

		.chapter-container {
			height: auto;
			flex-direction: column;
			gap: 16px;
		}

		.chapter-list {
			display: none;
		}

		.chapter-preview {
			padding: 18px;
			min-height: 50vh;
		}

		.mobile-chapter-controls {
			display: block;
		}

		.image-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
			gap: 12px;
		}

		.section-divider h2 {
			font-size: 1.35rem;
		}
	}
</style>
