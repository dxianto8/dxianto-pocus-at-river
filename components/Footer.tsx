type FooterProps = {
  text: string;
};

export function Footer({ text }: FooterProps) {
  return (
    <footer className="mt-24 border-t border-mist px-6 py-10 text-center font-serif text-[13px] italic tracking-[0.04em] text-stone">
      {text}
    </footer>
  );
}
