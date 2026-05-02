import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ichor",
  description: "Autonomous market intelligence — Phase 0",
  robots: { index: false, follow: false }, // pre-launch: keep out of search engines
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body className="bg-neutral-950 text-neutral-100 antialiased">
        {children}
      </body>
    </html>
  );
}
