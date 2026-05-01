import type { PageLoad } from './$types';

const API_BASE_URL = '/api/codex';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const response = await fetch(`${API_BASE_URL}/report/homepage`);

		if (!response.ok) {
			throw new Error('Codex backend is not responding');
		}

		const data = await response.json();

		return {
			mangaList: data.mangaList
		};
	} catch (err) {
		console.error('Fetch error:', err);
		return {
			mangaList: [],
			error: 'Could not connect to the Librarian'
		};
	}
};
