import { useEffect } from "react";

// Legal pages live as static HTML (public/privacy.html, public/terms.html) so crawlers (e.g. Google OAuth verification) see full content without JavaScript.
function Redirect({ to }) {
  useEffect(() => { window.location.replace(to); }, [to]);
  return null;
}

export function PrivacyPolicy() { return <Redirect to="/privacy.html" />; }
export function TermsOfService() { return <Redirect to="/terms.html" />; }
