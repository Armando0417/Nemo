import { createClient } from '@libsql/client';
import { drizzle } from 'drizzle-orm/libsql';
import * as schema from './src/lib/db/schema'; // adjust path
import initSqlJs from 'sql.js'; // or use 'better-sqlite3' to read the old file
import fs from 'fs';

// 1. Connect to your NEW database
const newClient = createClient({ url: 'file:local.db' }); // or your env URL
const db = drizzle(newClient, { schema });

async function migrate() {
	console.log('🚀 Starting migration...');

	// 2. Here you would usually fetch data from your old DB.
	// If you have a JSON export of your old data, it's even easier:
	const oldData = JSON.parse(fs.readFileSync('old_dump.json', 'utf8'));

	// 3. Migrate Series
	for (const s of oldData.series) {
		await db.insert(schema.series).values({
			id: s.id,
			title: s.title,
			path: s.path,
			isNsfw: s.is_nsfw
		});
	}

	// 4. Migrate Chapters
	for (const c of oldData.chapters) {
		await db.insert(schema.chapters).values({
			id: c.id,
			title: c.title,
			filename: c.filename,
			seriesId: c.series_id,
			pageCount: c.page_count
		});
	}

	console.log('✅ Migration complete!');
}

migrate();
