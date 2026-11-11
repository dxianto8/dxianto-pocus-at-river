"use client";

import { useEffect, useRef, type ReactNode } from "react";

type ParallaxProps = {
  /**
   * How far the layer moves down per pixel scrolled. The original site's hero
   * photo uses 0.8, so on screen it travels at 20% of the page's scroll speed.
   */
  lag?: number;
  className?: string;
  children: ReactNode;
  "data-testid"?: string;
};

/** Moves its contents down as the page scrolls. Turned off for users who prefer reduced motion. */
export function Parallax({ lag = 0.8, className, children, ...rest }: ParallaxProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const layer = ref.current;
    if (!layer) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;

    const update = () => {
      frame = 0;
      if (reducedMotion.matches) {
        layer.style.transform = "";
        return;
      }
      // Past two screens the hero is long gone, so stop moving it.
      const scrolled = Math.min(window.scrollY, window.innerHeight * 2);
      layer.style.transform = `translate3d(0, ${scrolled * lag}px, 0)`;
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    reducedMotion.addEventListener("change", update);
    return () => {
      window.removeEventListener("scroll", onScroll);
      reducedMotion.removeEventListener("change", update);
      cancelAnimationFrame(frame);
    };
  }, [lag]);

  return (
    <div ref={ref} className={className} {...rest}>
      {children}
    </div>
  );
}
