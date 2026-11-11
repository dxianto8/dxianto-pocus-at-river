import Image from "next/image";

import type { SocialLink } from "@/content/site";

type TopBarProps = {
  label: string;
  href: string;
  socials: SocialLink[];
};

/**
 * Sticky white bar. On wide screens it copies the original's fixed positions:
 * the label 80px from the left edge, the icons 402px right of the centre line.
 */
export function TopBar({ label, href, socials }: TopBarProps) {
  return (
    <header className="sticky top-0 z-50 h-16 bg-white sm:h-[79px]">
      <div className="flex h-full items-center justify-between px-5 sm:px-10 desk:block desk:px-0">
        <a
          href={href}
          className="flex h-10 items-center text-[13px] leading-[22.4px] text-charcoal sm:text-base desk:absolute desk:top-5 desk:left-20"
        >
          {label}
        </a>
        <ul className="flex items-center gap-2.5 desk:absolute desk:top-5 desk:left-[calc(50%+402px)]">
          {socials.map(({ name, href: socialHref, icon }) => (
            <li key={name}>
              <a
                href={socialHref}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={name}
                className="block transition-opacity hover:opacity-70"
              >
                <Image src={icon} alt="" className="size-8 sm:size-[39px]" />
              </a>
            </li>
          ))}
        </ul>
      </div>
    </header>
  );
}
