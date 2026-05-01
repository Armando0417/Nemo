import type { Manga } from '$lib/data/types';

export const mangaList: Manga[] = [
		{
			id: 'fgo-eor',
			title: 'Fate/Grand Order – Epic of Remnant',
			chapters: 100,
			image: 'https://placehold.co/400x600/222/white?text=FGO',
			description:
				'A continuation of the Grand Order story involving the remnants of the Demon God Pillars.',
			url: 'https://example.com/fgo-epic-of-remnant',
			watched: false,
			isAdult: true
		},
		{
			id: 'solo-leveling',
			title: 'Solo Leveling',
			chapters: 179,
			image: 'https://placehold.co/400x600/444/white?text=Solo+Leveling',
			description:
				"In a world where hunters must battle monsters, the weakest hunter of all mankind becomes the world's strongest.",
			url: 'https://example.com/solo-leveling',
			watched: true,
			isAdult: false
		},
		{
			id: 'chainsaw-man',
			title: 'Chainsaw Man',
			chapters: 150,
			image: 'https://placehold.co/400x600/333/white?text=Chainsaw+Man',
			description: 'Denji is a teenage boy living with a Chainsaw Devil named Pochita.',
			url: 'https://example.com/chainsaw-man',
			watched: false,
			isAdult: true
		},
		{
			id: 'monster',
			title: 'Monster',
			chapters: 162,
			image: 'https://placehold.co/400x600/111/white?text=Monster',
			description:
				'A psychological thriller following a brilliant doctor whose life unravels after saving the wrong person.',
			url: 'https://example.com/monster',
			watched: true,
			isAdult: false
		}
	];