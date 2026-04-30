import { base } from '$app/paths';

function normalizePath(path = '/') {
	return path.startsWith('/') ? path : `/${path}`;
}

export function buildIshtarUrl(path = '/') {
	return `${base}${normalizePath(path)}`;
}

export function buildIshtarApiUrl(path = '/') {
	return `/api/ishtar${normalizePath(path)}`;
}

export function buildGalleryListApiUrl({
	query = '',
	limit,
	offset,
	sort = 'newest'
}: {
	query?: string;
	limit: number;
	offset: number;
	sort?: 'relevance' | 'newest' | 'oldest' | 'title_asc' | 'title_desc' | 'pages_asc' | 'pages_desc' | 'random';
}) {
	const params = new URLSearchParams({
		limit: String(limit),
		offset: String(offset),
		sort
	});

	const normalizedQuery = query.trim();
	if (normalizedQuery) {
		params.set('q', normalizedQuery);
	}

	return buildIshtarApiUrl(`/search?${params.toString()}`);
}

export function buildGalleryUrl(galleryId: number | string) {
	return `${base}/gallery/${galleryId}`;
}

export function buildReaderUrl(galleryId: number | string) {
	return `${base}/reader/${galleryId}`;
}

export function buildGalleryDetailApiUrl(galleryId: number | string) {
	return buildIshtarApiUrl(`/gallery/${galleryId}`);
}

export function buildGalleryThumbApiUrl(galleryId: number | string) {
	return buildIshtarApiUrl(`/view/gallery/${galleryId}/thumbnail`);
}

export function buildGalleryPagesApiUrl(galleryId: number | string) {
	return buildIshtarApiUrl(`/view/gallery/${galleryId}/pages`);
}

export function buildGalleryPageApiUrl(galleryId: number | string, filename: string) {
	return buildIshtarApiUrl(`/view/gallery/${galleryId}/page/${encodeURIComponent(filename)}`);
}
