import Image from "next/image";

import type { Photo } from "@/content/site";

type GalleryProps = {
  images: Photo[];
};

export function Gallery({ images }: GalleryProps) {
  return (
    <ul
      data-testid="gallery"
      className="mx-auto mt-10 grid max-w-[1190px] grid-cols-1 gap-4 px-6 sm:grid-cols-3 sm:gap-[18px] sm:px-10"
    >
      {images.map((image) => (
        <li key={image.src.src} className="relative aspect-[370/256] overflow-hidden">
          <Image
            src={image.src}
            alt={image.alt}
            fill
            placeholder="blur"
            sizes="(min-width: 1190px) 370px, (min-width: 640px) 31vw, 100vw"
            className="object-cover"
          />
        </li>
      ))}
    </ul>
  );
}
