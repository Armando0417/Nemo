#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/CodexVault"
BACKEND_DIR="$ROOT_DIR/CodexVaultIndexer"
BACKEND_VENV_DIR="$BACKEND_DIR/venv"

load_env_file() {
	local env_file="$1"
	if [[ -f "$env_file" ]]; then
		set -a
		# shellcheck disable=SC1090
		source "$env_file"
		set +a
	fi
}

load_env_file "$BACKEND_DIR/.env"
load_env_file "$FRONTEND_DIR/.env"

BACKEND_HOST="${CODEX_VAULT_BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${CODEX_VAULT_BACKEND_PORT:-6220}"
FRONTEND_HOST="${CODEX_VAULT_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${CODEX_VAULT_FRONTEND_PORT:-6221}"
PYTHON_BIN="${CODEX_VAULT_PYTHON_BIN:-}"

require_command() {
	local command_name="$1"
	if ! command -v "$command_name" >/dev/null 2>&1; then
		echo "Missing required command: $command_name" >&2
		exit 1
	fi
}

bootstrap_backend() {
	local system_python="${PYTHON_BIN:-python3}"

	require_command "$system_python"

	if [[ ! -x "$BACKEND_VENV_DIR/bin/python" && ! -x "$BACKEND_VENV_DIR/Scripts/python.exe" ]]; then
		echo "Creating backend virtual environment..."
		"$system_python" -m venv "$BACKEND_VENV_DIR"
	fi

	if [[ -x "$BACKEND_VENV_DIR/bin/python" ]]; then
		PYTHON_BIN="$BACKEND_VENV_DIR/bin/python"
	else
		PYTHON_BIN="$BACKEND_VENV_DIR/Scripts/python.exe"
	fi

	if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
		echo "Bootstrapping pip in backend virtual environment..."
		if ! "$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1; then
			echo "Failed to install pip in the backend virtual environment." >&2
			echo "Install your system venv package first, for example:" >&2
			echo "  sudo apt install python3-venv python3-pip" >&2
			exit 1
		fi
	fi

	if ! "$PYTHON_BIN" -m uvicorn --version >/dev/null 2>&1; then
		echo "Installing backend dependencies..."
		"$PYTHON_BIN" -m pip install --upgrade pip
		"$PYTHON_BIN" -m pip install -r "$BACKEND_DIR/requirements.txt"
	fi
}

bootstrap_frontend() {
	require_command npm

	if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
		echo "Installing frontend dependencies..."
		(
			cd "$FRONTEND_DIR"
			npm install
		)
	fi
}

if [[ -z "$PYTHON_BIN" ]]; then
	if [[ -x "$BACKEND_VENV_DIR/bin/python" ]]; then
		PYTHON_BIN="$BACKEND_VENV_DIR/bin/python"
	elif [[ -x "$BACKEND_VENV_DIR/Scripts/python.exe" ]]; then
		PYTHON_BIN="$BACKEND_VENV_DIR/Scripts/python.exe"
	else
		PYTHON_BIN="python3"
	fi
fi

bootstrap_backend
bootstrap_frontend

cleanup() {
	if [[ -n "${BACKEND_PID:-}" ]]; then
		kill "$BACKEND_PID" 2>/dev/null || true
	fi

	if [[ -n "${FRONTEND_PID:-}" ]]; then
		kill "$FRONTEND_PID" 2>/dev/null || true
	fi
}

trap cleanup EXIT INT TERM

(
	cd "$BACKEND_DIR"
	exec "$PYTHON_BIN" -m uvicorn main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

(
	cd "$FRONTEND_DIR"
	npm run build
	exec npm run preview -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

wait -n "$BACKEND_PID" "$FRONTEND_PID"
