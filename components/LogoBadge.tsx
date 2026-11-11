import type { Badge } from "@/content/site";

type LogoBadgeProps = Badge & { className?: string };

/**
 * Round badge with text curving around the edge.
 * Top text sits on an arc over the top (reads left to right, letters pointing out);
 * bottom text sits on an arc under the bottom (reads left to right, letters pointing in),
 * so both stay upright.
 */
export function LogoBadge({ topText, bottomText, monogram, label, className }: LogoBadgeProps) {
  return (
    <svg viewBox="0 0 200 200" role="img" aria-label={label} className={className}>
      <defs>
        <path id="badge-top-arc" d="M 32 100 A 68 68 0 0 1 168 100" />
        <path id="badge-bottom-arc" d="M 21 100 A 79 79 0 0 0 179 100" />
      </defs>

      <circle cx="100" cy="100" r="98" className="fill-forest" />

      <g className="fill-cream font-sans" fontSize="13" letterSpacing="3.2">
        <text textAnchor="middle">
          <textPath href="#badge-top-arc" startOffset="50%">
            {topText.toUpperCase()}
          </textPath>
        </text>
        <text textAnchor="middle" fontSize="10.5" letterSpacing="2.6">
          <textPath href="#badge-bottom-arc" startOffset="50%">
            {bottomText.toUpperCase()}
          </textPath>
        </text>
      </g>

      <text
        x="100"
        y="100"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="84"
        className="fill-cream font-serif"
      >
        {monogram}
      </text>
    </svg>
  );
}
