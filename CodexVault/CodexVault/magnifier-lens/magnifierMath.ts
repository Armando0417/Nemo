export type RectLike = {
	left: number;
	top: number;
	width: number;
	height: number;
};

export type CursorMagnifierInput = {
	active: boolean;
	cursorX: number;
	cursorY: number;
	imageRect: RectLike;
	imageSrc: string;
	lensSize: number;
	zoomLevel: number;
	viewportWidth: number;
	viewportHeight: number;
	padding?: number;
};

export type CursorMagnifierFrame = {
	size: number;
	padding: number;
	imageSrc: string;
	lensX: number;
	lensY: number;
	backgroundX: number;
	backgroundY: number;
	backgroundWidth: number;
	backgroundHeight: number;
};

export function clamp(value: number, min: number, max: number) {
	return Math.max(min, Math.min(max, value));
}

export function buildCursorMagnifierFrame(
	input: CursorMagnifierInput
): CursorMagnifierFrame | null {
	if (!input.active) {
		return null;
	}

	const { cursorX, cursorY, imageRect, imageSrc, lensSize, zoomLevel, viewportWidth, viewportHeight } =
		input;
	const padding = input.padding ?? 6;
	const overImage =
		cursorX >= imageRect.left &&
		cursorX <= imageRect.left + imageRect.width &&
		cursorY >= imageRect.top &&
		cursorY <= imageRect.top + imageRect.height;

	if (!overImage) {
		return null;
	}

	const xInImage = clamp(cursorX - imageRect.left, 0, imageRect.width);
	const yInImage = clamp(cursorY - imageRect.top, 0, imageRect.height);
	const halfLens = lensSize / 2;
	const inner = lensSize - padding * 2;

	return {
		size: lensSize,
		padding,
		imageSrc,
		lensX: clamp(cursorX - halfLens, 0, viewportWidth - lensSize),
		lensY: clamp(cursorY - halfLens, 0, viewportHeight - lensSize),
		backgroundX: Math.round(-(xInImage * zoomLevel) + inner / 2),
		backgroundY: Math.round(-(yInImage * zoomLevel) + inner / 2),
		backgroundWidth: Math.round(imageRect.width * zoomLevel),
		backgroundHeight: Math.round(imageRect.height * zoomLevel)
	};
}
