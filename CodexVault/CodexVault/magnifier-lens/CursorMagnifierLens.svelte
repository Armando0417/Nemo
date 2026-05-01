<script lang="ts">
	export let visible = false;
	export let size = 260;
	export let padding = 6;
	export let translateX = 0;
	export let translateY = 0;
	export let imageSrc = '';
	export let backgroundX = 0;
	export let backgroundY = 0;
	export let backgroundWidth = 0;
	export let backgroundHeight = 0;
</script>

<div
	class="magnifier-lens"
	class:visible
	style={`width: ${size}px; height: ${size}px; transform: translate3d(${translateX}px, ${translateY}px, 0);`}
>
	<div
		class="magnifier-zoom"
		style={`inset: ${padding}px; background-image: url('${imageSrc}'); background-position: ${backgroundX}px ${backgroundY}px; background-size: ${backgroundWidth}px ${backgroundHeight}px;`}
	></div>
	<div class="magnifier-highlight"></div>
</div>

<style>
	.magnifier-lens {
		position: fixed;
		top: 0;
		left: 0;
		display: none;
		overflow: hidden;
		border-radius: 50%;
		pointer-events: none;
		z-index: 200;
		will-change: transform;
		border: 1px solid rgba(255, 255, 255, 0.4);
		box-shadow:
			0 0 0 1px rgba(255, 255, 255, 0.1),
			0 10px 30px rgba(0, 0, 0, 0.4),
			0 0 3px rgba(255, 255, 255, 0.1) inset;
		backface-visibility: hidden;
	}

	.magnifier-lens.visible {
		display: block;
	}

	.magnifier-zoom {
		position: absolute;
		border-radius: 50%;
		overflow: hidden;
		background-repeat: no-repeat;
	}

	.magnifier-highlight {
		position: absolute;
		inset: 0;
		border-radius: 50%;
		pointer-events: none;
		mix-blend-mode: overlay;
		opacity: 0.9;
		background:
			radial-gradient(120% 90% at 20% 20%, rgba(255, 255, 255, 0.22), transparent 55%),
			radial-gradient(120% 90% at 70% 80%, rgba(0, 0, 0, 0.18), transparent 55%);
	}
</style>
