import { redirect } from "next/navigation";

/**
 * / — Ichor lands the user STRAIGHT into the product (the day's session reads),
 * never on a marketing page (vision §9.4 : "je dois retrouver sur mon
 * application web l'ensemble des informations"). The cockpit is the home.
 */
export default function Home() {
  redirect("/briefing");
}
