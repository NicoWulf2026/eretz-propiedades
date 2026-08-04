const LOCAL_SITE_URL = "http://localhost:3000";

export function resolveSiteUrl(
  configured: string | undefined,
  productionDeployment = process.env.VERCEL_ENV === "production",
) {
  const candidate = configured?.trim() || LOCAL_SITE_URL;
  const url = new URL(candidate);
  const localHost = url.hostname === "localhost" || url.hostname === "127.0.0.1";
  if (productionDeployment && localHost) {
    throw new Error("NEXT_PUBLIC_SITE_URL must be a public HTTPS URL in production");
  }
  if (productionDeployment && url.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_SITE_URL must use HTTPS in production");
  }
  return url.origin;
}

export const siteUrl = resolveSiteUrl(process.env.NEXT_PUBLIC_SITE_URL);

