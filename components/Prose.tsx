type ProseProps = {
  paragraphs: string[];
  className?: string;
};

/** The centred 600px text column (20px Raleway on 28px lines, as on the original). */
export function Prose({ paragraphs, className = "" }: ProseProps) {
  return (
    <div
      className={`mx-auto max-w-[648px] space-y-7 px-6 text-[17px] leading-[26px] sm:text-xl sm:leading-7 ${className}`}
    >
      {paragraphs.map((text) => (
        <p key={text}>{text}</p>
      ))}
    </div>
  );
}
