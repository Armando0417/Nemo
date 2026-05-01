<script lang="ts">
	import '../app.css';
	import MangaModal from '$lib/components/mangaDialogue.svelte';
	import { buildCodexUrl } from '$lib/utils/reader';

	const FLASK_URL = '/api/codex';

	let { data } = $props();
	const mangaList = $derived(data.mangaList);

	let selectedManga: any | null = $state(null);
	let isModalOpen = $state(false);
	let searchQuery = $state('');
	let searchInput: HTMLInputElement;

	const filteredList = $derived(
		searchQuery.trim() === ''
			? mangaList
			: mangaList.filter((m: any) =>
					m.title.toLowerCase().includes(searchQuery.toLowerCase())
				)
	);

	function openManga(manga: any) {
		selectedManga = manga;
		isModalOpen = true;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === '/' && document.activeElement?.tagName !== 'INPUT') {
			e.preventDefault();
			searchInput?.focus();
		}
		if (e.key === 'Escape' && document.activeElement === searchInput) {
			searchQuery = '';
			searchInput?.blur();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="page-root">
	<div class="navbar shadow-sm">
		<div class="flex-1">
			<a href={buildCodexUrl('/')} class="btn btn-ghost text-xl">Codex Vault</a>
		</div>

		<div class="search-wrap">
			<svg class="search-icon" xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="none" viewBox="0 0 24 24" stroke-width="2.2" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
			</svg>
			<input
				bind:this={searchInput}
				bind:value={searchQuery}
				type="text"
				class="search-input"
				placeholder="Search library…"
				aria-label="Search library"
			/>
			{#if searchQuery}
				<button class="search-clear" onclick={() => (searchQuery = '')} aria-label="Clear search">×</button>
			{:else}
				<kbd class="search-hint">/</kbd>
			{/if}
		</div>

		<div class="navbar-end flex-none pl-4">
			<span class="count-badge">
				{#if searchQuery && filteredList.length !== mangaList.length}
					{filteredList.length} of {mangaList.length}
				{:else}
					{mangaList.length} series
				{/if}
			</span>
		</div>
	</div>

	<main class="library-main">
		{#if filteredList.length === 0}
			<div class="empty-state">
				No results for "<strong>{searchQuery}</strong>"
			</div>
		{:else}
			<div class="library-grid">
				{#each filteredList as manga}
					<button class="library-item" onclick={() => openManga(manga)}>
						<div class="cover-wrap">
							<img
								src={`${FLASK_URL}/view/series/cover/${manga.id}`}
								alt={manga.title}
								class="cover-img"
								onerror={(e) =>
									((e.currentTarget as HTMLImageElement).src =
										'https://placehold.co/400x600/ede8ff/a659ff?text=?')}
							/>
							{#if manga.isNsfw}
								<div class="nsfw-badge">18+</div>
							{/if}
						</div>
						<div class="item-info">
							<span class="item-title">{manga.title}</span>
							<span class="item-sub">{manga.chapterCount} chapters</span>
						</div>
					</button>
				{/each}
			</div>
		{/if}
	</main>
</div>

<MangaModal manga={selectedManga} bind:isOpen={isModalOpen} apiBase={FLASK_URL} />

<style>
	:global(body) {
		background-color: #fcf9f7;
		margin: 0;
	}

	.page-root {
		min-height: 100vh;
	}

	/* Navbar */
	.navbar {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		padding: 0 20px;
		height: 60px;
		background: rgba(252, 249, 247, 0.85);
		border-bottom: 1px solid rgba(0, 0, 0, 0.06);
		backdrop-filter: blur(12px);
		gap: 12px;
	}

	/* Search */
	.search-wrap {
		position: relative;
		display: flex;
		align-items: center;
		width: 100%;
		max-width: 420px;
	}

	.search-icon {
		position: absolute;
		left: 11px;
		color: #aaa;
		pointer-events: none;
	}

	.search-input {
		width: 100%;
		height: 36px;
		padding: 0 34px 0 34px;
		background: rgba(255, 255, 255, 0.7);
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 10px;
		color: #333;
		font-size: 14px;
		outline: none;
		transition: border-color 0.15s, box-shadow 0.15s;
	}

	.search-input::placeholder {
		color: #bbb;
	}

	.search-input:focus {
		border-color: #a659ff;
		box-shadow: 0 0 0 3px rgba(166, 89, 255, 0.12);
	}

	.search-clear {
		position: absolute;
		right: 9px;
		width: 20px;
		height: 20px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0, 0, 0, 0.07);
		border: none;
		border-radius: 50%;
		color: #888;
		font-size: 14px;
		cursor: pointer;
		line-height: 1;
	}

	.search-clear:hover {
		background: rgba(0, 0, 0, 0.13);
		color: #333;
	}

	.search-hint {
		position: absolute;
		right: 9px;
		padding: 2px 6px;
		background: rgba(0, 0, 0, 0.05);
		border-radius: 5px;
		font-size: 12px;
		color: #bbb;
		font-family: monospace;
		pointer-events: none;
	}

	.count-badge {
		font-size: 13px;
		color: #aaa;
		white-space: nowrap;
	}

	/* Library */
	.library-main {
		padding: 28px 28px 60px;
	}

	.library-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: 20px 16px;
	}

	.library-item {
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: 8px;
		text-align: left;
	}

	.cover-wrap {
		position: relative;
		aspect-ratio: 2 / 3;
		border-radius: 10px;
		overflow: hidden;
		background: #ede8e3;
		border: 1px solid rgba(0, 0, 0, 0.07);
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
		transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
	}

	.library-item:hover .cover-wrap {
		transform: translateY(-4px) scale(1.015);
		box-shadow: 0 10px 24px rgba(166, 89, 255, 0.18);
		border-color: #a659ff;
	}

	.cover-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.nsfw-badge {
		position: absolute;
		top: 6px;
		right: 6px;
		padding: 2px 5px;
		background: #dc2626;
		border-radius: 4px;
		font-size: 9px;
		font-weight: 700;
		color: #fff;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.item-info {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 0 2px;
	}

	.item-title {
		font-size: 12px;
		font-weight: 600;
		color: #2a2a2a;
		line-height: 1.3;
		display: -webkit-box;
		line-clamp: 2;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.item-sub {
		font-size: 11px;
		color: #aaa;
	}

	/* Empty */
	.empty-state {
		padding: 100px 0;
		text-align: center;
		color: #bbb;
		font-size: 15px;
	}

	.empty-state strong {
		color: #888;
	}

	/* Scale up columns on wider screens */
	@media (min-width: 768px) {
		.library-grid {
			grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		}
	}

	@media (min-width: 1280px) {
		.library-grid {
			grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
			gap: 24px 18px;
		}
	}
</style>
