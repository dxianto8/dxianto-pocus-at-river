import { Button } from "@/components/Button";
import { Footer } from "@/components/Footer";
import { Gallery } from "@/components/Gallery";
import { Hero } from "@/components/Hero";
import { SectionDivider } from "@/components/SectionDivider";
import { SectionHeading } from "@/components/SectionHeading";
import { TopBar } from "@/components/TopBar";
import { site } from "@/content/site";

function Prose({ paragraphs }: { paragraphs: string[] }) {
  return (
    <div className="mx-auto mt-10 max-w-[620px] space-y-7 px-6 text-base leading-7 sm:mt-14">
      {paragraphs.map((text) => (
        <p key={text}>{text}</p>
      ))}
    </div>
  );
}

export default function Home() {
  const { topBar, socials, hero, about, gallery, contact, footer } = site;
  const headingId = (sectionId: string) => `${sectionId}-heading`;

  return (
    <>
      <TopBar label={topBar.label} href={topBar.href} socials={socials} />

      <main>
        <Hero image={hero.image} badge={hero.badge} address={hero.address} />

        <section id={about.id} aria-labelledby={headingId(about.id)} className="scroll-mt-6 pt-14">
          <SectionDivider />
          <SectionHeading id={headingId(about.id)}>{about.heading}</SectionHeading>
          <Prose paragraphs={about.paragraphs} />
          <div className="mt-8 text-center">
            <Button href={about.cta.href}>{about.cta.label}</Button>
          </div>
        </section>

        <section id={gallery.id} aria-labelledby={headingId(gallery.id)} className="pt-20 sm:pt-24">
          <SectionDivider />
          <SectionHeading id={headingId(gallery.id)}>{gallery.heading}</SectionHeading>
          <Gallery images={gallery.images} />
          <Prose paragraphs={gallery.paragraphs} />
        </section>

        <section id={contact.id} aria-labelledby={headingId(contact.id)} className="pt-20 sm:pt-24">
          <SectionDivider />
          <SectionHeading id={headingId(contact.id)}>{contact.heading}</SectionHeading>
          <div className="mt-8 text-center">
            <Button href={contact.cta.href}>{contact.cta.label}</Button>
          </div>
        </section>
      </main>

      <Footer text={footer} />
    </>
  );
}
