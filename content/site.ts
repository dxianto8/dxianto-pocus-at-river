import type { StaticImageData } from "next/image";

import badge from "@/assets/images/badge.png";
import facebook from "@/assets/images/facebook.png";
import galleryDance from "@/assets/images/gallery-dance.jpg";
import galleryHall from "@/assets/images/gallery-hall.jpg";
import hero from "@/assets/images/hero.jpg";
import instagram from "@/assets/images/instagram.png";

export type Photo = {
  src: StaticImageData;
  alt: string;
};

export type SocialLink = {
  name: "Instagram" | "Facebook";
  href: string;
  icon: StaticImageData;
};

export type CallToAction = {
  label: string;
  href: string;
};

export type SiteContent = {
  meta: { title: string; description: string };
  email: string;
  topBar: { label: string; href: string };
  socials: SocialLink[];
  hero: { image: Photo; badge: Photo; address: string };
  about: { id: string; heading: string; paragraphs: string[]; cta: CallToAction };
  gallery: { id: string; heading: string; images: Photo[]; paragraphs: string[] };
  contact: { id: string; heading: string; cta: CallToAction };
  footer: string;
};

const email = "events@pocusatriver.com";
const enquiryHref = `mailto:${email}?subject=${encodeURIComponent("Event Inquiry")}`;

const heroPhoto: Photo = {
  src: hero,
  alt: "A styled reception table with roses, glassware, a slate plate and a dessert topped with nuts and pomegranate",
};

export const site: SiteContent = {
  meta: {
    title: "HOME | Pocus At River",
    description:
      "Weddings and events in the Historic Pocus Motors Building, 100 S. River Street, Downtown Aurora IL.",
  },
  email,
  topBar: { label: "EXPLORE POCUS AT RIVER", href: "/" },
  socials: [
    { name: "Instagram", href: "https://www.instagram.com/pocusatriver", icon: instagram },
    { name: "Facebook", href: "https://www.facebook.com/pocusatriver", icon: facebook },
  ],
  hero: {
    image: heroPhoto,
    badge: { src: badge, alt: "Pocus at River, weddings & events" },
    address: "100 S. River Street, Downtown Aurora IL",
  },
  about: {
    id: "about",
    heading: "Host Your Event at the Historic Pocus Motors Building",
    paragraphs: [
      `Say "I do" in one of downtown Aurora's most distinctive event spaces. Pocus at River sits inside the Historic Pocus Motors Building, where soaring windows, exposed brick, and original architectural details give your wedding day a backdrop you won't find in a typical ballroom. From an intimate ceremony or a reception for two hundred guests, the layout flexes to fit your vision without losing the character that makes it worth booking.`,
      `Downtown Aurora puts riverfront views, and walkable restaurants right outside the door, so out-of-town family can grab dinner the night before and coffee the morning after without needing a car. Reserve your date early, weekend slots at Pocus at River go fast during peak wedding season.`,
    ],
    cta: { label: "Enquire About Your Event", href: "/book" },
  },
  gallery: {
    id: "gallery",
    heading: "Tell Us About Your Event",
    images: [
      heroPhoto,
      {
        src: galleryDance,
        alt: "Wedding guests dancing and cheering on a packed dance floor",
      },
      {
        src: galleryHall,
        alt: "A long candlelit banquet table in the venue's industrial hall, with black chairs and exposed ductwork",
      },
    ],
    paragraphs: [
      `Looking for a corporate event space in downtown Aurora that doesn't feel like every other hotel ballroom? Pocus at River, set inside the Historic Pocus Motors Building, pairs industrial-chic architecture with a floor plan ideal for client dinners, product launches, team celebrations, and holiday parties.`,
      `The downtown Aurora location makes logistics easy with parking, nearby hotels for traveling guests, and restaurants within walking distance for an after-party. If you're hosting fifty coworkers for a holiday gathering or a few hundred for a company milestone, Pocus at River can be reserved for the date you need. December weekends book up quickly, so it's worth locking in your date now.`,
    ],
  },
  contact: {
    id: "contact",
    heading: "Get in Touch",
    cta: { label: "Email Us", href: enquiryHref },
  },
  footer: "© 2026 by Pocus at River",
};
