import "./globals.css";

export const metadata = {
  title: "Fresh Token Radar",
  description:
    "Tokens in their first smart-money hour — young tokens where Nansen-labeled smart money is placing early bets.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
