import "./globals.css";

export const metadata = {
  title: "Reel Studio",
  description: "Instagram downloader and branding studio",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
