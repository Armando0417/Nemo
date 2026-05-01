
/**
 * @typedef {Object} Manga
 * @prop {string} id
 * @prop {string} title
 * @prop {string} image
 * @prop {string} description
 * @prop {string} url   
 * @prop {boolean} watched
 */
export interface Manga {
  id: string;
  title: string;
  image: string;
  description: string;
  url: string;
  watched: boolean;
  isAdult: boolean;
  chapters: number;
};

