type FooterProps = {
  text: string;
};

/** Like the original, the © bar stays pinned to the bottom of the screen. */
export function Footer({ text }: FooterProps) {
  return (
    <footer className="sticky bottom-0 z-50 h-12 bg-white pt-[15px] text-center font-serif text-[13px] leading-[17px] tracking-[0.08em] text-stone italic sm:h-20 sm:pt-11 sm:text-sm">
      {text}
    </footer>
  );
}
