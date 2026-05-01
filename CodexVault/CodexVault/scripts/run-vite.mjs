import { realpathSync } from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const canonicalCwd = realpathSync(process.cwd());
if (canonicalCwd !== process.cwd()) {
	process.chdir(canonicalCwd);
}

const viteBin = path.join(canonicalCwd, 'node_modules', 'vite', 'bin', 'vite.js');
const args = [viteBin, ...process.argv.slice(2)];

const child = spawn(process.execPath, args, {
	cwd: canonicalCwd,
	stdio: 'inherit',
	env: process.env
});

child.on('exit', (code, signal) => {
	if (signal) {
		process.kill(process.pid, signal);
		return;
	}

	process.exit(code ?? 0);
});

child.on('error', (error) => {
	console.error(error);
	process.exit(1);
});
