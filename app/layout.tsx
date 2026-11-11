import type { Metadata } from "next";
import { Bodoni_Moda, Raleway } from "next/font/google";

import { site } from "@/content/site";

import "./globals.css";

const raleway = Raleway({
  variable: "--font-raleway",
  subsets: ["latin"],
});

// Bodoni Moda stands in for Didot, which the original site uses but is not free to use.
const bodoni = Bodoni_Moda({
  variable: "--font-bodoni",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: site.meta.title,
  description: site.meta.description,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${raleway.variable} ${bodoni.variable} antialiased`}>
      <body className="bg-white font-sans text-charcoal">{children}</body>
    </html>
  );
}
