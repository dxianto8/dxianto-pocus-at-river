import Image from "next/image";

import type { Photo } from "@/content/site";

type GalleryProps = {
  images: Photo[];
  className?: string;
};

/**
 * Three 370×256 photos with 18px gaps on wide screens; one column on phones.
 * The original's row sits 9px left of centre, which the desk:-translate-x copies.
 */
export function Gallery({ images, className = "" }: GalleryProps) {
  return (
    <ul
      data-testid="gallery"
      className={`mx-auto grid max-w-[1226px] grid-cols-1 gap-4 px-6 sm:grid-cols-3 sm:gap-[18px] sm:px-10 desk:-translate-x-[9px] ${className}`}
    >
      {images.map((image) => (
        <li key={image.src.src} className="relative aspect-[370/256] overflow-hidden">
          <Image
            src={image.src}
            alt={image.alt}
            fill
            placeholder="blur"
            sizes="(min-width: 1200px) 370px, (min-width: 640px) 31vw, 100vw"
            className="object-cover"
          />
        </li>
      ))}
    </ul>
  );
}
