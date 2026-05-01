<script lang="ts">
	import { buildReaderUrl, buildSeriesUrl, sortChapters } from '$lib/utils/reader';
	import { fade, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';

	type ChapterMeta = {
		id: number;
		title?: string;
		chapter_number?: number;
	};

	let chapterList = $state<ChapterMeta[]>([]);
	let isLoading = $state(true);

	let {
		manga = null,
		isOpen = $bindable(false),
		apiBase = '/api/codex'
	} = $props();
	let viewMode = $state<'list' | 'grid'>('list');

	function closeModal() {
		isOpen = false;
	}

	function toggleView(mode: 'list' | 'grid') {
		viewMode = mode;
	}

	let coverUrl = $derived(manga ? `${apiBase}/view/series/cover/${manga.id}` : null);
	let firstChapterUrl = $derived(
		manga ? (chapterList.length ? buildReaderUrl(manga.id, 1) : buildSeriesUrl(manga.id)) : '#'
	);

	$effect(() => {
		if (isOpen) {
			document.body.style.overflow = 'hidden';
			return () => (document.body.style.overflow = 'unset');
		}
	});

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) closeModal();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && isOpen) {
			closeModal();
		}
	}

	$effect(() => {
		if (manga?.id && isOpen) {
			loadChapters(manga.id);
		}
	});

	async function loadChapters(id: string | number) {
		isLoading = true;
		try {
			const response = await fetch(`${apiBase}/report/chapters?series_id=${id}`);
			const data = await response.json();
			chapterList = sortChapters(data);
		} catch (e) {
			console.error('Failed to load chapters', e);
		} finally {
			isLoading = false;
		}
	}
	function extractChapterNumber(title: string) {
		const match = title.match(/(\d+(\.\d+)?)/);
		return match ? match[0] : title;
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if isOpen && manga}
	<div
		transition:fade={{ duration: 200 }}
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-4 backdrop-blur-md"
		onclick={handleBackdropClick}
		role="presentation"
	>
		<div
			transition:fly={{ y: 20, duration: 300, easing: cubicOut }}
			class="glass relative h-[90vh] w-full max-w-4xl overflow-hidden rounded-3xl border border-white/40 bg-white/70 shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.key === 'Escape' && closeModal()}
			role="dialog"
			tabindex="0"
		>
			<div class="border-base-300 sticky top-0 z-10 border-b px-6 py-4">
				<div class="flex items-center justify-between">
					<button onclick={closeModal} class="btn btn-ghost btn-sm gap-2">
						<svg
							class="h-5 w-5"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
						>
							<path d="M19 12H5" /><polyline points="12 19 5 12 12 5" />
						</svg>
						Back
					</button>

					<a href={buildSeriesUrl(manga.id)} class="btn btn-ghost btn-sm gap-2">
						<svg
							xmlns="http://www.w3.org/2000/svg"
							class="h-5 w-5"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
							/>
						</svg>
						Expand
					</a>
				</div>
			</div>

			<div class="h-[calc(100%-73px)] overflow-y-auto">
				<div class="p-8">
					<section class="mb-10 flex flex-col gap-8 md:flex-row">
						<div class="w-48 shrink-0 overflow-hidden rounded-2xl shadow-xl">
							<img src={coverUrl} alt={manga.title} class="h-full w-full object-cover" />
						</div>

						<div class="flex flex-1 flex-col">
							<div class="mb-3 flex gap-2">
								{#if manga.isAdult}
									<span class="badge badge-error badge-outline text-[10px] font-bold uppercase"
										>NSFW</span
									>
								{/if}
								<span class="badge badge-ghost text-[10px] font-bold uppercase"
									>{chapterList.length || manga.chapterCount || 0} Chapters</span
								>
							</div>

							<h1 class="text-base-content mb-3 text-4xl font-black tracking-tight">
								{manga.title}
							</h1>

							{#if manga.description}
								<p class="mb-6 text-sm leading-relaxed opacity-70">
									{manga.description}
								</p>
							{/if}

							<div class="flex gap-3">
								<a
									href={firstChapterUrl}
									class="rounded-full bg-[#A659FF] px-8 py-3 font-bold text-white shadow-[0_0_20px_rgba(166,89,255,0.3)] transition-all hover:scale-105 hover:bg-[#B884FF] active:scale-95"
								>
									Start Reading
								</a>
							</div>
						</div>
					</section>

					<section>
						<div class="border-base-300 mb-6 flex items-center justify-between border-b pb-3">
							<h2 class="text-lg font-bold">Chapters</h2>
							<div class="segment-group">
								<button
									class="segment-button {viewMode === 'list' ? 'active' : ''}"
									onclick={() => toggleView('list')}
								>
									List
								</button>

								<button
									class="segment-button {viewMode === 'grid' ? 'active' : ''}"
									onclick={() => toggleView('grid')}
								>
									Grid
								</button>
							</div>
						</div>

						{#if viewMode === 'list'}
							<div class="flex flex-col gap-2">
								{#each chapterList as chapter, i}
									<a
										href={buildReaderUrl(manga.id, i + 1)}
										class="border-base-200 bg-base-100/50 hover:bg-base-200 flex items-center justify-between rounded-xl border px-6 py-4 transition-all"
									>
										<span class="font-bold">{i + 1}) {chapter.title || `chapter ${chapter.chapter_number}`}</span>
										<span class="text-xs font-medium opacity-50">READ</span>
									</a>
								{/each}
							</div>
						{:else}
							<div class="grid grid-cols-4 gap-4 md:grid-cols-6 lg:grid-cols-5">
								{#each chapterList as chapter, i}
									<a
										href={buildReaderUrl(manga.id, i + 1)}
										class="border-base-200
                                                bg-base-100/50
                                                hover:bg-base-200
                                                 cursor=pointer flex
                                                  h-14
                                                  items-center
                                                  justify-center rounded-xl border font-bold transition-all hover:scale-105 active:scale-95"
									>
										{ chapter.title ? extractChapterNumber(chapter.title) : chapter.chapter_number}
									</a>
								{/each}
							</div>
						{/if}
					</section>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	:global(.overflow-y-auto::-webkit-scrollbar) {
		width: 10px;
	}

	:global(.overflow-y-auto::-webkit-scrollbar-track) {
		background: #1a1a1a;
	}

	:global(.overflow-y-auto::-webkit-scrollbar-thumb) {
		background: #333;
		border-radius: 5px;
	}

	:global(.overflow-y-auto::-webkit-scrollbar-thumb:hover) {
		background: #444;
	}

	.segment-group {
		display: inline-flex;
		gap: 4px;
		padding: 4px;
		border-radius: 999px;

		/* background: rgba(255, 255, 255, 0.45); */
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);

		border: 1px solid rgba(255, 255, 255, 0.4);
		box-shadow:
			inset 0 1px 1px rgba(255, 255, 255, 0.5),
			0 8px 20px rgba(0, 0, 0, 0.15);
	}

	.segment-button {
		padding: 6px 14px;
		font-size: 12px;
		font-weight: 600;
		border-radius: 999px;
		border: none;
		background: transparent;
		cursor: pointer;

		color: rgba(0, 0, 0, 0.6);
		transition:
			background 0.2s ease,
			color 0.2s ease,
			box-shadow 0.2s ease;
	}

	.segment-button:hover {
		color: rgba(0, 0, 0, 0.9);
	}

	.segment-button.active {
		background: #f0e6ff;
		color: #000;
	}
</style>
