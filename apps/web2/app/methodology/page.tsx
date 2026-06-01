import { redirect } from "next/navigation";

/**
 * /methodology — neutralised (vision §9.5 : NO separate "méthodologie" /
 * explainer surface ; the pedagogy must live woven into the data itself).
 * Any lingering link lands the user back in the product cockpit.
 */
export default function MethodologyPage() {
  redirect("/briefing");
}
