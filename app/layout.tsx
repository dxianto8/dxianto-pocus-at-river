import type { Metadata } from "next";
import { Bodoni_Moda, Mulish, Raleway } from "next/font/google";

import { site } from "@/content/site";

import "./globals.css";

const raleway = Raleway({
  variable: "--font-raleway",
  subsets: ["latin"],
});

// Stand-ins for the paid fonts Wix licenses for the original site:
// Bodoni Moda italic for Didot italic, Mulish Light for Avenir 35 Light.
const bodoni = Bodoni_Moda({
  variable: "--font-bodoni",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

const mulish = Mulish({
  variable: "--font-mulish",
  subsets: ["latin"],
  weight: "300",
});

export const metadata: Metadata = {
  title: site.meta.title,
  description: site.meta.description,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${raleway.variable} ${bodoni.variable} ${mulish.variable} antialiased`}
    >
      <body className="bg-white font-sans text-charcoal">{children}</body>
    </html>
  );
}
