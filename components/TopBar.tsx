import type { SocialLink } from "@/content/site";

import { FacebookIcon, InstagramIcon } from "./icons";

const icons = { Instagram: InstagramIcon, Facebook: FacebookIcon } as const;

type TopBarProps = {
  label: string;
  href: string;
  socials: SocialLink[];
};

export function TopBar({ label, href, socials }: TopBarProps) {
  return (
    <header className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-5 sm:h-20 sm:px-10 lg:px-20">
      <a
        href={href}
        className="text-[12px] uppercase tracking-[0.04em] text-charcoal transition-colors hover:text-forest sm:text-[13px]"
      >
        {label}
      </a>
      <ul className="flex items-center gap-3">
        {socials.map(({ name, href: socialHref }) => {
          const Icon = icons[name];
          return (
            <li key={name}>
              <a
                href={socialHref}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={name}
                className="block p-1 text-black transition-colors hover:text-forest"
              >
                <Icon aria-hidden className="size-6 sm:size-7" />
              </a>
            </li>
          );
        })}
      </ul>
    </header>
  );
}
