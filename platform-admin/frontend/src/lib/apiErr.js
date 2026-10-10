// FastAPI error 'detail' can be a string, an array of Pydantic error objects
// {type, loc, msg, input, url}, or an object (e.g. {message}). Always return a
// plain string so sonner/React never tries to render an object child (crash).
export function apiErr(e, fallback = "Terjadi kesalahan") {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x?.loc ? `${x.loc[x.loc.length - 1]}: ${x.msg}` : x?.msg || "Tidak valid")).join("; ");
  if (d && typeof d === "object") return d.message || d.msg || JSON.stringify(d);
  return fallback;
}
