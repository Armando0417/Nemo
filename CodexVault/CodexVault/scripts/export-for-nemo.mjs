import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectDir = path.resolve(scriptDir, '..');
const nemoRoot = path.resolve(projectDir, '..', '..');
const buildRoot = path.join(projectDir, '.svelte-kit', 'output');
const clientDir = path.join(buildRoot, 'client');
const serverDir = path.join(buildRoot, 'server');
const distDir = path.join(nemoRoot, 'codex_frontend_dist');
const basePath = process.env.NEMO_CODEX_BASE_PATH ?? '/codex';

if (!fs.existsSync(clientDir)) {
	throw new Error(`Missing Svelte client build at ${clientDir}`);
}

fs.rmSync(distDir, { recursive: true, force: true });
fs.mkdirSync(distDir, { recursive: true });
fs.cpSync(clientDir, distDir, { recursive: true });

const { Server } = await import(pathToFileURL(path.join(serverDir, 'index.js')).href);
const { manifest } = await import(pathToFileURL(path.join(serverDir, 'manifest.js')).href);

const server = new Server(manifest);
await server.init({ env: process.env });

const normalizedBase = basePath === '' ? '/' : `${basePath.replace(/\/$/, '')}/`;
const response = await server.respond(
	new Request(new URL(normalizedBase, 'http://127.0.0.1').toString(), {
		headers: {
			accept: 'text/html'
		}
	}),
	{
		getClientAddress: () => '127.0.0.1'
	}
);

if (!response.ok) {
	throw new Error(`Failed to render Codex frontend shell: ${response.status} ${response.statusText}`);
}

fs.writeFileSync(path.join(distDir, 'index.html'), await response.text(), 'utf8');
console.log(`Exported Nemo Codex frontend to ${distDir}`);
