import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';
import { relations } from 'drizzle-orm';

// 1. Define the Series Table
export const series = sqliteTable('series', {
	id: integer('id').primaryKey({ autoIncrement: true }),
	title: text('title').notNull(),
	path: text('path').unique(),
	isNsfw: integer('is_nsfw', { mode: 'boolean' }).default(false)
});

// 2. Define the Chapter Table
export const chapters = sqliteTable('chapter', {
	id: integer('id').primaryKey({ autoIncrement: true }),
	title: text('title').notNull(),
	filename: text('filename').unique(),
	pageCount: integer('page_count').default(0),
	// This is the actual Foreign Key in the database
	seriesId: integer('series_id')
		.notNull()
		.references(() => series.id, { onDelete: 'cascade' })
});

// 3. Define the User Table
export const users = sqliteTable('user', {
	id: integer('id').primaryKey({ autoIncrement: true }),
	username: text('username').unique().notNull(),
	passwordHash: text('password_hash').notNull(),
	canSeeNsfw: integer('can_see_nsfw', { mode: 'boolean' }).default(false)
});

// --- RELATIONSHIPS (The "Drizzle Magic" part) ---

export const seriesRelations = relations(series, ({ many }) => ({
	chapters: many(chapters) // One Series -> Many Chapters
}));

export const chaptersRelations = relations(chapters, ({ one }) => ({
	series: one(series, {
		fields: [chapters.seriesId],
		references: [series.id]
	})
}));
