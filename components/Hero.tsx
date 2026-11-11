import Image from "next/image";

import type { Badge, Photo } from "@/content/site";

import { LogoBadge } from "./LogoBadge";

type HeroProps = {
  image: Photo;
  badge: Badge;
  address: string;
};

export function Hero({ image, badge, address }: HeroProps) {
  return (
    <div className="mx-auto max-w-[1440px] sm:px-10 lg:px-20">
      <div className="relative flex h-[70svh] min-h-[440px] flex-col items-center justify-center overflow-hidden px-6 sm:h-[560px] lg:h-[740px]">
        <Image
          src={image.src}
          alt={image.alt}
          fill
          loading="eager"
          fetchPriority="high"
          placeholder="blur"
          sizes="(min-width: 1440px) 1280px, (min-width: 640px) calc(100vw - 80px), 100vw"
          className="object-cover"
        />
        {/* Darkens the photo a little so the white address line stays readable. */}
        <div aria-hidden className="absolute inset-0 bg-black/30" />

        <h1 className="relative">
          <LogoBadge {...badge} className="size-40 drop-shadow-lg sm:size-52 lg:size-60" />
        </h1>
        <p className="relative mt-8 text-center font-serif text-lg italic tracking-[0.08em] text-white sm:text-xl">
          {address}
        </p>
      </div>
    </div>
  );
}
