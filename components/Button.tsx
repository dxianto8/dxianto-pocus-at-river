import type { ReactNode } from "react";

type ButtonProps = {
  href: string;
  children: ReactNode;
};

/** A link styled as the site's solid charcoal button. */
export function Button({ href, children }: ButtonProps) {
  return (
    <a
      href={href}
      className="inline-flex h-10 items-center bg-charcoal px-7 text-sm font-medium tracking-[0.03em] text-white transition-colors hover:bg-forest"
    >
      {children}
    </a>
  );
}
