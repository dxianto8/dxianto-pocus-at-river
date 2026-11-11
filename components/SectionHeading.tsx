import type { ReactNode } from "react";

type SectionHeadingProps = {
  id: string;
  /** The original colours its first heading forest green and the rest grey. */
  tone?: "forest" | "stone";
  className?: string;
  children: ReactNode;
};

const tones = { forest: "text-forest", stone: "text-stone" } as const;

export function SectionHeading({ id, tone = "stone", className = "mt-8", children }: SectionHeadingProps) {
  return (
    <h2
      id={id}
      className={`px-6 text-center font-serif text-lg leading-[22px] tracking-[0.08em] italic ${tones[tone]} ${className}`}
    >
      {children}
    </h2>
  );
}
