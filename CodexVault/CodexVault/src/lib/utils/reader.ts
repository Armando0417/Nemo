import { base } from '$app/paths';

export type ChapterLike = {
	id: number;
	chapter_number?: number | null;
};

export function sortChapters<T extends ChapterLike>(chapters: T[]): T[] {
	return [...chapters].sort(
		(a, b) => (a.chapter_number ?? 0) - (b.chapter_number ?? 0) || a.id - b.id
	);
}

export function buildReaderUrl(seriesId: number, chapterNumber: number, page = 0) {
	return `${base}/read/${seriesId}/${chapterNumber}/${page}`;
}

export function buildSeriesUrl(seriesId: number) {
	return `${base}/series/${seriesId}`;
}

export function buildCodexUrl(path = '/') {
	const normalizedPath = path.startsWith('/') ? path : `/${path}`;
	return `${base}${normalizedPath}`;
}

export function resolveSeriesChapter<T extends ChapterLike>(chapters: T[], requestedChapter: number) {
	if (!Number.isFinite(requestedChapter)) {
		return null;
	}

	const chapterIndex = requestedChapter - 1;
	if (chapterIndex >= 0 && chapterIndex < chapters.length) {
		return {
			chapter: chapters[chapterIndex],
			chapterIndex
		};
	}

	// Allow old chapter-id URLs to keep working and immediately canonicalize them.
	const legacyIndex = chapters.findIndex((entry) => entry.id === requestedChapter);
	if (legacyIndex !== -1) {
		return {
			chapter: chapters[legacyIndex],
			chapterIndex: legacyIndex
		};
	}

	return null;
}
