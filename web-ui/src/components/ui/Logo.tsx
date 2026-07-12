import React from 'react';

/**
 * Minder AI brand mark — the orbit-and-spark from the brand kit: two thin
 * elliptical orbit rings crossing on a diagonal, with a four-point star
 * where they converge. Vector-traced from the kit's raster logo so it scales
 * crisply at any size.
 *
 * Renders in `currentColor`: white on cosmic surfaces, ink on daybreak —
 * exactly the kit's two approved tones. Size/color via className.
 */
export function BrandMark({
  className = 'h-6 w-6',
  ...rest
}: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 256 256"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden
      focusable="false"
      {...rest}
    >
      {/* Orbit rings */}
      <g stroke="currentColor" strokeWidth="7" fill="none">
        <ellipse cx="116" cy="112" rx="86" ry="44" transform="rotate(-45 116 112)" />
        <ellipse cx="124" cy="122" rx="86" ry="44" transform="rotate(-30 124 122)" />
      </g>
      {/* Four-point spark */}
      <path
        d="M162 106 Q168.5 146 206 154 Q168.5 162 162 202 Q155.5 162 118 154 Q155.5 146 162 106 Z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}
