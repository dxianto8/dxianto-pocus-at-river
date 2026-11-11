import Link from "next/link";
import type { ReactNode } from "react";

type ButtonProps = {
  href: string;
  /** The original's buttons have fixed widths, e.g. "w-[247px]". */
  className?: string;
  children: ReactNode;
};

const styles =
  "inline-flex h-10 items-center justify-center bg-ink px-7 font-button text-[15px] font-light tracking-[0.05em] text-white transition-colors hover:bg-forest";

/** A link styled as the site's solid dark button. Internal links use client-side navigation. */
export function Button({ href, className = "", children }: ButtonProps) {
  if (href.startsWith("/")) {
    return (
      <Link href={href} className={`${styles} ${className}`}>
        {children}
      </Link>
    );
  }
  return (
    <a href={href} className={`${styles} ${className}`}>
      {children}
    </a>
  );
}
