<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/codex_vault.png';

	let { children } = $props();
</script>

<svelte:head>
	<title>Codex Vault</title>
	<link rel="icon" href={favicon} />
</svelte:head>
{@render children()}
