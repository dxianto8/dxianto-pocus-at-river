import Image from "next/image";

import type { Photo } from "@/content/site";

import { Parallax } from "./Parallax";

type HeroProps = {
  image: Photo;
  badge: Photo;
  address: string;
};

/**
 * Matches the original: an 821px-tall panel with 80px side margins. The photo is shown at
 * 71% opacity over charcoal and lags behind the scroll. The badge and address sit at fixed
 * heights from the top of the panel.
 */
export function Hero({ image, badge, address }: HeroProps) {
  return (
    <div
      data-testid="hero"
      className="relative h-[520px] overflow-hidden bg-charcoal sm:mx-10 sm:h-[821px] desk:mx-20"
    >
      <Parallax
        data-testid="hero-photo"
        className="absolute inset-x-0 -top-[63px] h-[max(100svh,520px)] opacity-71 will-change-transform sm:h-[max(100svh,821px)]"
      >
        <Image
          src={image.src}
          alt={image.alt}
          fill
          loading="eager"
          fetchPriority="high"
          placeholder="blur"
          sizes="(min-width: 1200px) calc(100vw - 160px), (min-width: 640px) calc(100vw - 80px), 100vw"
          className="object-cover"
        />
      </Parallax>

      <h1 className="absolute top-[110px] left-1/2 -translate-x-1/2 sm:top-[156px]">
        <Image
          src={badge.src}
          alt={badge.alt}
          loading="eager"
          sizes="245px"
          className="size-40 sm:size-[245px]"
        />
      </h1>
      <p className="absolute inset-x-0 top-[310px] px-6 text-center font-serif text-lg leading-[22px] tracking-[0.08em] text-mist italic sm:top-[450px]">
        {address}
      </p>
    </div>
  );
}
