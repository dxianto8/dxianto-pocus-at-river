import type { StaticImageData } from "next/image";

import galleryHall from "@/assets/images/gallery-hall.jpg";
import galleryTable from "@/assets/images/gallery-table.jpg";
import galleryToast from "@/assets/images/gallery-toast.jpg";
import hero from "@/assets/images/hero.jpg";

export type Photo = {
  src: StaticImageData;
  alt: string;
};

export type SocialLink = {
  name: "Instagram" | "Facebook";
  href: string;
};

export type CallToAction = {
  label: string;
  href: string;
};

export type Badge = {
  topText: string;
  bottomText: string;
  monogram: string;
  /** Read out by screen readers in place of the badge artwork. */
  label: string;
};

export type SiteContent = {
  meta: { title: string; description: string };
  topBar: { label: string; href: string };
  socials: SocialLink[];
  hero: { image: Photo; badge: Badge; address: string };
  about: { id: string; heading: string; paragraphs: string[]; cta: CallToAction };
  gallery: { id: string; heading: string; images: Photo[]; paragraphs: string[] };
  contact: { id: string; heading: string; cta: CallToAction };
  footer: string;
};

// Everything below is fictional: the venue, the town, the address and the email.
const email = "hello@example.com";
const enquiryHref = `mailto:${email}?subject=${encodeURIComponent("Event Inquiry")}`;

export const site: SiteContent = {
  meta: {
    title: "The Coachworks · Weddings & Events in Millbrook",
    description:
      "A restored carriage workshop in the heart of Millbrook, hosting weddings and corporate events for up to 200 guests. (A fictional venue built as a practice project.)",
  },
  topBar: { label: "Explore The Coachworks", href: "#about" },
  socials: [
    { name: "Instagram", href: "https://www.instagram.com/" },
    { name: "Facebook", href: "https://www.facebook.com/" },
  ],
  hero: {
    image: {
      src: hero,
      alt: "A long reception table set with glassware, white plates and bright bouquets of flowers",
    },
    badge: {
      topText: "The Coachworks",
      bottomText: "Weddings & Events",
      monogram: "C",
      label: "The Coachworks, weddings & events",
    },
    address: "12 Mill Street, Millbrook",
  },
  about: {
    id: "about",
    heading: "Host Your Event at the Historic Coachworks Building",
    paragraphs: [
      "Get married somewhere with a story. The Coachworks was built in 1908 to repair horse-drawn carriages, and the bones are still here: hand-laid brick, timber trusses and a wall of factory windows that fills the room with afternoon light. It suits a ceremony of thirty as well as a reception of two hundred, and the floor can be arranged around the day you have in mind.",
      "Step outside and you are in the middle of Millbrook, with the riverside path, cafés and two hotels a short walk away, so guests can settle in the night before and find breakfast the morning after without calling a cab. Saturdays from May to October fill up first, so it is worth getting in touch early.",
    ],
    cta: { label: "Enquire About Your Event", href: enquiryHref },
  },
  gallery: {
    id: "gallery",
    heading: "Tell Us About Your Event",
    images: [
      {
        src: galleryTable,
        alt: "A white-linen banquet table lined with small vases of wildflowers and folded napkins",
      },
      {
        src: galleryToast,
        alt: "Guests raising glasses of white wine in a toast",
      },
      {
        src: galleryHall,
        alt: "A timber-beamed hall lit with warm string lights above a polished wooden floor",
      },
    ],
    paragraphs: [
      "Planning a company event and tired of hotel function rooms? The Coachworks gives your team somewhere with real character: an old workshop with an open floor that adapts to client dinners, product launches, awards nights and end-of-year parties.",
      "Getting there is simple, with parking on site, hotels within walking distance for visiting colleagues and plenty of places nearby to carry on afterwards. Whether you are hosting forty people for a seasonal lunch or two hundred for a company milestone, we will help you plan the room. December dates go quickly, so ask about availability early.",
    ],
  },
  contact: {
    id: "contact",
    heading: "Get in Touch",
    cta: { label: "Email Us", href: enquiryHref },
  },
  footer: "© 2026 The Coachworks · a fictional venue",
};
