import { Button } from "@/components/Button";
import { Footer } from "@/components/Footer";
import { Gallery } from "@/components/Gallery";
import { Hero } from "@/components/Hero";
import { Prose } from "@/components/Prose";
import { SectionDivider } from "@/components/SectionDivider";
import { SectionHeading } from "@/components/SectionHeading";
import { TopBar } from "@/components/TopBar";
import { site } from "@/content/site";

const headingId = (sectionId: string) => `${sectionId}-heading`;

// Vertical gaps (in px) are the ones measured on the original at 1440px wide.
export default function Home() {
  const { topBar, socials, hero, about, gallery, contact, footer } = site;

  return (
    <>
      <TopBar label={topBar.label} href={topBar.href} socials={socials} />

      <main className="pb-[57px]">
        <Hero image={hero.image} badge={hero.badge} address={hero.address} />

        <section id={about.id} aria-labelledby={headingId(about.id)}>
          <SectionDivider />
          <SectionHeading id={headingId(about.id)} tone="forest">
            {about.heading}
          </SectionHeading>
          <Prose paragraphs={about.paragraphs} className="mt-12 sm:mt-[72px]" />
          <div className="mt-6 text-center">
            <Button href={about.cta.href} className="w-[247px]">
              {about.cta.label}
            </Button>
          </div>
        </section>

        <section id={gallery.id} aria-labelledby={headingId(gallery.id)} className="pt-[75px]">
          <SectionDivider />
          <SectionHeading id={headingId(gallery.id)} className="mt-[33px]">
            {gallery.heading}
          </SectionHeading>
          <Gallery images={gallery.images} className="mt-10" />
          <Prose paragraphs={gallery.paragraphs} className="mt-12" />
        </section>

        <section id={contact.id} aria-labelledby={headingId(contact.id)} className="pt-[62px]">
          <SectionDivider />
          <SectionHeading id={headingId(contact.id)}>{contact.heading}</SectionHeading>
          <div className="mt-[42px] text-center">
            <Button href={contact.cta.href} className="w-[142px]">
              {contact.cta.label}
            </Button>
          </div>
        </section>
      </main>

      <Footer text={footer} />
    </>
  );
}
