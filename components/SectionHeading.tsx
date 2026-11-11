import type { ReactNode } from "react";

type SectionHeadingProps = {
  id: string;
  children: ReactNode;
};

export function SectionHeading({ id, children }: SectionHeadingProps) {
  return (
    <h2
      id={id}
      className="mt-8 px-6 text-center font-serif text-lg italic tracking-[0.12em] text-stone sm:text-[19px]"
    >
      {children}
    </h2>
  );
}
